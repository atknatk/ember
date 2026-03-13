package ai.ember.app.features.onboarding

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.POST

/**
 * Retrofit API interface for onboarding endpoints.
 *
 * Requires Authorization header (handled by [TokenInterceptor]).
 */
interface OnboardingApi {

    @POST("api/v1/onboarding/complete")
    suspend fun completeOnboarding(
        @Body request: OnboardingRequest,
    ): Response<OnboardingResponse>
}
