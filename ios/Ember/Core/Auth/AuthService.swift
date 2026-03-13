import Foundation

// MARK: - AuthServiceProtocol

protocol AuthServiceProtocol: AnyObject, Sendable {
    func configure()
    func signIn(username: String, password: String) async throws
    func signUp(email: String, password: String, name: String) async throws
    func signOut() async
    func getAccessToken() async throws -> String
    /// Forces a token refresh and returns the new access token.
    /// Used by `APIClient` 401 retry logic.
    func refreshToken() async throws -> String

    /// Returns `true` if stored tokens exist (may be expired).
    var isAuthenticated: Bool { get }
}

// MARK: - AuthService

/// Production auth service that calls backend REST endpoints for sign-in, sign-up, and token refresh.
///
/// Makes its own `URLSession` requests to avoid a circular dependency with `APIClient`.
/// The three auth endpoints are public (no `Authorization` header needed).
final class AuthService: AuthServiceProtocol, @unchecked Sendable {
    static let shared = AuthService()

    private let tokenStore: KeychainTokenStore
    private let baseURL: URL
    private let session: URLSession
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder

    init(
        tokenStore: KeychainTokenStore = .shared,
        baseURL: URL? = nil,
        session: URLSession = .shared
    ) {
        self.tokenStore = tokenStore
        if let baseURL {
            self.baseURL = baseURL
        } else {
            let urlString = ProcessInfo.processInfo.environment["API_BASE_URL"] ?? "https://api.ember.ai"
            self.baseURL = URL(string: urlString) ?? URL(string: "https://api.ember.ai")!
        }
        self.session = session
        self.encoder = JSONEncoder.ember
        self.decoder = JSONDecoder.ember
    }

    // MARK: - AuthServiceProtocol

    var isAuthenticated: Bool {
        tokenStore.hasTokens
    }

    func configure() {
        // No-op. Keychain is always ready. Amplify is not used.
    }

    func signIn(username: String, password: String) async throws {
        struct LoginBody: Encodable {
            let email: String
            let password: String
        }

        let body = LoginBody(email: username, password: password)

        let authResponse: AuthResponse = try await performAuthRequest(
            path: "/api/v1/auth/login",
            body: body,
            errorMapper: mapSignInError
        )

        try tokenStore.saveTokens(
            accessToken: authResponse.token,
            refreshToken: authResponse.refreshToken
        )
    }

    func signUp(email: String, password: String, name: String) async throws {
        struct RegisterBody: Encodable {
            let email: String
            let password: String
            let name: String
        }

        let body = RegisterBody(email: email, password: password, name: name)

        let authResponse: AuthResponse = try await performAuthRequest(
            path: "/api/v1/auth/register",
            body: body,
            errorMapper: mapSignUpError
        )

        try tokenStore.saveTokens(
            accessToken: authResponse.token,
            refreshToken: authResponse.refreshToken
        )
    }

    func signOut() async {
        tokenStore.clearTokens()
    }

    func getAccessToken() async throws -> String {
        guard let token = tokenStore.getAccessToken() else {
            throw AuthError.tokenUnavailable
        }
        return token
    }

    func refreshToken() async throws -> String {
        guard let currentRefreshToken = tokenStore.getRefreshToken() else {
            throw AuthError.tokenUnavailable
        }

        struct RefreshBody: Encodable {
            let refreshToken: String
        }

        let body = RefreshBody(refreshToken: currentRefreshToken)

        let refreshResponse: RefreshResponse
        do {
            refreshResponse = try await performAuthRequest(
                path: "/api/v1/auth/refresh",
                body: body,
                errorMapper: { _, _ in AuthError.tokenUnavailable }
            )
        } catch {
            throw AuthError.tokenUnavailable
        }

        try tokenStore.updateAccessToken(refreshResponse.token)
        return refreshResponse.token
    }

    // MARK: - Private Helpers

    /// Performs a POST request to an auth endpoint and decodes the response.
    private func performAuthRequest<T: Decodable>(
        path: String,
        body: some Encodable,
        errorMapper: @Sendable (Int, String?) -> AuthError
    ) async throws -> T {
        guard let url = URL(string: path, relativeTo: baseURL) else {
            throw AuthError.signInFailed("Something went wrong. Please try again.")
        }

        // Resolve to absolute URL
        guard let absoluteURL = URL(string: url.absoluteString) else {
            throw AuthError.signInFailed("Something went wrong. Please try again.")
        }

        var request = URLRequest(url: absoluteURL)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(body)

        let data: Data
        let response: URLResponse

        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw errorMapper(0, "Connection failed. Please check your internet.")
        }

        guard let httpResponse = response as? HTTPURLResponse else {
            throw errorMapper(0, "Something went wrong. Please try again.")
        }

        let statusCode = httpResponse.statusCode

        guard (200...299).contains(statusCode) else {
            // Try to parse error detail from response body
            let detail = parseErrorDetail(from: data)
            throw errorMapper(statusCode, detail)
        }

        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw errorMapper(0, "Something went wrong. Please try again.")
        }
    }

    /// Parses `{"detail": "..."}` from an error response body.
    private func parseErrorDetail(from data: Data) -> String? {
        struct ErrorBody: Decodable {
            let detail: String
        }
        return (try? JSONDecoder().decode(ErrorBody.self, from: data))?.detail
    }

    /// Maps HTTP errors for sign-in.
    private func mapSignInError(statusCode: Int, detail: String?) -> AuthError {
        switch statusCode {
        case 0:
            return .signInFailed(detail ?? "Something went wrong. Please try again.")
        case 401:
            return .signInFailed("Invalid email or password")
        case 400:
            return .signInFailed(detail ?? "Invalid email or password")
        case 429:
            return .signInFailed("Too many attempts. Please try again later.")
        default:
            return .signInFailed("Something went wrong. Please try again.")
        }
    }

    /// Maps HTTP errors for sign-up.
    private func mapSignUpError(statusCode: Int, detail: String?) -> AuthError {
        switch statusCode {
        case 0:
            return .signUpFailed(detail ?? "Something went wrong. Please try again.")
        case 400:
            if let detail, detail.lowercased().contains("already exists") {
                return .signUpFailed("An account with this email already exists")
            }
            if let detail, detail.contains("Password") || detail.contains("password") {
                return .signUpFailed("Password does not meet requirements")
            }
            return .signUpFailed(detail ?? "Invalid registration data")
        case 429:
            return .signUpFailed("Too many attempts. Please try again later.")
        default:
            return .signUpFailed("Something went wrong. Please try again.")
        }
    }
}
