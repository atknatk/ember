package ai.ember.app.core.navigation

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccountCircle
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Psychology
import androidx.compose.material.icons.outlined.AccountCircle
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.Psychology
import androidx.compose.ui.graphics.vector.ImageVector

/**
 * Sealed route definitions for navigation.
 */
sealed class Screen(val route: String) {
    data object Auth : Screen("auth")
    data object Onboarding : Screen("onboarding")
    data object Home : Screen("home")
    data object Memories : Screen("memories")
    data object Profile : Screen("profile")
    data object Chat : Screen("chat/{characterId}/{characterName}") {
        fun createRoute(characterId: String, characterName: String): String =
            "chat/$characterId/$characterName"
    }
    data object CreateCharacter : Screen("create_character")
}

/**
 * Bottom navigation tab definitions matching iOS MainTabView.
 *
 * Uses Material Icons: outlined for unselected, filled for selected.
 */
enum class BottomTab(
    val screen: Screen,
    val labelResId: Int,
    val selectedIcon: ImageVector,
    val unselectedIcon: ImageVector,
    val contentDescriptionResId: Int,
) {
    HOME(
        screen = Screen.Home,
        labelResId = ai.ember.app.R.string.tab_home,
        selectedIcon = Icons.Filled.Home,
        unselectedIcon = Icons.Outlined.Home,
        contentDescriptionResId = ai.ember.app.R.string.tab_home,
    ),
    MEMORIES(
        screen = Screen.Memories,
        labelResId = ai.ember.app.R.string.tab_memories,
        selectedIcon = Icons.Filled.Psychology,
        unselectedIcon = Icons.Outlined.Psychology,
        contentDescriptionResId = ai.ember.app.R.string.tab_memories,
    ),
    PROFILE(
        screen = Screen.Profile,
        labelResId = ai.ember.app.R.string.tab_profile,
        selectedIcon = Icons.Filled.AccountCircle,
        unselectedIcon = Icons.Outlined.AccountCircle,
        contentDescriptionResId = ai.ember.app.R.string.tab_profile,
    ),
}
