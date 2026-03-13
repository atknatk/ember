package ai.ember.app.core.navigation

import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import ai.ember.app.core.ui.components.EmberBottomBar
import ai.ember.app.core.ui.theme.EmberBackground
import ai.ember.app.features.home.HomeScreen
import ai.ember.app.features.memories.MemoriesScreen
import ai.ember.app.features.profile.ProfileScreen

/**
 * Root navigation host with bottom tab bar.
 *
 * Matches iOS MainTabView structure: Home, Memories, Profile.
 */
@Composable
fun EmberNavHost() {
    val navController = rememberNavController()
    val navBackStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = navBackStackEntry?.destination?.route

    Scaffold(
        containerColor = EmberBackground,
        bottomBar = {
            EmberBottomBar(
                currentRoute = currentRoute,
                onTabSelected = { tab ->
                    navController.navigate(tab.screen.route) {
                        popUpTo(navController.graph.findStartDestination().id) {
                            saveState = true
                        }
                        launchSingleTop = true
                        restoreState = true
                    }
                },
            )
        },
    ) { paddingValues ->
        NavHost(
            navController = navController,
            startDestination = Screen.Home.route,
            modifier = Modifier.padding(paddingValues),
        ) {
            composable(Screen.Home.route) {
                HomeScreen()
            }
            composable(Screen.Memories.route) {
                MemoriesScreen()
            }
            composable(Screen.Profile.route) {
                ProfileScreen()
            }
        }
    }
}
