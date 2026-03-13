package ai.ember.app.core.auth

import ai.ember.app.core.models.ApiErrorBody
import ai.ember.app.core.models.AuthResponse
import ai.ember.app.core.models.LoginRequest
import ai.ember.app.core.models.RefreshTokenRequest
import ai.ember.app.core.models.RegisterRequest
import ai.ember.app.core.network.AuthApi
import kotlinx.serialization.json.Json
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Repository handling authentication operations.
 *
 * Makes REST calls via [AuthApi] and persists tokens via [TokenManager].
 * Mirrors iOS AuthService: signIn, signUp, signOut, refreshToken.
 */
@Singleton
class AuthRepository @Inject constructor(
    private val authApi: AuthApi,
    private val tokenManager: TokenManager,
    private val json: Json,
) {
    /** Returns true if stored tokens exist (may be expired). */
    val isAuthenticated: Boolean
        get() = tokenManager.hasTokens

    /**
     * Signs in with email and password.
     * On success, saves tokens to EncryptedSharedPreferences.
     */
    suspend fun signIn(email: String, password: String): Result<AuthResponse> {
        return try {
            val response = authApi.login(LoginRequest(email = email, password = password))
            if (response.isSuccessful) {
                val body = response.body()
                if (body != null) {
                    tokenManager.saveTokens(
                        accessToken = body.token,
                        refreshToken = body.refreshToken,
                    )
                    Result.success(body)
                } else {
                    Result.failure(AuthException("Something went wrong. Please try again."))
                }
            } else {
                val errorMessage = parseErrorMessage(response.errorBody()?.string(), response.code())
                Result.failure(AuthException(errorMessage))
            }
        } catch (e: AuthException) {
            Result.failure(e)
        } catch (e: Exception) {
            Result.failure(AuthException("Connection failed. Please check your internet."))
        }
    }

    /**
     * Registers a new account with name, email, and password.
     * On success, saves tokens to EncryptedSharedPreferences.
     */
    suspend fun signUp(email: String, password: String, name: String): Result<AuthResponse> {
        return try {
            val response = authApi.register(
                RegisterRequest(email = email, password = password, name = name),
            )
            if (response.isSuccessful) {
                val body = response.body()
                if (body != null) {
                    tokenManager.saveTokens(
                        accessToken = body.token,
                        refreshToken = body.refreshToken,
                    )
                    Result.success(body)
                } else {
                    Result.failure(AuthException("Something went wrong. Please try again."))
                }
            } else {
                val errorMessage = parseSignUpErrorMessage(
                    response.errorBody()?.string(),
                    response.code(),
                )
                Result.failure(AuthException(errorMessage))
            }
        } catch (e: AuthException) {
            Result.failure(e)
        } catch (e: Exception) {
            Result.failure(AuthException("Connection failed. Please check your internet."))
        }
    }

    /** Signs out by clearing stored tokens. */
    fun signOut() {
        tokenManager.clearTokens()
    }

    /** Returns the stored access token, or null. */
    fun getAccessToken(): String? = tokenManager.getAccessToken()

    /**
     * Refreshes the access token using the stored refresh token.
     * Called by [TokenInterceptor] on 401 responses.
     *
     * @return the new access token, or null if refresh failed.
     */
    suspend fun refreshAccessToken(): String? {
        val refreshToken = tokenManager.getRefreshToken() ?: return null
        return try {
            val response = authApi.refresh(RefreshTokenRequest(refreshToken = refreshToken))
            if (response.isSuccessful) {
                val newToken = response.body()?.token
                if (newToken != null) {
                    tokenManager.updateAccessToken(newToken)
                }
                newToken
            } else {
                // Refresh failed — tokens are stale
                null
            }
        } catch (e: Exception) {
            null
        }
    }

    /** Parses sign-in error messages from the API response. */
    private fun parseErrorMessage(errorBody: String?, statusCode: Int): String {
        val detail = parseDetail(errorBody)
        return when (statusCode) {
            401 -> "Invalid email or password"
            400 -> detail ?: "Invalid email or password"
            429 -> "Too many attempts. Please try again later."
            else -> "Something went wrong. Please try again."
        }
    }

    /** Parses sign-up error messages from the API response. */
    private fun parseSignUpErrorMessage(errorBody: String?, statusCode: Int): String {
        val detail = parseDetail(errorBody)
        return when (statusCode) {
            400 -> {
                val lower = detail?.lowercase() ?: ""
                when {
                    lower.contains("already exists") -> "An account with this email already exists"
                    lower.contains("password") -> "Password does not meet requirements"
                    else -> detail ?: "Invalid registration data"
                }
            }
            429 -> "Too many attempts. Please try again later."
            else -> "Something went wrong. Please try again."
        }
    }

    /** Tries to parse {"detail": "..."} from error body. */
    private fun parseDetail(errorBody: String?): String? {
        if (errorBody == null) return null
        return try {
            json.decodeFromString<ApiErrorBody>(errorBody).detail
        } catch (e: Exception) {
            null
        }
    }
}

/** Exception type for authentication errors with user-facing messages. */
class AuthException(message: String) : Exception(message)
