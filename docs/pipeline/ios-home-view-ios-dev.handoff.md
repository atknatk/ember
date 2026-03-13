# iOS Dev Handoff: iOS Home View

**Date**: 2026-03-13
**Agent**: ios-dev
**Status**: COMPLETE

## Implemented Files

### Created
- `ios/Ember/Core/Models/CharacterModels.swift` -- `Character` and `CharacterListResponse` Codable models
- `ios/Ember/Core/Models/MessageModels.swift` -- `MessagePreview` and `MessageListResponse` Codable models
- `ios/Ember/Features/Home/HomeView.swift` -- Main HomeView with greeting header, daily summary, character grid, empty/loading/error states
- `ios/Ember/Features/Home/HomeViewModel.swift` -- `@Observable` ViewModel with character loading, last message fetching, local unread tracking, greeting/template helpers
- `ios/Ember/Features/Home/DailySummaryCard.swift` -- Daily summary card showing default character's last AI message
- `ios/Ember/Features/Home/CharacterCardView.swift` -- Character card and Add Character card components
- `ios/EmberTests/Features/Home/HomeViewModelTests.swift` -- 11 test cases using Swift Testing

### Modified
- `ios/Ember/App/MainTabView.swift` -- Replaced `HomePlaceholderView()` with `HomeView()`, added `.createCharacter` route case
- `ios/Ember/App/AppRouter.swift` -- Added `case createCharacter` to `Route` enum
- `ios/Ember/Core/Extensions/EmberSymbol.swift` -- Added 7 template icon constants (`templateCompanion`, `templateEnglishTeacher`, `templateTherapist`, `templateFitnessCoach`, `templateCareerCoach`, `templateCustom`, `addCharacter`)

### Deleted
- `ios/Ember/Features/Home/HomePlaceholderView.swift` -- Replaced by production `HomeView`

## Screens Implemented
- **HomeView**: Time-of-day greeting header, daily summary card, two-column character grid with avatar icons, name, last message preview, relative time badge, unread dot, "+ Add Character" card, pull-to-refresh, loading/empty/error states

## Deviations from Spec
- None. All spec requirements implemented as designed.

## Notes for iOS Tester

### Mock Patterns
- `HomeViewModel` accepts `APIClientProtocol` via constructor injection
- Tests use a local `MockHomeAPIClient` (defined in the test file) that routes `listCharacters` and `listMessages` endpoints separately
- The mock supports `characterListResponse`, `messageListResponses` (keyed by character ID), and `requestError`

### What to Test
- `loadCharacters()` success path: verify `characters` populated, `lastMessages` populated, `isLoading` false
- `loadCharacters()` error path: verify `errorMessage` set, `characters` empty
- Pull-to-refresh: verify `isRefreshing` is used (not `isLoading`) when characters already exist, existing data preserved
- `defaultCharacter` computed property: first character with `isDefault == true`
- `defaultCharacterLastMessage`: lookup in `lastMessages` dict by default character ID
- `greeting(for:)`: "Good morning" (5-11), "Good afternoon" (12-16), "Good evening" (17-4)
- `templateIcon(for:)`: all 6 templates + unknown default
- Local unread tracking: `markCharacterAsOpened()` stores date in UserDefaults, `hasUnreadMessages()` compares `lastMessageAt` against stored date
- Accessibility: verify all cards, buttons, and the settings toolbar item have `accessibilityLabel`
- Haptics: `HapticManager.selection()` on character card tap and daily summary tap, `HapticManager.impact(.light)` on Add Character tap
