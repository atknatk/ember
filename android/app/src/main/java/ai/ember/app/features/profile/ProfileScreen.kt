package ai.ember.app.features.profile

import android.view.HapticFeedbackConstants
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AccountCircle
import androidx.compose.material.icons.outlined.CameraAlt
import androidx.compose.material.icons.outlined.ChevronRight
import androidx.compose.material.icons.outlined.DeleteOutline
import androidx.compose.material.icons.outlined.Edit
import androidx.compose.material.icons.outlined.ErrorOutline
import androidx.compose.material.icons.outlined.Language
import androidx.compose.material.icons.outlined.Logout
import androidx.compose.material.icons.outlined.Schedule
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import ai.ember.app.R
import ai.ember.app.core.ui.theme.EmberBackground
import ai.ember.app.core.ui.theme.EmberError
import ai.ember.app.core.ui.theme.EmberGradientEnd
import ai.ember.app.core.ui.theme.EmberGradientStart
import ai.ember.app.core.ui.theme.EmberPrimary
import ai.ember.app.core.ui.theme.EmberShapes
import ai.ember.app.core.ui.theme.EmberSpacing
import ai.ember.app.core.ui.theme.EmberSurface2
import ai.ember.app.core.ui.theme.EmberSurface3
import coil.compose.AsyncImage
import coil.request.ImageRequest

/**
 * Profile screen showing user info, preferences, and account actions.
 *
 * Sections:
 * 1. Profile header (avatar + name + email)
 * 2. Preferences (timezone, language, notifications)
 * 3. Account actions (sign out, delete)
 *
 * Mirrors iOS ProfileView behavior and layout.
 */
@Composable
fun ProfileScreen(
    onSignOut: () -> Unit = {},
    viewModel: ProfileViewModel = hiltViewModel(),
    modifier: Modifier = Modifier,
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    val shouldSignOut by viewModel.shouldSignOut.collectAsStateWithLifecycle()
    val snackbarHostState = remember { SnackbarHostState() }

    // Handle sign-out navigation
    LaunchedEffect(shouldSignOut) {
        if (shouldSignOut) {
            onSignOut()
        }
    }

    // Handle snackbar messages
    LaunchedEffect(uiState) {
        val message = (uiState as? ProfileUiState.Success)?.snackbarMessage
        if (message != null) {
            snackbarHostState.showSnackbar(message)
            viewModel.clearSnackbar()
        }
    }

    Scaffold(
        containerColor = EmberBackground,
        snackbarHost = { SnackbarHost(snackbarHostState) },
    ) { paddingValues ->
        when (val state = uiState) {
            is ProfileUiState.Loading -> LoadingState(
                modifier = modifier.padding(paddingValues),
            )

            is ProfileUiState.Success -> SuccessContent(
                state = state,
                viewModel = viewModel,
                modifier = modifier.padding(paddingValues),
            )

            is ProfileUiState.Error -> ErrorState(
                message = state.message,
                onRetry = viewModel::loadProfile,
                modifier = modifier.padding(paddingValues),
            )
        }
    }
}

// -- Success Content --

@Composable
private fun SuccessContent(
    state: ProfileUiState.Success,
    viewModel: ProfileViewModel,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current

    val photoPickerLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.PickVisualMedia(),
    ) { uri ->
        if (uri != null) {
            val inputStream = context.contentResolver.openInputStream(uri)
            val imageData = inputStream?.readBytes()
            inputStream?.close()
            if (imageData != null) {
                viewModel.uploadAvatar(imageData)
            }
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState()),
    ) {
        // Screen title
        Text(
            text = stringResource(R.string.profile_title),
            style = MaterialTheme.typography.headlineMedium,
            color = MaterialTheme.colorScheme.onBackground,
            modifier = Modifier.padding(
                start = EmberSpacing.lg,
                end = EmberSpacing.lg,
                top = EmberSpacing.md,
                bottom = EmberSpacing.xs,
            ),
        )

        Spacer(Modifier.height(EmberSpacing.md))

        // Profile Header
        ProfileHeader(
            profile = state.profile,
            isEditingName = state.isEditingName,
            editedName = state.editedName,
            isSaving = state.isSaving,
            isUploadingAvatar = state.isUploadingAvatar,
            onAvatarClick = {
                photoPickerLauncher.launch(
                    PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly),
                )
            },
            onStartEditName = viewModel::startEditingName,
            onCancelEditName = viewModel::cancelEditingName,
            onNameChanged = viewModel::onNameChanged,
            onSaveName = viewModel::saveName,
        )

        Spacer(Modifier.height(EmberSpacing.xl))

        // Preferences Section
        PreferencesSection(
            profile = state.profile,
            characters = state.characters,
            notificationPreferences = state.notificationPreferences,
            onTimezoneClick = viewModel::showTimezonePicker,
            onLanguageChanged = viewModel::updateLanguage,
            onNotificationChanged = viewModel::updateNotificationPreference,
        )

        Spacer(Modifier.height(EmberSpacing.xl))

        // Account Section
        AccountSection(
            onSignOut = viewModel::signOut,
            onDeleteAccount = viewModel::showDeleteConfirmation,
        )

        Spacer(Modifier.height(EmberSpacing.xxl))
    }

    // Timezone picker dialog
    if (state.showTimezonePicker) {
        TimezonePickerDialog(
            currentTimezone = state.profile.timezone,
            onTimezoneSelected = viewModel::updateTimezone,
            onDismiss = viewModel::hideTimezonePicker,
        )
    }

    // Delete confirmation dialog
    if (state.showDeleteConfirmation) {
        DeleteConfirmationDialog(
            confirmationText = state.deleteConfirmationText,
            isSaving = state.isSaving,
            onConfirmationTextChanged = viewModel::onDeleteConfirmationTextChanged,
            onConfirm = viewModel::deleteAccount,
            onDismiss = viewModel::hideDeleteConfirmation,
        )
    }
}

// -- Profile Header --

@Composable
private fun ProfileHeader(
    profile: ProfileData,
    isEditingName: Boolean,
    editedName: String,
    isSaving: Boolean,
    isUploadingAvatar: Boolean,
    onAvatarClick: () -> Unit,
    onStartEditName: () -> Unit,
    onCancelEditName: () -> Unit,
    onNameChanged: (String) -> Unit,
    onSaveName: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val avatarA11y = stringResource(R.string.profile_avatar_a11y)

    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = EmberSpacing.lg),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        // Avatar
        Box(
            modifier = Modifier
                .size(80.dp)
                .clip(CircleShape)
                .clickable(onClick = onAvatarClick)
                .semantics { contentDescription = avatarA11y },
            contentAlignment = Alignment.Center,
        ) {
            if (profile.avatarUrl != null) {
                AsyncImage(
                    model = ImageRequest.Builder(LocalContext.current)
                        .data(profile.avatarUrl)
                        .crossfade(true)
                        .build(),
                    contentDescription = null,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier
                        .size(80.dp)
                        .clip(CircleShape),
                )
            } else {
                // Gradient circle with initial
                Box(
                    modifier = Modifier
                        .size(80.dp)
                        .clip(CircleShape)
                        .background(
                            brush = Brush.linearGradient(
                                colors = listOf(EmberGradientStart, EmberGradientEnd),
                            ),
                        ),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        text = profile.name.firstOrNull()?.uppercase() ?: "?",
                        style = MaterialTheme.typography.headlineMedium,
                        color = MaterialTheme.colorScheme.onPrimary,
                        fontWeight = FontWeight.Bold,
                    )
                }
            }

            // Upload indicator
            if (isUploadingAvatar) {
                Box(
                    modifier = Modifier
                        .size(80.dp)
                        .clip(CircleShape)
                        .background(MaterialTheme.colorScheme.surface.copy(alpha = 0.7f)),
                    contentAlignment = Alignment.Center,
                ) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(24.dp),
                        color = MaterialTheme.colorScheme.primary,
                        strokeWidth = 2.dp,
                    )
                }
            }

            // Camera icon overlay
            if (!isUploadingAvatar) {
                Box(
                    modifier = Modifier.align(Alignment.BottomEnd),
                ) {
                    Box(
                        modifier = Modifier
                            .size(24.dp)
                            .clip(CircleShape)
                            .background(EmberSurface2),
                        contentAlignment = Alignment.Center,
                    ) {
                        Icon(
                            imageVector = Icons.Outlined.CameraAlt,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.size(14.dp),
                        )
                    }
                }
            }
        }

        Spacer(Modifier.height(EmberSpacing.sm))

        // Name (editable)
        if (isEditingName) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.Center,
            ) {
                OutlinedTextField(
                    value = editedName,
                    onValueChange = onNameChanged,
                    singleLine = true,
                    textStyle = MaterialTheme.typography.titleMedium.copy(
                        textAlign = TextAlign.Center,
                        color = MaterialTheme.colorScheme.onBackground,
                    ),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = EmberPrimary,
                        unfocusedBorderColor = EmberSurface3,
                        cursorColor = EmberPrimary,
                    ),
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                    keyboardActions = KeyboardActions(onDone = { onSaveName() }),
                    modifier = Modifier.width(200.dp),
                )
                Spacer(Modifier.width(EmberSpacing.xs))
                TextButton(
                    onClick = onSaveName,
                    enabled = !isSaving,
                ) {
                    Text(
                        text = stringResource(R.string.profile_save),
                        color = EmberPrimary,
                    )
                }
                TextButton(onClick = onCancelEditName) {
                    Text(
                        text = stringResource(R.string.profile_cancel),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        } else {
            val nameA11y = stringResource(R.string.profile_name_a11y, profile.name)
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .clickable(onClick = onStartEditName)
                    .semantics { contentDescription = nameA11y },
            ) {
                Text(
                    text = profile.name,
                    style = MaterialTheme.typography.titleLarge,
                    color = MaterialTheme.colorScheme.onBackground,
                    fontWeight = FontWeight.SemiBold,
                )
                Spacer(Modifier.width(EmberSpacing.xxs))
                Icon(
                    imageVector = Icons.Outlined.Edit,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.size(16.dp),
                )
            }
        }

        Spacer(Modifier.height(EmberSpacing.xxs))

        // Email
        Text(
            text = profile.email,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        Spacer(Modifier.height(EmberSpacing.xs))

        // Subscription badge
        val (tierLabel, tierColor) = if (profile.subscriptionTier == "premium") {
            stringResource(R.string.profile_tier_premium) to EmberPrimary
        } else {
            stringResource(R.string.profile_tier_free) to EmberSurface3
        }

        Box(
            modifier = Modifier
                .clip(EmberShapes.chip)
                .background(tierColor)
                .padding(horizontal = EmberSpacing.xs, vertical = EmberSpacing.xxs),
        ) {
            Text(
                text = tierLabel,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onPrimary,
                fontWeight = FontWeight.Medium,
            )
        }
    }
}

// -- Preferences Section --

@Composable
private fun PreferencesSection(
    profile: ProfileData,
    characters: List<ai.ember.app.core.models.Character>,
    notificationPreferences: Map<String, Boolean>,
    onTimezoneClick: () -> Unit,
    onLanguageChanged: (String) -> Unit,
    onNotificationChanged: (String, Boolean) -> Unit,
    modifier: Modifier = Modifier,
) {
    val view = LocalView.current

    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = EmberSpacing.lg),
    ) {
        Text(
            text = stringResource(R.string.profile_preferences_title),
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.onBackground,
            fontWeight = FontWeight.SemiBold,
        )

        Spacer(Modifier.height(EmberSpacing.sm))

        Card(
            shape = EmberShapes.input,
            colors = CardDefaults.cardColors(containerColor = EmberSurface2),
        ) {
            // Timezone row
            val timezoneA11y = stringResource(R.string.profile_timezone_a11y)
            SettingsRow(
                icon = Icons.Outlined.Schedule,
                label = stringResource(R.string.profile_timezone_label),
                value = profile.timezone,
                onClick = {
                    view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                    onTimezoneClick()
                },
                contentDescription = timezoneA11y,
            )

            HorizontalDivider(
                color = EmberSurface3,
                modifier = Modifier.padding(horizontal = EmberSpacing.md),
            )

            // Language row
            val languageLabel = if (profile.preferredLanguage == "tr") {
                stringResource(R.string.profile_language_turkish)
            } else {
                stringResource(R.string.profile_language_english)
            }
            val languageA11y = stringResource(R.string.profile_language_a11y)
            SettingsRow(
                icon = Icons.Outlined.Language,
                label = stringResource(R.string.profile_language_label),
                value = languageLabel,
                onClick = {
                    view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                    val newLang = if (profile.preferredLanguage == "en") "tr" else "en"
                    onLanguageChanged(newLang)
                },
                contentDescription = languageA11y,
            )
        }

        Spacer(Modifier.height(EmberSpacing.md))

        // Notifications sub-section
        Text(
            text = stringResource(R.string.profile_notifications_title),
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.onBackground,
            fontWeight = FontWeight.SemiBold,
        )

        Spacer(Modifier.height(EmberSpacing.sm))

        Card(
            shape = EmberShapes.input,
            colors = CardDefaults.cardColors(containerColor = EmberSurface2),
        ) {
            NotificationToggleRow(
                label = stringResource(R.string.profile_notif_morning),
                checked = notificationPreferences["morning_checkin"] ?: true,
                onCheckedChange = { checked ->
                    view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                    onNotificationChanged("morning_checkin", checked)
                },
            )

            HorizontalDivider(
                color = EmberSurface3,
                modifier = Modifier.padding(horizontal = EmberSpacing.md),
            )

            NotificationToggleRow(
                label = stringResource(R.string.profile_notif_evening),
                checked = notificationPreferences["evening_reflection"] ?: true,
                onCheckedChange = { checked ->
                    view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                    onNotificationChanged("evening_reflection", checked)
                },
            )

            HorizontalDivider(
                color = EmberSurface3,
                modifier = Modifier.padding(horizontal = EmberSpacing.md),
            )

            NotificationToggleRow(
                label = stringResource(R.string.profile_notif_sleep),
                checked = notificationPreferences["sleep_reminder"] ?: true,
                onCheckedChange = { checked ->
                    view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                    onNotificationChanged("sleep_reminder", checked)
                },
            )

            // Per-character notification toggles
            characters.forEach { character ->
                HorizontalDivider(
                    color = EmberSurface3,
                    modifier = Modifier.padding(horizontal = EmberSpacing.md),
                )

                NotificationToggleRow(
                    label = character.name,
                    checked = notificationPreferences[character.id] ?: true,
                    onCheckedChange = { checked ->
                        view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                        onNotificationChanged(character.id, checked)
                    },
                )
            }
        }
    }
}

// -- Account Section --

@Composable
private fun AccountSection(
    onSignOut: () -> Unit,
    onDeleteAccount: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val view = LocalView.current

    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = EmberSpacing.lg),
    ) {
        Text(
            text = stringResource(R.string.profile_account_title),
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.onBackground,
            fontWeight = FontWeight.SemiBold,
        )

        Spacer(Modifier.height(EmberSpacing.sm))

        // Sign Out button
        val signOutA11y = stringResource(R.string.profile_sign_out_a11y)
        Card(
            modifier = Modifier
                .fillMaxWidth()
                .clickable {
                    view.performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
                    onSignOut()
                }
                .semantics { contentDescription = signOutA11y },
            shape = EmberShapes.input,
            colors = CardDefaults.cardColors(containerColor = EmberSurface2),
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(EmberSpacing.md),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(
                    imageVector = Icons.Outlined.Logout,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.onSurface,
                    modifier = Modifier.size(20.dp),
                )
                Spacer(Modifier.width(EmberSpacing.sm))
                Text(
                    text = stringResource(R.string.profile_sign_out),
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.onSurface,
                )
            }
        }

        Spacer(Modifier.height(EmberSpacing.sm))

        // Delete Account button
        val deleteA11y = stringResource(R.string.profile_delete_account_a11y)
        Card(
            modifier = Modifier
                .fillMaxWidth()
                .clickable {
                    view.performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
                    onDeleteAccount()
                }
                .semantics { contentDescription = deleteA11y },
            shape = EmberShapes.input,
            colors = CardDefaults.cardColors(containerColor = EmberSurface2),
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(EmberSpacing.md),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(
                    imageVector = Icons.Outlined.DeleteOutline,
                    contentDescription = null,
                    tint = EmberError,
                    modifier = Modifier.size(20.dp),
                )
                Spacer(Modifier.width(EmberSpacing.sm))
                Text(
                    text = stringResource(R.string.profile_delete_account),
                    style = MaterialTheme.typography.titleMedium,
                    color = EmberError,
                )
            }
        }
    }
}

// -- Settings Row --

@Composable
private fun SettingsRow(
    icon: ImageVector,
    label: String,
    value: String,
    onClick: () -> Unit,
    contentDescription: String,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(EmberSpacing.md)
            .semantics { this.contentDescription = contentDescription },
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            imageVector = icon,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.size(20.dp),
        )
        Spacer(Modifier.width(EmberSpacing.sm))
        Text(
            text = label,
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurface,
            modifier = Modifier.weight(1f),
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f),
            textAlign = TextAlign.End,
        )
        Spacer(Modifier.width(EmberSpacing.xxs))
        Icon(
            imageVector = Icons.Outlined.ChevronRight,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.size(20.dp),
        )
    }
}

// -- Notification Toggle Row --

@Composable
private fun NotificationToggleRow(
    label: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(
                horizontal = EmberSpacing.md,
                vertical = EmberSpacing.sm,
            ),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurface,
            modifier = Modifier.weight(1f),
        )
        Switch(
            checked = checked,
            onCheckedChange = onCheckedChange,
            colors = SwitchDefaults.colors(
                checkedThumbColor = MaterialTheme.colorScheme.onPrimary,
                checkedTrackColor = EmberPrimary,
                uncheckedThumbColor = MaterialTheme.colorScheme.onSurfaceVariant,
                uncheckedTrackColor = EmberSurface3,
            ),
        )
    }
}

// -- Delete Confirmation Dialog --

@Composable
private fun DeleteConfirmationDialog(
    confirmationText: String,
    isSaving: Boolean,
    onConfirmationTextChanged: (String) -> Unit,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit,
) {
    val view = LocalView.current
    val isDeleteEnabled = confirmationText == ProfileViewModel.REQUIRED_DELETE_CONFIRMATION

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Text(text = stringResource(R.string.profile_delete_dialog_title))
        },
        text = {
            Column {
                Text(
                    text = stringResource(R.string.profile_delete_dialog_message),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(EmberSpacing.md))
                OutlinedTextField(
                    value = confirmationText,
                    onValueChange = onConfirmationTextChanged,
                    singleLine = true,
                    placeholder = {
                        Text(
                            text = stringResource(R.string.profile_delete_dialog_hint),
                            style = MaterialTheme.typography.bodyMedium,
                        )
                    },
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = EmberError,
                        unfocusedBorderColor = EmberSurface3,
                        cursorColor = EmberError,
                    ),
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    view.performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
                    onConfirm()
                },
                enabled = isDeleteEnabled && !isSaving,
            ) {
                if (isSaving) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(16.dp),
                        color = EmberError,
                        strokeWidth = 2.dp,
                    )
                } else {
                    Text(
                        text = stringResource(R.string.profile_delete_confirm),
                        color = if (isDeleteEnabled) EmberError else MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text(
                    text = stringResource(R.string.profile_delete_cancel),
                )
            }
        },
        containerColor = EmberSurface2,
    )
}

// -- Loading State --

@Composable
private fun LoadingState(
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        CircularProgressIndicator(
            color = MaterialTheme.colorScheme.primary,
        )
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
                text = stringResource(R.string.profile_retry),
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.onPrimary,
            )
        }
    }
}
