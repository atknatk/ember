import Foundation

/// HTTP method enum for type-safe endpoint definitions.
enum HTTPMethod: String {
    case get = "GET"
    case post = "POST"
    case put = "PUT"
    case delete = "DELETE"
}

/// Type-safe enum encapsulating all backend API endpoints.
/// New features add cases here without touching `APIClientProtocol`.
enum APIEndpoint {
    // Auth (public, no token needed)
    case register
    case login
    case refreshToken

    // Characters
    case listCharacters
    case createCharacter
    case updateCharacter(id: String)
    case deleteCharacter(id: String)

    // Chat
    case sendMessage(characterId: String)
    case streamMessage(characterId: String)
    case listMessages(characterId: String, cursor: String?, limit: Int)

    // Memories
    case listMemories(characterId: String)
    case deleteMemory(characterId: String, memoryId: String)
    case deleteAllMemories(characterId: String)

    // Media
    case uploadURL

    // Profile
    case getProfile
    case updateProfile
    case deleteAccount

    // Onboarding
    case completeOnboarding

    // Notifications
    case updateFCMToken
    case updateNotificationPreferences

    /// The URL path component. All paths are prefixed with `/api/v1/`.
    var path: String {
        switch self {
        // Auth
        case .register:
            return "/api/v1/auth/register"
        case .login:
            return "/api/v1/auth/login"
        case .refreshToken:
            return "/api/v1/auth/refresh"

        // Characters
        case .listCharacters, .createCharacter:
            return "/api/v1/characters"
        case .updateCharacter(let id), .deleteCharacter(let id):
            return "/api/v1/characters/\(id)"

        // Chat
        case .sendMessage(let characterId), .streamMessage(let characterId):
            return "/api/v1/characters/\(characterId)/messages"
        case .listMessages(let characterId, _, _):
            return "/api/v1/characters/\(characterId)/messages"

        // Memories
        case .listMemories(let characterId):
            return "/api/v1/characters/\(characterId)/memories"
        case .deleteMemory(let characterId, let memoryId):
            return "/api/v1/characters/\(characterId)/memories/\(memoryId)"
        case .deleteAllMemories(let characterId):
            return "/api/v1/characters/\(characterId)/memories"

        // Media
        case .uploadURL:
            return "/api/v1/media/upload-url"

        // Profile
        case .getProfile, .updateProfile:
            return "/api/v1/profile"
        case .deleteAccount:
            return "/api/v1/profile/account"

        // Onboarding
        case .completeOnboarding:
            return "/api/v1/onboarding/complete"

        // Notifications
        case .updateFCMToken:
            return "/api/v1/notifications/fcm-token"
        case .updateNotificationPreferences:
            return "/api/v1/notifications/preferences"
        }
    }

    /// The HTTP method for this endpoint.
    var method: HTTPMethod {
        switch self {
        case .register, .login, .refreshToken,
             .createCharacter,
             .sendMessage, .streamMessage,
             .uploadURL,
             .completeOnboarding,
             .updateFCMToken:
            return .post

        case .listCharacters,
             .listMessages,
             .listMemories,
             .getProfile:
            return .get

        case .updateCharacter, .updateProfile, .updateNotificationPreferences:
            return .put

        case .deleteCharacter, .deleteMemory, .deleteAllMemories, .deleteAccount:
            return .delete
        }
    }

    /// Whether this endpoint requires an `Authorization: Bearer` header.
    /// Returns `false` for public auth endpoints, `true` for all others.
    var requiresAuth: Bool {
        switch self {
        case .register, .login, .refreshToken:
            return false
        default:
            return true
        }
    }

    /// Query parameters for endpoints that need them. Returns `nil` when no query params.
    var queryItems: [URLQueryItem]? {
        switch self {
        case .listMessages(_, let cursor, let limit):
            var items: [URLQueryItem] = [
                URLQueryItem(name: "limit", value: "\(limit)")
            ]
            if let cursor {
                items.append(URLQueryItem(name: "cursor", value: cursor))
            }
            return items
        default:
            return nil
        }
    }
}
