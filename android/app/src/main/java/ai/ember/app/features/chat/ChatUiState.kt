package ai.ember.app.features.chat

import ai.ember.app.core.error.EmberError

/**
 * Sealed UI state for the Chat screen.
 *
 * Follows the mandatory pattern: Loading, Success, Error.
 * Success includes streaming state for SSE response handling.
 */
sealed interface ChatUiState {

    /** Initial loading state while fetching message history. */
    data object Loading : ChatUiState

    /** Messages loaded successfully. */
    data class Success(
        val messages: List<ChatMessage>,
        val isStreaming: Boolean = false,
        val isLoadingMore: Boolean = false,
        val hasMoreMessages: Boolean = false,
        val nextCursor: String? = null,
        val characterName: String = "",
        val currentError: EmberError? = null,
    ) : ChatUiState

    /** Loading failed with a user-facing error message. */
    data class Error(val message: String) : ChatUiState
}
