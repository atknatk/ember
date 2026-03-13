package ai.ember.app.features.onboarding

import android.view.HapticFeedbackConstants
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.spring
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalView
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle

/**
 * Root onboarding flow container.
 *
 * Routes between [WelcomeScreen] and [QuestionsScreen] based on
 * the current [OnboardingUiState] phase. Handles completion callback
 * to navigate the user to the main app.
 */
@Composable
fun OnboardingScreen(
    onOnboardingComplete: () -> Unit,
    viewModel: OnboardingViewModel = hiltViewModel(),
    modifier: Modifier = Modifier,
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    val view = LocalView.current

    // Navigate to main app on completion
    LaunchedEffect(uiState) {
        if (uiState is OnboardingUiState.Completed) {
            view.performHapticFeedback(HapticFeedbackConstants.CONFIRM)
            onOnboardingComplete()
        }
    }

    AnimatedContent(
        targetState = uiState,
        transitionSpec = {
            slideInHorizontally(
                animationSpec = spring(),
                initialOffsetX = { it },
            ) togetherWith slideOutHorizontally(
                animationSpec = spring(),
                targetOffsetX = { -it },
            )
        },
        modifier = modifier,
        label = "onboarding_phase_transition",
        contentKey = { state ->
            when (state) {
                is OnboardingUiState.Welcome -> "welcome"
                is OnboardingUiState.Questions -> "questions"
                is OnboardingUiState.Completed -> "completed"
                is OnboardingUiState.Error -> "questions" // Stay on questions view for errors
            }
        },
    ) { state ->
        when (state) {
            is OnboardingUiState.Welcome -> WelcomeScreen(
                currentPage = state.currentPage,
                onPageChanged = viewModel::setWelcomePage,
                onNextPage = viewModel::nextWelcomePage,
                onSkip = viewModel::skipToLastWelcomePage,
                onGetStarted = viewModel::advanceToQuestions,
            )

            is OnboardingUiState.Questions -> QuestionsScreen(
                currentIndex = state.currentIndex,
                answers = state.answers,
                isSubmitting = state.isSubmitting,
                canSubmit = viewModel.canSubmit(),
                onAnswerChanged = viewModel::onAnswerChanged,
                onNext = viewModel::nextQuestion,
                onPrevious = viewModel::previousQuestion,
                onSkip = viewModel::skipCurrentQuestion,
                onSubmit = viewModel::submitOnboarding,
            )

            is OnboardingUiState.Error -> {
                // Show questions screen with error dialog overlay
                QuestionsScreen(
                    currentIndex = state.currentIndex,
                    answers = state.answers,
                    isSubmitting = false,
                    canSubmit = state.answers.any { it.trim().isNotEmpty() },
                    onAnswerChanged = viewModel::onAnswerChanged,
                    onNext = viewModel::nextQuestion,
                    onPrevious = viewModel::previousQuestion,
                    onSkip = viewModel::skipCurrentQuestion,
                    onSubmit = viewModel::submitOnboarding,
                )

                OnboardingErrorDialog(
                    message = state.message,
                    onDismiss = viewModel::dismissError,
                    onRetry = {
                        viewModel.dismissError()
                        viewModel.submitOnboarding()
                    },
                )
            }

            is OnboardingUiState.Completed -> {
                // Brief placeholder — LaunchedEffect above handles navigation
            }
        }
    }
}
