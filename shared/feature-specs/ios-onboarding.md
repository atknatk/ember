# Feature Spec: P03-04 -- iOS Onboarding

**Feature ID**: P03-04
**Phase**: 3
**Layer**: ios
**GitHub Issue**: #20
**Date**: 2026-03-13
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature implements the full onboarding flow for the Ember iOS app. It replaces the placeholder `OnboardingPlaceholderView` (from P03-01) with two production screens:

1. **WelcomeView** -- A 3-screen horizontal swipe carousel using `TabView(.page)` with Lottie animations, page indicator dots, and a "Get Started" CTA button on the final page.

2. **QuestionsView** -- 7 full-screen question cards in a `TabView(.page)` with a progress indicator ("1/7" through "7/7"), free-text input per card, a "Skip" option per question, and a final "Submit" action that posts all answers to `POST /api/v1/onboarding/complete`.

An `@Observable OnboardingViewModel` drives the entire flow, managing page state, answer collection, validation, API submission, and the transition from welcome carousel to questions and from questions to the main app.

### Why It Exists

The onboarding flow is the user's first interaction with Ember after signing up. It collects 7 personalization answers that the backend converts into Mem0 memories via Claude Haiku. Without this flow, the AI companion has zero context about the user, making the first conversations generic and impersonal. This directly enables Ember's core value proposition as a memory-first AI companion.

### Dependencies

- **P03-03** (ios-cognito-auth) -- provides `AuthService` with working `getAccessToken()`, `AuthViewModel` with `isAuthenticated`, `EmberApp` with `@AppStorage("hasCompletedOnboarding")` routing that shows `OnboardingPlaceholderView` when the user is authenticated but has not completed onboarding.
- **P03-02** (ios-network-layer) -- provides `APIClient` with `request<T>(endpoint:body:responseType:)`, `APIEndpoint.completeOnboarding` case, `APIError` types, and automatic 401 retry.
- **P03-01** (ios-scaffold) -- provides `AppContainer`, design system constants (`Color+Ember`, `Font+Ember`, `CGFloat+Ember`), `HapticManager`, `EmberSymbol`.
- **P01-09** (onboarding-endpoint, backend) -- provides `POST /api/v1/onboarding/complete` that accepts 7 Q&A pairs and returns `{onboarding_completed: true, memories_seeded: N}`.

### What This Feature Does NOT Do

- It does not change any backend code. The backend endpoint already exists and is fully functional.
- It does not add `ProfileSetupView` (name + photo). The backend already collects the user's name during registration. Profile photo upload is a separate Phase 4 feature.
- It does not implement the `@AppStorage("hasCompletedOnboarding")` routing logic in `EmberApp.swift`. That already exists from P03-01/P03-03.
- It does not bundle Lottie animation JSON files. The Lottie JSON files must be sourced and added to the Xcode asset catalog separately. The spec defines placeholder asset names; the actual animation files should be downloaded from LottieFiles.com or created as custom assets before the feature ships. The view code references these by name and gracefully degrades to a static SF Symbol if the Lottie file is missing.
- It does not handle social sign-in, password reset, or email verification.

---

## 2. Data Models

No database changes. This is an iOS-only feature.

### Swift Models

#### OnboardingAnswer (request body component)

Maps to the backend's `OnboardingAnswer` Pydantic model (see `backend/app/schemas/onboarding.py`).

```
struct OnboardingAnswer: Codable {
    let questionKey: String
    let answer: String
}
```

#### OnboardingRequest (request body)

Maps to the backend's `OnboardingRequest` Pydantic model.

```
struct OnboardingRequest: Codable {
    let answers: [OnboardingAnswer]
}
```

#### OnboardingResponse (response)

Maps to the backend's `OnboardingResponse` Pydantic model.

```
struct OnboardingResponse: Codable {
    let onboardingCompleted: Bool
    let memoriesSeeded: Int
}
```

These structs are decoded using `JSONDecoder.ember` which converts `snake_case` keys to `camelCase` properties automatically.

---

## 3. API Endpoints

No new endpoints. This feature calls the existing backend endpoint:

```
POST /api/v1/onboarding/complete
Auth: Bearer JWT required
Request headers: Content-Type: application/json
Request body:
{
    "answers": [
        { "question_key": "preferred_name", "answer": "Alex" },
        { "question_key": "occupation", "answer": "Software engineer" },
        { "question_key": "daily_rhythm", "answer": "Night owl" },
        { "question_key": "health_goal", "answer": "Run a marathon" },
        { "question_key": "stress_management", "answer": "I go for walks" },
        { "question_key": "sleep_schedule", "answer": "12am to 8am" },
        { "question_key": "communication_style", "answer": "Casual and fun" }
    ]
}
Response 200:
{
    "onboarding_completed": true,
    "memories_seeded": 7
}
Response 409: { "detail": "Onboarding already completed" }
Response 422: { "detail": "..." } (validation error)
Response 401: { "detail": "..." } (unauthorized)
Response 503: { "detail": "..." } (upstream service unavailable)
```

The `APIEndpoint.completeOnboarding` case already exists in `ios/Ember/Core/Network/APIEndpoint.swift` (path: `/api/v1/onboarding/complete`, method: POST, requiresAuth: true).

---

## 4. Backend Logic

Not applicable. This is an iOS-only feature. The backend endpoint is fully implemented in `backend/app/routes/onboarding.py` and `backend/app/services/onboarding_service.py` (see P01-09).

---

## 5. iOS Screens and Components

### 5.1 OnboardingFlowView (Container)

**File**: `ios/Ember/Features/Onboarding/OnboardingFlowView.swift`

This is the top-level container that replaces `OnboardingPlaceholderView` in `EmberApp.swift`. It does not contain logic itself -- it creates the `OnboardingViewModel` and shows either `WelcomeView` or `QuestionsView` based on the ViewModel's `currentPhase` property.

- **ViewModel**: `@State private var viewModel = OnboardingViewModel()`
- **Navigation**: Entered from `EmberApp.swift` when `isAuthenticated == true && hasCompletedOnboarding == false`. Exits by setting `@AppStorage("hasCompletedOnboarding")` to `true` after successful submission.
- **Phase routing**:
  - `.welcome` phase: shows `WelcomeView`
  - `.questions` phase: shows `QuestionsView`
- **Transition**: The phase change from `.welcome` to `.questions` uses `.transition(.move(edge: .trailing))` with a 400ms spring animation.
- **Background**: `Color.emberBackground.ignoresSafeArea()`
- **Environment injection**: Passes `viewModel` to child views via the `@State` + binding pattern (not environment, since only two children use it).

### 5.2 WelcomeView (3-Screen Carousel)

**File**: `ios/Ember/Features/Onboarding/WelcomeView.swift`

A 3-screen horizontal swipe carousel built with `TabView` and `.tabViewStyle(.page(indexDisplayMode: .never))` (custom page dots instead of system dots).

#### ViewModel Properties Read

- `viewModel.currentWelcomePage` (Int, 0-2) -- bound to TabView selection

#### UI Elements

Each page consists of:

| Page | Lottie Asset Name | Fallback SF Symbol | Title | Description |
|------|------------------|--------------------|-------|-------------|
| 0 | `onboarding-welcome` | `sparkles` | "Meet Ember" | "Your personal AI companion that remembers, understands, and grows with you." |
| 1 | `onboarding-memory` | `brain.head.profile` | "Built on Memory" | "Every conversation builds a deeper understanding. Ember remembers what matters to you." |
| 2 | `onboarding-companion` | `heart.fill` | "Always Here for You" | "Get personalized support, motivation, and genuine connection -- anytime you need it." |

#### Layout per Page (top to bottom)

1. Lottie animation (or fallback SF Symbol) -- centered, 200pt height, constrained to screen width minus horizontal padding
2. Title text -- `Font.emberLargeTitle`, `Color.emberTextPrimary`, centered
3. Description text -- `Font.emberBody`, `Color.emberTextSecondary`, centered, multiline, max 3 lines

#### Page Indicator

Below the TabView, a row of 3 custom dots:
- Active dot: 8pt wide, 8pt tall, `Color.emberPrimary`, circular
- Inactive dot: 8pt wide, 8pt tall, `Color.emberTextDisabled`, circular
- Spacing between dots: 8pt
- Animation: `.spring(response: 0.3)` on the active dot's scale/opacity

#### "Get Started" Button

Visible on all pages, but appears with different styling:
- Pages 0 and 1: "Next" label, secondary style -- `Color.emberPrimary` text on transparent background with an `Color.emberPrimary` border (1pt), pill shape (`cornerRadius: .emberRadius28`), height 52pt
- Page 2: "Get Started" label, primary style -- `Color.emberTextPrimary` text on `LinearGradient(colors: [Color.emberGradientStart, Color.emberGradientEnd])` background, pill shape, height 52pt
- Tapping "Next" on pages 0/1 animates to the next page (`withAnimation(.spring(response: 0.4))`)
- Tapping "Get Started" on page 2 calls `viewModel.advanceToQuestions()` which sets `currentPhase = .questions`

#### "Skip" Link

- A text button below the main CTA: "Skip" in `Font.emberSecondary`, `Color.emberTextSecondary`
- Visible on pages 0 and 1 only
- Tapping skips directly to page 2 (not to questions)

#### Haptic Feedback

- Page change: `HapticManager.selection()`
- "Get Started" tap: `HapticManager.impact(.medium)`

#### Accessibility

- Lottie animations: `.accessibilityHidden(true)` (decorative)
- Page indicator dots: `.accessibilityHidden(true)` (page state communicated by VoiceOver reading the visible page title)
- "Next" / "Get Started" button: `.accessibilityLabel("Next page")` / `.accessibilityLabel("Get Started")`
- "Skip" button: `.accessibilityLabel("Skip to last welcome page")`

### 5.3 QuestionsView (7 Question Cards)

**File**: `ios/Ember/Features/Onboarding/QuestionsView.swift`

A full-screen question card flow using `TabView` with `.tabViewStyle(.page(indexDisplayMode: .never))` and swiping disabled (navigation controlled by "Next" / "Back" buttons only, to avoid accidental swipe-away while typing).

#### ViewModel Properties Read

- `viewModel.currentQuestionIndex` (Int, 0-6) -- bound to TabView selection
- `viewModel.answers` ([String], length 7) -- bound to each question card's TextField
- `viewModel.isSubmitting` (Bool) -- disables UI during API call
- `viewModel.errorMessage` (String?) -- shown in alert

#### Progress Indicator

At the top of the screen:
- Text: "\(currentQuestionIndex + 1)/7" in `Font.emberCaption`, `Color.emberTextSecondary`
- Progress bar: horizontal bar, full width minus 40pt (20pt padding each side), 4pt tall, `Color.emberSurface3` background, filled portion in `Color.emberPrimary`, fill percentage = `(currentQuestionIndex + 1) / 7`, corner radius 2pt
- Animation: `.easeInOut(duration: 0.3)` on fill width changes

#### Question Cards

Each card is a full-screen view containing:

| Index | question_key | Question Text | Placeholder |
|-------|-------------|---------------|-------------|
| 0 | `preferred_name` | "What should I call you?" | "Your preferred name" |
| 1 | `occupation` | "What do you do for work?" | "Your occupation or field" |
| 2 | `daily_rhythm` | "Are you a morning person or a night owl?" | "e.g., Early bird, Night owl" |
| 3 | `health_goal` | "What are your health or fitness goals?" | "e.g., Run a marathon, eat healthier" |
| 4 | `stress_management` | "How do you manage stress?" | "e.g., Exercise, meditation, walks" |
| 5 | `sleep_schedule` | "What is your sleep schedule like?" | "e.g., 11pm to 7am" |
| 6 | `communication_style` | "What kind of friendship do you expect from me?" | "e.g., Casual and fun, supportive coach" |

#### Card Layout (top to bottom, per card)

1. **Question number badge**: Circle with index+1, 32pt diameter, `Color.emberPrimary` background, white text, `Font.emberHeadline`
2. **Question text**: `Font.emberTitle`, `Color.emberTextPrimary`, centered, multiline
3. **Text input**: `TextField` with placeholder, `AuthTextFieldStyle` modifier (reused from `LoginView.swift`), keyboard type `.default`, `submitLabel(.next)` (or `.done` on card 6)
4. **Skip text**: "Skip" link, `Font.emberSecondary`, `Color.emberTextSecondary`, visible on all cards -- tapping clears the answer for this question and advances to next card (or submits if on card 6)

#### Navigation Buttons

At the bottom of the screen, a horizontal stack:

- **Back button**: Visible when `currentQuestionIndex > 0`. Tapping decrements `currentQuestionIndex`. Label: chevron.left icon + "Back", `Color.emberTextSecondary`.
- **Next / Submit button**: Right-aligned. For cards 0-5: "Next" label, enabled if `answers[currentQuestionIndex]` is non-empty OR (the user tapped "Skip" and the answer is empty, meaning they want to skip). For card 6: "Submit" label, gradient background (`emberGradientStart` to `emberGradientEnd`), enabled if at least one answer across all 7 is non-empty (cannot submit all blanks).
  - "Next" advances to the next card
  - "Submit" calls `viewModel.submitOnboarding()`
- Button styling: 52pt height, pill shape (`.emberRadius28`), full width

#### Keyboard Handling

- `@FocusState` tracks the active text field per question index
- When a card becomes visible, the text field auto-focuses after a 0.3s delay (using `.onAppear` + `Task.sleep`)
- `.scrollDismissesKeyboard(.interactively)` on the containing ScrollView
- The "Next" button is positioned above the keyboard using padding tied to keyboard height (or simply use a `ScrollView` to ensure the input is always visible)

#### Haptic Feedback

- Question advance (Next): `HapticManager.selection()`
- Skip: `HapticManager.selection()`
- Submit tap: `HapticManager.impact(.medium)`
- Submission success: `HapticManager.notification(.success)`
- Submission error: `HapticManager.notification(.error)`

#### Loading State

When `viewModel.isSubmitting == true`:
- The "Submit" button shows a `ProgressView()` instead of the "Submit" text
- The "Submit" button is disabled
- The back button and skip link are disabled
- All text fields are disabled

#### Error State

When `viewModel.errorMessage != nil`:
- Standard `.alert("Error", ...)` pattern (same as `LoginView`)
- 409 Conflict ("Onboarding already completed"): the ViewModel treats this as success and transitions to the main app
- 401 Unauthorized: handled by `APIClient`'s 401 retry; if retry fails, `APIError.unauthorized` is thrown -- the `AuthViewModel` (in `EmberApp`) will detect the session is invalid and redirect to login
- 503 / 500: show the error message with a "Try Again" button in the alert

#### Accessibility

- Question text: accessible by default (Text view)
- TextField: `.accessibilityLabel("Answer for question \(index + 1)")`
- Skip: `.accessibilityLabel("Skip this question")`
- Back: `.accessibilityLabel("Go to previous question")`
- Next: `.accessibilityLabel("Go to next question")`
- Submit: `.accessibilityLabel("Submit onboarding answers")`
- Progress: `.accessibilityLabel("Question \(index + 1) of 7")`

### 5.4 OnboardingViewModel

**File**: `ios/Ember/Features/Onboarding/OnboardingViewModel.swift`

```
@Observable
final class OnboardingViewModel {
    // Phase
    enum Phase { case welcome, questions }
    var currentPhase: Phase = .welcome

    // Welcome
    var currentWelcomePage: Int = 0

    // Questions
    var currentQuestionIndex: Int = 0
    var answers: [String] = Array(repeating: "", count: 7)

    // Submission
    var isSubmitting: Bool = false
    var errorMessage: String? = nil

    // Dependencies
    private let apiClient: APIClientProtocol

    init(apiClient: APIClientProtocol = APIClient.shared) { ... }
}
```

#### Computed Properties

- `canSubmit: Bool` -- at least one answer (across all 7) has a non-empty trimmed value. This prevents submitting 7 blank answers.
- `currentAnswerIsEmpty: Bool` -- `answers[currentQuestionIndex].trimmingCharacters(in: .whitespaces).isEmpty`
- `progressFraction: Double` -- `Double(currentQuestionIndex + 1) / 7.0`

#### Methods

##### `advanceToQuestions()`

Sets `currentPhase = .questions`. Called by WelcomeView's "Get Started" button.

##### `advanceToNextQuestion()`

If `currentQuestionIndex < 6`, increments `currentQuestionIndex`. If `currentQuestionIndex == 6`, does nothing (submit must be used).

##### `goToPreviousQuestion()`

If `currentQuestionIndex > 0`, decrements `currentQuestionIndex`.

##### `skipCurrentQuestion()`

Clears `answers[currentQuestionIndex]` (sets to empty string), then calls `advanceToNextQuestion()`. If on question 6 (last), calls `submitOnboarding()` instead.

##### `submitOnboarding() async`

1. Set `isSubmitting = true`, `errorMessage = nil`
2. Build an `[OnboardingAnswer]` array from the 7 question keys and answers. For skipped questions (empty answer), use the fallback string "Not provided" -- the backend requires all 7 answers with `min_length=1`.
3. Create `OnboardingRequest(answers: answersArray)`
4. Call `apiClient.request(endpoint: .completeOnboarding, body: request, responseType: OnboardingResponse.self)`
5. On success: set `isSubmitting = false`, return `true` (the calling view uses this to set `@AppStorage("hasCompletedOnboarding") = true`)
6. On 409 error (already completed): treat as success -- user's onboarding was already done, proceed to main app
7. On other errors: set `errorMessage`, set `isSubmitting = false`, return `false`

**Important**: The `submitOnboarding()` method does not set `@AppStorage("hasCompletedOnboarding")` directly, because `@AppStorage` is a SwiftUI property wrapper that must live in a View. Instead, `submitOnboarding()` returns a `Bool` indicating success, and the `OnboardingFlowView` sets the `@AppStorage` value in its `.task` or button handler.

Alternatively, the ViewModel can expose an `onComplete: (() -> Void)?` closure that the `OnboardingFlowView` sets during initialization, which the ViewModel calls on success. Either pattern is acceptable; the key constraint is that `@AppStorage` writes happen in the View layer.

#### Question Key Mapping

A static array maps indices to question keys:

```
static let questionKeys = [
    "preferred_name",
    "occupation",
    "daily_rhythm",
    "health_goal",
    "stress_management",
    "sleep_schedule",
    "communication_style",
]
```

This array matches `VALID_QUESTION_KEYS` in `backend/app/schemas/onboarding.py`.

### 5.5 Lottie Integration

**File**: Uses `Lottie` SPM package (already in the project dependencies from P03-01).

A thin wrapper view encapsulates Lottie playback:

**File**: `ios/Ember/Features/Onboarding/LottieAnimationViewWrapper.swift`

```
struct LottieAnimationViewWrapper: UIViewRepresentable {
    let animationName: String
    let loopMode: LottieLoopMode = .loop
    // UIViewRepresentable makeUIView / updateUIView
}
```

- Plays the named animation from the bundle in loop mode
- If the animation JSON file is not found in the bundle, the view renders as an empty frame (graceful degradation -- the fallback SF Symbol is handled at the WelcomeView level, not inside this wrapper)
- Accessibility: the wrapper adds `.accessibilityHidden(true)` since all Lottie animations in onboarding are decorative

#### Required Lottie Asset Files

These JSON files must be added to the Xcode project (under `ios/Ember/Resources/Animations/`):

| File Name | Used In | Description |
|-----------|---------|-------------|
| `onboarding-welcome.json` | WelcomeView page 0 | General welcome/sparkle animation |
| `onboarding-memory.json` | WelcomeView page 1 | Brain/memory concept animation |
| `onboarding-companion.json` | WelcomeView page 2 | Companion/connection animation |

The ios-dev agent should source these from LottieFiles.com (free tier) or use simple placeholder animations. The spec does not mandate specific animation content -- any thematically appropriate animation works.

---

## 6. Android Screens and Components

Not applicable. This is an iOS-only feature (layer: `ios`).

---

## 7. Test Plan

### iOS Tests

#### OnboardingViewModelTests

**File**: `ios/EmberTests/Features/Onboarding/OnboardingViewModelTests.swift`

Using Swift Testing (`@Suite`, `@Test`):

| Test | Scenario | Expected |
|------|----------|----------|
| `initialState` | Create a fresh ViewModel | `currentPhase == .welcome`, `currentWelcomePage == 0`, `currentQuestionIndex == 0`, all answers empty, `isSubmitting == false`, `errorMessage == nil` |
| `advanceToQuestions` | Call `advanceToQuestions()` | `currentPhase == .questions` |
| `advanceToNextQuestion_incrementsIndex` | Set `currentQuestionIndex = 2`, call `advanceToNextQuestion()` | `currentQuestionIndex == 3` |
| `advanceToNextQuestion_stopsAtSix` | Set `currentQuestionIndex = 6`, call `advanceToNextQuestion()` | `currentQuestionIndex == 6` (no change) |
| `goToPreviousQuestion_decrementsIndex` | Set `currentQuestionIndex = 3`, call `goToPreviousQuestion()` | `currentQuestionIndex == 2` |
| `goToPreviousQuestion_stopsAtZero` | Set `currentQuestionIndex = 0`, call `goToPreviousQuestion()` | `currentQuestionIndex == 0` (no change) |
| `skipCurrentQuestion_clearsAnswerAndAdvances` | Set `answers[2] = "test"`, `currentQuestionIndex = 2`, call `skipCurrentQuestion()` | `answers[2] == ""`, `currentQuestionIndex == 3` |
| `canSubmit_falseWhenAllEmpty` | All answers empty | `canSubmit == false` |
| `canSubmit_trueWhenOneAnswered` | Set `answers[0] = "Alex"` | `canSubmit == true` |
| `submitOnboarding_success` | Mock API returns `OnboardingResponse(onboardingCompleted: true, memoriesSeeded: 7)`. Set at least one answer. Call `submitOnboarding()`. | Returns `true`, `isSubmitting == false`, `errorMessage == nil` |
| `submitOnboarding_409_treatedAsSuccess` | Mock API throws `APIError.serverError(statusCode: 409, detail: "...")`. Call `submitOnboarding()`. | Returns `true` (treated as already completed) |
| `submitOnboarding_503_setsError` | Mock API throws `APIError.serverError(statusCode: 503, detail: "...")`. Call `submitOnboarding()`. | Returns `false`, `errorMessage != nil`, `isSubmitting == false` |
| `submitOnboarding_networkError_setsError` | Mock API throws `APIError.networkError(...)`. Call `submitOnboarding()`. | Returns `false`, `errorMessage != nil` |
| `submitOnboarding_setsNotProvidedForSkipped` | Leave `answers[1]` empty, fill all others. Call `submitOnboarding()`. Verify the request body. | The `OnboardingAnswer` for index 1 has `answer: "Not provided"` |
| `submitOnboarding_setsIsSubmittingDuringCall` | Call `submitOnboarding()`. Verify `isSubmitting == true` before the API call completes. | `isSubmitting == true` during, `false` after |

#### Mock Setup

Use `MockAPIClient` (from `ios/EmberTests/Fakes/MockAPIClient.swift`) extended with an `onboardingResponse` property and a check in its `request<T>` method for the `.completeOnboarding` endpoint.

Alternatively, extend `MockAPIClient` to accept a generic closure or response dictionary. The exact mock mechanism depends on the existing `MockAPIClient` shape from P03-02.

#### UI Tests (optional, lower priority)

If time permits, a basic `XCUITest`:

1. Launch app in unauthenticated + not-onboarded state
2. Complete login (or use a mock auth state)
3. Verify WelcomeView appears with "Meet Ember" title
4. Swipe left twice, verify "Get Started" button is visible
5. Tap "Get Started", verify first question "What should I call you?" appears
6. Enter "Alex", tap "Next" 6 times, entering answers
7. Tap "Submit", verify transition to main app

---

## 8. Acceptance Criteria

1. Given the user has authenticated and `hasCompletedOnboarding` is `false`, when the app launches, then `OnboardingFlowView` is displayed (not `OnboardingPlaceholderView`).

2. Given the user is on `WelcomeView`, when the user swipes left, then the next welcome page is displayed with a page transition animation.

3. Given the user is on welcome page 2, when the user taps "Get Started", then the view transitions to `QuestionsView` showing question 1 of 7.

4. Given the user is on welcome page 0 or 1, when the user taps "Skip", then the view jumps to welcome page 2.

5. Given the user is on `QuestionsView`, then a progress indicator showing "N/7" and a progress bar is visible at the top.

6. Given the user is on question card N (not the last), when the user types an answer and taps "Next", then question card N+1 is shown and the progress indicator updates.

7. Given the user is on question card N (not the first), when the user taps "Back", then question card N-1 is shown with the previously entered answer preserved.

8. Given the user is on any question card, when the user taps "Skip", then the answer for that question is cleared and the next question is shown.

9. Given the user is on question 7 and at least one answer across all questions is non-empty, when the user taps "Submit", then a POST request is sent to `/api/v1/onboarding/complete` with all 7 answers (using "Not provided" for skipped questions).

10. Given the submission succeeds (200 OK), then `@AppStorage("hasCompletedOnboarding")` is set to `true`, a success haptic fires, and the app navigates to `MainTabView`.

11. Given the submission fails with 409 Conflict, then the app treats it as success and navigates to `MainTabView`.

12. Given the submission fails with a network or server error (5xx), then an error alert is displayed with a dismiss button, and the user remains on the questions screen with their answers preserved.

13. Given the submission is in progress, then the "Submit" button shows a loading indicator and all inputs are disabled.

14. All interactive elements (buttons, text fields) have `accessibilityLabel` values.

15. All Lottie animations are marked `.accessibilityHidden(true)`.

16. Page changes and button taps produce haptic feedback as specified.

17. All views use `Color.emberBackground` for the background and respect the dark mode color system.

18. The `OnboardingViewModel` has at least 80% line coverage from unit tests.

---

## 9. File Manifest

```
iOS:
  DELETE  ios/Ember/Features/Auth/OnboardingPlaceholderView.swift
  CREATE  ios/Ember/Features/Onboarding/OnboardingFlowView.swift
  CREATE  ios/Ember/Features/Onboarding/OnboardingViewModel.swift
  CREATE  ios/Ember/Features/Onboarding/WelcomeView.swift
  CREATE  ios/Ember/Features/Onboarding/QuestionsView.swift
  CREATE  ios/Ember/Features/Onboarding/LottieAnimationViewWrapper.swift
  CREATE  ios/Ember/Core/Models/OnboardingModels.swift
  MODIFY  ios/Ember/App/EmberApp.swift (replace OnboardingPlaceholderView with OnboardingFlowView)
  CREATE  ios/Ember/Resources/Animations/onboarding-welcome.json (Lottie asset)
  CREATE  ios/Ember/Resources/Animations/onboarding-memory.json (Lottie asset)
  CREATE  ios/Ember/Resources/Animations/onboarding-companion.json (Lottie asset)

Tests:
  CREATE  ios/EmberTests/Features/Onboarding/OnboardingViewModelTests.swift

Shared:
  CREATE  shared/feature-specs/ios-onboarding.md (this file)
  CREATE  docs/pipeline/ios-onboarding-architect.handoff.md
```

### Modifications Detail

#### `ios/Ember/App/EmberApp.swift`

Change the line:
```
OnboardingPlaceholderView()
```
to:
```
OnboardingFlowView()
```

No other changes to `EmberApp.swift`.

#### `ios/Ember/Features/Auth/OnboardingPlaceholderView.swift`

Delete this file entirely. It is replaced by `OnboardingFlowView`.
