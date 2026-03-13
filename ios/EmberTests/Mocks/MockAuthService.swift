import Foundation
@testable import Ember

/// Mock implementation of `AuthServiceProtocol` for testing.
/// Allows tests to control token values, auth behavior, and inspect call arguments.
final class MockAuthService: AuthServiceProtocol, @unchecked Sendable {
    // MARK: - Token Control

    var accessToken: String = "mock-access-token"
    var refreshedToken: String = "mock-refreshed-token"
    var shouldThrowOnRefresh: Bool = false
    var shouldThrowOnGetToken: Bool = false

    // MARK: - Sign In Control

    var shouldThrowOnSignIn: Error?
    var signInCallCount: Int = 0
    var lastSignInEmail: String?
    var lastSignInPassword: String?

    // MARK: - Sign Up Control

    var shouldThrowOnSignUp: Error?
    var signUpCallCount: Int = 0
    var lastSignUpEmail: String?
    var lastSignUpPassword: String?
    var lastSignUpName: String?

    // MARK: - General

    var refreshCallCount: Int = 0
    var getAccessTokenCallCount: Int = 0
    var signOutCallCount: Int = 0
    var isAuthenticated: Bool = false

    // MARK: - AuthServiceProtocol

    func configure() {
        // No-op for tests
    }

    func signIn(username: String, password: String) async throws {
        signInCallCount += 1
        lastSignInEmail = username
        lastSignInPassword = password

        if let error = shouldThrowOnSignIn {
            throw error
        }

        isAuthenticated = true
    }

    func signUp(email: String, password: String, name: String) async throws {
        signUpCallCount += 1
        lastSignUpEmail = email
        lastSignUpPassword = password
        lastSignUpName = name

        if let error = shouldThrowOnSignUp {
            throw error
        }

        isAuthenticated = true
    }

    func signOut() async {
        signOutCallCount += 1
        isAuthenticated = false
    }

    func getAccessToken() async throws -> String {
        getAccessTokenCallCount += 1
        if shouldThrowOnGetToken {
            throw AuthError.tokenUnavailable
        }
        return accessToken
    }

    func refreshToken() async throws -> String {
        refreshCallCount += 1
        if shouldThrowOnRefresh {
            throw AuthError.tokenUnavailable
        }
        return refreshedToken
    }
}
