package ai.ember.app.core.ui.components

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import ai.ember.app.core.ui.theme.EmberSurface2
import ai.ember.app.core.ui.theme.EmberSurface3

/**
 * Reusable shimmer loading component that renders a rounded rectangle
 * with a sweeping gradient animation to simulate content loading.
 *
 * The gradient moves from leading to trailing over 1.2 seconds and repeats.
 *
 * Colors: base fill EmberSurface2, shimmer highlight EmberSurface3.
 */
@Composable
fun ShimmerBox(
    modifier: Modifier = Modifier,
    shape: Shape = EmberShimmerDefaults.defaultShape,
) {
    val shimmerBrush = rememberShimmerBrush()
    Box(
        modifier = modifier
            .clip(shape)
            .background(shimmerBrush),
    )
}

/**
 * Circular shimmer placeholder for avatar loading states.
 */
@Composable
fun ShimmerCircle(
    size: Dp,
    modifier: Modifier = Modifier,
) {
    ShimmerBox(
        modifier = modifier.size(size),
        shape = CircleShape,
    )
}

/**
 * Creates the animated shimmer brush used across all shimmer components.
 *
 * The gradient sweeps from left to right with a 1200ms cycle, matching
 * the iOS ShimmerView implementation.
 */
@Composable
fun rememberShimmerBrush(): Brush {
    val transition = rememberInfiniteTransition(label = "shimmer")
    val translateX by transition.animateFloat(
        initialValue = -SHIMMER_WIDTH,
        targetValue = SHIMMER_WIDTH,
        animationSpec = infiniteRepeatable(
            animation = tween(
                durationMillis = SHIMMER_DURATION_MS,
                easing = LinearEasing,
            ),
            repeatMode = RepeatMode.Restart,
        ),
        label = "shimmerTranslateX",
    )

    return Brush.linearGradient(
        colors = listOf(
            EmberSurface2,
            EmberSurface3.copy(alpha = 0.6f),
            EmberSurface2,
        ),
        start = Offset(translateX, 0f),
        end = Offset(translateX + SHIMMER_WIDTH, 0f),
    )
}

internal object EmberShimmerDefaults {
    val defaultShape = androidx.compose.foundation.shape.RoundedCornerShape(12.dp)
}

private const val SHIMMER_DURATION_MS = 1200
private const val SHIMMER_WIDTH = 800f
