package ai.ember.app.features.auth

import ai.ember.app.core.auth.AuthException
import ai.ember.app.core.auth.AuthRepository
import ai.ember.app.core.models.AuthResponse
import ai.ember.app.core.models.UserResponse
import app.cash.turbine.test
import io.mockk.coEvery
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Before
import org.junit.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertTrue

@OptIn(ExperimentalCoroutinesApi::class)
class AuthViewModelTest {

    private val testDispatcher = UnconfinedTestDispatcher()
    private lateinit var authRepository: AuthRepository
    private lateinit var viewModel: AuthViewModel

    private val fakeAuthResponse = AuthResponse(
        token = "access-token",
        refreshToken = "refresh-token",
        user = UserResponse(
            id = "user-1",
            email = "test@example.com",
            name = "Test User",
        ),
    )

    @Before
    fun setUp() {
        Dispatchers.setMain(testDispatcher)
        authRepository = mockk(relaxed = true)
        every { authRepository.isAuthenticated } returns false
        viewModel = AuthViewModel(authRepository)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    // -- Initial State --

    @Test
    fun `initial state is Idle`() = runTest {
        viewModel.uiState.test {
            assertIs<AuthUiState.Idle>(awaitItem())
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `initial form fields are empty`() = runTest {
        assertEquals("", viewModel.email.value)
        assertEquals("", viewModel.password.value)
        assertEquals("", viewModel.name.value)
        assertEquals("", viewModel.confirmPassword.value)
        assertFalse(viewModel.isShowingSignUp.value)
    }

    // -- Form Validation --

    @Test
    fun `sign in form valid with email containing @ and non-empty password`() {
        viewModel.onEmailChanged("user@test.com")
        viewModel.onPasswordChanged("password")
        assertTrue(viewModel.isSignInFormValid())
    }

    @Test
    fun `sign in form invalid with empty email`() {
        viewModel.onEmailChanged("")
        viewModel.onPasswordChanged("password")
        assertFalse(viewModel.isSignInFormValid())
    }

    @Test
    fun `sign in form invalid with email missing @`() {
        viewModel.onEmailChanged("invalid-email")
        viewModel.onPasswordChanged("password")
        assertFalse(viewModel.isSignInFormValid())
    }

    @Test
    fun `sign in form invalid with empty password`() {
        viewModel.onEmailChanged("user@test.com")
        viewModel.onPasswordChanged("")
        assertFalse(viewModel.isSignInFormValid())
    }

    @Test
    fun `sign up form valid with all fields correct`() {
        viewModel.onNameChanged("Test User")
        viewModel.onEmailChanged("user@test.com")
        viewModel.onPasswordChanged("password123")
        viewModel.onConfirmPasswordChanged("password123")
        assertTrue(viewModel.isSignUpFormValid())
    }

    @Test
    fun `sign up form invalid when password too short`() {
        viewModel.onNameChanged("Test User")
        viewModel.onEmailChanged("user@test.com")
        viewModel.onPasswordChanged("short")
        viewModel.onConfirmPasswordChanged("short")
        assertFalse(viewModel.isSignUpFormValid())
    }

    @Test
    fun `sign up form invalid when passwords do not match`() {
        viewModel.onNameChanged("Test User")
        viewModel.onEmailChanged("user@test.com")
        viewModel.onPasswordChanged("password123")
        viewModel.onConfirmPasswordChanged("different")
        assertFalse(viewModel.isSignUpFormValid())
    }

    @Test
    fun `sign up form invalid when name is empty`() {
        viewModel.onNameChanged("   ")
        viewModel.onEmailChanged("user@test.com")
        viewModel.onPasswordChanged("password123")
        viewModel.onConfirmPasswordChanged("password123")
        assertFalse(viewModel.isSignUpFormValid())
    }

    @Test
    fun `passwordsDoNotMatch returns true when mismatch`() {
        viewModel.onPasswordChanged("password123")
        viewModel.onConfirmPasswordChanged("different")
        assertTrue(viewModel.passwordsDoNotMatch())
    }

    @Test
    fun `passwordsDoNotMatch returns false when empty confirm`() {
        viewModel.onPasswordChanged("password123")
        viewModel.onConfirmPasswordChanged("")
        assertFalse(viewModel.passwordsDoNotMatch())
    }

    @Test
    fun `showEmailValidationError returns true after edit with invalid email`() {
        viewModel.onEmailChanged("invalid")
        viewModel.onEmailEditCompleted()
        assertTrue(viewModel.showEmailValidationError())
    }

    @Test
    fun `showEmailValidationError returns false before edit`() {
        viewModel.onEmailChanged("invalid")
        assertFalse(viewModel.showEmailValidationError())
    }

    // -- Sign In --

    @Test
    fun `signIn emits Success on repository success`() = runTest {
        coEvery { authRepository.signIn(any(), any()) } returns Result.success(fakeAuthResponse)

        viewModel.onEmailChanged("user@test.com")
        viewModel.onPasswordChanged("password123")

        viewModel.uiState.test {
            assertIs<AuthUiState.Idle>(awaitItem())
            viewModel.signIn()
            assertIs<AuthUiState.Loading>(awaitItem())
            assertIs<AuthUiState.Success>(awaitItem())
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `signIn emits Error on repository failure`() = runTest {
        coEvery { authRepository.signIn(any(), any()) } returns
            Result.failure(AuthException("Invalid email or password"))

        viewModel.onEmailChanged("user@test.com")
        viewModel.onPasswordChanged("wrong")

        viewModel.uiState.test {
            assertIs<AuthUiState.Idle>(awaitItem())
            viewModel.signIn()
            assertIs<AuthUiState.Loading>(awaitItem())
            val error = awaitItem()
            assertIs<AuthUiState.Error>(error)
            assertEquals("Invalid email or password", error.message)
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `signIn trims and lowercases email`() = runTest {
        coEvery { authRepository.signIn(any(), any()) } returns Result.success(fakeAuthResponse)

        viewModel.onEmailChanged("  User@Test.COM  ")
        viewModel.onPasswordChanged("password")
        viewModel.signIn()

        io.mockk.coVerify { authRepository.signIn("user@test.com", "password") }
    }

    @Test
    fun `signIn does nothing when form is invalid`() = runTest {
        viewModel.onEmailChanged("")
        viewModel.onPasswordChanged("")

        viewModel.uiState.test {
            assertIs<AuthUiState.Idle>(awaitItem())
            viewModel.signIn()
            // Should remain idle — no Loading emitted
            expectNoEvents()
            cancelAndIgnoreRemainingEvents()
        }
    }

    // -- Sign Up --

    @Test
    fun `signUp emits Success on repository success`() = runTest {
        coEvery { authRepository.signUp(any(), any(), any()) } returns
            Result.success(fakeAuthResponse)

        viewModel.onNameChanged("Test User")
        viewModel.onEmailChanged("user@test.com")
        viewModel.onPasswordChanged("password123")
        viewModel.onConfirmPasswordChanged("password123")

        viewModel.uiState.test {
            assertIs<AuthUiState.Idle>(awaitItem())
            viewModel.signUp()
            assertIs<AuthUiState.Loading>(awaitItem())
            assertIs<AuthUiState.Success>(awaitItem())
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `signUp emits Error on repository failure`() = runTest {
        coEvery { authRepository.signUp(any(), any(), any()) } returns
            Result.failure(AuthException("An account with this email already exists"))

        viewModel.onNameChanged("Test User")
        viewModel.onEmailChanged("user@test.com")
        viewModel.onPasswordChanged("password123")
        viewModel.onConfirmPasswordChanged("password123")

        viewModel.uiState.test {
            assertIs<AuthUiState.Idle>(awaitItem())
            viewModel.signUp()
            assertIs<AuthUiState.Loading>(awaitItem())
            val error = awaitItem()
            assertIs<AuthUiState.Error>(error)
            assertEquals("An account with this email already exists", error.message)
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `signUp trims name and lowercases email`() = runTest {
        coEvery { authRepository.signUp(any(), any(), any()) } returns
            Result.success(fakeAuthResponse)

        viewModel.onNameChanged("  Test User  ")
        viewModel.onEmailChanged("  USER@test.COM  ")
        viewModel.onPasswordChanged("password123")
        viewModel.onConfirmPasswordChanged("password123")
        viewModel.signUp()

        io.mockk.coVerify { authRepository.signUp("user@test.com", "password123", "Test User") }
    }

    // -- Sign Out --

    @Test
    fun `signOut clears form and resets state to Idle`() = runTest {
        viewModel.onEmailChanged("user@test.com")
        viewModel.onPasswordChanged("password")
        viewModel.onNameChanged("Name")
        viewModel.showSignUp()

        viewModel.signOut()

        assertEquals("", viewModel.email.value)
        assertEquals("", viewModel.password.value)
        assertEquals("", viewModel.name.value)
        assertEquals("", viewModel.confirmPassword.value)
        assertFalse(viewModel.isShowingSignUp.value)
        assertIs<AuthUiState.Idle>(viewModel.uiState.value)
        verify { authRepository.signOut() }
    }

    // -- Navigation --

    @Test
    fun `showSignUp sets isShowingSignUp to true`() {
        viewModel.showSignUp()
        assertTrue(viewModel.isShowingSignUp.value)
    }

    @Test
    fun `showLogin sets isShowingSignUp to false`() {
        viewModel.showSignUp()
        viewModel.showLogin()
        assertFalse(viewModel.isShowingSignUp.value)
    }

    // -- Error Clearing --

    @Test
    fun `clearError resets Error state to Idle`() = runTest {
        coEvery { authRepository.signIn(any(), any()) } returns
            Result.failure(AuthException("error"))

        viewModel.onEmailChanged("user@test.com")
        viewModel.onPasswordChanged("pass")
        viewModel.signIn()

        assertIs<AuthUiState.Error>(viewModel.uiState.value)
        viewModel.clearError()
        assertIs<AuthUiState.Idle>(viewModel.uiState.value)
    }

    @Test
    fun `clearError does nothing when not in Error state`() = runTest {
        assertIs<AuthUiState.Idle>(viewModel.uiState.value)
        viewModel.clearError()
        assertIs<AuthUiState.Idle>(viewModel.uiState.value)
    }
}
