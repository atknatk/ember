package ai.ember.app.features.chat

import android.view.HapticFeedbackConstants
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.outlined.CameraAlt
import androidx.compose.material.icons.outlined.Mic
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import ai.ember.app.R
import ai.ember.app.core.ui.theme.EmberAccent
import ai.ember.app.core.ui.theme.EmberPrimary
import ai.ember.app.core.ui.theme.EmberShapes
import ai.ember.app.core.ui.theme.EmberSpacing
import ai.ember.app.core.ui.theme.EmberSurface
import ai.ember.app.core.ui.theme.EmberSurface2
import ai.ember.app.core.ui.theme.EmberTextDisabled

/**
 * Chat input bar with text field, send button, photo button,
 * and voice recording mic button.
 *
 * The mic button uses long-press to start recording and release to stop.
 * Dragging upward during recording cancels it. When recording is active,
 * a [VoiceRecordingOverlay] appears above the input bar showing
 * waveform, duration, and cancel hint.
 *
 * The send button fires haptic feedback on tap and is disabled
 * when the input is empty or streaming is in progress.
 */
@Composable
fun ChatInputBar(
    inputText: String,
    onInputChanged: (String) -> Unit,
    onSend: () -> Unit,
    isStreaming: Boolean,
    voiceState: VoiceRecordingState,
    onStartRecording: () -> Boolean,
    onStopRecording: () -> Unit,
    onCancelRecording: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val view = LocalView.current
    val isSendEnabled = inputText.trim().isNotEmpty() && !isStreaming
    val isRecording = voiceState is VoiceRecordingState.Recording
    val isProcessing = voiceState is VoiceRecordingState.Uploading ||
        voiceState is VoiceRecordingState.Transcribing

    Column(modifier = modifier.fillMaxWidth()) {
        // Voice recording overlay (above the input bar)
        VoiceRecordingOverlay(
            isVisible = isRecording,
            durationMs = (voiceState as? VoiceRecordingState.Recording)?.durationMs ?: 0L,
            amplitudes = (voiceState as? VoiceRecordingState.Recording)?.amplitudes ?: emptyList(),
        )

        Box(
            modifier = Modifier
                .fillMaxWidth()
                .shadow(
                    elevation = INPUT_BAR_SHADOW_ELEVATION,
                    ambientColor = Color.Black.copy(alpha = INPUT_BAR_SHADOW_ALPHA),
                    spotColor = Color.Black.copy(alpha = INPUT_BAR_SHADOW_ALPHA),
                )
                .background(EmberSurface)
                .padding(
                    horizontal = EmberSpacing.xs,
                    vertical = EmberSpacing.xs,
                ),
        ) {
            Row(
                verticalAlignment = Alignment.Bottom,
                modifier = Modifier.fillMaxWidth(),
            ) {
                // Photo button -- disabled placeholder
                IconButton(
                    onClick = {},
                    enabled = false,
                    modifier = Modifier
                        .size(48.dp)
                        .alpha(DISABLED_ALPHA),
                ) {
                    Icon(
                        imageVector = Icons.Outlined.CameraAlt,
                        contentDescription = stringResource(R.string.chat_attach_photo),
                        tint = EmberTextDisabled,
                    )
                }

                // Text field
                TextField(
                    value = inputText,
                    onValueChange = onInputChanged,
                    enabled = !isRecording && !isProcessing,
                    placeholder = {
                        Text(
                            text = when {
                                isProcessing -> stringResource(R.string.voice_transcribing)
                                else -> stringResource(R.string.chat_input_placeholder)
                            },
                            style = MaterialTheme.typography.bodyLarge,
                            color = EmberTextDisabled,
                        )
                    },
                    textStyle = MaterialTheme.typography.bodyLarge.copy(
                        color = MaterialTheme.colorScheme.onSurface,
                    ),
                    shape = EmberShapes.input,
                    colors = TextFieldDefaults.colors(
                        focusedContainerColor = EmberSurface2,
                        unfocusedContainerColor = EmberSurface2,
                        disabledContainerColor = EmberSurface2,
                        focusedIndicatorColor = Color.Transparent,
                        unfocusedIndicatorColor = Color.Transparent,
                        disabledIndicatorColor = Color.Transparent,
                        cursorColor = EmberPrimary,
                    ),
                    maxLines = MAX_INPUT_LINES,
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Default),
                    modifier = Modifier
                        .weight(1f)
                        .heightIn(min = 48.dp),
                )

                // Mic / processing indicator button
                if (isProcessing) {
                    Box(
                        modifier = Modifier.size(48.dp),
                        contentAlignment = Alignment.Center,
                    ) {
                        CircularProgressIndicator(
                            color = EmberPrimary,
                            modifier = Modifier.size(24.dp),
                            strokeWidth = 2.dp,
                        )
                    }
                } else {
                    MicButton(
                        isRecording = isRecording,
                        isEnabled = !isStreaming && !isProcessing,
                        onStartRecording = {
                            view.performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
                            onStartRecording()
                        },
                        onStopRecording = {
                            view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                            onStopRecording()
                        },
                        onCancelRecording = {
                            view.performHapticFeedback(HapticFeedbackConstants.REJECT)
                            onCancelRecording()
                        },
                    )
                }

                // Send button with scale-on-press animation
                SendButton(
                    isSendEnabled = isSendEnabled && !isRecording && !isProcessing,
                    onSend = {
                        view.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
                        onSend()
                    },
                )
            }
        }
    }
}

/**
 * Mic button with long-press to record and drag-up to cancel.
 *
 * Press and hold starts recording. Releasing stops recording.
 * Dragging upward beyond [CANCEL_DRAG_THRESHOLD_DP] cancels recording.
 */
@Composable
private fun MicButton(
    isRecording: Boolean,
    isEnabled: Boolean,
    onStartRecording: () -> Boolean,
    onStopRecording: () -> Unit,
    onCancelRecording: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val density = LocalDensity.current
    val cancelThresholdPx = with(density) { CANCEL_DRAG_THRESHOLD_DP.dp.toPx() }
    var dragOffset by remember { mutableFloatStateOf(0f) }

    Box(
        modifier = modifier
            .size(48.dp)
            .pointerInput(isEnabled) {
                if (!isEnabled) return@pointerInput
                detectDragGestures(
                    onDragStart = {
                        dragOffset = 0f
                        onStartRecording()
                    },
                    onDrag = { change, dragAmount ->
                        change.consume()
                        // Track upward drag (negative Y)
                        dragOffset += dragAmount.y
                        if (dragOffset < -cancelThresholdPx) {
                            onCancelRecording()
                        }
                    },
                    onDragEnd = {
                        if (dragOffset >= -cancelThresholdPx) {
                            onStopRecording()
                        }
                        dragOffset = 0f
                    },
                    onDragCancel = {
                        onCancelRecording()
                        dragOffset = 0f
                    },
                )
            },
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            imageVector = Icons.Outlined.Mic,
            contentDescription = stringResource(R.string.voice_record),
            tint = when {
                isRecording -> EmberAccent
                isEnabled -> EmberPrimary
                else -> EmberTextDisabled
            },
        )
    }
}

/**
 * Send button with scale-on-press animation per design system.
 * Scales to 0.85 on press and springs back to 1.0 on release.
 */
@Composable
private fun SendButton(
    isSendEnabled: Boolean,
    onSend: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var isPressed by remember { mutableStateOf(false) }
    val scale by animateFloatAsState(
        targetValue = if (isPressed) SEND_BUTTON_PRESSED_SCALE else 1f,
        animationSpec = spring(
            dampingRatio = SEND_BUTTON_SPRING_DAMPING,
            stiffness = SEND_BUTTON_SPRING_STIFFNESS,
        ),
        label = "sendButtonScale",
    )

    Box(
        modifier = modifier
            .size(48.dp)
            .graphicsLayer {
                scaleX = scale
                scaleY = scale
            }
            .pointerInput(isSendEnabled) {
                if (isSendEnabled) {
                    detectTapGestures(
                        onPress = {
                            isPressed = true
                            tryAwaitRelease()
                            isPressed = false
                            onSend()
                        },
                    )
                }
            },
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            imageVector = Icons.AutoMirrored.Filled.Send,
            contentDescription = stringResource(R.string.chat_send_message),
            tint = if (isSendEnabled) {
                EmberPrimary
            } else {
                EmberPrimary.copy(alpha = DISABLED_ALPHA)
            },
        )
    }
}

private const val DISABLED_ALPHA = 0.4f
private const val MAX_INPUT_LINES = 5
private val INPUT_BAR_SHADOW_ELEVATION = 4.dp
private const val INPUT_BAR_SHADOW_ALPHA = 0.2f
private const val SEND_BUTTON_PRESSED_SCALE = 0.85f
private const val SEND_BUTTON_SPRING_DAMPING = 0.6f
private const val SEND_BUTTON_SPRING_STIFFNESS = 800f
private const val CANCEL_DRAG_THRESHOLD_DP = 100
