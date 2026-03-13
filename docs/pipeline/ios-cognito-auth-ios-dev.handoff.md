# iOS Dev Handoff: iOS Cognito Auth

**Date**: 2026-03-13
**Agent**: ios-dev
**Status**: COMPLETE

## Implemented Files

### Created
- `ios/Ember/Core/Auth/KeychainTokenStore.swift` -- Secure Keychain wrapper for JWT token storage (access + refresh)
- `ios/Ember/Core/Models/AuthModels.swift` -- `AuthResponse`, `UserResponse`, `RefreshResponse` Codable structs
- `ios/Ember/Features/Auth/AuthViewModel.swift` -- `@Observable` ViewModel with sign-in, sign-up, sign-out, form validation
- `ios/Ember/Features/Auth/LoginView.swift` -- Login screen with email/password fields, validation, loading state
- `ios/Ember/Features/Auth/SignUpView.swift` -- Sign-up screen with name, email, password, confirm password fields
- `ios/EmberTests/Core/Auth/KeychainTokenStoreTests.swift` -- 9 tests for Keychain CRUD operations
- `ios/EmberTests/Features/Auth/AuthViewModelTests.swift` -- 19 tests for ViewModel logic, validation, auth state

### Modified
- `ios/Ember/Core/Auth/AuthService.swift` -- Replaced stub with production implementation calling backend REST endpoints via URLSession
- `ios/Ember/Core/Auth/AuthError.swift` -- Added `.signUpFailed`, `.keychainError` cases; added `Equatable` conformance
- `ios/Ember/App/EmberApp.swift` -- Replaced `@AppStorage("isAuthenticated")` with `AuthViewModel.isAuthenticated`; injects `AuthViewModel` into environment
- `ios/Ember/Features/Profile/ProfilePlaceholderView.swift` -- Added "Sign Out" button using `AuthViewModel` from environment
- `ios/EmberTests/Mocks/MockAuthService.swift` -- Added `signUp`, `isAuthenticated`, call tracking properties
- `ios/Ember.xcodeproj/project.pbxproj` -- Added new files, removed deleted file

### Deleted
- `ios/Ember/Features/Auth/LoginPlaceholderView.swift` -- Replaced by `LoginView.swift`

## Screens Implemented
- **LoginView**: Email + password fields, "Sign In" button with loading spinner, link to sign-up, error alert
- **SignUpView**: Name + email + password + confirm password fields, "Create Account" button, password mismatch validation, error alert

## Deviations from Spec
- None. All spec requirements implemented as designed.

## Notes for iOS Tester

### Mock Patterns
- `MockAuthService` implements `AuthServiceProtocol` with call tracking (`signInCallCount`, `lastSignInEmail`, etc.)
- Set `shouldThrowOnSignIn` / `shouldThrowOnSignUp` to inject errors
- `MockURLProtocol` intercepts HTTP requests for `AuthService` integration tests
- `KeychainTokenStore` uses real Keychain -- tests require simulator or device

### What to Test
- **AuthViewModel**: Form validation (`isSignInFormValid`, `isSignUpFormValid`), email trimming/lowercasing, error message propagation, `isAuthenticated` state transitions
- **AuthService**: HTTP request body format (snake_case keys), error mapping (401 -> "Invalid email or password"), token storage after success, `isAuthenticated` computed property
- **KeychainTokenStore**: Save/read/overwrite/clear tokens, `hasTokens` computed property
- **Integration**: EmberApp switches from LoginView to OnboardingPlaceholderView when `authViewModel.isAuthenticated` becomes true
- **Sign-out**: Tokens cleared, state reset, returns to login screen
- **401 retry**: APIClient calls `authService.refreshToken()` on 401, which calls `POST /api/v1/auth/refresh` and updates stored access token

### Architecture Notes
- `AuthService` makes its own `URLSession` calls (not via `APIClient`) to avoid circular dependency
- `AuthViewModel` is the reactive bridge -- `AuthService` is not `@Observable`
- `KeychainTokenStore` is `@unchecked Sendable` -- Keychain APIs are thread-safe
- No Amplify SDK used; auth flows through backend REST endpoints
