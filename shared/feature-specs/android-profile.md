# Feature Spec: P04-07 -- Android Profile Screen

**Feature ID**: P04-07
**Phase**: 4
**Layer**: android
**GitHub Issue**: #34
**Date**: 2026-03-13
**Author**: architect

---

## 1. Overview

### What This Feature Does

Replaces the placeholder `ProfileScreen` with a production profile/settings screen. ProfileScreen is the third tab in the bottom navigation and serves as the user's settings hub. It contains:

1. **Profile header** -- Displays the user's avatar (from S3 or a gradient initial circle), display name (tap to edit), email, and subscription tier badge.

2. **Preferences section** -- Timezone picker (searchable bottom sheet), preferred language toggle (English/Turkish), and notification preferences with per-character toggles.

3. **Account section** -- Sign out button and delete account button with a two-step confirmation flow requiring the user to type "DELETE MY ACCOUNT".

### Dependencies

- **P04-01** (android-scaffold) -- Provides EmberNavHost, bottom navigation, theme tokens.
- **P04-02** (android-cognito-auth) -- Provides AuthRepository with signOut().
- **P04-06** (android-home-screen) -- Establishes patterns for ViewModel, Repository, Module.
- **P1.5-02** (profile-crud-endpoints) -- Backend GET/PUT /profile, DELETE /profile/account.
- **P01-10** (media-upload) -- Backend POST /media/upload-url for avatar upload.

### What This Feature Does NOT Do

- Does not implement partner section (Phase 8).
- Does not implement password change.
- Does not implement data export.
- Notification toggles are UI-only placeholders (no API call).

---

## 2. Data Models

### ProfileData
Maps to GET /api/v1/profile response.

### ProfileUpdateRequest
Maps to PUT /api/v1/profile request body.

### AccountDeleteRequest
Maps to DELETE /api/v1/profile/account request body.

### UploadUrlRequest / UploadUrlResponse
Maps to POST /api/v1/media/upload-url.

---

## 3. API Endpoints

All existing backend endpoints, no new endpoints created.

- GET /api/v1/profile
- PUT /api/v1/profile
- DELETE /api/v1/profile/account
- POST /api/v1/media/upload-url
- GET /api/v1/characters

---

## 4. Android Screens and Components

### ProfileScreen
Main composable with three sections. Uses Scaffold with SnackbarHost.
Handles Loading, Success, and Error UI states.

### ProfileHeader
Avatar (Coil AsyncImage or gradient initial), editable name, email, tier badge.

### PreferencesSection
Timezone row, language row, notification toggles (morning, evening, sleep, per-character).

### AccountSection
Sign out and delete account cards.

### TimezonePickerDialog
ModalBottomSheet with search field and scrollable timezone list.

### DeleteConfirmationDialog
AlertDialog with TextField requiring "DELETE MY ACCOUNT" confirmation text.

### ProfileViewModel
Manages profile loading, updates, avatar upload, sign out, delete account.
Uses sealed ProfileUiState with Loading, Success, Error variants.

### ProfileRepository
Wraps ProfileApi calls into Result pattern.

### ProfileModule
Hilt module providing ProfileApi via Retrofit.

---

## 5. Test Plan

### ProfileViewModelTest
1. loadProfile fetches profile and characters in parallel
2. loadProfile sets Error when profile fetch fails
3. loadProfile succeeds even if characters fetch fails
4. saveName trims whitespace and sends update
5. saveName rejects empty string
6. cancelEditingName restores original name
7. updateTimezone sends PUT and updates state
8. updateLanguage sends PUT and updates state
9. deleteAccount with correct confirmation succeeds and signs out
10. deleteAccount with wrong confirmation does not call API
11. deleteAccount on server error sets snackbar message
12. signOut calls authRepository and sets shouldSignOut
13. updateNotificationPreference updates local state
14. clearSnackbar clears snackbar message

### ProfileRepositoryTest
1. getProfile returns success on 200
2. getProfile returns failure on null body
3. getProfile returns failure on 401
4. getProfile returns failure on network exception
5. updateProfile returns success on 200
6. updateProfile returns failure on 422
7. deleteAccount returns success on 204
8. deleteAccount returns failure on 400
9. getUploadUrl returns success on 200
10. getCharacters returns success on 200
11. getCharacters returns failure on network error

---

## 6. File Manifest

```
Android:
  CREATE  android/.../features/profile/ProfileModels.kt
  CREATE  android/.../features/profile/ProfileApi.kt
  CREATE  android/.../features/profile/ProfileUiState.kt
  CREATE  android/.../features/profile/ProfileRepository.kt
  CREATE  android/.../features/profile/ProfileModule.kt
  CREATE  android/.../features/profile/ProfileViewModel.kt
  MODIFY  android/.../features/profile/ProfileScreen.kt
  CREATE  android/.../features/profile/TimezonePickerDialog.kt
  MODIFY  android/.../core/navigation/EmberNavHost.kt
  MODIFY  android/app/src/main/res/values/strings.xml
  CREATE  android/.../test/.../profile/ProfileViewModelTest.kt
  CREATE  android/.../test/.../profile/ProfileRepositoryTest.kt

Shared:
  CREATE  shared/feature-specs/android-profile.md
  CREATE  docs/pipeline/android-profile-architect.handoff.md
  CREATE  docs/pipeline/android-profile-android-dev.handoff.md
```
