# iOS Test Handoff: iOS Design Polish

**Date**: 2026-03-13
**Agent**: ios-tester
**Feature**: P03-10 — ios-design-polish
**Status**: COMPLETE

---

## Test Files Written

### Expanded from ios-dev stubs

| File | Tests | Notes |
|------|-------|-------|
| `ios/EmberTests/Core/Components/ShimmerViewTests.swift` | 27 | Expanded from 6-test stub |
| `ios/EmberTests/Core/Extensions/ScaleButtonStyleTests.swift` | 17 | Expanded from 2-test stub |
| `ios/EmberTests/Core/Extensions/ViewEmberShadowTests.swift` | 29 | Expanded from 3-test stub |

### New file

| File | Tests | Notes |
|------|-------|-------|
| `ios/EmberTests/Features/Profile/ProfileViewModelDesignPolishTests.swift` | 12 | `didSaveSuccessfully` / `flashSaveSuccess()` coverage |

### Total: 85 tests (previously 11 stubs)

---

## Coverage

### ShimmerViewTests (27 tests)
- Default constructor uses `.emberRadius12` constant — verified exact value (12)
- Custom corner radius for every design token: 0, `.emberRadius4`, `.emberRadius12`, `.emberRadius16`, `.emberRadius20`, large values (100)
- All skeleton frame sizes from the spec: DailySummaryCard (~100pt, emberRadius20), CharacterCard (180pt, emberRadius20), chat bubble wide (240x44) and narrow (160x36), MemoryRowView (70pt, emberRadius12), profile name (120x22), profile email (160x13), profile avatar (80x80), settings row (52pt), character picker pill (emberRadius28)
- Grid composition: 4 ShimmerViews in a 2-column LazyVGrid (HomeView skeleton pattern)
- List row composition: avatar circle + name + subtitle shimmer stack
- Alternating chat bubble skeletons in VStack (3 assistant + user pairs)
- `ShimmerModifier` applied via `.shimmer()` to: Circle, Capsule, RoundedRectangle, Rectangle
- `ShimmerModifier` applied via `.modifier(_:)` directly
- Equivalence: `.shimmer()` and `.modifier(ShimmerModifier())` both produce valid AnyView

### ScaleButtonStyleTests (17 tests)
- Constructor with no arguments
- Static `.ember` extension resolves (compile-time constraint verification)
- Design contract: pressed scale 0.85 < 1.0, spring response == 0.2, dampingFraction == 0.6
- Applied to all design-system button types: text (Sign In, Create Account), send icon (arrow.up.circle.fill), VStack icon+text, filled CTA (RoundedRectangle + emberRadius28), character card, tab-bar icon, microphone
- Composition: HStack, VStack, alongside `.disabled()` and `.padding()`, disabled=true button

### ViewEmberShadowTests (29 tests)
- Default property values: `EmberCardShadow.radius == 8`, `y == 4`, `opacity == 0.3`
- Custom property values stored independently (radius, y, opacity)
- Edge cases: zero opacity, zero radius
- Design spec relationship: default radius (8) > light variant (4), default opacity (0.3) > light (0.15)
- `.emberCardShadow()` on: CharacterCardView dimensions, DailySummaryCard, Text, Image avatar, VStack card layout, ZStack card with overlay
- `.emberCardShadowLight()` on: MemoryRowView, Text, Circle, settings row HStack
- Both variants via `.modifier(_:)` direct usage
- Custom `EmberCardShadow(radius:y:opacity:)` instantiation
- Shadow stacking (two `.emberCardShadow()` calls on same view)
- Composition after `.clipShape()` — correct usage pattern per spec
- Composition after `.background()` modifier
- Avatar primary tint shadow (inline `.shadow(color: Color.emberPrimary.opacity(0.3), ...)` from ProfileView)

### ProfileViewModelDesignPolishTests (12 tests)
- `didSaveSuccessfully == false` in initial state (no API calls)
- `updateName` success → `didSaveSuccessfully == true`
- `updateName` API failure (500) → `didSaveSuccessfully == false`
- `updateName` empty trimmed input (guard) → `didSaveSuccessfully == false`
- `updateTimezone` success → `didSaveSuccessfully == true`
- `updateTimezone` network error → `didSaveSuccessfully == false`
- `updateLanguage` success → `didSaveSuccessfully == true`
- `updateLanguage` server error (503) → `didSaveSuccessfully == false`
- Sequential saves (updateName → updateTimezone → updateLanguage): each sets flag to `true`
- Manual reset of `didSaveSuccessfully = false` between saves works
- Failed updateName: `didSaveSuccessfully == false` AND `errorMessage != nil`
- Successful updateName: `didSaveSuccessfully == true` AND `errorMessage == nil`

---

## Coverage Estimate

| Component | Estimated Line Coverage |
|-----------|------------------------|
| `ShimmerView.swift` | >= 80% |
| `View+EmberShadow.swift` | >= 95% |
| `ButtonStyle+Ember.swift` | >= 80% |
| `ProfileViewModel.didSaveSuccessfully` + `flashSaveSuccess()` | >= 90% |

Note: SwiftUI `body` computed properties in view types do not count toward unit test coverage per `docs/standards/testing.md §1` ("View layout and styling" is excluded). The shimmer gradient and modifier body implementations are view layout code.

---

## Test Results

All 85 tests pass. No compilation errors. No force-unwraps introduced.

---

## Issues Found During Testing

None. Implementation matches the spec exactly:
- `EmberCardShadow` defaults (radius 8, y 4, opacity 0.3) match spec §5.1.1
- `EmberCardShadowLight` values (opacity 0.15, radius 4, y 2) match spec §5.1.1
- `ScaleButtonStyle` pressed scale 0.85 with spring(response: 0.2, dampingFraction: 0.6) matches spec §5.1.4
- `ShimmerView` default cornerRadius is `.emberRadius12` (12pt) as per spec §5.1.2
- `ProfileViewModel.didSaveSuccessfully` is set correctly in all three update paths

---

## Notes for Reviewer

1. **didSaveSuccessfully reset timing**: `flashSaveSuccess()` resets the flag after `Task.sleep(nanoseconds: 500_000_000)` (0.5s). Unit tests assert `== true` immediately after the async update call returns — this is the correct observable state for the View. The delayed reset is a UI-timing concern covered by manual QA scenario 12 in the spec.

2. **ScaleButtonStyle makeBody**: `ButtonStyleConfiguration` has no public initialiser in SwiftUI. Tests verify the design contract constants (0.85 / 1.0 / 0.2 / 0.6) and confirm the style applies cleanly to all relevant button types. This is the maximum achievable unit test coverage for `ButtonStyle` conformances without a UIKit host.

3. **pbxproj update**: `ProfileViewModelDesignPolishTests.swift` was added to the pbxproj with new UUIDs (fileRef: `B2C3D4E5F6A7B8C9D0E1F2A3`, buildFile: `A1B2C3D4E5F6A7B8C9D0E1F2`) under Profile test group `7232EC3A121E3961A04DA6A2` and Sources build phase `91FC9734A1965EA61C9B43FF`. The three stub files registered by ios-dev had only their content expanded — no pbxproj changes needed for those.

4. **Existing ViewModel tests**: Haptic changes in `MemoriesViewModel` and `ProfileViewModel` are fire-and-forget and do not affect any existing test outcomes. All existing tests in `MemoriesViewModelTests.swift`, `ProfileViewModelTests.swift`, and `ProfileViewModelExtendedTests.swift` remain valid.
