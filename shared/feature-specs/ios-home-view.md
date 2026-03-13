# Feature Spec: P03-06 -- iOS Home View

**Feature ID**: P03-06
**Phase**: 3
**Layer**: ios
**GitHub Issue**: #22
**Date**: 2026-03-13
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature replaces the placeholder `HomePlaceholderView` (from P03-01) with the production HomeView screen. HomeView is the first screen the user sees after authentication and onboarding. It contains:

1. **Greeting header** -- A time-of-day greeting ("Good morning, Alex") with the current date, using the user's name from `UserResponse`.

2. **Daily summary card** -- A highlighted card at the top showing the last AI message from the user's default character (the General Friend, where `is_default == true`). This gives the user a quick daily touchpoint without needing to open the chat.

3. **Character grid** -- A `LazyVGrid` displaying all of the user's active characters as cards. Each card shows:
   - Avatar circle with a role icon overlay (SF Symbol based on `template`)
   - Character name
   - Last message preview (truncated)
   - Relative time badge (e.g., "2h ago", "Yesterday")
   - Unread badge for proactive messages (orange dot, visible when `last_message_at` is newer than the last time the user opened that character's chat)

4. **"+ Add Character" card** -- A special card at the end of the grid that navigates to the character creation flow (placeholder destination for now, since character creation UI is a separate feature).

5. **Pull-to-refresh** -- The user can pull down to reload the character list from the API.

Tapping a character card pushes `ChatView` via `AppRouter.push(.chat(characterId:))`. This is a full-screen NavigationStack push, not a modal. It does not create a new conversation -- it opens the existing single continuous conversation for that character.

### Why It Exists

HomeView is the central hub of the Ember app. It surfaces the user's AI companions in a scannable grid, making it easy to jump into any conversation. The daily summary card re-engages users by showing the default character's latest message without requiring them to open a chat. The unread badge for proactive messages ensures that background AI-generated messages are visible and discoverable.

### Dependencies

- **P03-04** (ios-onboarding) -- The onboarding flow must complete before HomeView is shown. `EmberApp.swift` already gates HomeView behind `hasCompletedOnboarding`.
- **P03-03** (ios-cognito-auth) -- Provides `AuthService` with `getAccessToken()` for authenticated API calls.
- **P03-02** (ios-network-layer) -- Provides `APIClient` with `request<T>(endpoint:body:responseType:)`, `APIEndpoint.listCharacters`, `APIError` types.
- **P03-01** (ios-scaffold) -- Provides `AppContainer`, `AppRouter`, design system (`Color+Ember`, `Font+Ember`, `CGFloat+Ember`), `HapticManager`, `EmberSymbol`, `MainTabView`.
- **P01-05** (character-crud, backend) -- Provides `GET /api/v1/characters` returning `CharacterListResponse`.

### What This Feature Does NOT Do

- It does not implement the ChatView screen. Tapping a character card pushes to `AppRouter.Route.chat(characterId:)`, which currently renders a placeholder. ChatView is a separate feature.
- It does not implement the character creation flow. The "+ Add Character" card will push to a placeholder screen or display a "Coming soon" alert until the character creation UI feature is implemented.
- It does not change any backend code. The `GET /api/v1/characters` endpoint already exists and is fully functional.
- It does not implement real unread tracking with server-side read receipts. The unread badge uses a local heuristic: comparing `lastMessageAt` from the API against a locally persisted `lastOpenedAt` timestamp per character stored in `UserDefaults`.
- It does not fetch the full last message content for each character. It uses `last_message_at` from the character list response for the time badge. The "last message preview" text requires fetching the most recent message per character, which this feature handles with a lightweight secondary fetch (see Section 5 for details).

---

## 2. Data Models

No database changes. This is an iOS-only feature.

### Swift Models

#### Character (new model file)

Maps to the backend's `CharacterListItem` Pydantic schema (see `backend/app/schemas/character.py`).

```
struct Character: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let template: String
    let description: String?
    let avatarStyle: String
    let isDefault: Bool
    let lastMessageAt: Date?
    let createdAt: Date
}
```

#### CharacterListResponse (new model)

Maps to the backend's `CharacterListResponse` Pydantic schema.

```
struct CharacterListResponse: Codable {
    let characters: [Character]
}
```

#### LastMessagePreview (local-only model for the preview fetch)

Used to represent the most recent message for a character, fetched from `GET /characters/:id/messages?limit=1`.

```
struct MessagePreview: Codable, Identifiable {
    let id: String
    let role: String
    let content: String
    let createdAt: Date
}

struct MessageListResponse: Codable {
    let items: [MessagePreview]
    let nextCursor: String?
    let hasMore: Bool
}
```

These structs are decoded using `JSONDecoder.ember` which converts `snake_case` keys to `camelCase` properties automatically.

---

## 3. API Endpoints

No new endpoints. This feature calls existing backend endpoints.

### GET /api/v1/characters

```
GET /api/v1/characters
Auth: Bearer JWT required
Request headers: none (beyond Authorization)
Request body: none

Response 200:
{
    "characters": [
        {
            "id": "uuid-string",
            "name": "Luna",
            "template": "companion",
            "description": null,
            "avatar_style": "default",
            "is_default": true,
            "last_message_at": "2026-03-12T14:30:00Z",
            "created_at": "2026-02-23T10:00:00Z"
        }
    ]
}

Response 401: { "detail": "..." } (unauthorized)
Response 500: { "detail": "..." } (server error)
```

The `APIEndpoint.listCharacters` case already exists in `ios/Ember/Core/Network/APIEndpoint.swift` (path: `/api/v1/characters`, method: GET, requiresAuth: true, no query items).

### GET /api/v1/characters/:id/messages?limit=1

Used to fetch the most recent message for each character to show a preview snippet. This uses the existing `APIEndpoint.listMessages(characterId:cursor:limit:)` case.

```
GET /api/v1/characters/:id/messages?limit=1
Auth: Bearer JWT required

Response 200:
{
    "items": [
        {
            "id": "uuid-string",
            "role": "assistant",
            "content": "Good morning! How are you feeling today?",
            "media_url": null,
            "metadata": null,
            "created_at": "2026-03-12T14:30:00Z"
        }
    ],
    "next_cursor": "...",
    "has_more": true
}
```

---

## 4. Backend Logic

Not applicable. This is an iOS-only feature. The backend endpoints are fully implemented in `backend/app/routes/characters.py` and `backend/app/routes/chat.py`.

---

## 5. iOS Screens and Components

### 5.1 HomeView

**File path**: `ios/Ember/Features/Home/HomeView.swift`

**Replaces**: `ios/Ember/Features/Home/HomePlaceholderView.swift` (this file is deleted)

**Navigation**: Shown as the first tab in `MainTabView`. The user arrives here after completing onboarding or on every app launch if already onboarded. The user can navigate to ChatView by tapping a character card, or to character creation by tapping "+ Add Character".

**View structure**:

```
ScrollView {
    VStack(spacing: emberSpacing24) {
        GreetingHeaderView(userName:)
        DailySummaryCard(message:characterName:onTap:)
        CharacterGridView(
            characters:
            lastMessages:
            lastOpenedDates:
            onCharacterTap:
            onAddCharacterTap:
        )
    }
    .padding(.horizontal, emberSpacing20)
}
.refreshable { await viewModel.loadCharacters() }
.background(Color.emberBackground.ignoresSafeArea())
.navigationBarTitleDisplayMode(.inline)
.toolbar {
    ToolbarItem(placement: .navigationBarTrailing) {
        Button { router.push(.settings) } label: {
            Image(systemName: EmberSymbol.settings)
                .symbolRenderingMode(.hierarchical)
                .foregroundStyle(Color.emberTextSecondary)
        }
        .accessibilityLabel("Settings")
    }
}
.task { await viewModel.loadCharacters() }
.alert(...)
```

**State binding**: `@State private var viewModel: HomeViewModel`

**Environment**: `@Environment(AppRouter.self) private var router`

**ViewModel initialization**: Initialized in `init()` via `_viewModel = State(initialValue: HomeViewModel(apiClient: ...))`. Alternatively, initialized in `.onAppear` with the container's `apiClient` via `@Environment(AppContainer.self)`.

**Loading state**: When `viewModel.isLoading` is true and `viewModel.characters` is empty, show a centered `ProgressView` with `.tint(Color.emberPrimary)`.

**Empty state**: When `viewModel.isLoading` is false and `viewModel.characters` is empty, show a `VStack` with an SF Symbol (`person.3.fill`), a headline "No characters yet", body text "Start chatting by adding your first character", and a primary button "Add Character".

**Error state**: When `viewModel.errorMessage` is not nil, show a `.alert("Error", ...)` with the message and an "OK" dismiss button plus a "Retry" button that calls `Task { await viewModel.loadCharacters() }`.

### 5.2 GreetingHeaderView

**File path**: inline in `ios/Ember/Features/Home/HomeView.swift` or extracted as a private subview

**UI elements**:

- Greeting text: "Good morning/afternoon/evening, {name}" in `.emberTitle` font, `Color.emberTextPrimary`. The greeting changes based on `Calendar.current.component(.hour, from: Date())`: 5-11 = "Good morning", 12-16 = "Good afternoon", 17-4 = "Good evening".
- Date text: formatted as "EEEE, d MMMM" (e.g., "Thursday, 13 March") in `.emberSecondary` font, `Color.emberTextSecondary`.

**Accessibility**: The greeting and date are combined into a single accessibility element.

### 5.3 DailySummaryCard

**File path**: `ios/Ember/Features/Home/DailySummaryCard.swift`

**Purpose**: Displays the last AI message from the user's default character (General Friend). Tapping the card opens that character's chat.

**UI elements**:

- Container: `RoundedRectangle(cornerRadius: .emberRadius20)` filled with a subtle gradient from `Color.emberSurface2` to `Color.emberSurface3`.
- Left edge accent: A 3pt-wide vertical bar in `Color.emberPrimary` along the leading edge (inset via overlay or clip shape).
- Character name label: The default character's name in `.emberCaption` font, `Color.emberTextSecondary`.
- Message preview: The last AI message content, truncated to 3 lines, in `.emberBody` font, `Color.emberTextPrimary`.
- Time label: Relative time ("2h ago") in `.emberMicro` font, `Color.emberTextSecondary`, aligned trailing bottom.
- If no default character or no messages exist, show a placeholder: "Start a conversation with your companion" in `.emberBody` font, `Color.emberTextSecondary`.

**Tap action**: Calls `onTap` closure which triggers `router.push(.chat(characterId: defaultCharacter.id))`.

**Haptics**: `HapticManager.selection()` on tap.

**Accessibility**: `accessibilityLabel("Daily summary from {characterName}: {messagePreview}")`. `accessibilityHint("Opens chat with {characterName}")`.

### 5.4 CharacterGridView and CharacterCardView

**File path**: `ios/Ember/Features/Home/CharacterCardView.swift`

**Grid layout**: `LazyVGrid(columns: [GridItem(.flexible(), spacing: .emberSpacing16), GridItem(.flexible(), spacing: .emberSpacing16)], spacing: .emberSpacing16)` -- two columns.

**CharacterCardView UI elements**:

- Container: `RoundedRectangle(cornerRadius: .emberRadius20)` filled with `Color.emberSurface2`. Fixed height not set -- height is determined by content.
- Avatar circle: 56pt circle filled with a color derived from `avatarStyle` (or `Color.emberSurface3` as fallback), centered at the top of the card. Contains an SF Symbol based on `template`:
  - `companion` -> `person.fill`
  - `english_teacher` -> `book.fill`
  - `therapist` -> `heart.text.square.fill`
  - `fitness_coach` -> `figure.run`
  - `career_coach` -> `briefcase.fill`
  - `custom` -> `sparkles`
  The icon is rendered in `Color.emberPrimary`, 22pt size.
- Character name: `.emberHeadline` font, `Color.emberTextPrimary`, centered below avatar, 1 line max.
- Last message preview: `.emberSecondary` font, `Color.emberTextSecondary`, centered, 2 line max with truncation.
- Time badge: `.emberMicro` font, `Color.emberTextSecondary`, relative time string.
- Unread dot: A small (8pt) orange circle (`Color.emberAccent`) positioned at the top-right corner of the card, visible only when the character has a message newer than the local `lastOpenedAt` for that character. This uses `@AppStorage` or `UserDefaults` to persist `lastOpenedAt` per character ID.

**"+ Add Character" card**:

- Same dimensions as a character card.
- Dashed border: `RoundedRectangle(cornerRadius: .emberRadius20).strokeBorder(Color.emberTextDisabled, style: StrokeStyle(lineWidth: 1.5, dash: [8]))`.
- Center content: SF Symbol `plus.circle.fill` in `Color.emberPrimary` (28pt), text "Add Character" in `.emberCaption` font, `Color.emberTextSecondary`.
- Tap: For now, does nothing actionable (character creation is a separate feature). Implementation options: (a) push a placeholder route, or (b) show a brief toast/alert "Coming soon". The spec recommends option (a): add `AppRouter.Route.createCharacter` and push it, with `MainTabView.destinationView` rendering a `Text("Create Character -- Coming Soon")` placeholder.

**Tap action on character card**: `router.push(.chat(characterId: character.id))`. On tap, also update `UserDefaults` with the current date as `lastOpenedAt` for that character, clearing the unread dot.

**Haptics**: `HapticManager.selection()` on character card tap. `HapticManager.impact(.light)` on "+ Add Character" tap.

**Accessibility**:
- Character card: `accessibilityLabel("{name}, {template} character. Last message: {preview}. {timeAgo}")`. If unread: append `", new message"`.
- "+ Add Character": `accessibilityLabel("Add a new character")`.

**Animation**: Cards appear with a staggered fade-in on initial load (`.transition(.opacity)` with `.animation(.easeIn(duration: 0.25).delay(Double(index) * 0.05))`). The unread dot uses a subtle scale-pop animation (`.transition(.scale.combined(with: .opacity))`).

### 5.5 HomeViewModel

**File path**: `ios/Ember/Features/Home/HomeViewModel.swift`

**Class definition**: `@Observable final class HomeViewModel`

**Properties**:

| Property | Type | Purpose |
|----------|------|---------|
| `characters` | `[Character]` | All active characters from the API |
| `lastMessages` | `[String: MessagePreview]` | Dictionary mapping character ID to their most recent message, for preview text |
| `isLoading` | `Bool` | True during the initial fetch |
| `isRefreshing` | `Bool` | True during pull-to-refresh (allows showing refresh indicator while keeping existing data visible) |
| `errorMessage` | `String?` | Non-nil when an error occurs |
| `userName` | `String` | User's display name, sourced from `UserDefaults` (stored at login/register by AuthViewModel) |

**Private properties**:

| Property | Type | Purpose |
|----------|------|---------|
| `apiClient` | `APIClientProtocol` | Injected network client |

**Constructor**: `init(apiClient: APIClientProtocol = APIClient.shared)`

**Methods**:

`func loadCharacters() async`

1. Set `isLoading = true` if `characters` is empty, otherwise set `isRefreshing = true`.
2. Clear `errorMessage`.
3. Call `apiClient.request(endpoint: .listCharacters, responseType: CharacterListResponse.self)`.
4. On success: set `characters` to the response's `characters` array (already sorted by the backend: `last_message_at DESC NULLS LAST, created_at DESC`).
5. After setting characters, fetch last message previews for each character in parallel using a `TaskGroup` or `async let` pattern. For each character, call `apiClient.request(endpoint: .listMessages(characterId: character.id, cursor: nil, limit: 1), responseType: MessageListResponse.self)`. Store the first item (if any) in `lastMessages[character.id]`.
6. On failure: set `errorMessage` to the localized error description.
7. Set `isLoading = false` and `isRefreshing = false`.

Note on performance: Fetching last messages for each character creates N+1 requests. For Phase 3 with a small number of characters (typically 1-6), this is acceptable. If this becomes a performance concern, the backend should add a `last_message_content` field to the `CharacterListItem` response in a future phase. The ViewModel already structures this as a dictionary lookup, so swapping to a single-response approach later requires only changing `loadCharacters()`.

**Computed properties**:

`var defaultCharacter: Character?` -- Returns the first character where `isDefault == true`.

`var defaultCharacterLastMessage: MessagePreview?` -- Returns `lastMessages[defaultCharacter?.id ?? ""]`.

**Helper functions**:

`static func templateIcon(for template: String) -> String` -- Returns the SF Symbol name for a given template string. This is a static function so it can be used from both the ViewModel and views without duplication.

```
companion -> "person.fill"
english_teacher -> "book.fill"
therapist -> "heart.text.square.fill"
fitness_coach -> "figure.run"
career_coach -> "briefcase.fill"
custom -> "sparkles"
default -> "person.fill"
```

`static func greeting(for date: Date = Date()) -> String` -- Returns "Good morning", "Good afternoon", or "Good evening" based on the hour.

### 5.6 Local Unread Tracking

Unread state is tracked locally using `UserDefaults` with a dictionary keyed by character ID. The value is the `Date` when the user last opened that character's chat.

**Key**: `"character_last_opened"` in `UserDefaults.standard`, storing `[String: Date]` (character ID to date).

**Read logic (in HomeView)**: For each character, compare `character.lastMessageAt` against the stored `lastOpenedAt` date. If `lastMessageAt` is newer (or no stored date exists for that character), show the unread dot.

**Write logic**: When the user taps a character card and navigates to chat, store `Date()` as `lastOpenedAt` for that character ID.

This is a simple local heuristic. Server-side read tracking is a future feature.

---

## 6. Android Screens and Components

Not applicable. This is an iOS-only feature (layer: ios).

---

## 7. Test Plan

### iOS Tests

#### HomeViewModelTests (Swift Testing)

**File path**: `ios/EmberTests/Features/Home/HomeViewModelTests.swift`

**Mock setup**: Use `MockAPIClient` (already exists in the test target from P03-02). Configure `MockAPIClient` to support returning `CharacterListResponse` and `MessageListResponse`.

**Test scenarios**:

1. **loadCharacters sets characters on success** -- Configure mock to return a list of 2 characters. Call `loadCharacters()`. Assert `characters.count == 2`, `isLoading == false`, `errorMessage == nil`.

2. **loadCharacters sets errorMessage on network failure** -- Configure mock to throw `APIError.networkError(...)`. Call `loadCharacters()`. Assert `characters` is empty, `errorMessage` is not nil, `isLoading == false`.

3. **loadCharacters sets errorMessage on server error** -- Configure mock to throw `APIError.serverError(statusCode: 500, detail: "Internal error")`. Call `loadCharacters()`. Assert `errorMessage` is not nil.

4. **loadCharacters fetches last messages for each character** -- Configure mock to return 2 characters and a last message for each. Call `loadCharacters()`. Assert `lastMessages` has 2 entries.

5. **defaultCharacter returns the is_default character** -- Configure mock with one default and one non-default character. Call `loadCharacters()`. Assert `defaultCharacter?.isDefault == true`.

6. **defaultCharacter returns nil when no characters** -- Assert `defaultCharacter` is nil when `characters` is empty.

7. **pull-to-refresh preserves existing data during refresh** -- Load initial data, then trigger `loadCharacters()` again. Assert `characters` is not emptied during the refresh (i.e., `isRefreshing` is true, not `isLoading`).

8. **greeting returns correct string for morning** -- Call `HomeViewModel.greeting(for: dateAt8AM)`. Assert result is "Good morning".

9. **greeting returns correct string for afternoon** -- Call `HomeViewModel.greeting(for: dateAt2PM)`. Assert result is "Good afternoon".

10. **greeting returns correct string for evening** -- Call `HomeViewModel.greeting(for: dateAt8PM)`. Assert result is "Good evening".

11. **templateIcon returns correct SF Symbol for each template** -- Assert all 6 template types map to the correct SF Symbol string.

#### MockAPIClient updates

The existing `MockAPIClient` needs to be extended to support returning different response types. The simplest approach: add a `characterListResponse: CharacterListResponse?` property and a `messageListResponse: MessageListResponse?` property, and route the `request(endpoint:body:responseType:)` method accordingly based on the endpoint case.

#### UI Tests (XCTest, optional stretch goal)

- Launch app in authenticated + onboarded state.
- Verify greeting text contains the user's name.
- Verify character cards are visible.
- Tap a character card and verify navigation to a chat destination.
- Pull to refresh and verify the refresh indicator appears.

---

## 8. Acceptance Criteria

1. Given the user is authenticated and has completed onboarding, when the app launches, then HomeView is displayed as the first tab with a time-appropriate greeting and the user's name.

2. Given the user has characters, when HomeView loads, then all active characters are displayed in a two-column grid with avatar icon, name, last message preview, and relative time badge.

3. Given the user has a default character with messages, when HomeView loads, then the daily summary card shows the default character's last AI message content (truncated to 3 lines).

4. Given the user taps a character card, then the app navigates to ChatView for that character via a full-screen NavigationStack push (not a modal, not a new conversation).

5. Given a character has a `last_message_at` timestamp newer than the locally stored `lastOpenedAt` for that character, when HomeView is displayed, then an orange unread dot is visible on that character's card.

6. Given the user taps a character card, then the unread dot for that character is cleared (the current date is stored as `lastOpenedAt`).

7. Given the user pulls down on HomeView, then the character list refreshes from the API, and existing data remains visible during the refresh.

8. Given the API call fails, when HomeView loads, then an error alert is shown with "OK" and "Retry" buttons.

9. Given the user has no characters, when HomeView loads, then an empty state is shown with a message and an "Add Character" button.

10. Given the user taps the "+ Add Character" card at the end of the grid, then the app navigates to a create-character destination (placeholder for now).

11. Given VoiceOver is enabled, when the user navigates HomeView, then all character cards, the daily summary card, the settings button, and the "+ Add Character" card have meaningful accessibility labels.

12. Given a character card is tapped, then `HapticManager.selection()` fires.

13. Given the daily summary card is tapped, then `HapticManager.selection()` fires and the app navigates to the default character's chat.

14. Given the app is in dark mode (forced), then all HomeView elements use colors from `Color+Ember.swift` and render correctly on a dark background.

---

## 9. File Manifest

```
iOS:
  CREATE  ios/Ember/Features/Home/HomeView.swift
  CREATE  ios/Ember/Features/Home/HomeViewModel.swift
  CREATE  ios/Ember/Features/Home/DailySummaryCard.swift
  CREATE  ios/Ember/Features/Home/CharacterCardView.swift
  CREATE  ios/Ember/Core/Models/CharacterModels.swift
  CREATE  ios/Ember/Core/Models/MessageModels.swift
  DELETE  ios/Ember/Features/Home/HomePlaceholderView.swift
  MODIFY  ios/Ember/App/MainTabView.swift (replace HomePlaceholderView with HomeView)
  MODIFY  ios/Ember/App/AppRouter.swift (add Route.createCharacter case)
  MODIFY  ios/Ember/Core/Extensions/EmberSymbol.swift (add template icon constants)
  CREATE  ios/EmberTests/Features/Home/HomeViewModelTests.swift

Shared:
  CREATE  shared/feature-specs/ios-home-view.md (this file)
  CREATE  docs/pipeline/ios-home-view-architect.handoff.md
```

### Modification Details

**MainTabView.swift**: Replace `HomePlaceholderView()` with `HomeView()` on line 18. Add `.createCharacter` to the `destinationView(for:)` switch statement.

**AppRouter.swift**: Add `case createCharacter` to the `Route` enum.

**EmberSymbol.swift**: Add constants for template-specific icons used in character cards:

```
static let templateCompanion = "person.fill"
static let templateEnglishTeacher = "book.fill"
static let templateTherapist = "heart.text.square.fill"
static let templateFitnessCoach = "figure.run"
static let templateCareerCoach = "briefcase.fill"
static let templateCustom = "sparkles"
static let addCharacter = "plus.circle.fill"
```
