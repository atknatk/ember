import Testing
import Foundation
@testable import Ember

// MARK: - ChatService Tests

/// Tests for `ChatService` — verifies that the service layer correctly
/// delegates to `APIClientProtocol` with the expected endpoints and bodies.

@Suite("ChatService")
struct ChatServiceTests {

    // MARK: - Helpers

    private func makeService(mock: MockAPIClient = MockAPIClient()) -> (ChatService, MockAPIClient) {
        let service = ChatService(apiClient: mock)
        return (service, mock)
    }

    private func makeMessage(
        id: String = UUID().uuidString,
        role: String = "assistant",
        content: String = "Hi"
    ) -> Message {
        Message(id: id, role: role, content: content, mediaUrl: nil, metadata: nil, createdAt: Date())
    }

    // MARK: - loadMessages

    @Test("loadMessages: uses .listMessages endpoint")
    func loadMessagesUsesCorrectEndpoint() async throws {
        let (service, mock) = makeService()
        mock.requestResult = ChatMessageListResponse(items: [], nextCursor: nil, hasMore: false)

        _ = try await service.loadMessages(characterId: "char_1", cursor: nil, limit: 20)

        if case .listMessages(let id, _, _) = mock.lastEndpoint {
            #expect(id == "char_1")
        } else {
            Issue.record("Expected .listMessages endpoint, got \(String(describing: mock.lastEndpoint))")
        }
    }

    @Test("loadMessages: passes cursor when provided")
    func loadMessagesPassesCursor() async throws {
        let (service, mock) = makeService()
        mock.requestResult = ChatMessageListResponse(items: [], nextCursor: nil, hasMore: false)

        _ = try await service.loadMessages(characterId: "char_1", cursor: "cursor_abc", limit: 20)

        if case .listMessages(_, let cursor, _) = mock.lastEndpoint {
            #expect(cursor == "cursor_abc")
        } else {
            Issue.record("Expected .listMessages endpoint")
        }
    }

    @Test("loadMessages: passes nil cursor for initial load")
    func loadMessagesPassesNilCursor() async throws {
        let (service, mock) = makeService()
        mock.requestResult = ChatMessageListResponse(items: [], nextCursor: nil, hasMore: false)

        _ = try await service.loadMessages(characterId: "char_1", cursor: nil, limit: 20)

        if case .listMessages(_, let cursor, _) = mock.lastEndpoint {
            #expect(cursor == nil)
        } else {
            Issue.record("Expected .listMessages endpoint")
        }
    }

    @Test("loadMessages: passes limit parameter")
    func loadMessagesPassesLimit() async throws {
        let (service, mock) = makeService()
        mock.requestResult = ChatMessageListResponse(items: [], nextCursor: nil, hasMore: false)

        _ = try await service.loadMessages(characterId: "char_1", cursor: nil, limit: 30)

        if case .listMessages(_, _, let limit) = mock.lastEndpoint {
            #expect(limit == 30)
        } else {
            Issue.record("Expected .listMessages endpoint")
        }
    }

    @Test("loadMessages: returns decoded ChatMessageListResponse")
    func loadMessagesReturnsDecodedResponse() async throws {
        let (service, mock) = makeService()
        let preview = makeMessage(id: "m1", role: "user", content: "Hello")
        let page = ChatMessageListResponse(items: [preview], nextCursor: "next_cursor", hasMore: true)
        mock.requestResult = page

        let result = try await service.loadMessages(characterId: "char_1", cursor: nil, limit: 20)

        #expect(result.items.count == 1)
        #expect(result.items[0].id == "m1")
        #expect(result.nextCursor == "next_cursor")
        #expect(result.hasMore == true)
    }

    @Test("loadMessages: propagates network error")
    func loadMessagesNetworkError() async {
        let (service, mock) = makeService()
        mock.requestError = APIError.networkError(
            NSError(domain: "NSURLErrorDomain", code: -1009, userInfo: nil)
        )

        do {
            _ = try await service.loadMessages(characterId: "char_1", cursor: nil, limit: 20)
            Issue.record("Expected error to be thrown")
        } catch {
            #expect(error is APIError)
        }
    }

    @Test("loadMessages: propagates server error")
    func loadMessagesServerError() async {
        let (service, mock) = makeService()
        mock.requestError = APIError.serverError(statusCode: 403, detail: "Forbidden")

        do {
            _ = try await service.loadMessages(characterId: "char_1", cursor: nil, limit: 20)
            Issue.record("Expected error to be thrown")
        } catch let error as APIError {
            if case .serverError(let code, _) = error {
                #expect(code == 403)
            } else {
                Issue.record("Expected .serverError")
            }
        } catch {
            Issue.record("Unexpected error type: \(error)")
        }
    }

    @Test("loadMessages: propagates unauthorized error")
    func loadMessagesUnauthorized() async {
        let (service, mock) = makeService()
        mock.requestError = APIError.unauthorized

        do {
            _ = try await service.loadMessages(characterId: "char_1", cursor: nil, limit: 20)
            Issue.record("Expected error to be thrown")
        } catch let error as APIError {
            #expect(error == .unauthorized)
        } catch {
            Issue.record("Unexpected error type")
        }
    }

    // MARK: - streamMessage

    @Test("streamMessage: uses .streamMessage endpoint with characterId")
    func streamMessageUsesCorrectEndpoint() async throws {
        let (service, mock) = makeService()
        mock.sseEvents = []

        let stream = service.streamMessage(characterId: "char_2", content: "Hello")
        // Consume the stream to trigger the call
        for try await _ in stream {}

        if case .streamMessage(let id) = mock.lastEndpoint {
            #expect(id == "char_2")
        } else {
            Issue.record("Expected .streamMessage endpoint, got \(String(describing: mock.lastEndpoint))")
        }
    }

    @Test("streamMessage: yields chunk events from the SSE stream")
    func streamMessageYieldsChunks() async throws {
        let (service, mock) = makeService()
        mock.sseEvents = [
            .chunk(content: "Hello"),
            .chunk(content: " world"),
            .done(messageId: "m1"),
        ]

        var received: [SSEEvent] = []
        let stream = service.streamMessage(characterId: "char_1", content: "Hi")
        for try await event in stream {
            received.append(event)
        }

        #expect(received.count == 3)
        if case .chunk(let text) = received[0] {
            #expect(text == "Hello")
        }
        if case .chunk(let text) = received[1] {
            #expect(text == " world")
        }
        if case .done(let msgId) = received[2] {
            #expect(msgId == "m1")
        }
    }

    @Test("streamMessage: propagates error from SSE stream")
    func streamMessagePropagatesError() async {
        let (service, mock) = makeService()
        mock.requestError = APIError.networkError(
            NSError(domain: "test", code: -1, userInfo: nil)
        )

        do {
            let stream = service.streamMessage(characterId: "char_1", content: "Hi")
            for try await _ in stream {}
            Issue.record("Expected error to be thrown")
        } catch {
            #expect(error is APIError)
        }
    }

    @Test("streamMessage: empty SSE stream finishes without error")
    func streamMessageEmptyStream() async throws {
        let (service, mock) = makeService()
        mock.sseEvents = []

        var count = 0
        let stream = service.streamMessage(characterId: "char_1", content: "Hello")
        for try await _ in stream {
            count += 1
        }

        #expect(count == 0)
    }

    @Test("streamMessage: calls streamSSE (not request) on apiClient")
    func streamMessageUsesStreamSSE() async throws {
        let (service, mock) = makeService()
        mock.sseEvents = []

        let stream = service.streamMessage(characterId: "char_1", content: "test")
        for try await _ in stream {}

        #expect(mock.streamCallCount == 1)
        #expect(mock.requestCallCount == 0)
    }

    @Test("loadMessages: calls request (not streamSSE) on apiClient")
    func loadMessagesUsesRequest() async throws {
        let (service, mock) = makeService()
        mock.requestResult = ChatMessageListResponse(items: [], nextCursor: nil, hasMore: false)

        _ = try await service.loadMessages(characterId: "char_1", cursor: nil, limit: 20)

        #expect(mock.requestCallCount == 1)
        #expect(mock.streamCallCount == 0)
    }
}
