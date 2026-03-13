package ai.ember.app.features.home

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.ErrorOutline
import androidx.compose.material.icons.outlined.Group
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import ai.ember.app.R
import ai.ember.app.core.models.Character
import ai.ember.app.core.models.MessagePreview
import ai.ember.app.core.ui.components.HomeSkeletonLoader
import ai.ember.app.core.ui.components.emberCardShadow
import ai.ember.app.core.ui.theme.EmberAccent
import ai.ember.app.core.ui.theme.EmberPrimary
import ai.ember.app.core.ui.theme.EmberShapes
import ai.ember.app.core.ui.theme.EmberSpacing
import ai.ember.app.core.ui.theme.EmberSurface2
import ai.ember.app.core.ui.theme.EmberSurface3
import ai.ember.app.core.ui.theme.EmberTextDisabled
import android.view.HapticFeedbackConstants
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Home screen displaying character grid, greeting header,
 * daily summary card, and pull-to-refresh.
 *
 * Mirrors iOS HomeView behavior and layout.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    onNavigateToChat: (characterId: String, characterName: String) -> Unit = { _, _ -> },
    onNavigateToCreateCharacter: () -> Unit = {},
    viewModel: HomeViewModel = hiltViewModel(),
    modifier: Modifier = Modifier,
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()

    when (val state = uiState) {
        is HomeUiState.Loading -> LoadingState(modifier = modifier)

        is HomeUiState.Empty -> EmptyState(
            userName = state.userName,
            onAddCharacter = onNavigateToCreateCharacter,
            modifier = modifier,
        )

        is HomeUiState.Success -> SuccessContent(
            state = state,
            viewModel = viewModel,
            onNavigateToChat = onNavigateToChat,
            onAddCharacter = onNavigateToCreateCharacter,
            modifier = modifier,
        )

        is HomeUiState.Error -> ErrorState(
            message = state.message,
            onRetry = viewModel::loadCharacters,
            modifier = modifier,
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SuccessContent(
    state: HomeUiState.Success,
    viewModel: HomeViewModel,
    onNavigateToChat: (characterId: String, characterName: String) -> Unit,
    onAddCharacter: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val view = LocalView.current

    PullToRefreshBox(
        isRefreshing = state.isRefreshing,
        onRefresh = { viewModel.loadCharacters() },
        modifier = modifier.fillMaxSize(),
    ) {
        LazyVerticalGrid(
            columns = GridCells.Fixed(2),
            contentPadding = PaddingValues(
                start = EmberSpacing.lg,
                end = EmberSpacing.lg,
                top = EmberSpacing.xs,
                bottom = EmberSpacing.xxl,
            ),
            horizontalArrangement = Arrangement.spacedBy(EmberSpacing.md),
            verticalArrangement = Arrangement.spacedBy(EmberSpacing.md),
        ) {
            // Greeting header — full width
            item(span = { GridItemSpan(2) }) {
                GreetingHeader(userName = state.userName)
            }

            // Daily summary card — full width
            item(span = { GridItemSpan(2) }) {
                val defaultCharacter = state.characters.firstOrNull { it.isDefault }
                val defaultMessage = defaultCharacter?.let { state.lastMessages[it.id] }
                DailySummaryCard(
                    characterName = defaultCharacter?.name,
                    message = defaultMessage,
                    onTap = {
                        if (defaultCharacter != null) {
                            view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                            viewModel.markCharacterAsOpened(defaultCharacter.id)
                            onNavigateToChat(defaultCharacter.id, defaultCharacter.name)
                        }
                    },
                )
            }

            // Section header — full width
            item(span = { GridItemSpan(2) }) {
                Text(
                    text = stringResource(R.string.home_characters_section),
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.onBackground,
                )
            }

            // Character cards
            itemsIndexed(
                items = state.characters,
                key = { _, character -> character.id },
            ) { index, character ->
                CharacterCard(
                    character = character,
                    lastMessage = state.lastMessages[character.id],
                    hasUnread = viewModel.hasUnreadMessages(character),
                    onTap = {
                        view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                        viewModel.markCharacterAsOpened(character.id)
                        onNavigateToChat(character.id, character.name)
                    },
                )
            }

            // Add character card
            item {
                AddCharacterCard(
                    onTap = {
                        view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                        onAddCharacter()
                    },
                )
            }
        }
    }
}

// -- Greeting Header --

@Composable
private fun GreetingHeader(
    userName: String,
    modifier: Modifier = Modifier,
) {
    val greetingText = if (userName.isNotEmpty()) {
        "${HomeViewModel.greeting()}, $userName"
    } else {
        HomeViewModel.greeting()
    }

    val dateFormat = remember { SimpleDateFormat("EEEE, d MMMM", Locale.getDefault()) }
    val dateString = remember { dateFormat.format(Date()) }

    // Fade-in + slide-up animation on first appearance
    var hasAppeared by remember { mutableStateOf(false) }
    val alpha by androidx.compose.animation.core.animateFloatAsState(
        targetValue = if (hasAppeared) 1f else 0f,
        animationSpec = tween(durationMillis = GREETING_ANIM_DURATION_MS),
        label = "greetingAlpha",
    )
    val offsetY by androidx.compose.animation.core.animateFloatAsState(
        targetValue = if (hasAppeared) 0f else GREETING_OFFSET_Y,
        animationSpec = tween(durationMillis = GREETING_ANIM_DURATION_MS),
        label = "greetingOffset",
    )

    LaunchedEffect(Unit) {
        hasAppeared = true
    }

    Column(
        modifier = modifier
            .fillMaxWidth()
            .alpha(alpha)
            .offset(y = offsetY.dp)
            .semantics(mergeDescendants = true) {},
    ) {
        Text(
            text = greetingText,
            style = MaterialTheme.typography.headlineMedium,
            color = MaterialTheme.colorScheme.onBackground,
        )
        Spacer(Modifier.height(EmberSpacing.xxs))
        Text(
            text = dateString,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

private const val GREETING_ANIM_DURATION_MS = 400
private const val GREETING_OFFSET_Y = 10f
private const val UNREAD_PULSE_TARGET_SCALE = 1.15f
private const val UNREAD_PULSE_DURATION_MS = 800

// -- Daily Summary Card --

@Composable
private fun DailySummaryCard(
    characterName: String?,
    message: MessagePreview?,
    onTap: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val summaryDescription = if (characterName != null && message != null) {
        stringResource(R.string.home_daily_summary_a11y, characterName, message.content)
    } else {
        stringResource(R.string.home_daily_summary_empty_a11y)
    }

    Card(
        modifier = modifier
            .fillMaxWidth()
            .emberCardShadow()
            .clickable(onClick = onTap)
            .semantics { contentDescription = summaryDescription },
        shape = EmberShapes.card,
        colors = CardDefaults.cardColors(
            containerColor = EmberSurface2,
        ),
    ) {
        Box {
            // Left accent bar
            Box(
                modifier = Modifier
                    .size(width = 3.dp, height = 80.dp)
                    .background(
                        brush = Brush.verticalGradient(
                            colors = listOf(EmberPrimary, EmberPrimary.copy(alpha = 0.4f)),
                        ),
                    )
                    .align(Alignment.CenterStart),
            )

            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(
                        start = EmberSpacing.lg,
                        end = EmberSpacing.md,
                        top = EmberSpacing.md,
                        bottom = EmberSpacing.md,
                    ),
            ) {
                if (characterName != null) {
                    Text(
                        text = characterName,
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Spacer(Modifier.height(EmberSpacing.xxs))
                }

                if (message != null) {
                    Text(
                        text = message.content,
                        style = MaterialTheme.typography.bodyLarge,
                        color = MaterialTheme.colorScheme.onSurface,
                        maxLines = 3,
                        overflow = TextOverflow.Ellipsis,
                    )
                } else {
                    Text(
                        text = stringResource(R.string.home_daily_summary_placeholder),
                        style = MaterialTheme.typography.bodyLarge,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

// -- Character Card --

@Composable
private fun CharacterCard(
    character: Character,
    lastMessage: MessagePreview?,
    hasUnread: Boolean,
    onTap: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val newMessageLabel = stringResource(R.string.home_new_message)
    val cardDescription = buildString {
        append(character.name)
        append(", ")
        append(character.template.replace("_", " "))
        if (lastMessage != null) {
            append(". ")
            append(lastMessage.content)
        }
        if (hasUnread) {
            append(", ")
            append(newMessageLabel)
        }
    }

    Card(
        modifier = modifier
            .fillMaxWidth()
            .emberCardShadow()
            .clickable(onClick = onTap)
            .semantics { contentDescription = cardDescription },
        shape = EmberShapes.card,
        colors = CardDefaults.cardColors(
            containerColor = EmberSurface2,
        ),
    ) {
        Box(modifier = Modifier.fillMaxWidth()) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(EmberSpacing.md),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                // Avatar circle with template icon
                Box(
                    modifier = Modifier
                        .size(56.dp)
                        .clip(CircleShape)
                        .background(EmberSurface3),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(
                        imageVector = HomeViewModel.templateIcon(character.template),
                        contentDescription = null,
                        tint = EmberPrimary,
                        modifier = Modifier.size(24.dp),
                    )
                }

                Spacer(Modifier.height(EmberSpacing.xs))

                // Character name
                Text(
                    text = character.name,
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.onSurface,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    textAlign = TextAlign.Center,
                )

                Spacer(Modifier.height(EmberSpacing.xxs))

                // Last message preview
                Text(
                    text = lastMessage?.content
                        ?: stringResource(R.string.home_no_messages_yet),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                    textAlign = TextAlign.Center,
                )
            }

            // Unread dot with pulse animation
            if (hasUnread) {
                val pulseTransition = rememberInfiniteTransition(label = "unreadPulse")
                val pulseScale by pulseTransition.animateFloat(
                    initialValue = 1f,
                    targetValue = UNREAD_PULSE_TARGET_SCALE,
                    animationSpec = infiniteRepeatable(
                        animation = tween(
                            durationMillis = UNREAD_PULSE_DURATION_MS,
                            easing = LinearEasing,
                        ),
                        repeatMode = RepeatMode.Reverse,
                    ),
                    label = "unreadPulseScale",
                )
                Box(
                    modifier = Modifier
                        .padding(EmberSpacing.xs)
                        .size(8.dp)
                        .scale(pulseScale)
                        .clip(CircleShape)
                        .background(EmberAccent)
                        .align(Alignment.TopEnd),
                )
            }
        }
    }
}

// -- Add Character Card --

@Composable
private fun AddCharacterCard(
    onTap: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val addCharacterA11y = stringResource(R.string.home_add_character_a11y)

    Card(
        modifier = modifier
            .fillMaxWidth()
            .clickable(onClick = onTap)
            .semantics {
                contentDescription = addCharacterA11y
            },
        shape = EmberShapes.card,
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.background,
        ),
        border = BorderStroke(
            width = 1.5.dp,
            color = EmberTextDisabled,
        ),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(EmberSpacing.md),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Spacer(Modifier.height(EmberSpacing.md))

            Icon(
                imageVector = Icons.Outlined.Add,
                contentDescription = null,
                tint = EmberPrimary,
                modifier = Modifier.size(28.dp),
            )

            Spacer(Modifier.height(EmberSpacing.xs))

            Text(
                text = stringResource(R.string.home_add_character),
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            Spacer(Modifier.height(EmberSpacing.md))
        }
    }
}

// -- Loading State (Shimmer Skeleton) --

@Composable
private fun LoadingState(
    modifier: Modifier = Modifier,
) {
    HomeSkeletonLoader(modifier = modifier)
}

// -- Empty State --

@Composable
private fun EmptyState(
    userName: String,
    onAddCharacter: () -> Unit,
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
            imageVector = Icons.Outlined.Group,
            contentDescription = null,
            tint = EmberPrimary,
            modifier = Modifier.size(48.dp),
        )

        Spacer(Modifier.height(EmberSpacing.md))

        Text(
            text = stringResource(R.string.home_empty_title),
            style = MaterialTheme.typography.headlineMedium,
            color = MaterialTheme.colorScheme.onBackground,
        )

        Spacer(Modifier.height(EmberSpacing.xs))

        Text(
            text = stringResource(R.string.home_empty_subtitle),
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )

        Spacer(Modifier.height(EmberSpacing.xl))

        Button(
            onClick = onAddCharacter,
            shape = EmberShapes.pill,
            colors = ButtonDefaults.buttonColors(
                containerColor = EmberPrimary,
            ),
        ) {
            Text(
                text = stringResource(R.string.home_add_character),
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.onPrimary,
            )
        }
    }
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
                text = stringResource(R.string.home_retry),
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.onPrimary,
            )
        }
    }
}
