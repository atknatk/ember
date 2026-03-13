package ai.ember.app.features.chat

import android.view.HapticFeedbackConstants
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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import ai.ember.app.R
import ai.ember.app.core.ui.theme.EmberPrimary
import ai.ember.app.core.ui.theme.EmberSpacing
import ai.ember.app.core.ui.theme.EmberSurface3
import ai.ember.app.core.ui.theme.EmberTextSecondary

/**
 * Compact audio progress bar displayed inside an AI message bubble
 * during TTS playback.
 *
 * Shows play/pause toggle, elapsed/total time, progress indicator,
 * and a speed toggle button.
 */
@Composable
fun AudioProgressBar(
    isPlaying: Boolean,
    currentMs: Long,
    durationMs: Long,
    speed: Float,
    onPlayPause: () -> Unit,
    onSpeedToggle: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val view = LocalView.current
    val progress = if (durationMs > 0) {
        (currentMs.toFloat() / durationMs.toFloat()).coerceIn(0f, 1f)
    } else {
        0f
    }

    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(top = EmberSpacing.xs),
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth(),
        ) {
            // Play/Pause button
            IconButton(
                onClick = {
                    view.performHapticFeedback(HapticFeedbackConstants.CONTEXT_CLICK)
                    onPlayPause()
                },
                modifier = Modifier.size(BUTTON_SIZE),
            ) {
                Icon(
                    imageVector = if (isPlaying) Icons.Filled.Pause else Icons.Filled.PlayArrow,
                    contentDescription = if (isPlaying) {
                        stringResource(R.string.tts_pause)
                    } else {
                        stringResource(R.string.tts_resume)
                    },
                    tint = EmberPrimary,
                    modifier = Modifier.size(ICON_SIZE),
                )
            }

            Spacer(Modifier.width(EmberSpacing.xxs))

            // Time labels
            Text(
                text = formatTime(currentMs),
                style = MaterialTheme.typography.labelSmall,
                color = EmberTextSecondary,
            )

            // Progress bar
            Box(
                modifier = Modifier
                    .weight(1f)
                    .padding(horizontal = EmberSpacing.xs),
            ) {
                LinearProgressIndicator(
                    progress = { progress },
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(PROGRESS_HEIGHT)
                        .clip(RoundedCornerShape(PROGRESS_CORNER_RADIUS)),
                    color = EmberPrimary,
                    trackColor = EmberSurface3,
                )
            }

            Text(
                text = formatTime(durationMs),
                style = MaterialTheme.typography.labelSmall,
                color = EmberTextSecondary,
            )

            Spacer(Modifier.width(EmberSpacing.xxs))

            // Speed toggle
            TextButton(
                onClick = {
                    view.performHapticFeedback(HapticFeedbackConstants.CONTEXT_CLICK)
                    onSpeedToggle()
                },
                modifier = Modifier.height(BUTTON_SIZE),
            ) {
                Text(
                    text = formatSpeed(speed),
                    style = MaterialTheme.typography.labelSmall,
                    color = EmberPrimary,
                )
            }
        }
    }
}

/**
 * Loading state variant of the audio progress bar.
 * Shows an indeterminate progress indicator.
 */
@Composable
fun AudioProgressBarLoading(
    modifier: Modifier = Modifier,
) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Center,
        modifier = modifier
            .fillMaxWidth()
            .padding(top = EmberSpacing.xs, bottom = EmberSpacing.xxs),
    ) {
        LinearProgressIndicator(
            modifier = Modifier
                .fillMaxWidth()
                .height(PROGRESS_HEIGHT)
                .clip(RoundedCornerShape(PROGRESS_CORNER_RADIUS)),
            color = EmberPrimary,
            trackColor = EmberSurface3,
        )
    }
}

/**
 * Formats milliseconds to "M:SS" time string.
 */
private fun formatTime(ms: Long): String {
    val totalSeconds = (ms / MS_PER_SECOND).coerceAtLeast(0)
    val minutes = totalSeconds / SECONDS_PER_MINUTE
    val seconds = totalSeconds % SECONDS_PER_MINUTE
    return "$minutes:%02d".format(seconds)
}

/**
 * Formats speed float to display string (e.g., "1x", "1.25x").
 */
private fun formatSpeed(speed: Float): String {
    return if (speed == speed.toLong().toFloat()) {
        "${speed.toLong()}x"
    } else {
        "${speed}x"
    }
}

private val BUTTON_SIZE = 36.dp
private val ICON_SIZE = 20.dp
private val PROGRESS_HEIGHT = 3.dp
private val PROGRESS_CORNER_RADIUS = 2.dp
private const val MS_PER_SECOND = 1000L
private const val SECONDS_PER_MINUTE = 60L
