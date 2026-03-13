package ai.ember.app.features.memories

import ai.ember.app.core.models.CharacterListResponse
import ai.ember.app.core.models.MemoryListResponse
import retrofit2.Response
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Path

/**
 * Retrofit API interface for memory endpoints.
 *
 * Handles both character-scoped and global memory operations.
 * Requires Authorization header (handled by [TokenInterceptor]).
 */
interface MemoryApi {

    @GET("api/v1/characters")
    suspend fun listCharacters(): Response<CharacterListResponse>

    @GET("api/v1/characters/{characterId}/memories")
    suspend fun listCharacterMemories(
        @Path("characterId") characterId: String,
    ): Response<MemoryListResponse>

    @DELETE("api/v1/characters/{characterId}/memories/{memoryId}")
    suspend fun deleteCharacterMemory(
        @Path("characterId") characterId: String,
        @Path("memoryId") memoryId: String,
    ): Response<Unit>

    @GET("api/v1/memories")
    suspend fun listGlobalMemories(): Response<MemoryListResponse>

    @DELETE("api/v1/memories/{memoryId}")
    suspend fun deleteGlobalMemory(
        @Path("memoryId") memoryId: String,
    ): Response<Unit>
}
