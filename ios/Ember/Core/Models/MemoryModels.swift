import Foundation

/// A single memory item from the Mem0 memory layer.
/// Maps to the backend's `MemoryItem` Pydantic schema.
/// Decoded with `JSONDecoder.ember` (snake_case -> camelCase).
struct MemoryItem: Codable, Identifiable, Equatable {
    let id: String
    let memory: String
    let createdAt: Date?
}

/// Response from `GET /api/v1/characters/:id/memories` and `GET /api/v1/memories`.
/// Maps to the backend's `MemoryListResponse` Pydantic schema.
struct MemoryListResponse: Codable {
    let memories: [MemoryItem]
}
