package ai.ember.app.features.chat

import android.view.HapticFeedbackConstants
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.outlined.CameraAlt
import androidx.compose.material.icons.outlined.Mic
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import ai.ember.app.R
import ai.ember.app.core.ui.theme.EmberPrimary
import ai.ember.app.core.ui.theme.EmberShapes
import ai.ember.app.core.ui.theme.EmberSpacing
import ai.ember.app.core.ui.theme.EmberSurface
import ai.ember.app.core.ui.theme.EmberSurface2
import ai.ember.app.core.ui.theme.EmberSurface3
import ai.ember.app.core.ui.theme.EmberTextDisabled

/**
 * Chat input bar with text field, send button, and placeholder
 * photo/voice buttons (disabled until Phase 5).
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
    modifier: Modifier = Modifier,
) {
    val view = LocalView.current
    val isSendEnabled = inputText.trim().isNotEmpty() && !isStreaming

    Box(
        modifier = modifier
            .fillMaxWidth()
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
            // Photo button — disabled, Phase 5
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
                placeholder = {
                    Text(
                        text = stringResource(R.string.chat_input_placeholder),
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
                    focusedIndicatorColor = Color.Transparent,
                    unfocusedIndicatorColor = Color.Transparent,
                    cursorColor = EmberPrimary,
                ),
                maxLines = MAX_INPUT_LINES,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Default),
                modifier = Modifier
                    .weight(1f)
                    .heightIn(min = 48.dp),
            )

            // Voice button — disabled, Phase 5
            IconButton(
                onClick = {},
                enabled = false,
                modifier = Modifier
                    .size(48.dp)
                    .alpha(DISABLED_ALPHA),
            ) {
                Icon(
                    imageVector = Icons.Outlined.Mic,
                    contentDescription = stringResource(R.string.chat_voice_message),
                    tint = EmberTextDisabled,
                )
            }

            // Send button
            IconButton(
                onClick = {
                    if (isSendEnabled) {
                        view.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
                        onSend()
                    }
                },
                enabled = isSendEnabled,
                modifier = Modifier.size(48.dp),
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
    }
}

private const val DISABLED_ALPHA = 0.4f
private const val MAX_INPUT_LINES = 5
