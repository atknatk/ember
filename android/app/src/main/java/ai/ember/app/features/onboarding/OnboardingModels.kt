package ai.ember.app.features.onboarding

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * A single Q&A pair for the onboarding flow.
 *
 * Maps to the backend's `OnboardingAnswer` Pydantic model.
 */
@Serializable
data class OnboardingAnswer(
    @SerialName("question_key") val questionKey: String,
    val answer: String,
)

/**
 * Request body for POST /api/v1/onboarding/complete.
 */
@Serializable
data class OnboardingRequest(
    val answers: List<OnboardingAnswer>,
)

/**
 * Response from POST /api/v1/onboarding/complete.
 */
@Serializable
data class OnboardingResponse(
    @SerialName("onboarding_completed") val onboardingCompleted: Boolean,
    @SerialName("memories_seeded") val memoriesSeeded: Int,
)

/**
 * Represents a single onboarding question card.
 *
 * Pure domain model — no Android dependencies.
 */
data class OnboardingQuestion(
    val index: Int,
    val questionKey: String,
    val questionTextResId: Int,
    val placeholderResId: Int,
)
