package ai.ember.app.features.onboarding

/**
 * Sealed UI state for onboarding flow screens.
 *
 * The onboarding flow has two phases: welcome carousel and questions.
 * This state manages both phases plus submission status.
 */
sealed interface OnboardingUiState {

    /** Welcome carousel phase — displaying welcome pages. */
    data class Welcome(
        val currentPage: Int = 0,
    ) : OnboardingUiState

    /** Questions phase — collecting user answers. */
    data class Questions(
        val currentIndex: Int = 0,
        val answers: List<String> = List(QUESTION_COUNT) { "" },
        val isSubmitting: Boolean = false,
    ) : OnboardingUiState

    /** Onboarding completed successfully. */
    data object Completed : OnboardingUiState

    /** Submission failed with a user-facing error message. */
    data class Error(
        val message: String,
        val answers: List<String>,
        val currentIndex: Int,
    ) : OnboardingUiState

    companion object {
        const val WELCOME_PAGE_COUNT = 3
        const val QUESTION_COUNT = 7
    }
}
