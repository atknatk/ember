package ai.ember.app.features.home

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.AutoStories
import androidx.compose.material.icons.outlined.Favorite
import androidx.compose.material.icons.outlined.FitnessCenter
import androidx.compose.material.icons.outlined.Person
import androidx.compose.material.icons.outlined.Work
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import ai.ember.app.core.auth.AuthRepository
import ai.ember.app.core.error.EmberError
import ai.ember.app.core.models.Character
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.util.Calendar
import javax.inject.Inject

/**
 * ViewModel for the Home screen.
 *
 * Loads characters and their last message previews, provides
 * time-based greeting, and tracks local unread state.
 * Mirrors iOS HomeViewModel behavior.
 */
@HiltViewModel
class HomeViewModel @Inject constructor(
    private val homeRepository: HomeRepository,
    private val authRepository: AuthRepository,
    private val unreadTracker: UnreadTracker,
) : ViewModel() {

    private val _uiState = MutableStateFlow<HomeUiState>(HomeUiState.Loading)
    val uiState: StateFlow<HomeUiState> = _uiState.asStateFlow()

    init {
        loadCharacters()
    }

    /**
     * Loads characters from the API and fetches last message previews.
     * On initial load, shows Loading state. On refresh, preserves
     * existing data and sets isRefreshing flag.
     */
    fun loadCharacters() {
        viewModelScope.launch {
            val currentState = _uiState.value
            val userName = authRepository.getUserName()

            // Show loading only on first load; preserve data on refresh
            if (currentState is HomeUiState.Success) {
                _uiState.value = currentState.copy(isRefreshing = true)
            } else {
                _uiState.value = HomeUiState.Loading
            }

            homeRepository.getCharacters()
                .onSuccess { characters ->
                    if (characters.isEmpty()) {
                        _uiState.value = HomeUiState.Empty(userName = userName)
                    } else {
                        // Set characters immediately, then fetch previews
                        _uiState.value = HomeUiState.Success(
                            characters = characters,
                            userName = userName,
                        )

                        // Fetch last messages in parallel
                        val lastMessages = homeRepository.getLastMessages(
                            characterIds = characters.map { it.id },
                        )

                        _uiState.value = HomeUiState.Success(
                            characters = characters,
                            lastMessages = lastMessages,
                            userName = userName,
                        )
                    }
                }
                .onFailure { e ->
                    val emberError = EmberError.from(e)
                    // On refresh failure, keep existing data and show banner
                    if (currentState is HomeUiState.Success) {
                        _uiState.value = currentState.copy(
                            isRefreshing = false,
                            currentError = emberError,
                        )
                    } else {
                        _uiState.value = HomeUiState.Error(emberError.userMessage)
                    }
                }
        }
    }

    /**
     * Dismisses the current transient error banner.
     */
    fun dismissError() {
        val currentState = _uiState.value as? HomeUiState.Success ?: return
        _uiState.value = currentState.copy(currentError = null)
    }

    /**
     * Marks a character as opened, clearing the unread indicator.
     */
    fun markCharacterAsOpened(characterId: String) {
        unreadTracker.markAsOpened(characterId)
    }

    /**
     * Returns whether a character has unread messages.
     */
    fun hasUnreadMessages(character: Character): Boolean {
        return unreadTracker.hasUnread(character)
    }

    companion object {

        /**
         * Returns a time-of-day greeting string.
         *
         * 5-11: "Good morning"
         * 12-16: "Good afternoon"
         * 17-4: "Good evening"
         */
        fun greeting(hour: Int = Calendar.getInstance().get(Calendar.HOUR_OF_DAY)): String {
            return when (hour) {
                in 5..11 -> "Good morning"
                in 12..16 -> "Good afternoon"
                else -> "Good evening"
            }
        }

        /**
         * Returns the Material Icon for a given character template.
         */
        fun templateIcon(template: String): ImageVector {
            return when (template) {
                "companion" -> Icons.Outlined.Person
                "english_teacher" -> Icons.Outlined.AutoStories
                "therapist" -> Icons.Outlined.Favorite
                "fitness_coach" -> Icons.Outlined.FitnessCenter
                "career_coach" -> Icons.Outlined.Work
                "custom" -> Icons.Outlined.AutoAwesome
                else -> Icons.Outlined.Person
            }
        }
    }
}
