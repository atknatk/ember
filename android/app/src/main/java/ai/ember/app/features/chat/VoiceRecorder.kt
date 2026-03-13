package ai.ember.app.features.chat

import android.content.Context
import android.media.MediaRecorder
import android.os.Build
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Wraps [MediaRecorder] for voice recording with amplitude metering.
 *
 * Records audio in MPEG-4/AAC format to a temp file in the app cache
 * directory. Polls amplitude at [AMPLITUDE_POLL_INTERVAL_MS] intervals
 * to drive waveform visualization. Auto-stops after [MAX_RECORDING_MS].
 *
 * Lifecycle: [start] -> [stop] or [cancel]. After [stop], the recorded
 * file is available via [outputFile]. After [cancel], the file is deleted.
 */
@Singleton
class VoiceRecorder @Inject constructor(
    @ApplicationContext private val context: Context,
) {

    private var recorder: MediaRecorder? = null
    private var currentFile: File? = null
    private var amplitudeJob: Job? = null
    private var startTimeMs: Long = 0L

    private val _state = MutableStateFlow<VoiceRecordingState>(VoiceRecordingState.Idle)
    val state: StateFlow<VoiceRecordingState> = _state.asStateFlow()

    /** The recorded audio file, available after [stop] completes successfully. */
    val outputFile: File?
        get() = currentFile

    /**
     * Starts recording audio to a temp file.
     *
     * @param scope CoroutineScope for amplitude polling (typically viewModelScope).
     * @return true if recording started successfully, false on error.
     */
    fun start(scope: CoroutineScope): Boolean {
        if (recorder != null) return false

        val file = File(context.cacheDir, "voice_${System.currentTimeMillis()}.m4a")
        currentFile = file

        val mediaRecorder = createMediaRecorder()

        return try {
            mediaRecorder.apply {
                setAudioSource(MediaRecorder.AudioSource.MIC)
                setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
                setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
                setAudioSamplingRate(SAMPLE_RATE)
                setAudioChannels(CHANNELS)
                setAudioEncodingBitRate(BIT_RATE)
                setOutputFile(file.absolutePath)
                setMaxDuration(MAX_RECORDING_MS)
                setOnInfoListener { _, what, _ ->
                    if (what == MediaRecorder.MEDIA_RECORDER_INFO_MAX_DURATION_REACHED) {
                        stopInternal()
                    }
                }
                prepare()
                start()
            }

            recorder = mediaRecorder
            startTimeMs = System.currentTimeMillis()
            _state.value = VoiceRecordingState.Recording()

            amplitudeJob = scope.launch(Dispatchers.Default) {
                this.pollAmplitudes()
            }

            true
        } catch (e: Exception) {
            releaseRecorder()
            file.delete()
            currentFile = null
            _state.value = VoiceRecordingState.Error(
                e.message ?: "Failed to start recording",
            )
            false
        }
    }

    /**
     * Stops recording and keeps the audio file for upload.
     *
     * After calling this, [outputFile] contains the recorded audio.
     */
    fun stop() {
        stopInternal()
    }

    /**
     * Cancels recording and deletes the temp audio file.
     */
    fun cancel() {
        amplitudeJob?.cancel()
        amplitudeJob = null
        releaseRecorder()
        currentFile?.delete()
        currentFile = null
        _state.value = VoiceRecordingState.Idle
    }

    /**
     * Resets state back to Idle. Called after upload/transcription completes.
     */
    fun reset() {
        _state.value = VoiceRecordingState.Idle
    }

    /**
     * Updates the state to reflect upload/transcription progress.
     */
    fun updateState(newState: VoiceRecordingState) {
        _state.value = newState
    }

    private fun stopInternal() {
        amplitudeJob?.cancel()
        amplitudeJob = null

        try {
            recorder?.stop()
        } catch (_: Exception) {
            // May throw if stopped too quickly
        }

        releaseRecorder()
        // State transitions to Uploading/Transcribing are managed by ViewModel
    }

    private fun releaseRecorder() {
        try {
            recorder?.release()
        } catch (_: Exception) {
            // Ignore release errors
        }
        recorder = null
    }

    @Suppress("DEPRECATION")
    private fun createMediaRecorder(): MediaRecorder {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            MediaRecorder(context)
        } else {
            MediaRecorder()
        }
    }

    private suspend fun CoroutineScope.pollAmplitudes() {
        val amplitudes = mutableListOf<Float>()

        while (isActive) {
            val currentRecorder = recorder ?: break

            val amplitude = try {
                currentRecorder.maxAmplitude.toFloat() / MAX_AMPLITUDE
            } catch (_: Exception) {
                break
            }

            amplitudes.add(amplitude.coerceIn(MIN_AMPLITUDE, MAX_AMPLITUDE_NORMALIZED))

            // Keep only the most recent bars for the waveform display
            if (amplitudes.size > WAVEFORM_BAR_COUNT) {
                amplitudes.removeAt(0)
            }

            val elapsedMs = System.currentTimeMillis() - startTimeMs
            _state.value = VoiceRecordingState.Recording(
                durationMs = elapsedMs,
                amplitudes = amplitudes.toList(),
            )

            delay(AMPLITUDE_POLL_INTERVAL_MS)
        }
    }

    companion object {
        const val SAMPLE_RATE = 44100
        const val CHANNELS = 1
        const val BIT_RATE = 128000
        const val MAX_RECORDING_MS = 120_000 // 2 minutes
        const val AMPLITUDE_POLL_INTERVAL_MS = 100L
        const val WAVEFORM_BAR_COUNT = 12
        const val MAX_AMPLITUDE = 32767f
        const val MIN_AMPLITUDE = 0.05f
        const val MAX_AMPLITUDE_NORMALIZED = 1.0f
    }
}
