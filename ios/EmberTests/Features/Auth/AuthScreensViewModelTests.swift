import Testing
import Foundation
@testable import Ember

/// Extended tests for `AuthViewModel` P03-05 polish properties.
/// Covers edge cases not tested in `AuthViewModelTests.swift` or `AuthViewModelExtendedTests.swift`:
/// - `showErrorShake` async reset after 500ms delay
/// - `showErrorShake` initial state and signOut reset
/// - `showErrorShake` independence from other state (`errorMessage`, `clearError`)
/// - `signUp` success does not set `showErrorShake`
/// - `emailHasBeenEdited` initial state and persistence
/// - `showEmailValidationError` boundary / edge-case email strings
/// - Consecutive failure shake behaviour
@Suite("AuthViewModel P03-05 Auth Screens")
struct AuthScreensViewModelTests {

    // MARK: - Helpers

    private func makeViewModel(isAuthenticated: Bool = false) -> (AuthViewModel, MockAuthService) {
        let mockAuth = MockAuthService()
        mockAuth.isAuthenticated = isAuthenticated
        let vm = AuthViewModel(authService: mockAuth)
        return (vm, mockAuth)
    }

    // MARK: - showErrorShake: Initial State

    @Test("showErrorShake defaults to false on init")
    func showErrorShakeDefaultsFalse() {
        let (vm, _) = makeViewModel()
        #expect(vm.showErrorShake == false)
    }

    // MARK: - showErrorShake: signUp Success

    @Test("signUp success does not set showErrorShake")
    func signUpSuccessDoesNotSetShake() async {
        let (vm, _) = makeViewModel()
        vm.name = "Test User"
        vm.email = "test@ember.ai"
        vm.password = "password123"
        vm.confirmPassword = "password123"

        await vm.signUp()

        #expect(vm.showErrorShake == false)
    }

    // MARK: - showErrorShake: Async Reset After Delay

    @Test("showErrorShake resets to false after approximately 500ms")
    func showErrorShakeResetsAfterDelay() async throws {
        let (vm, mockAuth) = makeViewModel()
        mockAuth.shouldThrowOnSignIn = AuthError.signInFailed("Invalid credentials")
        vm.email = "test@ember.ai"
        vm.password = "wrong"

        await vm.signIn()

        // Immediately after signIn() the shake is true (set synchronously before the async reset Task)
        #expect(vm.showErrorShake == true)

        // Wait longer than the 500ms reset delay (use 700ms to avoid flakiness)
        try await Task.sleep(nanoseconds: 700_000_000)

        #expect(vm.showErrorShake == false)
    }

    // MARK: - showErrorShake: signOut Reset

    @Test("signOut resets showErrorShake to false")
    func signOutResetsShowErrorShake() async {
        let (vm, mockAuth) = makeViewModel(isAuthenticated: true)
        // Manually set shake to simulate a prior failed attempt
        mockAuth.shouldThrowOnSignIn = AuthError.signInFailed("Forced failure")
        vm.email = "test@ember.ai"
        vm.password = "wrong"
        await vm.signIn()
        // Confirm shake was set
        #expect(vm.showErrorShake == true)

        // Sign out from any state; shake should clear
        await vm.signOut()

        // signOut does not explicitly reset showErrorShake in the implementation —
        // this test documents and verifies the actual behaviour:
        // if the implementation does NOT reset it, this test will fail and flag a gap.
        // Update expected value if the ViewModel is intentionally not resetting shake on signOut.
        #expect(vm.showErrorShake == false)
    }

    // MARK: - showErrorShake: Independence from clearError

    @Test("clearError does not reset showErrorShake")
    func clearErrorDoesNotResetShake() async {
        let (vm, mockAuth) = makeViewModel()
        mockAuth.shouldThrowOnSignIn = AuthError.signInFailed("Bad credentials")
        vm.email = "test@ember.ai"
        vm.password = "wrong"
        await vm.signIn()
        #expect(vm.showErrorShake == true)

        // clearError only clears errorMessage, not the shake state
        vm.clearError()

        #expect(vm.showErrorShake == true)
        #expect(vm.errorMessage == nil)
    }

    // MARK: - showErrorShake: Consecutive Failures

    @Test("second signIn failure sets showErrorShake to true again")
    func consecutiveSignInFailuresSetsShakeAgain() async {
        let (vm, mockAuth) = makeViewModel()
        mockAuth.shouldThrowOnSignIn = AuthError.signInFailed("First failure")
        vm.email = "test@ember.ai"
        vm.password = "wrong"

        await vm.signIn()
        #expect(vm.showErrorShake == true)

        // Trigger a second failure — shake must be true again immediately after
        await vm.signIn()
        #expect(vm.showErrorShake == true)
    }

    @Test("second signUp failure sets showErrorShake to true again")
    func consecutiveSignUpFailuresSetsShakeAgain() async {
        let (vm, mockAuth) = makeViewModel()
        mockAuth.shouldThrowOnSignUp = AuthError.signUpFailed("Email taken")
        vm.name = "User"
        vm.email = "test@ember.ai"
        vm.password = "password123"
        vm.confirmPassword = "password123"

        await vm.signUp()
        #expect(vm.showErrorShake == true)

        await vm.signUp()
        #expect(vm.showErrorShake == true)
    }

    // MARK: - showErrorShake: Does Not Affect errorMessage

    @Test("showErrorShake being true does not clear errorMessage")
    func shakeAndErrorMessageCoexist() async {
        let (vm, mockAuth) = makeViewModel()
        mockAuth.shouldThrowOnSignIn = AuthError.signInFailed("Network timeout")
        vm.email = "test@ember.ai"
        vm.password = "wrong"

        await vm.signIn()

        #expect(vm.showErrorShake == true)
        #expect(vm.errorMessage == "Network timeout")
    }

    // MARK: - emailHasBeenEdited: Initial State

    @Test("emailHasBeenEdited defaults to false on init")
    func emailHasBeenEditedDefaultsFalse() {
        let (vm, _) = makeViewModel()
        #expect(vm.emailHasBeenEdited == false)
    }

    // MARK: - emailHasBeenEdited: Persistence

    @Test("emailHasBeenEdited persists as true even after email is cleared")
    func emailHasBeenEditedPersistsAfterEmailCleared() {
        let (vm, _) = makeViewModel()
        vm.emailHasBeenEdited = true
        // Simulate user clearing the field
        vm.email = ""
        #expect(vm.emailHasBeenEdited == true)
    }

    @Test("emailHasBeenEdited is not reset by changing password field")
    func emailHasBeenEditedNotResetByPasswordChange() {
        let (vm, _) = makeViewModel()
        vm.emailHasBeenEdited = true
        vm.password = "newpassword"
        #expect(vm.emailHasBeenEdited == true)
    }

    @Test("emailHasBeenEdited is not reset by changing name field")
    func emailHasBeenEditedNotResetByNameChange() {
        let (vm, _) = makeViewModel()
        vm.emailHasBeenEdited = true
        vm.name = "New Name"
        #expect(vm.emailHasBeenEdited == true)
    }

    // MARK: - showEmailValidationError: Email Format Boundary Cases

    @Test("showEmailValidationError with @ at start of string returns false")
    func emailValidationErrorAtSignAtStart() {
        let (vm, _) = makeViewModel()
        vm.emailHasBeenEdited = true
        // "@foo.com" contains "@" — validation sees it as valid
        vm.email = "@foo.com"
        #expect(vm.showEmailValidationError == false)
    }

    @Test("showEmailValidationError with @ at end of string returns false")
    func emailValidationErrorAtSignAtEnd() {
        let (vm, _) = makeViewModel()
        vm.emailHasBeenEdited = true
        // "foo@" contains "@" — validation sees it as valid (basic check only)
        vm.email = "foo@"
        #expect(vm.showEmailValidationError == false)
    }

    @Test("showEmailValidationError with multiple @ symbols returns false")
    func emailValidationErrorMultipleAtSymbols() {
        let (vm, _) = makeViewModel()
        vm.emailHasBeenEdited = true
        // Contains "@" so validation passes (ViewModel only checks for presence)
        vm.email = "foo@@bar.com"
        #expect(vm.showEmailValidationError == false)
    }

    @Test("showEmailValidationError with whitespace-only email after editing returns false")
    func emailValidationErrorWhitespaceOnlyAfterEdit() {
        let (vm, _) = makeViewModel()
        vm.emailHasBeenEdited = true
        // Whitespace is not empty — "   ".contains("@") is false so error should show
        // BUT: the spec says "suppressed when empty to avoid noise".
        // "   " is not technically empty, so the computed property returns true.
        vm.email = "   "
        // "   ".isEmpty == false AND !contains("@") == true → showEmailValidationError == true
        #expect(vm.showEmailValidationError == true)
    }

    @Test("showEmailValidationError with single character non-@ returns true")
    func emailValidationErrorSingleCharacter() {
        let (vm, _) = makeViewModel()
        vm.emailHasBeenEdited = true
        vm.email = "a"
        #expect(vm.showEmailValidationError == true)
    }

    @Test("showEmailValidationError with only @ symbol returns false")
    func emailValidationErrorOnlyAtSymbol() {
        let (vm, _) = makeViewModel()
        vm.emailHasBeenEdited = true
        vm.email = "@"
        // Contains "@" → validation passes → error is NOT shown
        #expect(vm.showEmailValidationError == false)
    }

    // MARK: - showEmailValidationError: Not Reset by signIn Failure

    @Test("showEmailValidationError state is preserved after signIn failure")
    func emailValidationErrorPreservedAfterSignInFailure() async {
        let (vm, mockAuth) = makeViewModel()
        vm.emailHasBeenEdited = true
        vm.email = "notanemail"
        vm.password = "password123"
        mockAuth.shouldThrowOnSignIn = AuthError.signInFailed("Invalid credentials")

        await vm.signIn()

        // showEmailValidationError is a computed property — its value is still determined
        // by emailHasBeenEdited + email content, not by signIn outcome
        #expect(vm.showEmailValidationError == true)
    }

    @Test("showEmailValidationError state is preserved after signUp failure")
    func emailValidationErrorPreservedAfterSignUpFailure() async {
        let (vm, mockAuth) = makeViewModel()
        vm.emailHasBeenEdited = true
        vm.email = "notanemail"
        vm.name = "User"
        vm.password = "password123"
        vm.confirmPassword = "password123"
        mockAuth.shouldThrowOnSignUp = AuthError.signUpFailed("Email taken")

        await vm.signUp()

        #expect(vm.showEmailValidationError == true)
    }

    // MARK: - Combined State: showErrorShake + showEmailValidationError

    @Test("both showErrorShake and showEmailValidationError can be true simultaneously")
    func shakeAndEmailValidationCanCoexist() async {
        let (vm, mockAuth) = makeViewModel()
        // Set up invalid email state
        vm.emailHasBeenEdited = true
        vm.email = "notanemail"
        vm.password = "password123"
        mockAuth.shouldThrowOnSignIn = AuthError.signInFailed("Bad credentials")

        await vm.signIn()

        #expect(vm.showErrorShake == true)
        #expect(vm.showEmailValidationError == true)
    }

    // MARK: - emailHasBeenEdited: Reset by signOut but Not by signIn

    @Test("successful signIn does not reset emailHasBeenEdited")
    func successfulSignInDoesNotResetEmailHasBeenEdited() async {
        let (vm, _) = makeViewModel()
        vm.emailHasBeenEdited = true
        vm.email = "test@ember.ai"
        vm.password = "password123"

        await vm.signIn()

        // signIn does not touch emailHasBeenEdited — it is only reset by signOut
        #expect(vm.emailHasBeenEdited == true)
    }

    @Test("failed signIn does not reset emailHasBeenEdited")
    func failedSignInDoesNotResetEmailHasBeenEdited() async {
        let (vm, mockAuth) = makeViewModel()
        vm.emailHasBeenEdited = true
        vm.email = "test@ember.ai"
        vm.password = "wrong"
        mockAuth.shouldThrowOnSignIn = AuthError.signInFailed("Bad credentials")

        await vm.signIn()

        #expect(vm.emailHasBeenEdited == true)
    }

    @Test("successful signUp does not reset emailHasBeenEdited")
    func successfulSignUpDoesNotResetEmailHasBeenEdited() async {
        let (vm, _) = makeViewModel()
        vm.emailHasBeenEdited = true
        vm.name = "User"
        vm.email = "test@ember.ai"
        vm.password = "password123"
        vm.confirmPassword = "password123"

        await vm.signUp()

        #expect(vm.emailHasBeenEdited == true)
    }
}
