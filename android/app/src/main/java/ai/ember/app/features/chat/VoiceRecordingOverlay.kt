package ai.ember.app.features.chat

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.KeyboardArrowUp
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import ai.ember.app.R
import ai.ember.app.core.ui.theme.EmberError
import ai.ember.app.core.ui.theme.EmberSpacing
import ai.ember.app.core.ui.theme.EmberSurface

/**
 * Overlay that appears above the chat input bar during voice recording.
 *
 * Shows a pulsing red dot, duration timer, waveform visualization,
 * and a "slide up to cancel" hint. Appears/disappears with slide + fade
 * animation matching the design system transition specs.
 */
@Composable
fun VoiceRecordingOverlay(
    isVisible: Boolean,
    durationMs: Long,
    amplitudes: List<Float>,
    modifier: Modifier = Modifier,
) {
    AnimatedVisibility(
        visible = isVisible,
        enter = slideInVertically(initialOffsetY = { it }) + fadeIn(),
        exit = slideOutVertically(targetOffsetY = { it }) + fadeOut(),
        modifier = modifier,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier
                .fillMaxWidth()
                .background(EmberSurface)
                .padding(
                    horizontal = EmberSpacing.md,
                    vertical = EmberSpacing.sm,
                ),
        ) {
            // Recording indicator row: red dot + timer + waveform
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.Center,
                modifier = Modifier.fillMaxWidth(),
            ) {
                PulsingRecordingDot()

                Spacer(Modifier.width(EmberSpacing.xs))

                Text(
                    text = formatDuration(durationMs),
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurface,
                    modifier = Modifier.semantics {
                        liveRegion = LiveRegionMode.Polite
                    },
                )

                Spacer(Modifier.width(EmberSpacing.md))

                WaveformBars(
                    amplitudes = amplitudes,
                )
            }

            Spacer(Modifier.height(EmberSpacing.xs))

            // Cancel hint
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.Center,
            ) {
                Icon(
                    imageVector = Icons.Outlined.KeyboardArrowUp,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.size(16.dp),
                )
                Spacer(Modifier.width(EmberSpacing.xxs))
                Text(
                    text = stringResource(R.string.voice_slide_to_cancel),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

/**
 * Pulsing red dot indicating active recording.
 * Animates opacity between 0.3 and 1.0 at 800ms period.
 */
@Composable
private fun PulsingRecordingDot(
    modifier: Modifier = Modifier,
) {
    val infiniteTransition = rememberInfiniteTransition(label = "recordingPulse")
    val alpha by infiniteTransition.animateFloat(
        initialValue = PULSE_MIN_ALPHA,
        targetValue = PULSE_MAX_ALPHA,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = PULSE_DURATION_MS),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "recordingDotAlpha",
    )

    Box(
        modifier = modifier
            .size(RECORDING_DOT_SIZE)
            .alpha(alpha)
            .clip(CircleShape)
            .background(EmberError),
    )
}

/**
 * Formats milliseconds into MM:SS display string.
 */
private fun formatDuration(durationMs: Long): String {
    val totalSeconds = durationMs / MILLIS_PER_SECOND
    val minutes = totalSeconds / SECONDS_PER_MINUTE
    val seconds = totalSeconds % SECONDS_PER_MINUTE
    return "%d:%02d".format(minutes, seconds)
}

private val RECORDING_DOT_SIZE = 10.dp
private const val PULSE_MIN_ALPHA = 0.3f
private const val PULSE_MAX_ALPHA = 1.0f
private const val PULSE_DURATION_MS = 800
private const val MILLIS_PER_SECOND = 1000
private const val SECONDS_PER_MINUTE = 60
