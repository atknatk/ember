package ai.ember.app.features.profile

import ai.ember.app.core.models.Character

/**
 * Sealed UI state for the Profile screen.
 */
sealed interface ProfileUiState {

    /** Initial loading -- fetching profile data. */
    data object Loading : ProfileUiState

    /** Profile loaded successfully. */
    data class Success(
        val profile: ProfileData,
        val characters: List<Character> = emptyList(),
        val isSaving: Boolean = false,
        val isEditingName: Boolean = false,
        val editedName: String = "",
        val showTimezonePicker: Boolean = false,
        val showDeleteConfirmation: Boolean = false,
        val deleteConfirmationText: String = "",
        val isUploadingAvatar: Boolean = false,
        val notificationPreferences: Map<String, Boolean> = emptyMap(),
        val snackbarMessage: String? = null,
    ) : ProfileUiState

    /** Loading failed with a user-facing error message. */
    data class Error(val message: String) : ProfileUiState
}
