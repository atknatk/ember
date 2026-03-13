package ai.ember.app.features.chat

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import ai.ember.app.core.ui.theme.EmberSpacing
import ai.ember.app.core.ui.theme.EmberTextSecondary

/**
 * Date separator shown between messages from different calendar days.
 *
 * Displays "Today", "Yesterday", or the formatted date (e.g., "March 10")
 * centered in the message list.
 */
@Composable
fun DateSeparator(
    dateString: String,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier
            .fillMaxWidth()
            .padding(vertical = EmberSpacing.sm),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = dateString,
            style = MaterialTheme.typography.labelMedium,
            color = EmberTextSecondary,
        )
    }
}
