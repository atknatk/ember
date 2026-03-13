# iOS Dev Handoff: iOS Error Handling

**Date**: 2026-03-13
**Agent**: ios-dev
**Status**: COMPLETE

## Implemented Files

### New
- `ios/Ember/Core/Error/EmberError.swift` — Centralized error enum with user-friendly messages, retry semantics, factory method
- `ios/Ember/Core/Components/ErrorBannerView.swift` — Dismissible slide-down error banner with optional retry
- `ios/Ember/Core/Network/NetworkMonitor.swift` — @Observable NWPathMonitor wrapper for connectivity detection
- `ios/Ember/Core/Components/OfflineBannerView.swift` — Persistent offline warning banner
- `ios/Ember/Core/Utils/RetryHelper.swift` — Exponential backoff retry utility

### Modified
- `ios/Ember/App/EmberApp.swift` — NetworkMonitor injection into environment
- `ios/Ember/Features/Home/HomeViewModel.swift` — Added currentError, dismissError()
- `ios/Ember/Features/Home/HomeView.swift` — Replaced .alert with ErrorBannerView + OfflineBannerView
- `ios/Ember/Features/Chat/ChatViewModel.swift` — Added currentError, updated catch blocks
- `ios/Ember/Features/Chat/ChatView.swift` — Replaced .alert with ErrorBannerView + OfflineBannerView
- `ios/Ember/Features/Memories/MemoriesViewModel.swift` — Added currentError, dismissError()
- `ios/Ember/Features/Memories/MemoriesView.swift` — Replaced error .alert with ErrorBannerView + OfflineBannerView
- `ios/Ember/Features/Profile/ProfileViewModel.swift` — Added currentError, dismissError(), setError() helper
- `ios/Ember/Features/Profile/ProfileView.swift` — Replaced .alert with ErrorBannerView + OfflineBannerView

### Tests
- `ios/EmberTests/Core/Error/EmberErrorTests.swift` — 30+ tests covering messages, retry semantics, factory mapping, equatable
- `ios/EmberTests/Core/Network/NetworkMonitorTests.swift` — Initial state and connection type tests

## Screens Implemented
- ErrorBannerView: Reusable component across all screens
- OfflineBannerView: Reusable component across all screens
- Updated: HomeView, ChatView, MemoriesView, ProfileView

## Deviations from Spec
- None

## Notes for iOS Tester
- `EmberError.from()` factory handles APIError, AuthError, URLError, and passthrough of existing EmberError
- ErrorBannerView auto-dismisses after 5 seconds; test by setting autoDismissDelay to nil
- NetworkMonitor requires NWPathMonitor which needs real device or simulator with network controls
- RetryHelper.withExponentialBackoff throws immediately for non-retryable errors
- All ViewModels maintain backward compatibility: errorMessage String is still set alongside currentError
- Test that MemoriesView delete confirmation alert (`.alert("Delete Memory?")`) still works (not replaced)
- Test that ProfileView delete account alert still works (not replaced)
