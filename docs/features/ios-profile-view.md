# iOS Profile View

> A full-featured profile management screen where users can update their avatar, display name, timezone, language preference, notification toggles, sign out, and delete their account.

**Status**: Released
**Added in**: 2026-03-13
**Platforms**: iOS

---

## Overview

ProfileView is the third tab in `MainTabView`, replacing the placeholder screen introduced in P03-01 (ios-scaffold). It serves as the user's settings hub for the Ember app.

The screen has three logical sections. The **profile header** shows the user's avatar (loaded from S3 via Kingfisher, or a gradient initial-circle fallback), display name, email, and a subscription tier badge. Both the avatar and the name are directly editable inline. The **preferences section** exposes timezone selection via a searchable sheet, a language segmented picker (English / Turkish), and a group of notification toggles — three system-wide toggles plus one per character. The **account section** provides a sign-out button and a delete-account button guarded by a typed confirmation flow.

All profile mutations (name, timezone, language, avatar URL) call `PUT /api/v1/profile`. Account deletion calls `DELETE /api/v1/profile/account`. The notification toggle states are stored locally in `UserDefaults` and do not call any API in this feature; they are placeholders pending full backend integration of notification preferences.

---

## Architecture

### How It Works (Data Flow)

1. The user taps the Profile tab in `MainTabView`, which presents `ProfileView` inside a `NavigationStack`.
2. `ProfileView.body` fires `.task { await viewModel.loadProfile() }` on first appearance.
3. `ProfileViewModel.loadProfile()` uses `async let` to issue `GET /api/v1/profile` and `GET /api/v1/characters` in parallel.
4. On success, `profile` and `characters` are set, and `notificationPreferences` is initialized from `UserDefaults` (key `"notification_preferences"`), defaulting all toggles to `true` if no stored value exists.
5. The view switches from a centered `ProgressView` to the full profile content.
6. Profile mutations (name, timezone, language, avatar) each call `PUT /api/v1/profile` with a `ProfileUpdateBody` containing only the changed field. On success the local `profile` is replaced with the server response, which is the authoritative state.
7. Avatar upload is a three-step sequence: `POST /api/v1/media/upload-url` to get a presigned URL, `PUT` directly to S3 with the JPEG data, then `PUT /api/v1/profile` with the returned `fileUrl` as `avatar_url`.
8. Sign-out sets `shouldSignOut = true` on the ViewModel. The View observes this with `.onChange` and calls `authViewModel.signOut()`, which clears Cognito tokens and sets `isAuthenticated = false`, returning the user to the login screen.
9. Account deletion calls `DELETE /api/v1/profile/account` with `{"confirmation": "DELETE MY ACCOUNT"}`, resets `UserDefaults.standard["hasCompletedOnboarding"]` to `false`, and sets `accountDeleted = true`. The View's `.onChange(of: viewModel.accountDeleted)` handler then calls `authViewModel.signOut()`.

### ViewModel Decoupling Pattern

`ProfileViewModel` holds no reference to `AuthViewModel`. It signals intent via two boolean flags — `shouldSignOut` and `accountDeleted` — which the View observes. This keeps the ViewModel testable without an `AuthViewModel` dependency and is consistent with the pattern used across other iOS features in this project.

### Notification Preferences Storage

Notification toggles are persisted in `UserDefaults` under the key `"notification_preferences"` as a `[String: Bool]` dictionary. Keys are:
- `"morning_checkin"` — global morning check-in toggle
- `"evening_reflection"` — global evening reflection toggle
- `"sleep_reminder"` — global sleep reminder toggle
- `"character_{character.id}"` — one key per character

No API call is made when a toggle changes. When the backend notification preferences endpoint is complete, the `updateNotificationPreference(key:value:)` method is the integration point.

### Database Tables Involved

| Table | Operation | Notes |
|-------|-----------|-------|
| `profiles` | SELECT, UPDATE | Via `GET /api/v1/profile` and `PUT /api/v1/profile` |
| `profiles` | DELETE (cascade) | Via `DELETE /api/v1/profile/account` — GDPR-compliant, 30-day cleanup |
| `characters` | SELECT | Via `GET /api/v1/characters` — used for per-character notification toggles |

All database operations happen on the backend. The iOS layer reads and writes only through the REST API.

---

## API Reference

See [`docs/04-veri-api.md`](../04-veri-api.md) for the full API contract. Key endpoints for this feature:

### `GET /api/v1/profile`

**Auth**: Bearer JWT required

**Response 200**:
```json
{
  "id": "uuid-string",
  "email": "user@example.com",
  "name": "Alex",
  "timezone": "America/New_York",
  "avatar_url": "https://s3.amazonaws.com/.../avatar.jpg",
  "preferred_language": "en",
  "onboarding_completed": true,
  "subscription_tier": "free",
  "subscription_expires_at": null,
  "created_at": "2026-02-23T10:00:00Z"
}
```

**Error Responses**:

| Status | When |
|--------|------|
| 401 | Missing or invalid JWT |

### `PUT /api/v1/profile`

**Auth**: Bearer JWT required

**Request Body** (all fields optional; only non-nil fields are applied):
```json
{
  "name": "Alex Updated",
  "timezone": "Europe/Istanbul",
  "avatar_url": "https://s3.amazonaws.com/.../avatar.jpg",
  "preferred_language": "tr"
}
```

**Response 200**: Same shape as `GET /api/v1/profile`.

**Error Responses**:

| Status | When |
|--------|------|
| 400 | Validation error (e.g., unsupported language) |
| 401 | Missing or invalid JWT |
| 422 | Pydantic schema violation |

### `DELETE /api/v1/profile/account`

**Auth**: Bearer JWT required

**Request Body**:
```json
{
  "confirmation": "DELETE MY ACCOUNT"
}
```

**Response**: `204 No Content`

**Error Responses**:

| Status | When |
|--------|------|
| 400 | Confirmation text does not exactly match `"DELETE MY ACCOUNT"` |
| 401 | Missing or invalid JWT |

### `POST /api/v1/media/upload-url`

**Auth**: Bearer JWT required

**Request Body**:
```json
{
  "filename": "avatar.jpg",
  "content_type": "image/jpeg",
  "type": "photo"
}
```

**Response 200**:
```json
{
  "upload_url": "https://s3.amazonaws.com/...?X-Amz-Signature=...",
  "file_url": "https://s3.amazonaws.com/.../{user_id}/avatar.jpg"
}
```

After receiving this response, the client issues a raw `PUT` directly to `upload_url` with the JPEG bytes and `Content-Type: image/jpeg`, then calls `PUT /api/v1/profile` with the `file_url` as `avatar_url`.

---

## iOS Implementation

**Files**:
- `ios/Ember/Features/Profile/ProfileView.swift` — SwiftUI view, subviews inline
- `ios/Ember/Features/Profile/ProfileViewModel.swift` — `@Observable` ViewModel
- `ios/Ember/Features/Profile/TimezonePickerSheet.swift` — Searchable timezone sheet (separate file)
- `ios/Ember/Core/Models/ProfileModels.swift` — `ProfileData`, `ProfileUpdateBody`, `AccountDeleteBody`, `UploadURLRequest`, `UploadURLResponse`
- `ios/EmberTests/Features/Profile/ProfileViewModelTests.swift` — Swift Testing suite
- `ios/Ember/App/MainTabView.swift` — Modified: `ProfilePlaceholderView` replaced with `ProfileView`

**Deleted**:
- `ios/Ember/Features/Profile/ProfilePlaceholderView.swift`

### Key Patterns

- ViewModel is `@Observable final class ProfileViewModel` (iOS 17+). Do not add `@Published` wrappers.
- `ProfileView` receives the `APIClient` via its `init(apiClient:)` parameter, defaulting to `APIClient.shared`. This enables injection of `MockProfileAPIClient` in tests.
- `PhotosPicker` (PhotosUI, iOS 16+) is used for avatar selection. The picker item is loaded as `Data` via `loadTransferable(type: Data.self)`, compressed to JPEG at 0.8 quality, then passed to `uploadAvatar(imageData:)`.
- The delete confirmation uses a SwiftUI `.alert` with an embedded `TextField`, valid on iOS 17+. The "Delete" button action is gated by `deleteConfirmationText != "DELETE MY ACCOUNT"` at the ViewModel level (the UI also disables the button via `.disabled`).

### State Management

```swift
// ProfileViewModel — public state
var profile: ProfileData?
var characters: [Character] = []
var isLoading: Bool = false
var isSaving: Bool = false
var errorMessage: String?
var showPhotoPicker: Bool = false
var showTimezonePicker: Bool = false
var showDeleteConfirmation: Bool = false
var deleteConfirmationText: String = ""
var isEditingName: Bool = false
var editedName: String = ""
var notificationPreferences: [String: Bool] = [:]
var shouldSignOut: Bool = false
var accountDeleted: Bool = false
```

### Navigation

ProfileView is a tab root — there is no push navigation into or out of it. It is presented as the third tab in `MainTabView` inside its own `NavigationStack`. Modal sheets (timezone picker, photo picker) and alerts (error, delete confirmation) are presented inline. Sign-out and account deletion navigate away by changing `isAuthenticated` in `AuthViewModel`, which causes `EmberApp.swift` to replace the tab view with the login screen.

---

## Android Implementation

Not applicable. This is an iOS-only feature (layer: ios).

---

## Testing

### Coverage Summary

| Platform | File | Tests |
|----------|------|-------|
| iOS | `ProfileViewModelTests.swift` | 18 test cases, >= 80% line coverage |

### Test Suite Highlights

The `MockProfileAPIClient` in the test file is endpoint-aware: it returns different mock responses based on the `APIEndpoint` case (`.getProfile`, `.listCharacters`, `.updateProfile`, `.uploadURL`, `.deleteAccount`). It also tracks `calledEndpoints: [String]` for verifying parallel fetch behavior.

Notable test coverage:
- `loadProfile()` with success, network error, and 401 — verifies both endpoints are called
- `updateName()` with whitespace trimming and empty-string rejection (no API call made)
- `deleteAccount()` with correct confirmation, wrong confirmation (no API call), and server error
- `updateNotificationPreference()` verifies `UserDefaults` persistence and performs cleanup after the test
- `startEditingName()` and `cancelEditingName()` state transitions

### Running Tests

```bash
cd ios && xcodebuild test -scheme Ember -destination "platform=iOS Simulator,name=iPhone 15"
```

---

## Known Limitations

- **Notification toggles are UI-only placeholders**: Toggle states are persisted to `UserDefaults` but do not call any backend API. The `PUT /api/v1/notifications/preferences` endpoint exists in `APIEndpoint.swift` but the backend feature is not yet ready. This will be wired up in a future feature.
- **No UI test coverage**: UI tests (launch-and-interact) are listed as a stretch goal in the spec but were not implemented. Only ViewModel unit tests exist.
- **`uploadAvatar` makes three sequential calls**: The presigned URL request, the S3 PUT, and the profile update are sequential, not parallel. A network failure in any step leaves partial state (e.g., S3 upload succeeded but profile URL was not saved). There is no rollback mechanism.
- **`UserResponse.createdAt` is a `String`**: The existing `UserResponse` in `AuthModels.swift` stores `createdAt` as `String` to avoid breaking the auth flow. `ProfileData` uses `Date` with `JSONDecoder.ember`. These two models coexist intentionally and must not be merged without updating the auth flow.

---

## Extending This Feature

To connect notification toggles to the backend when the notification preferences endpoint is ready, update `updateNotificationPreference(key:value:)` in `ProfileViewModel.swift` to call `apiClient.requestVoid(endpoint: .notificationPreferences, body: ...)` after persisting to `UserDefaults`. The `UserDefaults` write should remain as a local cache so the UI reflects the user's choice immediately.

To add a new profile field (e.g., a bio), add the property to `ProfileData` (decode-only), add a corresponding `var` to `ProfileUpdateBody` (encode-only, optional), add the UI row in `ProfileView`, and add a new `updateBio(_ bio: String) async` method to `ProfileViewModel` following the same pattern as `updateTimezone`.

To add a "Clear Avatar" action, call `PUT /api/v1/profile` with `avatar_url: null`. The `ProfileUpdateBody.avatarUrl` field encodes as `null` when the Swift value is `nil` only if you configure the encoder with `.encodeNilAsNull`. Verify this behavior before implementing.

---

## Related Documentation

- [Database Schema](../04-veri-api.md)
- [Profile CRUD Endpoints](profile-crud-endpoints.md)
- [Media Upload](media-upload.md)
- [iOS Scaffold](ios-scaffold.md)
- [iOS Network Layer](ios-network-layer.md)
- [iOS Cognito Auth](ios-cognito-auth.md)
- [iOS Home View](ios-home-view.md)
- [Mobile Screens](../07-mobil.md)
- [Design System](../14-tasarim.md)
