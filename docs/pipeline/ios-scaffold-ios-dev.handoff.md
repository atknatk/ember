# iOS Dev Handoff: iOS Scaffold

**Date**: 2026-03-13
**Agent**: ios-dev
**Status**: COMPLETE

## Implemented Files

### App Entry Point
- `ios/Ember/App/EmberApp.swift` -- @main entry point with @AppStorage auth/onboarding state routing
- `ios/Ember/App/MainTabView.swift` -- Three-tab TabView (Home, Memories, Profile) with NavigationStack
- `ios/Ember/App/AppRouter.swift` -- @Observable router with NavigationPath and Route enum
- `ios/Ember/App/AppContainer.swift` -- @Observable dependency container (APIClient + AuthService)

### Feature Placeholders
- `ios/Ember/Features/Home/HomePlaceholderView.swift` -- Home tab placeholder
- `ios/Ember/Features/Memories/MemoriesPlaceholderView.swift` -- Memories tab placeholder
- `ios/Ember/Features/Profile/ProfilePlaceholderView.swift` -- Profile tab placeholder
- `ios/Ember/Features/Auth/LoginPlaceholderView.swift` -- Login placeholder with dev Sign In button
- `ios/Ember/Features/Auth/OnboardingPlaceholderView.swift` -- Onboarding placeholder with dev Complete button

### Core -- Network
- `ios/Ember/Core/Network/APIClient.swift` -- Protocol stub + shared singleton
- `ios/Ember/Core/Network/APIError.swift` -- Error enum (httpError, decodingError, networkError)
- `ios/Ember/Core/Network/JSONCoding.swift` -- JSONEncoder.ember / JSONDecoder.ember extensions

### Core -- Auth
- `ios/Ember/Core/Auth/AuthService.swift` -- Protocol + stub implementation (throws notImplemented)
- `ios/Ember/Core/Auth/AuthError.swift` -- Auth error enum

### Core -- Utils
- `ios/Ember/Core/Utils/HapticManager.swift` -- Full implementation with impact/notification/selection

### Core -- Extensions (Design System)
- `ios/Ember/Core/Extensions/Color+Ember.swift` -- All 18 color constants from docs/14-tasarim.md + hex initializer
- `ios/Ember/Core/Extensions/Font+Ember.swift` -- 7 typography constants with system fonts
- `ios/Ember/Core/Extensions/CGFloat+Ember.swift` -- 8 spacing + 5 corner radius constants
- `ios/Ember/Core/Extensions/EmberSymbol.swift` -- SF Symbol name constants

### Resources
- `ios/Ember/Resources/LaunchScreen.storyboard` -- Dark background (#0F0F14) with centered "Ember" text
- `ios/Ember/Resources/Assets.xcassets/` -- 10 color sets (dark appearance only) + AccentColor + AppIcon

### Tests
- `ios/EmberTests/App/AppRouterTests.swift` -- 5 tests (push, pop, popToRoot, empty path safety)
- `ios/EmberTests/Core/ColorTests.swift` -- 6 tests (color existence, hex initializer, all colors defined)
- `ios/EmberTests/App/AppContainerTests.swift` -- 1 test (default init creates valid container)

### Project
- `ios/project.yml` -- XcodeGen spec for project generation
- `ios/Ember.xcodeproj/` -- Generated Xcode project

## Screens Implemented
- LoginPlaceholderView: minimal login screen with dev "Sign In" button (sets @AppStorage)
- OnboardingPlaceholderView: minimal onboarding with dev "Complete" button (sets @AppStorage)
- MainTabView: three-tab layout (Home, Memories, Profile) with NavigationStack per tab
- HomePlaceholderView: centered icon + "Home" label
- MemoriesPlaceholderView: centered icon + "Memories" label
- ProfilePlaceholderView: centered icon + "Profile" label

## Deviations from Spec
- AWS Amplify Swift SPM dependency was omitted because the AuthService is fully stubbed and Amplify requires additional configuration files (amplifyconfiguration.json) that do not exist yet. Adding the package without proper config would cause build failures. It will be added when the auth feature is implemented.
- Color set values in Assets.xcassets use approximated float values (3 decimal places) for the sRGB components converted from hex.

## Notes for iOS Tester
- All ViewModels use `@Observable` (iOS 17+), never `ObservableObject`
- `AppRouter` guards against empty path on `pop()` and `popToRoot()` -- test that no crash occurs
- `LoginPlaceholderView` and `OnboardingPlaceholderView` use `@AppStorage` booleans for dev testing flow
- To reset app state for testing, delete UserDefaults keys `isAuthenticated` and `hasCompletedOnboarding`
- `AuthService` methods throw `AuthError.notImplemented` -- this is expected for the scaffold
- `APIClientProtocol` has no methods yet -- methods will be added by feature PRs
- Test target uses Swift Testing (`import Testing`) as the primary framework
- `HapticManager` is a no-op on simulator but functional on device
- The project uses XcodeGen (`project.yml`) -- run `xcodegen generate` in the `ios/` directory to regenerate the `.xcodeproj` if needed
