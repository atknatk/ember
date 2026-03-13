package ai.ember.app.core.ui.theme

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Shapes
import androidx.compose.ui.unit.dp

/**
 * Corner radius tokens matching iOS CGFloat+Ember.swift.
 *
 * Usage:
 *   Modifier.clip(EmberShapes.messageBubble)
 *   Card(shape = EmberShapes.card)
 */
object EmberShapes {
    /** Small chip, badge — 4dp */
    val chip = RoundedCornerShape(4.dp)

    /** Input fields, small cards — 12dp */
    val input = RoundedCornerShape(12.dp)

    /** Message bubbles — 16dp */
    val messageBubble = RoundedCornerShape(16.dp)

    /** Main cards, modals — 20dp */
    val card = RoundedCornerShape(20.dp)

    /** CTA buttons, pill shape — 28dp */
    val pill = RoundedCornerShape(28.dp)
}

val EmberMaterialShapes = Shapes(
    small = RoundedCornerShape(4.dp),
    medium = RoundedCornerShape(12.dp),
    large = RoundedCornerShape(20.dp),
)
