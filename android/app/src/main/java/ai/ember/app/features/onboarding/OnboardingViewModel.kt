package ai.ember.app.features.onboarding

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * ViewModel for the onboarding flow.
 *
 * Manages welcome carousel state, question navigation, answer collection,
 * and submission to POST /api/v1/onboarding/complete.
 */
@HiltViewModel
class OnboardingViewModel @Inject constructor(
    private val onboardingRepository: OnboardingRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow<OnboardingUiState>(OnboardingUiState.Welcome())
    val uiState: StateFlow<OnboardingUiState> = _uiState.asStateFlow()

    // -- Welcome Phase --

    /** Advances to the next welcome page, or stays on the last page. */
    fun nextWelcomePage() {
        val state = _uiState.value as? OnboardingUiState.Welcome ?: return
        if (state.currentPage < OnboardingUiState.WELCOME_PAGE_COUNT - 1) {
            _uiState.value = state.copy(currentPage = state.currentPage + 1)
        }
    }

    /** Sets the welcome page directly (e.g., from pager swipe). */
    fun setWelcomePage(page: Int) {
        val state = _uiState.value as? OnboardingUiState.Welcome ?: return
        val clampedPage = page.coerceIn(0, OnboardingUiState.WELCOME_PAGE_COUNT - 1)
        _uiState.value = state.copy(currentPage = clampedPage)
    }

    /** Skips the welcome carousel and moves to the last welcome page. */
    fun skipToLastWelcomePage() {
        val state = _uiState.value as? OnboardingUiState.Welcome ?: return
        _uiState.value = state.copy(currentPage = OnboardingUiState.WELCOME_PAGE_COUNT - 1)
    }

    /** Transitions from welcome carousel to questions phase. */
    fun advanceToQuestions() {
        if (_uiState.value !is OnboardingUiState.Welcome) return
        _uiState.value = OnboardingUiState.Questions()
    }

    // -- Questions Phase --

    /** Updates the answer for the current question. */
    fun onAnswerChanged(answer: String) {
        val state = currentQuestionsState() ?: return
        val updatedAnswers = state.answers.toMutableList()
        updatedAnswers[state.currentIndex] = answer
        _uiState.value = state.copy(answers = updatedAnswers)
    }

    /** Advances to the next question card. */
    fun nextQuestion() {
        val state = currentQuestionsState() ?: return
        if (state.currentIndex < OnboardingUiState.QUESTION_COUNT - 1) {
            _uiState.value = state.copy(currentIndex = state.currentIndex + 1)
        }
    }

    /** Goes back to the previous question card. */
    fun previousQuestion() {
        val state = currentQuestionsState() ?: return
        if (state.currentIndex > 0) {
            _uiState.value = state.copy(currentIndex = state.currentIndex - 1)
        }
    }

    /** Skips the current question (clears answer) and advances. */
    fun skipCurrentQuestion() {
        val state = currentQuestionsState() ?: return
        val updatedAnswers = state.answers.toMutableList()
        updatedAnswers[state.currentIndex] = ""

        if (state.currentIndex == OnboardingUiState.QUESTION_COUNT - 1) {
            // On the last question — submit
            _uiState.value = state.copy(answers = updatedAnswers)
            submitOnboarding()
        } else {
            _uiState.value = state.copy(
                answers = updatedAnswers,
                currentIndex = state.currentIndex + 1,
            )
        }
    }

    /**
     * Returns true if at least one answer across all questions is non-empty.
     * Cannot submit all blank answers.
     */
    fun canSubmit(): Boolean {
        val state = currentQuestionsState() ?: return false
        return state.answers.any { it.trim().isNotEmpty() }
    }

    /** Submits onboarding answers to the backend. */
    fun submitOnboarding() {
        val state = currentQuestionsState()
        val answers = state?.answers ?: recoverAnswersFromError() ?: return
        val currentIndex = state?.currentIndex
            ?: (_uiState.value as? OnboardingUiState.Error)?.currentIndex
            ?: return

        if (answers.none { it.trim().isNotEmpty() }) return

        viewModelScope.launch {
            _uiState.value = OnboardingUiState.Questions(
                currentIndex = currentIndex,
                answers = answers,
                isSubmitting = true,
            )

            val onboardingAnswers = QUESTION_KEYS.mapIndexed { index, key ->
                val answer = answers[index].trim()
                OnboardingAnswer(
                    questionKey = key,
                    answer = answer.ifEmpty { NOT_PROVIDED },
                )
            }

            onboardingRepository.completeOnboarding(onboardingAnswers)
                .onSuccess {
                    _uiState.value = OnboardingUiState.Completed
                }
                .onFailure { e ->
                    _uiState.value = OnboardingUiState.Error(
                        message = e.message ?: "Something went wrong. Please try again.",
                        answers = answers,
                        currentIndex = currentIndex,
                    )
                }
        }
    }

    /** Dismisses the error state and returns to the questions phase. */
    fun dismissError() {
        val errorState = _uiState.value as? OnboardingUiState.Error ?: return
        _uiState.value = OnboardingUiState.Questions(
            currentIndex = errorState.currentIndex,
            answers = errorState.answers,
        )
    }

    private fun currentQuestionsState(): OnboardingUiState.Questions? =
        _uiState.value as? OnboardingUiState.Questions

    private fun recoverAnswersFromError(): List<String>? =
        (_uiState.value as? OnboardingUiState.Error)?.answers

    companion object {
        /** The 7 question keys matching the backend's VALID_QUESTION_KEYS. */
        val QUESTION_KEYS = listOf(
            "preferred_name",
            "occupation",
            "daily_rhythm",
            "health_goal",
            "stress_management",
            "sleep_schedule",
            "communication_style",
        )

        /** Fallback answer for skipped questions (backend requires min_length=1). */
        private const val NOT_PROVIDED = "Not provided"
    }
}
