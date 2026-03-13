---
name: ios-design-polish test patterns
description: Patterns established during P03-10 iOS Design Polish testing — SwiftUI ViewModifier/ButtonStyle testing approach, ShimmerView composition tests, didSaveSuccessfully flash flag testing, pbxproj group IDs for design polish tests
type: project
---

The design polish feature (P03-10) adds three new shared components and one new ViewModel property. All are view-layer with no service or network dependencies — tests verify construction, default property values, and rendering without crash.

## Component Test Patterns

### ViewModifier tests (EmberCardShadow, ShimmerModifier)
- Verify stored property values directly: `modifier.radius == 8`, `modifier.y == 4`, `modifier.opacity == 0.3`
- Verify View extensions compile correctly: wrap result in `AnyView` and discard with `_ =`
- Test every shape type mentioned in the spec: Circle, Capsule, RoundedRectangle, Rectangle, Text, Image, VStack, ZStack
- Test every frame size mentioned in the spec (skeleton dimensions): card (100pt), row (70pt), bubble (240x44), avatar (80x80), etc.
- Test composition patterns: shadows after `.clipShape()` and `.background()`, stacked shadows

### ButtonStyle tests (ScaleButtonStyle)
- `ButtonStyleConfiguration` has NO public initialiser — cannot call `makeBody(configuration:)` directly
- Verify design contract constants as literal `#expect` values: 0.85, 1.0, 0.2, 0.6
- Verify all design-system button types compile: text CTA, icon-only, filled RoundedRectangle, card, tab-bar icon
- The static `where Self == ScaleButtonStyle` extension is verified by using `.buttonStyle(.ember)` in a test

### ShimmerView tests
- ShimmerView stores `cornerRadius` as a stored `let` — verify default == `.emberRadius12`
- Test all skeleton sizes from the spec to ensure they're buildable
- Test `ShimmerModifier` both via `.shimmer()` extension and `.modifier(ShimmerModifier())` directly

## ProfileViewModel.didSaveSuccessfully

`flashSaveSuccess()` is private and sets `didSaveSuccessfully = true`, then resets after 0.5s via `Task.sleep`. In unit tests:
- Assert `== true` immediately after `await vm.updateName()`/`updateTimezone()`/`updateLanguage()` — the async function has returned but the delayed reset task has NOT yet fired
- Assert `== false` on failure paths — the flag is never set on the catch branch
- Never try to observe the delayed reset in a unit test (it's a UI timing concern for manual QA)
- `didSaveSuccessfully` is a public `var` and can be manually reset to `false` between sequential save tests

## ios-dev left test stubs

For P03-10 the ios-dev pre-registered three test files with minimal content (6, 2, 3 tests respectively). The ios-tester expanded them in-place:
- `ios/EmberTests/Core/Components/ShimmerViewTests.swift` — fileRef `8EF01901F82F3FC3E20F1371`
- `ios/EmberTests/Core/Extensions/ScaleButtonStyleTests.swift` — fileRef `7DD8044BD987D0FA332BC0EC`
- `ios/EmberTests/Core/Extensions/ViewEmberShadowTests.swift` — fileRef `1136DA5D1E4E538F920EA57B`

New file added:
- `ios/EmberTests/Features/Profile/ProfileViewModelDesignPolishTests.swift` — fileRef `B2C3D4E5F6A7B8C9D0E1F2A3`, buildFile `A1B2C3D4E5F6A7B8C9D0E1F2`
- Profile test group UUID: `7232EC3A121E3961A04DA6A2`
- Sources build phase: `91FC9734A1965EA61C9B43FF`

**Why:** This is the first feature where the ios-dev pre-created test stubs. For future features, always check if test files already exist in the pbxproj before registering new ones.

**How to apply:** When ios-dev notes say "test files already registered," read the existing file content before writing tests. Expand in-place rather than creating a new file. Only create new test files when coverage requires a completely separate concern (e.g., a new ViewModel property class).
