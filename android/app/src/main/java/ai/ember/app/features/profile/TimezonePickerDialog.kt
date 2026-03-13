package ai.ember.app.features.profile

import android.view.HapticFeedbackConstants
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import ai.ember.app.R
import ai.ember.app.core.ui.theme.EmberPrimary
import ai.ember.app.core.ui.theme.EmberShapes
import ai.ember.app.core.ui.theme.EmberSpacing
import ai.ember.app.core.ui.theme.EmberSurface
import ai.ember.app.core.ui.theme.EmberSurface3
import java.util.TimeZone

/**
 * Bottom sheet dialog for selecting an IANA timezone.
 *
 * Shows a searchable list of timezone identifiers with UTC offsets.
 * The currently selected timezone is highlighted with a checkmark.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TimezonePickerDialog(
    currentTimezone: String,
    onTimezoneSelected: (String) -> Unit,
    onDismiss: () -> Unit,
) {
    val view = LocalView.current
    var searchText by remember { mutableStateOf("") }
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    val allTimezones = remember { TimeZone.getAvailableIDs().sorted() }
    val filteredTimezones = remember(searchText) {
        if (searchText.isEmpty()) {
            allTimezones
        } else {
            allTimezones.filter {
                it.contains(searchText, ignoreCase = true)
            }
        }
    }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = EmberSurface,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .fillMaxHeight(0.85f),
        ) {
            // Title
            Text(
                text = stringResource(R.string.profile_timezone_picker_title),
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.onBackground,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.padding(
                    horizontal = EmberSpacing.lg,
                    vertical = EmberSpacing.sm,
                ),
            )

            // Search field
            val searchA11y = stringResource(R.string.profile_timezone_search_a11y)
            OutlinedTextField(
                value = searchText,
                onValueChange = { searchText = it },
                singleLine = true,
                placeholder = {
                    Text(
                        text = stringResource(R.string.profile_timezone_search_hint),
                        style = MaterialTheme.typography.bodyMedium,
                    )
                },
                leadingIcon = {
                    Icon(
                        imageVector = Icons.Outlined.Search,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                },
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = EmberPrimary,
                    unfocusedBorderColor = EmberSurface3,
                    cursorColor = EmberPrimary,
                ),
                shape = EmberShapes.input,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = EmberSpacing.lg)
                    .semantics { contentDescription = searchA11y },
            )

            Spacer(Modifier.height(EmberSpacing.sm))

            // Timezone list
            LazyColumn(
                modifier = Modifier.fillMaxWidth(),
            ) {
                items(
                    items = filteredTimezones,
                    key = { it },
                ) { timezoneId ->
                    val tz = TimeZone.getTimeZone(timezoneId)
                    val offsetMs = tz.rawOffset
                    val hours = offsetMs / 3_600_000
                    val minutes = Math.abs(offsetMs % 3_600_000) / 60_000
                    val offsetString = String.format("UTC%+03d:%02d", hours, minutes)
                    val isSelected = timezoneId == currentTimezone
                    val rowA11y = "$timezoneId, $offsetString"

                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable {
                                view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                                onTimezoneSelected(timezoneId)
                            }
                            .padding(
                                horizontal = EmberSpacing.lg,
                                vertical = EmberSpacing.sm,
                            )
                            .semantics { contentDescription = rowA11y },
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = timezoneId,
                                style = MaterialTheme.typography.bodyLarge,
                                color = if (isSelected) {
                                    EmberPrimary
                                } else {
                                    MaterialTheme.colorScheme.onSurface
                                },
                                fontWeight = if (isSelected) FontWeight.SemiBold else FontWeight.Normal,
                            )
                            Text(
                                text = offsetString,
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }

                        if (isSelected) {
                            Spacer(Modifier.width(EmberSpacing.xs))
                            Icon(
                                imageVector = Icons.Filled.Check,
                                contentDescription = null,
                                tint = EmberPrimary,
                            )
                        }
                    }

                    HorizontalDivider(
                        color = EmberSurface3,
                        modifier = Modifier.padding(horizontal = EmberSpacing.lg),
                    )
                }
            }
        }
    }
}
