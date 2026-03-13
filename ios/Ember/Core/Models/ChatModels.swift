import Foundation

/// Full message model for the chat view.
/// Richer than `MessagePreview` (used by HomeView) -- includes `mediaUrl` and `metadata`.
struct Message: Codable, Identifiable, Equatable {
    let id: String
    let role: String
    var content: String
    let mediaUrl: String?
    let metadata: MessageMetadata?
    let createdAt: Date
}

/// Optional metadata attached to assistant messages (e.g., detected device action intents).
struct MessageMetadata: Codable, Equatable {
    let action: String?
    let payload: [String: String]?
}

/// Paginated response from `GET /api/v1/characters/:id/messages` for the chat view.
/// Uses `Message` items (not `MessagePreview`) since the chat needs `mediaUrl` and `metadata`.
struct ChatMessageListResponse: Codable {
    let items: [Message]
    let nextCursor: String?
    let hasMore: Bool
}
