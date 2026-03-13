package ai.ember.app.features.home

import ai.ember.app.core.models.CharacterListResponse
import ai.ember.app.core.models.MessageListResponse
import retrofit2.Response
import retrofit2.http.GET
import retrofit2.http.Path
import retrofit2.http.Query

/**
 * Retrofit API interface for character and message endpoints
 * used by the Home screen.
 *
 * Requires Authorization header (handled by [TokenInterceptor]).
 */
interface CharacterApi {

    @GET("api/v1/characters")
    suspend fun listCharacters(): Response<CharacterListResponse>

    @GET("api/v1/characters/{characterId}/messages")
    suspend fun listMessages(
        @Path("characterId") characterId: String,
        @Query("cursor") cursor: String? = null,
        @Query("limit") limit: Int = 1,
    ): Response<MessageListResponse>
}
