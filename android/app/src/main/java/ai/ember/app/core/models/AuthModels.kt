package ai.ember.app.core.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Response from POST /api/v1/auth/login and POST /api/v1/auth/register.
 */
@Serializable
data class AuthResponse(
    val token: String,
    @SerialName("refresh_token") val refreshToken: String,
    val user: UserResponse,
)

/**
 * User profile data returned inside [AuthResponse].
 */
@Serializable
data class UserResponse(
    val id: String,
    val email: String,
    val name: String,
    @SerialName("avatar_url") val avatarUrl: String? = null,
    val timezone: String = "UTC",
    @SerialName("preferred_language") val preferredLanguage: String = "en",
    @SerialName("onboarding_completed") val onboardingCompleted: Boolean = false,
    @SerialName("subscription_tier") val subscriptionTier: String = "free",
    @SerialName("created_at") val createdAt: String = "",
)

/**
 * Response from POST /api/v1/auth/refresh.
 */
@Serializable
data class RefreshResponse(
    val token: String,
)

/**
 * Request body for POST /api/v1/auth/login.
 */
@Serializable
data class LoginRequest(
    val email: String,
    val password: String,
)

/**
 * Request body for POST /api/v1/auth/register.
 */
@Serializable
data class RegisterRequest(
    val email: String,
    val password: String,
    val name: String,
)

/**
 * Request body for POST /api/v1/auth/refresh.
 */
@Serializable
data class RefreshTokenRequest(
    @SerialName("refresh_token") val refreshToken: String,
)

/**
 * Error response body from the API: {"detail": "..."}.
 */
@Serializable
data class ApiErrorBody(
    val detail: String,
)
