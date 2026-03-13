import Foundation

/// Response from `POST /api/v1/auth/login` and `POST /api/v1/auth/register`.
/// Decoded with `JSONDecoder.ember` (snake_case -> camelCase).
struct AuthResponse: Codable {
    let token: String
    let refreshToken: String
    let user: UserResponse
}

/// User profile data returned inside `AuthResponse`.
struct UserResponse: Codable, Identifiable {
    let id: String
    let email: String
    let name: String
    let avatarUrl: String?
    let timezone: String
    let preferredLanguage: String
    let onboardingCompleted: Bool
    let subscriptionTier: String
    let createdAt: String
}

/// Response from `POST /api/v1/auth/refresh`.
struct RefreshResponse: Codable {
    let token: String
}
