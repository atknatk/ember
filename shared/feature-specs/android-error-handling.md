# Feature Spec: Android Error Handling (P04-09)

## Overview

Centralized error handling for all Android screens — error banners, retry logic, offline detection (ConnectivityManager), user-friendly error messages, and exponential backoff.

## Problem

Before this feature, each ViewModel used raw `e.message` strings and each Repository had duplicated `parseErrorMessage()` logic. This led to:

1. Inconsistent error messages across screens (raw system error text vs. user-friendly)
2. No centralized error type — each feature had its own exception class (ChatException, HomeException, etc.)
3. No offline detection or connectivity awareness
4. No retry logic for transient failures
5. No way to distinguish retryable vs. fatal errors
6. Errors in Success state (e.g., send message failure) had no UI feedback mechanism

## Solution

### 1. EmberError Sealed Class

A centralized error type that maps exceptions and HTTP status codes into categories:

- **Offline** — UnknownHostException, device offline
- **NetworkError** — SSL, connection reset, generic IO
- **ServerError** — 5xx status codes
- **Unauthorized** — 401, requires re-authentication
- **NotFound** — 404
- **RateLimited** — 429
- **Timeout** — SocketTimeoutException, 408
- **Unknown** — catch-all

Each category has:
- `userMessage: String` — never exposes raw error text
- `isRetryable: Boolean` — retry semantics per error type
- `requiresReauth: Boolean` — expired session detection
- `EmberError.from(error)` — factory mapping any Throwable to EmberError
- `EmberError.fromHttpStatus(code)` — factory mapping HTTP status codes

### 2. ErrorBanner Composable

A non-blocking, dismissible banner that slides down from the top:
- Error icon, user-friendly message, optional retry button, dismiss button
- Auto-dismisses after 5 seconds (configurable)
- Haptic feedback (REJECT) on appearance
- Only shows retry button for `isRetryable` errors
- AnimatedVisibility with expand/shrink vertical animation

### 3. OfflineBanner Composable

A persistent (non-dismissible) amber/warning banner when offline:
- Uses EmberWarning color styling
- Automatically appears/disappears with connectivity changes
- Placed above error banners in the overlay

### 4. NetworkMonitor

ConnectivityManager-based online/offline detection:
- Singleton injected via Hilt
- Exposes `isOnline: StateFlow<Boolean>`
- Uses NetworkCallback for real-time connectivity changes
- Validates both INTERNET capability and VALIDATED capability
- Passed through EmberNavHost to all screens

### 5. RetryHelper

Exponential backoff utility:
- Configurable max retries (default 3), base delay (1s), max delay (10s)
- Random jitter to avoid thundering herd
- Only retries EmberError.isRetryable errors
- Non-retryable errors throw immediately
- Standalone utility — not auto-integrated into ViewModels

### 6. ViewModel Updates

All ViewModels updated to:
- Add `currentError: EmberError?` field in their Success UiState
- Use `EmberError.from(error)` in catch/onFailure blocks
- Provide `dismissError()` method that clears currentError
- Use `emberError.userMessage` for Error state messages

### 7. Screen Updates

All Screens updated to:
- Accept optional `NetworkMonitor` parameter
- Add `OfflineBanner` overlay for offline detection
- Add `ErrorBanner` overlay for transient errors from Success state
- Wrap content in `Box` with banners at `Alignment.TopCenter`
- Destructive action dialogs (delete account, delete memory) remain as AlertDialogs

## Files

### New Files
- `android/.../core/error/EmberError.kt` — Sealed error class with factory methods
- `android/.../core/error/RetryHelper.kt` — Exponential backoff utility
- `android/.../core/network/NetworkMonitor.kt` — ConnectivityManager-based monitor
- `android/.../core/ui/components/ErrorBanner.kt` — Dismissible error banner
- `android/.../core/ui/components/OfflineBanner.kt` — Persistent offline banner

### Modified Files
- `android/.../MainActivity.kt` — Inject NetworkMonitor, pass to EmberNavHost
- `android/.../core/navigation/EmberNavHost.kt` — Accept and distribute NetworkMonitor
- `android/.../features/home/HomeUiState.kt` — Add currentError field
- `android/.../features/home/HomeViewModel.kt` — Use EmberError, add dismissError
- `android/.../features/home/HomeScreen.kt` — Add ErrorBanner + OfflineBanner
- `android/.../features/chat/ChatUiState.kt` — Add currentError field
- `android/.../features/chat/ChatViewModel.kt` — Use EmberError, add dismissError
- `android/.../features/chat/ChatScreen.kt` — Add ErrorBanner + OfflineBanner
- `android/.../features/memories/MemoriesUiState.kt` — Add currentError field
- `android/.../features/memories/MemoriesViewModel.kt` — Use EmberError, add dismissError
- `android/.../features/memories/MemoriesScreen.kt` — Add ErrorBanner + OfflineBanner
- `android/.../features/profile/ProfileUiState.kt` — Add currentError field
- `android/.../features/profile/ProfileViewModel.kt` — Use EmberError, add dismissError
- `android/.../features/profile/ProfileScreen.kt` — Add ErrorBanner + OfflineBanner
- `android/app/src/main/AndroidManifest.xml` — Add ACCESS_NETWORK_STATE permission
- `android/app/src/main/res/values/strings.xml` — Add error handling strings

### Test Files
- `android/.../core/error/EmberErrorTest.kt` — Error mapping and semantics
- `android/.../core/error/RetryHelperTest.kt` — Retry logic and backoff calculation
- `android/.../core/network/NetworkMonitorTest.kt` — Connectivity check logic

## Design Decisions

1. **Banner over Snackbar**: Non-blocking banners slide from top — more visible and support retry buttons. Snackbar is kept for success confirmations (e.g., "Name updated").

2. **Dual error storage**: ViewModels keep both the sealed Error UiState (for full-screen errors on initial load) and `currentError: EmberError?` within Success state (for transient errors during operations).

3. **Auto-dismiss**: Error banners auto-dismiss after 5 seconds. Offline banners never auto-dismiss.

4. **NetworkMonitor as optional parameter**: Screens accept `NetworkMonitor?` to maintain backward compatibility with previews and tests.

5. **Destructive dialogs preserved**: Delete account and delete memory still use AlertDialog (not banner) per task requirements.

6. **RetryHelper standalone**: Not auto-integrated — provides utility for features that want automatic retry. The banner retry button handles user-initiated retry.
