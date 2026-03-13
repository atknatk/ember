# Feature Spec: P03-10 -- iOS Design Polish

**Feature ID**: P03-10
**Phase**: 3
**Layer**: ios
**GitHub Issue**: #26
**Date**: 2026-03-13
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature is a visual polish pass across all existing iOS screens -- Home, Chat, Memories, Profile, Auth, and the tab bar. No new screens are introduced. The goal is to bring every view into full alignment with the design system defined in `docs/14-tasarim.md` and the design token extensions in `Core/Extensions/`.

The polish work falls into seven categories:

1. **Shadows and elevation** -- Cards (CharacterCardView, DailySummaryCard, MemoryRowView) currently have no drop shadow. The design system calls for subtle shadows to create visual depth between surface layers. A reusable `ViewModifier` will be created to apply consistent card shadows app-wide.

2. **Transition animations** -- The design system specifies screen transitions (Home to Chat: slide up + fade, 300ms; modal open: bottom sheet spring, 350ms). Currently, navigation relies on the default NavigationStack push animation. Custom transitions should be added for the Chat push and for sheet presentations (TimezonePickerSheet).

3. **Loading skeletons** -- Currently, all loading states use a plain centered `ProgressView`. These should be replaced with shimmer/skeleton placeholder views that match the shape of the content they are replacing (character card skeletons in Home, message bubble skeletons in Chat, memory row skeletons in Memories, profile header skeleton in Profile).

4. **Pull-to-refresh consistency** -- HomeView has `.refreshable` but MemoriesView and ProfileView do not. All three tab root views should support pull-to-refresh with a consistent tinted refresh indicator.

5. **Tab bar polish** -- The tab bar uses `UITabBarAppearance` with `configureWithOpaqueBackground()` and `emberSurface` background, which is correct. However, it is missing: (a) a subtle top separator line or shadow, (b) the selected-tab indicator animation when switching tabs. The `tint` color is set correctly to `emberPrimary`.

6. **Micro-interactions** -- Several design system micro-interactions are missing:
   - Send button scale animation (1.0 to 0.85 to 1.0 on tap) per `docs/14-tasarim.md`.
   - New message slide-up + fade-in animation when appended to the chat list.
   - Notification badge scale pop (spring) on the unread dot in CharacterCardView.
   - Success checkmark or brief flash when a profile update saves.

7. **Haptic consistency audit** -- `docs/14-tasarim.md` specifies that message send should use `.light` impact (currently correct in ChatInputBar), memory delete should use `.medium` impact (currently not applied -- the delete is triggered via swipe action with no explicit haptic), and error states should use `.heavy` impact (currently the shake animation in LoginView fires haptics, but `ChatViewModel` and `MemoriesViewModel` do not trigger haptic on error).

### Why It Exists

The individual screen features (P03-06 through P03-09) focused on correctness -- getting API integration, data flow, and navigation working. This polish pass makes the app feel finished, consistent, and premium. Users perceive quality through animation smoothness, visual consistency, and tactile feedback. This feature addresses the gap between "functional" and "polished."

### Dependencies

- **P03-07** (ios-chat-view) -- Must be complete. ChatView, ChatInputBar, MessageBubbleView, TypingIndicatorView, DateSeparatorView exist and are functional.
- **P03-08** (ios-memory-list) -- Must be complete. MemoriesView, MemoryRowView exist and are functional.
- **P03-09** (ios-profile-view) -- Must be complete. ProfileView, TimezonePickerSheet exist and are functional.
- **P03-01** (ios-scaffold) -- Design token extensions (Color+Ember, Font+Ember, CGFloat+Ember, EmberSymbol, HapticManager) are the source of truth for all styling constants.

### What This Feature Does NOT Do

- It does not add new API calls or change backend behavior.
- It does not add new screens or change navigation structure.
- It does not implement Lottie animation files. The spec calls for lightweight SwiftUI shimmer and transition animations, not Lottie. Lottie integration for empty states and onboarding already exists in WelcomeView.
- It does not change the data models or ViewModel logic beyond adding animation/state properties.
- It does not implement light mode. Ember is dark-only per `docs/14-tasarim.md`.

---

## 2. Data Models

No database changes. No new Swift model types. This feature only adds view-layer styling and animation state properties to existing ViewModels.

---

## 3. API Endpoints

No API changes. This is a visual-only feature.

---

## 4. Backend Logic

Not applicable. This is an iOS-only visual polish feature.

---

## 5. iOS Screens and Components

### 5.1 New Shared Components

#### 5.1.1 `EmberCardShadow` ViewModifier

**File**: `ios/Ember/Core/Extensions/View+EmberShadow.swift`

A reusable modifier that applies the standard Ember card shadow: color `Color.black.opacity(0.3)`, radius 8, y-offset 4. This creates a subtle lift effect consistent across all card components.

Usage: `.modifier(EmberCardShadow())` or via a convenience `.emberCardShadow()` extension on `View`.

Properties:
- `radius: CGFloat = 8`
- `y: CGFloat = 4`
- `opacity: Double = 0.3`

There should also be an `EmberCardShadowLight` variant with `opacity: 0.15, radius: 4, y: 2` for smaller elements like MemoryRowView.

#### 5.1.2 `ShimmerView` Component

**File**: `ios/Ember/Core/Components/ShimmerView.swift`

A SwiftUI view that renders a rounded rectangle with a sweeping gradient animation to simulate content loading. The gradient moves from leading to trailing over 1.2 seconds and repeats.

Properties:
- `cornerRadius: CGFloat` (defaults to `.emberRadius12`)

Colors: base fill `Color.emberSurface2`, shimmer highlight `Color.emberSurface3.opacity(0.6)`.

This component is used in all skeleton loading states below.

#### 5.1.3 `ShimmerModifier` ViewModifier

**File**: Same file as ShimmerView.

Applies the shimmer gradient overlay to any view shape. Used by skeleton views that need non-rectangular shapes (e.g., circles for avatars).

#### 5.1.4 `ScaleButtonStyle`

**File**: `ios/Ember/Core/Extensions/ButtonStyle+Ember.swift`

A `ButtonStyle` that scales the button content to 0.85 on press and returns to 1.0 with a spring animation (response: 0.2, dampingFraction: 0.6). Used for the send button in ChatInputBar and primary CTA buttons.

Properties: none (values are fixed per design system).

### 5.2 HomeView Polish

**Files modified**: `ios/Ember/Features/Home/HomeView.swift`, `ios/Ember/Features/Home/CharacterCardView.swift`, `ios/Ember/Features/Home/DailySummaryCard.swift`

#### Loading State Change

Replace the current `loadingView` (centered `ProgressView`) with a skeleton layout:
- A shimmer rectangle matching the DailySummaryCard dimensions (full width, height ~100pt, cornerRadius `.emberRadius20`).
- A 2-column grid of 4 shimmer rectangles matching CharacterCardView dimensions (cornerRadius `.emberRadius20`, aspect ratio roughly matching the card height).
- Apply `.animation(.easeInOut(duration: 0.3), value: viewModel.isLoading)` so the skeleton fades out and real content fades in.

#### CharacterCardView Shadow

Add `.emberCardShadow()` modifier to the card's outermost container, after `.clipShape()`.

#### DailySummaryCard Shadow

Add `.emberCardShadow()` modifier after `.clipShape()`.

#### Unread Dot Animation

The unread dot in CharacterCardView already has `.transition(.scale.combined(with: .opacity))`. Enhance it by wrapping the dot in a `TimelineView(.animation)` or using a repeating scale animation (1.0 to 1.15, autoreverses, 0.8s duration) so it gently pulses to draw attention.

#### Greeting Header Animation

Add a fade-in + slight slide-up animation to the greeting text when the view first appears. Use an `@State private var hasAppeared: Bool = false` flag and `.opacity(hasAppeared ? 1 : 0).offset(y: hasAppeared ? 0 : 10)` with `.onAppear { withAnimation(.easeOut(duration: 0.4)) { hasAppeared = true } }`.

#### Character Card Stagger

The existing staggered animation on ForEach (delay based on index) is correct. No change needed.

### 5.3 ChatView Polish

**Files modified**: `ios/Ember/Features/Chat/ChatView.swift`, `ios/Ember/Features/Chat/ChatInputBar.swift`, `ios/Ember/Features/Chat/MessageBubbleView.swift`

#### Loading State Change

Replace the centered `ProgressView` with a skeleton chat layout:
- 3-4 alternating shimmer bubbles (left-aligned wider ones for assistant, right-aligned narrower ones for user) to mimic a conversation.
- Each skeleton bubble has `cornerRadius: .emberRadius16` and varying widths (60-80% for assistant, 40-60% for user).

#### Message Appearance Animation

Each new message appended during streaming should slide up from the bottom with a fade-in. Apply `.transition(.move(edge: .bottom).combined(with: .opacity))` on each `MessageBubbleView` inside the `ForEach`. Wrap the ForEach content changes with `withAnimation(.spring(response: 0.35, dampingFraction: 0.8))` in the ViewModel when messages change.

#### Send Button Scale Animation

In `ChatInputBar`, change the send button's `ButtonStyle` from default to the new `ScaleButtonStyle`. This provides the 1.0 to 0.85 to 1.0 scale effect on tap per the design system.

#### Input Bar Top Shadow

Replace the `Divider()` at the top of `ChatInputBar` with a subtle shadow on the input bar container:
- Remove the `Divider()`.
- Add `.shadow(color: Color.black.opacity(0.2), radius: 4, y: -2)` to the HStack container background.

This creates a more premium divider effect than a 1px line.

#### Empty State Enhancement

The empty chat state icon should have a gentle scale pulse animation (scale 0.95 to 1.05, repeating, 2s duration) to feel alive rather than static.

### 5.4 MemoriesView Polish

**Files modified**: `ios/Ember/Features/Memories/MemoriesView.swift`, `ios/Ember/Features/Memories/MemoryRowView.swift`

#### Pull-to-Refresh

Add `.refreshable { await viewModel.loadMemories() }` to the memory list `List` container.

#### Loading State Change

Replace the centered `ProgressView` with a skeleton layout:
- A horizontal row of 3-4 shimmer capsules matching the character picker pills.
- Below that, 4-5 shimmer rectangles matching MemoryRowView dimensions (height ~70pt, cornerRadius `.emberRadius12`).

#### MemoryRowView Shadow

Add `.emberCardShadowLight()` modifier to each MemoryRowView card after the `.background()` modifier.

#### Delete Haptic

When the user taps the delete swipe action, trigger `HapticManager.impact(.medium)` in the `viewModel.memoryToDelete` setter or directly in the `Button(role: .destructive)` action closure.

#### Delete Confirmation Haptic

When the user confirms deletion and `confirmDelete()` completes successfully, trigger `HapticManager.notification(.success)`. If deletion fails, trigger `HapticManager.notification(.error)`.

#### Segment Pill Transition

The existing `.animation(.easeInOut(duration: 0.2), value: isSelected)` on segment pills is correct. Enhance by adding `.matchedGeometryEffect(id: "selectedSegment", in: namespace)` on the selected pill's background capsule to create a smooth sliding indicator between pills. This requires adding a `@Namespace private var namespace` to `MemoriesView`.

### 5.5 ProfileView Polish

**Files modified**: `ios/Ember/Features/Profile/ProfileView.swift`, `ios/Ember/Features/Profile/TimezonePickerSheet.swift`

#### Pull-to-Refresh

Add `.refreshable { await viewModel.loadProfile() }` to the `ScrollView` in `profileContent`.

#### Loading State Change

Replace the centered `ProgressView` with a skeleton layout:
- A center-aligned shimmer circle (80pt, matching avatar size).
- Below it, a shimmer rectangle (width ~120pt, height ~22pt) for the name.
- Below that, a shimmer rectangle (width ~160pt, height ~13pt) for the email.
- Below those, 2-3 shimmer rectangles for settings rows (full width, height ~52pt, cornerRadius `.emberRadius12`).

#### Save Success Feedback

When `viewModel.updateName()` or `viewModel.updateTimezone()` or `viewModel.updateLanguage()` completes successfully:
- Trigger `HapticManager.notification(.success)`.
- Briefly flash a subtle green checkmark or tint the saved row with `Color.emberSuccess.opacity(0.2)` for 0.5s, then fade back. This can be done via a `@State private var showSaveSuccess: Bool = false` flag with a delayed reset.

#### Avatar Section Shadow

Add a subtle shadow to the avatar circle: `.shadow(color: Color.emberPrimary.opacity(0.3), radius: 8, y: 2)`.

#### Sign Out Button Haptic

Add `HapticManager.impact(.medium)` when the sign out button is tapped, before calling `viewModel.signOut()`.

#### Delete Account Haptic

The existing `HapticManager.notification(.warning)` on delete button tap is correct. No change needed.

#### TimezonePickerSheet Presentation

Add `.presentationDetents([.large])` and `.presentationDragIndicator(.visible)` to the sheet to give it the standard bottom-sheet drag indicator.

### 5.6 MainTabView Polish

**File modified**: `ios/Ember/App/MainTabView.swift`

#### Tab Bar Top Shadow

In the `UITabBarAppearance` configuration in `.onAppear`, add a shadow:
```
appearance.shadowColor = UIColor(Color.black.opacity(0.3))
```

This replaces the default system separator with a more premium shadow effect.

#### Tab Switch Haptic

Add `HapticManager.selection()` when the selected tab changes. Use `.onChange(of: selectedTab) { _, _ in HapticManager.selection() }`.

### 5.7 Auth Views Polish

**Files modified**: `ios/Ember/Features/Auth/LoginView.swift`, `ios/Ember/Features/Auth/SignUpView.swift`

#### Sign In/Sign Up Button Style

Apply `ScaleButtonStyle` to the primary CTA buttons (Sign In, Sign Up) so they scale on press.

#### Error Haptic on Auth Failure

In `AuthViewModel`, when `signIn()` or `signUp()` fails with an error, trigger `HapticManager.notification(.error)`. Currently the shake animation fires but there is no explicit error haptic in the ViewModel -- verify whether the shake handler already includes haptic. If not, add it.

### 5.8 EmberApp.swift Polish

**File modified**: `ios/Ember/App/EmberApp.swift`

No changes needed. The auth-to-main transition already uses `.animation(.easeInOut(duration: 0.35), value: authViewModel.isAuthenticated)` with `.transition(.opacity)`. This is consistent with the design system.

---

## 6. Android Screens and Components

Not applicable. This is an iOS-only feature.

---

## 7. Test Plan

### 7.1 Unit Tests

#### ShimmerView Snapshot/Rendering Test

**File**: `ios/EmberTests/Core/Components/ShimmerViewTests.swift`

- Test that `ShimmerView` renders without crash at various sizes (50x50, 200x50, full width).
- Test that `ShimmerView` with custom corner radius applies correctly.

#### ScaleButtonStyle Test

**File**: `ios/EmberTests/Core/Extensions/ScaleButtonStyleTests.swift`

- Test that `ScaleButtonStyle` exists and can be applied to a `Button` without crash.

#### EmberCardShadow Test

**File**: `ios/EmberTests/Core/Extensions/ViewEmberShadowTests.swift`

- Test that `.emberCardShadow()` modifier can be applied to any `View`.

### 7.2 ViewModel Tests (Existing -- Verify Haptic Additions)

No new ViewModel test files. The following existing test files should be verified to still pass after modifications:

- `ios/EmberTests/Features/Home/HomeViewModelTests.swift` -- No logic changes, should pass as-is.
- `ios/EmberTests/Features/Chat/ChatViewModelTests.swift` -- No logic changes, should pass as-is.
- `ios/EmberTests/Features/Memories/MemoriesViewModelTests.swift` -- Verify that haptic calls added to delete flow do not break existing tests (haptics are fire-and-forget, should not affect test outcomes).
- `ios/EmberTests/Features/Profile/ProfileViewModelTests.swift` -- Same verification.

### 7.3 UI/Manual Test Scenarios

These scenarios require running the app on a device or simulator and verifying visually:

1. **Home skeleton**: Launch app with slow/mocked network. Verify skeleton placeholders appear instead of spinner. Verify they fade out when content loads.
2. **Card shadows**: Verify DailySummaryCard and CharacterCardView have subtle shadows visible against the background.
3. **Unread dot pulse**: Create a scenario where a character has unread messages. Verify the red dot gently pulses.
4. **Chat skeleton**: Open a chat for the first time with slow network. Verify skeleton bubbles appear.
5. **Send button scale**: Tap the send button and verify it scales down and springs back.
6. **Message slide-in**: Send a message and verify the new assistant bubble slides up from the bottom.
7. **Input bar shadow**: Verify the chat input bar has a subtle top shadow instead of a hard divider line.
8. **Memories pull-to-refresh**: Pull down on the memories list and verify the refresh indicator appears and data reloads.
9. **Memory delete haptic**: Swipe to delete a memory and verify haptic feedback on the swipe action and on confirmation.
10. **Segment pill transition**: Tap different character segments in MemoriesView and verify the selected indicator slides smoothly.
11. **Profile skeleton**: Load profile with slow network and verify skeleton placeholders appear.
12. **Profile save feedback**: Edit the display name, save, and verify a brief success indicator (haptic + visual).
13. **Tab switch haptic**: Switch between tabs and verify a selection haptic fires on each switch.
14. **Tab bar shadow**: Verify the tab bar has a subtle top shadow.
15. **Auth button scale**: On the login screen, tap Sign In and verify the button scales on press.

---

## 8. Acceptance Criteria

1. Given the Home screen is loading characters, when the API call is in flight, then shimmer skeleton placeholders are shown instead of a centered spinner.
2. Given characters have loaded, when the Home screen renders CharacterCardView and DailySummaryCard, then both card types have a visible drop shadow that creates visual depth against the background.
3. Given a character has unread messages, when the unread dot appears on CharacterCardView, then the dot gently pulses with a repeating scale animation.
4. Given the Chat screen is loading message history, when the API call is in flight, then shimmer skeleton bubbles are shown instead of a centered spinner.
5. Given the user taps the send button in ChatInputBar, then the button scales to 0.85 and springs back to 1.0.
6. Given a new message is appended to the chat list (user or streaming assistant), then the bubble slides up from the bottom with a fade-in transition.
7. Given the ChatInputBar is visible, then the area above the input bar has a subtle shadow instead of a hard 1px divider.
8. Given the user pulls down on the Memories tab, then a pull-to-refresh indicator appears and memories reload.
9. Given the user swipes to delete a memory, then a medium haptic fires on the swipe action, and a success haptic fires when deletion completes.
10. Given the user taps a different character segment pill in MemoriesView, then the selected indicator animates smoothly to the new position (matchedGeometryEffect).
11. Given the Profile screen is loading, when the API call is in flight, then shimmer skeleton placeholders are shown instead of a centered spinner.
12. Given the user saves a profile change (name, timezone, language), then a success haptic fires and a brief visual success indicator appears.
13. Given the user pulls down on the Profile tab, then a pull-to-refresh indicator appears and the profile reloads.
14. Given the user switches tabs in MainTabView, then a selection haptic fires on each tab change.
15. Given the tab bar is visible, then it has a subtle top shadow instead of the default system separator.
16. Given the user taps Sign In or Sign Up on auth screens, then the button scales on press using ScaleButtonStyle.
17. Given an auth error occurs, then an error haptic fires alongside the existing shake animation.
18. Given the TimezonePickerSheet is presented, then it shows a drag indicator at the top.

---

## 9. File Manifest

```
iOS:
  CREATE ios/Ember/Core/Extensions/View+EmberShadow.swift
  CREATE ios/Ember/Core/Components/ShimmerView.swift
  CREATE ios/Ember/Core/Extensions/ButtonStyle+Ember.swift
  MODIFY ios/Ember/Features/Home/HomeView.swift
  MODIFY ios/Ember/Features/Home/CharacterCardView.swift
  MODIFY ios/Ember/Features/Home/DailySummaryCard.swift
  MODIFY ios/Ember/Features/Chat/ChatView.swift
  MODIFY ios/Ember/Features/Chat/ChatInputBar.swift
  MODIFY ios/Ember/Features/Chat/MessageBubbleView.swift
  MODIFY ios/Ember/Features/Memories/MemoriesView.swift
  MODIFY ios/Ember/Features/Memories/MemoryRowView.swift
  MODIFY ios/Ember/Features/Memories/MemoriesViewModel.swift
  MODIFY ios/Ember/Features/Profile/ProfileView.swift
  MODIFY ios/Ember/Features/Profile/ProfileViewModel.swift
  MODIFY ios/Ember/Features/Profile/TimezonePickerSheet.swift
  MODIFY ios/Ember/App/MainTabView.swift
  MODIFY ios/Ember/Features/Auth/LoginView.swift
  MODIFY ios/Ember/Features/Auth/SignUpView.swift
  MODIFY ios/Ember/Features/Auth/AuthViewModel.swift
  CREATE ios/EmberTests/Core/Components/ShimmerViewTests.swift
  CREATE ios/EmberTests/Core/Extensions/ScaleButtonStyleTests.swift
  CREATE ios/EmberTests/Core/Extensions/ViewEmberShadowTests.swift

Shared:
  CREATE shared/feature-specs/ios-design-polish.md (this file)
  CREATE docs/pipeline/ios-design-polish-architect.handoff.md
```
