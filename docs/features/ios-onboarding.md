# iOS Onboarding

> Provides the complete first-run onboarding experience for new Ember users — a 3-page welcome carousel followed by 7 personalization question cards that seed the AI companion's long-term memory before the first conversation.

**Status**: Released
**Added in**: Phase 3 (P03-04)
**Platforms**: iOS
**GitHub Issue**: #20

---

## Overview

This feature replaces the placeholder `OnboardingPlaceholderView` stub (introduced in P03-01) with two fully-built production screens. After signing up, the user sees a `WelcomeView` — a three-page horizontal swipe carousel with Lottie animations that introduces Ember's key concepts. Once the user taps "Get Started", they move to `QuestionsView`, which presents seven full-screen question cards collecting personalization data such as the user's preferred name, occupation, sleep schedule, and communication style.

The collected answers are submitted as a single `POST /api/v1/onboarding/complete` request (implemented in P01-09). The backend converts each answer into a Mem0 memory via Claude Haiku, so Ember's first conversation is already personalized rather than generic. This is the critical bridge between user registration and a meaningful first interaction with the AI companion.

An `@Observable OnboardingViewModel` owns all state for both screens: which phase is active (welcome or questions), the current page/card index, the text of each answer, and the submission lifecycle (loading, error, success). The `@AppStorage("hasCompletedOnboarding")` flag, which gates the entire flow in `EmberApp.swift`, is written by `OnboardingFlowView` (the View layer) after `submitOnboarding()` returns `true` — never by the ViewModel directly.

---

## Architecture

### How It Works (Data Flow)

1. `EmberApp.swift` evaluates `isAuthenticated == true && hasCompletedOnboarding == false` and renders `OnboardingFlowView`.
2. `OnboardingFlowView` creates `@State private var viewModel = OnboardingViewModel()` and passes it to whichever child screen is active.
3. `OnboardingViewModel.currentPhase` starts as `.welcome`. `WelcomeView` is shown.
4. The user swipes through three carousel pages (or taps "Next"). On the final page, "Get Started" calls `viewModel.advanceToQuestions()`.
5. `currentPhase` changes to `.questions`. SwiftUI transitions to `QuestionsView` with a `.move(edge: .trailing)` animation.
6. The user fills in up to 7 question cards. Empty answers are treated as "Not provided" at submission time, not before.
7. On the last card, tapping "Submit" (or "Skip" if the user wants to skip question 7) calls `viewModel.submitOnboarding()`.
8. `submitOnboarding()` sets `isSubmitting = true`, builds an `[OnboardingAnswer]` array (substituting `"Not provided"` for blank entries), and calls `APIClient.shared.request(endpoint: .completeOnboarding, ...)`.
9. On HTTP 200, the method returns `true`. On HTTP 409 ("already completed"), it also returns `true` — this handles the case where the network dropped after the backend committed but before the client received the response.
10. `QuestionsView`'s `onComplete` closure fires, setting `@AppStorage("hasCompletedOnboarding") = true`.
11. `EmberApp.swift` re-evaluates the root view branch and replaces `OnboardingFlowView` with `MainTabView`.

### Phase Routing in OnboardingFlowView

`OnboardingFlowView` is the only screen that owns the `@AppStorage` key. It is deliberately thin: it creates the ViewModel once as a `@State` property, switches on `viewModel.currentPhase`, and passes an `onComplete: () -> Void` closure to `QuestionsView`. This keeps `@AppStorage` writes in the View layer as required by SwiftUI's property-wrapper model.

```swift
QuestionsView(viewModel: viewModel) {
    hasCompletedOnboarding = true
}
```

### Skipped Answers and the "Not Provided" Rule

The backend's `POST /api/v1/onboarding/complete` schema requires every `OnboardingAnswer` to have `min_length=1`. If a user skips a question, `submitOnboarding()` substitutes `"Not provided"` for that blank entry before sending the request. The ViewModel stores the empty string internally; the substitution happens only at the moment of building the request body.

### Skip on the Last Question

Tapping "Skip" on question card 6 is a special case. Because `skipCurrentQuestion()` on index 6 needs to trigger submission (and `onComplete` must fire in the View layer), the skip button's action in `QuestionsView` handles this directly:

```swift
// Skip button action (QuestionsView, last card)
if index == 6 {
    Task {
        let success = await viewModel.submitOnboarding()
        if success { onComplete() }
    }
}
```

This is the key deviation from the original spec, which routed everything through `viewModel.skipCurrentQuestion()`. The `skipCurrentQuestion()` method on the ViewModel does fire `Task { await submitOnboarding() }` on index 6, but the View's skip button also handles it independently to ensure `onComplete` runs in the correct scope.

### Lottie Asset Resolution

`WelcomeView` checks `Bundle.main.url(forResource:withExtension:)` at render time. If the Lottie JSON file is found, `LottieAnimationViewWrapper` plays the animation. If not, an SF Symbol is shown using the same frame dimensions. This means the view is fully usable even if the animation JSON files are missing or are placeholder-quality.

The current Lottie JSON files are minimal placeholder animations (rotating sparkle, pulsing circle, heartbeat) and should be replaced with production-quality assets from LottieFiles.com before a public release.

### Key Files

```
ios/Ember/Features/Onboarding/
  OnboardingFlowView.swift       # Top-level container; owns @AppStorage; routes between phases
  OnboardingViewModel.swift      # @Observable ViewModel: all phase/answer/submission state
  WelcomeView.swift              # 3-page carousel with Lottie, page dots, CTA buttons
  QuestionsView.swift            # 7 question cards with progress bar, text input, navigation
  LottieAnimationViewWrapper.swift  # UIViewRepresentable wrapper for Lottie

ios/Ember/Core/Models/
  OnboardingModels.swift         # OnboardingAnswer, OnboardingRequest, OnboardingResponse

ios/Ember/Resources/Animations/
  onboarding-welcome.json        # Lottie asset for WelcomeView page 0 (placeholder)
  onboarding-memory.json         # Lottie asset for WelcomeView page 1 (placeholder)
  onboarding-companion.json      # Lottie asset for WelcomeView page 2 (placeholder)

ios/EmberTests/Features/Onboarding/
  OnboardingViewModelTests.swift  # Swift Testing suite for the ViewModel
```

---

## API Reference

See [`docs/04-veri-api.md`](../04-veri-api.md) for the full backend API contract. This feature calls one existing endpoint.

### `POST /api/v1/onboarding/complete`

**Auth**: Bearer JWT required
**Content-Type**: `application/json`

**Request Body**:
```json
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
```

**Response** (200):
```json
{
  "onboarding_completed": true,
  "memories_seeded": 7
}
```

**Error Responses**:

| Status | When | iOS handling |
|--------|------|--------------|
| 401 | Missing or invalid JWT | `APIClient` triggers token refresh; if that fails, `APIError.unauthorized` is thrown |
| 409 | Onboarding already completed | Treated as success — ViewModel returns `true` and does not set `errorMessage` |
| 422 | Validation error (e.g., empty answer) | `errorMessage` is set; user stays on questions screen |
| 503 | Upstream service unavailable (Mem0/Claude) | `errorMessage` is set with a "Try Again" prompt |

The `APIEndpoint.completeOnboarding` case already existed in `ios/Ember/Core/Network/APIEndpoint.swift` from P03-02. This feature does not modify it.

---

## iOS Implementation

**Files**:
- `ios/Ember/Features/Onboarding/OnboardingFlowView.swift` — Container view; owns `@AppStorage`
- `ios/Ember/Features/Onboarding/OnboardingViewModel.swift` — `@Observable` ViewModel
- `ios/Ember/Features/Onboarding/WelcomeView.swift` — Welcome carousel screen
- `ios/Ember/Features/Onboarding/QuestionsView.swift` — Question cards screen
- `ios/Ember/Features/Onboarding/LottieAnimationViewWrapper.swift` — Lottie UIViewRepresentable wrapper
- `ios/Ember/Core/Models/OnboardingModels.swift` — Codable request/response structs

**Key Patterns**:
- `OnboardingViewModel` is `@Observable` (iOS 17+). Use `@Bindable var viewModel` in child views that need two-way bindings (e.g., `$viewModel.currentWelcomePage`).
- `QuestionsView` receives `onComplete: () -> Void` as a closure parameter rather than relying on environment injection, since only this view needs to trigger the completion.
- `LottieAnimationViewWrapper` is a `UIViewRepresentable` and is always marked `.accessibilityHidden(true)` since all onboarding animations are decorative.
- `AuthTextFieldStyle` (from `LoginView.swift` in P03-03) is reused without modification for the question card text fields.

**State Properties** (`OnboardingViewModel`):
```swift
var currentPhase: Phase = .welcome         // .welcome or .questions
var currentWelcomePage: Int = 0            // 0–2, bound to WelcomeView TabView
var currentQuestionIndex: Int = 0          // 0–6, bound to QuestionsView TabView
var answers: [String] = Array(repeating: "", count: 7)
var isSubmitting: Bool = false
var errorMessage: String? = nil
```

**Computed Properties**:
- `canSubmit: Bool` — `true` if at least one answer has a non-whitespace-only value. Guards the Submit button's enabled state.
- `currentAnswerIsEmpty: Bool` — used by `QuestionsView` to determine Next button style.
- `progressFraction: Double` — drives the progress bar fill width.

**Static Data** (`OnboardingViewModel`):
- `questionKeys: [String]` — the 7 `question_key` values sent to the backend, in order. Must match `VALID_QUESTION_KEYS` in `backend/app/schemas/onboarding.py`.
- `questionTexts: [String]` — display text for each card.
- `questionPlaceholders: [String]` — `TextField` placeholder text for each card.

**Navigation**:
- Entered from `EmberApp.swift` when `authViewModel.isAuthenticated == true && !hasCompletedOnboarding`.
- Exits by the `onComplete` closure setting `@AppStorage("hasCompletedOnboarding") = true`, which causes `EmberApp` to re-render `MainTabView`.
- No `NavigationStack` push or sheet presentation is used — this is a full-screen replacement driven by `EmberApp`'s root view switch.

---

## Testing

### Coverage Summary

| Platform | File | Tests | Focus |
|----------|------|-------|-------|
| iOS | `OnboardingViewModelTests.swift` | 16 | All ViewModel state transitions, submission outcomes, edge cases |

All tests use Swift Testing (`import Testing`), not XCTest.

### Test Cases

| Test | What It Verifies |
|------|-----------------|
| `initialState` | All properties start at correct defaults |
| `advanceToQuestions` | `currentPhase` becomes `.questions` |
| `advanceToNextQuestion_incrementsIndex` | Index increments from 2 to 3 |
| `advanceToNextQuestion_stopsAtSix` | Index stays at 6 when already at the last card |
| `goToPreviousQuestion_decrementsIndex` | Index decrements from 3 to 2 |
| `goToPreviousQuestion_stopsAtZero` | Index stays at 0 when already at the first card |
| `skipCurrentQuestion_clearsAnswerAndAdvances` | Answer is cleared and index advances |
| `canSubmit_falseWhenAllEmpty` | `canSubmit` is `false` for all-empty answers |
| `canSubmit_trueWhenOneAnswered` | `canSubmit` is `true` when one answer is non-empty |
| `canSubmit_falseWhenOnlyWhitespace` | Whitespace-only answers do not count |
| `currentAnswerIsEmpty_true/false` | Reports empty vs. non-empty correctly |
| `progressFraction` | Returns correct fraction for index 0 and 6 |
| `submitOnboarding_success` | Returns `true`, `isSubmitting` resets to `false` |
| `submitOnboarding_409_treatedAsSuccess` | 409 returns `true`, no `errorMessage` |
| `submitOnboarding_503_setsError` | Returns `false`, `errorMessage` is non-nil |
| `submitOnboarding_networkError_setsError` | Returns `false`, `errorMessage` is non-nil |
| `questionKeysCount` | All three static arrays have 7 entries |
| `questionKeysMatchBackend` | `questionKeys` matches the exact backend enum values |

### Mock Setup

Tests inject `MockAPIClient` (from `ios/EmberTests/Mocks/MockAPIClient.swift`):

```swift
let mockAPI = MockAPIClient()
// Success:
mockAPI.requestResult = OnboardingResponse(onboardingCompleted: true, memoriesSeeded: 7)
// 409:
mockAPI.requestError = APIError.serverError(statusCode: 409, detail: "Onboarding already completed")
// 503:
mockAPI.requestError = APIError.serverError(statusCode: 503, detail: "Service unavailable")
```

The `requestCallCount` property on `MockAPIClient` verifies that exactly one API call was made.

### Running Tests

```bash
cd ios
xcodebuild test -scheme Ember -destination "platform=iOS Simulator,name=iPhone 16"
```

---

## Known Limitations

- **Placeholder Lottie animations**: The three Lottie JSON files bundled with this feature are minimal placeholders (rotating sparkle, pulsing circle, heartbeat). They must be replaced with production-quality animations from LottieFiles.com before a public release. The view degrades gracefully to SF Symbol fallbacks if files are missing.
- **No offline mode**: All 7 answers are submitted in one request. If the user completes all cards and has no network connectivity, submission fails and they must retry. There is no draft-save mechanism.
- **Question set is fixed**: The 7 question keys are hardcoded in `OnboardingViewModel.questionKeys`. Adding, removing, or reordering questions requires updating both this static array and `VALID_QUESTION_KEYS` in `backend/app/schemas/onboarding.py` together.
- **No "back to welcome" option**: Once the user advances from `WelcomeView` to `QuestionsView`, there is no button to return to the carousel. The phase transition is one-way.
- **Implementation deviation from spec — skip on last card**: The spec described routing the skip action on card 6 entirely through `viewModel.skipCurrentQuestion()`. In the implementation, `QuestionsView` handles the skip action on card 6 directly (calling `submitOnboarding()` and `onComplete()` in the View layer) to keep `@AppStorage` writes out of the ViewModel. The ViewModel's `skipCurrentQuestion()` still fires a `Task { await submitOnboarding() }` on index 6, but this path does not have access to `onComplete`. In practice, only the View's skip path is used for card 6.

---

## Extending This Feature

### Changing the question set

1. Update `OnboardingViewModel.questionKeys`, `questionTexts`, and `questionPlaceholders` in `OnboardingViewModel.swift` — all three arrays must stay in sync and have the same count.
2. Update `VALID_QUESTION_KEYS` in `backend/app/schemas/onboarding.py`.
3. Update `OnboardingViewModelTests.swift` — both `questionKeysCount` and `questionKeysMatchBackend` tests will fail if the arrays change.
4. The `answers` array size is derived from `questionKeys.count`, so `QuestionsView`'s `ForEach(0..<7, ...)` must also be updated if you add or remove questions.

### Replacing the Lottie animation assets

Drop production `.json` files into `ios/Ember/Resources/Animations/` using the exact filenames:
- `onboarding-welcome.json`
- `onboarding-memory.json`
- `onboarding-companion.json`

No code changes are needed. `WelcomeView` resolves assets by name at runtime, and `LottieAnimationViewWrapper` plays whatever file it finds.

### Adding a new welcome carousel page

1. Append a new `WelcomePage` struct to the `pages` array in `WelcomeView.swift`.
2. Update the page indicator `ForEach(0..<3, ...)` to the new total page count.
3. Update the "Skip" link condition (`currentWelcomePage < 2` becomes `currentWelcomePage < N-1`) and the CTA button condition accordingly.
4. Add the Lottie JSON asset to `ios/Ember/Resources/Animations/`.

### Testing a new submission error scenario

Add a test in `OnboardingViewModelTests.swift` following the existing pattern:

```swift
@Test("submitOnboarding handles <new scenario>")
func submitOnboardingNewScenario() async {
    let mockAPI = MockAPIClient()
    mockAPI.requestError = APIError.serverError(statusCode: <code>, detail: "<detail>")
    let vm = OnboardingViewModel(apiClient: mockAPI)
    vm.answers[0] = "Alex"

    let result = await vm.submitOnboarding()

    #expect(result == <expected>)
    #expect(vm.errorMessage <condition>)
}
```

---

## Related Documentation

- [Database Schema and API Contracts](../04-veri-api.md)
- [AI Memory System](../05-ai-bellek.md)
- [Mobile Screens and Navigation](../07-mobil.md)
- [Design System](../14-tasarim.md)
- [iOS Standards](../standards/ios.md)
- [iOS Scaffold](ios-scaffold.md)
- [iOS Network Layer](ios-network-layer.md)
- [iOS Cognito Auth](ios-cognito-auth.md)
- [Onboarding Backend Endpoint](onboarding-endpoint.md)
