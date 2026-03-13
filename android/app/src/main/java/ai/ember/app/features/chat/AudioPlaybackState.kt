package ai.ember.app.features.chat

/**
 * Sealed state for TTS audio playback.
 *
 * Tracked by [AudioPlayerManager] and exposed to the UI layer.
 * Each active state carries the [messageId] of the message being played,
 * allowing the UI to show the progress bar on the correct bubble.
 */
sealed interface AudioPlaybackState {

    /** No audio is playing or loaded. */
    data object Idle : AudioPlaybackState

    /** TTS request is in flight or audio is buffering. */
    data class Loading(val messageId: String) : AudioPlaybackState

    /** Audio is actively playing. */
    data class Playing(
        val messageId: String,
        val currentMs: Long,
        val durationMs: Long,
        val speed: Float,
    ) : AudioPlaybackState

    /** Audio is paused mid-playback. */
    data class Paused(
        val messageId: String,
        val currentMs: Long,
        val durationMs: Long,
        val speed: Float,
    ) : AudioPlaybackState

    /** Playback failed with a user-facing error. */
    data class Error(
        val messageId: String,
        val message: String,
    ) : AudioPlaybackState
}

/** Available playback speed options for TTS audio. */
val TTS_SPEED_OPTIONS = listOf(0.75f, 1.0f, 1.25f, 1.5f)
