# Android Dev Handoff: Android Profile Screen

**Date**: 2026-03-13
**Agent**: android-dev
**Status**: COMPLETE

## Implemented Files
- `android/app/src/main/java/ai/ember/app/features/profile/ProfileModels.kt`
- `android/app/src/main/java/ai/ember/app/features/profile/ProfileApi.kt`
- `android/app/src/main/java/ai/ember/app/features/profile/ProfileUiState.kt`
- `android/app/src/main/java/ai/ember/app/features/profile/ProfileRepository.kt`
- `android/app/src/main/java/ai/ember/app/features/profile/ProfileModule.kt`
- `android/app/src/main/java/ai/ember/app/features/profile/ProfileViewModel.kt`
- `android/app/src/main/java/ai/ember/app/features/profile/ProfileScreen.kt`
- `android/app/src/main/java/ai/ember/app/features/profile/TimezonePickerDialog.kt`
- `android/app/src/main/java/ai/ember/app/core/navigation/EmberNavHost.kt` (modified)
- `android/app/src/main/res/values/strings.xml` (modified)
- `android/app/src/test/java/ai/ember/app/features/profile/ProfileViewModelTest.kt`
- `android/app/src/test/java/ai/ember/app/features/profile/ProfileRepositoryTest.kt`

## Screens Implemented
- ProfileScreen: Full profile/settings screen with header, preferences, account actions

## strings.xml Keys Added
- `profile_save`: "Save"
- `profile_cancel`: "Cancel"
- `profile_retry`: "Retry"
- `profile_avatar_a11y`: "Profile photo. Tap to change"
- `profile_name_a11y`: "Display name: %1$s. Tap to edit"
- `profile_tier_premium`: "Premium"
- `profile_tier_free`: "Free"
- `profile_preferences_title`: "Preferences"
- `profile_timezone_label`: "Timezone"
- `profile_timezone_a11y`: "Timezone. Opens timezone picker"
- `profile_language_label`: "Language"
- `profile_language_english`: "English"
- `profile_language_turkish`: "Turkish"
- `profile_language_a11y`: "Language. Tap to change"
- `profile_notifications_title`: "Notifications"
- `profile_notif_morning`: "Morning Check-in"
- `profile_notif_evening`: "Evening Reflection"
- `profile_notif_sleep`: "Sleep Reminder"
- `profile_account_title`: "Account"
- `profile_sign_out`: "Sign Out"
- `profile_sign_out_a11y`: "Sign out of your account"
- `profile_delete_account`: "Delete Account"
- `profile_delete_account_a11y`: "Delete your account permanently"
- `profile_delete_dialog_title`: "Delete Account"
- `profile_delete_dialog_message`: (delete confirmation message)
- `profile_delete_dialog_hint`: "DELETE MY ACCOUNT"
- `profile_delete_confirm`: "Delete"
- `profile_delete_cancel`: "Cancel"
- `profile_timezone_picker_title`: "Select Timezone"
- `profile_timezone_search_hint`: "Search timezones..."
- `profile_timezone_search_a11y`: "Search timezones"

## Deviations from Spec
- None

## Notes for Android Tester
- ViewModel depends on `ProfileRepository` and `AuthRepository` -- use MockK `mockk<ProfileRepository>()` and `mockk<AuthRepository>(relaxed = true)`
- Profile and characters are loaded in parallel via `async/await`
- Avatar upload is a 3-step process: get presigned URL, upload to S3, update profile
- Notification preferences are local-only (no API call)
- Turbine is configured in project -- use `.test { }` for StateFlow assertions
- `shouldSignOut` StateFlow signals navigation back to auth screen
- Delete confirmation requires exact string match "DELETE MY ACCOUNT"
