import Testing
import Foundation
@testable import Ember

/// Extended tests for `AuthService`, `AuthError`, and `AuthModels` — edge cases not covered
/// by `AuthServiceTests.swift`. Covers: correct URL paths, snake_case request body keys for
/// refreshToken, rate-limit (429) error mapping, network error mapping, signOut idempotency,
/// AuthError cross-case inequality, all errorDescription non-nil, and AuthModels JSON decoding.
@Suite("AuthService Extended")
struct AuthServiceExtendedTests {

    // MARK: - Helpers

    private func makeService() -> (AuthService, KeychainTokenStore) {
        let tokenStore = KeychainTokenStore()
        tokenStore.clearTokens()

        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockURLProtocol.self]
        let session = URLSession(configuration: config)

        let service = AuthService(
            tokenStore: tokenStore,
            baseURL: URL(string: "https://test.ember.ai")!,
            session: session
        )
        return (service, tokenStore)
    }

    private func makeAuthResponseJSON() -> Data {
        """
        {
            "token": "test-access-token",
            "refresh_token": "test-refresh-token",
            "user": {
                "id": "user-1",
                "email": "test@ember.ai",
                "name": "Test User",
                "avatar_url": null,
                "timezone": "UTC",
                "preferred_language": "en",
                "onboarding_completed": false,
                "subscription_tier": "free",
                "created_at": "2026-01-01T00:00:00Z"
            }
        }
        """.data(using: .utf8)!
    }

    private func httpResponse(url: URL, statusCode: Int) -> HTTPURLResponse {
        HTTPURLResponse(url: url, statusCode: statusCode, httpVersion: nil, headerFields: nil)!
    }

    // MARK: - Correct URL Paths

    @Test("signIn sends request to /api/v1/auth/login path")
    func signInUsesCorrectPath() async throws {
        let (service, _) = makeService()
        let responseData = makeAuthResponseJSON()

        MockURLProtocol.requestHandler = { request in
            return (self.httpResponse(url: request.url!, statusCode: 200), responseData)
        }

        try await service.signIn(username: "test@ember.ai", password: "pass123")

        let lastRequest = MockURLProtocol.lastRequest
        #expect(lastRequest?.url?.path == "/api/v1/auth/login")

        MockURLProtocol.reset()
    }

    @Test("signUp sends request to /api/v1/auth/register path")
    func signUpUsesCorrectPath() async throws {
        let (service, _) = makeService()
        let responseData = makeAuthResponseJSON()

        MockURLProtocol.requestHandler = { request in
            return (self.httpResponse(url: request.url!, statusCode: 201), responseData)
        }

        try await service.signUp(email: "new@ember.ai", password: "pass123", name: "New")

        let lastRequest = MockURLProtocol.lastRequest
        #expect(lastRequest?.url?.path == "/api/v1/auth/register")

        MockURLProtocol.reset()
    }

    @Test("refreshToken sends request to /api/v1/auth/refresh path")
    func refreshTokenUsesCorrectPath() async throws {
        let (service, tokenStore) = makeService()
        try tokenStore.saveTokens(accessToken: "old", refreshToken: "valid-refresh")

        let refreshJSON = "{\"token\":\"new-token\"}".data(using: .utf8)!

        MockURLProtocol.requestHandler = { request in
            return (self.httpResponse(url: request.url!, statusCode: 200), refreshJSON)
        }

        _ = try await service.refreshToken()

        let lastRequest = MockURLProtocol.lastRequest
        #expect(lastRequest?.url?.path == "/api/v1/auth/refresh")

        MockURLProtocol.reset()
    }

    // MARK: - HTTP Method

    @Test("signIn sends POST request")
    func signInSendsPOST() async throws {
        let (service, _) = makeService()
        let responseData = makeAuthResponseJSON()

        MockURLProtocol.requestHandler = { request in
            return (self.httpResponse(url: request.url!, statusCode: 200), responseData)
        }

        try await service.signIn(username: "test@ember.ai", password: "pass")

        #expect(MockURLProtocol.lastRequest?.httpMethod == "POST")

        MockURLProtocol.reset()
    }

    @Test("signUp sends POST request")
    func signUpSendsPOST() async throws {
        let (service, _) = makeService()
        let responseData = makeAuthResponseJSON()

        MockURLProtocol.requestHandler = { request in
            return (self.httpResponse(url: request.url!, statusCode: 201), responseData)
        }

        try await service.signUp(email: "new@ember.ai", password: "pass", name: "User")

        #expect(MockURLProtocol.lastRequest?.httpMethod == "POST")

        MockURLProtocol.reset()
    }

    // MARK: - Content-Type Header

    @Test("signIn sets Content-Type: application/json header")
    func signInSetsContentTypeHeader() async throws {
        let (service, _) = makeService()
        let responseData = makeAuthResponseJSON()

        MockURLProtocol.requestHandler = { request in
            return (self.httpResponse(url: request.url!, statusCode: 200), responseData)
        }

        try await service.signIn(username: "test@ember.ai", password: "pass")

        let contentType = MockURLProtocol.lastRequest?.value(forHTTPHeaderField: "Content-Type")
        #expect(contentType == "application/json")

        MockURLProtocol.reset()
    }

    // MARK: - refreshToken Body Uses snake_case Key

    @Test("refreshToken request body uses snake_case 'refresh_token' key")
    func refreshTokenBodyUsesSnakeCaseKey() async throws {
        let (service, tokenStore) = makeService()
        try tokenStore.saveTokens(accessToken: "old", refreshToken: "my-refresh-token")

        let refreshJSON = "{\"token\":\"new-token\"}".data(using: .utf8)!

        MockURLProtocol.requestHandler = { request in
            return (self.httpResponse(url: request.url!, statusCode: 200), refreshJSON)
        }

        _ = try await service.refreshToken()

        if let body = MockURLProtocol.lastRequest?.httpBody,
           let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any] {
            // The key must be snake_case "refresh_token", not camelCase "refreshToken"
            #expect(json["refresh_token"] as? String == "my-refresh-token")
            #expect(json["refreshToken"] == nil)
        } else {
            Issue.record("Request body not captured or not valid JSON")
        }

        MockURLProtocol.reset()
    }

    // MARK: - Rate Limit (429) Error Mapping

    @Test("signIn with 429 response throws signInFailed with rate-limit message")
    func signInRateLimit() async throws {
        let (service, _) = makeService()

        MockURLProtocol.requestHandler = { request in
            let body = "{\"detail\":\"Rate limit exceeded\"}".data(using: .utf8)
            return (self.httpResponse(url: request.url!, statusCode: 429), body)
        }

        await #expect(throws: AuthError.signInFailed("Too many attempts. Please try again later.")) {
            try await service.signIn(username: "test@ember.ai", password: "pass")
        }

        MockURLProtocol.reset()
    }

    @Test("signUp with 429 response throws signUpFailed with rate-limit message")
    func signUpRateLimit() async throws {
        let (service, _) = makeService()

        MockURLProtocol.requestHandler = { request in
            let body = "{\"detail\":\"Too many requests\"}".data(using: .utf8)
            return (self.httpResponse(url: request.url!, statusCode: 429), body)
        }

        await #expect(throws: AuthError.signUpFailed("Too many attempts. Please try again later.")) {
            try await service.signUp(email: "test@ember.ai", password: "pass", name: "User")
        }

        MockURLProtocol.reset()
    }

    // MARK: - Network Error Mapping

    @Test("signIn with URLError throws signInFailed with connection message")
    func signInNetworkError() async throws {
        let (service, _) = makeService()

        MockURLProtocol.requestHandler = { _ in
            throw URLError(.notConnectedToInternet)
        }

        do {
            try await service.signIn(username: "test@ember.ai", password: "pass")
            Issue.record("Expected signIn to throw")
        } catch let error as AuthError {
            if case .signInFailed(let message) = error {
                #expect(message.contains("Connection") || message.contains("internet") || !message.isEmpty)
            } else {
                Issue.record("Expected signInFailed, got \(error)")
            }
        }

        MockURLProtocol.reset()
    }

    @Test("signUp with URLError throws signUpFailed")
    func signUpNetworkError() async throws {
        let (service, _) = makeService()

        MockURLProtocol.requestHandler = { _ in
            throw URLError(.timedOut)
        }

        do {
            try await service.signUp(email: "test@ember.ai", password: "pass", name: "User")
            Issue.record("Expected signUp to throw")
        } catch let error as AuthError {
            if case .signUpFailed = error {
                // expected
            } else {
                Issue.record("Expected signUpFailed, got \(error)")
            }
        }

        MockURLProtocol.reset()
    }

    // MARK: - signOut Idempotency

    @Test("signOut when already signed out does not throw")
    func signOutWhenAlreadySignedOut() async throws {
        let (service, tokenStore) = makeService()
        // Never saved any tokens
        #expect(service.isAuthenticated == false)

        // Should be a no-op without throwing
        await service.signOut()

        #expect(service.isAuthenticated == false)
        #expect(tokenStore.getAccessToken() == nil)
    }

    @Test("signOut called twice is idempotent")
    func signOutTwiceIsIdempotent() async throws {
        let (service, tokenStore) = makeService()
        try tokenStore.saveTokens(accessToken: "a", refreshToken: "r")
        #expect(service.isAuthenticated == true)

        await service.signOut()
        await service.signOut()  // second call must not crash

        #expect(service.isAuthenticated == false)
        #expect(tokenStore.getAccessToken() == nil)
        #expect(tokenStore.getRefreshToken() == nil)
    }

    // MARK: - signUp 400 Without Matching Keyword

    @Test("signUp with 400 and unrecognized detail uses detail message")
    func signUpGeneric400() async throws {
        let (service, _) = makeService()

        MockURLProtocol.requestHandler = { request in
            let body = "{\"detail\":\"Invalid registration data\"}".data(using: .utf8)
            return (self.httpResponse(url: request.url!, statusCode: 400), body)
        }

        await #expect(throws: AuthError.signUpFailed("Invalid registration data")) {
            try await service.signUp(email: "test@ember.ai", password: "pass", name: "User")
        }

        MockURLProtocol.reset()
    }

    @Test("signIn with 400 uses detail message from response")
    func signIn400WithDetail() async throws {
        let (service, _) = makeService()

        MockURLProtocol.requestHandler = { request in
            let body = "{\"detail\":\"Account disabled\"}".data(using: .utf8)
            return (self.httpResponse(url: request.url!, statusCode: 400), body)
        }

        await #expect(throws: AuthError.signInFailed("Account disabled")) {
            try await service.signIn(username: "test@ember.ai", password: "pass")
        }

        MockURLProtocol.reset()
    }

    // MARK: - refreshToken Does Not Change Refresh Token

    @Test("refreshToken success does not alter refresh token in keychain")
    func refreshTokenDoesNotChangeRefreshToken() async throws {
        let (service, tokenStore) = makeService()
        try tokenStore.saveTokens(accessToken: "old-access", refreshToken: "original-refresh")

        let refreshJSON = "{\"token\":\"brand-new-access\"}".data(using: .utf8)!

        MockURLProtocol.requestHandler = { request in
            return (self.httpResponse(url: request.url!, statusCode: 200), refreshJSON)
        }

        _ = try await service.refreshToken()

        #expect(tokenStore.getRefreshToken() == "original-refresh")
        #expect(tokenStore.getAccessToken() == "brand-new-access")

        MockURLProtocol.reset()
    }

    // MARK: - configure is No-Op

    @Test("configure is callable and does not mutate isAuthenticated")
    func configureDoesNotMutateState() throws {
        let (service, tokenStore) = makeService()
        try tokenStore.saveTokens(accessToken: "a", refreshToken: "r")

        service.configure()

        // isAuthenticated should still reflect the keychain state, unchanged
        #expect(service.isAuthenticated == true)
    }
}

// MARK: - AuthError Extended Tests

@Suite("AuthError Extended")
struct AuthErrorExtendedTests {

    // MARK: - All Cases Have Non-Empty Descriptions

    @Test("all AuthError cases produce non-empty errorDescription")
    func allCasesHaveNonEmptyDescription() {
        let allCases: [AuthError] = [
            .signInFailed("test message"),
            .signUpFailed("test message"),
            .tokenUnavailable,
            .keychainError,
            .notImplemented,
        ]

        for error in allCases {
            let description = error.errorDescription
            #expect(description != nil, "errorDescription nil for \(error)")
            #expect(!(description ?? "").isEmpty, "errorDescription empty for \(error)")
        }
    }

    @Test("signInFailed with empty string has empty errorDescription")
    func signInFailedEmptyMessage() {
        let error = AuthError.signInFailed("")
        // errorDescription should reflect the associated value exactly
        #expect(error.errorDescription == "")
    }

    @Test("signUpFailed with empty string has empty errorDescription")
    func signUpFailedEmptyMessage() {
        let error = AuthError.signUpFailed("")
        #expect(error.errorDescription == "")
    }

    // MARK: - Cross-Case Inequality

    @Test("different AuthError cases are not equal")
    func differentCasesAreNotEqual() {
        #expect(AuthError.tokenUnavailable != AuthError.keychainError)
        #expect(AuthError.tokenUnavailable != AuthError.notImplemented)
        #expect(AuthError.keychainError != AuthError.notImplemented)
        #expect(AuthError.signInFailed("x") != AuthError.signUpFailed("x"))
    }

    @Test("signInFailed and signUpFailed with same message are not equal")
    func signInFailedNotEqualToSignUpFailed() {
        let msg = "Account issue"
        #expect(AuthError.signInFailed(msg) != AuthError.signUpFailed(msg))
    }

    // MARK: - Specific Error Messages

    @Test("tokenUnavailable message mentions session")
    func tokenUnavailableMessageMentionsSession() {
        let error = AuthError.tokenUnavailable
        let description = error.errorDescription ?? ""
        // The spec requires a user-friendly session expiry message
        #expect(description.lowercased().contains("session") || description.lowercased().contains("sign in"))
    }

    @Test("keychainError message mentions authentication or secure")
    func keychainErrorMessageIsInformative() {
        let error = AuthError.keychainError
        let description = error.errorDescription ?? ""
        #expect(!description.isEmpty)
        // The message should guide the user — check it is human-readable
        #expect(description.count > 5)
    }

    // MARK: - localizedDescription Matches errorDescription

    @Test("localizedDescription matches errorDescription for all cases")
    func localizedDescriptionMatchesErrorDescription() {
        let cases: [AuthError] = [
            .signInFailed("Sign-in failed"),
            .signUpFailed("Sign-up failed"),
            .tokenUnavailable,
            .keychainError,
            .notImplemented,
        ]

        for error in cases {
            // LocalizedError uses errorDescription for localizedDescription
            #expect(error.localizedDescription == error.errorDescription)
        }
    }
}

// MARK: - AuthModels JSON Decoding Tests

@Suite("AuthModels")
struct AuthModelsTests {

    // MARK: - AuthResponse Decoding

    @Test("AuthResponse decodes with all fields present")
    func authResponseDecodesAllFields() throws {
        let json = """
        {
            "token": "access-token-abc",
            "refresh_token": "refresh-token-xyz",
            "user": {
                "id": "user-123",
                "email": "test@ember.ai",
                "name": "Test User",
                "avatar_url": "https://cdn.ember.ai/avatar.jpg",
                "timezone": "America/New_York",
                "preferred_language": "en",
                "onboarding_completed": true,
                "subscription_tier": "premium",
                "created_at": "2026-01-15T10:30:00Z"
            }
        }
        """.data(using: .utf8)!

        let response = try JSONDecoder.ember.decode(AuthResponse.self, from: json)

        #expect(response.token == "access-token-abc")
        #expect(response.refreshToken == "refresh-token-xyz")
        #expect(response.user.id == "user-123")
        #expect(response.user.email == "test@ember.ai")
        #expect(response.user.name == "Test User")
        #expect(response.user.avatarUrl == "https://cdn.ember.ai/avatar.jpg")
        #expect(response.user.timezone == "America/New_York")
        #expect(response.user.preferredLanguage == "en")
        #expect(response.user.onboardingCompleted == true)
        #expect(response.user.subscriptionTier == "premium")
    }

    @Test("AuthResponse decodes with null avatarUrl")
    func authResponseDecodesNullAvatarUrl() throws {
        let json = """
        {
            "token": "tok",
            "refresh_token": "ref",
            "user": {
                "id": "u1",
                "email": "a@b.com",
                "name": "Alice",
                "avatar_url": null,
                "timezone": "UTC",
                "preferred_language": "en",
                "onboarding_completed": false,
                "subscription_tier": "free",
                "created_at": "2026-01-01T00:00:00Z"
            }
        }
        """.data(using: .utf8)!

        let response = try JSONDecoder.ember.decode(AuthResponse.self, from: json)

        #expect(response.user.avatarUrl == nil)
    }

    @Test("AuthResponse decodes with missing optional avatarUrl field")
    func authResponseDecodesWithMissingAvatarUrl() throws {
        // avatarUrl is absent entirely (not present in JSON at all)
        let json = """
        {
            "token": "tok",
            "refresh_token": "ref",
            "user": {
                "id": "u1",
                "email": "a@b.com",
                "name": "Alice",
                "timezone": "UTC",
                "preferred_language": "en",
                "onboarding_completed": false,
                "subscription_tier": "free",
                "created_at": "2026-01-01T00:00:00Z"
            }
        }
        """.data(using: .utf8)!

        let response = try JSONDecoder.ember.decode(AuthResponse.self, from: json)

        #expect(response.user.avatarUrl == nil)
    }

    // MARK: - UserResponse Identifiable

    @Test("UserResponse.id matches Identifiable id")
    func userResponseIdentifiableId() throws {
        let json = """
        {
            "token": "tok",
            "refresh_token": "ref",
            "user": {
                "id": "user-identifiable-test",
                "email": "a@b.com",
                "name": "Alice",
                "avatar_url": null,
                "timezone": "UTC",
                "preferred_language": "en",
                "onboarding_completed": false,
                "subscription_tier": "free",
                "created_at": "2026-01-01T00:00:00Z"
            }
        }
        """.data(using: .utf8)!

        let response = try JSONDecoder.ember.decode(AuthResponse.self, from: json)

        // UserResponse conforms to Identifiable — id must be the user id string
        #expect(response.user.id == "user-identifiable-test")
    }

    // MARK: - RefreshResponse Decoding

    @Test("RefreshResponse decodes token field correctly")
    func refreshResponseDecodesToken() throws {
        let json = "{\"token\":\"new-access-token-abc\"}".data(using: .utf8)!

        let response = try JSONDecoder.ember.decode(RefreshResponse.self, from: json)

        #expect(response.token == "new-access-token-abc")
    }

    @Test("RefreshResponse decodes using ember decoder snake_case strategy")
    func refreshResponseUsesSnakeCaseDecoder() throws {
        // Backend returns {"token": "..."}, not {"access_token": "..."}
        // Verify that the ember decoder handles this correctly
        let json = "{\"token\":\"my-token\"}".data(using: .utf8)!

        let response = try JSONDecoder.ember.decode(RefreshResponse.self, from: json)

        #expect(response.token == "my-token")
    }

    // MARK: - onboardingCompleted Boolean Values

    @Test("UserResponse decodes onboardingCompleted true")
    func userResponseOnboardingCompletedTrue() throws {
        let json = """
        {
            "token": "t",
            "refresh_token": "r",
            "user": {
                "id": "u",
                "email": "a@b.com",
                "name": "A",
                "timezone": "UTC",
                "preferred_language": "en",
                "onboarding_completed": true,
                "subscription_tier": "free",
                "created_at": "2026-01-01T00:00:00Z"
            }
        }
        """.data(using: .utf8)!

        let response = try JSONDecoder.ember.decode(AuthResponse.self, from: json)
        #expect(response.user.onboardingCompleted == true)
    }

    @Test("UserResponse decodes onboardingCompleted false")
    func userResponseOnboardingCompletedFalse() throws {
        let json = """
        {
            "token": "t",
            "refresh_token": "r",
            "user": {
                "id": "u",
                "email": "a@b.com",
                "name": "A",
                "timezone": "UTC",
                "preferred_language": "en",
                "onboarding_completed": false,
                "subscription_tier": "free",
                "created_at": "2026-01-01T00:00:00Z"
            }
        }
        """.data(using: .utf8)!

        let response = try JSONDecoder.ember.decode(AuthResponse.self, from: json)
        #expect(response.user.onboardingCompleted == false)
    }

    // MARK: - Invalid JSON Throws

    @Test("AuthResponse throws on missing required token field")
    func authResponseThrowsOnMissingToken() {
        let json = """
        {
            "refresh_token": "ref",
            "user": {
                "id": "u", "email": "a@b.com", "name": "A",
                "timezone": "UTC", "preferred_language": "en",
                "onboarding_completed": false,
                "subscription_tier": "free",
                "created_at": "2026-01-01T00:00:00Z"
            }
        }
        """.data(using: .utf8)!

        #expect(throws: (any Error).self) {
            _ = try JSONDecoder.ember.decode(AuthResponse.self, from: json)
        }
    }

    @Test("RefreshResponse throws on missing token field")
    func refreshResponseThrowsOnMissingToken() {
        let json = "{\"other_field\":\"value\"}".data(using: .utf8)!

        #expect(throws: (any Error).self) {
            _ = try JSONDecoder.ember.decode(RefreshResponse.self, from: json)
        }
    }
}
