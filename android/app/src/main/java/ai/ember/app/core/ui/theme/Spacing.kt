package ai.ember.app.core.ui.theme

import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/**
 * Spacing tokens matching iOS CGFloat+Ember.swift (8px grid system).
 *
 * Usage:
 *   Modifier.padding(EmberSpacing.md)
 *   Spacer(Modifier.height(EmberSpacing.lg))
 */
object EmberSpacing {
    /** Icon-text gap, small padding — 4dp */
    val xxs: Dp = 4.dp

    /** Chip padding, small gap — 8dp */
    val xs: Dp = 8.dp

    /** List item vertical padding — 12dp */
    val sm: Dp = 12.dp

    /** Card padding, standard padding — 16dp */
    val md: Dp = 16.dp

    /** Screen horizontal margin — 20dp */
    val lg: Dp = 20.dp

    /** Section gap — 24dp */
    val xl: Dp = 24.dp

    /** Large section divider — 32dp */
    val xxl: Dp = 32.dp

    /** Screen top padding after safe area — 48dp */
    val xxxl: Dp = 48.dp
}
