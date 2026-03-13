package ai.ember.app.features.chat

import android.content.Context
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.PlaybackParameters
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Singleton manager for TTS audio playback using Media3 ExoPlayer.
 *
 * Only one audio track plays at a time. Starting a new track stops
 * the current one. Exposes [playbackState] as a [StateFlow] for the
 * UI to observe via collectAsStateWithLifecycle.
 *
 * Position is polled every [POSITION_POLL_INTERVAL_MS] while playing.
 */
@Singleton
class AudioPlayerManager @Inject constructor(
    @ApplicationContext private val context: Context,
) {

    private val _playbackState = MutableStateFlow<AudioPlaybackState>(AudioPlaybackState.Idle)
    val playbackState: StateFlow<AudioPlaybackState> = _playbackState.asStateFlow()

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var positionJob: Job? = null
    private var currentMessageId: String? = null
    private var currentSpeed: Float = DEFAULT_SPEED

    private val player: ExoPlayer by lazy {
        ExoPlayer.Builder(context).build().also { exo ->
            exo.addListener(playerListener)
        }
    }

    private val playerListener = object : Player.Listener {
        override fun onPlaybackStateChanged(playbackState: Int) {
            val msgId = currentMessageId ?: return
            when (playbackState) {
                Player.STATE_READY -> {
                    val current = _playbackState.value
                    if (current is AudioPlaybackState.Loading) {
                        if (player.playWhenReady) {
                            _playbackState.value = AudioPlaybackState.Playing(
                                messageId = msgId,
                                currentMs = player.currentPosition,
                                durationMs = player.duration.coerceAtLeast(0),
                                speed = currentSpeed,
                            )
                            startPositionPolling()
                        }
                    }
                }

                Player.STATE_ENDED -> {
                    stopPositionPolling()
                    _playbackState.value = AudioPlaybackState.Idle
                    currentMessageId = null
                }

                else -> { /* STATE_BUFFERING, STATE_IDLE — no-op */ }
            }
        }

        override fun onPlayerError(error: PlaybackException) {
            stopPositionPolling()
            val msgId = currentMessageId ?: return
            _playbackState.value = AudioPlaybackState.Error(
                messageId = msgId,
                message = error.localizedMessage ?: "Playback error",
            )
            currentMessageId = null
        }
    }

    /**
     * Starts playback of a TTS audio URL for the given message.
     *
     * If another message is playing, it is stopped first.
     * Call this after receiving the audio URL from the TTS API.
     *
     * @param url The S3 audio URL to play.
     * @param messageId The chat message ID this audio belongs to.
     */
    fun play(url: String, messageId: String) {
        stop()
        currentMessageId = messageId
        _playbackState.value = AudioPlaybackState.Loading(messageId)

        player.setMediaItem(MediaItem.fromUri(url))
        player.playbackParameters = PlaybackParameters(currentSpeed)
        player.playWhenReady = true
        player.prepare()
    }

    /**
     * Pauses current playback. No-op if not playing.
     */
    fun pause() {
        if (player.isPlaying) {
            player.pause()
            stopPositionPolling()
            val msgId = currentMessageId ?: return
            _playbackState.value = AudioPlaybackState.Paused(
                messageId = msgId,
                currentMs = player.currentPosition,
                durationMs = player.duration.coerceAtLeast(0),
                speed = currentSpeed,
            )
        }
    }

    /**
     * Resumes paused playback. No-op if not paused.
     */
    fun resume() {
        val state = _playbackState.value
        if (state is AudioPlaybackState.Paused) {
            player.play()
            _playbackState.value = AudioPlaybackState.Playing(
                messageId = state.messageId,
                currentMs = player.currentPosition,
                durationMs = state.durationMs,
                speed = currentSpeed,
            )
            startPositionPolling()
        }
    }

    /**
     * Stops playback and resets to Idle.
     */
    fun stop() {
        stopPositionPolling()
        player.stop()
        player.clearMediaItems()
        currentMessageId = null
        _playbackState.value = AudioPlaybackState.Idle
    }

    /**
     * Sets the playback speed. Takes effect immediately if playing.
     *
     * @param speed One of 0.75f, 1.0f, 1.25f, 1.5f.
     */
    fun setSpeed(speed: Float) {
        currentSpeed = speed
        player.playbackParameters = PlaybackParameters(speed)

        val state = _playbackState.value
        when (state) {
            is AudioPlaybackState.Playing -> {
                _playbackState.value = state.copy(speed = speed)
            }
            is AudioPlaybackState.Paused -> {
                _playbackState.value = state.copy(speed = speed)
            }
            else -> { /* no-op */ }
        }
    }

    /**
     * Sets the loading state for a message before the TTS API call completes.
     *
     * @param messageId The message ID being loaded.
     */
    fun setLoading(messageId: String) {
        stop()
        currentMessageId = messageId
        _playbackState.value = AudioPlaybackState.Loading(messageId)
    }

    /**
     * Releases ExoPlayer resources. Call when the application is destroyed.
     */
    fun release() {
        stopPositionPolling()
        player.removeListener(playerListener)
        player.release()
    }

    private fun startPositionPolling() {
        positionJob?.cancel()
        positionJob = scope.launch {
            while (isActive) {
                val msgId = currentMessageId ?: break
                val state = _playbackState.value
                if (state is AudioPlaybackState.Playing) {
                    _playbackState.value = state.copy(
                        currentMs = player.currentPosition,
                        durationMs = player.duration.coerceAtLeast(0),
                    )
                } else {
                    break
                }
                delay(POSITION_POLL_INTERVAL_MS)
            }
        }
    }

    private fun stopPositionPolling() {
        positionJob?.cancel()
        positionJob = null
    }

    companion object {
        private const val POSITION_POLL_INTERVAL_MS = 200L
        private const val DEFAULT_SPEED = 1.0f
    }
}
