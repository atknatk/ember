package ai.ember.app.core.navigation

import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import ai.ember.app.core.ui.components.EmberBottomBar
import ai.ember.app.core.ui.theme.EmberBackground
import ai.ember.app.features.auth.AuthScreen
import ai.ember.app.features.auth.AuthUiState
import ai.ember.app.features.auth.AuthViewModel
import ai.ember.app.features.home.HomeScreen
import ai.ember.app.features.memories.MemoriesScreen
import ai.ember.app.features.profile.ProfileScreen

/**
 * Root navigation host with auth flow and bottom tab bar.
 *
 * Determines start destination based on token state:
 * - If tokens exist: start at Home (main app)
 * - If no tokens: start at Auth (login/signup)
 *
 * On successful authentication, navigates to Home and clears the auth back stack.
 * Matches iOS AppRouter + MainTabView structure.
 */
@Composable
fun EmberNavHost() {
    val navController = rememberNavController()
    val navBackStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = navBackStackEntry?.destination?.route

    // Auth ViewModel scoped to the navigation graph for shared state
    val authViewModel: AuthViewModel = hiltViewModel()
    val authUiState by authViewModel.uiState.collectAsStateWithLifecycle()

    // Determine start destination based on existing tokens
    val startDestination = if (authViewModel.isAuthenticated) {
        Screen.Home.route
    } else {
        Screen.Auth.route
    }

    // Navigate to Home on successful authentication
    LaunchedEffect(authUiState) {
        if (authUiState is AuthUiState.Success) {
            navController.navigate(Screen.Home.route) {
                popUpTo(Screen.Auth.route) { inclusive = true }
                launchSingleTop = true
            }
        }
    }

    val showBottomBar = currentRoute in listOf(
        Screen.Home.route,
        Screen.Memories.route,
        Screen.Profile.route,
    )

    Scaffold(
        containerColor = EmberBackground,
        bottomBar = {
            if (showBottomBar) {
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
            }
        },
    ) { paddingValues ->
        NavHost(
            navController = navController,
            startDestination = startDestination,
            modifier = Modifier.padding(paddingValues),
        ) {
            composable(
                route = Screen.Auth.route,
                enterTransition = { fadeIn() },
                exitTransition = { fadeOut() },
            ) {
                AuthScreen(viewModel = authViewModel)
            }
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
