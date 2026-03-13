# Architect Handoff: iOS Onboarding

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## What Was Designed

The full iOS onboarding flow consisting of two screens: a 3-page WelcomeView carousel with Lottie animations and page indicator dots, and a 7-card QuestionsView that collects personalization answers and submits them to the existing `POST /api/v1/onboarding/complete` endpoint. An `@Observable OnboardingViewModel` manages both phases, answer state, validation, and API submission. The feature replaces the existing `OnboardingPlaceholderView` stub.

## Key Decisions

- **No Amplify dependency**: The onboarding endpoint is called via the existing `APIClient` and `APIEndpoint.completeOnboarding` case. No new SDK dependencies.
- **Skipped answers use "Not provided"**: The backend requires all 7 answers with `min_length=1`. When a user skips a question, the answer is sent as the literal string "Not provided" rather than omitting it.
- **409 treated as success**: If the backend returns 409 (onboarding already completed), the iOS app treats it as success and proceeds to the main app. This handles edge cases where the user's device loses connectivity after the backend commits but before the client receives the response.
- **Lottie graceful degradation**: Each welcome page has a fallback SF Symbol if the Lottie JSON file is not found in the bundle. This avoids a hard dependency on animation assets.
- **Swipe disabled on QuestionsView**: Question cards use a TabView but swiping is disabled to prevent accidental navigation while typing. Navigation is controlled by explicit "Next"/"Back" buttons only.
- **`@AppStorage` write stays in the View layer**: The ViewModel returns a Bool from `submitOnboarding()` rather than writing `@AppStorage` directly, since `@AppStorage` is a SwiftUI property wrapper that belongs in Views, not in `@Observable` classes.

## Spec Location

`shared/feature-specs/ios-onboarding.md`

## Assumptions Made

- The Lottie SPM package is already added to the Xcode project from P03-01 scaffold setup.
- The `MockAPIClient` from P03-02 can be extended to handle the `.completeOnboarding` endpoint for tests.
- The `AuthTextFieldStyle` view modifier from `LoginView.swift` is reusable for the question card text fields (same styling).
- Lottie animation JSON files will be sourced from LottieFiles.com or created as custom assets. The spec defines placeholder asset names but does not mandate specific animation content.

## Dependencies

- Requires: P03-03 (ios-cognito-auth), P03-02 (ios-network-layer), P03-01 (ios-scaffold), P01-09 (onboarding-endpoint)
- Blocks: ios-dev (implements from this spec), ios-tester (tests from this spec)

## Next Steps

ios-dev should read the spec and implement the feature. ios-tester should write tests after implementation.
