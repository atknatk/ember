package ai.ember.app.features.chat

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.view.HapticFeedbackConstants
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import ai.ember.app.R
import ai.ember.app.core.ui.theme.EmberAIBubbleEnd
import ai.ember.app.core.ui.theme.EmberAIBubbleStart
import ai.ember.app.core.ui.theme.EmberPrimary
import ai.ember.app.core.ui.theme.EmberSpacing
import ai.ember.app.core.ui.theme.EmberTextSecondary

/**
 * A single message bubble in the chat.
 *
 * User messages appear on the right with primary color background.
 * AI messages appear on the left with a gradient background.
 * Long-press opens a context menu with a "Copy" action.
 */
@OptIn(ExperimentalFoundationApi::class)
@Composable
fun MessageBubble(
    message: ChatMessage,
    characterName: String,
    modifier: Modifier = Modifier,
) {
    val isUser = message.role == MessageRole.USER
    val context = LocalContext.current
    val view = LocalView.current
    var showMenu by remember { mutableStateOf(false) }

    val screenWidth = LocalConfiguration.current.screenWidthDp.dp
    val maxBubbleWidth = screenWidth * MAX_BUBBLE_WIDTH_FRACTION

    // Accessibility
    val roleLabel = if (isUser) {
        stringResource(R.string.chat_message_you)
    } else {
        characterName
    }
    val a11yLabel = stringResource(R.string.chat_message_a11y, roleLabel, message.content)
    val copyLabel = stringResource(R.string.chat_copy)

    Row(
        modifier = modifier
            .fillMaxWidth()
            .semantics {
                contentDescription = a11yLabel
                customActions = listOf(
                    CustomAccessibilityAction(copyLabel) {
                        copyToClipboard(context, message.content)
                        true
                    },
                )
            },
        horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start,
    ) {
        Box {
            Column(
                horizontalAlignment = if (isUser) Alignment.End else Alignment.Start,
            ) {
                Box(
                    modifier = Modifier
                        .widthIn(max = maxBubbleWidth)
                        .background(
                            brush = if (isUser) {
                                Brush.linearGradient(listOf(EmberPrimary, EmberPrimary))
                            } else {
                                Brush.linearGradient(
                                    listOf(EmberAIBubbleStart, EmberAIBubbleEnd),
                                )
                            },
                            shape = bubbleShape(isUser),
                        )
                        .combinedClickable(
                            onClick = {},
                            onLongClick = {
                                view.performHapticFeedback(
                                    HapticFeedbackConstants.LONG_PRESS,
                                )
                                showMenu = true
                            },
                        )
                        .padding(
                            horizontal = EmberSpacing.sm,
                            vertical = EmberSpacing.xs,
                        ),
                ) {
                    Text(
                        text = message.content,
                        style = MaterialTheme.typography.bodyLarge,
                        color = if (isUser) {
                            Color.White
                        } else {
                            MaterialTheme.colorScheme.onSurface
                        },
                    )
                }

                // Timestamp
                if (message.createdAt.isNotEmpty()) {
                    Text(
                        text = formatTimestamp(message.createdAt),
                        style = MaterialTheme.typography.labelSmall,
                        color = EmberTextSecondary,
                        modifier = Modifier.padding(
                            top = EmberSpacing.xxs,
                            start = EmberSpacing.xxs,
                            end = EmberSpacing.xxs,
                        ),
                    )
                }
            }

            // Context menu for copy
            DropdownMenu(
                expanded = showMenu,
                onDismissRequest = { showMenu = false },
            ) {
                DropdownMenuItem(
                    text = { Text(stringResource(R.string.chat_copy)) },
                    onClick = {
                        copyToClipboard(context, message.content)
                        view.performHapticFeedback(HapticFeedbackConstants.CONFIRM)
                        showMenu = false
                    },
                )
            }
        }
    }
}

/**
 * Returns the bubble shape with a characteristic "tail" effect.
 *
 * User bubbles: smaller bottom-right corner.
 * AI bubbles: smaller bottom-left corner.
 */
private fun bubbleShape(isUser: Boolean): RoundedCornerShape {
    val large = 16.dp
    val small = 4.dp
    return if (isUser) {
        RoundedCornerShape(
            topStart = large,
            topEnd = large,
            bottomStart = large,
            bottomEnd = small,
        )
    } else {
        RoundedCornerShape(
            topStart = large,
            topEnd = large,
            bottomStart = small,
            bottomEnd = large,
        )
    }
}

/**
 * Formats an ISO 8601 timestamp into HH:mm for display below the bubble.
 */
private fun formatTimestamp(isoTimestamp: String): String {
    // Extract HH:mm from ISO timestamp (e.g., "2026-02-23T14:31:00Z" -> "14:31")
    return try {
        if (isoTimestamp.length >= TIMESTAMP_END_INDEX) {
            isoTimestamp.substring(TIMESTAMP_START_INDEX, TIMESTAMP_END_INDEX)
        } else {
            ""
        }
    } catch (e: Exception) {
        ""
    }
}

private fun copyToClipboard(context: Context, text: String) {
    val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
    val clip = ClipData.newPlainText("message", text)
    clipboard.setPrimaryClip(clip)
}

private const val MAX_BUBBLE_WIDTH_FRACTION = 0.75f
private const val TIMESTAMP_START_INDEX = 11
private const val TIMESTAMP_END_INDEX = 16
