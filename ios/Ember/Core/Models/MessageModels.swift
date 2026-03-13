import Foundation

/// Lightweight message preview for displaying the most recent message per character.
/// Fetched via `GET /api/v1/characters/:id/messages?limit=1`.
struct MessagePreview: Codable, Identifiable {
    let id: String
    let role: String
    let content: String
    let createdAt: Date
}

/// Paginated response from `GET /api/v1/characters/:id/messages`.
struct MessageListResponse: Codable {
    let items: [MessagePreview]
    let nextCursor: String?
    let hasMore: Bool
}
