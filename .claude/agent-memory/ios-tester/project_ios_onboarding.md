---
name: ios-onboarding test patterns
description: Patterns established during P03-04 iOS Onboarding testing — pbxproj group IDs, MockAPIClient usage for onboarding, JSON model testing
type: project
---

The onboarding feature (P03-04) uses `MockAPIClient` (from `ios/EmberTests/Mocks/MockAPIClient.swift`). Set `mockAPI.requestResult = OnboardingResponse(onboardingCompleted: true, memoriesSeeded: 7)` for success, `mockAPI.requestError = APIError.serverError(statusCode: 409, detail: "...")` for conflict. The `MockAPIClient.lastEndpoint` property tracks which endpoint was called — use a `case .completeOnboarding = endpoint` pattern to verify it.

Key test facts for onboarding:
- `submitOnboarding()` does NOT guard on `canSubmit` — that guard lives in the View. The method always calls the API.
- Whitespace-only answers become "Not provided" (the ViewModel trims before the isEmpty check).
- `skipCurrentQuestion()` on index 6 dispatches `Task { await submitOnboarding() }` — not directly awaitable in tests; only verify that `answers[6]` is cleared and `currentQuestionIndex` stays 6.
- `APIError.serverError(statusCode: 409, ...)` → returns `true`, `errorMessage` stays `nil`.
- `NSError` (non-`APIError`) → `errorMessage == "Something went wrong. Please try again."`.
- `JSONEncoder.ember` / `JSONDecoder.ember` convert `questionKey` ↔ `question_key` automatically.

pbxproj IDs for onboarding tests:
- Onboarding test group: `B02BF5137F841D865FE344DB`
- Sources build phase: `91FC9734A1965EA61C9B43FF`

**Why:** First feature with a dedicated model test file (`OnboardingModelsTests`) that exercises the JSON snake_case contract directly against `JSONEncoder.ember`.

**How to apply:** For any future feature with Codable models, write a separate `*ModelsTests.swift` that encodes and decodes using `JSONEncoder.ember`/`JSONDecoder.ember` and asserts on the raw JSON keys (via `JSONSerialization`) to catch snake_case regressions.
