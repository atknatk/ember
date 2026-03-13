# Feature Spec: P04-04 -- Android Home Screen

**Feature ID**: P04-04
**Phase**: 4
**Layer**: android
**GitHub Issue**: #31
**Date**: 2026-03-13
**Author**: architect

---

## 1. Overview

### What This Feature Does

Replaces the placeholder HomeScreen (from P04-01) with the production Home screen. The Home screen is the first screen the user sees after authentication and onboarding. It contains:

1. **Greeting header** -- A time-of-day greeting ("Good morning, Alex") with the current date, using the user's name from stored preferences.

2. **Daily summary card** -- A highlighted card at the top showing the last AI message from the user's default character (the General Friend, where `is_default == true`). Tapping navigates to that character's chat.

3. **Character grid** -- A `LazyVerticalGrid` (2 columns) displaying all active characters as cards. Each card shows:
   - Avatar circle with a template-specific Material Icon
   - Character name
   - Last message preview (truncated to 2 lines)
   - Unread dot (orange accent) when `last_message_at` is newer than local last-opened timestamp

4. **"+ Add Character" card** -- A bordered card at the end of the grid navigating to character creation (placeholder for now).

5. **Pull-to-refresh** -- User can pull down to reload characters from the API. Existing data is preserved during refresh.

### Dependencies

- **P04-01** (android-scaffold) -- Provides navigation, theme, bottom bar
- **P04-03** (android-onboarding) -- Onboarding flow gating
- **P01-05** (character-crud, backend) -- `GET /api/v1/characters`

### What This Feature Does NOT Do

- Does not implement ChatScreen. Tapping a character navigates to a placeholder.
- Does not implement character creation UI. The "+ Add Character" card navigates to a placeholder.
- Does not implement server-side read receipts. Uses local heuristic via SharedPreferences.

---

## 2. API Endpoints

### GET /api/v1/characters

Returns the user's active characters sorted by `last_message_at DESC`.

### GET /api/v1/characters/:id/messages?limit=1

Returns the most recent message for each character (used for preview text).

---

## 3. Android Implementation

### Files

| File | Purpose |
|------|---------|
| `features/home/HomeScreen.kt` | Composable screen with grid, greeting, summary card |
| `features/home/HomeViewModel.kt` | StateFlow, character loading, greeting, template icons |
| `features/home/HomeUiState.kt` | Sealed UI state: Loading, Success, Empty, Error |
| `features/home/HomeRepository.kt` | API calls via Retrofit, parallel message fetching |
| `features/home/CharacterApi.kt` | Retrofit interface |
| `features/home/HomeModule.kt` | Hilt module for CharacterApi |
| `features/home/UnreadTracker.kt` | Local unread tracking via SharedPreferences |
| `core/models/CharacterModels.kt` | Character, CharacterListResponse data classes |
| `core/models/MessageModels.kt` | MessagePreview, MessageListResponse data classes |

### Navigation

- `Screen.Chat` -- New route `chat/{characterId}/{characterName}` (placeholder)
- `Screen.CreateCharacter` -- New route `create_character` (placeholder)

---

## 4. Acceptance Criteria

1. Home screen displays time-appropriate greeting with user's name
2. Character grid shows all active characters in 2-column layout
3. Daily summary card shows default character's last AI message
4. Tapping character card navigates to chat (placeholder)
5. Unread dot shows on characters with messages newer than last opened
6. Tapping character clears unread dot
7. Pull-to-refresh reloads data, preserves existing content
8. Empty state shown when no characters exist
9. Error state shown with retry button on API failure
10. All strings from strings.xml, no hardcoded text
11. Accessibility: contentDescription on all interactive elements
12. Haptic feedback on card taps
