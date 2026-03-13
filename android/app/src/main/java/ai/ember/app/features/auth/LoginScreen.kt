package ai.ember.app.features.auth

import android.view.HapticFeedbackConstants
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusDirection
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import ai.ember.app.R
import ai.ember.app.core.ui.theme.EmberPrimary
import ai.ember.app.core.ui.theme.EmberShapes
import ai.ember.app.core.ui.theme.EmberSpacing
import ai.ember.app.core.ui.theme.EmberSurface2
import ai.ember.app.core.ui.theme.EmberTextDisabled
import ai.ember.app.core.ui.theme.EmberTextSecondary

/**
 * Login screen with email and password fields.
 *
 * Matches iOS LoginView: gradient logo, form validation, error shake,
 * sign-up navigation link, haptic feedback on success/error.
 */
@Composable
fun LoginScreen(
    viewModel: AuthViewModel,
    snackbarHostState: SnackbarHostState,
    modifier: Modifier = Modifier,
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    val email by viewModel.email.collectAsStateWithLifecycle()
    val password by viewModel.password.collectAsStateWithLifecycle()
    val emailHasBeenEdited by viewModel.emailHasBeenEdited.collectAsStateWithLifecycle()

    val isLoading = uiState is AuthUiState.Loading
    val isFormValid = viewModel.isSignInFormValid()
    val showEmailError = viewModel.showEmailValidationError()

    var isPasswordVisible by rememberSaveable { mutableStateOf(false) }
    val focusManager = LocalFocusManager.current
    val view = LocalView.current

    // Show error in snackbar
    LaunchedEffect(uiState) {
        if (uiState is AuthUiState.Error) {
            view.performHapticFeedback(HapticFeedbackConstants.REJECT)
            snackbarHostState.showSnackbar(
                message = (uiState as AuthUiState.Error).message,
            )
            viewModel.clearError()
        }
        if (uiState is AuthUiState.Success) {
            view.performHapticFeedback(HapticFeedbackConstants.CONFIRM)
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = EmberSpacing.lg),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Spacer(modifier = Modifier.height(EmberSpacing.xxxl))

        // Logo
        Icon(
            imageVector = Icons.Filled.AutoAwesome,
            contentDescription = null,
            modifier = Modifier.size(EmberSpacing.xxxl),
            tint = EmberPrimary,
        )

        Spacer(modifier = Modifier.height(EmberSpacing.xl))

        // Title
        Text(
            text = stringResource(R.string.auth_welcome_back),
            style = MaterialTheme.typography.headlineMedium,
            color = MaterialTheme.colorScheme.onBackground,
        )

        Spacer(modifier = Modifier.height(EmberSpacing.xs))

        Text(
            text = stringResource(R.string.auth_sign_in_subtitle),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        Spacer(modifier = Modifier.height(EmberSpacing.xl))

        // Email field
        OutlinedTextField(
            value = email,
            onValueChange = viewModel::onEmailChanged,
            label = { Text(stringResource(R.string.auth_email_label)) },
            singleLine = true,
            keyboardOptions = KeyboardOptions(
                keyboardType = KeyboardType.Email,
                imeAction = ImeAction.Next,
            ),
            keyboardActions = KeyboardActions(
                onNext = { focusManager.moveFocus(FocusDirection.Down) },
            ),
            isError = showEmailError,
            supportingText = if (showEmailError) {
                { Text(stringResource(R.string.auth_email_invalid)) }
            } else {
                null
            },
            colors = authTextFieldColors(),
            shape = EmberShapes.input,
            modifier = Modifier
                .fillMaxWidth()
                .onFocusChanged { focusState ->
                    if (!focusState.isFocused && email.isNotEmpty()) {
                        viewModel.onEmailEditCompleted()
                    }
                },
        )

        Spacer(modifier = Modifier.height(EmberSpacing.md))

        // Password field
        OutlinedTextField(
            value = password,
            onValueChange = viewModel::onPasswordChanged,
            label = { Text(stringResource(R.string.auth_password_label)) },
            singleLine = true,
            visualTransformation = if (isPasswordVisible) {
                VisualTransformation.None
            } else {
                PasswordVisualTransformation()
            },
            keyboardOptions = KeyboardOptions(
                keyboardType = KeyboardType.Password,
                imeAction = ImeAction.Done,
            ),
            keyboardActions = KeyboardActions(
                onDone = {
                    focusManager.clearFocus()
                    if (isFormValid && !isLoading) {
                        viewModel.signIn()
                    }
                },
            ),
            trailingIcon = {
                IconButton(onClick = { isPasswordVisible = !isPasswordVisible }) {
                    Icon(
                        imageVector = if (isPasswordVisible) {
                            Icons.Filled.VisibilityOff
                        } else {
                            Icons.Filled.Visibility
                        },
                        contentDescription = stringResource(R.string.auth_toggle_password_visibility),
                        tint = EmberTextSecondary,
                    )
                }
            },
            colors = authTextFieldColors(),
            shape = EmberShapes.input,
            modifier = Modifier.fillMaxWidth(),
        )

        Spacer(modifier = Modifier.height(EmberSpacing.xl))

        // Sign In button
        Button(
            onClick = {
                focusManager.clearFocus()
                view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                viewModel.signIn()
            },
            enabled = isFormValid && !isLoading,
            shape = EmberShapes.pill,
            colors = ButtonDefaults.buttonColors(
                containerColor = EmberPrimary,
                disabledContainerColor = EmberTextDisabled,
            ),
            modifier = Modifier
                .fillMaxWidth()
                .height(EmberSpacing.xxxl),
        ) {
            if (isLoading) {
                CircularProgressIndicator(
                    color = MaterialTheme.colorScheme.onPrimary,
                    strokeWidth = EmberSpacing.xxs / 2,
                    modifier = Modifier.size(EmberSpacing.xl),
                )
            } else {
                Text(
                    text = stringResource(R.string.auth_sign_in_button),
                    style = MaterialTheme.typography.titleMedium,
                )
            }
        }

        Spacer(modifier = Modifier.height(EmberSpacing.xl))

        // Sign Up link
        TextButton(onClick = { viewModel.showSignUp() }) {
            Text(
                text = stringResource(R.string.auth_no_account),
                style = MaterialTheme.typography.bodyMedium,
                color = EmberTextSecondary,
            )
            Text(
                text = " " + stringResource(R.string.auth_sign_up_link),
                style = MaterialTheme.typography.bodyMedium,
                color = EmberPrimary,
            )
        }

        Spacer(modifier = Modifier.height(EmberSpacing.xxl))
    }
}

/**
 * Shared text field colors for auth screens matching the Ember design system.
 */
@Composable
internal fun authTextFieldColors() = OutlinedTextFieldDefaults.colors(
    unfocusedContainerColor = EmberSurface2,
    focusedContainerColor = EmberSurface2,
    unfocusedBorderColor = EmberSurface2,
    focusedBorderColor = EmberPrimary,
    unfocusedLabelColor = EmberTextSecondary,
    focusedLabelColor = EmberPrimary,
    cursorColor = EmberPrimary,
    errorBorderColor = MaterialTheme.colorScheme.error,
    errorLabelColor = MaterialTheme.colorScheme.error,
)
