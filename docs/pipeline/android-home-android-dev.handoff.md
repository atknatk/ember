# Android Dev Handoff: Android Home Screen

**Date**: 2026-03-13
**Agent**: android-dev
**Status**: COMPLETE

## Implemented Files
- `android/app/src/main/java/ai/ember/app/features/home/HomeScreen.kt`
- `android/app/src/main/java/ai/ember/app/features/home/HomeViewModel.kt`
- `android/app/src/main/java/ai/ember/app/features/home/HomeUiState.kt`
- `android/app/src/main/java/ai/ember/app/features/home/HomeRepository.kt`
- `android/app/src/main/java/ai/ember/app/features/home/CharacterApi.kt`
- `android/app/src/main/java/ai/ember/app/features/home/HomeModule.kt`
- `android/app/src/main/java/ai/ember/app/features/home/UnreadTracker.kt`
- `android/app/src/main/java/ai/ember/app/core/models/CharacterModels.kt`
- `android/app/src/main/java/ai/ember/app/core/models/MessageModels.kt`

## Modified Files
- `android/app/src/main/java/ai/ember/app/core/auth/TokenManager.kt` -- Added `saveUserName()` and `getUserName()`
- `android/app/src/main/java/ai/ember/app/core/auth/AuthRepository.kt` -- Stores user name on sign-in/sign-up, added `getUserName()`
- `android/app/src/main/java/ai/ember/app/core/navigation/Screen.kt` -- Added `Chat` and `CreateCharacter` routes
- `android/app/src/main/java/ai/ember/app/core/navigation/EmberNavHost.kt` -- Connected HomeScreen navigation, added placeholder routes
- `android/app/src/main/res/values/strings.xml` -- Added home screen string resources

## Test Files
- `android/app/src/test/java/ai/ember/app/features/home/HomeViewModelTest.kt`
- `android/app/src/test/java/ai/ember/app/features/home/HomeRepositoryTest.kt`

## Screens Implemented
- Home screen: Character grid with greeting header, daily summary card, pull-to-refresh, empty/loading/error states

## strings.xml Keys Added
- `home_characters_section`: "Your Characters"
- `home_add_character`: "Add Character"
- `home_no_messages_yet`: "No messages yet"
- `home_empty_title`: "No characters yet"
- `home_empty_subtitle`: "Start chatting by adding your first character"
- `home_daily_summary_placeholder`: "Start a conversation with your companion"
- `home_daily_summary_a11y`: "Daily summary from %1$s: %2$s"
- `home_daily_summary_empty_a11y`: "Daily summary: start a conversation"
- `home_retry`: "Retry"

## Deviations from Spec
- Added `UnreadTracker` as a separate injectable class (not static methods) for better testability and DI
- Added `Empty` state to HomeUiState (separate from Success with empty list) for clearer empty state handling
- Added user name storage to `TokenManager`/`AuthRepository` since Android did not previously persist the user's name

## Notes for Android Tester
- ViewModel depends on `HomeRepository`, `AuthRepository`, `UnreadTracker` -- use MockK `mockk<>()`
- `HomeRepository.getLastMessages()` uses `coroutineScope` + `async` for parallel fetching -- test with `runTest`
- `UnreadTracker` uses `SharedPreferences` -- test with Robolectric or mock the context
- `HomeUiState` has 4 variants: `Loading`, `Success`, `Empty`, `Error`
- Pull-to-refresh preserves existing data -- on refresh failure, previous Success state is kept
- Turbine is configured in project -- use `.test { }` for StateFlow assertions
- Navigation uses `Screen.Chat.createRoute(characterId, characterName)` -- verify URL encoding for names with special characters
