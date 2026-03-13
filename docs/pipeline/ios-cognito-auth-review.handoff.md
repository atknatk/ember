# Reviewer Handoff: iOS Cognito Auth

**Date**: 2026-03-13
**Agent**: reviewer
**Status**: APPROVED

## Review Summary

| Category | Passed | Warnings | Issues |
|----------|--------|----------|--------|
| Architecture | 6 | 0 | 0 |
| iOS Code Quality | 8 | 1 | 0 |
| Testing | 7 | 1 | 0 |
| Security | 4 | 0 | 0 |
| **Total** | **25** | **2** | **0** |

## Files Reviewed

**Core/Auth**:
- `ios/Ember/Core/Auth/KeychainTokenStore.swift` -- PASS
- `ios/Ember/Core/Auth/AuthService.swift` -- PASS
- `ios/Ember/Core/Auth/AuthError.swift` -- PASS

**Core/Models**:
- `ios/Ember/Core/Models/AuthModels.swift` -- PASS

**Features/Auth**:
- `ios/Ember/Features/Auth/AuthViewModel.swift` -- PASS
- `ios/Ember/Features/Auth/LoginView.swift` -- PASS
- `ios/Ember/Features/Auth/SignUpView.swift` -- PASS

**App**:
- `ios/Ember/App/EmberApp.swift` -- PASS

**Features/Profile**:
- `ios/Ember/Features/Profile/ProfilePlaceholderView.swift` -- PASS

**Tests**:
- `ios/EmberTests/Core/Auth/KeychainTokenStoreTests.swift` -- PASS (9 tests)
- `ios/EmberTests/Core/Auth/AuthServiceTests.swift` -- PASS (17 tests incl. AuthError)
- `ios/EmberTests/Features/Auth/AuthViewModelTests.swift` -- PASS (19 tests)
- `ios/EmberTests/Mocks/MockAuthService.swift` -- PASS

**Deleted**:
- `ios/Ember/Features/Auth/LoginPlaceholderView.swift` -- confirmed deleted

## Checklist Results

### Architecture Compliance
- [x] Auth calls go to backend REST endpoints (`/api/v1/auth/login`, `/register`, `/refresh`), NOT Amplify SDK
- [x] No Amplify import anywhere in production code (only a comment in AuthService.swift)
- [x] AuthService makes its own URLSession calls to avoid circular dependency with APIClient
- [x] `@AppStorage("isAuthenticated")` fully removed from EmberApp.swift
- [x] Keychain-backed token presence drives auth state via AuthViewModel.isAuthenticated
- [x] All spec endpoints implemented: signIn, signUp, signOut, getAccessToken, refreshToken

### iOS Code Quality
- [x] `@Observable` used on AuthViewModel -- no ObservableObject, no @Published, no @StateObject
- [x] No `NavigationView` anywhere in new code
- [x] Tokens stored in iOS Keychain via `Security` framework, NOT UserDefaults
- [x] No hardcoded secrets or API keys
- [x] Dark mode: `.preferredColorScheme(.dark)` present on EmberApp root
- [x] SF Symbols used for logo (`"sparkles"`) with `.accessibilityHidden(true)`
- [x] All buttons and form fields have `.accessibilityLabel()`
- [x] Protocol-based DI: `AuthServiceProtocol` enables mock injection in tests
- [WARN] Force unwrap on `URL(string: "https://api.ember.ai")!` (line 44, AuthService.swift) -- acceptable because it is a known-valid URL literal after a nil-coalescing `??` fallback. Same pattern as pre-existing APIClient.swift.

### Testing
- [x] 45 total tests across 3 test files
- [x] Swift Testing (`import Testing`) used as primary framework
- [x] MockAuthService conforms to AuthServiceProtocol with full call tracking
- [x] MockURLProtocol used for HTTP request interception in AuthService tests
- [x] Error paths tested: 401, 503, 400 "already exists", 400 "Password" requirement
- [x] Form validation edge cases: empty fields, short password, mismatched passwords, whitespace-only name
- [x] Sign-out state reset verified (form fields, isAuthenticated, errorMessage all cleared)
- [WARN] Network error test (URLSession throwing URLError) not explicitly tested. The 503 status code test and the `catch` block in `performAuthRequest` cover the code path, but a dedicated URLError test would strengthen coverage. Non-blocking.

### Security
- [x] No secrets hardcoded -- `baseURL` from environment or safe default
- [x] Passwords not logged or stored in plain text (only sent in HTTP body, stored via Keychain)
- [x] No `print()` calls in any production code
- [x] Tokens stored in Keychain with `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly` -- not backed up, not transferred to new device

## Issues Resolved During Review
- None (first-pass clean)

## Warnings (Not Blocking)
1. **Force unwrap on URL literal** (`AuthService.swift:44`): `URL(string: "https://api.ember.ai")!` after `??` fallback. Known-valid literal, same pattern as APIClient. Consider replacing with a static constant in a future cleanup pass.
2. **Missing explicit network error test** (`AuthServiceTests.swift`): No test simulates `URLSession` throwing a `URLError` (e.g., no internet). The error mapping code handles it correctly, and the 503 test exercises the error path, but a dedicated test would improve coverage completeness.
