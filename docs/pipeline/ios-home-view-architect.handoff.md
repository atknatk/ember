# Architect Handoff: iOS Home View

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## What Was Designed

The HomeView screen for iOS, replacing the placeholder from P03-01. It features a time-of-day greeting header, a daily summary card showing the default character's last AI message, a two-column LazyVGrid of character cards with avatar icons, name, message preview, time badge, and unread dot, plus a "+ Add Character" card at the end. An @Observable HomeViewModel manages character fetching, last message preview loading, pull-to-refresh, and local unread tracking.

## Key Decisions

- **N+1 message preview fetching**: Each character's last message is fetched individually via `GET /characters/:id/messages?limit=1`. This creates N+1 requests but is acceptable for Phase 3 where users have 1-6 characters. A future backend enhancement could add `last_message_content` to the character list response to eliminate these extra calls.
- **Local unread tracking via UserDefaults**: Rather than implementing server-side read receipts, unread state is tracked by comparing `lastMessageAt` from the API against a locally persisted `lastOpenedAt` date per character. Simple, offline-capable, and sufficient for Phase 3.
- **Template-to-icon mapping as static function**: `HomeViewModel.templateIcon(for:)` is a static function so both the ViewModel tests and views can use it without duplication. The icon constants are also added to `EmberSymbol` for consistency.
- **AppRouter.Route.createCharacter added as placeholder**: The "+ Add Character" card pushes a new route rather than showing an alert, so navigation infrastructure is ready for when the character creation UI is built.
- **No new API endpoints**: All data comes from existing `GET /characters` and `GET /characters/:id/messages?limit=1` endpoints.
- **MessageModels.swift as a new file**: Message-related models (`MessagePreview`, `MessageListResponse`) are placed in their own file under Core/Models since they will be reused by the ChatView feature later.

## Spec Location

`shared/feature-specs/ios-home-view.md`

## Assumptions Made

- The user's display name is available from `UserDefaults` (stored during login/registration by `AuthViewModel` from P03-05). The spec references `viewModel.userName` which reads from this stored value.
- The backend's `GET /characters` response is already sorted by `last_message_at DESC NULLS LAST, created_at DESC` as implemented in `CharacterService.list_characters()`.
- `HomePlaceholderView.swift` can be safely deleted since it is only referenced from `MainTabView.swift`.

## Dependencies

- Requires: P03-04 (ios-onboarding), P03-03 (ios-cognito-auth), P03-02 (ios-network-layer), P03-01 (ios-scaffold), P01-05 (character-crud backend)
- Blocks: ios-dev (implements this spec)

## Next Steps

ios-dev should read the spec and implement. No backend-dev or android-dev work is needed for this feature.
