package ai.ember.app.features.memories

import ai.ember.app.core.models.Character
import ai.ember.app.core.models.MemoryItem

/**
 * Represents a segment in the character picker.
 * Either global memories or a specific character's memories.
 */
sealed interface MemorySegment {
    data object Global : MemorySegment
    data class CharacterSegment(
        val id: String,
        val name: String,
    ) : MemorySegment
}

/**
 * Sealed UI state for the Memories screen.
 */
sealed interface MemoriesUiState {

    /** Initial loading — fetching characters. */
    data object Loading : MemoriesUiState

    /** Characters and memories loaded successfully. */
    data class Success(
        val characters: List<Character>,
        val selectedSegment: MemorySegment = MemorySegment.Global,
        val memories: List<MemoryItem> = emptyList(),
        val isLoadingMemories: Boolean = false,
        val isDeletingMemoryId: String? = null,
    ) : MemoriesUiState

    /** Loading failed with a user-facing error message. */
    data class Error(val message: String) : MemoriesUiState
}
