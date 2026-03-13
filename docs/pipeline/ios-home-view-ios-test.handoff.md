# iOS Test Handoff — ios-home-view

- **status**: COMPLETE
- **feature**: P03-06 — ios-home-view
- **layer**: ios
- **agent**: ios-tester
- **date**: 2026-03-13

## Test Summary

- **test_count**: 44 (11 original + 33 extended)
- **framework**: Swift Testing (@Test, #expect)
- **files**:
  - `ios/EmberTests/Features/Home/HomeViewModelTests.swift` — 11 tests (written by ios-dev, not modified)
  - `ios/EmberTests/Features/Home/HomeViewModelExtendedTests.swift` — 33 tests (written by ios-tester)

## Coverage

| Area | Tests |
|------|-------|
| `loadCharacters()` success / error / empty list | 7 |
| `defaultCharacter` computed property | 4 |
| `defaultCharacterLastMessage` computed property | 4 |
| `greeting(for:)` — all boundary hours (5, 11, 12, 16, 17, 0, 4, 23) | 11 |
| `templateIcon(for:)` — all 6 templates + edge cases | 4 |
| `hasUnreadMessages(for:)` — no message / never opened / read / unread | 4 |
| `markCharacterAsOpened` / `lastOpenedDate` | 4 |
| `isLoading` / `isRefreshing` state transitions | 3 |
| `userName` from UserDefaults | 2 |
| Partial `lastMessages` fetch failure (silent per spec) | 2 |
| API request call count verification | 2 |
| Multiple / zero default characters | 2 |

## pbxproj Changes

- `PBXFileReference`: `043381FB0511D95E4E489A23`
- `PBXBuildFile`: `22C6CD510E9D51FF0842E0E0`
- Home test group (`D84181B6718F06335261CCAC`): file added as child
- Sources build phase (`91FC9734A1965EA61C9B43FF`): build file added

## Notes

- Tests use protocol-based fakes (local `MockHomeAPIClient` defined in each test file)
- Swift Testing framework used (consistent with P03-01 through P03-05 patterns)
- "No such module 'Testing'" SourceKit warning is expected — resolves during xcodebuild
- UserDefaults tests use UUID-based character IDs to avoid cross-test state pollution
- Partial `lastMessages` fetch failures are verified to be swallowed (not propagated to `errorMessage`) per spec Section 5.5
- `markCharacterAsOpened` + `hasUnreadMessages` round-trip verified end-to-end

## Issues Found

None. Implementation matches the spec exactly.
