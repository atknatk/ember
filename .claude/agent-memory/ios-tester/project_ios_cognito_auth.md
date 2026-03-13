---
name: ios-cognito-auth test patterns
description: Patterns established during P03-03 iOS Cognito Auth testing — AuthService URL interception, KeychainTokenStore edge cases, AuthViewModel extended coverage
type: project
---

The auth layer (P03-03) uses `AuthService` with injected `URLSession` + `MockURLProtocol` (same pattern as network layer tests). `AuthService` is constructed with `tokenStore:`, `baseURL:`, and `session:` parameters — NOT via APIClient. The `KeychainTokenStore` uses the real Keychain in tests (requires simulator or device with entitlements).

Key test facts:
- `AuthService` sends snake_case `refresh_token` key in refresh body via `JSONEncoder.ember`.
- `hasTokens` returns false if only one token (access or refresh) is stored — both must be present.
- `updateAccessToken` is an upsert — safe to call even before `saveTokens`.
- `signInFailed("")` has an empty `errorDescription` — callers must provide non-empty messages.
- `AuthError` is `Equatable` and cross-case comparisons work.
- `UserResponse.avatarUrl` is `String?` — absent JSON key decodes to nil (standard Swift Codable behavior).
- `AuthViewModel` does NOT trim passwords, only email (lowercased + trimmed).
- `isShowingSignUp` is reset to `false` by `signOut`.

**Why:** Auth is the first feature to call backend endpoints directly (not via `APIClient`), so `AuthService` has its own URLSession pattern. Important to verify URL paths and request body encoding separately.

**How to apply:** When writing extended tests for auth, always verify the URL path (not just success/failure), the HTTP method, Content-Type header, and body key names. For `KeychainTokenStore` tests, always call `store.clearTokens()` in setup to avoid cross-test contamination. Extended auth tests go in `*ExtendedTests.swift` alongside originals in:
- `ios/EmberTests/Core/Auth/` (for AuthService, AuthError, AuthModels, KeychainTokenStore)
- `ios/EmberTests/Features/Auth/` (for AuthViewModel)

Group IDs for pbxproj: Core/Auth tests group = `A65AAA63E57C211EBDD3BCE6`, Features/Auth tests group = `F7C943E9BD81D247624A0CB6`, Sources build phase = `91FC9734A1965EA61C9B43FF`.
