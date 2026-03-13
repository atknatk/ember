package ai.ember.app.features.chat

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp

/**
 * Animated waveform visualization showing audio amplitude as vertical bars.
 *
 * Displays [BAR_COUNT] bars whose heights are driven by the [amplitudes] list.
 * Each bar animates smoothly using spring physics for a natural feel.
 * Used during voice recording to provide visual feedback of audio input.
 */
@Composable
fun WaveformBars(
    amplitudes: List<Float>,
    modifier: Modifier = Modifier,
) {
    Row(
        horizontalArrangement = Arrangement.spacedBy(BAR_GAP),
        verticalAlignment = Alignment.CenterVertically,
        modifier = modifier,
    ) {
        for (i in 0 until BAR_COUNT) {
            val amplitude = amplitudes.getOrElse(i) { MIN_BAR_FRACTION }

            val animatedHeight by animateFloatAsState(
                targetValue = amplitude.coerceIn(MIN_BAR_FRACTION, MAX_BAR_FRACTION),
                animationSpec = spring(
                    dampingRatio = SPRING_DAMPING,
                    stiffness = SPRING_STIFFNESS,
                ),
                label = "waveformBar$i",
            )

            Box(
                modifier = Modifier
                    .width(BAR_WIDTH)
                    .height(MAX_BAR_HEIGHT * animatedHeight)
                    .clip(BAR_SHAPE)
                    .background(MaterialTheme.colorScheme.primary),
            )
        }
    }
}

private val BAR_WIDTH = 3.dp
private val BAR_GAP = 2.dp
private val MAX_BAR_HEIGHT = 32.dp
private val BAR_SHAPE = RoundedCornerShape(2.dp)
private const val BAR_COUNT = 12
private const val MIN_BAR_FRACTION = 0.1f
private const val MAX_BAR_FRACTION = 1.0f
private const val SPRING_DAMPING = 0.6f
private const val SPRING_STIFFNESS = 600f
