package ai.ember.app.core.network

import ai.ember.app.core.auth.AuthRepository
import kotlinx.coroutines.runBlocking
import okhttp3.Interceptor
import okhttp3.Response
import javax.inject.Inject
import javax.inject.Singleton

/**
 * OkHttp interceptor that attaches Bearer token to requests and handles 401 auto-refresh.
 *
 * Auth endpoints (login, register, refresh) are excluded from token injection
 * to avoid circular dependencies.
 *
 * On 401 response:
 * 1. Attempts to refresh the access token via [AuthRepository.refreshAccessToken].
 * 2. If refresh succeeds, retries the original request once with the new token.
 * 3. If refresh fails, returns the original 401 response.
 */
@Singleton
class TokenInterceptor @Inject constructor(
    private val authRepository: dagger.Lazy<AuthRepository>,
) : Interceptor {

    override fun intercept(chain: Interceptor.Chain): Response {
        val originalRequest = chain.request()

        // Skip token injection for auth endpoints
        val path = originalRequest.url.encodedPath
        if (isAuthEndpoint(path)) {
            return chain.proceed(originalRequest)
        }

        // Attach access token
        val token = authRepository.get().getAccessToken()
        val authenticatedRequest = if (token != null) {
            originalRequest.newBuilder()
                .header("Authorization", "Bearer $token")
                .build()
        } else {
            originalRequest
        }

        val response = chain.proceed(authenticatedRequest)

        // Handle 401 — attempt token refresh and retry once
        if (response.code == 401 && token != null) {
            val newToken = runBlocking { authRepository.get().refreshAccessToken() }
            if (newToken != null) {
                response.close()
                val retryRequest = originalRequest.newBuilder()
                    .header("Authorization", "Bearer $newToken")
                    .build()
                return chain.proceed(retryRequest)
            }
        }

        return response
    }

    private fun isAuthEndpoint(path: String): Boolean =
        path.contains("/auth/login") ||
            path.contains("/auth/register") ||
            path.contains("/auth/refresh")
}
