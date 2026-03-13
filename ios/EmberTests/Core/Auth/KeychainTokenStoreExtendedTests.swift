import Testing
import Foundation
@testable import Ember

/// Extended tests for `KeychainTokenStore` — edge cases not covered by `KeychainTokenStoreTests.swift`.
/// Covers: clearTokens on empty store, hasTokens with only one token saved,
/// updateAccessToken on a non-existent item (upsert), empty string tokens,
/// and unicode/long tokens.
@Suite("KeychainTokenStore Extended")
struct KeychainTokenStoreExtendedTests {

    private func makeStore() -> KeychainTokenStore {
        let store = KeychainTokenStore()
        store.clearTokens()
        return store
    }

    // MARK: - clearTokens on Empty Store

    @Test("clearTokens on empty store does not throw or crash")
    func clearTokensOnEmptyStoreIsNoop() {
        let store = makeStore()
        // Already cleared in makeStore(), calling again must be a no-op
        store.clearTokens()
        #expect(store.getAccessToken() == nil)
        #expect(store.getRefreshToken() == nil)
        #expect(store.hasTokens == false)
    }

    @Test("calling clearTokens twice in a row does not crash")
    func clearTokensTwiceDoesNotCrash() throws {
        let store = makeStore()
        try store.saveTokens(accessToken: "a", refreshToken: "r")
        store.clearTokens()
        store.clearTokens()  // second call must be silent no-op
        #expect(store.hasTokens == false)
    }

    // MARK: - hasTokens with Only One Token

    @Test("hasTokens returns false when only access token is saved")
    func hasTokensFalseWithOnlyAccessToken() throws {
        // Access updateAccessToken which upserts only the access token
        // so the refresh token is absent — hasTokens should be false
        let store = makeStore()
        try store.updateAccessToken("access-only")
        // Refresh token was never saved, so hasTokens must be false
        #expect(store.getAccessToken() == "access-only")
        #expect(store.getRefreshToken() == nil)
        #expect(store.hasTokens == false)
    }

    // MARK: - updateAccessToken as Upsert

    @Test("updateAccessToken on non-existent item adds the item")
    func updateAccessTokenUpsert() throws {
        let store = makeStore()
        // No prior saveTokens call — updateAccessToken must not throw
        try store.updateAccessToken("brand-new-token")
        #expect(store.getAccessToken() == "brand-new-token")
    }

    @Test("updateAccessToken does not affect refresh token")
    func updateAccessTokenLeavesRefreshTokenUnchanged() throws {
        let store = makeStore()
        try store.saveTokens(accessToken: "original", refreshToken: "keep-me")
        try store.updateAccessToken("new-access")
        #expect(store.getAccessToken() == "new-access")
        #expect(store.getRefreshToken() == "keep-me")
    }

    @Test("multiple updateAccessToken calls keep the last value")
    func multipleUpdateAccessTokenKeepsLast() throws {
        let store = makeStore()
        try store.saveTokens(accessToken: "v1", refreshToken: "r")
        try store.updateAccessToken("v2")
        try store.updateAccessToken("v3")
        #expect(store.getAccessToken() == "v3")
    }

    // MARK: - Empty String Tokens

    @Test("saving empty string access token stores and retrieves empty string")
    func emptyStringAccessToken() throws {
        let store = makeStore()
        try store.saveTokens(accessToken: "", refreshToken: "r")
        // The implementation stores whatever string is given — empty string is valid data
        let retrieved = store.getAccessToken()
        #expect(retrieved == "")
    }

    @Test("saving empty string refresh token stores and retrieves empty string")
    func emptyStringRefreshToken() throws {
        let store = makeStore()
        try store.saveTokens(accessToken: "a", refreshToken: "")
        let retrieved = store.getRefreshToken()
        #expect(retrieved == "")
    }

    // MARK: - Long and Unicode Token Values

    @Test("long JWT-like token (2048 chars) round-trips through Keychain")
    func longTokenRoundTrips() throws {
        let store = makeStore()
        let longToken = String(repeating: "eyJhbGciOiJSUzI1NiJ9.", count: 100)  // ~2100 chars
        try store.saveTokens(accessToken: longToken, refreshToken: "short-refresh")
        #expect(store.getAccessToken() == longToken)
    }

    @Test("token with unicode characters round-trips through Keychain")
    func unicodeTokenRoundTrips() throws {
        let store = makeStore()
        let unicodeToken = "token-\u{1F525}-ember-\u{2764}\u{FE0F}"
        try store.saveTokens(accessToken: unicodeToken, refreshToken: "r")
        #expect(store.getAccessToken() == unicodeToken)
    }

    // MARK: - Overwrite Preserves Correct Values

    @Test("overwriting tokens with different lengths preserves new values")
    func overwriteWithDifferentLengths() throws {
        let store = makeStore()
        try store.saveTokens(accessToken: "short", refreshToken: "short-r")
        let longAccess = String(repeating: "a", count: 512)
        let longRefresh = String(repeating: "r", count: 512)
        try store.saveTokens(accessToken: longAccess, refreshToken: longRefresh)
        #expect(store.getAccessToken() == longAccess)
        #expect(store.getRefreshToken() == longRefresh)
    }

    // MARK: - Independent Instances Share Same Keychain Service

    @Test("two store instances with same service read each other's tokens")
    func twoInstancesShareKeychain() throws {
        let store1 = makeStore()
        try store1.saveTokens(accessToken: "shared-access", refreshToken: "shared-refresh")

        let store2 = KeychainTokenStore()
        #expect(store2.getAccessToken() == "shared-access")
        #expect(store2.getRefreshToken() == "shared-refresh")

        // Cleanup
        store2.clearTokens()
    }
}
