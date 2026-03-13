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
}
