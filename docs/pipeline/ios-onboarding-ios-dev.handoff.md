# iOS Dev Handoff: iOS Onboarding

**Date**: 2026-03-13
**Agent**: ios-dev
**Status**: COMPLETE

## Implemented Files

### files_created
- `ios/Ember/Features/Onboarding/OnboardingFlowView.swift`
- `ios/Ember/Features/Onboarding/OnboardingViewModel.swift`
- `ios/Ember/Features/Onboarding/WelcomeView.swift`
- `ios/Ember/Features/Onboarding/QuestionsView.swift`
- `ios/Ember/Features/Onboarding/LottieAnimationViewWrapper.swift`
- `ios/Ember/Core/Models/OnboardingModels.swift`
- `ios/Ember/Resources/Animations/onboarding-welcome.json`
- `ios/Ember/Resources/Animations/onboarding-memory.json`
- `ios/Ember/Resources/Animations/onboarding-companion.json`
- `ios/EmberTests/Features/Onboarding/OnboardingViewModelTests.swift`

### files_modified
- `ios/Ember/App/EmberApp.swift` (replaced `OnboardingPlaceholderView()` with `OnboardingFlowView()`)

### files_deleted
- `ios/Ember/Features/Auth/OnboardingPlaceholderView.swift`

## Screens Implemented

- **OnboardingFlowView**: Top-level container routing between welcome and questions phases via `OnboardingViewModel.Phase`
- **WelcomeView**: 3-page horizontal swipe carousel with Lottie animations (graceful fallback to SF Symbols), custom page indicator dots, "Next"/"Get Started" CTA buttons, and "Skip" link
- **QuestionsView**: 7 full-screen question cards with progress bar, text input, skip/back/next navigation, and submit with loading state

## Deviations from Spec

- The `skipCurrentQuestion()` method on the ViewModel was simplified: when on the last question (index 6), skipping triggers submission via a `Task` block directly in the `QuestionsView` rather than calling the ViewModel's `skipCurrentQuestion()`, to keep the `onComplete` callback in the View layer (since `@AppStorage` writes must happen in Views).
- Lottie JSON files are minimal placeholder animations (rotating sparkle, pulsing circle, heartbeat). They should be replaced with production-quality animations from LottieFiles.com before ship.
- `QuestionsView` uses `TabView` with `.disabled(true)` to prevent swipe gesture, as specified.

## Notes for iOS Tester

- **ViewModel testing**: Use `MockAPIClient` (from `ios/EmberTests/Mocks/MockAPIClient.swift`). Set `requestResult = OnboardingResponse(onboardingCompleted: true, memoriesSeeded: 7)` for success cases, or `requestError = APIError.serverError(statusCode: 409, detail: "...")` for conflict cases.
- **Test `submitOnboarding()`**: Returns `Bool` -- `true` on success or 409, `false` on other errors. Verify `isSubmitting` transitions and `errorMessage` state.
- **Test `skipCurrentQuestion()`**: On indices 0-5, clears the answer and advances. On index 6, it triggers submission (but in the View layer, not via the ViewModel's skip method directly -- test the ViewModel's `advanceToNextQuestion` boundary at index 6 separately).
- **Test question key mapping**: `OnboardingViewModel.questionKeys` must match `VALID_QUESTION_KEYS` in `backend/app/schemas/onboarding.py`.
- **Skipped answers**: When an answer is blank, "Not provided" is sent to the backend (required by `min_length=1`).
- **409 handling**: `APIError.serverError(statusCode: 409, ...)` is treated as success -- verify the ViewModel returns `true` and does not set `errorMessage`.
- **Lottie fallback**: If the Lottie JSON files are removed from the bundle, WelcomeView should gracefully show SF Symbol fallbacks instead.
- **Accessibility**: Verify all buttons have `accessibilityLabel`, Lottie views are `accessibilityHidden(true)`, and progress text announces "Question N of 7".
