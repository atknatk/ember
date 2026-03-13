package ai.ember.app.core.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * A single message in a conversation.
 */
@Serializable
data class MessagePreview(
    val id: String,
    val role: String,
    val content: String,
    @SerialName("media_url") val mediaUrl: String? = null,
    val metadata: String? = null,
    @SerialName("created_at") val createdAt: String = "",
)

/**
 * Paginated response from GET /api/v1/characters/:id/messages.
 */
@Serializable
data class MessageListResponse(
    val items: List<MessagePreview>,
    @SerialName("next_cursor") val nextCursor: String? = null,
    @SerialName("has_more") val hasMore: Boolean = false,
)
