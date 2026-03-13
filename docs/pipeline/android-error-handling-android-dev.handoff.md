# Android Dev Handoff: Android Error Handling

**Date**: 2026-03-13
**Agent**: android-dev
**Status**: COMPLETE

## Implemented Files
- `android/app/src/main/java/ai/ember/app/core/error/EmberError.kt`
- `android/app/src/main/java/ai/ember/app/core/error/RetryHelper.kt`
- `android/app/src/main/java/ai/ember/app/core/network/NetworkMonitor.kt`
- `android/app/src/main/java/ai/ember/app/core/ui/components/ErrorBanner.kt`
- `android/app/src/main/java/ai/ember/app/core/ui/components/OfflineBanner.kt`

## Modified Files
- `android/app/src/main/java/ai/ember/app/MainActivity.kt`
- `android/app/src/main/java/ai/ember/app/core/navigation/EmberNavHost.kt`
- `android/app/src/main/java/ai/ember/app/features/home/HomeUiState.kt`
- `android/app/src/main/java/ai/ember/app/features/home/HomeViewModel.kt`
- `android/app/src/main/java/ai/ember/app/features/home/HomeScreen.kt`
- `android/app/src/main/java/ai/ember/app/features/chat/ChatUiState.kt`
- `android/app/src/main/java/ai/ember/app/features/chat/ChatViewModel.kt`
- `android/app/src/main/java/ai/ember/app/features/chat/ChatScreen.kt`
- `android/app/src/main/java/ai/ember/app/features/memories/MemoriesUiState.kt`
- `android/app/src/main/java/ai/ember/app/features/memories/MemoriesViewModel.kt`
- `android/app/src/main/java/ai/ember/app/features/memories/MemoriesScreen.kt`
- `android/app/src/main/java/ai/ember/app/features/profile/ProfileUiState.kt`
- `android/app/src/main/java/ai/ember/app/features/profile/ProfileViewModel.kt`
- `android/app/src/main/java/ai/ember/app/features/profile/ProfileScreen.kt`
- `android/app/src/main/AndroidManifest.xml`
- `android/app/src/main/res/values/strings.xml`

## Test Files
- `android/app/src/test/java/ai/ember/app/core/error/EmberErrorTest.kt`
- `android/app/src/test/java/ai/ember/app/core/error/RetryHelperTest.kt`
- `android/app/src/test/java/ai/ember/app/core/network/NetworkMonitorTest.kt`

## Screens Implemented
- ErrorBanner: Non-blocking, dismissible error banner with slide-down animation, auto-dismiss, retry button
- OfflineBanner: Persistent amber banner for offline state detection
- Updated all 4 main screens (Home, Chat, Memories, Profile) with overlay banners

## strings.xml Keys Added
- `error_banner_retry`: "Retry"
- `error_banner_dismiss`: "Dismiss error"
- `error_banner_a11y`: "Error: %1$s"
- `offline_banner_message`: "You are offline"
- `offline_banner_a11y`: "No internet connection"

## Deviations from Spec
- None

## Notes for Android Tester
- EmberError: Test all `from()` mappings — UnknownHostException -> Offline, SocketTimeoutException -> Timeout, etc.
- RetryHelper: Use `baseDelayMs = 1` and `jitter = false` in tests to avoid slow tests
- NetworkMonitor: Uses MockK to mock ConnectivityManager; callback flow requires instrumentation tests
- ViewModels: Each now has `dismissError()` — verify `currentError` is cleared in UiState
- ErrorBanner: Auto-dismisses after 5 seconds via `LaunchedEffect` + `delay`
- Existing tests may need `currentError = null` added to assertions checking Success state equality
- Turbine `.test { }` works for all StateFlow assertions
