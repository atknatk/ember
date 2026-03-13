# Reviewer Handoff: iOS Onboarding

**Date**: 2026-03-13
**Agent**: reviewer
**Status**: APPROVED

## Review Summary

| Category | Passed | Warnings | Issues |
|----------|--------|----------|--------|
| Architecture | 4 | 0 | 0 |
| iOS Code Quality | 9 | 0 | 0 |
| Testing | 7 | 0 | 0 |
| Security | 2 | 0 | 0 |
| **Total** | **22** | **1** | **0** |

## Files Reviewed

**iOS Implementation**:
- `ios/Ember/Features/Onboarding/OnboardingFlowView.swift` -- PASS
- `ios/Ember/Features/Onboarding/OnboardingViewModel.swift` -- PASS
- `ios/Ember/Features/Onboarding/WelcomeView.swift` -- PASS
- `ios/Ember/Features/Onboarding/QuestionsView.swift` -- PASS
- `ios/Ember/Features/Onboarding/LottieAnimationViewWrapper.swift` -- PASS
- `ios/Ember/Core/Models/OnboardingModels.swift` -- PASS
- `ios/Ember/App/EmberApp.swift` -- PASS

**Test Files**:
- `ios/EmberTests/Features/Onboarding/OnboardingViewModelTests.swift` -- PASS (20 tests)
- `ios/EmberTests/Features/Onboarding/OnboardingViewModelExtendedTests.swift` -- PASS (~35 tests, edge cases)
- `ios/EmberTests/Features/Onboarding/OnboardingModelsTests.swift` -- PASS (~16 tests, Codable round-trips)
- `ios/EmberTests/Mocks/MockAPIClient.swift` -- PASS (protocol-based mock)

**Lottie Assets**:
- `ios/Ember/Resources/Animations/onboarding-welcome.json` -- PASS (exists)
- `ios/Ember/Resources/Animations/onboarding-memory.json` -- PASS (exists)
- `ios/Ember/Resources/Animations/onboarding-companion.json` -- PASS (exists)

## Architecture Compliance

- [x] **@Observable used**: `OnboardingViewModel` uses `@Observable` macro. No `ObservableObject`, `@Published`, or `@StateObject` anywhere in onboarding files.
- [x] **No NavigationView**: No `NavigationView` references. Onboarding uses `TabView` for paging, not navigation stacks.
- [x] **Dark mode preserved**: `EmberApp.swift` still has `.preferredColorScheme(.dark)`. All views use `Color.emberBackground`.
- [x] **Spec adherence**: All screens from spec are implemented. `OnboardingPlaceholderView` deleted. `EmberApp.swift` updated to use `OnboardingFlowView`.

## iOS Code Quality

- [x] **No force unwrap**: No `!` on optionals. All `!` occurrences are logical NOT operators.
- [x] **No hardcoded colors**: All colors use `Color.ember*` constants. No `Color(red:)` or `UIColor()`.
- [x] **No hardcoded secrets**: No API keys, tokens, or credentials in code.
- [x] **No print statements**: No `print()` in production code.
- [x] **SF Symbols for icons**: Fallback symbols use `Image(systemName:)`. `EmberSymbol.back` used for chevron.
- [x] **Accessibility labels**: All buttons have `.accessibilityLabel()`: "Next page", "Get Started", "Skip to last welcome page", "Skip this question", "Go to previous question", "Go to next question", "Submit onboarding answers". Progress text has `.accessibilityLabel("Question N of 7")`. TextField has `.accessibilityLabel("Answer for question N")`.
- [x] **Lottie accessibilityHidden**: Both Lottie and fallback SF Symbol views have `.accessibilityHidden(true)`.
- [x] **Page indicator accessibilityHidden**: Page dots have `.accessibilityHidden(true)`.
- [x] **Service protocol**: `OnboardingViewModel` depends on `APIClientProtocol`, not `APIClient` directly. Constructor injection with default parameter.

## Key Spec Compliance

- [x] **409 treated as success**: `OnboardingViewModel.submitOnboarding()` line 139 catches `APIError.serverError` with statusCode 409 and returns `true`.
- [x] **Skipped answers sent as "Not provided"**: Line 122 maps empty/whitespace answers to "Not provided" string.
- [x] **Lottie graceful fallback**: `WelcomeView` checks `Bundle.main.url(forResource:withExtension:)` and shows SF Symbol if Lottie JSON is missing.
- [x] **Swipe disabled on QuestionsView**: `TabView` has `.disabled(true)` to prevent accidental swipe.
- [x] **@AppStorage write in View layer**: `OnboardingFlowView` holds `@AppStorage("hasCompletedOnboarding")` and sets it via `onComplete` closure. ViewModel returns `Bool` from `submitOnboarding()`.
- [x] **Question keys match backend**: 7 keys match `VALID_QUESTION_KEYS` in `backend/app/schemas/onboarding.py`. Tests verify this.
- [x] **Haptic feedback**: Selection haptic on page changes, medium impact on "Get Started" and "Submit", success/error notification haptics on submission result.

## Test Quality

- [x] **~71 tests across 3 test files**: Base ViewModel tests (20), extended ViewModel tests (~35 edge cases), model Codable tests (~16 encoding/decoding round-trips).
- [x] **Protocol-based mock**: Uses `MockAPIClient` conforming to `APIClientProtocol`.
- [x] **Swift Testing framework**: All test files use `@Suite`, `@Test`, `#expect` (not XCTest).
- [x] **Error paths tested**: 409 (success), 401, 500, 503, network error, generic non-API error all covered.
- [x] **No real API calls**: All tests use `MockAPIClient`.
- [x] **"Not provided" fallback tested**: Extended tests verify behavior with empty, whitespace-only, and mixed answers.
- [x] **Model encoding verified**: OnboardingModelsTests verify snake_case encoding matches backend contract (`question_key`, not `questionKey`).

## Security

- [x] **No credentials in code**: Grep for `api_key`, `secret`, `password`, `Bearer` found no hardcoded values.
- [x] **No UserDefaults for auth**: `@AppStorage("hasCompletedOnboarding")` is a non-sensitive boolean flag, not credentials. No `UserDefaults` access for sensitive data.

## Issues Resolved During Review

- None (first-pass clean)

## Warnings (Not Blocking)

1. **Dead code in ViewModel `skipCurrentQuestion()` for index 6** -- The ViewModel's `skipCurrentQuestion()` handles index 6 by calling `Task { await submitOnboarding() }`, but the View handles skip-on-last-question directly (QuestionsView lines 127-135) to keep `onComplete` in the View layer. The ViewModel path for index 6 would submit but never trigger `onComplete`. This is documented in the dev handoff and is not a bug since the View-side code is the one actually called. Consider removing the index 6 branch from the ViewModel's `skipCurrentQuestion()` in a future cleanup to avoid confusion.
