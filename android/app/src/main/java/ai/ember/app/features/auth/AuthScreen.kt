package ai.ember.app.features.auth

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import ai.ember.app.core.ui.theme.EmberBackground

/**
 * Root auth screen that switches between Login and Sign Up.
 *
 * Uses [AnimatedContent] for smooth slide transitions between forms,
 * matching the iOS sheet-based navigation pattern.
 */
@Composable
fun AuthScreen(
    viewModel: AuthViewModel = hiltViewModel(),
    modifier: Modifier = Modifier,
) {
    val isShowingSignUp by viewModel.isShowingSignUp.collectAsStateWithLifecycle()
    val snackbarHostState = remember { SnackbarHostState() }

    Scaffold(
        containerColor = EmberBackground,
        snackbarHost = { SnackbarHost(snackbarHostState) },
        modifier = modifier,
    ) { paddingValues ->
        AnimatedContent(
            targetState = isShowingSignUp,
            transitionSpec = {
                if (targetState) {
                    // Login -> SignUp: slide in from right
                    (slideInHorizontally { it } + fadeIn()) togetherWith
                        (slideOutHorizontally { -it } + fadeOut())
                } else {
                    // SignUp -> Login: slide in from left
                    (slideInHorizontally { -it } + fadeIn()) togetherWith
                        (slideOutHorizontally { it } + fadeOut())
                }
            },
            label = "AuthScreenTransition",
        ) { showSignUp ->
            if (showSignUp) {
                SignUpScreen(
                    viewModel = viewModel,
                    snackbarHostState = snackbarHostState,
                )
            } else {
                LoginScreen(
                    viewModel = viewModel,
                    snackbarHostState = snackbarHostState,
                )
            }
        }
    }
}
