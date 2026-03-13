package ai.ember.app.features.chat

import retrofit2.Response
import retrofit2.http.GET
import retrofit2.http.Path
import retrofit2.http.Query

/**
 * Retrofit API interface for chat message history.
 *
 * SSE streaming is handled directly via OkHttp [ChatRepository],
 * not through Retrofit, since Retrofit does not support SSE natively.
 *
 * Requires Authorization header (handled by [TokenInterceptor]).
 */
interface ChatApi {

    @GET("api/v1/characters/{characterId}/messages")
    suspend fun listMessages(
        @Path("characterId") characterId: String,
        @Query("cursor") cursor: String? = null,
        @Query("limit") limit: Int = 20,
    ): Response<ChatMessageListResponse>
}
