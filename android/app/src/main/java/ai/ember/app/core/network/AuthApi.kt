package ai.ember.app.core.network

import ai.ember.app.core.models.AuthResponse
import ai.ember.app.core.models.LoginRequest
import ai.ember.app.core.models.RefreshResponse
import ai.ember.app.core.models.RefreshTokenRequest
import ai.ember.app.core.models.RegisterRequest
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.POST

/**
 * Retrofit API interface for authentication endpoints.
 *
 * These endpoints are public (no Authorization header needed).
 * The [TokenInterceptor] skips auth header injection for these paths.
 */
interface AuthApi {

    @POST("api/v1/auth/login")
    suspend fun login(@Body request: LoginRequest): Response<AuthResponse>

    @POST("api/v1/auth/register")
    suspend fun register(@Body request: RegisterRequest): Response<AuthResponse>

    @POST("api/v1/auth/refresh")
    suspend fun refresh(@Body request: RefreshTokenRequest): Response<RefreshResponse>
}
