# Feature Spec: P03-03 -- iOS Cognito Auth

**Feature ID**: P03-03
**Phase**: 3
**Layer**: ios
**GitHub Issue**: #19
**Date**: 2026-03-13
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature implements the complete authentication flow for the Ember iOS app. It replaces the stub `AuthService` (from P03-01) with a production implementation that calls the backend's auth endpoints (`/api/v1/auth/register`, `/api/v1/auth/login`, `/api/v1/auth/refresh`) via the `APIClient` (from P03-02). It stores JWT tokens securely in the iOS Keychain, provides an `@Observable AuthViewModel` that drives the login and sign-up UI, and wires the `AuthServiceProtocol` methods (`getAccessToken`, `refreshToken`) so that `APIClient`'s automatic 401 retry works end-to-end. It replaces `LoginPlaceholderView` and `OnboardingPlaceholderView` with real authentication screens (login and sign-up forms). It replaces the `@AppStorage("isAuthenticated")` mechanism in `EmberApp` with Keychain-backed token presence checking.

### Why It Exists

Every feature after this (character list, chat, memory display, profile) makes authenticated API calls. Without a working auth flow, the APIClient's `getAccessToken()` throws `.notImplemented` and no network requests succeed. This feature is the first to connect the iOS app to the live backend.

### Dependencies

- **P03-01** (ios-scaffold) -- provides `AuthServiceProtocol` stub, `AuthError` enum, `EmberApp` with `@AppStorage` auth state, `LoginPlaceholderView`, `OnboardingPlaceholderView`, `AppContainer`, design system constants.
- **P03-02** (ios-network-layer) -- provides `APIClient` with `request<T>`, `requestVoid`, `streamSSE`, `APIEndpoint` enum (including `.register`, `.login`, `.refreshToken` cases), `APIError`, and the 401 retry logic that calls `AuthServiceProtocol.refreshToken()`.
- **P01-04** (auth-endpoints, backend) -- provides the backend endpoints: `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`.

### What This Feature Does NOT Do

- It does not implement the onboarding questionnaire flow. The `OnboardingPlaceholderView` remains as-is (with its dev-mode "Complete Onboarding" button). The auth flow skips to onboarding after sign-up; the real onboarding screens are a separate feature.
- It does not implement social sign-in (Apple, Google). Only email/password.
- It does not implement "forgot password" / password reset. That is a Phase 4 feature.
- It does not add the Amplify SDK. The backend already manages all Cognito operations via boto3. The iOS app authenticates through the backend's REST endpoints and stores the returned tokens in Keychain. Adding Amplify is unnecessary and would require config files (`amplifyconfiguration.json`) that add complexity with no benefit.
- It does not implement email verification UI. The backend auto-confirms users during registration (MVP).

### Architecture Decision: Backend Auth Endpoints vs. Amplify SDK

The issue title says "AWS Amplify Cognito integration." After analysis, the correct approach is to call the **backend auth endpoints** rather than using the Amplify iOS SDK directly:

1. The backend's `POST /api/v1/auth/register` does more than Cognito sign-up -- it creates Profile, Character, and Conversation rows in the database. Calling Cognito directly from iOS would skip this.
2. `docs/08-guvenlik-performans.md` states: "API key'ler hicbir zaman mobil uygulamada saklanmaz. Tum AI cagrilari backend uzerinden yapilir." Only JWT tokens and the backend API URL are stored on the client.
3. The Amplify SDK was intentionally omitted from P03-01 because it requires `amplifyconfiguration.json`. The P03-01 review documented this as a correct deviation.
4. The backend already handles Cognito user pools, auto-confirmation, and token issuance. The iOS app simply POSTs credentials to the backend and receives JWT tokens.

The `AuthServiceProtocol` method names remain the same (`signIn`, `signUp`, `signOut`, etc.) but the implementation calls `APIClient` instead of `Amplify.Auth`.

---

## 2. Data Models

No database changes. This is an iOS-only feature.

The following response models must be created as Swift `Codable` structs to decode the backend's auth endpoint responses.

### AuthResponse

Maps to the backend's `AuthResponse` Pydantic model (see `backend/app/schemas/auth.py`).

```
struct AuthResponse: Codable {
    let token: String           // Cognito ID token (JWT)
    let refreshToken: String    // Cognito refresh token
    let user: UserResponse
}
```

### UserResponse

Maps to the backend's `UserResponse` Pydantic model.

```
struct UserResponse: Codable, Identifiable {
    let id: String
    let email: String
    let name: String
    let avatarUrl: String?
    let timezone: String
    let preferredLanguage: String
    let onboardingCompleted: Bool
    let subscriptionTier: String
    let createdAt: String
}
```

### RefreshResponse

Maps to the backend's `RefreshResponse` Pydantic model.

```
struct RefreshResponse: Codable {
    let token: String
}
```

These structs are decoded using `JSONDecoder.ember` which converts `snake_case` keys to `camelCase` properties automatically.

---

## 3. API Endpoints

No new API endpoints. This feature calls three existing backend endpoints that are already defined in `APIEndpoint` (from P03-02):

| Endpoint Case | Backend Route | Used For |
|---|---|---|
| `.register` | `POST /api/v1/auth/register` | Sign up a new user |
| `.login` | `POST /api/v1/auth/login` | Sign in an existing user |
| `.refreshToken` | `POST /api/v1/auth/refresh` | Exchange refresh token for new access token |

All three are public endpoints (`requiresAuth: false`).

Request/response contracts are defined in `docs/04-veri-api.md` and implemented in `backend/app/schemas/auth.py`. The iOS models in Section 2 mirror these exactly.

---

## 4. Backend Logic

Not applicable. This is an iOS-only feature.

---

## 5. iOS Screens and Components

### 5.1 KeychainTokenStore

**File**: `ios/Ember/Core/Auth/KeychainTokenStore.swift` (CREATE)

A secure token storage layer using the iOS Keychain Services API. This replaces `@AppStorage` (which uses `UserDefaults`, unencrypted) for token storage.

**Properties (all private, accessed via methods)**:
- Access token (Cognito ID token)
- Refresh token

**Public Interface**:

```
final class KeychainTokenStore: @unchecked Sendable {
    static let shared = KeychainTokenStore()

    func saveTokens(accessToken: String, refreshToken: String) throws
    func getAccessToken() -> String?
    func getRefreshToken() -> String?
    func clearTokens()

    /// Returns true if both access token and refresh token are stored
    var hasTokens: Bool { get }
}
```

**Implementation Details**:

- Uses `Security` framework (`SecItemAdd`, `SecItemCopyMatching`, `SecItemUpdate`, `SecItemDelete`).
- Keychain item attributes:
  - `kSecClass`: `kSecClassGenericPassword`
  - `kSecAttrService`: `"com.ember.auth"` (constant string)
  - `kSecAttrAccount`: `"accessToken"` or `"refreshToken"` (distinguishes the two items)
  - `kSecAttrAccessible`: `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly` -- tokens are available after device unlock and are not backed up to iCloud or transferred to a new device.
- `saveTokens` saves both tokens atomically. If either keychain operation fails, throws `AuthError.keychainError`.
- `getAccessToken` and `getRefreshToken` return `nil` if the item does not exist (not an error).
- `clearTokens` deletes both items. Errors are silently ignored (best-effort cleanup).
- `@unchecked Sendable` is safe because Keychain operations are thread-safe at the OS level.

**Why not use a third-party Keychain wrapper**: The operations needed (save string, read string, delete) are simple enough that a wrapper adds a dependency without value. Four functions wrapping `SecItem*` calls is sufficient.

### 5.2 AuthService (Full Implementation)

**File**: `ios/Ember/Core/Auth/AuthService.swift` (MODIFY -- replace stub)

Replaces the stub implementation with a production `AuthService` that calls backend auth endpoints via `APIClient`.

```
final class AuthService: AuthServiceProtocol, @unchecked Sendable {
    static let shared = AuthService()

    private let tokenStore: KeychainTokenStore
    private var _apiClientProvider: (() -> APIClientProtocol)?
}
```

**Circular Dependency Resolution**:

`AuthService` and `APIClient` have a circular dependency: `APIClient` calls `authService.getAccessToken()` and `authService.refreshToken()`, while `AuthService` needs `APIClient` to call the auth endpoints. Resolution:

- `AuthService` does NOT receive `APIClient` in its constructor. Instead, it builds its own `URLSession` requests for the three public auth endpoints (register, login, refresh). These endpoints do not require authentication, so no `Authorization` header is needed, and the 401 retry logic is irrelevant.
- `AuthService` has its own private `baseURL` property (same source as `APIClient`: `ProcessInfo.processInfo.environment["API_BASE_URL"]` or `"https://api.ember.ai"`).
- `AuthService` uses `JSONEncoder.ember` and `JSONDecoder.ember` for encoding/decoding.

This avoids the circular dependency entirely: `AuthService` makes its own HTTP calls for auth operations, and `APIClient` calls `AuthService` only for `getAccessToken()` and `refreshToken()`.

**Protocol Methods**:

`configure()`:
- No-op. Amplify is not used. The Keychain is always ready.

`signIn(username:password:) async throws`:
- Builds a `POST` request to `{baseURL}/api/v1/auth/login` with body `{"email": username, "password": password}`.
- Decodes the response as `AuthResponse`.
- On success: saves `token` and `refreshToken` to `KeychainTokenStore`.
- On HTTP error: maps the backend error to `AuthError`:
  - 401 -> `AuthError.signInFailed("Invalid email or password")`
  - 400 -> `AuthError.signInFailed(detail)` where `detail` is from the response body
  - 429 -> `AuthError.signInFailed("Too many attempts. Please try again later.")`
  - 500/503 -> `AuthError.signInFailed("Something went wrong. Please try again.")`
  - Network error -> `AuthError.signInFailed("Connection failed. Please check your internet.")`

`signUp(email:password:name:) async throws`:
- NOTE: This method is NEW. The existing `AuthServiceProtocol` does not have it. It must be added to the protocol.
- Builds a `POST` request to `{baseURL}/api/v1/auth/register` with body `{"email": email, "password": password, "name": name}`.
- Decodes the response as `AuthResponse`.
- On success: saves tokens to `KeychainTokenStore`.
- On HTTP error: maps the backend error to `AuthError`:
  - 400 with "already exists" -> `AuthError.signUpFailed("An account with this email already exists")`
  - 400 with "Password" -> `AuthError.signUpFailed("Password does not meet requirements")`
  - Other errors: same mapping as `signIn`.

`signOut() async`:
- Clears tokens from `KeychainTokenStore`.
- No backend call needed (JWT-based auth, stateless). The tokens simply become unused.

`getAccessToken() async throws -> String`:
- Reads the access token from `KeychainTokenStore`.
- If nil, throws `AuthError.tokenUnavailable`.
- Returns the token string.
- NOTE: This does NOT validate whether the token is expired. If it is expired, the APIClient will get a 401 and call `refreshToken()`.

`refreshToken() async throws -> String`:
- Reads the refresh token from `KeychainTokenStore`.
- If nil, throws `AuthError.tokenUnavailable`.
- Builds a `POST` request to `{baseURL}/api/v1/auth/refresh` with body `{"refresh_token": refreshTokenValue}`.
- Decodes the response as `RefreshResponse`.
- On success: updates the access token in `KeychainTokenStore` (the refresh token does not change during a Cognito REFRESH_TOKEN_AUTH flow).
- Returns the new access token.
- On HTTP error (401): throws `AuthError.tokenUnavailable` (the refresh token is expired or invalid, user must sign in again).

`getCurrentUser() async throws -> UserResponse`:
- NOTE: This method is NEW. Added to `AuthServiceProtocol`.
- This method is a convenience: it calls `GET /api/v1/profile` to fetch the current user's profile.
- However, to avoid the circular dependency, the user profile is cached locally when sign-in / sign-up succeeds. `getCurrentUser()` returns the cached `UserResponse`. If no cache exists, throws `AuthError.tokenUnavailable`.
- The cached user is stored as encoded JSON in a private property (in-memory only, not persisted). It is cleared on sign-out.

### 5.3 AuthServiceProtocol (Enhanced)

**File**: `ios/Ember/Core/Auth/AuthService.swift` (same file, protocol section)

The existing protocol is modified to add the new methods needed for auth:

```
protocol AuthServiceProtocol: AnyObject, Sendable {
    func configure()
    func signIn(username: String, password: String) async throws
    func signUp(email: String, password: String, name: String) async throws
    func signOut() async
    func getAccessToken() async throws -> String
    func refreshToken() async throws -> String

    /// Returns true if stored tokens exist (may be expired).
    var isAuthenticated: Bool { get }
}
```

Changes from existing protocol:
- Added `signUp(email:password:name:)`.
- Added `var isAuthenticated: Bool { get }`.
- Removed `getCurrentUser()` from the protocol (it was never on the protocol; it is an implementation detail).

### 5.4 AuthError (Enhanced)

**File**: `ios/Ember/Core/Auth/AuthError.swift` (MODIFY)

New cases needed:

```
enum AuthError: LocalizedError {
    case signInFailed(String)
    case signUpFailed(String)
    case tokenUnavailable
    case keychainError
    case notImplemented

    var errorDescription: String? {
        switch self {
        case .signInFailed(let message):
            return message
        case .signUpFailed(let message):
            return message
        case .tokenUnavailable:
            return "Your session has expired. Please sign in again."
        case .keychainError:
            return "Failed to save authentication data securely."
        case .notImplemented:
            return "Authentication is not yet implemented"
        }
    }
}
```

Changes from existing enum:
- Added `.signUpFailed(String)`.
- Added `.keychainError`.
- Changed `.tokenUnavailable` error message to be more user-friendly.

### 5.5 Auth Response Models

**File**: `ios/Ember/Core/Models/AuthModels.swift` (CREATE)

Contains `AuthResponse`, `UserResponse`, and `RefreshResponse` as defined in Section 2. These are `Codable` structs used only by `AuthService` and `AuthViewModel`.

### 5.6 AuthViewModel

**File**: `ios/Ember/Features/Auth/AuthViewModel.swift` (CREATE)

An `@Observable` ViewModel shared between the login and sign-up views. Injected into the view hierarchy via `@Environment` from `EmberApp`.

```
@Observable
final class AuthViewModel {
    // Form state
    var email: String = ""
    var password: String = ""
    var name: String = ""               // used only for sign-up
    var confirmPassword: String = ""    // used only for sign-up

    // UI state
    var isLoading: Bool = false
    var errorMessage: String? = nil
    var isShowingSignUp: Bool = false   // toggles between login and sign-up

    // Computed
    var isSignInFormValid: Bool { ... }
    var isSignUpFormValid: Bool { ... }

    private let authService: AuthServiceProtocol

    init(authService: AuthServiceProtocol = AuthService.shared) { ... }

    func signIn() async { ... }
    func signUp() async { ... }
    func clearError() { ... }
}
```

**`isSignInFormValid`**:
- Email is not empty and contains `@`.
- Password is not empty.

**`isSignUpFormValid`**:
- Email is not empty and contains `@`.
- Password length >= 8 characters.
- `confirmPassword` matches `password`.
- Name is not empty.

**`signIn()` method**:
1. Set `isLoading = true`, `errorMessage = nil`.
2. Call `authService.signIn(username: email.lowercased().trimmingCharacters(in: .whitespaces), password: password)`.
3. On success: `isLoading = false`. The `EmberApp` observes `authService.isAuthenticated` and switches from the login view to the main content automatically.
4. On failure: `isLoading = false`, `errorMessage = error.localizedDescription`.
5. Call `HapticManager.notification(.error)` on failure, `HapticManager.notification(.success)` on success.

**`signUp()` method**:
1. Set `isLoading = true`, `errorMessage = nil`.
2. Call `authService.signUp(email: email.lowercased().trimmingCharacters(in: .whitespaces), password: password, name: name.trimmingCharacters(in: .whitespaces))`.
3. On success: `isLoading = false`. Same auto-transition as `signIn`.
4. On failure: `isLoading = false`, `errorMessage = error.localizedDescription`.
5. Haptics: same as `signIn`.

**`clearError()`**: Sets `errorMessage = nil`.

### 5.7 LoginView

**File**: `ios/Ember/Features/Auth/LoginView.swift` (CREATE -- replaces `LoginPlaceholderView`)

The real login screen. `LoginPlaceholderView` is deleted.

**Navigation**: This is the root view shown when `authService.isAuthenticated` is `false` in `EmberApp`.

**UI Layout** (top to bottom):
1. Ember logo/icon area: sparkles SF Symbol with gradient, or app name "Ember" in `.emberLargeTitle` font.
2. "Welcome Back" title in `.emberTitle`.
3. "Sign in to continue" subtitle in `.emberSecondary`, color `.emberTextSecondary`.
4. Email `TextField`:
   - Placeholder: "Email"
   - `keyboardType: .emailAddress`
   - `textContentType: .emailAddress`
   - `autocapitalization: .never`
   - `autocorrectionDisabled: true`
   - Background: `Color.emberSurface2`
   - Corner radius: `.emberRadius12`
   - Padding: `.emberSpacing16` horizontal inside
   - Height: 52pt
5. Password `SecureField`:
   - Placeholder: "Password"
   - `textContentType: .password`
   - Same styling as email field
6. "Sign In" button:
   - Full width, height 52pt
   - Background: `Color.emberPrimary` (disabled: `Color.emberTextDisabled`)
   - Corner radius: `.emberRadius28`
   - Font: `.emberHeadline`
   - Disabled when `!viewModel.isSignInFormValid` or `viewModel.isLoading`
   - Shows `ProgressView()` when `isLoading`, hides "Sign In" text
   - Action: `Task { await viewModel.signIn() }`
7. "Don't have an account? **Sign Up**" text link:
   - Tapping sets `viewModel.isShowingSignUp = true`
   - "Sign Up" portion in `Color.emberPrimary`, rest in `.emberTextSecondary`
   - Font: `.emberSecondary`

**Error Display**:
- `.alert("Error", isPresented:)` bound to `viewModel.errorMessage != nil`
- "OK" button calls `viewModel.clearError()`

**Accessibility**:
- `.accessibilityLabel("Email address")` on email field
- `.accessibilityLabel("Password")` on password field
- `.accessibilityLabel("Sign In")` on sign-in button
- `.accessibilityLabel("Sign Up")` on sign-up link

**Background**: `Color.emberBackground.ignoresSafeArea()`

**Keyboard**: `.submitLabel(.go)` on password field. Pressing return on password field triggers sign-in if form is valid.

### 5.8 SignUpView

**File**: `ios/Ember/Features/Auth/SignUpView.swift` (CREATE)

The sign-up screen, shown when `viewModel.isShowingSignUp` is `true`.

**Navigation**: Shown as a full-screen replacement of `LoginView` (not a sheet or push). Toggled via `viewModel.isShowingSignUp`. Alternatively, `LoginView` and `SignUpView` can be within the same view using conditional rendering -- the developer chooses the cleaner approach. The spec requires that the transition is smooth (not jarring).

**UI Layout** (top to bottom):
1. Same header area as LoginView (logo + app name).
2. "Create Account" title in `.emberTitle`.
3. "Join Ember to get started" subtitle in `.emberSecondary`.
4. Name `TextField`:
   - Placeholder: "Full Name"
   - `textContentType: .name`
   - Same styling as LoginView fields
5. Email `TextField`:
   - Same configuration as LoginView
6. Password `SecureField`:
   - Placeholder: "Password (8+ characters)"
   - `textContentType: .newPassword`
7. Confirm Password `SecureField`:
   - Placeholder: "Confirm Password"
   - `textContentType: .newPassword`
   - If `confirmPassword` is non-empty and does not match `password`, show a small error text below: "Passwords do not match" in `Color.emberError`, font `.emberCaption`.
8. "Create Account" button:
   - Same styling as "Sign In" button
   - Disabled when `!viewModel.isSignUpFormValid` or `viewModel.isLoading`
   - Action: `Task { await viewModel.signUp() }`
9. "Already have an account? **Sign In**" text link:
   - Tapping sets `viewModel.isShowingSignUp = false`

**Error Display**: Same `.alert` pattern as LoginView.

**Accessibility**: Labels on all fields and buttons.

**Background**: `Color.emberBackground.ignoresSafeArea()`

### 5.9 EmberApp (Modified)

**File**: `ios/Ember/App/EmberApp.swift` (MODIFY)

Replace the `@AppStorage("isAuthenticated")` mechanism with Keychain-backed auth state.

Changes:
- Remove `@AppStorage("isAuthenticated") private var isAuthenticated = false`.
- Add `@State private var authViewModel = AuthViewModel()`.
- The `AuthService.shared.isAuthenticated` property (which checks `KeychainTokenStore.hasTokens`) drives the auth/non-auth view switch.
- The `authViewModel` is passed into the environment so `LoginView` and `SignUpView` can access it.

Updated body logic:
```
if !AuthService.shared.isAuthenticated {
    // LoginView or SignUpView based on authViewModel.isShowingSignUp
    Group {
        if authViewModel.isShowingSignUp {
            SignUpView()
        } else {
            LoginView()
        }
    }
    .environment(authViewModel)
} else if !hasCompletedOnboarding {
    OnboardingPlaceholderView()
} else {
    MainTabView()
}
```

Note: `@AppStorage("hasCompletedOnboarding")` remains for now. It will be replaced when the real onboarding feature is implemented.

The `AuthService.shared.configure()` call in `init()` remains (now a no-op, but keeps the hook for future use).

**Auth State Reactivity**:

The challenge: `AuthService.isAuthenticated` is a computed property on a `Sendable` class, not an `@Observable`. To make SwiftUI react to auth state changes:

- `AuthViewModel` has an `isAuthenticated: Bool` property that is set after successful sign-in/sign-up and cleared on sign-out.
- `EmberApp` observes `authViewModel.isAuthenticated` instead of calling `AuthService.shared.isAuthenticated` directly.
- When `authViewModel.signIn()` or `authViewModel.signUp()` succeeds, it sets `self.isAuthenticated = true`.
- For sign-out (called from Settings or Profile), `AuthViewModel` exposes a `signOut()` method that clears tokens and sets `isAuthenticated = false`.
- On app launch, `AuthViewModel.init()` checks `AuthService.shared.isAuthenticated` to set the initial value.

Updated `AuthViewModel` properties:
```
var isAuthenticated: Bool = false    // drives EmberApp view switching
```

Updated `AuthViewModel.init()`:
```
init(authService: AuthServiceProtocol = AuthService.shared) {
    self.authService = authService
    self.isAuthenticated = authService.isAuthenticated
}
```

### 5.10 AppContainer (Modified)

**File**: `ios/Ember/App/AppContainer.swift` (MODIFY)

No structural change needed. `AppContainer` already holds `authService: AuthServiceProtocol`. The updated `AuthService.shared` will be injected automatically via the default parameter.

### 5.11 Sign-Out Integration Point

Sign-out is triggered from the Profile tab (ProfilePlaceholderView for now). The spec defines the `AuthViewModel.signOut()` method but does NOT modify `ProfilePlaceholderView` to add a sign-out button -- that is a future feature when the real profile screen is built. For dev testing, the following is added:

**File**: `ios/Ember/Features/Profile/ProfilePlaceholderView.swift` (MODIFY)

Add a "Sign Out" button below the existing content:

```
Button {
    Task {
        await authViewModel.signOut()
    }
} label: {
    Text("Sign Out")
        .font(.emberHeadline)
        .foregroundStyle(Color.emberError)
}
.accessibilityLabel("Sign Out")
```

This requires `ProfilePlaceholderView` to access `AuthViewModel` via `@Environment(AuthViewModel.self)`.

---

## 6. Android Screens and Components

Not applicable. This is an iOS-only feature.

---

## 7. Test Plan

### Unit Tests

All tests use Swift Testing (`import Testing`) as the primary framework.

#### KeychainTokenStore Tests

**File**: `ios/EmberTests/Core/Auth/KeychainTokenStoreTests.swift`

| # | Scenario | Expected |
|---|----------|----------|
| 1 | Save tokens then read access token | Returns saved access token |
| 2 | Save tokens then read refresh token | Returns saved refresh token |
| 3 | Read access token when nothing saved | Returns nil |
| 4 | Read refresh token when nothing saved | Returns nil |
| 5 | `hasTokens` when tokens saved | Returns true |
| 6 | `hasTokens` when no tokens saved | Returns false |
| 7 | Clear tokens then read | Both return nil, `hasTokens` is false |
| 8 | Save tokens twice (overwrite) | Second values are returned |

Note: Keychain tests must run on a simulator or device, not in a pure unit test context. If Keychain is unavailable (CI without entitlements), these tests should be skipped with `#if !targetEnvironment(simulator)` or marked as integration tests.

#### AuthService Tests

**File**: `ios/EmberTests/Core/Auth/AuthServiceTests.swift`

Uses `MockURLProtocol` (from P03-02) to intercept HTTP requests. Uses a real or mock `KeychainTokenStore`.

| # | Scenario | Expected |
|---|----------|----------|
| 1 | `signIn` with 200 response | Tokens saved to keychain, `isAuthenticated` true |
| 2 | `signIn` with 401 response `{"detail":"Invalid email or password"}` | Throws `AuthError.signInFailed("Invalid email or password")` |
| 3 | `signIn` with 503 response | Throws `AuthError.signInFailed` with service unavailable message |
| 4 | `signIn` with network error | Throws `AuthError.signInFailed` with connection message |
| 5 | `signUp` with 201 response | Tokens saved, `isAuthenticated` true |
| 6 | `signUp` with 400 "already exists" | Throws `AuthError.signUpFailed` with existing account message |
| 7 | `signUp` with 400 "Password" | Throws `AuthError.signUpFailed` with password requirements message |
| 8 | `signOut` | Tokens cleared from keychain, `isAuthenticated` false |
| 9 | `getAccessToken` when token saved | Returns the token string |
| 10 | `getAccessToken` when no token | Throws `AuthError.tokenUnavailable` |
| 11 | `refreshToken` with 200 response | New access token saved, returns new token |
| 12 | `refreshToken` with 401 response | Throws `AuthError.tokenUnavailable` |
| 13 | `refreshToken` when no refresh token in keychain | Throws `AuthError.tokenUnavailable` |
| 14 | `signIn` request body has correct JSON keys (`email`, `password`) | Verified via MockURLProtocol |
| 15 | `signUp` request body has correct JSON keys (`email`, `password`, `name`) | Verified via MockURLProtocol |

#### AuthViewModel Tests

**File**: `ios/EmberTests/Features/Auth/AuthViewModelTests.swift`

Uses `MockAuthService` (from P03-02).

| # | Scenario | Expected |
|---|----------|----------|
| 1 | `signIn` success | `isLoading` becomes true then false, `isAuthenticated` true, `errorMessage` nil |
| 2 | `signIn` failure | `isLoading` false, `errorMessage` set, `isAuthenticated` false |
| 3 | `signUp` success | `isLoading` false, `isAuthenticated` true, `errorMessage` nil |
| 4 | `signUp` failure | `isLoading` false, `errorMessage` set |
| 5 | `isSignInFormValid` with valid email + password | Returns true |
| 6 | `isSignInFormValid` with empty email | Returns false |
| 7 | `isSignInFormValid` with empty password | Returns false |
| 8 | `isSignUpFormValid` with valid inputs | Returns true |
| 9 | `isSignUpFormValid` with short password (<8 chars) | Returns false |
| 10 | `isSignUpFormValid` with mismatched passwords | Returns false |
| 11 | `isSignUpFormValid` with empty name | Returns false |
| 12 | `clearError` resets errorMessage to nil | `errorMessage` is nil |
| 13 | `signIn` trims and lowercases email | MockAuthService receives trimmed lowercase email |
| 14 | `signOut` clears isAuthenticated | `isAuthenticated` is false |
| 15 | Initial `isAuthenticated` matches `authService.isAuthenticated` | ViewModel reads auth state from service on init |

#### MockAuthService Enhancement

**File**: `ios/EmberTests/Mocks/MockAuthService.swift` (MODIFY)

Add to existing mock:
- `var signInCallCount: Int = 0`
- `var signUpCallCount: Int = 0`
- `var lastSignInEmail: String?`
- `var lastSignInPassword: String?`
- `var lastSignUpEmail: String?`
- `var lastSignUpPassword: String?`
- `var lastSignUpName: String?`
- `var shouldThrowOnSignIn: Error?`
- `var shouldThrowOnSignUp: Error?`
- `var isAuthenticated: Bool = false`
- Implement `signUp(email:password:name:)` and `isAuthenticated` property.

---

## 8. Acceptance Criteria

1. Given the app launches for the first time (no tokens in Keychain), when the root view appears, then the login screen is displayed with email field, password field, sign-in button, and sign-up link.

2. Given the login screen is showing, when the user enters a valid email and password and taps "Sign In", then the app calls `POST /api/v1/auth/login`, stores the returned tokens in the iOS Keychain, and transitions to the onboarding placeholder (if onboarding is not completed) or the main tab view.

3. Given the login screen is showing, when the user enters invalid credentials and taps "Sign In", then an error alert appears with the message "Invalid email or password" and the user remains on the login screen.

4. Given the login screen is showing, when the user taps "Sign Up", then the sign-up form appears with name, email, password, and confirm password fields.

5. Given the sign-up form is showing, when the user fills in valid data and taps "Create Account", then the app calls `POST /api/v1/auth/register`, stores tokens in Keychain, and transitions to the onboarding placeholder.

6. Given the sign-up form is showing, when the user enters an email that already has an account, then an error alert appears with "An account with this email already exists".

7. Given the sign-up form is showing, when the user enters a password shorter than 8 characters, then the "Create Account" button is disabled.

8. Given the sign-up form is showing, when the passwords do not match, then a validation message "Passwords do not match" appears below the confirm password field and the button is disabled.

9. Given the user is authenticated and using the app, when the access token expires and the user makes an API request, then the `APIClient` receives a 401, calls `AuthService.refreshToken()` which calls `POST /api/v1/auth/refresh`, receives a new access token, stores it in Keychain, and retries the original request transparently.

10. Given the user is authenticated and the refresh token is also expired, when the `APIClient` retry calls `refreshToken()` and it fails, then the user is redirected to the login screen (tokens are cleared from Keychain).

11. Given the user taps "Sign Out" (from ProfilePlaceholderView), then tokens are cleared from Keychain and the app returns to the login screen.

12. Given tokens are stored in Keychain and the app is killed and relaunched, then the user is still authenticated (no re-login required) and the main tab view or onboarding screen is shown.

13. Given the sign-in or sign-up button is tapped, when the operation is in progress, then a loading spinner replaces the button text and the button is disabled.

14. Given a successful sign-in, then `.notification(.success)` haptic feedback is triggered.

15. Given a failed sign-in, then `.notification(.error)` haptic feedback is triggered.

16. Given all unit tests, when they are run, then all tests pass with zero failures.

17. Given the login screen, when VoiceOver is enabled, then all form fields and buttons are announced with correct labels.

18. Given the app is in dark mode (always), then the login and sign-up screens use design system colors from `Color+Ember.swift` with no light-mode artifacts.

---

## 9. File Manifest

```
iOS:
  CREATE  ios/Ember/Core/Auth/KeychainTokenStore.swift
  CREATE  ios/Ember/Core/Models/AuthModels.swift
  CREATE  ios/Ember/Features/Auth/AuthViewModel.swift
  CREATE  ios/Ember/Features/Auth/LoginView.swift
  CREATE  ios/Ember/Features/Auth/SignUpView.swift
  MODIFY  ios/Ember/Core/Auth/AuthService.swift
  MODIFY  ios/Ember/Core/Auth/AuthError.swift
  MODIFY  ios/Ember/App/EmberApp.swift
  MODIFY  ios/Ember/Features/Profile/ProfilePlaceholderView.swift
  DELETE  ios/Ember/Features/Auth/LoginPlaceholderView.swift

Tests:
  CREATE  ios/EmberTests/Core/Auth/KeychainTokenStoreTests.swift
  CREATE  ios/EmberTests/Core/Auth/AuthServiceTests.swift
  CREATE  ios/EmberTests/Features/Auth/AuthViewModelTests.swift
  MODIFY  ios/EmberTests/Mocks/MockAuthService.swift

Shared:
  CREATE  shared/feature-specs/ios-cognito-auth.md         (this file)
  CREATE  docs/pipeline/ios-cognito-auth-architect.handoff.md
```

| Action | Count |
|--------|-------|
| CREATE | 8 |
| MODIFY | 5 |
| DELETE | 1 |

---

## 10. Design Decisions and Rationale

### Why backend auth endpoints instead of Amplify SDK

Detailed in Section 1 under "Architecture Decision." Summary: the backend already manages Cognito and creates DB rows. Using Amplify on the client would duplicate Cognito calls, skip DB profile creation, and require distributing Cognito config files to the iOS app. The backend auth endpoints are the correct abstraction boundary.

### Why Keychain instead of @AppStorage

`@AppStorage` uses `UserDefaults`, which is unencrypted. `docs/standards/common.md` Section 8 explicitly states: "Token storage: iOS Keychain." JWT tokens are sensitive credentials and must not be stored in an unencrypted store.

### Why AuthService makes its own HTTP calls instead of using APIClient

Circular dependency: `APIClient` depends on `AuthService` for `getAccessToken()` and `refreshToken()`. If `AuthService` also depended on `APIClient`, initialization order and runtime calls would create a loop. Since the three auth endpoints are public (no `Authorization` header needed), `AuthService` can use `URLSession` directly with minimal boilerplate. This is simpler than lazy initialization or setter injection patterns.

### Why isAuthenticated on AuthViewModel instead of AuthService

SwiftUI reactivity requires `@Observable`. `AuthService` is `@unchecked Sendable` and not `@Observable`. Making it `@Observable` would conflict with its `Sendable` conformance and thread-safety model. Instead, `AuthViewModel` acts as the reactive bridge: it reads `AuthService.isAuthenticated` on init and updates its own `isAuthenticated` property on sign-in/sign-up/sign-out. `EmberApp` observes the `AuthViewModel`.

### Why no Amplify SDK package dependency

The P03-01 scaffold intentionally omitted Amplify because it requires `amplifyconfiguration.json`. Since this feature does not use Amplify at all (auth goes through backend endpoints), there is no reason to add the dependency. If Amplify is needed in the future (e.g., for AWS-specific features), it can be added then.

### Why LoginPlaceholderView is deleted instead of modified

The placeholder was a minimal dev-testing shim with an `@AppStorage` toggle. The real `LoginView` has entirely different content (form fields, ViewModel integration, Keychain-backed state). Modifying the placeholder would mean rewriting 100% of its code. Deleting and creating a new file is cleaner for git history.

### Why password confirmation field on sign-up

Standard UX pattern for account creation. Prevents typos in passwords since the field is a `SecureField` (masked). Client-side validation only; the backend does not receive `confirmPassword`.

---

## 11. Notes for Developers

### For ios-dev

- **Keychain testing**: Keychain operations may fail in certain CI environments. Use `SecItemCopyMatching` return codes to handle `errSecItemNotFound` (-25300) gracefully. The `getAccessToken()` and `getRefreshToken()` methods should return `nil` (not throw) when no item is found.

- **URL construction in AuthService**: Use the same pattern as `APIClient.buildRequest()` for consistency. The three auth endpoint paths are:
  - `/api/v1/auth/login`
  - `/api/v1/auth/register`
  - `/api/v1/auth/refresh`

- **snake_case encoding**: The backend expects `refresh_token` (snake_case) in the refresh request body. Use `JSONEncoder.ember` which is configured with `.convertToSnakeCase`.

- **EmberApp auth state**: The transition from `@AppStorage` to `AuthViewModel.isAuthenticated` must be clean. Remove all `@AppStorage("isAuthenticated")` references from `EmberApp.swift`. The `LoginPlaceholderView` (which also uses `@AppStorage("isAuthenticated")`) is deleted.

- **MockAuthService update**: The existing `MockAuthService` (from P03-02) must be updated with the new protocol methods (`signUp`, `isAuthenticated`). All existing tests that use `MockAuthService` must still compile.

- **Thread safety**: `KeychainTokenStore` is `@unchecked Sendable`. Document that Keychain APIs (`SecItem*`) are thread-safe per Apple documentation. No locking needed.

- **Text field focus**: Consider using `@FocusState` to manage keyboard focus across form fields. Tab order: email -> password (login), or name -> email -> password -> confirm password (sign-up).

- **No Amplify import**: Do NOT import `Amplify` or `AWSCognitoAuthPlugin` anywhere. The entire auth flow uses `URLSession` (in `AuthService`) and Keychain (in `KeychainTokenStore`).
