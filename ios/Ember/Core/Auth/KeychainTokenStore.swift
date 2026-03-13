import Foundation
import Security

/// Securely stores JWT tokens in the iOS Keychain.
///
/// Uses `kSecClassGenericPassword` items with service `"com.ember.auth"`.
/// Thread-safe: Keychain APIs (`SecItem*`) are thread-safe per Apple documentation.
final class KeychainTokenStore: @unchecked Sendable {
    static let shared = KeychainTokenStore()

    private let service = "com.ember.auth"
    private let accessTokenAccount = "accessToken"
    private let refreshTokenAccount = "refreshToken"

    init() {}

    // MARK: - Public Interface

    /// Saves both access and refresh tokens to the Keychain.
    /// - Throws: `AuthError.keychainError` if either save operation fails.
    func saveTokens(accessToken: String, refreshToken: String) throws {
        try saveItem(account: accessTokenAccount, value: accessToken)
        try saveItem(account: refreshTokenAccount, value: refreshToken)
    }

    /// Updates only the access token in the Keychain.
    /// - Throws: `AuthError.keychainError` if the save operation fails.
    func updateAccessToken(_ token: String) throws {
        try saveItem(account: accessTokenAccount, value: token)
    }

    /// Reads the stored access token, or `nil` if not present.
    func getAccessToken() -> String? {
        readItem(account: accessTokenAccount)
    }

    /// Reads the stored refresh token, or `nil` if not present.
    func getRefreshToken() -> String? {
        readItem(account: refreshTokenAccount)
    }

    /// Deletes both tokens from the Keychain. Errors are silently ignored.
    func clearTokens() {
        deleteItem(account: accessTokenAccount)
        deleteItem(account: refreshTokenAccount)
    }

    /// Returns `true` if both access and refresh tokens are stored.
    var hasTokens: Bool {
        getAccessToken() != nil && getRefreshToken() != nil
    }

    // MARK: - Private Keychain Helpers

    private func saveItem(account: String, value: String) throws {
        guard let data = value.data(using: .utf8) else {
            throw AuthError.keychainError
        }

        // Try to update first
        let searchQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]

        let updateAttributes: [String: Any] = [
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        ]

        let updateStatus = SecItemUpdate(searchQuery as CFDictionary, updateAttributes as CFDictionary)

        if updateStatus == errSecSuccess {
            return
        }

        if updateStatus == errSecItemNotFound {
            // Item does not exist yet — add it
            var addQuery = searchQuery
            addQuery[kSecValueData as String] = data
            addQuery[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly

            let addStatus = SecItemAdd(addQuery as CFDictionary, nil)
            guard addStatus == errSecSuccess else {
                throw AuthError.keychainError
            }
            return
        }

        throw AuthError.keychainError
    }

    private func readItem(account: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]

        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)

        guard status == errSecSuccess,
              let data = result as? Data,
              let string = String(data: data, encoding: .utf8) else {
            return nil
        }

        return string
    }

    private func deleteItem(account: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
        SecItemDelete(query as CFDictionary)
    }
}
