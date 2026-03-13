# Architect Handoff: iOS Design Polish

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## What Was Designed

A comprehensive visual polish pass across all existing iOS screens (Home, Chat, Memories, Profile, Auth, TabBar). The spec covers seven categories: card shadows with reusable ViewModifiers, shimmer skeleton loading states replacing plain spinners, consistent pull-to-refresh across all tabs, micro-interaction animations (send button scale, message slide-in, unread dot pulse, segment pill sliding indicator), haptic feedback consistency audit and additions, tab bar shadow polish, and auth screen button animation.

## Key Decisions

- **Shimmer over Lottie for skeletons**: Shimmer placeholders are implemented as lightweight SwiftUI views (gradient sweep animation) rather than Lottie files. This avoids adding animation assets for every skeleton state and keeps the binary size small. Lottie remains in use only for onboarding (already implemented in WelcomeView).
- **matchedGeometryEffect for segment pills**: The Memories character picker will use `matchedGeometryEffect` to animate the selected pill indicator sliding between pills. This provides a premium feel without complex geometry calculations.
- **Shadow values derived from design system**: The design system (`docs/14-tasarim.md`) does not specify exact shadow values, so shadows use `Color.black.opacity(0.3), radius 8, y 4` for cards and `opacity 0.15, radius 4, y 2` for smaller elements. These values create visible depth on the dark background without appearing harsh.
- **No ViewModel logic changes**: All modifications are view-layer only (animations, modifiers, haptics). ViewModels gain at most a `@State` flag for animation triggers. No API calls, data flow, or business logic is altered.
- **Input bar shadow replaces divider**: The 1px `Divider()` at the top of ChatInputBar is replaced with a shadow on the container. This is a common premium chat app pattern (iMessage, WhatsApp) that feels more polished.

## Spec Location

`shared/feature-specs/ios-design-polish.md`

## Assumptions Made

- The existing `ProgressView` loading states in all views can be replaced without affecting ViewModel state transitions (the `isLoading` flag behavior remains unchanged).
- `UITabBarAppearance.shadowColor` is sufficient for the tab bar top shadow effect (no custom shadow layer needed).
- `matchedGeometryEffect` works correctly inside a `ScrollView(.horizontal)` for the segment pills in MemoriesView.
- The Auth error shake animation in LoginView does not already include haptic feedback (code review shows it uses `DispatchQueue` for the shake offset but no `HapticManager` call).

## Dependencies

- Requires: P03-07 (ios-chat-view), P03-08 (ios-memory-list), P03-09 (ios-profile-view) -- all confirmed complete.
- Blocks: ios-dev (implements this spec).

## Next Steps

ios-dev should read the spec and implement all changes. This is a single-platform (iOS) feature with no backend or Android work. The ios-tester should then verify the 18 acceptance criteria, focusing on visual and haptic behavior on a physical device.
