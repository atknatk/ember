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

    /// Requests a presigned upload URL from the backend.
    func getUploadURL(request: UploadURLRequest) async throws -> UploadURLResponse

    /// Uploads raw file data to a presigned S3 URL.
    func uploadFile(to url: URL, data: Data, contentType: String) async throws

    /// Sends an audio URL to the STT endpoint for transcription.
    func transcribeAudio(request: STTRequest) async throws -> STTResponse
}

// MARK: - Chat Service

/// Production implementation backed by `APIClientProtocol`.
final class ChatService: ChatServiceProtocol {
    private let apiClient: APIClientProtocol
    private let urlSession: URLSession

    init(apiClient: APIClientProtocol = APIClient.shared, urlSession: URLSession = .shared) {
        self.apiClient = apiClient
        self.urlSession = urlSession
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

    func getUploadURL(request: UploadURLRequest) async throws -> UploadURLResponse {
        try await apiClient.request(
            endpoint: .uploadURL,
            body: request,
            responseType: UploadURLResponse.self
        )
    }

    func uploadFile(to url: URL, data: Data, contentType: String) async throws {
        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        request.httpBody = data
        request.setValue(contentType, forHTTPHeaderField: "Content-Type")

        let (_, response) = try await urlSession.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            let statusCode = (response as? HTTPURLResponse)?.statusCode ?? 0
            throw APIError.serverError(statusCode: statusCode, detail: "File upload failed")
        }
    }

    func transcribeAudio(request: STTRequest) async throws -> STTResponse {
        try await apiClient.request(
            endpoint: .transcribeAudio,
            body: request,
            responseType: STTResponse.self
        )
    }
}

// MARK: - Request Body

/// Request body for `POST /api/v1/characters/:id/messages`.
private struct SendMessageBody: Encodable {
    let content: String
}
