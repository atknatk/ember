package ai.ember.app.features.auth

/**
 * Sealed UI state for authentication screens (Login / Sign Up).
 */
sealed interface AuthUiState {
    /** Initial idle state — form is ready for input. */
    data object Idle : AuthUiState

    /** Authentication request is in progress. */
    data object Loading : AuthUiState

    /** Authentication succeeded. */
    data object Success : AuthUiState

    /** Authentication failed with a user-facing error message. */
    data class Error(val message: String) : AuthUiState
}
