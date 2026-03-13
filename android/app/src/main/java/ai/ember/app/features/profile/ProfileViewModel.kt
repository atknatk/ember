package ai.ember.app.features.profile

import android.content.SharedPreferences
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import ai.ember.app.core.auth.AuthRepository
import ai.ember.app.core.error.EmberError
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import javax.inject.Inject

/**
 * ViewModel for the Profile screen.
 *
 * Manages profile loading, updating, avatar upload, sign out,
 * and account deletion. Notification preferences are stored
 * locally via SharedPreferences.
 *
 * Mirrors iOS ProfileViewModel behavior.
 */
@HiltViewModel
class ProfileViewModel @Inject constructor(
    private val profileRepository: ProfileRepository,
    private val authRepository: AuthRepository,
    private val json: Json,
) : ViewModel() {

    private val _uiState = MutableStateFlow<ProfileUiState>(ProfileUiState.Loading)
    val uiState: StateFlow<ProfileUiState> = _uiState.asStateFlow()

    /** Set to true when the user should be navigated to the auth screen. */
    private val _shouldSignOut = MutableStateFlow(false)
    val shouldSignOut: StateFlow<Boolean> = _shouldSignOut.asStateFlow()

    init {
        loadProfile()
    }

    /**
     * Loads the user's profile and character list in parallel.
     */
    fun loadProfile() {
        viewModelScope.launch {
            _uiState.value = ProfileUiState.Loading

            val profileDeferred = async { profileRepository.getProfile() }
            val charactersDeferred = async { profileRepository.getCharacters() }

            val profileResult = profileDeferred.await()
            val charactersResult = charactersDeferred.await()

            profileResult
                .onSuccess { profile ->
                    val characters = charactersResult.getOrDefault(emptyList())
                    _uiState.value = ProfileUiState.Success(
                        profile = profile,
                        characters = characters,
                        editedName = profile.name,
                    )
                }
                .onFailure { e ->
                    val emberError = EmberError.from(e)
                    _uiState.value = ProfileUiState.Error(emberError.userMessage)
                }
        }
    }

    /**
     * Starts editing the display name.
     */
    fun startEditingName() {
        val currentState = _uiState.value as? ProfileUiState.Success ?: return
        _uiState.value = currentState.copy(
            isEditingName = true,
            editedName = currentState.profile.name,
        )
    }

    /**
     * Cancels name editing.
     */
    fun cancelEditingName() {
        val currentState = _uiState.value as? ProfileUiState.Success ?: return
        _uiState.value = currentState.copy(
            isEditingName = false,
            editedName = currentState.profile.name,
        )
    }

    /**
     * Updates the edited name text.
     */
    fun onNameChanged(name: String) {
        val currentState = _uiState.value as? ProfileUiState.Success ?: return
        _uiState.value = currentState.copy(editedName = name)
    }

    /**
     * Saves the edited display name via PUT /api/v1/profile.
     */
    fun saveName() {
        val currentState = _uiState.value as? ProfileUiState.Success ?: return
        val trimmedName = currentState.editedName.trim()
        if (trimmedName.isEmpty()) {
            _uiState.value = currentState.copy(
                snackbarMessage = "Name cannot be empty",
            )
            return
        }

        _uiState.value = currentState.copy(isSaving = true)

        viewModelScope.launch {
            profileRepository.updateProfile(ProfileUpdateRequest(name = trimmedName))
                .onSuccess { updatedProfile ->
                    val latestState = _uiState.value as? ProfileUiState.Success ?: return@launch
                    _uiState.value = latestState.copy(
                        profile = updatedProfile,
                        isEditingName = false,
                        editedName = updatedProfile.name,
                        isSaving = false,
                        snackbarMessage = "Name updated",
                    )
                }
                .onFailure { e ->
                    val latestState = _uiState.value as? ProfileUiState.Success ?: return@launch
                    val emberError = EmberError.from(e)
                    _uiState.value = latestState.copy(
                        isSaving = false,
                        currentError = emberError,
                    )
                }
        }
    }

    /**
     * Updates the timezone via PUT /api/v1/profile.
     */
    fun updateTimezone(timezone: String) {
        val currentState = _uiState.value as? ProfileUiState.Success ?: return
        _uiState.value = currentState.copy(isSaving = true, showTimezonePicker = false)

        viewModelScope.launch {
            profileRepository.updateProfile(ProfileUpdateRequest(timezone = timezone))
                .onSuccess { updatedProfile ->
                    val latestState = _uiState.value as? ProfileUiState.Success ?: return@launch
                    _uiState.value = latestState.copy(
                        profile = updatedProfile,
                        isSaving = false,
                        snackbarMessage = "Timezone updated",
                    )
                }
                .onFailure { e ->
                    val latestState = _uiState.value as? ProfileUiState.Success ?: return@launch
                    val emberError = EmberError.from(e)
                    _uiState.value = latestState.copy(
                        isSaving = false,
                        currentError = emberError,
                    )
                }
        }
    }

    /**
     * Updates the preferred language via PUT /api/v1/profile.
     */
    fun updateLanguage(language: String) {
        val currentState = _uiState.value as? ProfileUiState.Success ?: return
        _uiState.value = currentState.copy(isSaving = true)

        viewModelScope.launch {
            profileRepository.updateProfile(ProfileUpdateRequest(preferredLanguage = language))
                .onSuccess { updatedProfile ->
                    val latestState = _uiState.value as? ProfileUiState.Success ?: return@launch
                    _uiState.value = latestState.copy(
                        profile = updatedProfile,
                        isSaving = false,
                        snackbarMessage = "Language updated",
                    )
                }
                .onFailure { e ->
                    val latestState = _uiState.value as? ProfileUiState.Success ?: return@launch
                    val emberError = EmberError.from(e)
                    _uiState.value = latestState.copy(
                        isSaving = false,
                        currentError = emberError,
                    )
                }
        }
    }

    /**
     * Uploads a new avatar image to S3 and updates the profile.
     */
    fun uploadAvatar(imageData: ByteArray) {
        val currentState = _uiState.value as? ProfileUiState.Success ?: return
        _uiState.value = currentState.copy(isUploadingAvatar = true)

        viewModelScope.launch {
            profileRepository.getUploadUrl("avatar.jpg", "image/jpeg")
                .onSuccess { uploadResponse ->
                    profileRepository.uploadToS3(
                        uploadResponse.uploadUrl,
                        imageData,
                        "image/jpeg",
                    ).onSuccess {
                        profileRepository.updateProfile(
                            ProfileUpdateRequest(avatarUrl = uploadResponse.fileUrl),
                        ).onSuccess { updatedProfile ->
                            val latestState = _uiState.value as? ProfileUiState.Success
                                ?: return@launch
                            _uiState.value = latestState.copy(
                                profile = updatedProfile,
                                isUploadingAvatar = false,
                                snackbarMessage = "Avatar updated",
                            )
                        }.onFailure { e ->
                            handleAvatarError(e)
                        }
                    }.onFailure { e ->
                        handleAvatarError(e)
                    }
                }
                .onFailure { e ->
                    handleAvatarError(e)
                }
        }
    }

    private fun handleAvatarError(e: Throwable) {
        val latestState = _uiState.value as? ProfileUiState.Success ?: return
        val emberError = EmberError.from(e)
        _uiState.value = latestState.copy(
            isUploadingAvatar = false,
            currentError = emberError,
        )
    }

    /**
     * Shows the timezone picker dialog.
     */
    fun showTimezonePicker() {
        val currentState = _uiState.value as? ProfileUiState.Success ?: return
        _uiState.value = currentState.copy(showTimezonePicker = true)
    }

    /**
     * Hides the timezone picker dialog.
     */
    fun hideTimezonePicker() {
        val currentState = _uiState.value as? ProfileUiState.Success ?: return
        _uiState.value = currentState.copy(showTimezonePicker = false)
    }

    /**
     * Shows the delete account confirmation dialog.
     */
    fun showDeleteConfirmation() {
        val currentState = _uiState.value as? ProfileUiState.Success ?: return
        _uiState.value = currentState.copy(
            showDeleteConfirmation = true,
            deleteConfirmationText = "",
        )
    }

    /**
     * Hides the delete account confirmation dialog.
     */
    fun hideDeleteConfirmation() {
        val currentState = _uiState.value as? ProfileUiState.Success ?: return
        _uiState.value = currentState.copy(
            showDeleteConfirmation = false,
            deleteConfirmationText = "",
        )
    }

    /**
     * Updates the delete confirmation text input.
     */
    fun onDeleteConfirmationTextChanged(text: String) {
        val currentState = _uiState.value as? ProfileUiState.Success ?: return
        _uiState.value = currentState.copy(deleteConfirmationText = text)
    }

    /**
     * Deletes the user's account after confirmation.
     */
    fun deleteAccount() {
        val currentState = _uiState.value as? ProfileUiState.Success ?: return
        if (currentState.deleteConfirmationText != REQUIRED_DELETE_CONFIRMATION) {
            _uiState.value = currentState.copy(
                snackbarMessage = "Please type DELETE MY ACCOUNT to confirm",
            )
            return
        }

        _uiState.value = currentState.copy(isSaving = true)

        viewModelScope.launch {
            profileRepository.deleteAccount(REQUIRED_DELETE_CONFIRMATION)
                .onSuccess {
                    authRepository.signOut()
                    _shouldSignOut.value = true
                }
                .onFailure { e ->
                    val latestState = _uiState.value as? ProfileUiState.Success ?: return@launch
                    val emberError = EmberError.from(e)
                    _uiState.value = latestState.copy(
                        isSaving = false,
                        showDeleteConfirmation = false,
                        deleteConfirmationText = "",
                        currentError = emberError,
                    )
                }
        }
    }

    /**
     * Signs out the current user.
     *
     * Sets shouldSignOut flag. The actual token clearing and navigation
     * is handled by the onSignOut callback in the NavHost to avoid
     * double sign-out when AuthViewModel.signOut() is also called.
     */
    fun signOut() {
        _shouldSignOut.value = true
    }

    /**
     * Updates a notification preference locally.
     * No API call -- placeholder for future notification preferences endpoint.
     */
    fun updateNotificationPreference(key: String, value: Boolean) {
        val currentState = _uiState.value as? ProfileUiState.Success ?: return
        val updatedPrefs = currentState.notificationPreferences.toMutableMap()
        updatedPrefs[key] = value
        _uiState.value = currentState.copy(notificationPreferences = updatedPrefs)
    }

    /**
     * Clears the snackbar message.
     */
    fun clearSnackbar() {
        val currentState = _uiState.value as? ProfileUiState.Success ?: return
        _uiState.value = currentState.copy(snackbarMessage = null)
    }

    /**
     * Dismisses the current transient error banner.
     */
    fun dismissError() {
        val currentState = _uiState.value as? ProfileUiState.Success ?: return
        _uiState.value = currentState.copy(currentError = null)
    }

    companion object {
        const val REQUIRED_DELETE_CONFIRMATION = "DELETE MY ACCOUNT"
    }
}
