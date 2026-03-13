import Foundation

// MARK: - Chat Service Protocol

/// Protocol for chat-related network operations.
/// Decouples `ChatViewModel` from `APIClient` for testability.
protocol ChatServiceProtocol: Sendable {
    /// Loads message history using cursor-based pagination.
    /// Messages are returned newest-first from the API; the caller reverses them.
    func loadMessages(
        characterId: String,
        cursor: String?,
        limit: Int
    ) async throws -> ChatMessageListResponse

    /// Opens an SSE stream for sending a message and receiving the AI response.
    func streamMessage(
        characterId: String,
        content: String
    ) -> AsyncThrowingStream<SSEEvent, Error>
}

// MARK: - Chat Service

/// Production implementation backed by `APIClientProtocol`.
final class ChatService: ChatServiceProtocol {
    private let apiClient: APIClientProtocol

    init(apiClient: APIClientProtocol = APIClient.shared) {
        self.apiClient = apiClient
    }

    func loadMessages(
        characterId: String,
        cursor: String?,
        limit: Int
    ) async throws -> ChatMessageListResponse {
        try await apiClient.request(
            endpoint: .listMessages(characterId: characterId, cursor: cursor, limit: limit),
            responseType: ChatMessageListResponse.self
        )
    }

    func streamMessage(
        characterId: String,
        content: String
    ) -> AsyncThrowingStream<SSEEvent, Error> {
        apiClient.streamSSE(
            endpoint: .streamMessage(characterId: characterId),
            body: SendMessageBody(content: content)
        )
    }
}

// MARK: - Request Body

/// Request body for `POST /api/v1/characters/:id/messages`.
private struct SendMessageBody: Encodable {
    let content: String
}
