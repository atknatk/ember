package ai.ember.app.features.memories

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.DeleteOutline
import androidx.compose.material.icons.outlined.ErrorOutline
import androidx.compose.material.icons.outlined.Psychology
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SwipeToDismissBox
import androidx.compose.material3.SwipeToDismissBoxValue
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.material3.rememberSwipeToDismissBoxState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import ai.ember.app.R
import ai.ember.app.core.models.Character
import ai.ember.app.core.models.MemoryItem
import ai.ember.app.core.ui.components.MemoriesSkeletonLoader
import ai.ember.app.core.ui.components.emberCardShadowLight
import ai.ember.app.core.ui.theme.EmberError
import ai.ember.app.core.ui.theme.EmberPrimary
import ai.ember.app.core.ui.theme.EmberShapes
import ai.ember.app.core.ui.theme.EmberSpacing
import ai.ember.app.core.ui.theme.EmberSurface2
import ai.ember.app.core.ui.theme.EmberSurface3
import android.view.HapticFeedbackConstants
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.TimeUnit

/**
 * Memories screen showing per-character and global Mem0 memories
 * with segment picker and swipe-to-delete.
 *
 * Mirrors iOS MemoriesView behavior and layout.
 */
@Composable
fun MemoriesScreen(
    viewModel: MemoriesViewModel = hiltViewModel(),
    modifier: Modifier = Modifier,
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()

    when (val state = uiState) {
        is MemoriesUiState.Loading -> LoadingState(modifier = modifier)

        is MemoriesUiState.Success -> SuccessContent(
            state = state,
            onSegmentSelected = viewModel::selectSegment,
            onDeleteMemory = viewModel::deleteMemory,
            onRefresh = viewModel::retryLoadMemories,
            onRetry = viewModel::retryLoadMemories,
            modifier = modifier,
        )

        is MemoriesUiState.Error -> ErrorState(
            message = state.message,
            onRetry = viewModel::loadInitialData,
            modifier = modifier,
        )
    }
}

// -- Success Content --

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SuccessContent(
    state: MemoriesUiState.Success,
    onSegmentSelected: (MemorySegment) -> Unit,
    onDeleteMemory: (MemoryItem) -> Unit,
    onRefresh: () -> Unit,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    PullToRefreshBox(
        isRefreshing = state.isLoadingMemories && state.memories.isNotEmpty(),
        onRefresh = onRefresh,
        modifier = modifier.fillMaxSize(),
    ) {
        Column(
            modifier = Modifier.fillMaxSize(),
        ) {
            // Screen title
            Text(
                text = stringResource(R.string.memories_title),
                style = MaterialTheme.typography.headlineMedium,
                color = MaterialTheme.colorScheme.onBackground,
                modifier = Modifier
                    .padding(
                        start = EmberSpacing.lg,
                        end = EmberSpacing.lg,
                        top = EmberSpacing.md,
                        bottom = EmberSpacing.xs,
                    ),
            )

            // Character segment picker
            CharacterPicker(
                characters = state.characters,
                selectedSegment = state.selectedSegment,
                onSegmentSelected = onSegmentSelected,
            )

            // Content area
            when {
                state.isLoadingMemories && state.memories.isEmpty() -> {
                    MemoriesSkeletonLoader(
                        modifier = Modifier.weight(1f),
                    )
                }

                state.memories.isEmpty() -> {
                    EmptyMemoriesState(
                        modifier = Modifier
                            .fillMaxSize()
                            .weight(1f),
                    )
                }

                else -> {
                    MemoryList(
                        memories = state.memories,
                        deletingMemoryId = state.isDeletingMemoryId,
                        onDeleteMemory = onDeleteMemory,
                        modifier = Modifier.weight(1f),
                    )
                }
            }
        }
    }
}

// -- Character Picker --

@Composable
private fun CharacterPicker(
    characters: List<Character>,
    selectedSegment: MemorySegment,
    onSegmentSelected: (MemorySegment) -> Unit,
    modifier: Modifier = Modifier,
) {
    val view = LocalView.current

    LazyRow(
        modifier = modifier
            .fillMaxWidth()
            .padding(vertical = EmberSpacing.sm),
        contentPadding = PaddingValues(horizontal = EmberSpacing.lg),
        horizontalArrangement = Arrangement.spacedBy(EmberSpacing.xs),
    ) {
        // Global chip
        item(key = "global") {
            val isSelected = selectedSegment is MemorySegment.Global
            val globalA11y = stringResource(R.string.memories_global_a11y)

            SegmentChip(
                label = stringResource(R.string.memories_segment_global),
                isSelected = isSelected,
                onClick = {
                    view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                    onSegmentSelected(MemorySegment.Global)
                },
                contentDescription = globalA11y,
            )
        }

        // Character chips
        items(
            items = characters,
            key = { it.id },
        ) { character ->
            val segment = MemorySegment.CharacterSegment(
                id = character.id,
                name = character.name,
            )
            val isSelected = selectedSegment == segment
            val characterA11y = stringResource(
                R.string.memories_character_a11y,
                character.name,
            )

            SegmentChip(
                label = character.name,
                isSelected = isSelected,
                onClick = {
                    view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                    onSegmentSelected(segment)
                },
                contentDescription = characterA11y,
            )
        }
    }
}

@Composable
private fun SegmentChip(
    label: String,
    isSelected: Boolean,
    onClick: () -> Unit,
    contentDescription: String,
    modifier: Modifier = Modifier,
) {
    val backgroundColor = if (isSelected) EmberPrimary else EmberSurface2
    val textColor = if (isSelected) {
        MaterialTheme.colorScheme.onPrimary
    } else {
        MaterialTheme.colorScheme.onSurfaceVariant
    }
    val fontWeight = if (isSelected) FontWeight.SemiBold else FontWeight.Normal

    Box(
        modifier = modifier
            .clip(EmberShapes.pill)
            .background(backgroundColor)
            .clickable(onClick = onClick)
            .padding(
                horizontal = EmberSpacing.sm,
                vertical = EmberSpacing.xs,
            )
            .semantics {
                this.contentDescription = contentDescription
            },
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.labelMedium,
            color = textColor,
            fontWeight = fontWeight,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

// -- Memory List --

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MemoryList(
    memories: List<MemoryItem>,
    deletingMemoryId: String?,
    onDeleteMemory: (MemoryItem) -> Unit,
    modifier: Modifier = Modifier,
) {
    var memoryToDelete by remember { mutableStateOf<MemoryItem?>(null) }
    val view = LocalView.current

    LazyColumn(
        modifier = modifier.fillMaxWidth(),
        contentPadding = PaddingValues(
            start = EmberSpacing.lg,
            end = EmberSpacing.lg,
            top = EmberSpacing.xs,
            bottom = EmberSpacing.xxl,
        ),
        verticalArrangement = Arrangement.spacedBy(EmberSpacing.xs),
    ) {
        items(
            items = memories,
            key = { it.id },
        ) { memory ->
            val isDeleting = deletingMemoryId == memory.id
            val dismissState = rememberSwipeToDismissBoxState(
                confirmValueChange = { value ->
                    if (value == SwipeToDismissBoxValue.EndToStart) {
                        view.performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
                        memoryToDelete = memory
                        false // Don't auto-dismiss; wait for confirmation
                    } else {
                        false
                    }
                },
            )

            SwipeToDismissBox(
                state = dismissState,
                backgroundContent = {
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .clip(EmberShapes.input)
                            .background(EmberError)
                            .padding(horizontal = EmberSpacing.lg),
                        contentAlignment = Alignment.CenterEnd,
                    ) {
                        Icon(
                            imageVector = Icons.Outlined.DeleteOutline,
                            contentDescription = stringResource(R.string.memories_delete_a11y),
                            tint = MaterialTheme.colorScheme.onError,
                        )
                    }
                },
                enableDismissFromStartToEnd = false,
                modifier = Modifier.animateItem(),
            ) {
                MemoryRow(
                    memory = memory,
                    isDeleting = isDeleting,
                )
            }
        }
    }

    // Delete confirmation dialog
    memoryToDelete?.let { memory ->
        DeleteConfirmationDialog(
            onConfirm = {
                onDeleteMemory(memory)
                memoryToDelete = null
            },
            onDismiss = {
                memoryToDelete = null
            },
        )
    }
}

// -- Memory Row --

@Composable
private fun MemoryRow(
    memory: MemoryItem,
    isDeleting: Boolean,
    modifier: Modifier = Modifier,
) {
    val relativeTime = memory.createdAt?.let { formatRelativeTime(it) }
    val memoryA11y = buildString {
        append(stringResource(R.string.memories_row_a11y_prefix))
        append(memory.memory)
        if (relativeTime != null) {
            append(". ")
            append(relativeTime)
        }
    }

    Card(
        modifier = modifier
            .fillMaxWidth()
            .emberCardShadowLight()
            .semantics { contentDescription = memoryA11y },
        shape = EmberShapes.input,
        colors = CardDefaults.cardColors(containerColor = EmberSurface2),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(EmberSpacing.md),
            horizontalArrangement = Arrangement.spacedBy(EmberSpacing.sm),
            verticalAlignment = Alignment.Top,
        ) {
            // Brain icon
            Box(
                modifier = Modifier
                    .size(32.dp)
                    .clip(CircleShape)
                    .background(EmberSurface3),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    imageVector = Icons.Outlined.Psychology,
                    contentDescription = null,
                    tint = EmberPrimary,
                    modifier = Modifier.size(16.dp),
                )
            }

            // Memory text and timestamp
            Column(
                modifier = Modifier.weight(1f),
            ) {
                Text(
                    text = memory.memory,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurface,
                )

                if (relativeTime != null) {
                    Spacer(Modifier.height(EmberSpacing.xxs))
                    Text(
                        text = relativeTime,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            // Deleting indicator
            if (isDeleting) {
                CircularProgressIndicator(
                    modifier = Modifier.size(16.dp),
                    color = MaterialTheme.colorScheme.primary,
                    strokeWidth = 2.dp,
                )
            }
        }
    }
}

// -- Delete Confirmation Dialog --

@Composable
private fun DeleteConfirmationDialog(
    onConfirm: () -> Unit,
    onDismiss: () -> Unit,
) {
    val view = LocalView.current

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Text(text = stringResource(R.string.memories_delete_title))
        },
        text = {
            Text(text = stringResource(R.string.memories_delete_message))
        },
        confirmButton = {
            TextButton(
                onClick = {
                    view.performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
                    onConfirm()
                },
            ) {
                Text(
                    text = stringResource(R.string.memories_delete_confirm),
                    color = EmberError,
                )
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text(text = stringResource(R.string.memories_delete_cancel))
            }
        },
        containerColor = EmberSurface2,
    )
}

// -- Empty State --

@Composable
private fun EmptyMemoriesState(
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
            imageVector = Icons.Outlined.Psychology,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.size(48.dp),
        )

        Spacer(Modifier.height(EmberSpacing.md))

        Text(
            text = stringResource(R.string.memories_empty_title),
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.onBackground,
            textAlign = TextAlign.Center,
        )

        Spacer(Modifier.height(EmberSpacing.xs))

        Text(
            text = stringResource(R.string.memories_empty_subtitle),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )
    }
}

// -- Loading State (Shimmer Skeleton) --

@Composable
private fun LoadingState(
    modifier: Modifier = Modifier,
) {
    MemoriesSkeletonLoader(modifier = modifier)
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
                text = stringResource(R.string.memories_retry),
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.onPrimary,
            )
        }
    }
}

// -- Utilities --

/**
 * Formats an ISO 8601 timestamp string into a relative time description.
 */
private fun formatRelativeTime(isoTimestamp: String): String? {
    return try {
        val formats = listOf(
            SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US),
            SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US),
            SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.US),
        )

        var date: Date? = null
        for (format in formats) {
            try {
                date = format.parse(isoTimestamp)
                if (date != null) break
            } catch (e: Exception) {
                continue
            }
        }

        if (date == null) return null

        val now = System.currentTimeMillis()
        val diff = now - date.time
        val minutes = TimeUnit.MILLISECONDS.toMinutes(diff)
        val hours = TimeUnit.MILLISECONDS.toHours(diff)
        val days = TimeUnit.MILLISECONDS.toDays(diff)
        val weeks = days / 7

        when {
            minutes < 1 -> "Just now"
            minutes < 60 -> "${minutes}m ago"
            hours < 24 -> "${hours}h ago"
            days < 7 -> "${days}d ago"
            weeks < 4 -> "${weeks}w ago"
            else -> {
                val outputFormat = SimpleDateFormat("MMM d, yyyy", Locale.getDefault())
                outputFormat.format(date)
            }
        }
    } catch (e: Exception) {
        null
    }
}
