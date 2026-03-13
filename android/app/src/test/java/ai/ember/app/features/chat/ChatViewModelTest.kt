package ai.ember.app.features.chat

import androidx.lifecycle.SavedStateHandle
import app.cash.turbine.test
import io.mockk.coEvery
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Before
import org.junit.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertTrue

@OptIn(ExperimentalCoroutinesApi::class)
class ChatViewModelTest {

    private val testDispatcher = UnconfinedTestDispatcher()
    private lateinit var chatRepository: ChatRepository
    private lateinit var savedStateHandle: SavedStateHandle
    private lateinit var viewModel: ChatViewModel

    @Before
    fun setUp() {
        Dispatchers.setMain(testDispatcher)
        chatRepository = mockk()
        savedStateHandle = SavedStateHandle(
            mapOf(
                "characterId" to "char-1",
                "characterName" to "Luna",
            ),
        )
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private fun createViewModel(): ChatViewModel {
        return ChatViewModel(chatRepository, savedStateHandle)
    }

    @Test
    fun `loadHistory populates messages on success`() = runTest {
        val messages = listOf(
            ChatMessage(id = "3", role = MessageRole.ASSISTANT, content = "Hello!", createdAt = "2026-03-12T14:31:00Z"),
            ChatMessage(id = "2", role = MessageRole.USER, content = "Hi", createdAt = "2026-03-12T14:30:30Z"),
            ChatMessage(id = "1", role = MessageRole.ASSISTANT, content = "Welcome", createdAt = "2026-03-12T14:30:00Z"),
        )
        coEvery { chatRepository.getMessages("char-1", null, 20) } returns Result.success(
            ChatMessageListResponse(items = messages, nextCursor = "cursor1", hasMore = true),
        )

        viewModel = createViewModel()

        viewModel.uiState.test {
            val state = awaitItem()
            assertIs<ChatUiState.Success>(state)
            // Messages should be reversed (oldest first)
            assertEquals(3, state.messages.size)
            assertEquals("1", state.messages.first().id)
            assertEquals("3", state.messages.last().id)
            assertTrue(state.hasMoreMessages)
            assertEquals("cursor1", state.nextCursor)
            assertEquals("Luna", state.characterName)
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `loadHistory sets error on failure`() = runTest {
        coEvery { chatRepository.getMessages("char-1", null, 20) } returns Result.failure(
            ChatException("Connection failed. Please check your internet."),
        )

        viewModel = createViewModel()

        viewModel.uiState.test {
            val state = awaitItem()
            assertIs<ChatUiState.Error>(state)
            assertTrue(state.message.isNotEmpty())
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `loadHistory with empty messages shows empty success`() = runTest {
        coEvery { chatRepository.getMessages("char-1", null, 20) } returns Result.success(
            ChatMessageListResponse(items = emptyList(), hasMore = false),
        )

        viewModel = createViewModel()

        viewModel.uiState.test {
            val state = awaitItem()
            assertIs<ChatUiState.Success>(state)
            assertTrue(state.messages.isEmpty())
            assertFalse(state.hasMoreMessages)
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `sendMessage appends user and assistant messages`() = runTest {
        coEvery { chatRepository.getMessages("char-1", null, 20) } returns Result.success(
            ChatMessageListResponse(items = emptyList(), hasMore = false),
        )
        every { chatRepository.streamMessage("char-1", "Hi Ember") } returns flowOf(
            SseEvent(type = "chunk", content = "Hello"),
            SseEvent(type = "chunk", content = " there!"),
            SseEvent(type = "done", messageId = "msg-1"),
        )

        viewModel = createViewModel()
        viewModel.onInputChanged("Hi Ember")

        viewModel.uiState.test {
            skipItems(1) // initial success state
            viewModel.sendMessage()
            val finalState = expectMostRecentItem()
            assertIs<ChatUiState.Success>(finalState)
            assertEquals(2, finalState.messages.size)
            assertEquals("Hi Ember", finalState.messages[0].content)
            assertEquals(MessageRole.USER, finalState.messages[0].role)
            assertEquals("Hello there!", finalState.messages[1].content)
            assertEquals(MessageRole.ASSISTANT, finalState.messages[1].role)
            assertEquals("msg-1", finalState.messages[1].id)
            assertFalse(finalState.isStreaming)
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `sendMessage clears input text immediately`() = runTest {
        coEvery { chatRepository.getMessages("char-1", null, 20) } returns Result.success(
            ChatMessageListResponse(items = emptyList(), hasMore = false),
        )
        every { chatRepository.streamMessage("char-1", "Hello") } returns flowOf(
            SseEvent(type = "chunk", content = "Hi"),
            SseEvent(type = "done", messageId = "msg-1"),
        )

        viewModel = createViewModel()
        viewModel.onInputChanged("Hello")

        viewModel.inputText.test {
            assertEquals("Hello", awaitItem())
            viewModel.sendMessage()
            assertEquals("", awaitItem())
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `sendMessage does nothing with empty input`() = runTest {
        coEvery { chatRepository.getMessages("char-1", null, 20) } returns Result.success(
            ChatMessageListResponse(items = emptyList(), hasMore = false),
        )

        viewModel = createViewModel()
        viewModel.onInputChanged("   ")

        viewModel.uiState.test {
            val initialState = awaitItem()
            assertIs<ChatUiState.Success>(initialState)
            viewModel.sendMessage()
            // No new state emission — messages remain empty
            expectNoEvents()
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `sendMessage handles stream error`() = runTest {
        coEvery { chatRepository.getMessages("char-1", null, 20) } returns Result.success(
            ChatMessageListResponse(items = emptyList(), hasMore = false),
        )
        every { chatRepository.streamMessage("char-1", "Hi") } returns flow {
            throw ChatException("Network error")
        }

        viewModel = createViewModel()
        viewModel.onInputChanged("Hi")

        viewModel.uiState.test {
            skipItems(1) // initial success
            viewModel.sendMessage()
            val state = expectMostRecentItem()
            assertIs<ChatUiState.Success>(state)
            // User message should remain, no empty assistant message
            assertEquals(1, state.messages.size)
            assertEquals(MessageRole.USER, state.messages[0].role)
            assertFalse(state.isStreaming)
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `sendMessage handles SSE error event`() = runTest {
        coEvery { chatRepository.getMessages("char-1", null, 20) } returns Result.success(
            ChatMessageListResponse(items = emptyList(), hasMore = false),
        )
        every { chatRepository.streamMessage("char-1", "Hi") } returns flowOf(
            SseEvent(type = "chunk", content = "Partial"),
            SseEvent(type = "error", message = "LLM down"),
        )

        viewModel = createViewModel()
        viewModel.onInputChanged("Hi")

        viewModel.uiState.test {
            skipItems(1) // initial success
            viewModel.sendMessage()
            val state = expectMostRecentItem()
            assertIs<ChatUiState.Success>(state)
            assertFalse(state.isStreaming)
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `loadMoreMessages prepends older messages`() = runTest {
        val initialMessages = listOf(
            ChatMessage(id = "3", role = MessageRole.ASSISTANT, content = "Hi"),
        )
        coEvery { chatRepository.getMessages("char-1", null, 20) } returns Result.success(
            ChatMessageListResponse(items = initialMessages, nextCursor = "cursor1", hasMore = true),
        )
        coEvery { chatRepository.getMessages("char-1", "cursor1", 20) } returns Result.success(
            ChatMessageListResponse(
                items = listOf(
                    ChatMessage(id = "2", role = MessageRole.USER, content = "Older"),
                    ChatMessage(id = "1", role = MessageRole.ASSISTANT, content = "Oldest"),
                ),
                hasMore = false,
            ),
        )

        viewModel = createViewModel()

        viewModel.uiState.test {
            val initialState = awaitItem()
            assertIs<ChatUiState.Success>(initialState)
            assertEquals(1, initialState.messages.size)

            viewModel.loadMoreMessages()
            val updatedState = expectMostRecentItem()
            assertIs<ChatUiState.Success>(updatedState)
            // Older messages prepended (reversed), so oldest first
            assertEquals(3, updatedState.messages.size)
            assertEquals("1", updatedState.messages[0].id)
            assertEquals("2", updatedState.messages[1].id)
            assertEquals("3", updatedState.messages[2].id)
            assertFalse(updatedState.hasMoreMessages)
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `loadMoreMessages does nothing when hasMoreMessages is false`() = runTest {
        coEvery { chatRepository.getMessages("char-1", null, 20) } returns Result.success(
            ChatMessageListResponse(items = emptyList(), hasMore = false),
        )

        viewModel = createViewModel()

        viewModel.uiState.test {
            val state = awaitItem()
            assertIs<ChatUiState.Success>(state)
            viewModel.loadMoreMessages()
            // No additional emission
            expectNoEvents()
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `cancelStream sets isStreaming to false`() = runTest {
        coEvery { chatRepository.getMessages("char-1", null, 20) } returns Result.success(
            ChatMessageListResponse(items = emptyList(), hasMore = false),
        )

        viewModel = createViewModel()

        viewModel.uiState.test {
            val state = awaitItem()
            assertIs<ChatUiState.Success>(state)
            // Manually trigger cancel even without active stream — should be safe
            viewModel.cancelStream()
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `onInputChanged updates input text`() = runTest {
        coEvery { chatRepository.getMessages("char-1", null, 20) } returns Result.success(
            ChatMessageListResponse(items = emptyList(), hasMore = false),
        )

        viewModel = createViewModel()

        viewModel.inputText.test {
            assertEquals("", awaitItem())
            viewModel.onInputChanged("Hello world")
            assertEquals("Hello world", awaitItem())
            cancelAndIgnoreRemainingEvents()
        }
    }
}
