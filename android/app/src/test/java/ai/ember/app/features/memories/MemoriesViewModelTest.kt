package ai.ember.app.features.memories

import ai.ember.app.core.models.Character
import ai.ember.app.core.models.MemoryItem
import app.cash.turbine.test
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
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
import kotlin.test.assertNull
import kotlin.test.assertTrue

@OptIn(ExperimentalCoroutinesApi::class)
class MemoriesViewModelTest {

    private val testDispatcher = UnconfinedTestDispatcher()
    private lateinit var memoriesRepository: MemoriesRepository

    @Before
    fun setUp() {
        Dispatchers.setMain(testDispatcher)
        memoriesRepository = mockk()
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private fun createViewModel(): MemoriesViewModel {
        return MemoriesViewModel(memoriesRepository)
    }

    // -- Loading and Initial Data --

    @Test
    fun `loadInitialData fetches characters and then global memories`() = runTest {
        val characters = listOf(
            createCharacter("1", "Luna", "companion"),
            createCharacter("2", "Sarah", "english_teacher"),
        )
        val memories = listOf(
            createMemory("m1", "Likes morning workouts"),
            createMemory("m2", "Works as engineer"),
            createMemory("m3", "Prefers short responses"),
        )
        coEvery { memoriesRepository.getCharacters() } returns Result.success(characters)
        coEvery { memoriesRepository.getGlobalMemories() } returns Result.success(memories)

        val viewModel = createViewModel()

        viewModel.uiState.test {
            val state = expectMostRecentItem()
            assertIs<MemoriesUiState.Success>(state)
            assertEquals(2, state.characters.size)
            assertIs<MemorySegment.Global>(state.selectedSegment)
            assertEquals(3, state.memories.size)
            assertEquals(false, state.isLoadingMemories)
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `loadInitialData sets Error when character fetch fails`() = runTest {
        coEvery { memoriesRepository.getCharacters() } returns
            Result.failure(MemoriesException("Connection failed. Please check your internet."))

        val viewModel = createViewModel()

        viewModel.uiState.test {
            val state = expectMostRecentItem()
            assertIs<MemoriesUiState.Error>(state)
            assertTrue(state.message.isNotEmpty())
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `loadInitialData shows empty memories when global has none`() = runTest {
        coEvery { memoriesRepository.getCharacters() } returns
            Result.success(listOf(createCharacter("1", "Luna", "companion")))
        coEvery { memoriesRepository.getGlobalMemories() } returns Result.success(emptyList())

        val viewModel = createViewModel()

        viewModel.uiState.test {
            val state = expectMostRecentItem()
            assertIs<MemoriesUiState.Success>(state)
            assertTrue(state.memories.isEmpty())
            cancelAndIgnoreRemainingEvents()
        }
    }

    // -- Segment Switching --

    @Test
    fun `selectSegment changes segment and loads character memories`() = runTest {
        val characters = listOf(createCharacter("char-1", "Luna", "companion"))
        val globalMemories = listOf(createMemory("m1", "Global fact"))
        val charMemories = listOf(
            createMemory("m2", "Character specific fact"),
            createMemory("m3", "Another fact"),
        )

        coEvery { memoriesRepository.getCharacters() } returns Result.success(characters)
        coEvery { memoriesRepository.getGlobalMemories() } returns Result.success(globalMemories)
        coEvery { memoriesRepository.getCharacterMemories("char-1") } returns Result.success(charMemories)

        val viewModel = createViewModel()

        // Verify initial state is global
        viewModel.uiState.test {
            val initialState = expectMostRecentItem()
            assertIs<MemoriesUiState.Success>(initialState)
            assertIs<MemorySegment.Global>(initialState.selectedSegment)
            assertEquals(1, initialState.memories.size)
            cancelAndIgnoreRemainingEvents()
        }

        // Switch to character segment
        val charSegment = MemorySegment.CharacterSegment(id = "char-1", name = "Luna")
        viewModel.selectSegment(charSegment)

        viewModel.uiState.test {
            val state = expectMostRecentItem()
            assertIs<MemoriesUiState.Success>(state)
            assertEquals(charSegment, state.selectedSegment)
            assertEquals(2, state.memories.size)
            assertEquals("Character specific fact", state.memories[0].memory)
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `selectSegment with same segment is a no-op`() = runTest {
        coEvery { memoriesRepository.getCharacters() } returns
            Result.success(listOf(createCharacter("1", "Luna", "companion")))
        coEvery { memoriesRepository.getGlobalMemories() } returns
            Result.success(listOf(createMemory("m1", "Fact")))

        val viewModel = createViewModel()

        // Wait for initial load
        viewModel.uiState.test {
            expectMostRecentItem()
            cancelAndIgnoreRemainingEvents()
        }

        // Select same segment - should not trigger another API call
        viewModel.selectSegment(MemorySegment.Global)

        coVerify(exactly = 1) { memoriesRepository.getGlobalMemories() }
    }

    // -- Memory Deletion --

    @Test
    fun `deleteMemory removes memory from list on success for global`() = runTest {
        val memories = listOf(
            createMemory("m1", "First"),
            createMemory("m2", "Second"),
            createMemory("m3", "Third"),
        )
        coEvery { memoriesRepository.getCharacters() } returns Result.success(emptyList())
        coEvery { memoriesRepository.getGlobalMemories() } returns Result.success(memories)
        coEvery { memoriesRepository.deleteGlobalMemory("m2") } returns Result.success(Unit)

        val viewModel = createViewModel()

        viewModel.uiState.test {
            val initial = expectMostRecentItem()
            assertIs<MemoriesUiState.Success>(initial)
            assertEquals(3, initial.memories.size)
            cancelAndIgnoreRemainingEvents()
        }

        viewModel.deleteMemory(createMemory("m2", "Second"))

        viewModel.uiState.test {
            val state = expectMostRecentItem()
            assertIs<MemoriesUiState.Success>(state)
            assertEquals(2, state.memories.size)
            assertTrue(state.memories.none { it.id == "m2" })
            assertNull(state.isDeletingMemoryId)
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `deleteMemory calls correct API for character segment`() = runTest {
        val charSegment = MemorySegment.CharacterSegment(id = "char-1", name = "Luna")
        val memories = listOf(createMemory("m1", "Character fact"))

        coEvery { memoriesRepository.getCharacters() } returns
            Result.success(listOf(createCharacter("char-1", "Luna", "companion")))
        coEvery { memoriesRepository.getGlobalMemories() } returns Result.success(emptyList())
        coEvery { memoriesRepository.getCharacterMemories("char-1") } returns Result.success(memories)
        coEvery { memoriesRepository.deleteCharacterMemory("char-1", "m1") } returns Result.success(Unit)

        val viewModel = createViewModel()
        viewModel.selectSegment(charSegment)

        viewModel.deleteMemory(createMemory("m1", "Character fact"))

        coVerify { memoriesRepository.deleteCharacterMemory("char-1", "m1") }
    }

    @Test
    fun `deleteMemory keeps memory on failure`() = runTest {
        val memories = listOf(
            createMemory("m1", "First"),
            createMemory("m2", "Second"),
        )
        coEvery { memoriesRepository.getCharacters() } returns Result.success(emptyList())
        coEvery { memoriesRepository.getGlobalMemories() } returns Result.success(memories)
        coEvery { memoriesRepository.deleteGlobalMemory("m1") } returns
            Result.failure(MemoriesException("Network error"))

        val viewModel = createViewModel()

        viewModel.uiState.test {
            expectMostRecentItem()
            cancelAndIgnoreRemainingEvents()
        }

        viewModel.deleteMemory(createMemory("m1", "First"))

        viewModel.uiState.test {
            val state = expectMostRecentItem()
            assertIs<MemoriesUiState.Success>(state)
            assertEquals(2, state.memories.size)
            assertNull(state.isDeletingMemoryId)
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `deleteMemory clears isDeletingMemoryId after completion`() = runTest {
        coEvery { memoriesRepository.getCharacters() } returns Result.success(emptyList())
        coEvery { memoriesRepository.getGlobalMemories() } returns
            Result.success(listOf(createMemory("m1", "Fact")))
        coEvery { memoriesRepository.deleteGlobalMemory("m1") } returns Result.success(Unit)

        val viewModel = createViewModel()
        viewModel.deleteMemory(createMemory("m1", "Fact"))

        viewModel.uiState.test {
            val state = expectMostRecentItem()
            assertIs<MemoriesUiState.Success>(state)
            assertNull(state.isDeletingMemoryId)
            cancelAndIgnoreRemainingEvents()
        }
    }

    // -- Retry --

    @Test
    fun `retryLoadMemories reloads from Error state`() = runTest {
        coEvery { memoriesRepository.getCharacters() } returns
            Result.failure(MemoriesException("Network error"))

        val viewModel = createViewModel()

        viewModel.uiState.test {
            val state = expectMostRecentItem()
            assertIs<MemoriesUiState.Error>(state)
            cancelAndIgnoreRemainingEvents()
        }

        // Now fix the mock and retry
        coEvery { memoriesRepository.getCharacters() } returns
            Result.success(listOf(createCharacter("1", "Luna", "companion")))
        coEvery { memoriesRepository.getGlobalMemories() } returns Result.success(emptyList())

        viewModel.retryLoadMemories()

        viewModel.uiState.test {
            val state = expectMostRecentItem()
            assertIs<MemoriesUiState.Success>(state)
            cancelAndIgnoreRemainingEvents()
        }
    }

    // -- Helpers --

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

    private fun createMemory(
        id: String,
        memory: String,
        createdAt: String? = "2026-02-20T10:00:00Z",
    ) = MemoryItem(
        id = id,
        memory = memory,
        createdAt = createdAt,
    )
}
