# Reviewer Handoff: iOS Profile View

**Date**: 2026-03-13
**Agent**: reviewer
**Status**: APPROVED

## Review Summary

| Category | Passed | Warnings | Issues |
|----------|--------|----------|--------|
| Architecture | 5 | 0 | 0 |
| iOS Code Quality | 9 | 0 | 0 |
| Testing | 6 | 1 | 0 |
| Security | 3 | 0 | 0 |
| **Total** | **23** | **1** | **0** |

## Files Reviewed

**iOS**:
- `ios/Ember/Features/Profile/ProfileView.swift` -- PASS
- `ios/Ember/Features/Profile/ProfileViewModel.swift` -- PASS
- `ios/Ember/Features/Profile/TimezonePickerSheet.swift` -- PASS
- `ios/Ember/Core/Models/ProfileModels.swift` -- PASS
- `ios/Ember/App/MainTabView.swift` (modification verified) -- PASS
- `ios/EmberTests/Features/Profile/ProfileViewModelTests.swift` -- PASS
- `ios/EmberTests/Features/Profile/ProfileViewModelExtendedTests.swift` -- PASS

## Architecture Compliance

- [PASS] **No /conversations path segment**: No mobile-facing API uses `/conversations`. Profile endpoints use `/api/v1/profile` and `/api/v1/media/upload-url`.
- [PASS] **Spec adherence**: All screens and components from spec sections 5.1-5.7 are implemented. File manifest matches: ProfileView, ProfileViewModel, TimezonePickerSheet, ProfileModels created; ProfilePlaceholderView deleted; MainTabView updated.
- [PASS] **No new backend code**: Confirmed iOS-only feature, no backend changes.
- [PASS] **Parallel fetch**: `loadProfile()` uses `async let` for profile and characters fetch (lines 40-49 of ViewModel).
- [PASS] **API endpoints match spec**: getProfile, updateProfile, deleteAccount, uploadURL, listCharacters all used correctly per spec section 3.

## iOS Code Quality

- [PASS] **@Observable**: `ProfileViewModel` uses `@Observable` macro (line 4). No `ObservableObject`, `@Published`, or `@StateObject` anywhere in `ios/Ember/`.
- [PASS] **No force unwrap**: Grep for `\)!` in Profile feature files returned zero matches.
- [PASS] **NavigationStack**: TimezonePickerSheet uses `NavigationStack` (line 20). No `NavigationView` anywhere in `ios/Ember/`.
- [PASS] **Dark mode**: `preferredColorScheme(.dark)` confirmed in `EmberApp.swift` (line 47).
- [PASS] **SF Symbols for icons**: Camera overlay, cancel button, error state icon, chevron, checkmark all use `Image(systemName:)`. No custom image assets.
- [PASS] **Accessibility labels**: Avatar button, name button, sign out, delete account, timezone row, edit field, save/cancel buttons all have appropriate labels. Decorative error icon has `accessibilityHidden(true)`. Timezone checkmark has `accessibilityHidden(true)`.
- [PASS] **No hardcoded colors**: All colors use `Color.ember*` constants. No raw color values.
- [PASS] **Kingfisher for network images**: Avatar uses `KFImage(url)` with `.placeholder`, `.fade(duration: 0.25)`, `.resizable()`, `.aspectRatio(contentMode: .fill)`. No `AsyncImage` usage anywhere in `ios/Ember/`.
- [PASS] **Service protocol**: ViewModel takes `APIClientProtocol` via constructor injection. Tests use `MockProfileAPIClient` conforming to the protocol.

## Testing

- [PASS] **Test count**: 56 total tests (20 base + 36 extended) covering all ViewModel public methods and model encoding/decoding.
- [PASS] **Edge cases covered**: Auth failure (401), server error (400/500/503), validation rejection (empty name), wrong confirmation text, network errors, nil profile state, UserDefaults round-trip, Codable round-trip all tested.
- [PASS] **Protocol-based mocks**: `MockProfileAPIClient` conforms to `APIClientProtocol`. No partial mocks.
- [PASS] **No real API calls**: All tests use mock API client.
- [PASS] **Spec test scenarios**: All 14 spec-required scenarios covered. Extended tests cover uploadAvatar error paths, hasCompletedOnboarding reset, notification preferences initialisation and restoration.
- [PASS] **UserDefaults test isolation**: Extended tests properly clean up UserDefaults after each test that writes to it.
- [WARN] **uploadAvatar S3 upload step not fully testable**: The `uploadAvatar(imageData:)` method uses `URLSession.shared` directly for the S3 PUT step. The presigned URL request and profile update steps are tested through the mock, and error paths are tested. The actual S3 upload success path cannot be unit-tested without URLSession abstraction. Consider introducing a `FileUploader` protocol in a future refactor.

## Security

- [PASS] **No credentials in code**: Grep for `api_key`, `secret`, hardcoded tokens returned zero matches.
- [PASS] **No user_id from client**: Profile endpoints derive user_id from JWT server-side.
- [PASS] **Delete account confirmation**: Two-step flow requires exact string "DELETE MY ACCOUNT" before API call (ViewModel guard + View `.disabled` on button).

## Issues Resolved During Review
- None (first-pass clean)

## Warnings (Not Blocking)

1. **uploadAvatar S3 upload step not fully testable**: The direct `URLSession.shared.upload()` call for S3 PUT cannot be intercepted by the mock API client. Error paths are tested (presigned URL failure, isSaving reset). Consider a `FileUploader` protocol for full testability in a future iteration.

2. **Notification toggles are UI-only placeholders**: Toggle states are stored in `UserDefaults` only. Will be connected to backend notification preferences API in a future phase. This is by design per the architect spec.
