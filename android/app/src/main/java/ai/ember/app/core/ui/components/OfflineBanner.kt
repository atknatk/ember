package ai.ember.app.core.ui.components

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.WifiOff
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import ai.ember.app.R
import ai.ember.app.core.ui.theme.EmberSpacing
import ai.ember.app.core.ui.theme.EmberWarning

/**
 * Persistent (non-dismissible) warning banner shown when the device is offline.
 *
 * Uses amber/warning color styling. Automatically appears/disappears
 * with connectivity changes. Placed above error banners in the overlay.
 *
 * Mirrors iOS OfflineBannerView behavior and design.
 *
 * @param isOffline Whether the device is currently offline.
 */
@Composable
fun OfflineBanner(
    isOffline: Boolean,
    modifier: Modifier = Modifier,
) {
    val offlineA11y = stringResource(R.string.offline_banner_a11y)

    AnimatedVisibility(
        visible = isOffline,
        enter = expandVertically(expandFrom = Alignment.Top) + fadeIn(),
        exit = shrinkVertically(shrinkTowards = Alignment.Top) + fadeOut(),
        modifier = modifier,
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .background(EmberWarning)
                .padding(
                    horizontal = EmberSpacing.md,
                    vertical = EmberSpacing.xs,
                )
                .semantics { contentDescription = offlineA11y },
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                imageVector = Icons.Outlined.WifiOff,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.surface,
                modifier = Modifier.size(16.dp),
            )

            Spacer(Modifier.width(EmberSpacing.xs))

            Text(
                text = stringResource(R.string.offline_banner_message),
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.surface,
            )
        }
    }
}
