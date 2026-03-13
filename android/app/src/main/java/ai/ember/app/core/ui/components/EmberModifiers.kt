package ai.ember.app.core.ui.components

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import ai.ember.app.core.ui.theme.EmberShapes

/**
 * Standard Ember card shadow modifier.
 *
 * Applies a subtle drop shadow matching the iOS EmberCardShadow modifier:
 * color black at 30% opacity, radius 8dp, y-offset 4dp.
 *
 * Usage: Modifier.emberCardShadow()
 */
fun Modifier.emberCardShadow(
    elevation: Dp = 8.dp,
): Modifier = this.shadow(
    elevation = elevation,
    shape = EmberShapes.card,
    ambientColor = Color.Black.copy(alpha = 0.3f),
    spotColor = Color.Black.copy(alpha = 0.3f),
)

/**
 * Light variant of card shadow for smaller elements like MemoryRow.
 *
 * Matches the iOS EmberCardShadowLight: opacity 0.15, radius 4dp, y-offset 2dp.
 *
 * Usage: Modifier.emberCardShadowLight()
 */
fun Modifier.emberCardShadowLight(
    elevation: Dp = 4.dp,
): Modifier = this.shadow(
    elevation = elevation,
    shape = EmberShapes.input,
    ambientColor = Color.Black.copy(alpha = 0.15f),
    spotColor = Color.Black.copy(alpha = 0.15f),
)

/**
 * Scale-on-press animation modifier for buttons and interactive elements.
 *
 * Scales the element to [pressedScale] (default 0.85) on press, then
 * springs back to 1.0 on release. Matches the iOS ScaleButtonStyle.
 *
 * Usage: Modifier.scaleOnPress { onClick() }
 */
fun Modifier.scaleOnPress(
    pressedScale: Float = PRESSED_SCALE,
    onClick: () -> Unit,
): Modifier = composed {
    var isPressed by remember { mutableStateOf(false) }
    val scale by animateFloatAsState(
        targetValue = if (isPressed) pressedScale else 1f,
        animationSpec = spring(
            dampingRatio = SPRING_DAMPING,
            stiffness = SPRING_STIFFNESS,
        ),
        label = "scaleOnPress",
    )

    this
        .graphicsLayer {
            scaleX = scale
            scaleY = scale
        }
        .pointerInput(Unit) {
            detectTapGestures(
                onPress = {
                    isPressed = true
                    tryAwaitRelease()
                    isPressed = false
                    onClick()
                },
            )
        }
}

private const val PRESSED_SCALE = 0.85f
private const val SPRING_DAMPING = 0.6f
private const val SPRING_STIFFNESS = 800f
