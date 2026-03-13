package ai.ember.app.features.home

import ai.ember.app.core.models.Character
import ai.ember.app.core.models.MessagePreview

/**
 * Sealed UI state for the Home screen.
 */
sealed interface HomeUiState {

    /** Initial loading state — no data yet. */
    data object Loading : HomeUiState

    /** Characters loaded successfully. */
    data class Success(
        val characters: List<Character>,
        val lastMessages: Map<String, MessagePreview> = emptyMap(),
        val userName: String = "",
        val isRefreshing: Boolean = false,
    ) : HomeUiState

    /** No characters exist for this user. */
    data class Empty(
        val userName: String = "",
    ) : HomeUiState

    /** Loading failed with a user-facing error message. */
    data class Error(val message: String) : HomeUiState
}
