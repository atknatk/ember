package ai.ember.app.features.profile

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Profile data from GET /api/v1/profile.
 *
 * Maps to the backend ProfileResponse Pydantic schema.
 * All properties are immutable (val) per domain model rules.
 */
@Serializable
data class ProfileData(
    val id: String,
    val email: String,
    val name: String,
    val timezone: String = "UTC",
    @SerialName("avatar_url") val avatarUrl: String? = null,
    @SerialName("preferred_language") val preferredLanguage: String = "en",
    @SerialName("onboarding_completed") val onboardingCompleted: Boolean = false,
    @SerialName("subscription_tier") val subscriptionTier: String = "free",
    @SerialName("subscription_expires_at") val subscriptionExpiresAt: String? = null,
    @SerialName("created_at") val createdAt: String = "",
)

/**
 * Request body for PUT /api/v1/profile.
 *
 * Only non-null fields are serialized and sent to the backend.
 */
@Serializable
data class ProfileUpdateRequest(
    val name: String? = null,
    val timezone: String? = null,
    @SerialName("avatar_url") val avatarUrl: String? = null,
    @SerialName("preferred_language") val preferredLanguage: String? = null,
)

/**
 * Request body for DELETE /api/v1/profile/account.
 */
@Serializable
data class AccountDeleteRequest(
    val confirmation: String,
)

/**
 * Request body for POST /api/v1/media/upload-url.
 */
@Serializable
data class UploadUrlRequest(
    val filename: String,
    @SerialName("content_type") val contentType: String,
    val type: String,
)

/**
 * Response from POST /api/v1/media/upload-url.
 */
@Serializable
data class UploadUrlResponse(
    @SerialName("upload_url") val uploadUrl: String,
    @SerialName("file_url") val fileUrl: String,
)
