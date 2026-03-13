package ai.ember.app.features.profile

import ai.ember.app.core.models.ApiErrorBody
import ai.ember.app.core.models.Character
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Repository handling profile operations for the Profile screen.
 *
 * Converts Retrofit responses into [Result] following the same
 * pattern as [MemoriesRepository] and [HomeRepository].
 */
@Singleton
class ProfileRepository @Inject constructor(
    private val profileApi: ProfileApi,
    private val okHttpClient: OkHttpClient,
    private val json: Json,
) {

    /**
     * Fetches the current user's profile.
     */
    suspend fun getProfile(): Result<ProfileData> {
        return try {
            val response = profileApi.getProfile()
            if (response.isSuccessful) {
                val body = response.body()
                if (body != null) {
                    Result.success(body)
                } else {
                    Result.failure(ProfileException("Something went wrong. Please try again."))
                }
            } else {
                val errorMessage = parseErrorMessage(
                    response.errorBody()?.string(),
                    response.code(),
                )
                Result.failure(ProfileException(errorMessage))
            }
        } catch (e: ProfileException) {
            Result.failure(e)
        } catch (e: Exception) {
            Result.failure(
                ProfileException("Connection failed. Please check your internet."),
            )
        }
    }

    /**
     * Updates the user's profile with the given fields.
     */
    suspend fun updateProfile(request: ProfileUpdateRequest): Result<ProfileData> {
        return try {
            val response = profileApi.updateProfile(request)
            if (response.isSuccessful) {
                val body = response.body()
                if (body != null) {
                    Result.success(body)
                } else {
                    Result.failure(ProfileException("Something went wrong. Please try again."))
                }
            } else {
                val errorMessage = parseErrorMessage(
                    response.errorBody()?.string(),
                    response.code(),
                )
                Result.failure(ProfileException(errorMessage))
            }
        } catch (e: ProfileException) {
            Result.failure(e)
        } catch (e: Exception) {
            Result.failure(
                ProfileException("Connection failed. Please check your internet."),
            )
        }
    }

    /**
     * Deletes the user's account. Requires confirmation text.
     */
    suspend fun deleteAccount(confirmation: String): Result<Unit> {
        return try {
            val response = profileApi.deleteAccount(
                AccountDeleteRequest(confirmation = confirmation),
            )
            if (response.isSuccessful || response.code() == HTTP_NO_CONTENT) {
                Result.success(Unit)
            } else {
                val errorMessage = parseErrorMessage(
                    response.errorBody()?.string(),
                    response.code(),
                )
                Result.failure(ProfileException(errorMessage))
            }
        } catch (e: ProfileException) {
            Result.failure(e)
        } catch (e: Exception) {
            Result.failure(
                ProfileException("Connection failed. Please check your internet."),
            )
        }
    }

    /**
     * Gets a presigned S3 upload URL for avatar upload.
     */
    suspend fun getUploadUrl(
        filename: String,
        contentType: String,
    ): Result<UploadUrlResponse> {
        return try {
            val response = profileApi.getUploadUrl(
                UploadUrlRequest(
                    filename = filename,
                    contentType = contentType,
                    type = "photo",
                ),
            )
            if (response.isSuccessful) {
                val body = response.body()
                if (body != null) {
                    Result.success(body)
                } else {
                    Result.failure(ProfileException("Something went wrong. Please try again."))
                }
            } else {
                val errorMessage = parseErrorMessage(
                    response.errorBody()?.string(),
                    response.code(),
                )
                Result.failure(ProfileException(errorMessage))
            }
        } catch (e: ProfileException) {
            Result.failure(e)
        } catch (e: Exception) {
            Result.failure(
                ProfileException("Connection failed. Please check your internet."),
            )
        }
    }

    /**
     * Uploads image data to the presigned S3 URL.
     */
    suspend fun uploadToS3(uploadUrl: String, imageData: ByteArray, contentType: String): Result<Unit> {
        return try {
            val requestBody = imageData.toRequestBody(contentType.toMediaType())
            val request = Request.Builder()
                .url(uploadUrl)
                .put(requestBody)
                .addHeader("Content-Type", contentType)
                .build()

            val response = okHttpClient.newCall(request).execute()
            if (response.isSuccessful) {
                Result.success(Unit)
            } else {
                Result.failure(ProfileException("Failed to upload image. Please try again."))
            }
        } catch (e: Exception) {
            Result.failure(
                ProfileException("Connection failed. Please check your internet."),
            )
        }
    }

    /**
     * Fetches all active characters for notification preference toggles.
     */
    suspend fun getCharacters(): Result<List<Character>> {
        return try {
            val response = profileApi.listCharacters()
            if (response.isSuccessful) {
                val body = response.body()
                if (body != null) {
                    Result.success(body.characters)
                } else {
                    Result.failure(ProfileException("Something went wrong. Please try again."))
                }
            } else {
                val errorMessage = parseErrorMessage(
                    response.errorBody()?.string(),
                    response.code(),
                )
                Result.failure(ProfileException(errorMessage))
            }
        } catch (e: ProfileException) {
            Result.failure(e)
        } catch (e: Exception) {
            Result.failure(
                ProfileException("Connection failed. Please check your internet."),
            )
        }
    }

    private fun parseErrorMessage(errorBody: String?, statusCode: Int): String {
        val detail = parseDetail(errorBody)
        return when (statusCode) {
            HTTP_BAD_REQUEST -> detail ?: "Invalid request. Please check your input."
            HTTP_UNAUTHORIZED -> "Session expired. Please sign in again."
            HTTP_UNPROCESSABLE -> detail ?: "Invalid data. Please check your input."
            HTTP_SERVICE_UNAVAILABLE -> "Service unavailable. Please try again later."
            else -> detail ?: "Something went wrong. Please try again."
        }
    }

    private fun parseDetail(errorBody: String?): String? {
        if (errorBody == null) return null
        return try {
            json.decodeFromString<ApiErrorBody>(errorBody).detail
        } catch (e: Exception) {
            null
        }
    }

    companion object {
        private const val HTTP_BAD_REQUEST = 400
        private const val HTTP_UNAUTHORIZED = 401
        private const val HTTP_UNPROCESSABLE = 422
        private const val HTTP_NO_CONTENT = 204
        private const val HTTP_SERVICE_UNAVAILABLE = 503
    }
}

/** Exception type for profile screen errors with user-facing messages. */
class ProfileException(message: String) : Exception(message)
