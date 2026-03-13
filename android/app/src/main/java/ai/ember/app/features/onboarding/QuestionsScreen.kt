package ai.ember.app.features.onboarding

import android.view.HapticFeedbackConstants
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import ai.ember.app.R
import ai.ember.app.core.ui.theme.EmberPrimary
import ai.ember.app.core.ui.theme.EmberShapes
import ai.ember.app.core.ui.theme.EmberSpacing
import ai.ember.app.core.ui.theme.EmberSurface3
import ai.ember.app.core.ui.theme.EmberTextDisabled
import ai.ember.app.core.ui.theme.EmberTextSecondary
import ai.ember.app.features.auth.authTextFieldColors
import kotlinx.coroutines.delay

/**
 * Questions screen with 7 personalization cards.
 *
 * Each card shows a question with a free-text input.
 * Progress indicator at the top, navigation buttons at the bottom.
 */
@Composable
fun QuestionsScreen(
    currentIndex: Int,
    answers: List<String>,
    isSubmitting: Boolean,
    canSubmit: Boolean,
    onAnswerChanged: (String) -> Unit,
    onNext: () -> Unit,
    onPrevious: () -> Unit,
    onSkip: () -> Unit,
    onSubmit: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val view = LocalView.current
    val focusManager = LocalFocusManager.current
    val isLastQuestion = currentIndex == OnboardingUiState.QUESTION_COUNT - 1

    Column(
        modifier = modifier.fillMaxSize(),
    ) {
        Spacer(modifier = Modifier.height(EmberSpacing.xxxl))

        // Progress indicator
        ProgressSection(currentIndex = currentIndex)

        Spacer(modifier = Modifier.height(EmberSpacing.xl))

        // Question card with animated transitions
        AnimatedContent(
            targetState = currentIndex,
            transitionSpec = {
                if (targetState > initialState) {
                    slideInHorizontally { it } togetherWith slideOutHorizontally { -it }
                } else {
                    slideInHorizontally { -it } togetherWith slideOutHorizontally { it }
                }
            },
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth(),
            label = "question_transition",
        ) { questionIndex ->
            QuestionCard(
                questionIndex = questionIndex,
                answer = answers.getOrElse(questionIndex) { "" },
                isSubmitting = isSubmitting,
                isLastQuestion = questionIndex == OnboardingUiState.QUESTION_COUNT - 1,
                onAnswerChanged = onAnswerChanged,
                onImeAction = {
                    focusManager.clearFocus()
                    if (questionIndex == OnboardingUiState.QUESTION_COUNT - 1) {
                        if (canSubmit) onSubmit()
                    } else {
                        onNext()
                    }
                },
            )
        }

        // Skip link
        TextButton(
            onClick = {
                view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                onSkip()
            },
            enabled = !isSubmitting,
            modifier = Modifier.align(Alignment.CenterHorizontally),
        ) {
            Text(
                text = stringResource(R.string.onboarding_skip),
                style = MaterialTheme.typography.bodyMedium,
                color = if (isSubmitting) EmberTextDisabled else EmberTextSecondary,
            )
        }

        Spacer(modifier = Modifier.height(EmberSpacing.md))

        // Navigation buttons
        QuestionNavigationButtons(
            currentIndex = currentIndex,
            isSubmitting = isSubmitting,
            canSubmit = canSubmit,
            currentAnswerNotEmpty = answers.getOrElse(currentIndex) { "" }.trim().isNotEmpty(),
            onPrevious = {
                view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                onPrevious()
            },
            onNext = {
                view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                onNext()
            },
            onSubmit = {
                view.performHapticFeedback(HapticFeedbackConstants.CONFIRM)
                focusManager.clearFocus()
                onSubmit()
            },
        )

        Spacer(modifier = Modifier.height(EmberSpacing.xxl))
    }
}

@Composable
private fun ProgressSection(
    currentIndex: Int,
    modifier: Modifier = Modifier,
) {
    val progress by animateFloatAsState(
        targetValue = (currentIndex + 1).toFloat() / OnboardingUiState.QUESTION_COUNT,
        animationSpec = tween(durationMillis = 300),
        label = "progress_animation",
    )

    Column(
        modifier = modifier.padding(horizontal = EmberSpacing.lg),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            text = stringResource(
                R.string.onboarding_progress,
                currentIndex + 1,
                OnboardingUiState.QUESTION_COUNT,
            ),
            style = MaterialTheme.typography.labelMedium,
            color = EmberTextSecondary,
        )

        Spacer(modifier = Modifier.height(EmberSpacing.xs))

        LinearProgressIndicator(
            progress = { progress },
            modifier = Modifier
                .fillMaxWidth()
                .height(4.dp)
                .clip(EmberShapes.chip),
            color = EmberPrimary,
            trackColor = EmberSurface3,
        )
    }
}

@Composable
private fun QuestionCard(
    questionIndex: Int,
    answer: String,
    isSubmitting: Boolean,
    isLastQuestion: Boolean,
    onAnswerChanged: (String) -> Unit,
    onImeAction: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val focusRequester = remember { FocusRequester() }

    // Auto-focus text field when card appears
    LaunchedEffect(questionIndex) {
        delay(FOCUS_DELAY_MS)
        try {
            focusRequester.requestFocus()
        } catch (e: Exception) {
            // Focus request may fail if the composable is not yet laid out
        }
    }

    val questionTextResId = questionTextResIds.getOrElse(questionIndex) {
        R.string.onboarding_question_1
    }
    val placeholderResId = questionPlaceholderResIds.getOrElse(questionIndex) {
        R.string.onboarding_placeholder_1
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = EmberSpacing.lg),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Spacer(modifier = Modifier.height(EmberSpacing.xl))

        // Question number badge
        Box(
            contentAlignment = Alignment.Center,
            modifier = Modifier
                .size(32.dp)
                .clip(CircleShape)
                .background(EmberPrimary),
        ) {
            Text(
                text = "${questionIndex + 1}",
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.onPrimary,
            )
        }

        Spacer(modifier = Modifier.height(EmberSpacing.xl))

        // Question text
        Text(
            text = stringResource(questionTextResId),
            style = MaterialTheme.typography.headlineMedium,
            color = MaterialTheme.colorScheme.onBackground,
            textAlign = TextAlign.Center,
        )

        Spacer(modifier = Modifier.height(EmberSpacing.xl))

        // Answer input
        OutlinedTextField(
            value = answer,
            onValueChange = onAnswerChanged,
            placeholder = {
                Text(
                    text = stringResource(placeholderResId),
                    color = EmberTextDisabled,
                )
            },
            enabled = !isSubmitting,
            singleLine = false,
            maxLines = 3,
            keyboardOptions = KeyboardOptions(
                imeAction = if (isLastQuestion) ImeAction.Done else ImeAction.Next,
            ),
            keyboardActions = KeyboardActions(
                onNext = { onImeAction() },
                onDone = { onImeAction() },
            ),
            colors = authTextFieldColors(),
            shape = EmberShapes.input,
            modifier = Modifier
                .fillMaxWidth()
                .focusRequester(focusRequester),
        )
    }
}

@Composable
private fun QuestionNavigationButtons(
    currentIndex: Int,
    isSubmitting: Boolean,
    canSubmit: Boolean,
    currentAnswerNotEmpty: Boolean,
    onPrevious: () -> Unit,
    onNext: () -> Unit,
    onSubmit: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val isLastQuestion = currentIndex == OnboardingUiState.QUESTION_COUNT - 1

    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = EmberSpacing.lg),
        horizontalArrangement = Arrangement.spacedBy(EmberSpacing.sm),
    ) {
        // Back button
        if (currentIndex > 0) {
            TextButton(
                onClick = onPrevious,
                enabled = !isSubmitting,
            ) {
                Icon(
                    imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                    contentDescription = stringResource(R.string.onboarding_back),
                    tint = if (isSubmitting) EmberTextDisabled else EmberTextSecondary,
                )
                Text(
                    text = stringResource(R.string.onboarding_back),
                    style = MaterialTheme.typography.bodyMedium,
                    color = if (isSubmitting) EmberTextDisabled else EmberTextSecondary,
                )
            }
        }

        Spacer(modifier = Modifier.weight(1f))

        // Next / Submit button
        Button(
            onClick = if (isLastQuestion) onSubmit else onNext,
            enabled = !isSubmitting && if (isLastQuestion) canSubmit else true,
            shape = EmberShapes.pill,
            colors = ButtonDefaults.buttonColors(
                containerColor = EmberPrimary,
                disabledContainerColor = EmberTextDisabled,
            ),
            modifier = Modifier.height(52.dp),
        ) {
            if (isSubmitting) {
                CircularProgressIndicator(
                    color = MaterialTheme.colorScheme.onPrimary,
                    strokeWidth = EmberSpacing.xxs / 2,
                    modifier = Modifier.size(EmberSpacing.xl),
                )
            } else {
                Text(
                    text = if (isLastQuestion) {
                        stringResource(R.string.onboarding_submit)
                    } else {
                        stringResource(R.string.onboarding_next)
                    },
                    style = MaterialTheme.typography.titleMedium,
                )
            }
        }
    }
}

/**
 * Error dialog shown when onboarding submission fails.
 */
@Composable
fun OnboardingErrorDialog(
    message: String,
    onDismiss: () -> Unit,
    onRetry: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Text(
                text = stringResource(R.string.onboarding_error_title),
                style = MaterialTheme.typography.titleMedium,
            )
        },
        text = {
            Text(
                text = message,
                style = MaterialTheme.typography.bodyLarge,
            )
        },
        confirmButton = {
            TextButton(onClick = onRetry) {
                Text(
                    text = stringResource(R.string.onboarding_try_again),
                    color = EmberPrimary,
                )
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text(
                    text = stringResource(R.string.onboarding_dismiss),
                    color = EmberTextSecondary,
                )
            }
        },
    )
}

/** Question text resource IDs ordered by question index. */
private val questionTextResIds = listOf(
    R.string.onboarding_question_1,
    R.string.onboarding_question_2,
    R.string.onboarding_question_3,
    R.string.onboarding_question_4,
    R.string.onboarding_question_5,
    R.string.onboarding_question_6,
    R.string.onboarding_question_7,
)

/** Placeholder text resource IDs ordered by question index. */
private val questionPlaceholderResIds = listOf(
    R.string.onboarding_placeholder_1,
    R.string.onboarding_placeholder_2,
    R.string.onboarding_placeholder_3,
    R.string.onboarding_placeholder_4,
    R.string.onboarding_placeholder_5,
    R.string.onboarding_placeholder_6,
    R.string.onboarding_placeholder_7,
)

private const val FOCUS_DELAY_MS = 300L
