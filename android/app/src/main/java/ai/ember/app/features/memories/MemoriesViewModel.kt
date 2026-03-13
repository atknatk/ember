package ai.ember.app.features.memories

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import ai.ember.app.core.models.MemoryItem
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * ViewModel for the Memories screen.
 *
 * Loads characters for the segment picker, fetches memories for the
 * selected segment (global or per-character), and handles memory deletion.
 * Mirrors iOS MemoriesViewModel behavior.
 */
@HiltViewModel
class MemoriesViewModel @Inject constructor(
    private val memoriesRepository: MemoriesRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow<MemoriesUiState>(MemoriesUiState.Loading)
    val uiState: StateFlow<MemoriesUiState> = _uiState.asStateFlow()

    init {
        loadInitialData()
    }

    /**
     * Loads characters and then the default (global) memories.
     */
    fun loadInitialData() {
        viewModelScope.launch {
            _uiState.value = MemoriesUiState.Loading

            memoriesRepository.getCharacters()
                .onSuccess { characters ->
                    _uiState.value = MemoriesUiState.Success(
                        characters = characters,
                        selectedSegment = MemorySegment.Global,
                        isLoadingMemories = true,
                    )
                    loadMemoriesForSegment(MemorySegment.Global)
                }
                .onFailure { e ->
                    _uiState.value = MemoriesUiState.Error(
                        e.message ?: "Something went wrong. Please try again.",
                    )
                }
        }
    }

    /**
     * Switches the selected segment and loads its memories.
     */
    fun selectSegment(segment: MemorySegment) {
        val currentState = _uiState.value as? MemoriesUiState.Success ?: return
        if (currentState.selectedSegment == segment) return

        _uiState.value = currentState.copy(
            selectedSegment = segment,
            memories = emptyList(),
            isLoadingMemories = true,
        )

        viewModelScope.launch {
            loadMemoriesForSegment(segment)
        }
    }

    /**
     * Deletes a memory. Shows confirmation by setting the deleting ID,
     * then removes from list on success.
     */
    fun deleteMemory(memory: MemoryItem) {
        val currentState = _uiState.value as? MemoriesUiState.Success ?: return

        _uiState.value = currentState.copy(isDeletingMemoryId = memory.id)

        viewModelScope.launch {
            val result = when (val segment = currentState.selectedSegment) {
                is MemorySegment.Global -> {
                    memoriesRepository.deleteGlobalMemory(memory.id)
                }
                is MemorySegment.CharacterSegment -> {
                    memoriesRepository.deleteCharacterMemory(segment.id, memory.id)
                }
            }

            val latestState = _uiState.value as? MemoriesUiState.Success ?: return@launch

            result
                .onSuccess {
                    _uiState.value = latestState.copy(
                        memories = latestState.memories.filter { it.id != memory.id },
                        isDeletingMemoryId = null,
                    )
                }
                .onFailure {
                    // Clear deleting state but keep memory in list
                    _uiState.value = latestState.copy(isDeletingMemoryId = null)
                }
        }
    }

    /**
     * Reloads memories for the currently selected segment.
     */
    fun retryLoadMemories() {
        val currentState = _uiState.value as? MemoriesUiState.Success ?: run {
            loadInitialData()
            return
        }

        _uiState.value = currentState.copy(isLoadingMemories = true)

        viewModelScope.launch {
            loadMemoriesForSegment(currentState.selectedSegment)
        }
    }

    private suspend fun loadMemoriesForSegment(segment: MemorySegment) {
        val result = when (segment) {
            is MemorySegment.Global -> memoriesRepository.getGlobalMemories()
            is MemorySegment.CharacterSegment -> memoriesRepository.getCharacterMemories(segment.id)
        }

        val currentState = _uiState.value as? MemoriesUiState.Success ?: return

        // Only update if we're still on the same segment
        if (currentState.selectedSegment != segment) return

        result
            .onSuccess { memories ->
                _uiState.value = currentState.copy(
                    memories = memories,
                    isLoadingMemories = false,
                )
            }
            .onFailure { e ->
                _uiState.value = currentState.copy(
                    memories = emptyList(),
                    isLoadingMemories = false,
                )
            }
    }
}
