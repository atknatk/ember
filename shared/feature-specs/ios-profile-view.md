# Feature Spec: P03-09 -- iOS Profile View

**Feature ID**: P03-09
**Phase**: 3
**Layer**: ios
**GitHub Issue**: #25
**Date**: 2026-03-13
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature replaces the `ProfilePlaceholderView` (from P03-01) with a production ProfileView screen. ProfileView is the third tab in `MainTabView` and serves as the user's settings hub. It contains:

1. **Profile header** -- Displays the user's avatar (from S3 `avatar_url` or a fallback initial-circle), display name, and email. Tapping the avatar opens the system photo picker to upload a new profile photo via `POST /api/v1/media/upload-url` followed by `PUT /api/v1/profile`. Tapping the name opens an inline edit field.

2. **Preferences section** -- Timezone picker (IANA timezone list presented as a searchable sheet), preferred language toggle (English / Turkish), and notification preferences with per-character toggles.

3. **Account section** -- Sign out button, and delete account button with a two-step confirmation flow requiring the user to type "DELETE MY ACCOUNT".

### Why It Exists

Users need a central place to view and edit their profile information, manage notification preferences, and perform account-level actions (sign out, delete account). This screen completes the core tab navigation established in P03-01 and connects to the profile backend endpoints implemented in P1.5-02.

### Dependencies

- **P03-01** (ios-scaffold) -- Provides `MainTabView`, `AppContainer`, `AppRouter`, design system extensions, `HapticManager`, `EmberSymbol`.
- **P03-03** (ios-cognito-auth) -- Provides `AuthService` with `signOut()` and `getAccessToken()`.
- **P03-02** (ios-network-layer) -- Provides `APIClient` with `request()` and `requestVoid()`, `APIEndpoint.getProfile`, `.updateProfile`, `.deleteAccount`, `.uploadURL`.
- **P03-06** (ios-home-view) -- Provides the established pattern for `@Observable` ViewModels, `CharacterModels.swift` (for `Character` and `CharacterListResponse`).
- **P01-09** (onboarding) -- Onboarding must be completed before ProfileView is reachable.
- **P1.5-02** (profile-crud-endpoints, backend) -- Provides `GET /api/v1/profile`, `PUT /api/v1/profile`, `DELETE /api/v1/profile/account`.
- **P01-10** (media-upload, backend) -- Provides `POST /api/v1/media/upload-url` for avatar photo upload.
- **P01-05** (character-crud, backend) -- Provides `GET /api/v1/characters` for character list (used for per-character notification toggles).

### What This Feature Does NOT Do

- It does not implement the partner section (Phase 8 feature).
- It does not implement password change (Cognito direct operation, separate feature).
- It does not implement data export (JSON export is a future feature).
- It does not implement notification preferences API calls. The toggles are rendered and stored locally in `UserDefaults` for now. The `PUT /api/v1/notifications/preferences` endpoint exists in `APIEndpoint.swift` but the backend notification preferences feature is not yet ready for full integration. The toggles are UI-only placeholders that will be connected when the notification preferences backend is complete.
- It does not change any backend code. All API endpoints are already implemented.

---

## 2. Data Models

No database changes. This is an iOS-only feature.

### Swift Models

#### ProfileData (new model)

Maps to the backend's `ProfileResponse` Pydantic schema (see `backend/app/schemas/profile.py`).

```
struct ProfileData: Codable, Identifiable {
    let id: String
    let email: String
    let name: String
    let timezone: String
    let avatarUrl: String?
    let preferredLanguage: String
    let onboardingCompleted: Bool
    let subscriptionTier: String
    let subscriptionExpiresAt: Date?
    let createdAt: Date
}
```

Note: The existing `UserResponse` in `AuthModels.swift` has `createdAt` as `String` instead of `Date`. `ProfileData` uses `Date` for consistency with `JSONDecoder.ember` date decoding. `UserResponse` is not modified to preserve backward compatibility with the auth flow.

#### ProfileUpdateBody (new model)

Maps to the backend's `ProfileUpdateRequest` schema. Only non-nil fields are sent in the request body.

```
struct ProfileUpdateBody: Encodable {
    var name: String?
    var timezone: String?
    var avatarUrl: String?
    var preferredLanguage: String?
}
```

#### AccountDeleteBody (new model)

Maps to the backend's `AccountDeleteRequest` schema.

```
struct AccountDeleteBody: Encodable {
    let confirmation: String
}
```

#### UploadURLRequest and UploadURLResponse (existing)

These models already exist or should be added alongside the profile models. They map to `POST /api/v1/media/upload-url`.

```
struct UploadURLRequest: Encodable {
    let filename: String
    let contentType: String
    let type: String
}

struct UploadURLResponse: Codable {
    let uploadUrl: String
    let fileUrl: String
}
```

All structs are decoded using `JSONDecoder.ember` which converts `snake_case` keys to `camelCase` properties.

---

## 3. API Endpoints

No new endpoints. This feature calls existing backend endpoints.

### GET /api/v1/profile

```
GET /api/v1/profile
Auth: Bearer JWT required
Request body: none

Response 200:
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

Response 401: { "detail": "..." }
```

The `APIEndpoint.getProfile` case already exists (path: `/api/v1/profile`, method: GET, requiresAuth: true).

### PUT /api/v1/profile

```
PUT /api/v1/profile
Auth: Bearer JWT required
Request headers: Content-Type: application/json
Request body:
{
    "name": "Alex Updated",          // optional
    "timezone": "Europe/Istanbul",   // optional
    "avatar_url": "https://...",     // optional, null clears
    "preferred_language": "tr"       // optional: "en" or "tr"
}

Response 200: same shape as GET /api/v1/profile response
Response 400: { "detail": "..." } (validation error)
Response 401: { "detail": "..." }
Response 422: { "detail": "..." } (Pydantic validation)
```

The `APIEndpoint.updateProfile` case already exists (path: `/api/v1/profile`, method: PUT, requiresAuth: true).

### DELETE /api/v1/profile/account

```
DELETE /api/v1/profile/account
Auth: Bearer JWT required
Request headers: Content-Type: application/json
Request body:
{
    "confirmation": "DELETE MY ACCOUNT"
}

Response 204: (no body)
Response 400: { "detail": "Confirmation text must be exactly 'DELETE MY ACCOUNT'" }
Response 401: { "detail": "..." }
```

The `APIEndpoint.deleteAccount` case already exists (path: `/api/v1/profile/account`, method: DELETE, requiresAuth: true).

### POST /api/v1/media/upload-url

```
POST /api/v1/media/upload-url
Auth: Bearer JWT required
Request headers: Content-Type: application/json
Request body:
{
    "filename": "avatar.jpg",
    "content_type": "image/jpeg",
    "type": "photo"
}

Response 200:
{
    "upload_url": "https://s3.amazonaws.com/...?X-Amz-Signature=...",
    "file_url": "https://s3.amazonaws.com/.../{user_id}/avatar.jpg"
}
```

The `APIEndpoint.uploadURL` case already exists (path: `/api/v1/media/upload-url`, method: POST, requiresAuth: true).

### GET /api/v1/characters

Used to fetch the character list for per-character notification toggles. Already documented in the ios-home-view spec. Uses `APIEndpoint.listCharacters`.

---

## 4. Backend Logic

Not applicable. This is an iOS-only feature. All backend endpoints are fully implemented:
- Profile routes: `backend/app/routes/profile.py`
- Profile service: `backend/app/services/profile_service.py`
- Media upload: `backend/app/routes/media.py`
- Character list: `backend/app/routes/characters.py`

---

## 5. iOS Screens and Components

### 5.1 ProfileView

**File path**: `ios/Ember/Features/Profile/ProfileView.swift`

**Replaces**: `ios/Ember/Features/Profile/ProfilePlaceholderView.swift` (this file is deleted)

**Navigation**: Shown as the third tab ("Profile") in `MainTabView`. The user arrives here by tapping the Profile tab icon. No outbound navigation to other screens except modals presented inline (photo picker, timezone picker, delete confirmation).

**View structure**:

```
ScrollView {
    VStack(spacing: .emberSpacing24) {
        ProfileHeaderView(...)
        PreferencesSectionView(...)
        AccountSectionView(...)
    }
    .padding(.horizontal, .emberSpacing20)
    .padding(.top, .emberSpacing24)
}
.background(Color.emberBackground.ignoresSafeArea())
.navigationTitle("Profile")
.navigationBarTitleDisplayMode(.inline)
.task { await viewModel.loadProfile() }
.alert("Delete Account", isPresented: $viewModel.showDeleteConfirmation) { ... }
.sheet(isPresented: $viewModel.showTimezonePicker) { ... }
.photosPicker(isPresented: $viewModel.showPhotoPicker, ...) { ... }
```

**State binding**: `@State private var viewModel: ProfileViewModel`

**Environment**: `@Environment(AuthViewModel.self) private var authViewModel`, `@Environment(AppContainer.self) private var container`

**ViewModel initialization**: Initialized in `init()` or via `.onAppear` using the container's `apiClient`.

**Loading state**: When `viewModel.isLoading` is true, show a centered `ProgressView()` with `.tint(Color.emberPrimary)`.

**Error state**: When `viewModel.errorMessage` is not nil, show a `.alert("Error", ...)` with the message and "OK" dismiss button plus "Retry" button.

### 5.2 ProfileHeaderView

**File path**: inline in `ProfileView.swift` or extracted as a private subview within the same file

**UI elements**:

- **Avatar circle**: 80pt diameter circle. If `viewModel.profile?.avatarUrl` is non-nil, display the image using Kingfisher (`KFImage`). Otherwise, display a gradient circle (`.emberGradientStart` to `.emberGradientEnd`) with the user's first initial in `.emberLargeTitle` font, white. A small camera icon overlay (12pt, `Color.emberTextSecondary`, with a `Color.emberSurface2` background circle at the bottom-right of the avatar) indicates the avatar is tappable.
- **Tap action**: Tapping the avatar sets `viewModel.showPhotoPicker = true` to present `PhotosPicker`.
- **Name display**: The user's name in `.emberTitle` font, `Color.emberTextPrimary`, centered below the avatar. Tapping the name triggers inline editing: the text is replaced by a `TextField` with a `Color.emberSurface2` background, and a "Save" button appears. On save, calls `viewModel.updateName()`.
- **Email display**: The user's email in `.emberSecondary` font, `Color.emberTextSecondary`, centered. Not editable (email changes go through Cognito).
- **Subscription badge**: If `viewModel.profile?.subscriptionTier == "premium"`, show a small pill badge "Premium" in `.emberCaption` font with `Color.emberPrimary` background. Otherwise, show "Free" with `Color.emberSurface3` background.

**Accessibility**: Avatar has `accessibilityLabel("Profile photo. Tap to change")`. Name has `accessibilityLabel("Display name: {name}. Tap to edit")`.

### 5.3 PreferencesSectionView

**File path**: inline in `ProfileView.swift` or extracted as a private subview

**Section header**: "Preferences" in `.emberHeadline` font, `Color.emberTextPrimary`, leading aligned.

**UI elements**:

- **Timezone row**: A row showing the current timezone value (e.g., "America/New_York") with a chevron. Tapping opens a searchable sheet (`viewModel.showTimezonePicker = true`). The sheet presents a `List` of common IANA timezones filtered by a search field. Selecting a timezone calls `viewModel.updateTimezone(newTimezone)`.

- **Language row**: A row showing the current language ("English" or "Turkish"). Tapping toggles between `"en"` and `"tr"` and calls `viewModel.updateLanguage(newLanguage)`. Displayed as a `Picker` with `.segmented` style or a simple tap-to-toggle row.

- **Notifications sub-section**: Header "Notifications" in `.emberHeadline` font. Below it, a list of `Toggle` rows:
  - "Morning Check-in" -- toggle
  - "Evening Reflection" -- toggle
  - "Sleep Reminder" -- toggle
  - Per-character toggles: For each character from `viewModel.characters`, show a toggle row with the character's name. These toggles are stored locally in `UserDefaults` under key `"notification_preferences"` as a dictionary. The toggles do NOT call any API in this feature. They are UI-only placeholders.

**Haptics**: `HapticManager.selection()` when a timezone is selected. `HapticManager.impact(.light)` when a language is changed. `HapticManager.selection()` when a notification toggle changes.

**Accessibility**: Each row has an appropriate `accessibilityLabel`. Toggle rows use the default SwiftUI Toggle accessibility. The timezone row has `accessibilityHint("Opens timezone picker")`.

### 5.4 AccountSectionView

**File path**: inline in `ProfileView.swift` or extracted as a private subview

**Section header**: "Account" in `.emberHeadline` font, `Color.emberTextPrimary`, leading aligned.

**UI elements**:

- **Sign Out button**: Full-width button with `.emberHeadline` font, `Color.emberTextPrimary` text, `Color.emberSurface2` background, `cornerRadius(.emberRadius12)`. Tapping calls `viewModel.signOut()` which delegates to `authViewModel.signOut()`.

- **Delete Account button**: Full-width button with `.emberHeadline` font, `Color.emberError` text, `Color.emberSurface2` background, `cornerRadius(.emberRadius12)`. Tapping sets `viewModel.showDeleteConfirmation = true`.

**Delete confirmation flow**:

1. An `.alert` is presented with title "Delete Account" and message "This action is permanent and cannot be undone. All your data, conversations, and memories will be deleted. Type DELETE MY ACCOUNT to confirm."
2. The alert contains a `TextField` bound to `viewModel.deleteConfirmationText`.
3. A "Delete" button (`.destructive` role) is enabled only when `viewModel.deleteConfirmationText == "DELETE MY ACCOUNT"`. Tapping calls `viewModel.deleteAccount()`.
4. A "Cancel" button (`.cancel` role) dismisses the alert and clears `viewModel.deleteConfirmationText`.

Note: SwiftUI `.alert` with a `TextField` requires iOS 16+. Since the app targets iOS 17+, this approach is valid. Alternatively, a full-screen `.sheet` can be used for a richer confirmation UI. The spec recommends the `.alert` approach for simplicity, but the developer may use a `.sheet` if the `TextField`-in-alert UX feels insufficient.

**Post-delete behavior**: After successful `DELETE /api/v1/profile/account`, the ViewModel calls `authViewModel.signOut()` which clears tokens and sets `isAuthenticated = false`, returning the user to the login screen. The `hasCompletedOnboarding` `@AppStorage` flag is also reset to `false`.

**Post-sign-out behavior**: After calling `authViewModel.signOut()`, `isAuthenticated` becomes `false` and `EmberApp.swift` automatically transitions to the login screen.

**Haptics**: `HapticManager.impact(.medium)` on sign out. `HapticManager.notification(.warning)` when the delete confirmation alert appears. `HapticManager.notification(.error)` after successful account deletion (strong feedback for irreversible action).

**Accessibility**: Sign out button has `accessibilityLabel("Sign out of your account")`. Delete button has `accessibilityLabel("Delete your account permanently")`.

### 5.5 TimezonePickerSheet

**File path**: inline in `ProfileView.swift` or extracted as `ios/Ember/Features/Profile/TimezonePickerSheet.swift`

**Presented as**: `.sheet(isPresented: $viewModel.showTimezonePicker)`

**UI elements**:

- **Navigation bar**: Title "Select Timezone", trailing "Done" button that dismisses the sheet.
- **Search field**: `TextField("Search...", text: $searchText)` at the top.
- **Timezone list**: A `List` of `TimeZone.knownTimeZoneIdentifiers` filtered by `searchText`. Each row shows the IANA identifier (e.g., "America/New_York") and the current UTC offset (e.g., "UTC-05:00"). Tapping a row calls `viewModel.updateTimezone(identifier)` and dismisses the sheet.
- **Current selection**: The currently selected timezone row has a checkmark trailing icon in `Color.emberPrimary`.

**Accessibility**: Each timezone row has `accessibilityLabel("{identifier}, {offset}")`. Search field has `accessibilityLabel("Search timezones")`.

### 5.6 ProfileViewModel

**File path**: `ios/Ember/Features/Profile/ProfileViewModel.swift`

**Class definition**: `@Observable final class ProfileViewModel`

**Properties**:

| Property | Type | Purpose |
|----------|------|---------|
| `profile` | `ProfileData?` | The user's profile from the API |
| `characters` | `[Character]` | Character list for notification toggles |
| `isLoading` | `Bool` | True during initial profile fetch |
| `isSaving` | `Bool` | True during any profile update operation |
| `errorMessage` | `String?` | Non-nil when an error occurs |
| `showPhotoPicker` | `Bool` | Controls PhotosPicker presentation |
| `showTimezonePicker` | `Bool` | Controls timezone sheet presentation |
| `showDeleteConfirmation` | `Bool` | Controls delete confirmation alert |
| `deleteConfirmationText` | `String` | User input for delete confirmation |
| `isEditingName` | `Bool` | True when the name field is in edit mode |
| `editedName` | `String` | Current value of the name being edited |
| `notificationPreferences` | `[String: Bool]` | Local notification toggle states, keyed by preference ID |

**Private properties**:

| Property | Type | Purpose |
|----------|------|---------|
| `apiClient` | `APIClientProtocol` | Injected network client |

**Constructor**: `init(apiClient: APIClientProtocol = APIClient.shared)`

**Methods**:

`func loadProfile() async`

1. Set `isLoading = true`.
2. Clear `errorMessage`.
3. Fetch profile and characters in parallel using `async let`:
   - `async let profileResponse = apiClient.request(endpoint: .getProfile, responseType: ProfileData.self)`
   - `async let charactersResponse = apiClient.request(endpoint: .listCharacters, responseType: CharacterListResponse.self)`
4. On success: set `profile` and `characters`. Initialize `notificationPreferences` from `UserDefaults` (key: `"notification_preferences"`). If no stored preferences exist, default all toggles to `true`.
5. On failure: set `errorMessage`.
6. Set `isLoading = false`.

`func updateName() async`

1. Guard `editedName` is not empty after trimming whitespace. If empty, set `errorMessage = "Name cannot be empty"` and return.
2. Set `isSaving = true`.
3. Create `ProfileUpdateBody(name: editedName.trimmingCharacters(in: .whitespaces))`.
4. Call `apiClient.request(endpoint: .updateProfile, body: body, responseType: ProfileData.self)`.
5. On success: update `profile` with the response. Set `isEditingName = false`. Fire `HapticManager.notification(.success)`.
6. On failure: set `errorMessage`. Fire `HapticManager.notification(.error)`.
7. Set `isSaving = false`.

`func updateTimezone(_ timezone: String) async`

1. Set `isSaving = true`.
2. Create `ProfileUpdateBody(timezone: timezone)`.
3. Call `apiClient.request(endpoint: .updateProfile, body: body, responseType: ProfileData.self)`.
4. On success: update `profile`. Fire `HapticManager.notification(.success)`.
5. On failure: set `errorMessage`. Fire `HapticManager.notification(.error)`.
6. Set `isSaving = false`.

`func updateLanguage(_ language: String) async`

1. Set `isSaving = true`.
2. Create `ProfileUpdateBody(preferredLanguage: language)`.
3. Call `apiClient.request(endpoint: .updateProfile, body: body, responseType: ProfileData.self)`.
4. On success: update `profile`. Fire `HapticManager.notification(.success)`.
5. On failure: set `errorMessage`. Fire `HapticManager.notification(.error)`.
6. Set `isSaving = false`.

`func uploadAvatar(imageData: Data) async`

1. Set `isSaving = true`.
2. Request presigned URL: call `apiClient.request(endpoint: .uploadURL, body: UploadURLRequest(filename: "avatar.jpg", contentType: "image/jpeg", type: "photo"), responseType: UploadURLResponse.self)`.
3. Upload the image data directly to the presigned `uploadUrl` using a raw `URLSession.shared.upload(for:from:)` PUT request.
4. On successful upload, call `updateAvatarUrl(uploadResponse.fileUrl)` which sends `PUT /api/v1/profile` with `avatar_url = fileUrl`.
5. On success: update `profile`. Fire `HapticManager.notification(.success)`.
6. On failure: set `errorMessage`. Fire `HapticManager.notification(.error)`.
7. Set `isSaving = false`.

`func deleteAccount() async`

1. Guard `deleteConfirmationText == "DELETE MY ACCOUNT"`. If not, set `errorMessage` and return.
2. Set `isSaving = true`.
3. Call `apiClient.requestVoid(endpoint: .deleteAccount, body: AccountDeleteBody(confirmation: "DELETE MY ACCOUNT"))`.
4. On success: clear `@AppStorage("hasCompletedOnboarding")` by writing `false` to `UserDefaults.standard`. Set a flag `accountDeleted = true` that the view observes to trigger sign-out.
5. On failure: set `errorMessage`. Fire `HapticManager.notification(.error)`.
6. Set `isSaving = false`.
7. Clear `deleteConfirmationText`.

Note: The actual sign-out call (`authViewModel.signOut()`) is triggered from the View layer since `authViewModel` is an `@Environment` object. The ViewModel sets a boolean flag `accountDeleted`, and the View observes it with `.onChange(of: viewModel.accountDeleted)` to call `authViewModel.signOut()`.

`func signOut()` -- Sets a boolean flag `shouldSignOut = true` observed by the View to delegate to `authViewModel.signOut()`. This keeps the ViewModel decoupled from `AuthViewModel`.

`func updateNotificationPreference(key: String, value: Bool)`

1. Update `notificationPreferences[key] = value`.
2. Persist to `UserDefaults` under key `"notification_preferences"`.
3. Fire `HapticManager.selection()`.
4. No API call (placeholder for future notification preferences endpoint).

**Additional ViewModel properties for sign-out and delete flow**:

| Property | Type | Purpose |
|----------|------|---------|
| `shouldSignOut` | `Bool` | Signals the View to call `authViewModel.signOut()` |
| `accountDeleted` | `Bool` | Signals the View to call `authViewModel.signOut()` after account deletion |

### 5.7 PhotosPicker Integration

The avatar upload uses SwiftUI's `PhotosPicker` (iOS 16+). When the user selects a photo:

1. The `PhotosPickerItem` is loaded via `item.loadTransferable(type: Data.self)`.
2. The image data is compressed to JPEG with reasonable quality (0.8).
3. `viewModel.uploadAvatar(imageData:)` is called.

The `PhotosPicker` is presented via `.photosPicker(isPresented: $viewModel.showPhotoPicker, selection: $selectedPhotoItem, matching: .images)`. The `selectedPhotoItem` `onChange` handler triggers the upload.

---

## 6. Android Screens and Components

Not applicable. This is an iOS-only feature (layer: ios).

---

## 7. Test Plan

### iOS Tests

#### ProfileViewModelTests (Swift Testing)

**File path**: `ios/EmberTests/Features/Profile/ProfileViewModelTests.swift`

**Mock setup**: Use `MockAPIClient` (from test target). Configure it to return `ProfileData` and `CharacterListResponse`.

**Test scenarios**:

1. **loadProfile sets profile on success** -- Configure mock to return a `ProfileData` and a `CharacterListResponse` with 2 characters. Call `loadProfile()`. Assert `profile` is not nil, `characters.count == 2`, `isLoading == false`, `errorMessage == nil`.

2. **loadProfile sets errorMessage on network failure** -- Configure mock to throw `APIError.networkError(...)`. Call `loadProfile()`. Assert `profile` is nil, `errorMessage` is not nil, `isLoading == false`.

3. **loadProfile sets errorMessage on 401** -- Configure mock to throw `APIError.unauthorized`. Call `loadProfile()`. Assert `errorMessage` is not nil.

4. **updateName trims whitespace and sends PUT** -- Set `editedName = "  Alex  "`. Call `updateName()`. Assert the mock received a `ProfileUpdateBody` with `name: "Alex"`. Assert `profile.name == "Alex"` after the mock returns success.

5. **updateName rejects empty string** -- Set `editedName = "   "`. Call `updateName()`. Assert `errorMessage` is not nil. Assert the mock was NOT called.

6. **updateTimezone sends PUT** -- Call `updateTimezone("Europe/Istanbul")`. Assert the mock received `ProfileUpdateBody(timezone: "Europe/Istanbul")`. Assert `profile.timezone == "Europe/Istanbul"` after success.

7. **updateLanguage sends PUT** -- Call `updateLanguage("tr")`. Assert the mock received `ProfileUpdateBody(preferredLanguage: "tr")`. Assert `profile.preferredLanguage == "tr"` after success.

8. **uploadAvatar requests presigned URL then uploads** -- Configure mock to return an `UploadURLResponse`. Call `uploadAvatar(imageData: someData)`. Assert the mock was called with `.uploadURL` endpoint first, then `.updateProfile` endpoint.

9. **deleteAccount with correct confirmation succeeds** -- Set `deleteConfirmationText = "DELETE MY ACCOUNT"`. Call `deleteAccount()`. Assert the mock received `.deleteAccount` endpoint with `AccountDeleteBody(confirmation: "DELETE MY ACCOUNT")`. Assert `accountDeleted == true`.

10. **deleteAccount with wrong confirmation does not call API** -- Set `deleteConfirmationText = "delete"`. Call `deleteAccount()`. Assert the mock was NOT called. Assert `errorMessage` is not nil.

11. **deleteAccount on server error sets errorMessage** -- Configure mock to throw `APIError.serverError(statusCode: 503, ...)`. Call `deleteAccount()` with correct confirmation. Assert `errorMessage` is not nil. Assert `accountDeleted == false`.

12. **updateNotificationPreference persists to UserDefaults** -- Call `updateNotificationPreference(key: "morning_checkin", value: false)`. Assert `notificationPreferences["morning_checkin"] == false`. Verify `UserDefaults` was updated.

13. **signOut sets shouldSignOut flag** -- Call `signOut()`. Assert `shouldSignOut == true`.

14. **loadProfile fetches profile and characters in parallel** -- This is an implementation detail test. Verify both mock endpoints (`.getProfile` and `.listCharacters`) are called when `loadProfile()` is invoked.

#### MockAPIClient updates

The existing `MockAPIClient` needs to support returning different response types per endpoint. If not already done, add a dictionary-based approach: `var responses: [String: Any]` keyed by endpoint path, so different endpoints return different mock responses.

#### UI Tests (optional stretch goal)

- Launch app in authenticated + onboarded state.
- Verify profile photo, name, and email are displayed.
- Tap the name to enter edit mode, type a new name, tap Save.
- Tap Sign Out and verify transition to login screen.

---

## 8. Acceptance Criteria

1. Given the user is authenticated and taps the Profile tab, when the profile loads successfully, then the user's avatar (or initial), name, email, and subscription tier are displayed.

2. Given the user taps their avatar, when the photo picker is presented and the user selects an image, then the image is uploaded to S3 via presigned URL and the profile's `avatar_url` is updated via `PUT /api/v1/profile`.

3. Given the user taps their display name, when they edit the name and tap Save, then the name is updated via `PUT /api/v1/profile` and the UI reflects the new name.

4. Given the user taps the Timezone row, when the timezone picker sheet is presented and the user selects a timezone, then the timezone is updated via `PUT /api/v1/profile`.

5. Given the user taps the language toggle, when the language changes between English and Turkish, then the preferred language is updated via `PUT /api/v1/profile`.

6. Given the user toggles a notification preference, when the toggle state changes, then the new state is persisted locally in `UserDefaults` (no API call in this feature).

7. Given the user taps Sign Out, when the sign-out completes, then the user is returned to the login screen (tokens are cleared, `isAuthenticated` becomes `false`).

8. Given the user taps Delete Account, when the confirmation alert is presented and the user types "DELETE MY ACCOUNT" and taps Delete, then `DELETE /api/v1/profile/account` is called, on success the user is signed out and returned to the login screen, and `hasCompletedOnboarding` is reset to `false`.

9. Given the user taps Delete Account and types the wrong confirmation text, when they tap Delete, then the delete button is disabled (the API is not called).

10. Given the profile API call fails, when ProfileView loads, then an error alert is shown with a Retry button.

11. Given a profile update API call fails, when the user tries to save changes, then an error message is displayed and the previous values are preserved.

12. Given VoiceOver is enabled, when the user navigates ProfileView, then all interactive elements (avatar, name, timezone row, language toggle, notification toggles, sign out, delete account) have meaningful accessibility labels.

13. Given a profile update succeeds, then a success haptic fires (`HapticManager.notification(.success)`).

14. Given the app is in dark mode (forced), then all ProfileView elements use colors from `Color+Ember.swift` and render correctly on a dark background.

---

## 9. File Manifest

```
iOS:
  CREATE  ios/Ember/Features/Profile/ProfileView.swift
  CREATE  ios/Ember/Features/Profile/ProfileViewModel.swift
  CREATE  ios/Ember/Core/Models/ProfileModels.swift
  DELETE  ios/Ember/Features/Profile/ProfilePlaceholderView.swift
  MODIFY  ios/Ember/App/MainTabView.swift (replace ProfilePlaceholderView with ProfileView)
  CREATE  ios/EmberTests/Features/Profile/ProfileViewModelTests.swift

Shared:
  CREATE  shared/feature-specs/ios-profile-view.md (this file)
  CREATE  docs/pipeline/ios-profile-view-architect.handoff.md
```

### Modification Details

**MainTabView.swift**: Replace `ProfilePlaceholderView()` with `ProfileView()` on line 50 (inside the third `NavigationStack`).

**ProfileModels.swift**: Contains `ProfileData`, `ProfileUpdateBody`, `AccountDeleteBody`, `UploadURLRequest`, and `UploadURLResponse`. If `UploadURLRequest`/`UploadURLResponse` already exist in another model file from a previous feature, they should be reused from that location instead of duplicated.

### Notes on Existing Files

- `APIEndpoint.swift` already has all required endpoint cases (`.getProfile`, `.updateProfile`, `.deleteAccount`, `.uploadURL`). No changes needed.
- `AppRouter.swift` does not need changes. No new routes are introduced since ProfileView is a tab root, not a pushed destination.
- `EmberSymbol.swift` may need a few new constants (e.g., `chevron.right` for row disclosure, `camera.fill` for avatar overlay) but these can use SF Symbol names inline. Adding constants is optional.
- `AuthViewModel.swift` already has `signOut()`. No changes needed.
