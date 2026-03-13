---
name: ios-home-view test patterns
description: Patterns established during P03-06 iOS Home View testing — MockHomeAPIClient with per-endpoint routing, UserDefaults isolation, pbxproj group IDs for Home tests
type: project
---

The home view feature (P03-06) uses a local `MockHomeAPIClient` defined inside each test file (not the shared `MockAPIClient`). This mock routes `listCharacters` and `listMessages` endpoints separately via a `switch endpoint` on `APIEndpoint`.

Key mock properties:
- `characterListResponse: CharacterListResponse` — returned for `.listCharacters`
- `messageListResponses: [String: MessageListResponse]` — keyed by characterId, returned for `.listMessages`
- `requestError: Error?` — throws on all calls
- `messageRequestError: Error?` (extended mock only) — throws only on `.listMessages` calls

The ios-dev wrote `HomeViewModelTests.swift` (11 tests) as part of the feature. The ios-tester's job was to write `HomeViewModelExtendedTests.swift` (33 additional tests).

Key test patterns for home view:
- `hasUnreadMessages` and `markCharacterAsOpened` write to `UserDefaults` — always use UUID-based character IDs to avoid cross-test pollution
- Partial `lastMessages` fetch failure is SILENT per spec (only `listCharacters` failure sets `errorMessage`)
- `greeting(for:)` boundaries: 5-11 = morning, 12-16 = afternoon, 17-4 = evening
- `templateIcon(for:)` is case-sensitive — "Companion" → "person.fill" (default)
- `defaultCharacterLastMessage` returns nil when no default character, even if `lastMessages` is populated
- API call count: 1 (listCharacters) + N (listMessages, one per character) = N+1 total

pbxproj IDs for Home tests:
- Home test group: `D84181B6718F06335261CCAC`
- Sources build phase: `91FC9734A1965EA61C9B43FF`
- Extended tests fileRef: `043381FB0511D95E4E489A23`
- Extended tests buildFile: `22C6CD510E9D51FF0842E0E0`

**Why:** The linter auto-runs xcodegen when test files are added — this regenerates the pbxproj with new UUIDs. My manually inserted UUIDs were replaced. The final UUIDs in the committed pbxproj are the xcodegen-generated ones.

**How to apply:** When adding new test files to the ios target, add the Swift file to disk first, then add to pbxproj manually. The linter will regenerate via xcodegen — check `git log` to confirm the final UUIDs. Do not rely on manually-generated UUIDs persisting.
