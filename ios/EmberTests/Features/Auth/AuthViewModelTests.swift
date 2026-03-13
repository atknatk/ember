import Testing
import Foundation
@testable import Ember

@Suite("AuthViewModel")
struct AuthViewModelTests {

    // MARK: - Helpers

    private func makeViewModel(isAuthenticated: Bool = false) -> (AuthViewModel, MockAuthService) {
        let mockAuth = MockAuthService()
        mockAuth.isAuthenticated = isAuthenticated
        let vm = AuthViewModel(authService: mockAuth)
        return (vm, mockAuth)
    }

    // MARK: - signIn Tests

    @Test("signIn success sets isAuthenticated true and clears error")
    func signInSuccess() async {
        let (vm, _) = makeViewModel()
        vm.email = "test@ember.ai"
        vm.password = "password123"

        await vm.signIn()

        #expect(vm.isAuthenticated == true)
        #expect(vm.isLoading == false)
        #expect(vm.errorMessage == nil)
    }

    @Test("signIn failure sets errorMessage and keeps isAuthenticated false")
    func signInFailure() async {
        let (vm, mockAuth) = makeViewModel()
        mockAuth.shouldThrowOnSignIn = AuthError.signInFailed("Invalid email or password")
        vm.email = "test@ember.ai"
        vm.password = "wrong"

        await vm.signIn()

        #expect(vm.isAuthenticated == false)
        #expect(vm.isLoading == false)
        #expect(vm.errorMessage == "Invalid email or password")
    }

    @Test("signIn trims and lowercases email")
    func signInTrimsEmail() async {
        let (vm, mockAuth) = makeViewModel()
        vm.email = "  Test@Ember.AI  "
        vm.password = "password123"

        await vm.signIn()

        #expect(mockAuth.lastSignInEmail == "test@ember.ai")
    }

    // MARK: - signUp Tests

    @Test("signUp success sets isAuthenticated true and clears error")
    func signUpSuccess() async {
        let (vm, _) = makeViewModel()
        vm.name = "Test User"
        vm.email = "test@ember.ai"
        vm.password = "password123"
        vm.confirmPassword = "password123"

        await vm.signUp()

        #expect(vm.isAuthenticated == true)
        #expect(vm.isLoading == false)
        #expect(vm.errorMessage == nil)
    }

    @Test("signUp failure sets errorMessage")
    func signUpFailure() async {
        let (vm, mockAuth) = makeViewModel()
        mockAuth.shouldThrowOnSignUp = AuthError.signUpFailed("An account with this email already exists")
        vm.name = "Test User"
        vm.email = "existing@ember.ai"
        vm.password = "password123"
        vm.confirmPassword = "password123"

        await vm.signUp()

        #expect(vm.isAuthenticated == false)
        #expect(vm.isLoading == false)
        #expect(vm.errorMessage == "An account with this email already exists")
    }

    @Test("signUp trims email and name")
    func signUpTrimsInputs() async {
        let (vm, mockAuth) = makeViewModel()
        vm.name = "  Test User  "
        vm.email = "  Test@Ember.AI  "
        vm.password = "password123"
        vm.confirmPassword = "password123"

        await vm.signUp()

        #expect(mockAuth.lastSignUpEmail == "test@ember.ai")
        #expect(mockAuth.lastSignUpName == "Test User")
    }

    // MARK: - Form Validation Tests

    @Test("isSignInFormValid with valid email and password")
    func signInFormValidTrue() {
        let (vm, _) = makeViewModel()
        vm.email = "test@ember.ai"
        vm.password = "password123"
        #expect(vm.isSignInFormValid == true)
    }

    @Test("isSignInFormValid with empty email")
    func signInFormInvalidEmptyEmail() {
        let (vm, _) = makeViewModel()
        vm.email = ""
        vm.password = "password123"
        #expect(vm.isSignInFormValid == false)
    }

    @Test("isSignInFormValid with email missing @")
    func signInFormInvalidNoAt() {
        let (vm, _) = makeViewModel()
        vm.email = "testember.ai"
        vm.password = "password123"
        #expect(vm.isSignInFormValid == false)
    }

    @Test("isSignInFormValid with empty password")
    func signInFormInvalidEmptyPassword() {
        let (vm, _) = makeViewModel()
        vm.email = "test@ember.ai"
        vm.password = ""
        #expect(vm.isSignInFormValid == false)
    }

    @Test("isSignUpFormValid with valid inputs")
    func signUpFormValidTrue() {
        let (vm, _) = makeViewModel()
        vm.name = "Test User"
        vm.email = "test@ember.ai"
        vm.password = "password123"
        vm.confirmPassword = "password123"
        #expect(vm.isSignUpFormValid == true)
    }

    @Test("isSignUpFormValid with short password")
    func signUpFormInvalidShortPassword() {
        let (vm, _) = makeViewModel()
        vm.name = "Test User"
        vm.email = "test@ember.ai"
        vm.password = "short"
        vm.confirmPassword = "short"
        #expect(vm.isSignUpFormValid == false)
    }

    @Test("isSignUpFormValid with mismatched passwords")
    func signUpFormInvalidMismatch() {
        let (vm, _) = makeViewModel()
        vm.name = "Test User"
        vm.email = "test@ember.ai"
        vm.password = "password123"
        vm.confirmPassword = "different123"
        #expect(vm.isSignUpFormValid == false)
    }

    @Test("isSignUpFormValid with empty name")
    func signUpFormInvalidEmptyName() {
        let (vm, _) = makeViewModel()
        vm.name = ""
        vm.email = "test@ember.ai"
        vm.password = "password123"
        vm.confirmPassword = "password123"
        #expect(vm.isSignUpFormValid == false)
    }

    @Test("isSignUpFormValid with whitespace-only name")
    func signUpFormInvalidWhitespaceName() {
        let (vm, _) = makeViewModel()
        vm.name = "   "
        vm.email = "test@ember.ai"
        vm.password = "password123"
        vm.confirmPassword = "password123"
        #expect(vm.isSignUpFormValid == false)
    }

    // MARK: - passwordsDoNotMatch Tests

    @Test("passwordsDoNotMatch when confirm is non-empty and different")
    func passwordsDoNotMatchTrue() {
        let (vm, _) = makeViewModel()
        vm.password = "password123"
        vm.confirmPassword = "different"
        #expect(vm.passwordsDoNotMatch == true)
    }

    @Test("passwordsDoNotMatch when confirm is empty")
    func passwordsDoNotMatchEmpty() {
        let (vm, _) = makeViewModel()
        vm.password = "password123"
        vm.confirmPassword = ""
        #expect(vm.passwordsDoNotMatch == false)
    }

    // MARK: - clearError Tests

    @Test("clearError resets errorMessage to nil")
    func clearError() {
        let (vm, _) = makeViewModel()
        vm.errorMessage = "Some error"
        vm.clearError()
        #expect(vm.errorMessage == nil)
    }

    // MARK: - signOut Tests

    @Test("signOut clears isAuthenticated and resets form state")
    func signOut() async {
        let (vm, _) = makeViewModel(isAuthenticated: true)
        vm.email = "test@ember.ai"
        vm.password = "pass"
        vm.name = "Test"

        await vm.signOut()

        #expect(vm.isAuthenticated == false)
        #expect(vm.email == "")
        #expect(vm.password == "")
        #expect(vm.name == "")
        #expect(vm.confirmPassword == "")
        #expect(vm.errorMessage == nil)
        #expect(vm.isShowingSignUp == false)
    }

    // MARK: - Initial State Tests

    @Test("initial isAuthenticated matches authService.isAuthenticated")
    func initialStateMatchesService() {
        let mockAuth = MockAuthService()
        mockAuth.isAuthenticated = true
        let vm = AuthViewModel(authService: mockAuth)
        #expect(vm.isAuthenticated == true)

        let mockAuth2 = MockAuthService()
        mockAuth2.isAuthenticated = false
        let vm2 = AuthViewModel(authService: mockAuth2)
        #expect(vm2.isAuthenticated == false)
    }

    // MARK: - P03-05 Error Shake Tests

    @Test("signIn failure sets showErrorShake to true")
    func signInFailureSetsShake() async {
        let (vm, mockAuth) = makeViewModel()
        mockAuth.shouldThrowOnSignIn = AuthError.signInFailed("Invalid credentials")
        vm.email = "test@ember.ai"
        vm.password = "wrong"

        await vm.signIn()

        #expect(vm.showErrorShake == true)
    }

    @Test("signUp failure sets showErrorShake to true")
    func signUpFailureSetsShake() async {
        let (vm, mockAuth) = makeViewModel()
        mockAuth.shouldThrowOnSignUp = AuthError.signUpFailed("Email taken")
        vm.name = "Test"
        vm.email = "test@ember.ai"
        vm.password = "password123"
        vm.confirmPassword = "password123"

        await vm.signUp()

        #expect(vm.showErrorShake == true)
    }

    @Test("signIn success does not set showErrorShake")
    func signInSuccessNoShake() async {
        let (vm, _) = makeViewModel()
        vm.email = "test@ember.ai"
        vm.password = "password123"

        await vm.signIn()

        #expect(vm.showErrorShake == false)
    }

    // MARK: - P03-05 Email Validation Tests

    @Test("showEmailValidationError with edited email missing @ returns true")
    func emailValidationErrorMissingAt() {
        let (vm, _) = makeViewModel()
        vm.emailHasBeenEdited = true
        vm.email = "testember.ai"

        #expect(vm.showEmailValidationError == true)
    }

    @Test("showEmailValidationError with valid email returns false")
    func emailValidationErrorValidEmail() {
        let (vm, _) = makeViewModel()
        vm.emailHasBeenEdited = true
        vm.email = "test@ember.ai"

        #expect(vm.showEmailValidationError == false)
    }

    @Test("showEmailValidationError with unedited email returns false")
    func emailValidationErrorUnedited() {
        let (vm, _) = makeViewModel()
        vm.emailHasBeenEdited = false
        vm.email = "testember.ai"

        #expect(vm.showEmailValidationError == false)
    }

    @Test("showEmailValidationError with empty email after editing returns false")
    func emailValidationErrorEmptyAfterEdit() {
        let (vm, _) = makeViewModel()
        vm.emailHasBeenEdited = true
        vm.email = ""

        #expect(vm.showEmailValidationError == false)
    }

    // MARK: - P03-05 signOut resets emailHasBeenEdited

    @Test("signOut resets emailHasBeenEdited to false")
    func signOutResetsEmailEdited() async {
        let (vm, _) = makeViewModel(isAuthenticated: true)
        vm.emailHasBeenEdited = true

        await vm.signOut()

        #expect(vm.emailHasBeenEdited == false)
    }
}
