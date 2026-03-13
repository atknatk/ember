package ai.ember.app.features.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import ai.ember.app.core.auth.AuthRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * ViewModel for Login and Sign Up screens.
 *
 * Manages form state (email, password, name, confirmPassword),
 * validation, and authentication requests via [AuthRepository].
 *
 * Mirrors iOS AuthViewModel behavior including form validation rules.
 */
@HiltViewModel
class AuthViewModel @Inject constructor(
    private val authRepository: AuthRepository,
) : ViewModel() {

    // -- UI State --

    private val _uiState = MutableStateFlow<AuthUiState>(AuthUiState.Idle)
    val uiState: StateFlow<AuthUiState> = _uiState.asStateFlow()

    // -- Form Fields --

    private val _email = MutableStateFlow("")
    val email: StateFlow<String> = _email.asStateFlow()

    private val _password = MutableStateFlow("")
    val password: StateFlow<String> = _password.asStateFlow()

    private val _name = MutableStateFlow("")
    val name: StateFlow<String> = _name.asStateFlow()

    private val _confirmPassword = MutableStateFlow("")
    val confirmPassword: StateFlow<String> = _confirmPassword.asStateFlow()

    private val _isShowingSignUp = MutableStateFlow(false)
    val isShowingSignUp: StateFlow<Boolean> = _isShowingSignUp.asStateFlow()

    private val _emailHasBeenEdited = MutableStateFlow(false)
    val emailHasBeenEdited: StateFlow<Boolean> = _emailHasBeenEdited.asStateFlow()

    // -- Auth check --

    /** Returns true if stored tokens exist. */
    val isAuthenticated: Boolean
        get() = authRepository.isAuthenticated

    /** Returns true if onboarding has been completed. */
    val hasCompletedOnboarding: Boolean
        get() = authRepository.hasCompletedOnboarding

    /** Marks onboarding as completed (called after successful onboarding). */
    fun setOnboardingCompleted() {
        authRepository.setOnboardingCompleted()
    }

    // -- Form Updates --

    fun onEmailChanged(value: String) {
        _email.value = value
    }

    fun onPasswordChanged(value: String) {
        _password.value = value
    }

    fun onNameChanged(value: String) {
        _name.value = value
    }

    fun onConfirmPasswordChanged(value: String) {
        _confirmPassword.value = value
    }

    fun onEmailEditCompleted() {
        _emailHasBeenEdited.value = true
    }

    fun showSignUp() {
        _isShowingSignUp.value = true
        clearError()
    }

    fun showLogin() {
        _isShowingSignUp.value = false
        clearError()
    }

    fun clearError() {
        if (_uiState.value is AuthUiState.Error) {
            _uiState.value = AuthUiState.Idle
        }
    }

    // -- Validation --

    /** Returns true if the sign-in form has valid input. */
    fun isSignInFormValid(): Boolean {
        val trimmedEmail = _email.value.trim()
        return trimmedEmail.isNotEmpty() &&
            trimmedEmail.contains("@") &&
            _password.value.isNotEmpty()
    }

    /** Returns true if the sign-up form has valid input. */
    fun isSignUpFormValid(): Boolean {
        val trimmedEmail = _email.value.trim()
        return trimmedEmail.isNotEmpty() &&
            trimmedEmail.contains("@") &&
            _password.value.length >= MIN_PASSWORD_LENGTH &&
            _confirmPassword.value == _password.value &&
            _name.value.trim().isNotEmpty()
    }

    /** Returns true if confirm password is non-empty and does not match password. */
    fun passwordsDoNotMatch(): Boolean =
        _confirmPassword.value.isNotEmpty() && _confirmPassword.value != _password.value

    /** Returns true if the email field has been edited and does not contain @. */
    fun showEmailValidationError(): Boolean =
        _emailHasBeenEdited.value && _email.value.isNotEmpty() && !_email.value.contains("@")

    // -- Actions --

    fun signIn() {
        if (!isSignInFormValid()) return
        viewModelScope.launch {
            _uiState.value = AuthUiState.Loading
            val trimmedEmail = _email.value.lowercase().trim()
            authRepository.signIn(trimmedEmail, _password.value)
                .onSuccess {
                    _uiState.value = AuthUiState.Success
                }
                .onFailure { e ->
                    _uiState.value = AuthUiState.Error(
                        e.message ?: "Something went wrong. Please try again.",
                    )
                }
        }
    }

    fun signUp() {
        if (!isSignUpFormValid()) return
        viewModelScope.launch {
            _uiState.value = AuthUiState.Loading
            val trimmedEmail = _email.value.lowercase().trim()
            val trimmedName = _name.value.trim()
            authRepository.signUp(trimmedEmail, _password.value, trimmedName)
                .onSuccess {
                    _uiState.value = AuthUiState.Success
                }
                .onFailure { e ->
                    _uiState.value = AuthUiState.Error(
                        e.message ?: "Something went wrong. Please try again.",
                    )
                }
        }
    }

    fun signOut() {
        authRepository.signOut()
        _email.value = ""
        _password.value = ""
        _name.value = ""
        _confirmPassword.value = ""
        _isShowingSignUp.value = false
        _emailHasBeenEdited.value = false
        _uiState.value = AuthUiState.Idle
    }

    companion object {
        const val MIN_PASSWORD_LENGTH = 8
    }
}
