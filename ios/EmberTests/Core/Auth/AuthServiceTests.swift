import Testing
import Foundation
@testable import Ember

/// Tests for the production `AuthService` implementation.
/// Uses `MockURLProtocol` to intercept HTTP requests.
@Suite("AuthService")
struct AuthServiceTests {

    // MARK: - Helpers

    /// Creates an `AuthService` with a `URLSession` that intercepts requests via `MockURLProtocol`.
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

    private func makeHTTPResponse(url: URL, statusCode: Int) -> HTTPURLResponse {
        HTTPURLResponse(
            url: url,
            statusCode: statusCode,
            httpVersion: nil,
            headerFields: nil
        )!
    }

    // MARK: - signIn Tests

    @Test("signIn with 200 response saves tokens and sets isAuthenticated")
    func signInSuccess() async throws {
        let (service, tokenStore) = makeService()
        let responseData = makeAuthResponseJSON()

        MockURLProtocol.requestHandler = { request in
            let response = self.makeHTTPResponse(url: request.url!, statusCode: 200)
            return (response, responseData)
        }

        try await service.signIn(username: "test@ember.ai", password: "password123")

        #expect(tokenStore.getAccessToken() == "test-access-token")
        #expect(tokenStore.getRefreshToken() == "test-refresh-token")
        #expect(service.isAuthenticated == true)

        MockURLProtocol.reset()
    }

    @Test("signIn with 401 throws signInFailed with invalid credentials message")
    func signInUnauthorized() async throws {
        let (service, _) = makeService()

        MockURLProtocol.requestHandler = { request in
            let body = "{\"detail\":\"Invalid email or password\"}".data(using: .utf8)
            let response = self.makeHTTPResponse(url: request.url!, statusCode: 401)
            return (response, body)
        }

        await #expect(throws: AuthError.signInFailed("Invalid email or password")) {
            try await service.signIn(username: "test@ember.ai", password: "wrong")
        }

        MockURLProtocol.reset()
    }

    @Test("signIn with 503 throws signInFailed with service unavailable message")
    func signInServiceUnavailable() async throws {
        let (service, _) = makeService()

        MockURLProtocol.requestHandler = { request in
            let response = self.makeHTTPResponse(url: request.url!, statusCode: 503)
            return (response, Data())
        }

        await #expect(throws: AuthError.signInFailed("Something went wrong. Please try again.")) {
            try await service.signIn(username: "test@ember.ai", password: "pass")
        }

        MockURLProtocol.reset()
    }

    @Test("signIn request body has correct JSON keys")
    func signInRequestBody() async throws {
        let (service, _) = makeService()
        let responseData = makeAuthResponseJSON()

        MockURLProtocol.requestHandler = { request in
            let response = self.makeHTTPResponse(url: request.url!, statusCode: 200)
            return (response, responseData)
        }

        try await service.signIn(username: "user@test.com", password: "pass123")

        if let lastRequest = MockURLProtocol.lastRequest,
           let body = lastRequest.httpBody,
           let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any] {
            #expect(json["email"] as? String == "user@test.com")
            #expect(json["password"] as? String == "pass123")
        } else {
            Issue.record("Request body not captured or not valid JSON")
        }

        MockURLProtocol.reset()
    }

    // MARK: - signUp Tests

    @Test("signUp with 201 response saves tokens and sets isAuthenticated")
    func signUpSuccess() async throws {
        let (service, tokenStore) = makeService()
        let responseData = makeAuthResponseJSON()

        MockURLProtocol.requestHandler = { request in
            let response = self.makeHTTPResponse(url: request.url!, statusCode: 201)
            return (response, responseData)
        }

        try await service.signUp(email: "new@ember.ai", password: "password123", name: "New User")

        #expect(tokenStore.getAccessToken() == "test-access-token")
        #expect(tokenStore.getRefreshToken() == "test-refresh-token")
        #expect(service.isAuthenticated == true)

        MockURLProtocol.reset()
    }

    @Test("signUp with 400 'already exists' throws signUpFailed")
    func signUpAlreadyExists() async throws {
        let (service, _) = makeService()

        MockURLProtocol.requestHandler = { request in
            let body = "{\"detail\":\"User already exists\"}".data(using: .utf8)
            let response = self.makeHTTPResponse(url: request.url!, statusCode: 400)
            return (response, body)
        }

        await #expect(throws: AuthError.signUpFailed("An account with this email already exists")) {
            try await service.signUp(email: "existing@ember.ai", password: "password123", name: "User")
        }

        MockURLProtocol.reset()
    }

    @Test("signUp with 400 'Password' throws signUpFailed with password requirements")
    func signUpPasswordRequirements() async throws {
        let (service, _) = makeService()

        MockURLProtocol.requestHandler = { request in
            let body = "{\"detail\":\"Password must contain uppercase\"}".data(using: .utf8)
            let response = self.makeHTTPResponse(url: request.url!, statusCode: 400)
            return (response, body)
        }

        await #expect(throws: AuthError.signUpFailed("Password does not meet requirements")) {
            try await service.signUp(email: "test@ember.ai", password: "weak", name: "User")
        }

        MockURLProtocol.reset()
    }

    @Test("signUp request body has correct JSON keys")
    func signUpRequestBody() async throws {
        let (service, _) = makeService()
        let responseData = makeAuthResponseJSON()

        MockURLProtocol.requestHandler = { request in
            let response = self.makeHTTPResponse(url: request.url!, statusCode: 200)
            return (response, responseData)
        }

        try await service.signUp(email: "user@test.com", password: "pass12345", name: "Test User")

        if let lastRequest = MockURLProtocol.lastRequest,
           let body = lastRequest.httpBody,
           let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any] {
            #expect(json["email"] as? String == "user@test.com")
            #expect(json["password"] as? String == "pass12345")
            #expect(json["name"] as? String == "Test User")
        } else {
            Issue.record("Request body not captured or not valid JSON")
        }

        MockURLProtocol.reset()
    }

    // MARK: - signOut Tests

    @Test("signOut clears tokens from keychain")
    func signOutClearsTokens() async throws {
        let (service, tokenStore) = makeService()
        try tokenStore.saveTokens(accessToken: "a", refreshToken: "r")
        #expect(service.isAuthenticated == true)

        await service.signOut()

        #expect(service.isAuthenticated == false)
        #expect(tokenStore.getAccessToken() == nil)
        #expect(tokenStore.getRefreshToken() == nil)
    }

    // MARK: - getAccessToken Tests

    @Test("getAccessToken returns token when saved")
    func getAccessTokenSuccess() async throws {
        let (service, tokenStore) = makeService()
        try tokenStore.saveTokens(accessToken: "my-token", refreshToken: "r")

        let token = try await service.getAccessToken()
        #expect(token == "my-token")
    }

    @Test("getAccessToken throws tokenUnavailable when no token")
    func getAccessTokenNoToken() async throws {
        let (service, _) = makeService()

        await #expect(throws: AuthError.tokenUnavailable) {
            _ = try await service.getAccessToken()
        }
    }

    // MARK: - refreshToken Tests

    @Test("refreshToken with 200 response updates access token and returns new token")
    func refreshTokenSuccess() async throws {
        let (service, tokenStore) = makeService()
        try tokenStore.saveTokens(accessToken: "old-access", refreshToken: "valid-refresh")

        let refreshResponseJSON = "{\"token\":\"new-access-token\"}".data(using: .utf8)!

        MockURLProtocol.requestHandler = { request in
            let response = self.makeHTTPResponse(url: request.url!, statusCode: 200)
            return (response, refreshResponseJSON)
        }

        let newToken = try await service.refreshToken()

        #expect(newToken == "new-access-token")
        #expect(tokenStore.getAccessToken() == "new-access-token")
        // Refresh token should not change
        #expect(tokenStore.getRefreshToken() == "valid-refresh")

        MockURLProtocol.reset()
    }

    @Test("refreshToken with 401 response throws tokenUnavailable")
    func refreshTokenExpired() async throws {
        let (service, tokenStore) = makeService()
        try tokenStore.saveTokens(accessToken: "old", refreshToken: "expired-refresh")

        MockURLProtocol.requestHandler = { request in
            let response = self.makeHTTPResponse(url: request.url!, statusCode: 401)
            return (response, Data())
        }

        await #expect(throws: AuthError.tokenUnavailable) {
            _ = try await service.refreshToken()
        }

        MockURLProtocol.reset()
    }

    @Test("refreshToken when no refresh token in keychain throws tokenUnavailable")
    func refreshTokenNoRefreshToken() async throws {
        let (service, _) = makeService()

        await #expect(throws: AuthError.tokenUnavailable) {
            _ = try await service.refreshToken()
        }
    }

    // MARK: - isAuthenticated Tests

    @Test("isAuthenticated returns false when no tokens")
    func isAuthenticatedFalseNoTokens() {
        let (service, _) = makeService()
        #expect(service.isAuthenticated == false)
    }

    @Test("isAuthenticated returns true when tokens present")
    func isAuthenticatedTrueWithTokens() throws {
        let (service, tokenStore) = makeService()
        try tokenStore.saveTokens(accessToken: "a", refreshToken: "r")
        #expect(service.isAuthenticated == true)
    }

    // MARK: - configure Tests

    @Test("configure does not crash (no-op)")
    func configureNoOp() {
        let (service, _) = makeService()
        service.configure()
    }
}

// MARK: - AuthError Tests

@Suite("AuthError")
struct AuthErrorTests {

    @Test("notImplemented has non-empty error description")
    func notImplementedHasDescription() {
        let error = AuthError.notImplemented
        #expect(error.errorDescription != nil)
        #expect(!(error.errorDescription ?? "").isEmpty)
    }

    @Test("tokenUnavailable has user-friendly message")
    func tokenUnavailableHasDescription() {
        let error = AuthError.tokenUnavailable
        #expect(error.errorDescription == "Your session has expired. Please sign in again.")
    }

    @Test("signInFailed carries the message string")
    func signInFailedCarriesMessage() {
        let message = "Invalid credentials"
        let error = AuthError.signInFailed(message)
        #expect(error.errorDescription == message)
    }

    @Test("signUpFailed carries the message string")
    func signUpFailedCarriesMessage() {
        let message = "Account already exists"
        let error = AuthError.signUpFailed(message)
        #expect(error.errorDescription == message)
    }

    @Test("keychainError has error description")
    func keychainErrorHasDescription() {
        let error = AuthError.keychainError
        #expect(error.errorDescription != nil)
        #expect(!(error.errorDescription ?? "").isEmpty)
    }

    @Test("AuthError conforms to LocalizedError")
    func authErrorConformsToLocalizedError() {
        let error: any LocalizedError = AuthError.notImplemented
        #expect(error.errorDescription != nil)
    }

    @Test("AuthError conforms to Equatable")
    func authErrorEquatable() {
        #expect(AuthError.tokenUnavailable == AuthError.tokenUnavailable)
        #expect(AuthError.signInFailed("a") == AuthError.signInFailed("a"))
        #expect(AuthError.signInFailed("a") != AuthError.signInFailed("b"))
        #expect(AuthError.signUpFailed("x") == AuthError.signUpFailed("x"))
        #expect(AuthError.keychainError == AuthError.keychainError)
    }
}
