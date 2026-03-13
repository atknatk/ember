package ai.ember.app.features.chat

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * A full chat message for the Chat screen.
 *
 * Richer than [ai.ember.app.core.models.MessagePreview] used by HomeView.
 * Uses immutable vals for all fields; [content] is only mutated through
 * copy() during SSE streaming.
 */
@Serializable
data class ChatMessage(
    val id: String,
    val role: String,
    val content: String,
    @SerialName("media_url") val mediaUrl: String? = null,
    val metadata: MessageMetadata? = null,
    @SerialName("created_at") val createdAt: String = "",
)

/**
 * Optional metadata for action events from the AI (alarm, calendar).
 */
@Serializable
data class MessageMetadata(
    val action: String? = null,
    val payload: Map<String, String>? = null,
)

/**
 * Request body for POST /api/v1/characters/:id/messages.
 */
@Serializable
data class SendMessageRequest(
    val content: String,
    @SerialName("media_url") val mediaUrl: String? = null,
)

/**
 * Paginated response from GET /api/v1/characters/:id/messages.
 *
 * Uses full [ChatMessage] objects (not [MessagePreview]).
 */
@Serializable
data class ChatMessageListResponse(
    val items: List<ChatMessage>,
    @SerialName("next_cursor") val nextCursor: String? = null,
    @SerialName("has_more") val hasMore: Boolean = false,
)

/**
 * Represents a single SSE event from the streaming message endpoint.
 */
@Serializable
data class SseEvent(
    val type: String,
    val content: String? = null,
    @SerialName("message_id") val messageId: String? = null,
    val message: String? = null,
    val action: String? = null,
    val payload: Map<String, String>? = null,
)

/**
 * Message role constants matching backend role values.
 */
object MessageRole {
    const val USER = "user"
    const val ASSISTANT = "assistant"
}
