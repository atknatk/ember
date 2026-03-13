import Foundation

protocol AuthServiceProtocol: AnyObject, Sendable {
    func configure()
    func signIn(username: String, password: String) async throws
    func signOut() async
    func getAccessToken() async throws -> String
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
}
