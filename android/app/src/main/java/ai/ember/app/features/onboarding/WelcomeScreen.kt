package ai.ember.app.features.onboarding

import android.view.HapticFeedbackConstants
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.spring
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.Psychology
import androidx.compose.foundation.BorderStroke
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import ai.ember.app.R
import ai.ember.app.core.ui.theme.EmberPrimary
import ai.ember.app.core.ui.theme.EmberSpacing
import ai.ember.app.core.ui.theme.EmberTextDisabled
import ai.ember.app.core.ui.theme.EmberTextSecondary
import com.airbnb.lottie.compose.LottieAnimation
import com.airbnb.lottie.compose.LottieCompositionSpec
import com.airbnb.lottie.compose.LottieConstants
import com.airbnb.lottie.compose.rememberLottieComposition

/**
 * Welcome carousel screen with 3 pages introducing Ember.
 *
 * Each page shows a Lottie animation (with fallback icon), title,
 * and description. Page indicators and navigation buttons at the bottom.
 */
@Composable
fun WelcomeScreen(
    currentPage: Int,
    onPageChanged: (Int) -> Unit,
    onNextPage: () -> Unit,
    onSkip: () -> Unit,
    onGetStarted: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val view = LocalView.current
    val pagerState = rememberPagerState(
        initialPage = currentPage,
        pageCount = { OnboardingUiState.WELCOME_PAGE_COUNT },
    )

    // Sync pager with ViewModel state
    LaunchedEffect(currentPage) {
        if (pagerState.currentPage != currentPage) {
            pagerState.animateScrollToPage(currentPage)
        }
    }

    // Notify ViewModel of pager swipe
    LaunchedEffect(pagerState) {
        snapshotFlow { pagerState.currentPage }.collect { page ->
            if (page != currentPage) {
                view.performHapticFeedback(HapticFeedbackConstants.CLOCK_TICK)
                onPageChanged(page)
            }
        }
    }

    Column(
        modifier = modifier.fillMaxSize(),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Spacer(modifier = Modifier.height(EmberSpacing.xxxl))

        // Pager
        HorizontalPager(
            state = pagerState,
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f),
        ) { page ->
            WelcomePage(pageIndex = page)
        }

        // Page indicators
        PageIndicator(
            pageCount = OnboardingUiState.WELCOME_PAGE_COUNT,
            currentPage = pagerState.currentPage,
        )

        Spacer(modifier = Modifier.height(EmberSpacing.xxl))

        // Navigation buttons
        WelcomeNavigationButtons(
            currentPage = pagerState.currentPage,
            onNext = {
                view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                onNextPage()
            },
            onGetStarted = {
                view.performHapticFeedback(HapticFeedbackConstants.CONFIRM)
                onGetStarted()
            },
        )

        // Skip link (visible on pages 0 and 1)
        if (pagerState.currentPage < OnboardingUiState.WELCOME_PAGE_COUNT - 1) {
            TextButton(
                onClick = {
                    view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                    onSkip()
                },
            ) {
                Text(
                    text = stringResource(R.string.onboarding_skip),
                    style = MaterialTheme.typography.bodyMedium,
                    color = EmberTextSecondary,
                )
            }
        }

        Spacer(modifier = Modifier.height(EmberSpacing.xxl))
    }
}

@Composable
private fun WelcomePage(
    pageIndex: Int,
    modifier: Modifier = Modifier,
) {
    val pageData = welcomePages[pageIndex]

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(horizontal = EmberSpacing.lg),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        // Lottie animation with fallback icon
        WelcomeAnimation(
            lottieAsset = pageData.lottieAsset,
            fallbackIcon = pageData.fallbackIcon,
        )

        Spacer(modifier = Modifier.height(EmberSpacing.xxl))

        // Title
        Text(
            text = stringResource(pageData.titleResId),
            style = MaterialTheme.typography.headlineLarge,
            color = MaterialTheme.colorScheme.onBackground,
            textAlign = TextAlign.Center,
        )

        Spacer(modifier = Modifier.height(EmberSpacing.sm))

        // Description
        Text(
            text = stringResource(pageData.descriptionResId),
            style = MaterialTheme.typography.bodyLarge,
            color = EmberTextSecondary,
            textAlign = TextAlign.Center,
            maxLines = 3,
        )
    }
}

@Composable
private fun WelcomeAnimation(
    lottieAsset: String,
    fallbackIcon: ImageVector,
    modifier: Modifier = Modifier,
) {
    val composition by rememberLottieComposition(
        LottieCompositionSpec.Asset(lottieAsset),
    )

    if (composition != null) {
        LottieAnimation(
            composition = composition,
            iterations = LottieConstants.IterateForever,
            modifier = modifier.size(200.dp),
        )
    } else {
        // Fallback icon when Lottie asset is unavailable
        Icon(
            imageVector = fallbackIcon,
            contentDescription = null,
            tint = EmberPrimary,
            modifier = modifier.size(120.dp),
        )
    }
}

@Composable
private fun PageIndicator(
    pageCount: Int,
    currentPage: Int,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier,
        horizontalArrangement = Arrangement.spacedBy(EmberSpacing.xs),
    ) {
        repeat(pageCount) { index ->
            val color by animateColorAsState(
                targetValue = if (index == currentPage) EmberPrimary else EmberTextDisabled,
                animationSpec = spring(),
                label = "page_indicator_color",
            )
            Box(
                modifier = Modifier
                    .size(EmberSpacing.xs)
                    .clip(CircleShape)
                    .background(color),
            )
        }
    }
}

@Composable
private fun WelcomeNavigationButtons(
    currentPage: Int,
    onNext: () -> Unit,
    onGetStarted: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val isLastPage = currentPage == OnboardingUiState.WELCOME_PAGE_COUNT - 1

    if (isLastPage) {
        // Get Started — gradient primary button
        Button(
            onClick = onGetStarted,
            shape = ai.ember.app.core.ui.theme.EmberShapes.pill,
            colors = ButtonDefaults.buttonColors(
                containerColor = EmberPrimary,
            ),
            modifier = modifier
                .fillMaxWidth()
                .padding(horizontal = EmberSpacing.lg)
                .height(52.dp),
        ) {
            Text(
                text = stringResource(R.string.onboarding_get_started),
                style = MaterialTheme.typography.titleMedium,
            )
        }
    } else {
        // Next — outlined secondary button
        OutlinedButton(
            onClick = onNext,
            shape = ai.ember.app.core.ui.theme.EmberShapes.pill,
            colors = ButtonDefaults.outlinedButtonColors(
                contentColor = EmberPrimary,
            ),
            border = BorderStroke(1.dp, EmberPrimary),
            modifier = modifier
                .fillMaxWidth()
                .padding(horizontal = EmberSpacing.lg)
                .height(52.dp),
        ) {
            Text(
                text = stringResource(R.string.onboarding_next),
                style = MaterialTheme.typography.titleMedium,
            )
        }
    }
}

/**
 * Data for each welcome page (title, description, animation).
 */
private data class WelcomePageData(
    val titleResId: Int,
    val descriptionResId: Int,
    val lottieAsset: String,
    val fallbackIcon: ImageVector,
)

private val welcomePages = listOf(
    WelcomePageData(
        titleResId = R.string.onboarding_welcome_title_1,
        descriptionResId = R.string.onboarding_welcome_desc_1,
        lottieAsset = "onboarding-welcome.json",
        fallbackIcon = Icons.Filled.AutoAwesome,
    ),
    WelcomePageData(
        titleResId = R.string.onboarding_welcome_title_2,
        descriptionResId = R.string.onboarding_welcome_desc_2,
        lottieAsset = "onboarding-memory.json",
        fallbackIcon = Icons.Filled.Psychology,
    ),
    WelcomePageData(
        titleResId = R.string.onboarding_welcome_title_3,
        descriptionResId = R.string.onboarding_welcome_desc_3,
        lottieAsset = "onboarding-companion.json",
        fallbackIcon = Icons.Filled.Favorite,
    ),
)
