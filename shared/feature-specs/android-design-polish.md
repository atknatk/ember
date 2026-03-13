# Feature Spec: P04-08 -- Android Design Polish

**Feature ID**: P04-08
**Phase**: 4
**Layer**: android
**GitHub Issue**: #35
**Date**: 2026-03-13
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature is a visual polish pass across all existing Android screens -- Home, Chat, Memories, Profile, Auth, and the bottom navigation bar. No new screens are introduced. The goal is to bring every view into full alignment with the design system defined in `docs/14-tasarim.md` and match the iOS design polish implemented in P03-10.

The polish work falls into seven categories:

1. **Shimmer loading skeletons** -- Replace all `CircularProgressIndicator` loading states with shimmer skeleton placeholders that match the shape of the content they replace (character card skeletons in Home, message bubble skeletons in Chat, memory row skeletons in Memories, profile header skeleton in Profile).

2. **Card shadows/elevation** -- Add consistent drop shadows to `Card` components (DailySummaryCard, CharacterCard, MemoryRow) using a reusable `emberCardShadow()` modifier.

3. **Scale button effect** -- Add press-to-scale animation (1.0 to 0.85 to 1.0 with spring) on the chat send button and auth CTA buttons.

4. **Pull-to-refresh** -- Ensure all tab root views (Home already has it, add to Memories and Profile) support pull-to-refresh.

5. **Micro-interactions** -- Greeting header fade-in + slide-up animation, unread dot pulse animation, input bar top shadow replacing hard divider.

6. **Bottom bar polish** -- Add top shadow to the bottom navigation bar for visual depth.

7. **Haptic consistency** -- Add haptic feedback on memory swipe-to-delete gesture (was missing), maintain existing haptics across all interactions.

### Why It Exists

The individual screen features (P04-05 through P04-07) focused on correctness. This polish pass makes the app feel finished, consistent, and premium. It matches the iOS design polish (P03-10) to ensure platform parity.

### Dependencies

- P04-05 (android-home) -- HomeScreen exists and is functional.
- P04-06 (android-chat) -- ChatScreen, ChatInputBar, MessageBubble exist and are functional.
- P04-07 (android-memory-list) -- MemoriesScreen exists and is functional.
- P04-09 (android-profile-screen) -- ProfileScreen exists and is functional.
- P04-02 (android-scaffold) -- Design token files (Color, Shape, Spacing, Theme) are the source of truth.

### What This Feature Does NOT Do

- It does not add new API calls or change backend behavior.
- It does not add new screens or change navigation structure.
- It does not change data models or ViewModel logic.
- It does not implement Lottie animations.
- It does not implement light mode.

---

## 2. Data Models

No changes.

---

## 3. API Endpoints

No changes.

---

## 4. Backend Logic

Not applicable.

---

## 5. Android Screens and Components

### 5.1 New Shared Components

#### 5.1.1 `ShimmerEffect.kt`

**File**: `android/.../core/ui/components/ShimmerEffect.kt`

Reusable shimmer composables: `ShimmerBox` (rounded rectangle with sweeping gradient), `ShimmerCircle` (circular avatar placeholder), and `rememberShimmerBrush()` (shared animation). Colors: base EmberSurface2, highlight EmberSurface3 at 60% opacity. Animation: 1200ms sweep, linear easing, infinite repeat.

#### 5.1.2 `SkeletonLayouts.kt`

**File**: `android/.../core/ui/components/SkeletonLayouts.kt`

Pre-built skeleton layouts for each screen: `HomeSkeletonLoader`, `ChatSkeletonLoader`, `MemoriesSkeletonLoader`, `ProfileSkeletonLoader`. Each matches the shape and layout of its screen's success content.

#### 5.1.3 `EmberModifiers.kt`

**File**: `android/.../core/ui/components/EmberModifiers.kt`

Reusable modifiers:
- `Modifier.emberCardShadow()` -- Standard card shadow (8dp elevation, black 30%).
- `Modifier.emberCardShadowLight()` -- Light card shadow for smaller elements (4dp, black 15%).
- `Modifier.scaleOnPress()` -- Scale-to-0.85 on press with spring animation.

### 5.2 HomeScreen Polish

- Loading state: shimmer skeleton replacing CircularProgressIndicator.
- DailySummaryCard: `.emberCardShadow()` modifier.
- CharacterCard: `.emberCardShadow()` modifier.
- Unread dot: pulsing scale animation (1.0 to 1.15, 800ms, infinite).
- GreetingHeader: fade-in + slide-up animation on first appearance (400ms).

### 5.3 ChatScreen Polish

- Loading state: shimmer skeleton with alternating bubble shapes.
- ChatInputBar: top shadow replacing hard edge (4dp elevation).
- Send button: scale-on-press animation (0.85 scale, spring).

### 5.4 MemoriesScreen Polish

- Pull-to-refresh: `PullToRefreshBox` wrapping success content.
- Loading state: shimmer skeleton with pill and row placeholders.
- MemoryRow: `.emberCardShadowLight()` modifier.
- Swipe-to-delete: haptic feedback on swipe gesture.

### 5.5 ProfileScreen Polish

- Pull-to-refresh: `PullToRefreshBox` wrapping success content.
- Loading state: shimmer skeleton with avatar circle and row placeholders.
- Avatar: shadow with EmberPrimary tint (8dp, 30% opacity).

### 5.6 Auth Screens Polish

- Sign In button: scale-on-press animation via InteractionSource.
- Create Account button: scale-on-press animation via InteractionSource.

### 5.7 EmberBottomBar Polish

- Top shadow: 8dp elevation with black 30% opacity.

---

## 6. Test Plan

### 6.1 Unit Tests

No new unit tests required. All changes are view-layer only.

Existing tests verified to still pass:
- `HomeViewModelTest` -- No logic changes.
- `ChatViewModelTest` -- No logic changes.
- `MemoriesViewModelTest` -- No logic changes.
- `ProfileViewModelTest` -- No logic changes.
- `AuthViewModelTest` -- No logic changes.

### 6.2 UI/Manual Test Scenarios

1. Home skeleton: launch with slow network, verify shimmer placeholders appear instead of spinner.
2. Card shadows: verify DailySummaryCard and CharacterCard have subtle shadows.
3. Unread dot pulse: verify the unread dot gently pulses.
4. Greeting animation: verify greeting header fades in and slides up on first load.
5. Chat skeleton: open chat with slow network, verify shimmer bubbles appear.
6. Send button scale: tap send button, verify it scales down and springs back.
7. Input bar shadow: verify chat input bar has subtle top shadow.
8. Memories pull-to-refresh: pull down on memories list, verify refresh works.
9. Memory row shadow: verify memory cards have light shadows.
10. Memory swipe haptic: swipe to delete, verify haptic fires.
11. Profile skeleton: load profile with slow network, verify shimmer placeholders.
12. Profile pull-to-refresh: pull down on profile, verify refresh works.
13. Avatar shadow: verify profile avatar has purple-tinted shadow.
14. Auth button scale: tap sign in/create account, verify scale animation.
15. Bottom bar shadow: verify bottom navigation has top shadow.

---

## 7. Acceptance Criteria

1. All loading states show shimmer skeleton placeholders instead of centered spinners.
2. Character cards and daily summary card have visible drop shadows.
3. Unread dot pulses with a repeating scale animation.
4. Greeting header animates in with fade + slide-up.
5. Send button scales to 0.85 on press and springs back.
6. Chat input bar has a subtle top shadow.
7. Memories screen supports pull-to-refresh.
8. Memory rows have light card shadows.
9. Swipe-to-delete fires medium haptic feedback.
10. Profile screen supports pull-to-refresh.
11. Profile avatar has a purple-tinted shadow.
12. Auth CTA buttons scale on press.
13. Bottom navigation bar has a top shadow.
14. All existing tests pass without modification.
15. No `!!` force unwraps in any modified file.
16. No hardcoded strings in any modified file.

---

## 8. File Manifest

```
Android:
  CREATE android/.../core/ui/components/ShimmerEffect.kt
  CREATE android/.../core/ui/components/SkeletonLayouts.kt
  CREATE android/.../core/ui/components/EmberModifiers.kt
  MODIFY android/.../core/ui/components/EmberBottomBar.kt
  MODIFY android/.../features/home/HomeScreen.kt
  MODIFY android/.../features/chat/ChatScreen.kt
  MODIFY android/.../features/chat/ChatInputBar.kt
  MODIFY android/.../features/memories/MemoriesScreen.kt
  MODIFY android/.../features/profile/ProfileScreen.kt
  MODIFY android/.../features/auth/LoginScreen.kt
  MODIFY android/.../features/auth/SignUpScreen.kt

Shared:
  CREATE shared/feature-specs/android-design-polish.md (this file)
  CREATE docs/pipeline/android-design-polish-architect.handoff.md
  CREATE docs/pipeline/android-design-polish-android-dev.handoff.md
```
