package ai.ember.app.core.ui.components

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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import ai.ember.app.core.ui.theme.EmberShapes
import ai.ember.app.core.ui.theme.EmberSpacing

/**
 * Skeleton loading placeholder for the Home screen.
 *
 * Matches the layout of the Home success state:
 * - Shimmer greeting text area
 * - Shimmer daily summary card
 * - 4 shimmer character cards in a 2-column grid
 */
@Composable
fun HomeSkeletonLoader(
    modifier: Modifier = Modifier,
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
        modifier = modifier.fillMaxSize(),
        userScrollEnabled = false,
    ) {
        // Greeting skeleton — full width
        item(span = { GridItemSpan(2) }) {
            Column {
                ShimmerBox(
                    modifier = Modifier
                        .width(200.dp)
                        .height(28.dp),
                    shape = EmberShapes.chip,
                )
                Spacer(Modifier.height(EmberSpacing.xxs))
                ShimmerBox(
                    modifier = Modifier
                        .width(140.dp)
                        .height(16.dp),
                    shape = EmberShapes.chip,
                )
            }
        }

        // Daily summary card skeleton — full width
        item(span = { GridItemSpan(2) }) {
            ShimmerBox(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(100.dp),
                shape = EmberShapes.card,
            )
        }

        // Section header skeleton — full width
        item(span = { GridItemSpan(2) }) {
            ShimmerBox(
                modifier = Modifier
                    .width(120.dp)
                    .height(20.dp),
                shape = EmberShapes.chip,
            )
        }

        // 4 character card skeletons
        items(HOME_SKELETON_CARD_COUNT) {
            Column(
                modifier = Modifier.fillMaxWidth(),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                ShimmerBox(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(140.dp),
                    shape = EmberShapes.card,
                )
            }
        }
    }
}

/**
 * Skeleton loading placeholder for the Chat screen.
 *
 * Shows alternating shimmer bubbles mimicking a conversation:
 * left-aligned wider ones for assistant, right-aligned narrower for user.
 */
@Composable
fun ChatSkeletonLoader(
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(horizontal = EmberSpacing.md),
        verticalArrangement = Arrangement.spacedBy(EmberSpacing.xs),
    ) {
        Spacer(Modifier.height(EmberSpacing.xs))

        // Assistant bubble (wider, left-aligned)
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.Start,
        ) {
            ShimmerBox(
                modifier = Modifier
                    .fillMaxWidth(0.7f)
                    .height(60.dp),
                shape = EmberShapes.messageBubble,
            )
        }

        // User bubble (narrower, right-aligned)
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.End,
        ) {
            ShimmerBox(
                modifier = Modifier
                    .fillMaxWidth(0.5f)
                    .height(40.dp),
                shape = EmberShapes.messageBubble,
            )
        }

        // Assistant bubble
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.Start,
        ) {
            ShimmerBox(
                modifier = Modifier
                    .fillMaxWidth(0.65f)
                    .height(80.dp),
                shape = EmberShapes.messageBubble,
            )
        }

        // User bubble
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.End,
        ) {
            ShimmerBox(
                modifier = Modifier
                    .fillMaxWidth(0.45f)
                    .height(36.dp),
                shape = EmberShapes.messageBubble,
            )
        }
    }
}

/**
 * Skeleton loading placeholder for the Memories screen.
 *
 * Shows shimmer segment pills and memory row placeholders.
 */
@Composable
fun MemoriesSkeletonLoader(
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(horizontal = EmberSpacing.lg),
    ) {
        // Title skeleton
        ShimmerBox(
            modifier = Modifier
                .width(120.dp)
                .height(28.dp)
                .padding(top = EmberSpacing.md),
            shape = EmberShapes.chip,
        )

        Spacer(Modifier.height(EmberSpacing.md))

        // Segment pills skeleton
        Row(
            horizontalArrangement = Arrangement.spacedBy(EmberSpacing.xs),
        ) {
            repeat(MEMORIES_SKELETON_PILL_COUNT) {
                ShimmerBox(
                    modifier = Modifier
                        .width(70.dp)
                        .height(32.dp),
                    shape = EmberShapes.pill,
                )
            }
        }

        Spacer(Modifier.height(EmberSpacing.md))

        // Memory row skeletons
        repeat(MEMORIES_SKELETON_ROW_COUNT) {
            ShimmerBox(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(70.dp),
                shape = EmberShapes.input,
            )
            Spacer(Modifier.height(EmberSpacing.xs))
        }
    }
}

/**
 * Skeleton loading placeholder for the Profile screen.
 *
 * Shows shimmer placeholders matching the profile layout:
 * avatar circle, name, email, and settings rows.
 */
@Composable
fun ProfileSkeletonLoader(
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(horizontal = EmberSpacing.lg),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        // Title skeleton
        ShimmerBox(
            modifier = Modifier
                .width(80.dp)
                .height(28.dp)
                .padding(top = EmberSpacing.md)
                .align(Alignment.Start),
            shape = EmberShapes.chip,
        )

        Spacer(Modifier.height(EmberSpacing.xl))

        // Avatar circle
        ShimmerCircle(size = 80.dp)

        Spacer(Modifier.height(EmberSpacing.sm))

        // Name
        ShimmerBox(
            modifier = Modifier
                .width(120.dp)
                .height(22.dp),
            shape = EmberShapes.chip,
        )

        Spacer(Modifier.height(EmberSpacing.xxs))

        // Email
        ShimmerBox(
            modifier = Modifier
                .width(160.dp)
                .height(14.dp),
            shape = EmberShapes.chip,
        )

        Spacer(Modifier.height(EmberSpacing.xl))

        // Settings rows
        repeat(PROFILE_SKELETON_ROW_COUNT) {
            ShimmerBox(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(52.dp),
                shape = EmberShapes.input,
            )
            Spacer(Modifier.height(EmberSpacing.xs))
        }
    }
}

private const val HOME_SKELETON_CARD_COUNT = 4
private const val MEMORIES_SKELETON_PILL_COUNT = 3
private const val MEMORIES_SKELETON_ROW_COUNT = 5
private const val PROFILE_SKELETON_ROW_COUNT = 3
