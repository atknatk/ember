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
import ai.ember.app.features.onboarding.OnboardingScreen
import ai.ember.app.features.profile.ProfileScreen

/**
 * Root navigation host with auth flow, onboarding, and bottom tab bar.
 *
 * Determines start destination based on token and onboarding state:
 * - If no tokens: start at Auth (login/signup)
 * - If tokens exist but onboarding not completed: start at Onboarding
 * - If tokens exist and onboarding completed: start at Home (main app)
 *
 * On successful authentication, navigates to Onboarding or Home based on
 * the onboarding_completed flag from the auth response.
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

    // Determine start destination based on existing tokens and onboarding state
    val startDestination = when {
        !authViewModel.isAuthenticated -> Screen.Auth.route
        !authViewModel.hasCompletedOnboarding -> Screen.Onboarding.route
        else -> Screen.Home.route
    }

    // Navigate after successful authentication
    LaunchedEffect(authUiState) {
        if (authUiState is AuthUiState.Success) {
            val destination = if (authViewModel.hasCompletedOnboarding) {
                Screen.Home.route
            } else {
                Screen.Onboarding.route
            }
            navController.navigate(destination) {
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
            composable(
                route = Screen.Onboarding.route,
                enterTransition = { fadeIn() },
                exitTransition = { fadeOut() },
            ) {
                OnboardingScreen(
                    onOnboardingComplete = {
                        authViewModel.setOnboardingCompleted()
                        navController.navigate(Screen.Home.route) {
                            popUpTo(Screen.Onboarding.route) { inclusive = true }
                            launchSingleTop = true
                        }
                    },
                )
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
