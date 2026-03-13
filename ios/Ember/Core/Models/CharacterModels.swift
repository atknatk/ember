import Foundation

/// Maps to the backend's `CharacterListItem` Pydantic schema.
/// Decoded with `JSONDecoder.ember` (snake_case -> camelCase).
struct Character: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let template: String
    let description: String?
    let avatarStyle: String
    let isDefault: Bool
    let lastMessageAt: Date?
    let createdAt: Date
}

/// Response from `GET /api/v1/characters`.
struct CharacterListResponse: Codable {
    let characters: [Character]
}
