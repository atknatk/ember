import Observation
import Foundation

@Observable
final class AuthViewModel {
    // MARK: - Form State

    var email: String = ""
    var password: String = ""
    var name: String = ""
    var confirmPassword: String = ""

    // MARK: - UI State

    var isLoading: Bool = false
    var errorMessage: String? = nil
    var isShowingSignUp: Bool = false
    var isAuthenticated: Bool = false

    // MARK: - Computed Validation

    var isSignInFormValid: Bool {
        !email.trimmingCharacters(in: .whitespaces).isEmpty
            && email.contains("@")
            && !password.isEmpty
    }

    var isSignUpFormValid: Bool {
        !email.trimmingCharacters(in: .whitespaces).isEmpty
            && email.contains("@")
            && password.count >= 8
            && confirmPassword == password
            && !name.trimmingCharacters(in: .whitespaces).isEmpty
    }

    var passwordsDoNotMatch: Bool {
        !confirmPassword.isEmpty && confirmPassword != password
    }

    // MARK: - Dependencies

    private let authService: AuthServiceProtocol

    init(authService: AuthServiceProtocol = AuthService.shared) {
        self.authService = authService
        self.isAuthenticated = authService.isAuthenticated
    }

    // MARK: - Actions

    func signIn() async {
        isLoading = true
        errorMessage = nil

        let trimmedEmail = email.lowercased().trimmingCharacters(in: .whitespaces)

        do {
            try await authService.signIn(username: trimmedEmail, password: password)
            isAuthenticated = true
            HapticManager.notification(.success)
        } catch {
            errorMessage = error.localizedDescription
            HapticManager.notification(.error)
        }

        isLoading = false
    }

    func signUp() async {
        isLoading = true
        errorMessage = nil

        let trimmedEmail = email.lowercased().trimmingCharacters(in: .whitespaces)
        let trimmedName = name.trimmingCharacters(in: .whitespaces)

        do {
            try await authService.signUp(
                email: trimmedEmail,
                password: password,
                name: trimmedName
            )
            isAuthenticated = true
            HapticManager.notification(.success)
        } catch {
            errorMessage = error.localizedDescription
            HapticManager.notification(.error)
        }

        isLoading = false
    }

    func signOut() async {
        await authService.signOut()
        isAuthenticated = false
        // Reset form state
        email = ""
        password = ""
        name = ""
        confirmPassword = ""
        errorMessage = nil
        isShowingSignUp = false
    }

    func clearError() {
        errorMessage = nil
    }
}
