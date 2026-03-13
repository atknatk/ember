import Foundation

/// Maps to the backend's `ProfileResponse` Pydantic schema.
/// Decoded with `JSONDecoder.ember` (snake_case -> camelCase).
struct ProfileData: Codable, Identifiable {
    let id: String
    let email: String
    let name: String
    let timezone: String
    let avatarUrl: String?
    let preferredLanguage: String
    let onboardingCompleted: Bool
    let subscriptionTier: String
    let subscriptionExpiresAt: Date?
    let createdAt: Date
}

/// Request body for `PUT /api/v1/profile`.
/// Only non-nil fields are sent in the request body.
struct ProfileUpdateBody: Encodable {
    var name: String?
    var timezone: String?
    var avatarUrl: String?
    var preferredLanguage: String?
}

/// Request body for `DELETE /api/v1/profile/account`.
struct AccountDeleteBody: Encodable {
    let confirmation: String
}

/// Request body for `POST /api/v1/media/upload-url`.
struct UploadURLRequest: Encodable {
    let filename: String
    let contentType: String
    let type: String
}

/// Response from `POST /api/v1/media/upload-url`.
struct UploadURLResponse: Codable {
    let uploadUrl: String
    let fileUrl: String
}
