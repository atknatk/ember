package ai.ember.app.features.chat

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.outlined.ErrorOutline
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import ai.ember.app.R
import ai.ember.app.core.ui.components.ChatSkeletonLoader
import ai.ember.app.core.ui.theme.EmberBackground
import ai.ember.app.core.ui.theme.EmberPrimary
import ai.ember.app.core.ui.theme.EmberShapes
import ai.ember.app.core.ui.theme.EmberSpacing
import ai.ember.app.core.ui.theme.EmberSurface3

/**
 * Chat screen displaying conversation with an AI character.
 *
 * Shows message list with user/AI bubbles, typing indicator during streaming,
 * date separators between message groups, and an input bar at the bottom.
 * Supports cursor-based pagination for loading older messages on scroll.
 *
 * Mirrors iOS ChatView behavior and layout.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChatScreen(
    onNavigateBack: () -> Unit,
    viewModel: ChatViewModel = hiltViewModel(),
    modifier: Modifier = Modifier,
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    val inputText by viewModel.inputText.collectAsStateWithLifecycle()

    // Cancel SSE stream when leaving the screen
    DisposableEffect(Unit) {
        onDispose { viewModel.cancelStream() }
    }

    Scaffold(
        containerColor = EmberBackground,
        topBar = {
            ChatTopBar(
                characterName = when (val state = uiState) {
                    is ChatUiState.Success -> state.characterName
                    else -> ""
                },
                onNavigateBack = onNavigateBack,
            )
        },
        modifier = modifier,
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .imePadding(),
        ) {
            when (val state = uiState) {
                is ChatUiState.Loading -> LoadingState(
                    modifier = Modifier.weight(1f),
                )

                is ChatUiState.Success -> {
                    ChatContent(
                        state = state,
                        onLoadMore = viewModel::loadMoreMessages,
                        modifier = Modifier.weight(1f),
                    )
                    ChatInputBar(
                        inputText = inputText,
                        onInputChanged = viewModel::onInputChanged,
                        onSend = viewModel::sendMessage,
                        isStreaming = state.isStreaming,
                    )
                }

                is ChatUiState.Error -> ErrorState(
                    message = state.message,
                    onRetry = viewModel::loadHistory,
                    modifier = Modifier.weight(1f),
                )
            }
        }
    }
}

// -- Top Bar --

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ChatTopBar(
    characterName: String,
    onNavigateBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    TopAppBar(
        title = {
            Row(
                verticalAlignment = Alignment.CenterVertically,
            ) {
                // Small avatar placeholder circle
                Box(
                    modifier = Modifier
                        .size(32.dp)
                        .clip(CircleShape)
                        .background(EmberSurface3),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        text = characterName.firstOrNull()?.uppercase() ?: "",
                        style = MaterialTheme.typography.labelMedium,
                        color = EmberPrimary,
                    )
                }
                Spacer(Modifier.width(EmberSpacing.xs))
                Text(
                    text = characterName,
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.onBackground,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        },
        navigationIcon = {
            IconButton(onClick = onNavigateBack) {
                Icon(
                    imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                    contentDescription = stringResource(R.string.chat_navigate_back),
                    tint = MaterialTheme.colorScheme.onBackground,
                )
            }
        },
        colors = TopAppBarDefaults.topAppBarColors(
            containerColor = EmberBackground,
        ),
        modifier = modifier,
    )
}

// -- Chat Content (Message List + Typing Indicator) --

@Composable
private fun ChatContent(
    state: ChatUiState.Success,
    onLoadMore: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val listState = rememberLazyListState()

    // Auto-scroll to bottom when new messages arrive or during streaming
    val messageCount = state.messages.size
    LaunchedEffect(messageCount, state.isStreaming) {
        if (messageCount > 0) {
            // Scroll to the very last item (including typing indicator if streaming)
            val targetIndex = if (state.isStreaming) messageCount else messageCount - 1
            listState.animateScrollToItem(targetIndex.coerceAtLeast(0))
        }
    }

    // Trigger load more when scrolled near the top
    val shouldLoadMore by remember {
        derivedStateOf {
            val firstVisibleItem = listState.firstVisibleItemIndex
            firstVisibleItem <= LOAD_MORE_THRESHOLD &&
                state.hasMoreMessages &&
                !state.isLoadingMore
        }
    }

    LaunchedEffect(shouldLoadMore) {
        if (shouldLoadMore) {
            onLoadMore()
        }
    }

    LazyColumn(
        state = listState,
        contentPadding = PaddingValues(
            start = EmberSpacing.md,
            end = EmberSpacing.md,
            top = EmberSpacing.xs,
            bottom = EmberSpacing.xs,
        ),
        verticalArrangement = Arrangement.spacedBy(EmberSpacing.xxs),
        modifier = modifier.fillMaxWidth(),
    ) {
        // Loading more indicator at top
        if (state.isLoadingMore) {
            item(key = "loading_more") {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = EmberSpacing.xs),
                    contentAlignment = Alignment.Center,
                ) {
                    CircularProgressIndicator(
                        color = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.size(24.dp),
                    )
                }
            }
        }

        // Messages with date separators
        itemsIndexed(
            items = state.messages,
            key = { _, message -> message.id },
        ) { index, message ->
            // Date separator between messages from different days
            val showDateSeparator = shouldShowDateSeparator(
                currentMessage = message,
                previousMessage = if (index > 0) state.messages[index - 1] else null,
            )
            if (showDateSeparator) {
                DateSeparator(dateString = formatDateSeparator(message.createdAt))
            }

            // Message bubble with slide-in animation
            AnimatedVisibility(
                visible = true,
                enter = slideInVertically(initialOffsetY = { it / 2 }) + fadeIn(),
                exit = fadeOut(),
            ) {
                MessageBubble(
                    message = message,
                    characterName = state.characterName,
                )
            }
        }

        // Typing indicator during streaming before first chunk
        if (state.isStreaming) {
            val lastMessage = state.messages.lastOrNull()
            val showTypingIndicator = lastMessage == null ||
                lastMessage.role == MessageRole.USER
            if (showTypingIndicator) {
                item(key = "typing_indicator") {
                    TypingIndicator(
                        modifier = Modifier.padding(top = EmberSpacing.xxs),
                    )
                }
            }
        }
    }
}

// -- Loading State (Shimmer Skeleton) --

@Composable
private fun LoadingState(
    modifier: Modifier = Modifier,
) {
    ChatSkeletonLoader(modifier = modifier)
}

// -- Error State --

@Composable
private fun ErrorState(
    message: String,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(horizontal = EmberSpacing.lg),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Icon(
            imageVector = Icons.Outlined.ErrorOutline,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.error,
            modifier = Modifier.size(48.dp),
        )

        Spacer(Modifier.height(EmberSpacing.md))

        Text(
            text = message,
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onBackground,
            textAlign = TextAlign.Center,
        )

        Spacer(Modifier.height(EmberSpacing.xl))

        Button(
            onClick = onRetry,
            shape = EmberShapes.pill,
            colors = ButtonDefaults.buttonColors(
                containerColor = EmberPrimary,
            ),
        ) {
            Text(
                text = stringResource(R.string.chat_retry),
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.onPrimary,
            )
        }
    }
}

// -- Helpers --

/**
 * Determines if a date separator should be shown between two messages.
 * Shows a separator when the day changes between consecutive messages.
 */
private fun shouldShowDateSeparator(
    currentMessage: ChatMessage,
    previousMessage: ChatMessage?,
): Boolean {
    if (previousMessage == null) return currentMessage.createdAt.isNotEmpty()
    val currentDay = currentMessage.createdAt.take(DATE_PREFIX_LENGTH)
    val previousDay = previousMessage.createdAt.take(DATE_PREFIX_LENGTH)
    return currentDay != previousDay
}

/**
 * Formats an ISO 8601 timestamp into a user-friendly date separator string.
 *
 * Returns "Today", "Yesterday", or the date portion from the ISO string.
 */
private fun formatDateSeparator(isoTimestamp: String): String {
    if (isoTimestamp.length < DATE_PREFIX_LENGTH) return isoTimestamp
    // Extract date portion (YYYY-MM-DD)
    val datePart = isoTimestamp.take(DATE_PREFIX_LENGTH)

    val today = java.time.LocalDate.now().toString()
    val yesterday = java.time.LocalDate.now().minusDays(1).toString()

    return when (datePart) {
        today -> "Today"
        yesterday -> "Yesterday"
        else -> {
            try {
                val date = java.time.LocalDate.parse(datePart)
                val formatter = java.time.format.DateTimeFormatter.ofPattern("MMMM d")
                date.format(formatter)
            } catch (e: Exception) {
                datePart
            }
        }
    }
}

private const val LOAD_MORE_THRESHOLD = 3
private const val DATE_PREFIX_LENGTH = 10
