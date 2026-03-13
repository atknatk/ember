# iOS Dev Handoff: iOS Profile View

**Date**: 2026-03-13
**Agent**: ios-dev
**Status**: COMPLETE

## Implemented Files

- `ios/Ember/Features/Profile/ProfileView.swift` (CREATE)
- `ios/Ember/Features/Profile/ProfileViewModel.swift` (CREATE)
- `ios/Ember/Features/Profile/TimezonePickerSheet.swift` (CREATE)
- `ios/Ember/Core/Models/ProfileModels.swift` (CREATE)
- `ios/EmberTests/Features/Profile/ProfileViewModelTests.swift` (CREATE)
- `ios/Ember/Features/Profile/ProfilePlaceholderView.swift` (DELETE)
- `ios/Ember/App/MainTabView.swift` (MODIFY -- replaced ProfilePlaceholderView with ProfileView)
- `ios/Ember.xcodeproj/project.pbxproj` (MODIFY -- updated file references)

## Screens Implemented

- **ProfileView**: Full profile screen with header (avatar upload via PhotosPicker + Kingfisher, inline name editing, email display, subscription badge), preferences section (timezone picker sheet, language segmented picker, per-character notification toggles stored in UserDefaults), and account section (sign out, delete account with typed confirmation)
- **TimezonePickerSheet**: Searchable sheet presenting all IANA timezones with UTC offset display and current selection checkmark

## Deviations from Spec

- None. All spec requirements were implemented as designed.

## Notes for iOS Tester

- ViewModel uses `APIClientProtocol` -- create a `MockProfileAPIClient` implementing this protocol (example in test file)
- Test `loadProfile()` with parallel fetch of profile and characters using `async let`
- Test `updateName()` with whitespace trimming and empty string rejection
- Test `deleteAccount()` with correct/wrong confirmation text
- The `uploadAvatar()` method makes 3 sequential API calls: presigned URL, S3 PUT upload, profile update -- mock each step
- Notification preferences are stored locally in `UserDefaults` key `"notification_preferences"` -- clean up after tests
- Sign-out and delete-account delegation uses boolean flags (`shouldSignOut`, `accountDeleted`) observed by the View via `.onChange` to call `authViewModel.signOut()`
- The delete confirmation uses SwiftUI `.alert` with `TextField` (iOS 17+)
