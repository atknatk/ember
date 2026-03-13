package ai.ember.app.features.chat

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import ai.ember.app.core.error.EmberError
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.launch
import java.util.UUID
import javax.inject.Inject

/**
 * ViewModel for the Chat screen.
 *
 * Manages message history loading with cursor-based pagination,
 * user message sending, and SSE streaming for AI responses.
 *
 * Route arguments:
 * - characterId: the character UUID
 * - characterName: the display name for the top bar
 */
@HiltViewModel
class ChatViewModel @Inject constructor(
    private val chatRepository: ChatRepository,
    private val savedStateHandle: SavedStateHandle,
) : ViewModel() {

    private val characterId: String = checkNotNull(savedStateHandle["characterId"])
    private val characterName: String = checkNotNull(savedStateHandle["characterName"])

    private val _uiState = MutableStateFlow<ChatUiState>(ChatUiState.Loading)
    val uiState: StateFlow<ChatUiState> = _uiState.asStateFlow()

    private val _inputText = MutableStateFlow("")
    val inputText: StateFlow<String> = _inputText.asStateFlow()

    private var streamJob: Job? = null

    init {
        loadHistory()
    }

    /**
     * Updates the current input text from the text field.
     */
    fun onInputChanged(text: String) {
        _inputText.value = text
    }

    /**
     * Loads initial message history from the API.
     *
     * Fetches the most recent 20 messages and reverses them
     * to display oldest-first in the LazyColumn.
     */
    fun loadHistory() {
        viewModelScope.launch {
            _uiState.value = ChatUiState.Loading
            chatRepository.getMessages(characterId, cursor = null, limit = MESSAGES_PER_PAGE)
                .onSuccess { page ->
                    _uiState.value = ChatUiState.Success(
                        messages = page.items.reversed(),
                        hasMoreMessages = page.hasMore,
                        nextCursor = page.nextCursor,
                        characterName = characterName,
                    )
                }
                .onFailure { e ->
                    val emberError = EmberError.from(e)
                    _uiState.value = ChatUiState.Error(emberError.userMessage)
                }
        }
    }

    /**
     * Loads older messages when the user scrolls to the top.
     *
     * Uses cursor-based pagination — never OFFSET/LIMIT.
     * Prepends older messages to the existing list.
     */
    fun loadMoreMessages() {
        val currentState = _uiState.value as? ChatUiState.Success ?: return
        if (currentState.isLoadingMore || !currentState.hasMoreMessages) return
        val cursor = currentState.nextCursor ?: return

        _uiState.value = currentState.copy(isLoadingMore = true)

        viewModelScope.launch {
            chatRepository.getMessages(characterId, cursor = cursor, limit = MESSAGES_PER_PAGE)
                .onSuccess { page ->
                    val state = _uiState.value as? ChatUiState.Success ?: return@launch
                    _uiState.value = state.copy(
                        messages = page.items.reversed() + state.messages,
                        isLoadingMore = false,
                        hasMoreMessages = page.hasMore,
                        nextCursor = page.nextCursor,
                    )
                }
                .onFailure {
                    val state = _uiState.value as? ChatUiState.Success ?: return@launch
                    _uiState.value = state.copy(isLoadingMore = false)
                }
        }
    }

    /**
     * Sends the current input text as a user message and starts SSE streaming.
     *
     * 1. Creates a local user message and appends it immediately.
     * 2. Starts SSE stream, creating an assistant message on first chunk.
     * 3. Appends chunks to the assistant message as they arrive.
     * 4. On "done" event, updates the assistant message ID.
     * 5. On error, sets error message and cleans up empty assistant message.
     */
    fun sendMessage() {
        val content = _inputText.value.trim()
        if (content.isEmpty()) return
        _inputText.value = ""

        val currentState = _uiState.value as? ChatUiState.Success ?: return
        val userMessage = ChatMessage(
            id = UUID.randomUUID().toString(),
            role = MessageRole.USER,
            content = content,
        )

        _uiState.value = currentState.copy(
            messages = currentState.messages + userMessage,
            isStreaming = true,
        )

        streamJob = viewModelScope.launch {
            chatRepository.streamMessage(characterId, content)
                .catch { e ->
                    val state = _uiState.value as? ChatUiState.Success ?: return@catch
                    val emberError = EmberError.from(e)
                    // Remove empty assistant message if present
                    val cleanedMessages = removeEmptyAssistantTail(state.messages)
                    _uiState.value = state.copy(
                        messages = cleanedMessages,
                        isStreaming = false,
                        currentError = emberError,
                    )
                }
                .collect { event ->
                    handleSseEvent(event)
                }

            // Ensure streaming is marked false after flow completes
            val finalState = _uiState.value as? ChatUiState.Success
            if (finalState != null && finalState.isStreaming) {
                _uiState.value = finalState.copy(isStreaming = false)
            }
        }
    }

    /**
     * Dismisses the current transient error banner.
     */
    fun dismissError() {
        val state = _uiState.value as? ChatUiState.Success ?: return
        _uiState.value = state.copy(currentError = null)
    }

    /**
     * Cancels any active SSE stream.
     *
     * Called when the user navigates away from the chat screen.
     */
    fun cancelStream() {
        streamJob?.cancel()
        streamJob = null
        val state = _uiState.value as? ChatUiState.Success ?: return
        if (state.isStreaming) {
            _uiState.value = state.copy(isStreaming = false)
        }
    }

    private fun handleSseEvent(event: SseEvent) {
        val state = _uiState.value as? ChatUiState.Success ?: return

        when (event.type) {
            "chunk" -> {
                val chunk = event.content ?: return
                val messages = state.messages
                val lastMsg = messages.lastOrNull()

                if (lastMsg != null && lastMsg.role == MessageRole.ASSISTANT) {
                    // Append to existing assistant message
                    val updated = messages.dropLast(1) +
                        lastMsg.copy(content = lastMsg.content + chunk)
                    _uiState.value = state.copy(messages = updated)
                } else {
                    // Create new assistant message with first chunk
                    val assistantMessage = ChatMessage(
                        id = UUID.randomUUID().toString(),
                        role = MessageRole.ASSISTANT,
                        content = chunk,
                    )
                    _uiState.value = state.copy(
                        messages = messages + assistantMessage,
                    )
                }
            }

            "done" -> {
                val messageId = event.messageId
                if (messageId != null) {
                    val messages = state.messages
                    val lastMsg = messages.lastOrNull()
                    if (lastMsg != null && lastMsg.role == MessageRole.ASSISTANT) {
                        val updated = messages.dropLast(1) +
                            lastMsg.copy(id = messageId)
                        _uiState.value = state.copy(
                            messages = updated,
                            isStreaming = false,
                        )
                    } else {
                        _uiState.value = state.copy(isStreaming = false)
                    }
                } else {
                    _uiState.value = state.copy(isStreaming = false)
                }
            }

            "error" -> {
                val cleanedMessages = removeEmptyAssistantTail(state.messages)
                _uiState.value = state.copy(
                    messages = cleanedMessages,
                    isStreaming = false,
                )
            }

            "action" -> {
                // Action events (alarm, calendar) are stored in metadata.
                // UI handling deferred to future phases.
            }
        }
    }

    /**
     * Removes a trailing empty assistant message if present.
     * Used during error cleanup to avoid showing an empty bubble.
     */
    private fun removeEmptyAssistantTail(messages: List<ChatMessage>): List<ChatMessage> {
        val lastMsg = messages.lastOrNull()
        return if (lastMsg != null &&
            lastMsg.role == MessageRole.ASSISTANT &&
            lastMsg.content.isEmpty()
        ) {
            messages.dropLast(1)
        } else {
            messages
        }
    }

    companion object {
        const val MESSAGES_PER_PAGE = 20
    }
}
