package ai.ember.app.core.ui.components

import android.view.HapticFeedbackConstants
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.ErrorOutline
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import ai.ember.app.R
import ai.ember.app.core.error.EmberError
import ai.ember.app.core.ui.theme.EmberError as EmberErrorColor
import ai.ember.app.core.ui.theme.EmberSpacing
import kotlinx.coroutines.delay

/**
 * Non-blocking, dismissible error banner that slides down from the top.
 *
 * Shows error icon, user-friendly message, optional retry button (for
 * retryable errors), and a dismiss button. Auto-dismisses after
 * [autoDismissMs] milliseconds.
 *
 * Mirrors iOS ErrorBannerView behavior and design.
 *
 * @param error The [EmberError] to display, or null to hide the banner.
 * @param onDismiss Callback when the user dismisses the banner or it auto-dismisses.
 * @param onRetry Optional callback for the retry button. Only shown if the error is retryable.
 * @param autoDismissMs Auto-dismiss delay in milliseconds. Set to 0 to disable.
 */
@Composable
fun ErrorBanner(
    error: EmberError?,
    onDismiss: () -> Unit,
    onRetry: (() -> Unit)? = null,
    autoDismissMs: Long = DEFAULT_AUTO_DISMISS_MS,
    modifier: Modifier = Modifier,
) {
    val view = LocalView.current
    val isVisible = error != null

    // Haptic feedback on appearance
    LaunchedEffect(error) {
        if (error != null) {
            view.performHapticFeedback(HapticFeedbackConstants.REJECT)
        }
    }

    // Auto-dismiss
    LaunchedEffect(error) {
        if (error != null && autoDismissMs > 0) {
            delay(autoDismissMs)
            onDismiss()
        }
    }

    AnimatedVisibility(
        visible = isVisible,
        enter = expandVertically(expandFrom = Alignment.Top) + fadeIn(),
        exit = shrinkVertically(shrinkTowards = Alignment.Top) + fadeOut(),
        modifier = modifier,
    ) {
        if (error != null) {
            ErrorBannerContent(
                error = error,
                onDismiss = onDismiss,
                onRetry = if (error.isRetryable) onRetry else null,
            )
        }
    }
}

@Composable
private fun ErrorBannerContent(
    error: EmberError,
    onDismiss: () -> Unit,
    onRetry: (() -> Unit)?,
    modifier: Modifier = Modifier,
) {
    val bannerA11y = stringResource(R.string.error_banner_a11y, error.userMessage)

    Row(
        modifier = modifier
            .fillMaxWidth()
            .background(EmberErrorColor.copy(alpha = BANNER_BACKGROUND_ALPHA))
            .padding(
                start = EmberSpacing.md,
                end = EmberSpacing.xxs,
                top = EmberSpacing.xs,
                bottom = EmberSpacing.xs,
            )
            .semantics { contentDescription = bannerA11y },
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        // Error icon
        Icon(
            imageVector = Icons.Outlined.ErrorOutline,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.onError,
            modifier = Modifier.size(20.dp),
        )

        Spacer(Modifier.width(EmberSpacing.xs))

        // Error message
        Text(
            text = error.userMessage,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onError,
            modifier = Modifier.weight(1f),
        )

        // Retry button (if retryable)
        if (onRetry != null) {
            TextButton(onClick = onRetry) {
                Icon(
                    imageVector = Icons.Outlined.Refresh,
                    contentDescription = stringResource(R.string.error_banner_retry),
                    tint = MaterialTheme.colorScheme.onError,
                    modifier = Modifier.size(18.dp),
                )
            }
        }

        // Dismiss button
        IconButton(
            onClick = onDismiss,
            modifier = Modifier.size(DISMISS_BUTTON_SIZE),
        ) {
            Icon(
                imageVector = Icons.Outlined.Close,
                contentDescription = stringResource(R.string.error_banner_dismiss),
                tint = MaterialTheme.colorScheme.onError,
                modifier = Modifier.size(18.dp),
            )
        }
    }
}

private const val DEFAULT_AUTO_DISMISS_MS = 5000L
private const val BANNER_BACKGROUND_ALPHA = 0.9f
private val DISMISS_BUTTON_SIZE = 36.dp
