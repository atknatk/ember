# Architect Handoff: Android Chat

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## Spec Location
`shared/feature-specs/android-chat.md`

## Summary
Designed the Android chat screen with OkHttp SSE streaming, message bubbles, typing indicator, cursor-based pagination, and date separators. Follows existing patterns from ios-chat-view spec adapted for Kotlin/Compose.

## Key Decisions
- Reuse existing `Screen.Chat` route with characterId and characterName arguments
- SSE via OkHttp EventSource + callbackFlow (not Retrofit)
- Cursor-based pagination matching backend contract
- ChatMessage model separate from MessagePreview (richer fields)
- Long-press copy via combinedClickable + DropdownMenu
- Photo and voice buttons visible but disabled (Phase 5)
