package ai.ember.app.features.chat

import ai.ember.app.BuildConfig
import ai.ember.app.core.auth.AuthRepository
import ai.ember.app.core.models.ApiErrorBody
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.sse.EventSource
import okhttp3.sse.EventSourceListener
import okhttp3.sse.EventSources
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
    }
}

/** Exception type for chat errors with user-facing messages. */
class ChatException(message: String) : Exception(message)
