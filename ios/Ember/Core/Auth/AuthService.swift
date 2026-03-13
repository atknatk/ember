import Foundation

protocol AuthServiceProtocol: AnyObject, Sendable {
    func configure()
    func signIn(username: String, password: String) async throws
    func signOut() async
    func getAccessToken() async throws -> String
    /// Forces a token refresh and returns the new access token.
    /// Used by `APIClient` 401 retry logic.
    func refreshToken() async throws -> String
}

final class AuthService: AuthServiceProtocol, @unchecked Sendable {
    static let shared = AuthService()

    private init() {}

    func configure() {
        // Stub: Amplify configuration will be added in the auth feature
    }

    func signIn(username: String, password: String) async throws {
        throw AuthError.notImplemented
    }

    func signOut() async {
        // Stub: sign out will be implemented in the auth feature
    }

    func getAccessToken() async throws -> String {
        throw AuthError.notImplemented
    }

    func refreshToken() async throws -> String {
        // Stub: real implementation will call Amplify.Auth.fetchAuthSession()
        // or POST /api/v1/auth/refresh in the Cognito auth feature.
        throw AuthError.notImplemented
    }
}
