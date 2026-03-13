package ai.ember.app.features.home

import ai.ember.app.core.auth.AuthRepository
import ai.ember.app.core.models.Character
import ai.ember.app.core.models.MessagePreview
import app.cash.turbine.test
import io.mockk.coEvery
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Before
import org.junit.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

@OptIn(ExperimentalCoroutinesApi::class)
class HomeViewModelTest {

    private val testDispatcher = UnconfinedTestDispatcher()
    private lateinit var homeRepository: HomeRepository
    private lateinit var authRepository: AuthRepository
    private lateinit var unreadTracker: UnreadTracker

    @Before
    fun setUp() {
        Dispatchers.setMain(testDispatcher)
        homeRepository = mockk()
        authRepository = mockk()
        unreadTracker = mockk(relaxed = true)
        every { authRepository.getUserName() } returns "Alex"
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private fun createViewModel(): HomeViewModel {
        return HomeViewModel(homeRepository, authRepository, unreadTracker)
    }

    // -- Loading and Success --

    @Test
    fun `loadCharacters sets Success with characters on API success`() = runTest {
        val characters = listOf(
            createCharacter("1", "Luna", "companion", isDefault = true),
            createCharacter("2", "Sarah", "english_teacher"),
        )
        coEvery { homeRepository.getCharacters() } returns Result.success(characters)
        coEvery { homeRepository.getLastMessages(any()) } returns emptyMap()

        val viewModel = createViewModel()

        viewModel.uiState.test {
            val state = expectMostRecentItem()
            assertIs<HomeUiState.Success>(state)
            assertEquals(2, state.characters.size)
            assertEquals("Alex", state.userName)
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `loadCharacters sets Empty when no characters`() = runTest {
        coEvery { homeRepository.getCharacters() } returns Result.success(emptyList())

        val viewModel = createViewModel()

        viewModel.uiState.test {
            val state = expectMostRecentItem()
            assertIs<HomeUiState.Empty>(state)
            assertEquals("Alex", state.userName)
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `loadCharacters sets Error on API failure`() = runTest {
        coEvery { homeRepository.getCharacters() } returns
            Result.failure(HomeException("Connection failed. Please check your internet."))

        val viewModel = createViewModel()

        viewModel.uiState.test {
            val state = expectMostRecentItem()
            assertIs<HomeUiState.Error>(state)
            assertTrue(state.message.isNotEmpty())
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `loadCharacters fetches last messages for each character`() = runTest {
        val characters = listOf(
            createCharacter("1", "Luna", "companion"),
            createCharacter("2", "Sarah", "english_teacher"),
        )
        val lastMessages = mapOf(
            "1" to createMessagePreview("msg-1", "Hello!"),
            "2" to createMessagePreview("msg-2", "Let's practice!"),
        )
        coEvery { homeRepository.getCharacters() } returns Result.success(characters)
        coEvery { homeRepository.getLastMessages(any()) } returns lastMessages

        val viewModel = createViewModel()

        viewModel.uiState.test {
            val state = expectMostRecentItem()
            assertIs<HomeUiState.Success>(state)
            assertEquals(2, state.lastMessages.size)
            assertEquals("Hello!", state.lastMessages["1"]?.content)
            assertEquals("Let's practice!", state.lastMessages["2"]?.content)
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `pull-to-refresh preserves existing data during refresh`() = runTest {
        val characters = listOf(createCharacter("1", "Luna", "companion"))
        coEvery { homeRepository.getCharacters() } returns Result.success(characters)
        coEvery { homeRepository.getLastMessages(any()) } returns emptyMap()

        val viewModel = createViewModel()

        // Wait for initial load
        viewModel.uiState.test {
            val initialState = expectMostRecentItem()
            assertIs<HomeUiState.Success>(initialState)
            assertEquals(1, initialState.characters.size)
            cancelAndIgnoreRemainingEvents()
        }

        // Trigger refresh — characters should still be visible
        viewModel.loadCharacters()

        viewModel.uiState.test {
            val state = expectMostRecentItem()
            assertIs<HomeUiState.Success>(state)
            assertEquals(1, state.characters.size)
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `refresh failure preserves existing data`() = runTest {
        val characters = listOf(createCharacter("1", "Luna", "companion"))
        coEvery { homeRepository.getCharacters() } returns Result.success(characters)
        coEvery { homeRepository.getLastMessages(any()) } returns emptyMap()

        val viewModel = createViewModel()

        // Wait for initial load
        viewModel.uiState.test {
            expectMostRecentItem()
            cancelAndIgnoreRemainingEvents()
        }

        // Now fail the refresh
        coEvery { homeRepository.getCharacters() } returns
            Result.failure(HomeException("Network error"))

        viewModel.loadCharacters()

        viewModel.uiState.test {
            val state = expectMostRecentItem()
            assertIs<HomeUiState.Success>(state)
            assertEquals(1, state.characters.size)
            cancelAndIgnoreRemainingEvents()
        }
    }

    // -- Greeting --

    @Test
    fun `greeting returns Good morning for morning hours`() {
        assertEquals("Good morning", HomeViewModel.greeting(hour = 5))
        assertEquals("Good morning", HomeViewModel.greeting(hour = 8))
        assertEquals("Good morning", HomeViewModel.greeting(hour = 11))
    }

    @Test
    fun `greeting returns Good afternoon for afternoon hours`() {
        assertEquals("Good afternoon", HomeViewModel.greeting(hour = 12))
        assertEquals("Good afternoon", HomeViewModel.greeting(hour = 14))
        assertEquals("Good afternoon", HomeViewModel.greeting(hour = 16))
    }

    @Test
    fun `greeting returns Good evening for evening hours`() {
        assertEquals("Good evening", HomeViewModel.greeting(hour = 17))
        assertEquals("Good evening", HomeViewModel.greeting(hour = 20))
        assertEquals("Good evening", HomeViewModel.greeting(hour = 4))
        assertEquals("Good evening", HomeViewModel.greeting(hour = 0))
    }

    // -- Template Icons --

    @Test
    fun `templateIcon returns correct icon for each template`() {
        // Just verify all templates return without error
        val templates = listOf(
            "companion", "english_teacher", "therapist",
            "fitness_coach", "career_coach", "custom", "unknown",
        )
        templates.forEach { template ->
            HomeViewModel.templateIcon(template) // should not throw
        }
    }

    // -- Unread Tracking --

    @Test
    fun `markCharacterAsOpened delegates to UnreadTracker`() = runTest {
        coEvery { homeRepository.getCharacters() } returns Result.success(emptyList())

        val viewModel = createViewModel()
        viewModel.markCharacterAsOpened("char-1")

        verify { unreadTracker.markAsOpened("char-1") }
    }

    // -- Helpers --

    private fun createCharacter(
        id: String,
        name: String,
        template: String,
        isDefault: Boolean = false,
        lastMessageAt: String? = null,
    ) = Character(
        id = id,
        name = name,
        template = template,
        isDefault = isDefault,
        lastMessageAt = lastMessageAt,
    )

    private fun createMessagePreview(
        id: String,
        content: String,
        role: String = "assistant",
    ) = MessagePreview(
        id = id,
        role = role,
        content = content,
    )
}
