# iOS Design Polish

> A visual polish pass across all existing iOS screens that replaces plain spinners with shimmer skeletons, adds card shadows, standardizes haptic feedback, and introduces micro-interaction animations throughout the app.

**Status**: Released
**Added in**: P03-10 (2026-03-13)
**Platforms**: iOS

---

## Overview

This feature is a comprehensive visual refinement of the Home, Chat, Memories, Profile, Auth, and Tab Bar screens. No new screens or API calls were introduced. The goal was to close the gap between a functional app and a polished, premium product by ensuring every screen adheres to the design system defined in `docs/14-tasarim.md`.

The work is grouped into seven categories: card shadows for visual depth, shimmer skeleton loading states to replace all centered `ProgressView` spinners, consistent pull-to-refresh across all three tab root views, micro-interaction animations (send button scale, message slide-in, unread dot pulse, segment pill sliding indicator), a haptic feedback consistency audit with targeted additions, tab bar shadow polish, and auth screen button animation.

The feature depended on all four preceding iOS screen features (P03-06 through P03-09) being complete. It introduces three new reusable components — `ShimmerView`, `EmberCardShadow` / `EmberCardShadowLight`, and `ScaleButtonStyle` — that are now available across the entire codebase.

---

## Architecture

### How It Works

Because this is a view-layer-only feature, there is no data flow change. The architecture description focuses on where each new component fits and how it interacts with existing ViewModel state.

1. A ViewModel's `isLoading` flag (unchanged) drives the skeleton display: when `isLoading` is `true` and the data array is empty, the view renders a skeleton layout instead of a `ProgressView`.
2. The skeleton layout is composed of `ShimmerView` instances sized and shaped to match the real content they stand in for.
3. When `isLoading` transitions to `false`, SwiftUI animates the swap from skeleton to real content via `.animation(.easeInOut(duration: 0.3), value: viewModel.isLoading)` and `.transition(.opacity)`.
4. Card components receive `.emberCardShadow()` or `.emberCardShadowLight()` modifiers applied after `.clipShape()`. These are view modifiers with no ViewModel dependency.
5. `ScaleButtonStyle` is applied at the call site (`buttonStyle(.ember)`) — it reads `configuration.isPressed` internally and animates the scale using a spring (response: 0.2, dampingFraction: 0.6).
6. New message bubbles in ChatView receive `.transition(.move(edge: .bottom).combined(with: .opacity))`. The wrapping `withAnimation(.spring(response: 0.35, dampingFraction: 0.8))` is triggered when the ViewModel appends messages.
7. The `MemoriesView` segment picker uses `matchedGeometryEffect(id: "selectedSegment", in: namespace)` on the selected pill's `Capsule` background. The `@Namespace` lives in `MemoriesView`.
8. Haptic calls (`HapticManager.impact`, `HapticManager.selection`, `HapticManager.notification`) are fire-and-forget and have no ViewModel state dependency.
9. The `ProfileViewModel` gained a `didSaveSuccessfully` flag with a `flashSaveSuccess()` method. `ProfileView` observes it to show a 0.5-second `Color.emberSuccess.opacity(0.2)` overlay on the saved row.

### New Shared Components

| Component | File | Purpose |
|-----------|------|---------|
| `ShimmerView` | `Core/Components/ShimmerView.swift` | Rounded-rectangle loading placeholder with sweeping gradient animation |
| `ShimmerModifier` | Same file | Applies shimmer overlay to non-rectangular shapes (e.g., avatar circles). Access via `.shimmer()` |
| `EmberCardShadow` | `Core/Extensions/View+EmberShadow.swift` | Standard card shadow. Access via `.emberCardShadow()` |
| `EmberCardShadowLight` | Same file | Lighter shadow for smaller elements. Access via `.emberCardShadowLight()` |
| `ScaleButtonStyle` | `Core/Extensions/ButtonStyle+Ember.swift` | Press-to-scale button style. Access via `.buttonStyle(.ember)` |

### Shadow Values

The design system does not specify exact shadow numbers. The values chosen for this feature are:

| Variant | Color opacity | Radius | Y offset | Used on |
|---------|--------------|--------|----------|---------|
| Standard (`emberCardShadow`) | 0.30 | 8 | 4 | CharacterCardView, DailySummaryCard |
| Light (`emberCardShadowLight`) | 0.15 | 4 | 2 | MemoryRowView |
| Avatar (inline) | `emberPrimary` 0.30 | 8 | 2 | Profile avatar circle |
| Input bar (inline) | `black` 0.20 | 4 | -2 | ChatInputBar top edge |
| Tab bar (UITabBarAppearance) | `black` 0.30 | — | — | `appearance.shadowColor` |

### Shimmer Animation Parameters

- **Duration**: 1.2 seconds per sweep
- **Repeat**: `.repeatForever(autoreverses: false)` — phase travels from -1 to 1
- **Base color**: `Color.emberSurface2`
- **Highlight color**: `Color.emberSurface3.opacity(0.6)`
- **Default corner radius**: `.emberRadius12` (overridable per skeleton)

---

## iOS Implementation

### New Files

- `ios/Ember/Core/Components/ShimmerView.swift` — `ShimmerView` struct + `ShimmerModifier` ViewModifier + `.shimmer()` View extension
- `ios/Ember/Core/Extensions/View+EmberShadow.swift` — `EmberCardShadow`, `EmberCardShadowLight` ViewModifiers + `.emberCardShadow()` / `.emberCardShadowLight()` View extensions
- `ios/Ember/Core/Extensions/ButtonStyle+Ember.swift` — `ScaleButtonStyle` + `.ember` static extension on `ButtonStyle`

### Modified Files

| File | Changes |
|------|---------|
| `Features/Home/HomeView.swift` | Skeleton loading layout (shimmer grid + summary card); greeting header fade-in + slide-up on appear |
| `Features/Home/CharacterCardView.swift` | `.emberCardShadow()` on card container; unread dot pulse animation |
| `Features/Home/DailySummaryCard.swift` | `.emberCardShadow()` on card container |
| `Features/Chat/ChatView.swift` | Skeleton chat bubble layout; message slide-up transition; empty-state icon scale pulse |
| `Features/Chat/ChatInputBar.swift` | Removed `Divider()`, replaced with `.shadow(color: Color.black.opacity(0.2), radius: 4, y: -2)`; `ScaleButtonStyle` on send button |
| `Features/Memories/MemoriesView.swift` | Skeleton loading layout; `.refreshable`; `matchedGeometryEffect` on segment pill background; delete haptic on swipe action |
| `Features/Memories/MemoryRowView.swift` | `.emberCardShadowLight()` on row card |
| `Features/Memories/MemoriesViewModel.swift` | Delete success haptic changed to `.notification(.success)`; `.notification(.error)` added on load failure and delete failure |
| `Features/Profile/ProfileView.swift` | Skeleton loading layout; `.refreshable`; avatar shadow; `showSaveSuccess` overlay; timezone sheet `.presentationDetents([.large])` + `.presentationDragIndicator(.visible)` |
| `Features/Profile/ProfileViewModel.swift` | Added `didSaveSuccessfully: Bool` + `flashSaveSuccess()` for save feedback coordination |
| `App/MainTabView.swift` | `appearance.shadowColor` on tab bar; `HapticManager.selection()` on `.onChange(of: selectedTab)` |
| `Features/Auth/LoginView.swift` | `ScaleButtonStyle` on Sign In button |
| `Features/Auth/SignUpView.swift` | `ScaleButtonStyle` on Create Account button |

### Files Verified Correct (No Changes)

- `Features/Auth/AuthViewModel.swift` — already had `HapticManager.notification(.error)` on both sign-in and sign-up error paths
- `Features/Chat/ChatViewModel.swift` — already had error haptics on stream error and catch paths
- `Features/Chat/MessageBubbleView.swift` — transitions are applied at the `ForEach` level in `ChatView`, not inside the bubble
- `Features/Profile/TimezonePickerSheet.swift` — presentation modifiers applied at the `.sheet` call site in `ProfileView`
- `App/EmberApp.swift` — already had `.animation(.easeInOut(duration: 0.35), value: authViewModel.isAuthenticated)` on the auth/main transition

### Key Patterns

**Skeleton loading** — all skeleton layouts use the same `isLoading` flag that already controlled the `ProgressView`. No ViewModel logic changed. The skeleton is a separate `@ViewBuilder` private var that SwiftUI swaps in via `.transition(.opacity)`.

**ScaleButtonStyle usage**:
```swift
Button { /* action */ } label: { /* label */ }
    .buttonStyle(.ember)
```

**EmberCardShadow usage** (applied after `.clipShape()`):
```swift
CardView()
    .clipShape(RoundedRectangle(cornerRadius: .emberRadius20))
    .emberCardShadow()
```

**matchedGeometryEffect for segment pills** — the `@Namespace` lives in `MemoriesView`. Only the selected pill's `Capsule` background carries the `matchedGeometryEffect`; the unselected pill's background does not, so SwiftUI interpolates the capsule position between selections.

**Save success feedback in ProfileView**:
- `ProfileViewModel.flashSaveSuccess()` sets `didSaveSuccessfully = true`, then after 0.5 seconds resets it to `false`.
- `ProfileView` observes this flag to show a `Color.emberSuccess.opacity(0.2)` overlay that fades in and out.

### State Properties Added

`ProfileViewModel`:
- `didSaveSuccessfully: Bool` — drives the save success overlay in `ProfileView`

`HomeView`:
- `@State private var hasAppeared: Bool = false` — drives the greeting header fade-in + slide-up

`ProfileView`:
- `@State private var showSaveSuccess: Bool = false` — local flag for the save success overlay (in addition to the ViewModel flag)

`MemoriesView`:
- `@Namespace private var namespace` — required for `matchedGeometryEffect` on segment pills

---

## API Reference

This feature introduces no API changes. See [`docs/04-veri-api.md`](../04-veri-api.md) for all existing endpoint contracts.

---

## Testing

### Test Files Created

| File | What It Tests |
|------|--------------|
| `ios/EmberTests/Core/Components/ShimmerViewTests.swift` | `ShimmerView` renders without crash at small, medium, and full-width sizes; custom corner radius; `.shimmer()` modifier on non-rectangular shapes |
| `ios/EmberTests/Core/Extensions/ScaleButtonStyleTests.swift` | `ScaleButtonStyle` can be applied to a `Button` without crash |
| `ios/EmberTests/Core/Extensions/ViewEmberShadowTests.swift` | `.emberCardShadow()` and `.emberCardShadowLight()` can be applied to any `View` |

### Existing Tests Unaffected

The following test files required no changes. Haptic calls are fire-and-forget and do not affect ViewModel outcomes:

- `ios/EmberTests/Features/Home/HomeViewModelTests.swift`
- `ios/EmberTests/Features/Chat/ChatViewModelTests.swift`
- `ios/EmberTests/Features/Memories/MemoriesViewModelTests.swift`
- `ios/EmberTests/Features/Profile/ProfileViewModelTests.swift`

### Running Tests

```bash
cd ios && xcodebuild test -scheme Ember -destination "platform=iOS Simulator,name=iPhone 15" -only-testing EmberTests/Core/Components/ShimmerViewTests -only-testing EmberTests/Core/Extensions/ScaleButtonStyleTests -only-testing EmberTests/Core/Extensions/ViewEmberShadowTests
```

To run the full test suite:

```bash
cd ios && xcodebuild test -scheme Ember -destination "platform=iOS Simulator,name=iPhone 15"
```

### Manual Verification Checklist

The following scenarios require a device or simulator because they involve animation and haptics:

1. Launch with throttled network — verify shimmer skeletons appear on Home, Chat, Memories, and Profile screens (not spinners)
2. Verify `DailySummaryCard` and `CharacterCardView` have visible drop shadows
3. With a character that has unread messages — verify the red dot pulses with a repeating scale animation
4. Open a chat on slow network — verify skeleton bubble layout appears
5. Tap the send button — verify it scales to 0.85 and springs back
6. Send a message — verify the new assistant bubble slides up from the bottom with fade-in
7. Verify the ChatInputBar area above the text field has a shadow, not a hard divider line
8. Pull down on the Memories tab — verify pull-to-refresh indicator appears and data reloads
9. Swipe to delete a memory — verify medium haptic on swipe and success haptic on confirmation
10. Tap different character segment pills — verify the selected capsule slides smoothly (matchedGeometryEffect)
11. Pull down on the Profile tab — verify pull-to-refresh works
12. Edit a display name and save — verify success haptic and brief green tint on the saved row
13. Switch between tabs — verify a selection haptic fires on each switch
14. Verify the tab bar has a subtle top shadow
15. Tap Sign In or Create Account on auth screens — verify the button scales on press

---

## Known Limitations

- Pull-to-refresh on `HomeView` was already present before this feature (added in P03-06). This feature added it to `MemoriesView` and `ProfileView` to make the behavior consistent across all tab roots.
- The `matchedGeometryEffect` for segment pills is implemented inside a `ScrollView(.horizontal)`. SwiftUI's `matchedGeometryEffect` works correctly in this layout, but if the number of character pills is large enough to require scrolling, the animation path may clip at the scroll container edge. This is an accepted limitation for the current phase.
- The unread dot pulse uses a repeating scale animation (1.0 to 1.15). It does not use `TimelineView(.animation)` as mentioned as an alternative in the spec — the simpler `withAnimation(.easeInOut.repeatForever(autoreverses: true))` approach was used instead, which achieves the same visual result.
- Shadow values are not pulled from design tokens because `docs/14-tasarim.md` does not specify exact shadow numbers. The values (opacity 0.30, radius 8, y 4 for standard; opacity 0.15, radius 4, y 2 for light) are documented here as the canonical reference until the design system is updated.

---

## Extending This Feature

**Adding a skeleton to a new screen**: Create a `@ViewBuilder private var loadingView` in the new view that uses `ShimmerView` instances sized to match the real content. The skeleton should replace the current `ProgressView` by checking `viewModel.isLoading && viewModel.data.isEmpty`. Apply `.transition(.opacity)` on both the skeleton and the content, and `.animation(.easeInOut(duration: 0.3), value: viewModel.isLoading)` on the wrapping `Group`.

**Adding a new card type**: Apply `.emberCardShadow()` for full-size cards or `.emberCardShadowLight()` for smaller list rows, placed after the `.clipShape()` call. Do not pass custom values to the modifier — use the two standard variants to keep shadows consistent.

**Adding a new primary CTA button**: Apply `.buttonStyle(.ember)` to get the design system scale press animation at no cost.

**Adding new haptic touchpoints**: Call `HapticManager.impact(.light)` for standard taps, `HapticManager.impact(.medium)` for destructive actions, `HapticManager.notification(.success)` or `.error` for operation outcomes, and `HapticManager.selection()` for picker or segment changes. Keep calls fire-and-forget at the call site — do not store haptic state in ViewModels.

---

## Related Documentation

- [Design System](../14-tasarim.md)
- [Mobile Screens](../07-mobil.md)
- [iOS Scaffold](ios-scaffold.md)
- [iOS Chat View](ios-chat-view.md)
- [iOS Memory List](ios-memory-list.md)
- [iOS Profile View](ios-profile-view.md)
