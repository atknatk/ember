# Feature Spec: iOS Error Handling (P03-11)

## Overview

Centralized error handling for all iOS screens — network error banners, retry logic, offline detection, and user-friendly error messages.

## Problem

Before this feature, each ViewModel used raw `error.localizedDescription` strings, and each View used `.alert()` modifiers for error display. This led to:

1. Inconsistent error messages across screens (raw system error text vs. user-friendly)
2. Blocking `.alert()` modals for non-critical errors (network hiccups)
3. No offline detection or connectivity awareness
4. No retry logic for transient failures
5. No way to distinguish retryable vs. fatal errors

## Solution

### 1. EmberError Enum

A centralized error type that wraps `APIError`, `AuthError`, and `URLError` into a single type with:

- **User-friendly messages** — never expose raw error text
- **Retry semantics** — `isRetryable` flag for each error type
- **Reauth detection** — `requiresReauth` flag for expired sessions
- **Factory method** — `EmberError.from(error)` maps any `Error` to `EmberError`

### 2. ErrorBannerView

A non-blocking, dismissible banner that slides down from the top:

- Shows error icon, message, optional retry button, dismiss button
- Auto-dismisses after 5 seconds (configurable)
- Haptic feedback on appearance
- Only shows retry button for `isRetryable` errors

### 3. NetworkMonitor

An `@Observable` class using `NWPathMonitor` to detect connectivity changes:

- Injected via `@Environment(NetworkMonitor.self)` at app root
- Exposes `isConnected` and `connectionType`
- Started once at app launch

### 4. OfflineBannerView

A persistent (non-dismissible) warning banner shown when offline:

- Uses warning color styling (amber)
- Automatically appears/disappears with connectivity changes
- Placed in overlay above error banners

### 5. RetryHelper

Exponential backoff utility for transient errors:

- Configurable max retries, base delay, max delay, jitter
- Only retries for `EmberError.isRetryable` errors
- Non-retryable errors throw immediately

### 6. ViewModel Updates

All ViewModels updated to:

- Store `currentError: EmberError?` alongside `errorMessage: String?`
- Use `EmberError.from(error)` in catch blocks
- Provide `dismissError()` method that clears both

### 7. View Updates

All Views updated to:

- Replace `.alert()` error modals with `ErrorBannerView` overlays
- Add `OfflineBannerView` for offline detection
- Inject `NetworkMonitor` from environment

## Files

### New Files
- `ios/Ember/Core/Error/EmberError.swift`
- `ios/Ember/Core/Components/ErrorBannerView.swift`
- `ios/Ember/Core/Network/NetworkMonitor.swift`
- `ios/Ember/Core/Components/OfflineBannerView.swift`
- `ios/Ember/Core/Utils/RetryHelper.swift`

### Modified Files
- `ios/Ember/App/EmberApp.swift` — inject NetworkMonitor
- `ios/Ember/Features/Home/HomeViewModel.swift` — add currentError, dismissError
- `ios/Ember/Features/Home/HomeView.swift` — ErrorBannerView + OfflineBannerView
- `ios/Ember/Features/Chat/ChatViewModel.swift` — add currentError, dismissError
- `ios/Ember/Features/Chat/ChatView.swift` — ErrorBannerView + OfflineBannerView
- `ios/Ember/Features/Memories/MemoriesViewModel.swift` — add currentError, dismissError
- `ios/Ember/Features/Memories/MemoriesView.swift` — ErrorBannerView + OfflineBannerView
- `ios/Ember/Features/Profile/ProfileViewModel.swift` — add currentError, dismissError, setError helper
- `ios/Ember/Features/Profile/ProfileView.swift` — ErrorBannerView + OfflineBannerView

### Test Files
- `ios/EmberTests/Core/Error/EmberErrorTests.swift`
- `ios/EmberTests/Core/Network/NetworkMonitorTests.swift`

## Design Decisions

1. **Banner over Alert**: Non-blocking banners are less intrusive for transient errors. The user can continue interacting with the app while seeing the error.

2. **Dual error storage**: ViewModels keep both `errorMessage: String?` (backward compatibility) and `currentError: EmberError?` (typed error for banner). This avoids breaking existing tests that check `errorMessage`.

3. **Auto-dismiss**: Error banners auto-dismiss after 5 seconds by default. Offline banners never auto-dismiss.

4. **RetryHelper as standalone**: Not integrated into ViewModels by default — it's a utility for features that want automatic retry (e.g., background sync). Views handle retry via the banner's retry button.
