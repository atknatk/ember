# Architect Handoff: iOS Profile View

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## What Was Designed

The production ProfileView screen for iOS, replacing the existing `ProfilePlaceholderView`. The screen provides profile header with avatar upload, name editing, timezone/language preferences, notification toggle placeholders, sign-out, and GDPR-compliant account deletion with typed confirmation.

## Key Decisions

- **Notification toggles are UI-only placeholders**: The toggle states are stored in `UserDefaults` and do not call the `PUT /notifications/preferences` API. The backend notification preferences feature is not yet fully integrated. This avoids blocking the profile screen on an incomplete backend dependency.
- **Sign-out and delete-account delegation via boolean flags**: The ViewModel sets `shouldSignOut` or `accountDeleted` flags, and the View observes them to call `authViewModel.signOut()`. This keeps the ViewModel decoupled from `AuthViewModel` (which lives in the `@Environment`).
- **ProfileData model is separate from UserResponse**: The existing `UserResponse` in `AuthModels.swift` uses `String` for `createdAt`, while `ProfileData` uses `Date` for proper decoding. This avoids a breaking change to the auth flow.
- **Avatar upload uses presigned PUT**: Follows the established pattern from P01-10 (media-upload). The flow is: request presigned URL -> PUT image data to S3 -> update profile `avatar_url` via PUT /profile.
- **Delete confirmation uses SwiftUI .alert with TextField**: Valid for iOS 17+ target. The developer may use a `.sheet` instead if the alert UX feels constrained.
- **Parallel fetch for profile and characters**: `loadProfile()` uses `async let` to fetch `GET /profile` and `GET /characters` in parallel, since characters are needed for per-character notification toggles.

## Spec Location

`shared/feature-specs/ios-profile-view.md`

## Assumptions Made

- `MockAPIClient` in the test target can be extended to support returning different response types per endpoint.
- `UploadURLRequest` and `UploadURLResponse` models may already exist from a media upload feature. If so, they should be reused rather than duplicated.
- The `PhotosPicker` API from PhotosUI is available (iOS 16+, within the iOS 17+ target).

## Dependencies

- Requires: P03-01 (ios-scaffold), P03-02 (ios-network-layer), P03-03 (ios-cognito-auth), P03-06 (ios-home-view), P1.5-02 (profile-crud-endpoints), P01-10 (media-upload)
- Blocks: ios-dev (implements this spec)

## Next Steps

ios-dev should read the spec at `shared/feature-specs/ios-profile-view.md` and implement accordingly.
