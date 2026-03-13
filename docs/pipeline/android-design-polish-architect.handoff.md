# Architect Handoff: Android Design Polish

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## Summary

Designed a visual polish pass for all Android screens matching the iOS P03-10 design polish. Seven categories of improvements: shimmer loading skeletons, card shadows, scale button effects, pull-to-refresh, micro-interactions, bottom bar polish, and haptic consistency.

## Spec Created

- `shared/feature-specs/android-design-polish.md`

## Key Decisions

- Shimmer animation duration: 1200ms (matching iOS)
- Card shadow: 8dp elevation, black 30% opacity
- Scale press: 0.85 target with spring damping 0.6
- Unread dot pulse: 1.0 to 1.15 scale, 800ms cycle
- Greeting animation: 400ms fade-in + slide-up

## Dependencies

- P04-05 (android-home), P04-06 (android-chat), P04-07 (android-memory-list), P04-09 (android-profile-screen)

## Notes for Android Dev

- All changes are view-layer only -- no ViewModel or data layer modifications
- Reusable components go in `core/ui/components/`
- Match existing code patterns (EmberShapes, EmberSpacing, EmberColors)
- Use `InteractionSource.collectIsPressedAsState()` for Material 3 Button scale animation
