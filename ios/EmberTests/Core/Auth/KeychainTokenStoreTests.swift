import Testing
import Foundation
@testable import Ember

/// Tests for `KeychainTokenStore`.
///
/// Note: Keychain tests require a simulator or device with Keychain access.
/// Each test uses a fresh `KeychainTokenStore` instance with the shared service name,
/// so tests clear tokens in setup to avoid cross-test contamination.
@Suite("KeychainTokenStore")
struct KeychainTokenStoreTests {

    private func makeStore() -> KeychainTokenStore {
        let store = KeychainTokenStore()
        store.clearTokens()
        return store
    }

    @Test("saves tokens then reads access token")
    func saveAndReadAccessToken() throws {
        let store = makeStore()
        try store.saveTokens(accessToken: "access-123", refreshToken: "refresh-456")
        #expect(store.getAccessToken() == "access-123")
    }

    @Test("saves tokens then reads refresh token")
    func saveAndReadRefreshToken() throws {
        let store = makeStore()
        try store.saveTokens(accessToken: "access-123", refreshToken: "refresh-456")
        #expect(store.getRefreshToken() == "refresh-456")
    }

    @Test("returns nil for access token when nothing saved")
    func noAccessToken() {
        let store = makeStore()
        #expect(store.getAccessToken() == nil)
    }

    @Test("returns nil for refresh token when nothing saved")
    func noRefreshToken() {
        let store = makeStore()
        #expect(store.getRefreshToken() == nil)
    }

    @Test("hasTokens returns true when tokens saved")
    func hasTokensTrue() throws {
        let store = makeStore()
        try store.saveTokens(accessToken: "a", refreshToken: "r")
        #expect(store.hasTokens == true)
    }

    @Test("hasTokens returns false when no tokens saved")
    func hasTokensFalse() {
        let store = makeStore()
        #expect(store.hasTokens == false)
    }

    @Test("clearTokens removes both tokens")
    func clearTokens() throws {
        let store = makeStore()
        try store.saveTokens(accessToken: "a", refreshToken: "r")
        store.clearTokens()
        #expect(store.getAccessToken() == nil)
        #expect(store.getRefreshToken() == nil)
        #expect(store.hasTokens == false)
    }

    @Test("saving tokens twice overwrites previous values")
    func overwriteTokens() throws {
        let store = makeStore()
        try store.saveTokens(accessToken: "old-access", refreshToken: "old-refresh")
        try store.saveTokens(accessToken: "new-access", refreshToken: "new-refresh")
        #expect(store.getAccessToken() == "new-access")
        #expect(store.getRefreshToken() == "new-refresh")
    }

    @Test("updateAccessToken updates only access token")
    func updateAccessTokenOnly() throws {
        let store = makeStore()
        try store.saveTokens(accessToken: "original", refreshToken: "refresh-keep")
        try store.updateAccessToken("updated")
        #expect(store.getAccessToken() == "updated")
        #expect(store.getRefreshToken() == "refresh-keep")
    }
}
