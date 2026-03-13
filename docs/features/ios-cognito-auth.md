# iOS Cognito Auth

> Provides the complete authentication flow for the Ember iOS app — sign-in, sign-up, secure token storage, and transparent token refresh — connecting the app to the live backend for the first time.

**Status**: Released
**Added in**: Phase 3 (P03-03)
**Platforms**: iOS
**GitHub Issue**: #19

---

## Overview

This feature replaces the dev-mode stub authentication in the iOS scaffold (P03-01) with a production implementation. It introduces three connected pieces: `KeychainTokenStore` for secure JWT storage, a fully working `AuthService` that calls the backend's auth REST endpoints, and an `@Observable AuthViewModel` that drives `LoginView` and `SignUpView`.

Before this feature, every call through `APIClient` failed immediately because `AuthService.getAccessToken()` threw `AuthError.notImplemented`. After this feature, the complete auth round-trip works: the user enters credentials, the app calls the backend, tokens arrive and are stored in the iOS Keychain, and every subsequent `APIClient` request attaches the correct `Authorization` header. When an access token expires, `APIClient`'s existing 401 retry (from P03-02) transparently calls `AuthService.refreshToken()`, fetches a new token from the backend, and retries the original request — all without user interaction.

The implementation deliberately avoids the AWS Amplify iOS SDK. The backend already manages all Cognito operations (user pool sign-up, login, token issuance) and also creates Profile, Character, and Conversation rows in PostgreSQL during registration. The iOS app calls those backend endpoints directly over plain `URLSession`, keeping the client side simple and avoiding the need to distribute `amplifyconfiguration.json`.

---

## Architecture

### How It Works (Data Flow)

**Sign-in:**

1. User enters email and password in `LoginView` and taps "Sign In".
2. `LoginView` calls `Task { await viewModel.signIn() }`.
3. `AuthViewModel.signIn()` sets `isLoading = true` and calls `AuthService.signIn(username:password:)` with a trimmed, lowercased email.
4. `AuthService` builds a `URLRequest` directly (not through `APIClient`) and POSTs `{"email": ..., "password": ...}` to `{baseURL}/api/v1/auth/login`.
5. On HTTP 200, `AuthService` decodes the `AuthResponse` and calls `KeychainTokenStore.saveTokens(accessToken:refreshToken:)`.
6. `AuthViewModel` sets `isAuthenticated = true` and fires a success haptic.
7. `EmberApp` observes `authViewModel.isAuthenticated`. Because it changed, SwiftUI re-evaluates the root view branch and replaces `LoginView` with `OnboardingPlaceholderView` (first sign-in) or `MainTabView` (returning user who completed onboarding).

**Authenticated API request with expired token:**

1. A ViewModel calls `apiClient.request(endpoint:responseType:)` for any protected endpoint.
2. `APIClient` reads the access token via `AuthService.getAccessToken()`, which reads from `KeychainTokenStore`.
3. The backend returns HTTP 401 (access token expired).
4. `APIClient`'s retry path calls `AuthService.refreshToken()`.
5. `AuthService` reads the refresh token from `KeychainTokenStore` and POSTs `{"refresh_token": ...}` to `{baseURL}/api/v1/auth/refresh`.
6. On HTTP 200, `AuthService` calls `KeychainTokenStore.updateAccessToken(_:)` with the new access token and returns it.
7. `APIClient` rebuilds the original request with the new token and retries. The caller never sees the interruption.

**App relaunch while authenticated:**

1. `AuthViewModel.init()` calls `AuthService.shared.isAuthenticated`, which checks `KeychainTokenStore.hasTokens`.
2. Tokens were saved from the previous session. `hasTokens` is `true`.
3. `AuthViewModel.isAuthenticated` is initialized to `true`.
4. `EmberApp` renders `MainTabView` (or `OnboardingPlaceholderView`) without showing the login screen.

### Circular Dependency Resolution

`APIClient` depends on `AuthService` (to get tokens), and `AuthService` needs to call auth endpoints. Injecting `APIClient` into `AuthService` would create a circular dependency. The solution: `AuthService` makes its own `URLSession` calls for the three public auth endpoints (`/login`, `/register`, `/refresh`). These endpoints require no `Authorization` header, so the 401 retry logic is irrelevant. `AuthService` reads its `baseURL` from the same source as `APIClient` (`ProcessInfo.processInfo.environment["API_BASE_URL"]`, falling back to `"https://api.ember.ai"`).

### SwiftUI Reactivity Bridge

`AuthService` is `@unchecked Sendable` — it cannot be `@Observable` without conflicting with its thread-safety model. `AuthViewModel` acts as the reactive bridge. It reads `AuthService.isAuthenticated` (a computed property checking `KeychainTokenStore.hasTokens`) on init to set its initial state, and it updates its own `isAuthenticated: Bool` property after successful sign-in, sign-up, or sign-out. `EmberApp` observes `AuthViewModel`, which is `@Observable`, and re-renders when `isAuthenticated` changes.

### Key Files

```
ios/Ember/Core/Auth/
  KeychainTokenStore.swift       # Keychain wrapper: save/read/update/clear JWT tokens
  AuthService.swift              # AuthServiceProtocol + production implementation
  AuthError.swift                # Error enum with user-facing localizedDescription

ios/Ember/Core/Models/
  AuthModels.swift               # AuthResponse, UserResponse, RefreshResponse Codable structs

ios/Ember/Features/Auth/
  AuthViewModel.swift            # @Observable ViewModel: form state, validation, auth actions
  LoginView.swift                # Login screen (replaces LoginPlaceholderView)
  SignUpView.swift               # Sign-up screen

ios/Ember/App/
  EmberApp.swift                 # Root view switching on authViewModel.isAuthenticated

ios/Ember/Features/Profile/
  ProfilePlaceholderView.swift   # Added "Sign Out" button for dev testing

ios/EmberTests/Core/Auth/
  KeychainTokenStoreTests.swift  # 9 tests for Keychain CRUD
  AuthServiceTests.swift         # 15 tests for HTTP calls, error mapping, token storage

ios/EmberTests/Features/Auth/
  AuthViewModelTests.swift       # 19 tests for form validation and auth state transitions

ios/EmberTests/Mocks/
  MockAuthService.swift          # Enhanced with signUp, isAuthenticated, call tracking
```

---

## API Reference

See [`docs/04-veri-api.md`](../04-veri-api.md) for the full backend API contract. This feature calls three existing endpoints. All are public (`requiresAuth: false` in `APIEndpoint`).

### `POST /api/v1/auth/login`

**Request Body**:
```json
{ "email": "user@example.com", "password": "secret123" }
```

**Response** (200):
```json
{
  "token": "<cognito_id_token>",
  "refresh_token": "<cognito_refresh_token>",
  "user": { "id": "usr_...", "email": "...", "name": "...", "onboarding_completed": false, ... }
}
```

**Error Responses**:

| Status | When | iOS mapping |
|--------|------|-------------|
| 400 | Validation error | `AuthError.signInFailed(detail)` |
| 401 | Wrong credentials | `AuthError.signInFailed("Invalid email or password")` |
| 429 | Rate limited | `AuthError.signInFailed("Too many attempts. Please try again later.")` |
| 500/503 | Server error | `AuthError.signInFailed("Something went wrong. Please try again.")` |

### `POST /api/v1/auth/register`

**Request Body**:
```json
{ "email": "user@example.com", "password": "secret123", "name": "Alex" }
```

**Response** (201): Same structure as login response.

**Error Responses**:

| Status | Body contains | iOS mapping |
|--------|---------------|-------------|
| 400 | `"already exists"` | `AuthError.signUpFailed("An account with this email already exists")` |
| 400 | `"Password"` | `AuthError.signUpFailed("Password does not meet requirements")` |
| 400 | other | `AuthError.signUpFailed(detail)` |

### `POST /api/v1/auth/refresh`

**Request Body**:
```json
{ "refresh_token": "<cognito_refresh_token>" }
```

Note: the key is `refresh_token` (snake_case). `AuthService` uses `JSONEncoder.ember` which applies `.convertToSnakeCase`.

**Response** (200):
```json
{ "token": "<new_cognito_id_token>" }
```

**Error Responses**:

| Status | When | iOS mapping |
|--------|------|-------------|
| 401 | Refresh token expired or invalid | `AuthError.tokenUnavailable` |

---

## iOS Implementation

### KeychainTokenStore

`KeychainTokenStore` is a `final class` marked `@unchecked Sendable`. The `@unchecked` annotation is safe because Apple's `SecItem*` APIs are thread-safe.

Each token is stored as a `kSecClassGenericPassword` Keychain item:
- `kSecAttrService`: `"com.ember.auth"` (constant, shared for both items)
- `kSecAttrAccount`: `"accessToken"` or `"refreshToken"` (distinguishes the two items)
- `kSecAttrAccessible`: `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly` — tokens survive device restart (after first unlock) and are never backed up to iCloud or migrated to a new device.

The `saveItem(account:value:)` private method attempts `SecItemUpdate` first. If that returns `errSecItemNotFound`, it calls `SecItemAdd`. Any other error throws `AuthError.keychainError`. `readItem` returns `nil` on `errSecItemNotFound` — absence of a token is not an error.

A public `updateAccessToken(_:)` method is available for the refresh flow, allowing `AuthService` to update only the access token without touching the refresh token (Cognito's `REFRESH_TOKEN_AUTH` flow issues only a new access token).

### AuthService

`AuthService` is a `final class` conforming to `AuthServiceProtocol`. It uses `URLSession.shared` with no additional configuration.

**Protocol changes from P03-01/P03-02:**
- Added `signUp(email:password:name:) async throws`
- Added `var isAuthenticated: Bool { get }` (computed; reads `KeychainTokenStore.hasTokens`)

**Error mapping:** Each method maps HTTP status codes to `AuthError` cases with user-facing messages. Network transport errors (thrown by `URLSession`) are caught and mapped to `AuthError.signInFailed("Connection failed. Please check your internet.")` or the equivalent sign-up version.

**`getAccessToken()` does not validate token expiry.** It reads from Keychain and returns. If the token is expired, the next `APIClient` call receives a 401 and triggers the `refreshToken()` path automatically.

**`signOut()` makes no backend call.** JWTs are stateless; discarding the tokens from Keychain is sufficient. The backend has no session to invalidate.

**Cached user:** After sign-in or sign-up, the `UserResponse` from the response is cached in memory (`private var cachedUser: UserResponse?`). `getCurrentUser()` returns this cache. It is an implementation method, not on the protocol.

### AuthViewModel

`AuthViewModel` is an `@Observable final class`. It is injected into the SwiftUI view hierarchy from `EmberApp` via `.environment(authViewModel)` and accessed in views with `@Environment(AuthViewModel.self)`.

**State properties:**
```swift
var email: String = ""
var password: String = ""
var name: String = ""
var confirmPassword: String = ""
var isLoading: Bool = false
var errorMessage: String? = nil
var isShowingSignUp: Bool = false
var isAuthenticated: Bool = false
```

**Computed validation:**
- `isSignInFormValid`: email non-empty + contains `@`, password non-empty
- `isSignUpFormValid`: email valid + password >= 8 chars + `confirmPassword == password` + name non-empty
- `passwordsDoNotMatch`: `!confirmPassword.isEmpty && confirmPassword != password` — used by `SignUpView` to show the inline validation message

**`signIn()` and `signUp()`** both trim and lowercase the email before passing it to `AuthService`. On success, `isAuthenticated = true` and a success haptic fires. On failure, `errorMessage` is set with the `localizedDescription` of the thrown error, and an error haptic fires.

**`signOut()`** calls `authService.signOut()`, sets `isAuthenticated = false`, and resets all form fields to empty strings.

### LoginView and SignUpView

Both views use `@Environment(AuthViewModel.self)` to access the shared ViewModel. Neither view creates its own ViewModel instance.

`LoginView` shows email + password fields and a "Sign In" pill button (full-width, 52pt, corner radius `.emberRadius28`). The button is disabled when `!viewModel.isSignInFormValid || viewModel.isLoading`. When loading, a `ProgressView()` replaces the button label.

`SignUpView` adds Name and Confirm Password fields. The Confirm Password `SecureField` shows a `Text("Passwords do not match")` in `Color.emberError` below it when `viewModel.passwordsDoNotMatch` is true. The "Create Account" button guards on `isSignUpFormValid`.

Both views use `.alert` bound to `viewModel.errorMessage != nil` for error display. The alert "OK" button calls `viewModel.clearError()`.

**Navigation between the two screens** is controlled by `viewModel.isShowingSignUp`. `EmberApp` renders `SignUpView` or `LoginView` based on this flag. The transition is a standard SwiftUI content replacement (no push, no sheet).

### EmberApp Changes

`@AppStorage("isAuthenticated")` is removed. The root view branch now reads:

```swift
if !authViewModel.isAuthenticated {
    if authViewModel.isShowingSignUp { SignUpView() }
    else { LoginView() }
} else if !hasCompletedOnboarding {
    OnboardingPlaceholderView()
} else {
    MainTabView()
}
```

`authViewModel` is a `@State private var` on `EmberApp`, initialized once at app launch. It is passed into the environment so all auth-related views can access it without prop drilling. `@AppStorage("hasCompletedOnboarding")` remains for now and is replaced when the real onboarding feature lands.

### Sign-Out Integration Point

`ProfilePlaceholderView` has a "Sign Out" button added for dev testing. It accesses `AuthViewModel` via `@Environment(AuthViewModel.self)` and calls `Task { await authViewModel.signOut() }`. The real profile screen (a future feature) will replace this placeholder entirely.

---

## Testing

### Coverage Summary

| File | Tests | What Is Covered |
|------|-------|-----------------|
| `KeychainTokenStoreTests.swift` | 9 | Save, read, overwrite, clear, `hasTokens` |
| `AuthServiceTests.swift` | 15 | HTTP request body format, status code → error mapping, token save, `isAuthenticated`, refresh flow |
| `AuthViewModelTests.swift` | 19 | Form validation, email trimming/lowercasing, loading state, `isAuthenticated` transitions, sign-out reset |
| **Total** | **43** | |

All tests use Swift Testing (`import Testing`).

**Keychain tests** require a real simulator or device — Keychain is unavailable in pure unit test hosts without entitlements. Tests that touch `KeychainTokenStore` directly will be skipped in environments where the Keychain is inaccessible.

**`AuthService` tests** use `MockURLProtocol` (from P03-02) to intercept HTTP requests. The `MockURLProtocol.requestHandler` closure is set per-test to return a controlled `HTTPURLResponse` and body data. This lets tests verify the exact JSON keys sent in request bodies (e.g., confirming `"refresh_token"` snake_case in the refresh request).

**`AuthViewModel` tests** use `MockAuthService` (enhanced in this feature with `signUp`, `isAuthenticated`, and call tracking properties). No network calls are made.

### Running Tests

```bash
cd ios
xcodebuild test -scheme Ember -destination "platform=iOS Simulator,name=iPhone 16"
```

---

## Known Limitations

- **No forgot-password / password reset**: This is deferred to Phase 4. Users who forget their password have no self-service recovery path in the app.
- **No social sign-in**: Only email/password. Apple Sign-In and Google Sign-In are out of scope for this phase.
- **No email verification UI**: The backend auto-confirms new users (MVP mode). If auto-confirmation is ever disabled in Cognito, the iOS app has no screen to handle an "email not confirmed" state.
- **`hasCompletedOnboarding` still uses `@AppStorage`**: The onboarding completion flag remains in `UserDefaults` (unencrypted). It is not a sensitive credential, so this is acceptable until the real onboarding feature replaces it.
- **Keychain not available in some CI contexts**: Tests that use `KeychainTokenStore` directly require a simulator or device with Keychain entitlements. Pure unit test hosts in restricted CI environments will skip these tests.
- **Sign-out is client-side only**: Tokens are deleted from Keychain but the backend is not notified. The Cognito refresh token technically remains valid until its natural expiry. Revoking tokens server-side requires a separate `POST /api/v1/auth/logout` endpoint, which does not yet exist.

---

## Extending This Feature

### Adding forgot-password flow

The backend will need a `POST /api/v1/auth/forgot-password` endpoint. On the iOS side:
1. Add `.forgotPassword` to `APIEndpoint` (in `ios/Ember/Core/Network/APIEndpoint.swift`).
2. Add a `forgotPassword(email:) async throws` method to `AuthServiceProtocol` and implement it in `AuthService` using `URLSession` (same pattern as the existing three auth methods, since it is a public endpoint).
3. Add a `ForgotPasswordView` in `ios/Ember/Features/Auth/` and wire it from `LoginView`.

### Adding server-side sign-out (token revocation)

1. Add `POST /api/v1/auth/logout` to the backend.
2. Add `.logout` to `APIEndpoint` with `requiresAuth: true`.
3. In `AuthService.signOut()`, call `APIClient.shared.requestVoid(endpoint: .logout)` before clearing Keychain tokens. Swallow any network error — clearing local tokens is the critical operation.

### Adding a new field to sign-up (e.g., phone number)

1. Add the field to `AuthViewModel` and update `isSignUpFormValid` if validation is needed.
2. Add the field to `SignUpView`.
3. Pass the field to `authService.signUp(...)` — update the method signature in `AuthServiceProtocol`, `AuthService`, and `MockAuthService`.
4. Update the JSON body in `AuthService.signUp()` to include the new key.
5. Confirm the backend's `POST /api/v1/auth/register` accepts the new field.

### Testing a new auth error scenario

Use `MockURLProtocol.requestHandler` to return the desired HTTP status code and JSON body, then assert that `AuthService` maps it to the expected `AuthError` case. See `AuthServiceTests.swift` for the existing pattern.

---

## Related Documentation

- [Database Schema and API Contracts](../04-veri-api.md)
- [Mobile Screens and Navigation](../07-mobil.md)
- [Security and Performance](../08-guvenlik-performans.md)
- [iOS Standards](../standards/ios.md)
- [iOS Scaffold](ios-scaffold.md)
- [iOS Network Layer](ios-network-layer.md)
