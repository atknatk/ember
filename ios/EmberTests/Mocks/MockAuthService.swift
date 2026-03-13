import Foundation
@testable import Ember

/// Mock implementation of `AuthServiceProtocol` for testing.
/// Allows tests to control token values and refresh behavior.
final class MockAuthService: AuthServiceProtocol, @unchecked Sendable {
    var accessToken: String = "mock-access-token"
    var refreshedToken: String = "mock-refreshed-token"
    var shouldThrowOnRefresh: Bool = false
    var shouldThrowOnGetToken: Bool = false
    var refreshCallCount: Int = 0
    var getAccessTokenCallCount: Int = 0

    func configure() {
        // No-op for tests
    }

    func signIn(username: String, password: String) async throws {
        throw AuthError.notImplemented
    }

    func signOut() async {
        // No-op for tests
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
