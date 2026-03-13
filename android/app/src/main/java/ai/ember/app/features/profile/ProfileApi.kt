package ai.ember.app.features.profile

import ai.ember.app.core.models.CharacterListResponse
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.HTTP
import retrofit2.http.POST
import retrofit2.http.PUT

/**
 * Retrofit API interface for profile endpoints.
 *
 * Handles profile CRUD, account deletion, and media upload URL requests.
 * Authorization header is handled by [TokenInterceptor].
 */
interface ProfileApi {

    @GET("api/v1/profile")
    suspend fun getProfile(): Response<ProfileData>

    @PUT("api/v1/profile")
    suspend fun updateProfile(
        @Body body: ProfileUpdateRequest,
    ): Response<ProfileData>

    @HTTP(method = "DELETE", path = "api/v1/profile/account", hasBody = true)
    suspend fun deleteAccount(
        @Body body: AccountDeleteRequest,
    ): Response<Unit>

    @POST("api/v1/media/upload-url")
    suspend fun getUploadUrl(
        @Body body: UploadUrlRequest,
    ): Response<UploadUrlResponse>

    @GET("api/v1/characters")
    suspend fun listCharacters(): Response<CharacterListResponse>
}
