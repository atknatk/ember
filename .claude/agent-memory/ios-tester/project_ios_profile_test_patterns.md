---
name: ios-profile-view test patterns
description: Patterns established during P03-09 iOS Profile View testing — MockProfileAPIClient with endpoint routing, UserDefaults cleanup for notification_preferences and hasCompletedOnboarding, uploadAvatar S3 step untestable without URLSession injection, pbxproj group IDs for profile tests
type: project
---

The profile feature (P03-09) ViewModel uses `APIClientProtocol` directly (same injection pattern as Home and Memories). The ios-dev wrote `ProfileViewModelTests.swift` (25 tests) as part of the feature; the ios-tester wrote `ProfileViewModelExtendedTests.swift` (34 tests) covering state transitions, UserDefaults side effects, and Codable correctness.

Key mock properties (local `MockProfileAPIClient` in each test file):
- `profileResponse: ProfileData?` — returned for `.getProfile`
- `characterListResponse: CharacterListResponse` — returned for `.listCharacters`
- `updateProfileResponse: ProfileData?` — returned for `.updateProfile` (falls back to `profileResponse` if nil)
- `uploadURLResponse: UploadURLResponse?` — returned for `.uploadURL`
- `requestError: Error?` — throws on all `request()` calls
- `deleteError: Error?` — throws on `requestVoid()` calls only
- `requestCallCount: Int`, `requestVoidCallCount: Int` — call tracking
- `calledEndpoints: [String]` — ordered list of endpoint keys for sequence verification
- `lastEndpoint: APIEndpoint?` — last endpoint used in either `request` or `requestVoid`

Key test facts for profile:
- `loadProfile()` uses `async let` for parallel fetch of profile and characters. Both `.getProfile` and `.listCharacters` must appear in `calledEndpoints`.
- `loadProfile()` clears `errorMessage = nil` at start — test by pre-setting `vm.errorMessage` before calling.
- Notification preferences: loaded from `UserDefaults["notification_preferences"]` after profile fetch. If no stored value, defaults all keys to `true` including `"character_{id}"` per character. Always clean up `UserDefaults.standard.removeObject(forKey: "notification_preferences")` in tests.
- `deleteAccount()` resets `UserDefaults["hasCompletedOnboarding"]` to `false` on success. Always clean up `UserDefaults.standard.removeObject(forKey: "hasCompletedOnboarding")` in tests.
- `uploadAvatar()` makes 3 steps: (1) `.uploadURL` via `apiClient.request`, (2) raw `URLSession.shared.upload` for S3 PUT, (3) `.updateProfile` via `apiClient.request`. Step 2 is untestable with a mock without `MockURLProtocol`. Only steps 1 and 3 failures are testable.
- `isSaving` is set to `false` in the finally block — always test after the await returns.
- `isEditingName` is only set to `false` on success, NOT on failure — the user can retry editing.
- `shouldSignOut` and `accountDeleted` are boolean flags observed by the View to call `authViewModel.signOut()`. The ViewModel never calls sign-out directly.
- `ProfileUpdateBody` uses default Codable synthesis — nil fields encode as JSON `null` (not omitted). The backend accepts this fine.

pbxproj notes for profile tests:
- Profile test group UUID: `7232EC3A121E3961A04DA6A2`
- `ProfileViewModelTests.swift` fileRef: `9BE57CD572D033F9DDE6D4F8`, buildFile: `0983B49E0ED083083A371866`
- `ProfileViewModelExtendedTests.swift` fileRef: `2C3D4E5F6A7B8C9D0E1F2A3B`, buildFile: `1B2C3D4E5F6A7B8C9D0E1F2A`
- Sources build phase: `91FC9734A1965EA61C9B43FF` (same as all other test files)
- The ios-dev already registered `ProfileViewModelTests.swift`. The ios-tester registered `ProfileViewModelExtendedTests.swift`.

**Why:** The profile feature is the most complex ViewModel so far — it has parallel loading, UserDefaults side effects in two separate keys, a three-step upload flow, and two boolean delegation flags for auth state changes.

**How to apply:** For any future ViewModel with UserDefaults side effects, always clean up the specific key in a test-local cleanup block (`UserDefaults.standard.removeObject(forKey:)`). For upload flows with raw URLSession calls, note the untestable step and test the surrounding API calls instead.
