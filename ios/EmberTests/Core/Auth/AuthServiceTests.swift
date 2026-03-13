import Testing
import Foundation
@testable import Ember

/// Tests for the AuthService scaffold stub.
/// The stub is intentionally incomplete — all methods except configure() and signOut()
/// throw AuthError.notImplemented. These tests verify the expected stub behaviour so
/// that a future developer cannot accidentally ship the stub in production.
@Suite("AuthService stub")
struct AuthServiceTests {

    // MARK: - signIn throws notImplemented

    @Test("signIn throws AuthError.notImplemented")
    func signInThrowsNotImplemented() async throws {
        let service = AuthService.shared

        await #expect(throws: AuthError.notImplemented) {
            try await service.signIn(username: "test@ember.ai", password: "secret")
        }
    }

    @Test("signIn throws with any username and password")
    func signInThrowsForAnyCredentials() async {
        let service = AuthService.shared
        var didThrow = false
        do {
            try await service.signIn(username: "", password: "")
        } catch {
            didThrow = true
        }
        #expect(didThrow)
    }

    // MARK: - getAccessToken throws notImplemented

    @Test("getAccessToken throws AuthError.notImplemented")
    func getAccessTokenThrowsNotImplemented() async throws {
        let service = AuthService.shared

        await #expect(throws: AuthError.notImplemented) {
            _ = try await service.getAccessToken()
        }
    }

    // MARK: - configure() is a no-op (does not crash)

    @Test("configure does not crash")
    func configureDoesNotCrash() {
        // configure() is a stub no-op — must not throw or crash
        let service = AuthService.shared
        service.configure()
    }

    // MARK: - signOut is a no-op (does not crash)

    @Test("signOut does not crash")
    func signOutDoesNotCrash() async {
        let service = AuthService.shared
        await service.signOut()
    }

    // MARK: - Shared Singleton

    @Test("AuthService.shared returns same instance on repeated access")
    func sharedInstanceIsSingleton() {
        let a = AuthService.shared
        let b = AuthService.shared
        #expect(a === b)
    }

    // MARK: - Protocol Conformance

    @Test("AuthService conforms to AuthServiceProtocol")
    func authServiceConformsToProtocol() {
        let service: any AuthServiceProtocol = AuthService.shared
        // If this compiles and runs, the conformance is correct
        #expect(service is AuthService)
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

    @Test("tokenUnavailable has non-empty error description")
    func tokenUnavailableHasDescription() {
        let error = AuthError.tokenUnavailable
        #expect(error.errorDescription != nil)
        #expect(!(error.errorDescription ?? "").isEmpty)
    }

    @Test("signInFailed carries the message string")
    func signInFailedCarriesMessage() {
        let message = "Invalid credentials"
        let error = AuthError.signInFailed(message)
        #expect(error.errorDescription == message)
    }

    @Test("signInFailed with empty message has empty error description")
    func signInFailedEmptyMessage() {
        let error = AuthError.signInFailed("")
        #expect(error.errorDescription == "")
    }

    @Test("AuthError conforms to LocalizedError")
    func authErrorConformsToLocalizedError() {
        let error: any LocalizedError = AuthError.notImplemented
        #expect(error.errorDescription != nil)
    }
}
