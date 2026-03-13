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
    private val voiceRecorder: VoiceRecorder,
    private val audioPlayerManager: AudioPlayerManager,
    private val savedStateHandle: SavedStateHandle,
) : ViewModel() {

    private val characterId: String = checkNotNull(savedStateHandle["characterId"])
    private val characterName: String = checkNotNull(savedStateHandle["characterName"])

    private val _uiState = MutableStateFlow<ChatUiState>(ChatUiState.Loading)
    val uiState: StateFlow<ChatUiState> = _uiState.asStateFlow()

    private val _inputText = MutableStateFlow("")
    val inputText: StateFlow<String> = _inputText.asStateFlow()

    /** Voice recording state — separate from chat UI state. */
    val voiceState: StateFlow<VoiceRecordingState> = voiceRecorder.state

    /** Audio playback state for TTS — separate from chat UI state. */
    val audioPlaybackState: StateFlow<AudioPlaybackState> = audioPlayerManager.playbackState

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

    // -- Voice Recording --

    /**
     * Starts voice recording via [VoiceRecorder].
     *
     * @return true if recording started, false if permission or recorder error.
     */
    fun startRecording(): Boolean {
        return voiceRecorder.start(viewModelScope)
    }

    /**
     * Stops voice recording and triggers the upload + STT transcription pipeline.
     *
     * Flow: stop recording -> get upload URL -> upload file -> transcribe -> set input text.
     */
    fun stopRecording() {
        voiceRecorder.stop()
        val file = voiceRecorder.outputFile ?: run {
            voiceRecorder.updateState(
                VoiceRecordingState.Error("Recording file not found."),
            )
            return
        }

        viewModelScope.launch {
            voiceRecorder.updateState(VoiceRecordingState.Uploading)

            // Step 1: Get presigned upload URL
            val uploadUrlResult = chatRepository.getUploadUrl(file.name)
            val uploadResponse = uploadUrlResult.getOrElse { e ->
                voiceRecorder.updateState(
                    VoiceRecordingState.Error(e.message ?: "Failed to get upload URL."),
                )
                return@launch
            }

            // Step 2: Upload audio file to S3
            val uploadResult = chatRepository.uploadAudioFile(uploadResponse.uploadUrl, file)
            uploadResult.onFailure { e ->
                voiceRecorder.updateState(
                    VoiceRecordingState.Error(e.message ?: "Upload failed."),
                )
                return@launch
            }

            voiceRecorder.updateState(VoiceRecordingState.Transcribing)

            // Step 3: Transcribe audio
            val transcriptResult = chatRepository.transcribeAudio(uploadResponse.fileUrl)
            transcriptResult.onSuccess { transcript ->
                _inputText.value = transcript
                voiceRecorder.reset()
                // Clean up temp file
                file.delete()
            }.onFailure { e ->
                voiceRecorder.updateState(
                    VoiceRecordingState.Error(e.message ?: "Transcription failed."),
                )
            }
        }
    }

    /**
     * Cancels voice recording and discards the audio file.
     */
    fun cancelRecording() {
        voiceRecorder.cancel()
    }

    /**
     * Dismisses a voice recording error and resets to idle.
     */
    fun dismissVoiceError() {
        voiceRecorder.reset()
    }

    // -- TTS Playback --

    /**
     * Requests TTS synthesis for the given message and starts playback.
     *
     * Flow: set loading -> POST /api/v1/tts -> play audio via ExoPlayer.
     * If the message is already playing, toggles pause/resume instead.
     *
     * @param messageId The ID of the AI message to synthesize.
     */
    fun requestTTS(messageId: String) {
        val currentState = audioPlayerManager.playbackState.value

        // If this message is already playing, pause it
        if (currentState is AudioPlaybackState.Playing && currentState.messageId == messageId) {
            audioPlayerManager.pause()
            return
        }

        // If this message is paused, resume it
        if (currentState is AudioPlaybackState.Paused && currentState.messageId == messageId) {
            audioPlayerManager.resume()
            return
        }

        // If already loading this message, ignore
        if (currentState is AudioPlaybackState.Loading && currentState.messageId == messageId) {
            return
        }

        // Find the message content
        val state = _uiState.value as? ChatUiState.Success ?: return
        val message = state.messages.find { it.id == messageId } ?: return
        if (message.content.isEmpty()) return

        audioPlayerManager.setLoading(messageId)

        viewModelScope.launch {
            chatRepository.requestTTS(message.content, characterId)
                .onSuccess { ttsResponse ->
                    audioPlayerManager.play(ttsResponse.audioUrl, messageId)
                }
                .onFailure {
                    audioPlayerManager.stop()
                }
        }
    }

    /**
     * Pauses TTS audio playback.
     */
    fun pauseAudio() {
        audioPlayerManager.pause()
    }

    /**
     * Resumes TTS audio playback.
     */
    fun resumeAudio() {
        audioPlayerManager.resume()
    }

    /**
     * Stops TTS audio playback.
     */
    fun stopAudio() {
        audioPlayerManager.stop()
    }

    /**
     * Cycles the TTS playback speed to the next option.
     *
     * Order: 0.75x -> 1x -> 1.25x -> 1.5x -> 0.75x
     */
    fun cyclePlaybackSpeed() {
        val currentState = audioPlayerManager.playbackState.value
        val currentSpeed = when (currentState) {
            is AudioPlaybackState.Playing -> currentState.speed
            is AudioPlaybackState.Paused -> currentState.speed
            else -> return
        }
        val currentIndex = TTS_SPEED_OPTIONS.indexOf(currentSpeed)
        val nextIndex = if (currentIndex >= 0) {
            (currentIndex + 1) % TTS_SPEED_OPTIONS.size
        } else {
            TTS_SPEED_OPTIONS.indexOf(1.0f)
        }
        audioPlayerManager.setSpeed(TTS_SPEED_OPTIONS[nextIndex])
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
