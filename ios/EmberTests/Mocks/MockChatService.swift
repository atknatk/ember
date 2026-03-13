import Foundation
@testable import Ember

/// Fake implementation of `ChatServiceProtocol` for ViewModel unit tests.
///
/// Configure before each test:
/// - `stubbedPage` — returned by `loadMessages`
/// - `stubbedSSEEvents` — yielded by `streamMessage`
/// - `shouldThrow` — causes both methods to throw when set
///
/// Inspect after each test:
/// - `loadMessagesCallCount`, `lastCursor`, `lastLimit`
/// - `streamMessageCallCount`, `lastStreamContent`
final class MockChatService: ChatServiceProtocol, @unchecked Sendable {

    // MARK: - Stubs

    var stubbedPage: ChatMessageListResponse = ChatMessageListResponse(items: [], nextCursor: nil, hasMore: false)
    var stubbedSSEEvents: [SSEEvent] = []
    var shouldThrow: Error? = nil

    // MARK: - Call Tracking

    var loadMessagesCallCount: Int = 0
    var lastCharacterId: String? = nil
    var lastCursor: String? = nil
    var lastLimit: Int = 0

    var streamMessageCallCount: Int = 0
    var lastStreamContent: String? = nil

    // MARK: - ChatServiceProtocol

    func loadMessages(
        characterId: String,
        cursor: String?,
        limit: Int
    ) async throws -> ChatMessageListResponse {
        loadMessagesCallCount += 1
        lastCharacterId = characterId
        lastCursor = cursor
        lastLimit = limit
        if let error = shouldThrow { throw error }
        return stubbedPage
    }

    func streamMessage(
        characterId: String,
        content: String
    ) -> AsyncThrowingStream<SSEEvent, Error> {
        streamMessageCallCount += 1
        lastStreamContent = content

        let events = stubbedSSEEvents
        let error = shouldThrow
        return AsyncThrowingStream { continuation in
            Task {
                if let error {
                    continuation.finish(throwing: error)
                    return
                }
                for event in events {
                    continuation.yield(event)
                    // Small sleep to let the consumer process each event
                    try? await Task.sleep(nanoseconds: 1_000_000)
                }
                continuation.finish()
            }
        }
    }

    // MARK: - Voice Recording Stubs

    var stubbedUploadURLResponse: UploadURLResponse = UploadURLResponse(uploadUrl: "https://s3.example.com/upload", fileUrl: "https://s3.example.com/file.m4a")
    var stubbedSTTResponse: STTResponse = STTResponse(transcript: "Hello world", language: "en", confidence: 0.95, durationSeconds: 2.5)

    var getUploadURLCallCount: Int = 0
    var uploadFileCallCount: Int = 0
    var transcribeAudioCallCount: Int = 0
    var lastUploadURL: URL? = nil
    var lastTranscribeRequest: STTRequest? = nil

    func getUploadURL(request: UploadURLRequest) async throws -> UploadURLResponse {
        getUploadURLCallCount += 1
        if let error = shouldThrow { throw error }
        return stubbedUploadURLResponse
    }

    func uploadFile(to url: URL, data: Data, contentType: String) async throws {
        uploadFileCallCount += 1
        lastUploadURL = url
        if let error = shouldThrow { throw error }
    }

    func transcribeAudio(request: STTRequest) async throws -> STTResponse {
        transcribeAudioCallCount += 1
        lastTranscribeRequest = request
        if let error = shouldThrow { throw error }
        return stubbedSTTResponse
    }
}
