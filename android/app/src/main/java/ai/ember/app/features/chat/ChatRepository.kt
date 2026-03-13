package ai.ember.app.features.chat

import ai.ember.app.BuildConfig
import ai.ember.app.core.auth.AuthRepository
import ai.ember.app.core.models.ApiErrorBody
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.sse.EventSource
import okhttp3.sse.EventSourceListener
import okhttp3.sse.EventSources
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Repository handling chat message loading and SSE streaming.
 *
 * Message history uses Retrofit via [ChatApi].
 * SSE streaming uses OkHttp EventSource directly for real-time
 * AI responses, following the pattern from docs/standards/android.md.
 */
@Singleton
class ChatRepository @Inject constructor(
    private val chatApi: ChatApi,
    private val voiceApi: VoiceApi,
    private val okHttpClient: OkHttpClient,
    private val authRepository: AuthRepository,
    private val json: Json,
) {

    /**
     * Fetches paginated message history using cursor-based pagination.
     *
     * @param characterId The character to fetch messages for.
     * @param cursor Opaque base64 cursor for pagination, null for latest messages.
     * @param limit Number of messages per page (default 20).
     * @return [Result] with the response page or an error.
     */
    suspend fun getMessages(
        characterId: String,
        cursor: String?,
        limit: Int = 20,
    ): Result<ChatMessageListResponse> {
        return try {
            val response = chatApi.listMessages(characterId, cursor, limit)
            if (response.isSuccessful) {
                val body = response.body()
                if (body != null) {
                    Result.success(body)
                } else {
                    Result.failure(ChatException("Something went wrong. Please try again."))
                }
            } else {
                val errorMessage = parseErrorMessage(
                    response.errorBody()?.string(),
                    response.code(),
                )
                Result.failure(ChatException(errorMessage))
            }
        } catch (e: ChatException) {
            Result.failure(e)
        } catch (e: Exception) {
            Result.failure(
                ChatException("Connection failed. Please check your internet."),
            )
        }
    }

    /**
     * Streams an AI response via SSE for the given character.
     *
     * Uses OkHttp EventSource with callbackFlow to bridge the callback-based
     * EventSourceListener to a Kotlin Flow. Emits [SseEvent] for each SSE
     * data line. The flow completes when a "done" event is received or when
     * the connection is closed.
     *
     * @param characterId The character to send the message to.
     * @param content The user's message content.
     * @return Flow of [SseEvent] representing stream events.
     */
    fun streamMessage(characterId: String, content: String): Flow<SseEvent> = callbackFlow {
        val token = authRepository.getAccessToken()

        val requestBody = json.encodeToString(
            SendMessageRequest.serializer(),
            SendMessageRequest(content = content),
        ).toRequestBody("application/json".toMediaType())

        val request = Request.Builder()
            .url("${BuildConfig.API_BASE_URL}api/v1/characters/$characterId/messages")
            .post(requestBody)
            .apply {
                if (token != null) {
                    addHeader("Authorization", "Bearer $token")
                }
            }
            .addHeader("Accept", "text/event-stream")
            .build()

        val listener = object : EventSourceListener() {
            override fun onEvent(
                eventSource: EventSource,
                id: String?,
                type: String?,
                data: String,
            ) {
                if (data == "[DONE]") {
                    close()
                    return
                }
                try {
                    val event = json.decodeFromString<SseEvent>(data)
                    trySend(event)
                    if (event.type == "done") {
                        close()
                    }
                } catch (_: Exception) {
                    // Skip malformed events
                }
            }

            override fun onFailure(
                eventSource: EventSource,
                t: Throwable?,
                response: Response?,
            ) {
                close(
                    t ?: ChatException(
                        "SSE connection failed: ${response?.code ?: "unknown"}",
                    ),
                )
            }
        }

        val factory = EventSources.createFactory(okHttpClient)
        val eventSource = factory.newEventSource(request, listener)

        awaitClose { eventSource.cancel() }
    }

    /**
     * Gets a presigned S3 upload URL for an audio file.
     *
     * @param filename The audio filename (e.g., "voice_1234.m4a").
     * @return [Result] with [UploadUrlResponse] containing upload and file URLs.
     */
    suspend fun getUploadUrl(filename: String): Result<UploadUrlResponse> {
        return try {
            val response = voiceApi.getUploadUrl(
                UploadUrlRequest(
                    filename = filename,
                    contentType = AUDIO_CONTENT_TYPE,
                    type = AUDIO_MEDIA_TYPE,
                ),
            )
            if (response.isSuccessful) {
                val body = response.body()
                if (body != null) {
                    Result.success(body)
                } else {
                    Result.failure(ChatException("Failed to get upload URL."))
                }
            } else {
                val errorMessage = parseErrorMessage(
                    response.errorBody()?.string(),
                    response.code(),
                )
                Result.failure(ChatException(errorMessage))
            }
        } catch (e: Exception) {
            Result.failure(
                ChatException("Connection failed. Please check your internet."),
            )
        }
    }

    /**
     * Uploads an audio file to S3 using a presigned PUT URL.
     *
     * Performs a raw HTTP PUT with the file body and audio/mp4 content type.
     * Runs on [Dispatchers.IO] to avoid blocking the main thread.
     *
     * @param uploadUrl The presigned S3 PUT URL.
     * @param file The audio file to upload.
     * @return [Result] with Unit on success or an error.
     */
    suspend fun uploadAudioFile(uploadUrl: String, file: File): Result<Unit> {
        return withContext(Dispatchers.IO) {
            try {
                val requestBody = file.asRequestBody(AUDIO_CONTENT_TYPE.toMediaType())
                val request = Request.Builder()
                    .url(uploadUrl)
                    .put(requestBody)
                    .addHeader("Content-Type", AUDIO_CONTENT_TYPE)
                    .build()

                val response = okHttpClient.newCall(request).execute()
                if (response.isSuccessful) {
                    Result.success(Unit)
                } else {
                    Result.failure(
                        ChatException("Upload failed (${response.code}). Please try again."),
                    )
                }
            } catch (e: Exception) {
                Result.failure(
                    ChatException("Upload failed. Please check your internet."),
                )
            }
        }
    }

    /**
     * Sends an audio URL to the STT endpoint for transcription.
     *
     * @param audioUrl The permanent S3 URL of the uploaded audio file.
     * @return [Result] with the transcript text on success.
     */
    suspend fun transcribeAudio(audioUrl: String): Result<String> {
        return try {
            val response = voiceApi.transcribeAudio(STTRequest(audioUrl = audioUrl))
            if (response.isSuccessful) {
                val body = response.body()
                if (body != null) {
                    Result.success(body.transcript)
                } else {
                    Result.failure(ChatException("Transcription returned empty result."))
                }
            } else {
                val errorMessage = parseErrorMessage(
                    response.errorBody()?.string(),
                    response.code(),
                )
                Result.failure(ChatException(errorMessage))
            }
        } catch (e: Exception) {
            Result.failure(
                ChatException("Transcription failed. Please check your internet."),
            )
        }
    }

    private fun parseErrorMessage(errorBody: String?, statusCode: Int): String {
        val detail = parseDetail(errorBody)
        return when (statusCode) {
            HTTP_UNAUTHORIZED -> "Session expired. Please sign in again."
            HTTP_NOT_FOUND -> "Character not found."
            HTTP_SERVICE_UNAVAILABLE -> "Service temporarily unavailable. Please try again."
            else -> detail ?: "Something went wrong. Please try again."
        }
    }

    private fun parseDetail(errorBody: String?): String? {
        if (errorBody == null) return null
        return try {
            json.decodeFromString<ApiErrorBody>(errorBody).detail
        } catch (e: Exception) {
            null
        }
    }

    companion object {
        private const val HTTP_UNAUTHORIZED = 401
        private const val HTTP_NOT_FOUND = 404
        private const val HTTP_SERVICE_UNAVAILABLE = 503
        private const val AUDIO_CONTENT_TYPE = "audio/mp4"
        private const val AUDIO_MEDIA_TYPE = "audio"
    }
}

/** Exception type for chat errors with user-facing messages. */
class ChatException(message: String) : Exception(message)
