# Feature Spec: P03-01 -- iOS Scaffold

**Feature ID**: P03-01
**Phase**: 3
**Layer**: ios
**GitHub Issue**: #17
**Date**: 2026-03-13
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature establishes the foundational Xcode project for the Ember iOS app. It creates the SwiftUI app entry point (`EmberApp`), a three-tab `TabView` (Home, Memories, Profile), the `AppRouter` with `NavigationStack`, the design system constants (colors, typography, spacing from `docs/14-tasarim.md`), the dependency container (`AppContainer`), SPM package dependencies, dark mode enforcement, the `LaunchScreen.storyboard`, and all scaffolding directories and placeholder files that subsequent iOS features will build upon.

### Why It Exists

Every subsequent iOS feature (auth screens, character list, chat, memory display, voice) depends on this scaffold. Without it, there is no app target to add views to, no navigation system to push screens onto, no design system constants to reference, and no dependency container for service injection. This is the prerequisite for all iOS Phase 3 work.

### Dependencies

- **P01-07** (messages-pagination) -- the backend must be operational for future iOS features, but this scaffold does not call any backend endpoints. The dependency is logical (the API exists), not technical (no network calls in this feature).

### What This Feature Does NOT Do

- It does not implement authentication screens or Cognito integration. Auth UI is a separate feature.
- It does not implement character list, chat, or memory screens. Those are separate features that will fill in the placeholder views created here.
- It does not make any network calls. The `APIClient`, `SSEClient`, and `AuthService` are created as empty protocol stubs.
- It does not include any backend changes.

---

## 2. Data Models

No database changes. This is an iOS-only scaffold feature.

---

## 3. API Endpoints

No new API endpoints. This feature creates the iOS network layer stubs that will call existing backend endpoints in subsequent features.

---

## 4. Backend Logic

Not applicable. This is an iOS-only feature.

---

## 5. iOS Screens and Components

### 5.1 EmberApp (App Entry Point)

**File**: `ios/Ember/App/EmberApp.swift`

The `@main` struct for the application.

- Creates `@State private var router = AppRouter()`
- Creates `@State private var container = AppContainer()`
- Uses `@AppStorage("isAuthenticated")` to track auth state (defaults to `false`)
- Uses `@AppStorage("hasCompletedOnboarding")` to track onboarding state (defaults to `false`)
- WindowGroup body:
  - If not authenticated: shows `LoginPlaceholderView`
  - If authenticated but not onboarded: shows `OnboardingPlaceholderView`
  - If authenticated and onboarded: shows `MainTabView`
- All branches wrapped with `.environment(router)`, `.environment(container)`, `.preferredColorScheme(.dark)`
- Calls `AuthService.shared.configure()` in `init()` (stub, no-op for now)

### 5.2 MainTabView

**File**: `ios/Ember/App/MainTabView.swift`

A `TabView` with three tabs. Each tab wraps its content in a `NavigationStack`.

| Tab | Label | SF Symbol (normal) | SF Symbol (selected) | Root View |
|-----|-------|--------------------|---------------------|-----------|
| Home | Home | `bubble.left.and.bubble.right` | `bubble.left.and.bubble.right.fill` | `HomePlaceholderView` |
| Memories | Memories | `brain` | `brain.fill` | `MemoriesPlaceholderView` |
| Profile | Profile | `person.circle` | `person.circle.fill` | `ProfilePlaceholderView` |

- `@State private var selectedTab: Tab = .home`
- Tab enum defined locally: `.home`, `.memories`, `.profile`
- Tab bar tint color: `Color.emberPrimary`
- Tab bar background: `Color.emberSurface`
- Each tab root view has `.navigationDestination(for: AppRouter.Route.self)` registered

### 5.3 AppRouter

**File**: `ios/Ember/App/AppRouter.swift`

As defined in `docs/standards/ios.md` Section 3.

- `@Observable final class AppRouter`
- `var path = NavigationPath()`
- `enum Route: Hashable` with cases:
  - `.characterDetail(characterId: String)`
  - `.chat(characterId: String)`
  - `.memoryList(characterId: String)`
  - `.settings`
- Methods: `push(_ route:)`, `pop()`, `popToRoot()`

### 5.4 AppContainer

**File**: `ios/Ember/App/AppContainer.swift`

As defined in `docs/standards/ios.md` Section 15 (Dependency Container).

- `@Observable final class AppContainer`
- Properties:
  - `let apiClient: APIClientProtocol`
  - `let authService: AuthServiceProtocol`
- Default init uses `APIClient.shared` and `AuthService.shared`

### 5.5 Placeholder Views

These are minimal placeholder views that will be replaced by real implementations in subsequent features. Each shows a centered text label and uses the design system colors.

| View | File | Content |
|------|------|---------|
| `HomePlaceholderView` | `ios/Ember/Features/Home/HomePlaceholderView.swift` | "Home" text + `house.fill` icon, `emberBackground` |
| `MemoriesPlaceholderView` | `ios/Ember/Features/Memories/MemoriesPlaceholderView.swift` | "Memories" text + `brain` icon, `emberBackground` |
| `ProfilePlaceholderView` | `ios/Ember/Features/Profile/ProfilePlaceholderView.swift` | "Profile" text + `person.circle` icon, `emberBackground` |
| `LoginPlaceholderView` | `ios/Ember/Features/Auth/LoginPlaceholderView.swift` | "Login" text + "Sign In" button that sets `isAuthenticated = true` (for dev testing) |
| `OnboardingPlaceholderView` | `ios/Ember/Features/Auth/OnboardingPlaceholderView.swift` | "Onboarding" text + "Complete" button that sets `hasCompletedOnboarding = true` (for dev testing) |

Each placeholder:
- Background: `Color.emberBackground.ignoresSafeArea()`
- Text color: `Color.emberTextPrimary`
- Font: `.emberTitle` for the label
- Has `.accessibilityLabel` on all interactive elements

### 5.6 Design System

#### Colors

**File**: `ios/Ember/Core/Extensions/Color+Ember.swift`

All colors defined as `static let` on `Color` extension, using hex initializer:

| Constant | Hex | Usage |
|----------|-----|-------|
| `emberPrimary` | `#5B4FE8` | Primary brand, buttons, user message bubbles |
| `emberPrimaryPressed` | `#4B3FD8` | Pressed state of primary |
| `emberPrimaryHover` | `#6B5FF8` | Hover/highlight state |
| `emberAccent` | `#FF6B6B` | Proactive notifications, special events |
| `emberBackground` | `#0F0F14` | Main background |
| `emberSurface` | `#1A1A24` | Surface-level containers, tab bar |
| `emberSurface2` | `#22223A` | Cards, input fields, AI message bubbles |
| `emberSurface3` | `#2C2C4A` | Hover, active states |
| `emberTextPrimary` | `#F0F0F8` | Primary text |
| `emberTextSecondary` | `#9090B0` | Secondary text, timestamps |
| `emberTextDisabled` | `#5A5A7A` | Disabled buttons, placeholders |
| `emberSuccess` | `#4CAF87` | Success states |
| `emberWarning` | `#F5A623` | Warning states |
| `emberError` | `#E85B5B` | Error states |
| `emberGradientStart` | `#5B4FE8` | Onboarding gradient start |
| `emberGradientEnd` | `#FF6B6B` | Onboarding gradient end |
| `emberAIBubbleStart` | `#1E1E35` | AI message bubble gradient start |
| `emberAIBubbleEnd` | `#252545` | AI message bubble gradient end |

A private `Color.init(hex:)` initializer must be defined in the same file to construct colors from hex strings.

Colors are also declared in `Assets.xcassets` as named color sets (dark appearance only) so that they can be referenced by name in Interface Builder if needed. The code-level hex initializer is the primary source of truth.

#### Typography

**File**: `ios/Ember/Core/Extensions/Font+Ember.swift`

The design system specifies Inter as the font. For the scaffold, use system fonts with matching weights and sizes that respect Dynamic Type. Inter will be bundled in a future feature when custom font files are added.

| Constant | Style | Size | Weight | relativeTo |
|----------|-------|------|--------|------------|
| `emberLargeTitle` | Display | 28 | `.bold` | `.largeTitle` |
| `emberTitle` | Title | 22 | `.semibold` | `.title2` |
| `emberHeadline` | Section heading | 16 | `.semibold` | `.headline` |
| `emberBody` | Message text | 15 | `.regular` | `.body` |
| `emberSecondary` | Secondary text | 13 | `.regular` | `.subheadline` |
| `emberCaption` | Labels, chips | 12 | `.medium` | `.caption` |
| `emberMicro` | Timestamps | 11 | `.regular` | `.caption2` |

All fonts use `Font.system(size:weight:design:)` with `relativeTo:` to support Dynamic Type scaling.

#### Spacing

**File**: `ios/Ember/Core/Extensions/CGFloat+Ember.swift`

| Constant | Value | Usage |
|----------|-------|-------|
| `emberSpacing4` | 4 | Icon-text gap, small padding |
| `emberSpacing8` | 8 | Chip padding, small gap |
| `emberSpacing12` | 12 | List item vertical padding |
| `emberSpacing16` | 16 | Card padding, standard padding |
| `emberSpacing20` | 20 | Screen horizontal margin |
| `emberSpacing24` | 24 | Section gap |
| `emberSpacing32` | 32 | Large section divider |
| `emberSpacing48` | 48 | Screen top padding after safe area |

Defined as `static let` on `CGFloat` extension.

#### Corner Radii

**File**: `ios/Ember/Core/Extensions/CGFloat+Ember.swift` (same file as spacing)

| Constant | Value | Usage |
|----------|-------|-------|
| `emberRadius4` | 4 | Small chip, badge |
| `emberRadius12` | 12 | Input fields, small cards |
| `emberRadius16` | 16 | Message bubbles |
| `emberRadius20` | 20 | Main cards, modals |
| `emberRadius28` | 28 | CTA buttons (pill) |

#### SF Symbols

**File**: `ios/Ember/Core/Extensions/EmberSymbol.swift`

As defined in `docs/standards/ios.md` Section 8:

```
enum EmberSymbol {
    static let send       = "arrow.up.circle.fill"
    static let microphone = "mic.fill"
    static let memory     = "brain.head.profile"
    static let character  = "person.crop.circle"
    static let settings   = "gearshape.fill"
    static let back       = "chevron.left"
    static let home       = "bubble.left.and.bubble.right"
    static let homeFill   = "bubble.left.and.bubble.right.fill"
    static let memoryTab  = "brain"
    static let memoryTabFill = "brain.fill"
    static let profile    = "person.circle"
    static let profileFill = "person.circle.fill"
}
```

### 5.7 Core Stubs

These files are created with protocol definitions and minimal implementations. They will be fleshed out in subsequent features.

#### APIClient Stub

**File**: `ios/Ember/Core/Network/APIClient.swift`

- `APIClientProtocol` protocol with no methods (methods added by feature PRs)
- `APIClient` class conforming to protocol, with `static let shared`
- `baseURL` from `ProcessInfo.processInfo.environment["API_BASE_URL"]` or default `"https://api.ember.ai"`

**File**: `ios/Ember/Core/Network/APIError.swift`

- `APIError` enum with cases: `.httpError(statusCode: Int)`, `.decodingError(Error)`, `.networkError(Error)`
- Conforms to `LocalizedError`

#### AuthService Stub

**File**: `ios/Ember/Core/Auth/AuthService.swift`

- `AuthServiceProtocol` with methods: `configure()`, `signIn(username:password:) async throws`, `signOut() async`, `getAccessToken() async throws -> String`
- `AuthService` class with `static let shared`, all methods stubbed (no-op or throw "not implemented")

**File**: `ios/Ember/Core/Auth/AuthError.swift`

- `AuthError` enum: `.signInFailed(String)`, `.tokenUnavailable`, `.notImplemented`
- Conforms to `LocalizedError`

#### HapticManager

**File**: `ios/Ember/Core/Utils/HapticManager.swift`

As defined in `docs/standards/ios.md` Section 12. Full implementation (not a stub) since it has no dependencies.

#### JSON Coding

**File**: `ios/Ember/Core/Network/JSONCoding.swift`

`JSONEncoder.ember` and `JSONDecoder.ember` extensions as defined in `docs/standards/ios.md` Section 4. Full implementation.

### 5.8 LaunchScreen

**File**: `ios/Ember/Resources/LaunchScreen.storyboard`

- Background color: `#0F0F14` (emberBackground)
- Centered app name "Ember" in white text, or a placeholder logo image
- No animation (static storyboard, prevents white flash on launch)

### 5.9 Asset Catalog

**File**: `ios/Ember/Resources/Assets.xcassets`

Structure:
- `Contents.json` (root)
- `AccentColor.colorset/` -- set to `#5B4FE8`
- `AppIcon.appiconset/` -- placeholder (empty with `Contents.json`)
- Color sets for each ember color (dark appearance only):
  - `EmberPrimary.colorset/`
  - `EmberAccent.colorset/`
  - `EmberBackground.colorset/`
  - `EmberSurface.colorset/`
  - `EmberSurface2.colorset/`
  - `EmberTextPrimary.colorset/`
  - `EmberTextSecondary.colorset/`
  - `EmberSuccess.colorset/`
  - `EmberWarning.colorset/`
  - `EmberError.colorset/`

---

## 6. Android Screens and Components

Not applicable. This is an iOS-only feature.

---

## 7. Dependencies (Swift Package Manager)

The following packages are declared in the Xcode project's Package Dependencies (or a `Package.swift` if using a local package):

| Package | URL | Version | Purpose |
|---------|-----|---------|---------|
| AWS Amplify for Swift | `https://github.com/aws-amplify/amplify-swift` | 2.x | Cognito authentication |
| Kingfisher | `https://github.com/onevcat/Kingfisher` | 8.x | Network image loading + caching |
| Lottie for iOS | `https://github.com/airbnb/lottie-ios` | 4.x | Animations (onboarding, empty states) |
| swift-markdown-ui | `https://github.com/gonzalezreal/swift-markdown-ui` | 2.x | Markdown rendering in AI responses |

Notes:
- All packages use "Up to Next Major Version" resolution.
- The packages are declared in this scaffold but their code is not called until subsequent features import them.
- Firebase iOS SDK is NOT added in this scaffold. It will be added when push notifications are implemented.

---

## 8. Test Plan

### Unit Tests

Since this is a scaffold feature, tests verify the structural setup works correctly.

#### AppRouter Tests

**File**: `ios/EmberTests/App/AppRouterTests.swift`

| # | Scenario | Expected |
|---|----------|----------|
| 1 | Push a route | `path.count` increases by 1 |
| 2 | Pop after push | `path.count` decreases by 1 |
| 3 | Pop to root after multiple pushes | `path.count` becomes 0 |
| 4 | Pop on empty path | No crash (guard against count == 0) |

#### Color Tests

**File**: `ios/EmberTests/Core/ColorTests.swift`

| # | Scenario | Expected |
|---|----------|----------|
| 1 | `Color.emberPrimary` is not nil | Color is initialized successfully |
| 2 | `Color.emberBackground` is not nil | Color is initialized successfully |
| 3 | Hex initializer with `#5B4FE8` | Produces a valid color |
| 4 | Hex initializer with invalid string | Falls back gracefully (clear or black) |

#### AppContainer Tests

**File**: `ios/EmberTests/App/AppContainerTests.swift`

| # | Scenario | Expected |
|---|----------|----------|
| 1 | Default init creates container | `apiClient` and `authService` are non-nil |

### UI Tests (minimal)

No UI tests for this scaffold. UI tests will be added with the first interactive feature.

---

## 9. Acceptance Criteria

1. Given a developer opens the Xcode project, when they build and run on an iOS 17+ simulator, then the app launches without crashes and shows the login placeholder screen.

2. Given the app is running on the login placeholder, when the developer taps the dev "Sign In" button, then the app transitions to the onboarding placeholder screen.

3. Given the app is showing the onboarding placeholder, when the developer taps the "Complete" button, then the app transitions to the main tab view with three tabs.

4. Given the main tab view is showing, when the developer taps each tab (Home, Memories, Profile), then the corresponding placeholder view is displayed with the correct icon and label.

5. Given the main tab view is showing, then the tab bar uses `emberPrimary` as the tint color for the selected tab.

6. Given the app is running, then dark mode is enforced globally via `.preferredColorScheme(.dark)` -- the app never shows in light mode.

7. Given the `Color+Ember.swift` file, when a developer inspects it, then all 14+ color constants are defined with the exact hex values from `docs/14-tasarim.md`.

8. Given the `Font+Ember.swift` file, when a developer inspects it, then all 7 typography constants are defined with `relativeTo:` parameters for Dynamic Type support.

9. Given the `CGFloat+Ember.swift` file, when a developer inspects it, then all spacing (8 values) and corner radius (5 values) constants are defined matching `docs/14-tasarim.md`.

10. Given the Xcode project, when a developer inspects Package Dependencies, then Amplify Swift, Kingfisher, Lottie iOS, and swift-markdown-ui are listed.

11. Given the `LaunchScreen.storyboard`, when the app launches, then the launch screen shows with `#0F0F14` background (no white flash).

12. Given the project directory structure, when a developer inspects `ios/Ember/`, then all directories exist: `App/`, `Features/Home/`, `Features/Memories/`, `Features/Profile/`, `Features/Auth/`, `Core/Network/`, `Core/Auth/`, `Core/Utils/`, `Core/Extensions/`, `Resources/`.

13. Given the test target, when a developer runs all unit tests, then all tests pass with zero failures.

14. Given the `AppRouter`, when `push`, `pop`, and `popToRoot` are called, then the `NavigationPath` count changes correctly.

15. Given the `HapticManager`, when its static methods are called, then no crashes occur (functional on device, no-op on simulator).

16. Given the `Assets.xcassets`, when a developer inspects it, then color sets exist for all primary design system colors with dark appearance only.

17. Given the project builds, when a developer runs SwiftLint (if configured), then zero errors are reported.

---

## 10. File Manifest

Every file to be created, grouped by purpose.

### App Entry Point

```
iOS:
  CREATE  ios/Ember/App/EmberApp.swift
  CREATE  ios/Ember/App/MainTabView.swift
  CREATE  ios/Ember/App/AppRouter.swift
  CREATE  ios/Ember/App/AppContainer.swift
```

### Feature Placeholders

```
iOS:
  CREATE  ios/Ember/Features/Home/HomePlaceholderView.swift
  CREATE  ios/Ember/Features/Memories/MemoriesPlaceholderView.swift
  CREATE  ios/Ember/Features/Profile/ProfilePlaceholderView.swift
  CREATE  ios/Ember/Features/Auth/LoginPlaceholderView.swift
  CREATE  ios/Ember/Features/Auth/OnboardingPlaceholderView.swift
```

### Core -- Network

```
iOS:
  CREATE  ios/Ember/Core/Network/APIClient.swift
  CREATE  ios/Ember/Core/Network/APIError.swift
  CREATE  ios/Ember/Core/Network/JSONCoding.swift
```

### Core -- Auth

```
iOS:
  CREATE  ios/Ember/Core/Auth/AuthService.swift
  CREATE  ios/Ember/Core/Auth/AuthError.swift
```

### Core -- Utils

```
iOS:
  CREATE  ios/Ember/Core/Utils/HapticManager.swift
```

### Core -- Extensions (Design System)

```
iOS:
  CREATE  ios/Ember/Core/Extensions/Color+Ember.swift
  CREATE  ios/Ember/Core/Extensions/Font+Ember.swift
  CREATE  ios/Ember/Core/Extensions/CGFloat+Ember.swift
  CREATE  ios/Ember/Core/Extensions/EmberSymbol.swift
```

### Resources

```
iOS:
  CREATE  ios/Ember/Resources/LaunchScreen.storyboard
  CREATE  ios/Ember/Resources/Assets.xcassets/Contents.json
  CREATE  ios/Ember/Resources/Assets.xcassets/AccentColor.colorset/Contents.json
  CREATE  ios/Ember/Resources/Assets.xcassets/AppIcon.appiconset/Contents.json
  CREATE  ios/Ember/Resources/Assets.xcassets/EmberPrimary.colorset/Contents.json
  CREATE  ios/Ember/Resources/Assets.xcassets/EmberAccent.colorset/Contents.json
  CREATE  ios/Ember/Resources/Assets.xcassets/EmberBackground.colorset/Contents.json
  CREATE  ios/Ember/Resources/Assets.xcassets/EmberSurface.colorset/Contents.json
  CREATE  ios/Ember/Resources/Assets.xcassets/EmberSurface2.colorset/Contents.json
  CREATE  ios/Ember/Resources/Assets.xcassets/EmberTextPrimary.colorset/Contents.json
  CREATE  ios/Ember/Resources/Assets.xcassets/EmberTextSecondary.colorset/Contents.json
  CREATE  ios/Ember/Resources/Assets.xcassets/EmberSuccess.colorset/Contents.json
  CREATE  ios/Ember/Resources/Assets.xcassets/EmberWarning.colorset/Contents.json
  CREATE  ios/Ember/Resources/Assets.xcassets/EmberError.colorset/Contents.json
```

### Xcode Project

```
iOS:
  CREATE  ios/Ember.xcodeproj/  (Xcode project bundle -- created via Xcode or xcodegen)
  CREATE  ios/Ember/Info.plist   (if not embedded in project settings)
```

### Tests

```
iOS:
  CREATE  ios/EmberTests/App/AppRouterTests.swift
  CREATE  ios/EmberTests/Core/ColorTests.swift
  CREATE  ios/EmberTests/App/AppContainerTests.swift
```

### Pipeline

```
Shared:
  CREATE  shared/feature-specs/ios-scaffold.md         (this file)
  CREATE  docs/pipeline/ios-scaffold-architect.handoff.md
```

### Summary

| Action | Count |
|--------|-------|
| CREATE | ~40 (including xcassets color sets) |
| MODIFY | 0 |
| DELETE | 1 (ios/.gitkeep -- replaced by real content) |

---

## 11. Design Decisions and Rationale

### Why placeholder views instead of empty directories

Empty directories are not tracked by git. Placeholder views serve double duty: they prove the navigation and tab system works end-to-end, and they provide a visible confirmation that the scaffold is functional. Each placeholder will be replaced by the real view in its feature PR.

### Why system fonts instead of bundled Inter

The Inter font files are not yet available in the project. Using `Font.system(size:weight:design:)` with `relativeTo:` provides the correct sizing, weight mapping, and Dynamic Type support. When Inter is bundled (a future feature), the `Font+Ember.swift` constants are the single place to update.

### Why hex initializer instead of Asset Catalog only

The hex initializer provides compile-time constants that autocomplete in code. Asset Catalog color sets are also created for Interface Builder compatibility (LaunchScreen.storyboard). The hex values in code are the source of truth; the Asset Catalog values must match.

### Why `@AppStorage` for auth state in the scaffold

`@AppStorage` provides a simple, persistent boolean for the scaffold phase. In the real auth feature, this will be replaced by Cognito session state checking via `Amplify.Auth.fetchAuthSession()`. The `@AppStorage` approach lets developers test the tab navigation flow without a backend.

### Why Firebase SDK is not added yet

Firebase iOS SDK adds significant build time and binary size. It should only be added when FCM push notifications are implemented. The SPM dependency list in this scaffold includes only packages that will be used in the immediate next features (auth, character list, chat).

### Why no SSEClient or full APIClient in this scaffold

The `docs/standards/ios.md` defines detailed implementations for `SSEClient` and `APIClient`. These are complex and tightly coupled to specific API endpoints. Including them as stubs risks them going stale. Instead, only the protocol and error types are created. The full implementations will be added when the first networking feature (auth or character list) is built.

---

## 12. Notes for Developers

### For ios-dev

- The project structure follows `docs/standards/ios.md` Section 1 exactly. The directory names use `Features/` (not `Feature/`) to match the standard.
- Create the Xcode project using Xcode's "New Project" wizard (App template, SwiftUI lifecycle, Swift language). Then restructure the generated files into the directory layout specified here.
- Add SPM dependencies via Xcode's Project Settings > Package Dependencies. Use "Up to Next Major Version" for all packages.
- The `Color.init(hex:)` initializer should handle both 6-character (`#5B4FE8`) and 8-character (`#FF5B4FE8`) hex strings.
- All color hex values come from `docs/14-tasarim.md`. Do NOT use the values from `docs/standards/ios.md` Section 10 -- those are different (e.g., `#7C6AF7` vs `#5B4FE8`). The design system doc (`docs/14-tasarim.md`) is authoritative.
- `LaunchScreen.storyboard` is required (not a SwiftUI launch screen) because it prevents the white flash on cold start.
- The `AppRouter.pop()` method must guard against `path.count == 0` to avoid a runtime crash.
- Do NOT add `Localizable.xcstrings` in this scaffold. Localization files will be added when the first user-facing strings feature is implemented.
- The test target should be named `EmberTests` and use Swift Testing (`import Testing`) as the primary framework, per `docs/standards/ios.md` Section 14.

### Discrepancy: docs/standards/ios.md vs docs/14-tasarim.md colors

The iOS standards doc (`docs/standards/ios.md` Section 10) lists colors like `#7C6AF7` for primary and `#E85D9A` for accent. The design system doc (`docs/14-tasarim.md`) lists `#5B4FE8` for primary and `#FF6B6B` for accent. **`docs/14-tasarim.md` takes precedence** as it is the authoritative design system document referenced by the issue description.
