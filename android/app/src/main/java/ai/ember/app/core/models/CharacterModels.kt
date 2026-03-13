package ai.ember.app.core.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * A user's AI character, mapped from GET /api/v1/characters response.
 */
@Serializable
data class Character(
    val id: String,
    val name: String,
    val template: String,
    val description: String? = null,
    @SerialName("avatar_style") val avatarStyle: String = "default",
    @SerialName("is_default") val isDefault: Boolean = false,
    @SerialName("last_message_at") val lastMessageAt: String? = null,
    @SerialName("created_at") val createdAt: String = "",
)

/**
 * Response wrapper for GET /api/v1/characters.
 */
@Serializable
data class CharacterListResponse(
    val characters: List<Character>,
)
