import Foundation

/// A single Q&A pair from the onboarding flow.
/// Maps to the backend's `OnboardingAnswer` Pydantic model.
struct OnboardingAnswer: Codable {
    let questionKey: String
    let answer: String
}

/// Request body for `POST /api/v1/onboarding/complete`.
/// Maps to the backend's `OnboardingRequest` Pydantic model.
struct OnboardingRequest: Codable {
    let answers: [OnboardingAnswer]
}

/// Response from `POST /api/v1/onboarding/complete`.
/// Maps to the backend's `OnboardingResponse` Pydantic model.
struct OnboardingResponse: Codable {
    let onboardingCompleted: Bool
    let memoriesSeeded: Int
}
