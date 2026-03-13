package ai.ember.app.core.ui.theme

import android.app.Activity
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

/**
 * Ember dark-only Material 3 theme.
 *
 * Ember is dark-first. Force dark theme at the application level.
 * See docs/14-tasarim.md for the full design system specification.
 */
@Composable
fun EmberTheme(
    content: @Composable () -> Unit,
) {
    val colorScheme = EmberDarkColorScheme
    val view = LocalView.current

    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as? Activity)?.window ?: return@SideEffect
            window.statusBarColor = colorScheme.background.toArgb()
            window.navigationBarColor = colorScheme.surface.toArgb()
            WindowCompat.getInsetsController(window, view).apply {
                isAppearanceLightStatusBars = false
                isAppearanceLightNavigationBars = false
            }
        }
    }

    MaterialTheme(
        colorScheme = colorScheme,
        typography = EmberTypography,
        shapes = EmberMaterialShapes,
        content = content,
    )
}
