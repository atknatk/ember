package ai.ember.app.core.ui.components

import android.view.HapticFeedbackConstants
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.res.stringResource
import ai.ember.app.core.navigation.BottomTab
import ai.ember.app.core.ui.theme.EmberPrimary
import ai.ember.app.core.ui.theme.EmberSurface
import ai.ember.app.core.ui.theme.EmberTextDisabled
import ai.ember.app.core.ui.theme.EmberTextPrimary

/**
 * Bottom navigation bar with Home, Memories, and Profile tabs.
 *
 * Matches iOS MainTabView behavior:
 * - Uses outlined icons for unselected, filled for selected.
 * - Haptic feedback on tab selection.
 * - Surface background color.
 */
@Composable
fun EmberBottomBar(
    currentRoute: String?,
    onTabSelected: (BottomTab) -> Unit,
    modifier: Modifier = Modifier,
) {
    val view = LocalView.current

    NavigationBar(
        containerColor = EmberSurface,
        contentColor = EmberTextPrimary,
        modifier = modifier,
    ) {
        BottomTab.entries.forEach { tab ->
            val isSelected = currentRoute == tab.screen.route

            NavigationBarItem(
                selected = isSelected,
                onClick = {
                    if (!isSelected) {
                        view.performHapticFeedback(HapticFeedbackConstants.CONTEXT_CLICK)
                        onTabSelected(tab)
                    }
                },
                icon = {
                    Icon(
                        imageVector = if (isSelected) tab.selectedIcon else tab.unselectedIcon,
                        contentDescription = stringResource(tab.contentDescriptionResId),
                    )
                },
                label = {
                    Text(
                        text = stringResource(tab.labelResId),
                        style = MaterialTheme.typography.labelSmall,
                    )
                },
                colors = NavigationBarItemDefaults.colors(
                    selectedIconColor = EmberPrimary,
                    selectedTextColor = EmberPrimary,
                    unselectedIconColor = EmberTextDisabled,
                    unselectedTextColor = EmberTextDisabled,
                    indicatorColor = EmberPrimary.copy(alpha = 0.12f),
                ),
            )
        }
    }
}
