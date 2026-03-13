package ai.ember.app.features.profile

import ai.ember.app.core.auth.AuthRepository
import ai.ember.app.core.models.Character
import app.cash.turbine.test
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlinx.serialization.json.Json
import org.junit.After
import org.junit.Before
import org.junit.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

@OptIn(ExperimentalCoroutinesApi::class)
class ProfileViewModelTest {

    private val testDispatcher = UnconfinedTestDispatcher()
    private lateinit var profileRepository: ProfileRepository
    private lateinit var authRepository: AuthRepository
    private lateinit var json: Json

    @Before
    fun setUp() {
        Dispatchers.setMain(testDispatcher)
        profileRepository = mockk()
        authRepository = mockk(relaxed = true)
        json = Json { ignoreUnknownKeys = true }
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private fun createViewModel(): ProfileViewModel {
        return ProfileViewModel(profileRepository, authRepository, json)
    }

    // -- Loading --

    @Test
    fun `loadProfile fetches profile and characters in parallel`() = runTest {
        val profile = createProfile()
        val characters = listOf(
            createCharacter("1", "Luna", "companion"),
            createCharacter("2", "Sarah", "english_teacher"),
        )
        coEvery { profileRepository.getProfile() } returns Result.success(profile)
        coEvery { profileRepository.getCharacters() } returns Result.success(characters)

        val viewModel = createViewModel()

        viewModel.uiState.test {
            val state = expectMostRecentItem()
            assertIs<ProfileUiState.Success>(state)
            assertEquals("Alex", state.profile.name)
            assertEquals("user@example.com", state.profile.email)
            assertEquals(2, state.characters.size)
            assertEquals("Alex", state.editedName)
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `loadProfile sets Error when profile fetch fails`() = runTest {
        coEvery { profileRepository.getProfile() } returns
            Result.failure(ProfileException("Connection failed. Please check your internet."))
        coEvery { profileRepository.getCharacters() } returns Result.success(emptyList())

        val viewModel = createViewModel()

        viewModel.uiState.test {
            val state = expectMostRecentItem()
            assertIs<ProfileUiState.Error>(state)
            assertTrue(state.message.isNotEmpty())
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `loadProfile succeeds even if characters fetch fails`() = runTest {
        val profile = createProfile()
        coEvery { profileRepository.getProfile() } returns Result.success(profile)
        coEvery { profileRepository.getCharacters() } returns
            Result.failure(ProfileException("Characters failed"))

        val viewModel = createViewModel()

        viewModel.uiState.test {
            val state = expectMostRecentItem()
            assertIs<ProfileUiState.Success>(state)
            assertEquals("Alex", state.profile.name)
            assertTrue(state.characters.isEmpty())
            cancelAndIgnoreRemainingEvents()
        }
    }

    // -- Name Editing --

    @Test
    fun `saveName trims whitespace and sends update`() = runTest {
        val profile = createProfile()
        val updatedProfile = profile.copy(name = "Alex Updated")
        coEvery { profileRepository.getProfile() } returns Result.success(profile)
        coEvery { profileRepository.getCharacters() } returns Result.success(emptyList())
        coEvery { profileRepository.updateProfile(any()) } returns Result.success(updatedProfile)

        val viewModel = createViewModel()
        viewModel.startEditingName()
        viewModel.onNameChanged("  Alex Updated  ")
        viewModel.saveName()

        viewModel.uiState.test {
            val state = expectMostRecentItem()
            assertIs<ProfileUiState.Success>(state)
            assertEquals("Alex Updated", state.profile.name)
            assertFalse(state.isEditingName)
            cancelAndIgnoreRemainingEvents()
        }

        coVerify {
            profileRepository.updateProfile(
                ProfileUpdateRequest(name = "Alex Updated"),
            )
        }
    }

    @Test
    fun `saveName rejects empty string`() = runTest {
        val profile = createProfile()
        coEvery { profileRepository.getProfile() } returns Result.success(profile)
        coEvery { profileRepository.getCharacters() } returns Result.success(emptyList())

        val viewModel = createViewModel()
        viewModel.startEditingName()
        viewModel.onNameChanged("   ")
        viewModel.saveName()

        viewModel.uiState.test {
            val state = expectMostRecentItem()
            assertIs<ProfileUiState.Success>(state)
            assertEquals("Name cannot be empty", state.snackbarMessage)
            cancelAndIgnoreRemainingEvents()
        }

        coVerify(exactly = 0) { profileRepository.updateProfile(any()) }
    }

    @Test
    fun `cancelEditingName restores original name`() = runTest {
        val profile = createProfile()
        coEvery { profileRepository.getProfile() } returns Result.success(profile)
        coEvery { profileRepository.getCharacters() } returns Result.success(emptyList())

        val viewModel = createViewModel()
        viewModel.startEditingName()
        viewModel.onNameChanged("New Name")
        viewModel.cancelEditingName()

        viewModel.uiState.test {
            val state = expectMostRecentItem()
            assertIs<ProfileUiState.Success>(state)
            assertFalse(state.isEditingName)
            assertEquals("Alex", state.editedName)
            cancelAndIgnoreRemainingEvents()
        }
    }

    // -- Timezone --

    @Test
    fun `updateTimezone sends PUT and updates state`() = runTest {
        val profile = createProfile()
        val updatedProfile = profile.copy(timezone = "Europe/Istanbul")
        coEvery { profileRepository.getProfile() } returns Result.success(profile)
        coEvery { profileRepository.getCharacters() } returns Result.success(emptyList())
        coEvery { profileRepository.updateProfile(any()) } returns Result.success(updatedProfile)

        val viewModel = createViewModel()
        viewModel.updateTimezone("Europe/Istanbul")

        viewModel.uiState.test {
            val state = expectMostRecentItem()
            assertIs<ProfileUiState.Success>(state)
            assertEquals("Europe/Istanbul", state.profile.timezone)
            assertFalse(state.showTimezonePicker)
            cancelAndIgnoreRemainingEvents()
        }

        coVerify {
            profileRepository.updateProfile(
                ProfileUpdateRequest(timezone = "Europe/Istanbul"),
            )
        }
    }

    // -- Language --

    @Test
    fun `updateLanguage sends PUT and updates state`() = runTest {
        val profile = createProfile()
        val updatedProfile = profile.copy(preferredLanguage = "tr")
        coEvery { profileRepository.getProfile() } returns Result.success(profile)
        coEvery { profileRepository.getCharacters() } returns Result.success(emptyList())
        coEvery { profileRepository.updateProfile(any()) } returns Result.success(updatedProfile)

        val viewModel = createViewModel()
        viewModel.updateLanguage("tr")

        viewModel.uiState.test {
            val state = expectMostRecentItem()
            assertIs<ProfileUiState.Success>(state)
            assertEquals("tr", state.profile.preferredLanguage)
            cancelAndIgnoreRemainingEvents()
        }

        coVerify {
            profileRepository.updateProfile(
                ProfileUpdateRequest(preferredLanguage = "tr"),
            )
        }
    }

    // -- Delete Account --

    @Test
    fun `deleteAccount with correct confirmation succeeds and signs out`() = runTest {
        val profile = createProfile()
        coEvery { profileRepository.getProfile() } returns Result.success(profile)
        coEvery { profileRepository.getCharacters() } returns Result.success(emptyList())
        coEvery { profileRepository.deleteAccount(any()) } returns Result.success(Unit)

        val viewModel = createViewModel()
        viewModel.showDeleteConfirmation()
        viewModel.onDeleteConfirmationTextChanged("DELETE MY ACCOUNT")
        viewModel.deleteAccount()

        viewModel.shouldSignOut.test {
            val value = expectMostRecentItem()
            assertTrue(value)
            cancelAndIgnoreRemainingEvents()
        }

        verify { authRepository.signOut() }
        coVerify { profileRepository.deleteAccount("DELETE MY ACCOUNT") }
    }

    @Test
    fun `deleteAccount with wrong confirmation does not call API`() = runTest {
        val profile = createProfile()
        coEvery { profileRepository.getProfile() } returns Result.success(profile)
        coEvery { profileRepository.getCharacters() } returns Result.success(emptyList())

        val viewModel = createViewModel()
        viewModel.showDeleteConfirmation()
        viewModel.onDeleteConfirmationTextChanged("delete my account")
        viewModel.deleteAccount()

        viewModel.uiState.test {
            val state = expectMostRecentItem()
            assertIs<ProfileUiState.Success>(state)
            assertEquals(
                "Please type DELETE MY ACCOUNT to confirm",
                state.snackbarMessage,
            )
            cancelAndIgnoreRemainingEvents()
        }

        coVerify(exactly = 0) { profileRepository.deleteAccount(any()) }
    }

    @Test
    fun `deleteAccount on server error sets snackbar message`() = runTest {
        val profile = createProfile()
        coEvery { profileRepository.getProfile() } returns Result.success(profile)
        coEvery { profileRepository.getCharacters() } returns Result.success(emptyList())
        coEvery { profileRepository.deleteAccount(any()) } returns
            Result.failure(ProfileException("Service unavailable. Please try again later."))

        val viewModel = createViewModel()
        viewModel.showDeleteConfirmation()
        viewModel.onDeleteConfirmationTextChanged("DELETE MY ACCOUNT")
        viewModel.deleteAccount()

        viewModel.uiState.test {
            val state = expectMostRecentItem()
            assertIs<ProfileUiState.Success>(state)
            assertFalse(state.showDeleteConfirmation)
            assertTrue(state.snackbarMessage?.isNotEmpty() == true)
            cancelAndIgnoreRemainingEvents()
        }
    }

    // -- Sign Out --

    @Test
    fun `signOut sets shouldSignOut flag`() = runTest {
        val profile = createProfile()
        coEvery { profileRepository.getProfile() } returns Result.success(profile)
        coEvery { profileRepository.getCharacters() } returns Result.success(emptyList())

        val viewModel = createViewModel()
        viewModel.signOut()

        viewModel.shouldSignOut.test {
            val value = expectMostRecentItem()
            assertTrue(value)
            cancelAndIgnoreRemainingEvents()
        }
    }

    // -- Notification Preferences --

    @Test
    fun `updateNotificationPreference updates local state`() = runTest {
        val profile = createProfile()
        coEvery { profileRepository.getProfile() } returns Result.success(profile)
        coEvery { profileRepository.getCharacters() } returns Result.success(emptyList())

        val viewModel = createViewModel()
        viewModel.updateNotificationPreference("morning_checkin", false)

        viewModel.uiState.test {
            val state = expectMostRecentItem()
            assertIs<ProfileUiState.Success>(state)
            assertEquals(false, state.notificationPreferences["morning_checkin"])
            cancelAndIgnoreRemainingEvents()
        }
    }

    // -- Snackbar --

    @Test
    fun `clearSnackbar clears snackbar message`() = runTest {
        val profile = createProfile()
        coEvery { profileRepository.getProfile() } returns Result.success(profile)
        coEvery { profileRepository.getCharacters() } returns Result.success(emptyList())

        val viewModel = createViewModel()

        // Trigger a snackbar via empty name save
        viewModel.startEditingName()
        viewModel.onNameChanged("   ")
        viewModel.saveName()

        viewModel.uiState.test {
            val state = expectMostRecentItem()
            assertIs<ProfileUiState.Success>(state)
            assertTrue(state.snackbarMessage != null)
            cancelAndIgnoreRemainingEvents()
        }

        viewModel.clearSnackbar()

        viewModel.uiState.test {
            val state = expectMostRecentItem()
            assertIs<ProfileUiState.Success>(state)
            assertNull(state.snackbarMessage)
            cancelAndIgnoreRemainingEvents()
        }
    }

    // -- Helpers --

    private fun createProfile(
        name: String = "Alex",
        email: String = "user@example.com",
        timezone: String = "America/New_York",
        preferredLanguage: String = "en",
        avatarUrl: String? = null,
        subscriptionTier: String = "free",
    ) = ProfileData(
        id = "uuid-1",
        email = email,
        name = name,
        timezone = timezone,
        avatarUrl = avatarUrl,
        preferredLanguage = preferredLanguage,
        subscriptionTier = subscriptionTier,
        createdAt = "2026-02-23T10:00:00Z",
    )

    private fun createCharacter(
        id: String,
        name: String,
        template: String,
        isDefault: Boolean = false,
    ) = Character(
        id = id,
        name = name,
        template = template,
        isDefault = isDefault,
    )
}
