package ai.ember.app.features.chat

/**
 * Sealed state representing the voice recording lifecycle.
 *
 * Separate from [ChatUiState] to allow independent state tracking
 * of voice recording without affecting the main chat UI state.
 */
sealed interface VoiceRecordingState {

    /** No recording in progress. */
    data object Idle : VoiceRecordingState

    /** Actively recording audio with live amplitude data. */
    data class Recording(
        val durationMs: Long = 0L,
        val amplitudes: List<Float> = emptyList(),
    ) : VoiceRecordingState

    /** Recording finished, uploading audio file to S3. */
    data object Uploading : VoiceRecordingState

    /** Upload complete, waiting for STT transcription. */
    data object Transcribing : VoiceRecordingState

    /** An error occurred during recording, upload, or transcription. */
    data class Error(val message: String) : VoiceRecordingState
}
