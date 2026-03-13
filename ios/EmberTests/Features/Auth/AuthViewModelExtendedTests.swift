import Testing
import Foundation
@testable import Ember

/// Extended tests for `AuthViewModel` — edge cases not covered by `AuthViewModelTests.swift`.
/// Covers: concurrent signIn calls, signOut call tracking, form validation edge cases,
/// email normalization nuances, isShowingSignUp state, and signIn/signUp call isolation.
@Suite("AuthViewModel Extended")
struct AuthViewModelExtendedTests {

    // MARK: - Helpers

    private func makeViewModel(isAuthenticated: Bool = false) -> (AuthViewModel, MockAuthService) {
        let mockAuth = MockAuthService()
        mockAuth.isAuthenticated = isAuthenticated
        let vm = AuthViewModel(authService: mockAuth)
        return (vm, mockAuth)
    }

    // MARK: - Concurrent signIn Guard

    @Test("signIn sets isLoading false after completion regardless of success")
    func signInIsLoadingFalseAfterSuccess() async {
        let (vm, _) = makeViewModel()
        vm.email = "test@ember.ai"
        vm.password = "password123"

        await vm.signIn()

        #expect(vm.isLoading == false)
    }

    @Test("signIn sets isLoading false after failure")
    func signInIsLoadingFalseAfterFailure() async {
        let (vm, mockAuth) = makeViewModel()
        mockAuth.shouldThrowOnSignIn = AuthError.signInFailed("Bad credentials")
        vm.email = "test@ember.ai"
        vm.password = "wrong"

        await vm.signIn()

        #expect(vm.isLoading == false)
    }

    @Test("signUp sets isLoading false after completion regardless of success")
    func signUpIsLoadingFalseAfterSuccess() async {
        let (vm, _) = makeViewModel()
        vm.name = "User"
        vm.email = "test@ember.ai"
        vm.password = "password123"
        vm.confirmPassword = "password123"

        await vm.signUp()

        #expect(vm.isLoading == false)
    }

    @Test("signUp sets isLoading false after failure")
    func signUpIsLoadingFalseAfterFailure() async {
        let (vm, mockAuth) = makeViewModel()
        mockAuth.shouldThrowOnSignUp = AuthError.signUpFailed("Already exists")
        vm.name = "User"
        vm.email = "existing@ember.ai"
        vm.password = "password123"
        vm.confirmPassword = "password123"

        await vm.signUp()

        #expect(vm.isLoading == false)
    }

    // MARK: - signIn Does Not Call signUp and Vice Versa

    @Test("signIn does not call signUp method")
    func signInDoesNotCallSignUp() async {
        let (vm, mockAuth) = makeViewModel()
        vm.email = "test@ember.ai"
        vm.password = "password123"

        await vm.signIn()

        #expect(mockAuth.signUpCallCount == 0)
        #expect(mockAuth.signInCallCount == 1)
    }

    @Test("signUp does not call signIn method")
    func signUpDoesNotCallSignIn() async {
        let (vm, mockAuth) = makeViewModel()
        vm.name = "User"
        vm.email = "test@ember.ai"
        vm.password = "password123"
        vm.confirmPassword = "password123"

        await vm.signUp()

        #expect(mockAuth.signInCallCount == 0)
        #expect(mockAuth.signUpCallCount == 1)
    }

    // MARK: - signOut Call Tracking

    @Test("signOut calls authService.signOut exactly once")
    func signOutCallsServiceOnce() async {
        let (vm, mockAuth) = makeViewModel(isAuthenticated: true)

        await vm.signOut()

        #expect(mockAuth.signOutCallCount == 1)
    }

    @Test("calling signOut twice calls authService.signOut twice")
    func signOutCalledTwiceInvokesServiceTwice() async {
        let (vm, mockAuth) = makeViewModel(isAuthenticated: true)

        await vm.signOut()
        await vm.signOut()

        #expect(mockAuth.signOutCallCount == 2)
        #expect(vm.isAuthenticated == false)
    }

    // MARK: - Email Normalization

    @Test("signIn passes password as-is without trimming")
    func signInDoesNotTrimPassword() async {
        let (vm, mockAuth) = makeViewModel()
        vm.email = "test@ember.ai"
        vm.password = " password with spaces "

        await vm.signIn()

        // Password must NOT be trimmed — only email is normalized
        #expect(mockAuth.lastSignInPassword == " password with spaces ")
    }

    @Test("signUp passes password as-is without trimming")
    func signUpDoesNotTrimPassword() async {
        let (vm, mockAuth) = makeViewModel()
        vm.name = "User"
        vm.email = "test@ember.ai"
        vm.password = " pass123 "
        vm.confirmPassword = " pass123 "

        await vm.signUp()

        #expect(mockAuth.lastSignUpPassword == " pass123 ")
    }

    @Test("signIn lowercases mixed-case email domain")
    func signInLowercasesEmailDomain() async {
        let (vm, mockAuth) = makeViewModel()
        vm.email = "User@EMBER.AI"
        vm.password = "password123"

        await vm.signIn()

        #expect(mockAuth.lastSignInEmail == "user@ember.ai")
    }

    @Test("signUp lowercases mixed-case email")
    func signUpLowercasesEmail() async {
        let (vm, mockAuth) = makeViewModel()
        vm.name = "User"
        vm.email = "USER@EXAMPLE.COM"
        vm.password = "password123"
        vm.confirmPassword = "password123"

        await vm.signUp()

        #expect(mockAuth.lastSignUpEmail == "user@example.com")
    }

    // MARK: - Form Validation Edge Cases

    @Test("isSignInFormValid with whitespace-only email returns false")
    func signInFormInvalidWhitespaceEmail() {
        let (vm, _) = makeViewModel()
        vm.email = "   "
        vm.password = "password123"
        #expect(vm.isSignInFormValid == false)
    }

    @Test("isSignInFormValid with @ at end of string returns true (minimal valid)")
    func signInFormValidAtSymbolPresent() {
        let (vm, _) = makeViewModel()
        vm.email = "a@b"
        vm.password = "password123"
        // The spec says: "contains @" — a@b satisfies this
        #expect(vm.isSignInFormValid == true)
    }

    @Test("isSignUpFormValid with password exactly 8 characters returns true")
    func signUpFormValidExactly8CharPassword() {
        let (vm, _) = makeViewModel()
        vm.name = "User"
        vm.email = "test@ember.ai"
        vm.password = "12345678"
        vm.confirmPassword = "12345678"
        #expect(vm.isSignUpFormValid == true)
    }

    @Test("isSignUpFormValid with password exactly 7 characters returns false")
    func signUpFormInvalid7CharPassword() {
        let (vm, _) = makeViewModel()
        vm.name = "User"
        vm.email = "test@ember.ai"
        vm.password = "1234567"
        vm.confirmPassword = "1234567"
        #expect(vm.isSignUpFormValid == false)
    }

    @Test("isSignUpFormValid with empty confirmPassword returns false")
    func signUpFormInvalidEmptyConfirmPassword() {
        let (vm, _) = makeViewModel()
        vm.name = "User"
        vm.email = "test@ember.ai"
        vm.password = "password123"
        vm.confirmPassword = ""
        // Empty confirmPassword != password ("password123") so form is invalid
        #expect(vm.isSignUpFormValid == false)
    }

    @Test("isSignUpFormValid with missing @ in email returns false")
    func signUpFormInvalidEmailMissingAt() {
        let (vm, _) = makeViewModel()
        vm.name = "User"
        vm.email = "notanemail"
        vm.password = "password123"
        vm.confirmPassword = "password123"
        #expect(vm.isSignUpFormValid == false)
    }

    // MARK: - passwordsDoNotMatch Edge Cases

    @Test("passwordsDoNotMatch is false when both are empty")
    func passwordsDoNotMatchBothEmpty() {
        let (vm, _) = makeViewModel()
        vm.password = ""
        vm.confirmPassword = ""
        // confirmPassword is empty — must return false per spec
        #expect(vm.passwordsDoNotMatch == false)
    }

    @Test("passwordsDoNotMatch is false when both match")
    func passwordsDoNotMatchBothMatch() {
        let (vm, _) = makeViewModel()
        vm.password = "password123"
        vm.confirmPassword = "password123"
        #expect(vm.passwordsDoNotMatch == false)
    }

    @Test("passwordsDoNotMatch is true when confirmPassword has extra trailing space")
    func passwordsDoNotMatchTrailingSpace() {
        let (vm, _) = makeViewModel()
        vm.password = "password123"
        vm.confirmPassword = "password123 "
        #expect(vm.passwordsDoNotMatch == true)
    }

    // MARK: - clearError Multiple Calls

    @Test("calling clearError when errorMessage is already nil is safe")
    func clearErrorWhenAlreadyNilIsSafe() {
        let (vm, _) = makeViewModel()
        vm.errorMessage = nil
        vm.clearError()
        #expect(vm.errorMessage == nil)
    }

    @Test("calling clearError twice leaves errorMessage nil")
    func clearErrorTwiceIsIdempotent() {
        let (vm, _) = makeViewModel()
        vm.errorMessage = "Some error"
        vm.clearError()
        vm.clearError()
        #expect(vm.errorMessage == nil)
    }

    // MARK: - isShowingSignUp State

    @Test("isShowingSignUp defaults to false")
    func isShowingSignUpDefaultsFalse() {
        let (vm, _) = makeViewModel()
        #expect(vm.isShowingSignUp == false)
    }

    @Test("isShowingSignUp can be toggled to true")
    func isShowingSignUpCanBeSetTrue() {
        let (vm, _) = makeViewModel()
        vm.isShowingSignUp = true
        #expect(vm.isShowingSignUp == true)
    }

    @Test("signOut resets isShowingSignUp to false")
    func signOutResetsIsShowingSignUp() async {
        let (vm, _) = makeViewModel(isAuthenticated: true)
        vm.isShowingSignUp = true

        await vm.signOut()

        #expect(vm.isShowingSignUp == false)
    }

    // MARK: - Error Cleared Before Each Attempt

    @Test("signIn clears previous errorMessage before attempting")
    func signInClearsPreviousError() async {
        let (vm, mockAuth) = makeViewModel()
        // First attempt fails
        mockAuth.shouldThrowOnSignIn = AuthError.signInFailed("First failure")
        vm.email = "test@ember.ai"
        vm.password = "wrong"
        await vm.signIn()
        #expect(vm.errorMessage == "First failure")

        // Second attempt succeeds — error must be cleared
        mockAuth.shouldThrowOnSignIn = nil
        await vm.signIn()
        #expect(vm.errorMessage == nil)
        #expect(vm.isAuthenticated == true)
    }

    @Test("signUp clears previous errorMessage before attempting")
    func signUpClearsPreviousError() async {
        let (vm, mockAuth) = makeViewModel()
        // First attempt fails
        mockAuth.shouldThrowOnSignUp = AuthError.signUpFailed("Already taken")
        vm.name = "User"
        vm.email = "test@ember.ai"
        vm.password = "password123"
        vm.confirmPassword = "password123"
        await vm.signUp()
        #expect(vm.errorMessage == "Already taken")

        // Second attempt succeeds
        mockAuth.shouldThrowOnSignUp = nil
        await vm.signUp()
        #expect(vm.errorMessage == nil)
        #expect(vm.isAuthenticated == true)
    }

    // MARK: - Initial State

    @Test("initial form fields are all empty strings")
    func initialFormFieldsAreEmpty() {
        let (vm, _) = makeViewModel()
        #expect(vm.email == "")
        #expect(vm.password == "")
        #expect(vm.name == "")
        #expect(vm.confirmPassword == "")
    }

    @Test("initial isLoading is false")
    func initialIsLoadingFalse() {
        let (vm, _) = makeViewModel()
        #expect(vm.isLoading == false)
    }

    @Test("initial errorMessage is nil")
    func initialErrorMessageNil() {
        let (vm, _) = makeViewModel()
        #expect(vm.errorMessage == nil)
    }
}
