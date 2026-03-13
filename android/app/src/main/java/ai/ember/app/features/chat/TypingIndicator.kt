package ai.ember.app.features.chat

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import ai.ember.app.R
import ai.ember.app.core.ui.theme.EmberAIBubbleEnd
import ai.ember.app.core.ui.theme.EmberAIBubbleStart
import ai.ember.app.core.ui.theme.EmberSpacing
import ai.ember.app.core.ui.theme.EmberTextSecondary

/**
 * Animated three-dot typing indicator shown while the AI is processing.
 *
 * Displays before the first SSE chunk arrives, then replaced by the
 * streaming assistant message bubble.
 *
 * Animation: Each dot bounces vertically with a 400ms period,
 * staggered 133ms between dots.
 */
@Composable
fun TypingIndicator(
    modifier: Modifier = Modifier,
) {
    val a11yLabel = stringResource(R.string.chat_typing_indicator)
    val transition = rememberInfiniteTransition(label = "typing")

    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.Start,
    ) {
        Box(
            modifier = Modifier
                .background(
                    brush = Brush.linearGradient(
                        listOf(EmberAIBubbleStart, EmberAIBubbleEnd),
                    ),
                    shape = RoundedCornerShape(
                        topStart = 16.dp,
                        topEnd = 16.dp,
                        bottomStart = 4.dp,
                        bottomEnd = 16.dp,
                    ),
                )
                .padding(
                    horizontal = EmberSpacing.md,
                    vertical = EmberSpacing.sm,
                )
                .semantics { contentDescription = a11yLabel },
        ) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(DOT_SPACING),
            ) {
                repeat(DOT_COUNT) { index ->
                    val delay = index * STAGGER_DELAY_MS
                    val offset by transition.animateFloat(
                        initialValue = 0f,
                        targetValue = -BOUNCE_HEIGHT,
                        animationSpec = infiniteRepeatable(
                            animation = tween(
                                durationMillis = ANIMATION_DURATION_MS,
                                delayMillis = delay,
                            ),
                            repeatMode = RepeatMode.Reverse,
                        ),
                        label = "dot_$index",
                    )

                    Box(
                        modifier = Modifier
                            .size(DOT_SIZE)
                            .offset { IntOffset(0, offset.toInt()) }
                            .clip(CircleShape)
                            .background(EmberTextSecondary),
                    )
                }
            }
        }
    }
}

private val DOT_SIZE = 6.dp
private val DOT_SPACING = 4.dp
private const val DOT_COUNT = 3
private const val BOUNCE_HEIGHT = 8f
private const val ANIMATION_DURATION_MS = 400
private const val STAGGER_DELAY_MS = 133
