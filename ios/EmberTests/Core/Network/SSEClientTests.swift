import Testing
import Foundation
@testable import Ember

/// Tests for SSE event parsing via SSEDelegate and APIClient.streamSSE.
@Suite("SSEClient")
struct SSEClientTests {

    // MARK: - Test Helpers

    /// Creates an APIClient configured with MockURLProtocol for SSE testing.
    private func makeClient() -> APIClient {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockURLProtocol.self]
        let session = URLSession(configuration: config)
        let baseURL = URL(string: "https://test.ember.ai")!
        let authService = MockAuthService()
        return APIClient(baseURL: baseURL, session: session, authService: authService)
    }

    /// Helper to build SSE data lines.
    private func sseData(_ events: [String]) -> Data {
        events.map { "data: \($0)\n\n" }.joined().data(using: .utf8)!
    }

    // MARK: - Chunk Events

    @Test("stream with three chunk events and done yields correctly")
    func streamChunksAndDone() async throws {
        let client = makeClient()
        let sseText = """
        data: {"type":"chunk","content":"Hello"}\n
        \n
        data: {"type":"chunk","content":" world"}\n
        \n
        data: {"type":"chunk","content":"!"}\n
        \n
        data: {"type":"done","message_id":"msg-123"}\n
        \n
        """

        MockURLProtocol.requestHandler = { request in
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "text/event-stream"]
            )!
            return (response, sseText.data(using: .utf8))
        }

        var events: [SSEEvent] = []
        let stream = client.streamSSE(
            endpoint: .streamMessage(characterId: "abc"),
            body: nil
        )

        for try await event in stream {
            events.append(event)
        }

        #expect(events.count == 4)
        if case .chunk(let content) = events[0] {
            #expect(content == "Hello")
        } else {
            #expect(Bool(false), "Expected chunk event")
        }
        if case .chunk(let content) = events[1] {
            #expect(content == " world")
        }
        if case .chunk(let content) = events[2] {
            #expect(content == "!")
        }
        if case .done(let messageId) = events[3] {
            #expect(messageId == "msg-123")
        } else {
            #expect(Bool(false), "Expected done event")
        }

        MockURLProtocol.reset()
    }

    // MARK: - Error Event

    @Test("stream with error event yields SSEEvent.error")
    func streamError() async throws {
        let client = makeClient()
        let sseText = "data: {\"type\":\"error\",\"message\":\"AI service temporarily unavailable\"}\n\n"

        MockURLProtocol.requestHandler = { request in
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "text/event-stream"]
            )!
            return (response, sseText.data(using: .utf8))
        }

        var events: [SSEEvent] = []
        for try await event in client.streamSSE(endpoint: .streamMessage(characterId: "abc"), body: nil) {
            events.append(event)
        }

        #expect(events.count >= 1)
        if case .error(let message) = events[0] {
            #expect(message == "AI service temporarily unavailable")
        } else {
            #expect(Bool(false), "Expected error event")
        }

        MockURLProtocol.reset()
    }

    // MARK: - Action Event

    @Test("stream with action event yields SSEEvent.action with payload")
    func streamAction() async throws {
        let client = makeClient()
        let sseText = "data: {\"type\":\"action\",\"action\":\"SET_ALARM\",\"payload\":{\"time\":\"07:00\"}}\n\n"

        MockURLProtocol.requestHandler = { request in
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "text/event-stream"]
            )!
            return (response, sseText.data(using: .utf8))
        }

        var events: [SSEEvent] = []
        for try await event in client.streamSSE(endpoint: .streamMessage(characterId: "abc"), body: nil) {
            events.append(event)
        }

        #expect(events.count >= 1)
        if case .action(let action, _) = events[0] {
            #expect(action == "SET_ALARM")
            let payload = events[0].actionPayload()
            #expect(payload?["time"] as? String == "07:00")
        } else {
            #expect(Bool(false), "Expected action event")
        }

        MockURLProtocol.reset()
    }

    // MARK: - Moderation Event

    @Test("stream with moderation event yields correctly")
    func streamModeration() async throws {
        let client = makeClient()
        let sseText = "data: {\"type\":\"moderation\",\"message\":\"Content policy violation\"}\n\n"

        MockURLProtocol.requestHandler = { request in
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "text/event-stream"]
            )!
            return (response, sseText.data(using: .utf8))
        }

        var events: [SSEEvent] = []
        for try await event in client.streamSSE(endpoint: .streamMessage(characterId: "abc"), body: nil) {
            events.append(event)
        }

        #expect(events.count >= 1)
        if case .moderation(let message) = events[0] {
            #expect(message == "Content policy violation")
        } else {
            #expect(Bool(false), "Expected moderation event")
        }

        MockURLProtocol.reset()
    }

    // MARK: - HTTP Error on SSE

    @Test("stream receives HTTP 401 and yields error event")
    func stream401() async throws {
        let client = makeClient()

        MockURLProtocol.requestHandler = { request in
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 401,
                httpVersion: nil,
                headerFields: nil
            )!
            return (response, nil)
        }

        var events: [SSEEvent] = []
        for try await event in client.streamSSE(endpoint: .streamMessage(characterId: "abc"), body: nil) {
            events.append(event)
        }

        // The delegate should yield an error event for non-2xx status
        let hasError = events.contains { event in
            if case .error = event { return true }
            return false
        }
        #expect(hasError)

        MockURLProtocol.reset()
    }

    // MARK: - SSEEvent convenience

    @Test("actionPayload returns nil for non-action events")
    func actionPayloadNilForNonAction() {
        let event = SSEEvent.chunk(content: "hello")
        #expect(event.actionPayload() == nil)
    }

    @Test("actionPayload decodes valid JSON data")
    func actionPayloadDecodesJSON() {
        let json = #"{"key":"value","count":42}"#
        let event = SSEEvent.action(action: "TEST", payloadJSON: json.data(using: .utf8)!)
        let payload = event.actionPayload()
        #expect(payload?["key"] as? String == "value")
        #expect(payload?["count"] as? Int == 42)
    }

    // MARK: - APIError Tests (enhanced)

    @Test("APIError.unauthorized has user-facing description")
    func unauthorizedDescription() {
        let error = APIError.unauthorized
        #expect(error.errorDescription == "Your session has expired. Please sign in again.")
    }

    @Test("APIError.serverError 429 shows rate limit message")
    func serverError429() {
        let error = APIError.serverError(statusCode: 429, detail: "Rate limited")
        #expect(error.errorDescription == "Too many requests. Please wait a moment and try again.")
    }

    @Test("APIError.serverError 500 shows generic message")
    func serverError500() {
        let error = APIError.serverError(statusCode: 500, detail: "Internal")
        #expect(error.errorDescription == "Something went wrong. Please try again.")
    }

    @Test("APIError.serverError 404 shows detail from server")
    func serverError404ShowsDetail() {
        let error = APIError.serverError(statusCode: 404, detail: "Character not found")
        #expect(error.errorDescription == "Character not found")
    }

    @Test("APIError.networkError shows connection message")
    func networkErrorMessage() {
        let error = APIError.networkError(NSError(domain: "test", code: -1))
        #expect(error.errorDescription == "Connection failed. Please check your internet and try again.")
    }

    @Test("APIError.decodingError shows generic message")
    func decodingErrorMessage() {
        let error = APIError.decodingError(NSError(domain: "test", code: -1))
        #expect(error.errorDescription == "Something went wrong. Please try again.")
    }

    // MARK: - APIError Equatable

    @Test("APIError.unauthorized equals unauthorized")
    func unauthorizedEquatable() {
        #expect(APIError.unauthorized == APIError.unauthorized)
    }

    @Test("APIError.serverError with same values are equal")
    func serverErrorEquatable() {
        #expect(APIError.serverError(statusCode: 404, detail: "Not found") ==
                APIError.serverError(statusCode: 404, detail: "Not found"))
    }

    @Test("APIError.serverError with different values are not equal")
    func serverErrorNotEqual() {
        #expect(APIError.serverError(statusCode: 404, detail: "Not found") !=
                APIError.serverError(statusCode: 500, detail: "Not found"))
    }

    @Test("APIError different cases are not equal")
    func differentCasesNotEqual() {
        #expect(APIError.unauthorized != APIError.serverError(statusCode: 401, detail: "test"))
    }
}
