# iOS Scaffold

> Establishes the foundational Xcode project, SwiftUI app entry point, tab navigation, and design system constants that all subsequent Ember iOS features build upon.

**Status**: Released
**Added in**: Phase 3 (P03-01)
**Platforms**: iOS
**GitHub Issue**: #17

---

## Overview

The iOS scaffold creates everything a developer needs before writing a single feature screen: a working Xcode project, a three-tab `MainTabView` with `NavigationStack` per tab, an `@Observable` router and dependency container, the complete Ember design system (colors, typography, spacing, corner radii), core protocol stubs for networking and authentication, and placeholder views that prove the navigation flow end-to-end.

Every subsequent iOS feature -- authentication, character list, chat, memory display, real-time voice -- has a hard prerequisite on this scaffold. Without it, there is no app target to add views to, no design system constants to reference, and no dependency injection container to pull services from. The scaffold intentionally makes no network calls: the `APIClientProtocol` and `AuthServiceProtocol` are empty stubs, and the `AuthService` implementation throws `AuthError.notImplemented` for all methods. Real implementations arrive with the first networking feature.

Dark mode is enforced globally from this scaffold via `.preferredColorScheme(.dark)` on every view branch in `EmberApp`. The app never renders in light mode, matching the design system requirement from `docs/14-tasarim.md`. For the scaffold phase, `@AppStorage` booleans (`isAuthenticated`, `hasCompletedOnboarding`) stand in for real Cognito session state. The authentication feature replaces these with `Amplify.Auth.fetchAuthSession()` calls.

---

## Architecture

### How It Works (App Launch Flow)

1. The system launches `EmberApp` (the `@main` struct in `ios/Ember/App/EmberApp.swift`).
2. `EmberApp` reads two `@AppStorage` keys: `isAuthenticated` and `hasCompletedOnboarding`.
3. Based on those values, the `WindowGroup` renders one of three branches:
   - Not authenticated: `LoginPlaceholderView`
   - Authenticated but not onboarded: `OnboardingPlaceholderView`
   - Authenticated and onboarded: `MainTabView`
4. All three branches receive `.environment(router)`, `.environment(container)`, and `.preferredColorScheme(.dark)`.
5. `AuthService.shared.configure()` is called in `EmberApp.init()` -- a no-op stub for now.

### Tab Navigation

`MainTabView` contains three tabs, each with its own `NavigationStack`:

| Tab index | Label | SF Symbol (default) | SF Symbol (selected) | Root View |
|-----------|-------|---------------------|----------------------|-----------|
| 0 | Home | `bubble.left.and.bubble.right` | `bubble.left.and.bubble.right.fill` | `HomePlaceholderView` |
| 1 | Memories | `brain` | `brain.fill` | `MemoriesPlaceholderView` |
| 2 | Profile | `person.circle` | `person.circle.fill` | `ProfilePlaceholderView` |

The tab bar tint is `Color.emberPrimary` (`#5B4FE8`) and the tab bar background uses `Color.emberSurface` (`#1A1A24`). Each `NavigationStack` registers `.navigationDestination(for: AppRouter.Route.self)` so that deep links pushed via `AppRouter` resolve correctly within each tab's stack.

### AppRouter

`AppRouter` (`ios/Ember/App/AppRouter.swift`) is an `@Observable final class` that wraps SwiftUI's `NavigationPath`. It defines the complete set of navigable routes for the app:

- `.characterDetail(characterId: String)`
- `.chat(characterId: String)`
- `.memoryList(characterId: String)`
- `.settings`

`push(_ route:)` appends to the path, `pop()` removes the last element (guarded against an empty path to prevent crashes), and `popToRoot()` sets the path to an empty `NavigationPath`. Feature ViewModels receive `AppRouter` via `@Environment` and call these methods to navigate.

### AppContainer

`AppContainer` (`ios/Ember/App/AppContainer.swift`) is an `@Observable final class` that holds the shared service singletons:

- `let apiClient: APIClientProtocol` -- defaults to `APIClient.shared`
- `let authService: AuthServiceProtocol` -- defaults to `AuthService.shared`

Feature ViewModels receive `AppContainer` via `@Environment` and call services through these protocol properties. This allows tests to inject mock implementations without modifying any view code.

### Design System Constants

The design system is implemented as Swift extensions rather than a framework or package. This means all constants are available everywhere in the app with no import statement, and the compiler can inline them.

**Colors** (`ios/Ember/Core/Extensions/Color+Ember.swift`): Static `let` properties on `Color`, constructed via a private `Color.init(hex:)` initializer. The hex initializer handles both 6-character and 8-character hex strings. The hex values in code are the primary source of truth; the Asset Catalog color sets exist for Interface Builder (LaunchScreen.storyboard) compatibility only.

**Typography** (`ios/Ember/Core/Extensions/Font+Ember.swift`): Static `let` properties on `Font` using `Font.system(size:weight:design:)` with `relativeTo:` parameters for Dynamic Type scaling. Inter (specified in `docs/14-tasarim.md`) is not yet bundled; system fonts with matching weights are used as a drop-in. When Inter is added, `Font+Ember.swift` is the single file to update.

**Spacing and corner radii** (`ios/Ember/Core/Extensions/CGFloat+Ember.swift`): Static `let` properties on `CGFloat`.

**SF Symbols** (`ios/Ember/Core/Extensions/EmberSymbol.swift`): A `case`-less enum with static string constants for every symbol used in the app. Using the enum instead of string literals prevents typos and makes symbol changes a single-file update.

---

## Project Structure

```
ios/
  project.yml                           # XcodeGen spec — regenerate with: xcodegen generate
  Ember.xcodeproj/                      # Generated Xcode project
  Ember/
    App/
      EmberApp.swift                    # @main, WindowGroup, auth routing
      MainTabView.swift                 # Three-tab TabView + NavigationStack per tab
      AppRouter.swift                   # @Observable router, NavigationPath, Route enum
      AppContainer.swift                # @Observable dependency container
    Features/
      Auth/
        LoginPlaceholderView.swift      # Dev-mode login (sets isAuthenticated)
        OnboardingPlaceholderView.swift # Dev-mode onboarding (sets hasCompletedOnboarding)
      Home/
        HomePlaceholderView.swift       # Home tab placeholder
      Memories/
        MemoriesPlaceholderView.swift   # Memories tab placeholder
      Profile/
        ProfilePlaceholderView.swift    # Profile tab placeholder
    Core/
      Network/
        APIClient.swift                 # APIClientProtocol + shared singleton stub
        APIError.swift                  # Error enum: httpError, decodingError, networkError
        JSONCoding.swift                # JSONEncoder.ember / JSONDecoder.ember
      Auth/
        AuthService.swift               # AuthServiceProtocol + stub (throws notImplemented)
        AuthError.swift                 # Error enum: signInFailed, tokenUnavailable, notImplemented
      Utils/
        HapticManager.swift             # Full haptic implementation (no-op on simulator)
      Extensions/
        Color+Ember.swift               # 18 color constants + hex initializer
        Font+Ember.swift                # 7 typography constants with Dynamic Type
        CGFloat+Ember.swift             # 8 spacing + 5 corner radius constants
        EmberSymbol.swift               # SF Symbol name constants
    Resources/
      LaunchScreen.storyboard           # Dark (#0F0F14) background, no white flash
      Assets.xcassets/                  # AppIcon, AccentColor, 10 named color sets
  EmberTests/
    App/
      AppRouterTests.swift              # 5 tests: push, pop, popToRoot, empty path safety
      AppContainerTests.swift           # 1 test: default init creates valid container
    Core/
      ColorTests.swift                  # 6 tests: color existence, hex initializer
```

---

## Design System Reference

### Colors

All constants are `Color.{name}` (e.g., `Color.emberPrimary`). Values come from `docs/14-tasarim.md`.

| Constant | Hex | Usage |
|----------|-----|-------|
| `emberPrimary` | `#5B4FE8` | Brand primary, buttons, user message bubbles, tab bar tint |
| `emberPrimaryPressed` | `#4B3FD8` | Pressed state of primary actions |
| `emberPrimaryHover` | `#6B5FF8` | Hover and highlight states |
| `emberAccent` | `#FF6B6B` | Proactive notifications, special events |
| `emberBackground` | `#0F0F14` | Main screen background |
| `emberSurface` | `#1A1A24` | Surface containers, tab bar background |
| `emberSurface2` | `#22223A` | Cards, input fields, AI message bubbles |
| `emberSurface3` | `#2C2C4A` | Hover and active states |
| `emberTextPrimary` | `#F0F0F8` | Primary body text |
| `emberTextSecondary` | `#9090B0` | Secondary text, timestamps |
| `emberTextDisabled` | `#5A5A7A` | Disabled buttons, placeholder text |
| `emberSuccess` | `#4CAF87` | Success states |
| `emberWarning` | `#F5A623` | Warning states |
| `emberError` | `#E85B5B` | Error states |
| `emberGradientStart` | `#5B4FE8` | Onboarding gradient start |
| `emberGradientEnd` | `#FF6B6B` | Onboarding gradient end |
| `emberAIBubbleStart` | `#1E1E35` | AI message bubble gradient start |
| `emberAIBubbleEnd` | `#252545` | AI message bubble gradient end |

Note: `docs/standards/ios.md` Section 10 lists different hex values (e.g., `#7C6AF7` for primary). Those values are superseded by `docs/14-tasarim.md`, which is the authoritative design document.

### Typography

All constants are `Font.{name}` (e.g., `Font.emberTitle`). All use `Font.system` with `relativeTo:` for Dynamic Type.

| Constant | Size | Weight | relativeTo |
|----------|------|--------|------------|
| `emberLargeTitle` | 28 | `.bold` | `.largeTitle` |
| `emberTitle` | 22 | `.semibold` | `.title2` |
| `emberHeadline` | 16 | `.semibold` | `.headline` |
| `emberBody` | 15 | `.regular` | `.body` |
| `emberSecondary` | 13 | `.regular` | `.subheadline` |
| `emberCaption` | 12 | `.medium` | `.caption` |
| `emberMicro` | 11 | `.regular` | `.caption2` |

### Spacing

All constants are `CGFloat.{name}` (e.g., `CGFloat.emberSpacing16`).

| Constant | Value | Typical usage |
|----------|-------|---------------|
| `emberSpacing4` | 4 | Icon-to-text gap |
| `emberSpacing8` | 8 | Chip padding, small gaps |
| `emberSpacing12` | 12 | List item vertical padding |
| `emberSpacing16` | 16 | Card padding, standard screen padding |
| `emberSpacing20` | 20 | Screen horizontal margin |
| `emberSpacing24` | 24 | Section gap |
| `emberSpacing32` | 32 | Large section divider |
| `emberSpacing48` | 48 | Screen top padding after safe area |

### Corner Radii

| Constant | Value | Typical usage |
|----------|-------|---------------|
| `emberRadius4` | 4 | Small chips, badges |
| `emberRadius12` | 12 | Input fields, small cards |
| `emberRadius16` | 16 | Message bubbles |
| `emberRadius20` | 20 | Main cards, modals |
| `emberRadius28` | 28 | CTA buttons (pill shape) |

---

## Dependencies (Swift Package Manager)

Declared in `project.yml` and resolved into `Ember.xcodeproj`. All packages use "Up to Next Major Version".

| Package | Version | Purpose |
|---------|---------|---------|
| Kingfisher (`onevcat/Kingfisher`) | 8.x | Network image loading and caching |
| Lottie iOS (`airbnb/lottie-ios`) | 4.x | Animations for onboarding and empty states |
| swift-markdown-ui (`gonzalezreal/swift-markdown-ui`) | 2.x | Markdown rendering in AI responses |

AWS Amplify Swift (`aws-amplify/amplify-swift`) was intentionally excluded from this scaffold. Adding Amplify requires `amplifyconfiguration.json`, which does not exist until the authentication feature is implemented. Amplify will be added in the auth feature PR to avoid build failures. Firebase iOS SDK is similarly deferred until push notification implementation.

---

## Testing

### Coverage Summary

| File | Tests | What Is Covered |
|------|-------|-----------------|
| `EmberTests/App/AppRouterTests.swift` | 5 | `push`, `pop`, `popToRoot`, pop on empty path (no crash) |
| `EmberTests/App/AppContainerTests.swift` | 1 | Default init creates non-nil `apiClient` and `authService` |
| `EmberTests/Core/ColorTests.swift` | 6 | Each design system color initializes without crash, hex initializer, invalid hex fallback |

Tests use Swift Testing (`import Testing`), not XCTest. The test target is `EmberTests`.

### Running Tests

```bash
cd ios
xcodebuild test -scheme Ember -destination "platform=iOS Simulator,name=iPhone 16"
```

To regenerate the Xcode project before testing (if `project.yml` was modified):

```bash
cd ios
xcodegen generate
```

### Resetting Dev State for Manual Testing

The auth routing relies on two `UserDefaults` keys. To reset to the login screen:

```bash
# On simulator, delete the app and reinstall, or clear defaults programmatically:
# UserDefaults.standard.removeObject(forKey: "isAuthenticated")
# UserDefaults.standard.removeObject(forKey: "hasCompletedOnboarding")
```

---

## Known Limitations

- **No real authentication**: `AuthService` throws `AuthError.notImplemented` for all methods. Real Cognito integration is implemented in the auth feature.
- **No network layer**: `APIClientProtocol` has no methods. Endpoint methods are added by each feature PR as it lands.
- **No SSEClient**: `SSEClient` is not created in this scaffold. It arrives with the first streaming feature (chat). Only the error type infrastructure (`APIError`) is in place.
- **System fonts, not Inter**: Inter is specified in the design system but font files are not bundled. `Font+Ember.swift` uses system fonts with matching weights. When Inter is added, `Font+Ember.swift` is the single update point.
- **Amplify SDK missing**: AWS Amplify Swift is not in SPM dependencies. It will be added when `amplifyconfiguration.json` is available in the auth feature.
- **No Localizable.xcstrings**: Localization infrastructure is deferred until the first user-facing string feature.
- **No UI tests**: UI tests will be added with the first interactive feature.

### Implementation Deviation from Spec

The spec listed AWS Amplify Swift as an SPM dependency to declare in this scaffold. The ios-dev agent omitted it because Amplify requires `amplifyconfiguration.json` configuration files that do not yet exist. Adding the package without these files causes build failures. This is a correct deviation.

---

## Extending This Feature

### Adding a new tab

1. Add a case to the `Tab` enum in `MainTabView.swift`.
2. Add the corresponding `TabView` item with a label and `NavigationStack`.
3. Create the placeholder or real view in `ios/Ember/Features/{TabName}/`.

### Adding a new navigation route

1. Add a case to `AppRouter.Route` in `AppRouter.swift`. The case must be `Hashable`.
2. Register a `.navigationDestination(for:)` in the `NavigationStack` of the relevant tab in `MainTabView.swift`.
3. Inject `@Environment(AppRouter.self)` into the ViewModel that needs to trigger navigation, and call `router.push(.yourRoute(...))`.

### Adding methods to APIClient

Feature PRs extend `APIClientProtocol` with new method requirements and add the corresponding implementation to `APIClient`. They also add mock implementations for tests. This keeps the protocol minimal until each feature actually needs it.

### Replacing @AppStorage auth state with real Cognito

When the auth feature lands, the two `@AppStorage` properties in `EmberApp` are removed. The `WindowGroup` body is replaced with an `async` check via `Amplify.Auth.fetchAuthSession()`. The `isAuthenticated` and `hasCompletedOnboarding` booleans become transient `@State` driven by the Cognito session result.

---

## Related Documentation

- [Mobile Screens and Navigation](../07-mobil.md)
- [Design System](../14-tasarim.md)
- [iOS Standards](../standards/ios.md)
- [System Architecture](../03-mimari.md)
