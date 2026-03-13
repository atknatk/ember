package ai.ember.app.core.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * A single memory entry from Mem0, mapped from GET /api/v1/memories
 * and GET /api/v1/characters/:id/memories responses.
 */
@Serializable
data class MemoryItem(
    val id: String,
    val memory: String,
    @SerialName("created_at") val createdAt: String? = null,
)

/**
 * Response wrapper for memory list endpoints.
 */
@Serializable
data class MemoryListResponse(
    val memories: List<MemoryItem>,
)
