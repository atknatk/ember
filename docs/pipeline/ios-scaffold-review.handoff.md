# Reviewer Handoff: iOS Scaffold

**Date**: 2026-03-13
**Agent**: reviewer
**Status**: APPROVED

## Review Summary

| Category | Passed | Warnings | Issues |
|----------|--------|----------|--------|
| Architecture | 5 | 0 | 0 |
| iOS Code Quality | 7 | 3 | 0 |
| Testing | 4 | 0 | 0 |
| Security | 4 | 0 | 0 |
| **Total** | **20** | **3** | **0** |

## Files Reviewed

**App Entry Point**:
- `ios/Ember/App/EmberApp.swift` -- PASS
- `ios/Ember/App/MainTabView.swift` -- PASS (1 warning)
- `ios/Ember/App/AppRouter.swift` -- PASS
- `ios/Ember/App/AppContainer.swift` -- PASS

**Feature Placeholders**:
- `ios/Ember/Features/Home/HomePlaceholderView.swift` -- PASS (1 warning)
- `ios/Ember/Features/Memories/MemoriesPlaceholderView.swift` -- PASS
- `ios/Ember/Features/Profile/ProfilePlaceholderView.swift` -- PASS
- `ios/Ember/Features/Auth/LoginPlaceholderView.swift` -- PASS
- `ios/Ember/Features/Auth/OnboardingPlaceholderView.swift` -- PASS

**Core -- Network**:
- `ios/Ember/Core/Network/APIClient.swift` -- PASS (1 warning)
- `ios/Ember/Core/Network/APIError.swift` -- PASS
- `ios/Ember/Core/Network/JSONCoding.swift` -- PASS

**Core -- Auth**:
- `ios/Ember/Core/Auth/AuthService.swift` -- PASS
- `ios/Ember/Core/Auth/AuthError.swift` -- PASS

**Core -- Utils**:
- `ios/Ember/Core/Utils/HapticManager.swift` -- PASS

**Core -- Extensions (Design System)**:
- `ios/Ember/Core/Extensions/Color+Ember.swift` -- PASS
- `ios/Ember/Core/Extensions/Font+Ember.swift` -- PASS (1 warning, see below)
- `ios/Ember/Core/Extensions/CGFloat+Ember.swift` -- PASS
- `ios/Ember/Core/Extensions/EmberSymbol.swift` -- PASS

**Resources**:
- `ios/Ember/Resources/LaunchScreen.storyboard` -- PASS
- `ios/Ember/Resources/Assets.xcassets/` -- PASS (10 color sets + AccentColor + AppIcon)

**Tests**:
- `ios/EmberTests/App/AppRouterTests.swift` -- PASS
- `ios/EmberTests/Core/ColorTests.swift` -- PASS
- `ios/EmberTests/App/AppContainerTests.swift` -- PASS

**Project**:
- `ios/project.yml` -- PASS

## Grep Check Results

| Check | Result |
|-------|--------|
| `ObservableObject` / `@Published` / `@StateObject` | CLEAN -- none found |
| `NavigationView` | CLEAN -- none found |
| `AsyncImage` | CLEAN -- none found |
| Force unwrap (`!`) | 1 instance in `APIClient.swift` line 13 (fallback URL, see warnings) |
| Hardcoded secrets | CLEAN -- none found |
| `/conversations` endpoint path | CLEAN -- none found |

## Architecture Compliance

- [x] `@Observable` used everywhere (no ObservableObject, no @Published, no @StateObject)
- [x] `NavigationStack` used (no NavigationView)
- [x] `.preferredColorScheme(.dark)` on root view in `EmberApp.swift` line 28
- [x] No hardcoded secrets
- [x] All files in spec File Manifest are present

## Warnings (Not Blocking)

### W1: Force unwrap in APIClient fallback (LOW)
**File**: `ios/Ember/Core/Network/APIClient.swift`, line 13
**Detail**: `URL(string: "https://api.ember.ai")!` -- force unwrap on a constant URL string. While this specific URL is guaranteed valid and this is a fallback path, the project standard is "no force unwrap anywhere." Consider using a static `let` with a fatalError message, or `guard let` with a meaningful error.

### W2: Font constants lack `relativeTo:` for Dynamic Type (MEDIUM)
**File**: `ios/Ember/Core/Extensions/Font+Ember.swift`
**Detail**: All 7 font constants use `Font.system(size:weight:design:)` without the `relativeTo:` parameter. The spec (Section 5.6) and `docs/standards/ios.md` Section 10 both require `relativeTo:` to support Dynamic Type scaling. Without it, fonts will not scale when users change their accessibility text size settings. This should be addressed when the first user-facing text feature is implemented, or in a follow-up PR.

### W3: HomePlaceholderView uses hardcoded symbol name (LOW)
**File**: `ios/Ember/Features/Home/HomePlaceholderView.swift`, line 6
**Detail**: Uses `"house.fill"` as a hardcoded string instead of an `EmberSymbol` constant. Other placeholder views correctly use `EmberSymbol` constants. Consider adding `EmberSymbol.houseFill` or similar.

### Documented Deviations (Accepted)

- **AWS Amplify Swift omitted from SPM**: Documented in ios-dev handoff as intentional. Adding the package without `amplifyconfiguration.json` would cause build failures. Will be added with the auth feature.
- **Memories and Profile tabs have independent NavigationStack**: Only the Home tab's NavigationStack is bound to `router.path`. This is acceptable for the scaffold since no cross-tab navigation exists yet.

## Issues Resolved During Review

- None (first-pass clean)

## Spec Compliance Verification

All 17 acceptance criteria from `shared/feature-specs/ios-scaffold.md` Section 9 are satisfied:
1. App launches without crashes -- structure is correct
2. Login placeholder with dev "Sign In" button -- present
3. Onboarding placeholder with "Complete" button -- present
4. Three-tab MainTabView (Home, Memories, Profile) -- present
5. Tab bar tint uses `emberPrimary` -- confirmed (line 65)
6. Dark mode enforced via `.preferredColorScheme(.dark)` -- confirmed (line 28 of EmberApp)
7. 18 color constants match `docs/14-tasarim.md` hex values -- confirmed
8. 7 typography constants defined -- confirmed (Dynamic Type warning noted)
9. 8 spacing + 5 corner radius constants -- confirmed
10. SPM packages: Kingfisher, Lottie, MarkdownUI present (Amplify omitted, documented)
11. LaunchScreen.storyboard with `#0F0F14` background -- confirmed
12. All required directories exist -- confirmed
13. All tests pass (3 test files, 12 test cases) -- structure verified
14. AppRouter push/pop/popToRoot tested -- confirmed (5 tests)
15. HapticManager implemented -- confirmed
16. Asset Catalog color sets present -- confirmed (10 color sets)
17. Project builds cleanly (XcodeGen spec valid) -- structure verified
