package ai.ember.app.features.chat

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.POST

/**
 * Retrofit API interface for media upload URL generation and STT transcription.
 *
 * Used by voice recording flow: get presigned URL -> upload audio -> transcribe.
 * The actual S3 PUT upload is done via raw OkHttp (not Retrofit) since it
 * requires binary body without JSON serialization.
 */
interface VoiceApi {

    @POST("api/v1/media/upload-url")
    suspend fun getUploadUrl(
        @Body request: UploadUrlRequest,
    ): Response<UploadUrlResponse>

    @POST("api/v1/stt")
    suspend fun transcribeAudio(
        @Body request: STTRequest,
    ): Response<STTResponse>

    @POST("api/v1/tts")
    suspend fun synthesizeSpeech(
        @Body request: TTSRequest,
    ): Response<TTSResponse>
}

// -- Request/Response models --

@Serializable
data class UploadUrlRequest(
    val filename: String,
    @SerialName("content_type") val contentType: String,
    val type: String,
)

@Serializable
data class UploadUrlResponse(
    @SerialName("upload_url") val uploadUrl: String,
    @SerialName("file_url") val fileUrl: String,
)

@Serializable
data class STTRequest(
    @SerialName("audio_url") val audioUrl: String,
)

@Serializable
data class STTResponse(
    val transcript: String,
    val language: String,
    val confidence: Float,
    @SerialName("duration_seconds") val durationSeconds: Float? = null,
)

@Serializable
data class TTSRequest(
    val text: String,
    @SerialName("character_id") val characterId: String,
    @SerialName("voice_id") val voiceId: String? = null,
    val language: String = "en",
)

@Serializable
data class TTSResponse(
    @SerialName("audio_url") val audioUrl: String,
    @SerialName("duration_seconds") val durationSeconds: Float? = null,
)
