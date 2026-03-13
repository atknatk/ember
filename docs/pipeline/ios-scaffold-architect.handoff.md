# Architect Handoff: iOS Scaffold

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## What Was Designed

The foundational Xcode project scaffold for the Ember iOS app. Includes the SwiftUI app entry point with `@AppStorage`-based auth state routing, a three-tab `MainTabView` (Home, Memories, Profile), `AppRouter` with `NavigationStack`, the complete design system (colors from `docs/14-tasarim.md`, typography, spacing, corner radii), core stubs (APIClient protocol, AuthService protocol, HapticManager), SPM package declarations, `LaunchScreen.storyboard`, and Asset Catalog color sets.

## Key Decisions

- **Placeholder views over empty directories**: Each tab and auth flow has a minimal placeholder view that proves navigation works end-to-end. These will be replaced by real implementations in subsequent features.
- **System fonts, not Inter**: Inter is specified in the design system but font files are not bundled yet. System fonts with matching weights/sizes and `relativeTo:` for Dynamic Type are used. `Font+Ember.swift` is the single update point when Inter is added.
- **`docs/14-tasarim.md` colors take precedence**: There is a discrepancy between `docs/standards/ios.md` Section 10 (e.g., `#7C6AF7` primary) and `docs/14-tasarim.md` (e.g., `#5B4FE8` primary). The design system doc is authoritative per the issue description.
- **`@AppStorage` for auth state in scaffold**: Simple persistent boolean for dev testing. Will be replaced by Cognito session checking in the auth feature.
- **Firebase SDK deferred**: Not added to SPM dependencies in this scaffold. Will be added when push notifications are implemented to avoid unnecessary build time overhead.
- **No SSEClient or full APIClient**: Only protocols and error types created. Full implementations arrive with the first networking feature.
- **Hex initializer + Asset Catalog dual approach**: Code-level hex initializer is source of truth; Asset Catalog color sets exist for Interface Builder (LaunchScreen.storyboard) compatibility.

## Spec Location

`shared/feature-specs/ios-scaffold.md`

## Assumptions Made

- The Xcode project will be created manually via Xcode's New Project wizard, then restructured to match the specified directory layout.
- Swift 5.9+ and iOS 17+ deployment target (as per `CLAUDE.md`).
- No CI/CD workflow changes needed for this feature (iOS CI workflow already exists at `.github/workflows/ios-ci.yml`).
- The backend is already operational from Phase 1 work, but this scaffold makes no network calls.

## Dependencies

- Requires: P01-07 (backend operational) -- logical dependency only, no runtime dependency
- Blocks: All subsequent iOS features (auth UI, character list, chat view, memory display, voice)

## Next Steps

ios-dev should read the spec and implement. No backend-dev or android-dev work needed for this feature.
