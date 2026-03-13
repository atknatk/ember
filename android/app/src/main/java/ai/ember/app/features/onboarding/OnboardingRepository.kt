package ai.ember.app.features.onboarding

import kotlinx.serialization.json.Json
import ai.ember.app.core.models.ApiErrorBody
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Repository handling onboarding API operations.
 *
 * Converts Retrofit responses into [Result] following the same
 * pattern as [AuthRepository].
 */
@Singleton
class OnboardingRepository @Inject constructor(
    private val onboardingApi: OnboardingApi,
    private val json: Json,
) {

    /**
     * Submits onboarding answers to the backend.
     *
     * @param answers list of Q&A pairs to seed as Mem0 memories.
     * @return [OnboardingResponse] on success, or a descriptive error.
     */
    suspend fun completeOnboarding(
        answers: List<OnboardingAnswer>,
    ): Result<OnboardingResponse> {
        return try {
            val response = onboardingApi.completeOnboarding(
                OnboardingRequest(answers = answers),
            )
            if (response.isSuccessful) {
                val body = response.body()
                if (body != null) {
                    Result.success(body)
                } else {
                    Result.failure(OnboardingException("Something went wrong. Please try again."))
                }
            } else {
                val errorMessage = parseErrorMessage(
                    response.errorBody()?.string(),
                    response.code(),
                )
                // 409 means already completed — treat as success
                if (response.code() == HTTP_CONFLICT) {
                    Result.success(
                        OnboardingResponse(
                            onboardingCompleted = true,
                            memoriesSeeded = 0,
                        ),
                    )
                } else {
                    Result.failure(OnboardingException(errorMessage))
                }
            }
        } catch (e: OnboardingException) {
            Result.failure(e)
        } catch (e: Exception) {
            Result.failure(
                OnboardingException("Connection failed. Please check your internet."),
            )
        }
    }

    private fun parseErrorMessage(errorBody: String?, statusCode: Int): String {
        val detail = parseDetail(errorBody)
        return when (statusCode) {
            HTTP_CONFLICT -> "Onboarding already completed"
            HTTP_UNPROCESSABLE -> detail ?: "Invalid onboarding data"
            HTTP_UNAUTHORIZED -> "Session expired. Please sign in again."
            HTTP_SERVICE_UNAVAILABLE -> "Service temporarily unavailable. Please try again."
            else -> "Something went wrong. Please try again."
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
        private const val HTTP_CONFLICT = 409
        private const val HTTP_UNPROCESSABLE = 422
        private const val HTTP_UNAUTHORIZED = 401
        private const val HTTP_SERVICE_UNAVAILABLE = 503
    }
}

/** Exception type for onboarding errors with user-facing messages. */
class OnboardingException(message: String) : Exception(message)
