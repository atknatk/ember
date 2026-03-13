import Testing
import Foundation
@testable import Ember

/// Extended tests for SSEClient and APIError edge cases not covered by SSEClientTests.swift.
/// Focuses on: malformed JSON, partial data buffering, multiple events in one chunk,
/// unknown event types, missing fields, [DONE] sentinel, and APIError Equatable edge cases.
@Suite("SSEClient Extended")
struct SSEClientExtendedTests {

    // MARK: - Helpers

    private func makeClient() -> APIClient {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockURLProtocol.self]
        let session = URLSession(configuration: config)
        let authService = MockAuthService()
        return APIClient(
            baseURL: URL(string: "https://test.ember.ai")!,
            session: session,
            authService: authService
        )
    }

    private func sseResponse(for request: URLRequest, body: Data?) -> (HTTPURLResponse, Data?) {
        let response = HTTPURLResponse(
            url: request.url!,
            statusCode: 200,
            httpVersion: nil,
            headerFields: ["Content-Type": "text/event-stream"]
        )!
        return (response, body)
    }

    // MARK: - Multiple Events in One Chunk

    @Test("multiple SSE events delivered in one data callback are all yielded")
    func multipleEventsInOneChunk() async throws {
        let client = makeClient()

        // All three events in a single Data delivery
        let sseText = [
            "data: {\"type\":\"chunk\",\"content\":\"Hello\"}",
            "",
            "data: {\"type\":\"chunk\",\"content\":\" world\"}",
            "",
            "data: {\"type\":\"done\",\"message_id\":\"msg-001\"}",
            "",
        ].joined(separator: "\n")

        MockURLProtocol.requestHandler = { request in
            self.sseResponse(for: request, body: sseText.data(using: .utf8))
        }

        var events: [SSEEvent] = []
        for try await event in client.streamSSE(endpoint: .streamMessage(characterId: "abc"), body: nil) {
            events.append(event)
        }

        #expect(events.count == 3)
        if case .chunk(let c) = events[0] { #expect(c == "Hello") }
        else { #expect(Bool(false), "Expected first chunk") }
        if case .chunk(let c) = events[1] { #expect(c == " world") }
        else { #expect(Bool(false), "Expected second chunk") }
        if case .done(let id) = events[2] { #expect(id == "msg-001") }
        else { #expect(Bool(false), "Expected done event") }

        MockURLProtocol.reset()
    }

    // MARK: - Malformed JSON Lines

    @Test("malformed JSON SSE line is silently ignored and stream continues")
    func malformedJSONLineIgnored() async throws {
        let client = makeClient()

        // One bad line followed by a valid done event
        let sseText = "data: not-valid-json\n\n" +
                      "data: {\"type\":\"done\",\"message_id\":\"msg-ok\"}\n\n"

        MockURLProtocol.requestHandler = { request in
            self.sseResponse(for: request, body: sseText.data(using: .utf8))
        }

        var events: [SSEEvent] = []
        for try await event in client.streamSSE(endpoint: .streamMessage(characterId: "abc"), body: nil) {
            events.append(event)
        }

        // Malformed line must be skipped; done event must still be yielded
        #expect(events.count == 1)
        if case .done(let id) = events[0] { #expect(id == "msg-ok") }
        else { #expect(Bool(false), "Expected done event after malformed line") }

        MockURLProtocol.reset()
    }

    @Test("empty data line (keep-alive) is not yielded as an event")
    func emptyDataLineIgnored() async throws {
        let client = makeClient()

        // Keep-alive empty data lines
        let sseText = "data: \n\n" +
                      "data: {\"type\":\"chunk\",\"content\":\"Hi\"}\n\n"

        MockURLProtocol.requestHandler = { request in
            self.sseResponse(for: request, body: sseText.data(using: .utf8))
        }

        var events: [SSEEvent] = []
        for try await event in client.streamSSE(endpoint: .streamMessage(characterId: "abc"), body: nil) {
            events.append(event)
        }

        // Only the valid chunk should appear
        #expect(events.count == 1)
        if case .chunk(let content) = events[0] { #expect(content == "Hi") }
        else { #expect(Bool(false), "Expected chunk event") }

        MockURLProtocol.reset()
    }

    // MARK: - Unknown Event Type

    @Test("unknown event type is silently ignored")
    func unknownEventTypeIgnored() async throws {
        let client = makeClient()

        let sseText = "data: {\"type\":\"ping\"}\n\n" +
                      "data: {\"type\":\"done\",\"message_id\":\"msg-final\"}\n\n"

        MockURLProtocol.requestHandler = { request in
            self.sseResponse(for: request, body: sseText.data(using: .utf8))
        }

        var events: [SSEEvent] = []
        for try await event in client.streamSSE(endpoint: .streamMessage(characterId: "abc"), body: nil) {
            events.append(event)
        }

        // Only done should appear; unknown type is skipped
        #expect(events.count == 1)
        if case .done = events[0] { /* expected */ }
        else { #expect(Bool(false), "Expected done event") }

        MockURLProtocol.reset()
    }

    // MARK: - Missing Required Fields

    @Test("chunk event missing content field is silently skipped")
    func chunkMissingContentSkipped() async throws {
        let client = makeClient()

        // chunk with no content field, then a valid done
        let sseText = "data: {\"type\":\"chunk\"}\n\n" +
                      "data: {\"type\":\"done\",\"message_id\":\"msg-x\"}\n\n"

        MockURLProtocol.requestHandler = { request in
            self.sseResponse(for: request, body: sseText.data(using: .utf8))
        }

        var events: [SSEEvent] = []
        for try await event in client.streamSSE(endpoint: .streamMessage(characterId: "abc"), body: nil) {
            events.append(event)
        }

        // Chunk without content must be ignored; done must still appear
        #expect(events.count == 1)
        if case .done(let id) = events[0] { #expect(id == "msg-x") }
        else { #expect(Bool(false), "Expected done event only") }

        MockURLProtocol.reset()
    }

    @Test("done event missing message_id is skipped")
    func doneMissingMessageIdSkipped() async throws {
        let client = makeClient()

        // done without message_id field — the delegate should skip it
        let sseText = "data: {\"type\":\"done\"}\n\n"

        MockURLProtocol.requestHandler = { request in
            self.sseResponse(for: request, body: sseText.data(using: .utf8))
        }

        var events: [SSEEvent] = []
        for try await event in client.streamSSE(endpoint: .streamMessage(characterId: "abc"), body: nil) {
            events.append(event)
        }

        // No event yielded for a malformed done
        #expect(events.isEmpty)

        MockURLProtocol.reset()
    }

    // MARK: - [DONE] Sentinel

    @Test("[DONE] sentinel finishes the stream without yielding an event")
    func doneSentinelFinishesStream() async throws {
        let client = makeClient()

        // [DONE] is a legacy sentinel format — should finish the stream cleanly
        let sseText = "data: {\"type\":\"chunk\",\"content\":\"Final\"}\n\n" +
                      "data: [DONE]\n\n"

        MockURLProtocol.requestHandler = { request in
            self.sseResponse(for: request, body: sseText.data(using: .utf8))
        }

        var events: [SSEEvent] = []
        for try await event in client.streamSSE(endpoint: .streamMessage(characterId: "abc"), body: nil) {
            events.append(event)
        }

        // Only the chunk before [DONE] should be yielded
        #expect(events.count == 1)
        if case .chunk(let c) = events[0] { #expect(c == "Final") }
        else { #expect(Bool(false), "Expected chunk before DONE") }

        MockURLProtocol.reset()
    }

    // MARK: - Action Event with No Payload

    @Test("action event with no payload produces empty payloadJSON")
    func actionEventNoPayload() async throws {
        let client = makeClient()

        let sseText = "data: {\"type\":\"action\",\"action\":\"SHOW_MENU\"}\n\n"

        MockURLProtocol.requestHandler = { request in
            self.sseResponse(for: request, body: sseText.data(using: .utf8))
        }

        var events: [SSEEvent] = []
        for try await event in client.streamSSE(endpoint: .streamMessage(characterId: "abc"), body: nil) {
            events.append(event)
        }

        #expect(events.count == 1)
        if case .action(let action, _) = events[0] {
            #expect(action == "SHOW_MENU")
            // payload should be empty or nil when no payload key provided
            let payload = events[0].actionPayload()
            #expect(payload == nil || payload!.isEmpty)
        } else {
            #expect(Bool(false), "Expected action event")
        }

        MockURLProtocol.reset()
    }

    // MARK: - Moderation then Chunks then Done (ordering)

    @Test("moderation then chunks then done are yielded in order")
    func moderationThenChunksThenDone() async throws {
        let client = makeClient()

        let sseText = [
            "data: {\"type\":\"moderation\",\"message\":\"Please keep it friendly\"}",
            "",
            "data: {\"type\":\"chunk\",\"content\":\"Safe\"}",
            "",
            "data: {\"type\":\"chunk\",\"content\":\" response\"}",
            "",
            "data: {\"type\":\"done\",\"message_id\":\"msg-mod-001\"}",
            "",
        ].joined(separator: "\n")

        MockURLProtocol.requestHandler = { request in
            self.sseResponse(for: request, body: sseText.data(using: .utf8))
        }

        var events: [SSEEvent] = []
        for try await event in client.streamSSE(endpoint: .streamMessage(characterId: "abc"), body: nil) {
            events.append(event)
        }

        #expect(events.count == 4)
        if case .moderation(let msg) = events[0] { #expect(!msg.isEmpty) }
        else { #expect(Bool(false), "Expected moderation first") }
        if case .chunk(let c) = events[1] { #expect(c == "Safe") }
        else { #expect(Bool(false), "Expected chunk second") }
        if case .chunk(let c) = events[2] { #expect(c == " response") }
        else { #expect(Bool(false), "Expected chunk third") }
        if case .done(let id) = events[3] { #expect(id == "msg-mod-001") }
        else { #expect(Bool(false), "Expected done last") }

        MockURLProtocol.reset()
    }

    // MARK: - HTTP Error Codes on SSE

    @Test("stream receives HTTP 500 and yields error event")
    func stream500YieldsError() async throws {
        let client = makeClient()

        MockURLProtocol.requestHandler = { request in
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 500,
                httpVersion: nil,
                headerFields: nil
            )!
            return (response, nil)
        }

        var events: [SSEEvent] = []
        for try await event in client.streamSSE(endpoint: .streamMessage(characterId: "abc"), body: nil) {
            events.append(event)
        }

        let hasError = events.contains {
            if case .error = $0 { return true }
            return false
        }
        #expect(hasError)

        MockURLProtocol.reset()
    }

    @Test("stream receives HTTP 403 and yields error event")
    func stream403YieldsError() async throws {
        let client = makeClient()

        MockURLProtocol.requestHandler = { request in
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 403,
                httpVersion: nil,
                headerFields: nil
            )!
            return (response, nil)
        }

        var events: [SSEEvent] = []
        for try await event in client.streamSSE(endpoint: .streamMessage(characterId: "abc"), body: nil) {
            events.append(event)
        }

        let hasError = events.contains {
            if case .error = $0 { return true }
            return false
        }
        #expect(hasError)

        MockURLProtocol.reset()
    }

    // MARK: - SSEEvent Convenience

    @Test("actionPayload returns nil for done event")
    func actionPayloadNilForDone() {
        let event = SSEEvent.done(messageId: "m1")
        #expect(event.actionPayload() == nil)
    }

    @Test("actionPayload returns nil for error event")
    func actionPayloadNilForError() {
        let event = SSEEvent.error(message: "something went wrong")
        #expect(event.actionPayload() == nil)
    }

    @Test("actionPayload returns nil for moderation event")
    func actionPayloadNilForModeration() {
        let event = SSEEvent.moderation(message: "moderated")
        #expect(event.actionPayload() == nil)
    }

    @Test("actionPayload returns nil for action with empty Data")
    func actionPayloadEmptyData() {
        let event = SSEEvent.action(action: "TEST", payloadJSON: Data())
        #expect(event.actionPayload() == nil)
    }

    @Test("actionPayload returns nested string value correctly")
    func actionPayloadNestedString() {
        let json = #"{"alarm":"07:30","label":"Morning wake-up"}"#
        let event = SSEEvent.action(action: "SET_ALARM", payloadJSON: json.data(using: .utf8)!)
        let payload = event.actionPayload()
        #expect(payload?["alarm"] as? String == "07:30")
        #expect(payload?["label"] as? String == "Morning wake-up")
    }

    @Test("actionPayload with integer value decodes correctly")
    func actionPayloadIntegerValue() {
        let json = #"{"duration":3600,"repeat":7}"#
        let event = SSEEvent.action(action: "SET_TIMER", payloadJSON: json.data(using: .utf8)!)
        let payload = event.actionPayload()
        #expect(payload?["duration"] as? Int == 3600)
    }

    // MARK: - APIError Equatable Edge Cases

    @Test("decodingError with same localizedDescription is equal")
    func decodingErrorEqualSameDescription() {
        struct FakeError: Error, LocalizedError {
            let errorDescription: String? = "decode failed"
        }
        let e1 = APIError.decodingError(FakeError())
        let e2 = APIError.decodingError(FakeError())
        #expect(e1 == e2)
    }

    @Test("networkError with same localizedDescription is equal")
    func networkErrorEqualSameDescription() {
        let nsError = NSError(domain: NSURLErrorDomain, code: NSURLErrorNotConnectedToInternet,
                              userInfo: [NSLocalizedDescriptionKey: "offline"])
        let e1 = APIError.networkError(nsError)
        let e2 = APIError.networkError(nsError)
        #expect(e1 == e2)
    }

    @Test("decodingError and networkError with same description are not equal (different cases)")
    func decodingErrorNotEqualToNetworkError() {
        struct SameDescriptionError: Error, LocalizedError {
            let errorDescription: String? = "same message"
        }
        let e1 = APIError.decodingError(SameDescriptionError())
        let e2 = APIError.networkError(SameDescriptionError())
        #expect(e1 != e2)
    }

    @Test("serverError with same code but different detail strings are not equal")
    func serverErrorDifferentDetailNotEqual() {
        let e1 = APIError.serverError(statusCode: 404, detail: "Not found")
        let e2 = APIError.serverError(statusCode: 404, detail: "Resource missing")
        #expect(e1 != e2)
    }

    @Test("unauthorized is not equal to serverError 401")
    func unauthorizedNotEqualToServerError401() {
        #expect(APIError.unauthorized != APIError.serverError(statusCode: 401, detail: "Unauthorized"))
    }

    // MARK: - APIError Description Edge Cases

    @Test("serverError 400 returns server-supplied detail string")
    func serverError400ReturnsDetail() {
        let error = APIError.serverError(statusCode: 400, detail: "Bad request payload")
        #expect(error.errorDescription == "Bad request payload")
    }

    @Test("serverError 422 returns server-supplied detail string")
    func serverError422ReturnsDetail() {
        let error = APIError.serverError(statusCode: 422, detail: "Validation failed")
        #expect(error.errorDescription == "Validation failed")
    }

    @Test("serverError 503 returns generic server error message")
    func serverError503ReturnsGeneric() {
        let error = APIError.serverError(statusCode: 503, detail: "Service unavailable")
        #expect(error.errorDescription == "Something went wrong. Please try again.")
    }

    @Test("serverError 502 returns generic server error message")
    func serverError502ReturnsGeneric() {
        let error = APIError.serverError(statusCode: 502, detail: "Bad gateway")
        #expect(error.errorDescription == "Something went wrong. Please try again.")
    }

    @Test("all APIError cases have non-nil errorDescription")
    func allErrorCasesHaveNonNilDescription() {
        let errors: [APIError] = [
            .unauthorized,
            .serverError(statusCode: 400, detail: "Bad"),
            .serverError(statusCode: 404, detail: "Missing"),
            .serverError(statusCode: 429, detail: "Rate limited"),
            .serverError(statusCode: 500, detail: "Internal"),
            .serverError(statusCode: 503, detail: "Down"),
            .decodingError(NSError(domain: "test", code: -1)),
            .networkError(NSError(domain: "test", code: -1)),
        ]
        for error in errors {
            #expect(error.errorDescription != nil, "errorDescription is nil for \(error)")
            #expect(!(error.errorDescription ?? "").isEmpty, "errorDescription is empty for \(error)")
        }
    }

    // MARK: - MockAuthService Behavior

    @Test("MockAuthService returns accessToken from getAccessToken")
    func mockAuthServiceReturnsAccessToken() async throws {
        let service = MockAuthService()
        service.accessToken = "custom-token"
        let token = try await service.getAccessToken()
        #expect(token == "custom-token")
    }

    @Test("MockAuthService tracks getAccessToken call count")
    func mockAuthServiceTracksGetTokenCallCount() async throws {
        let service = MockAuthService()
        _ = try await service.getAccessToken()
        _ = try await service.getAccessToken()
        #expect(service.getAccessTokenCallCount == 2)
    }

    @Test("MockAuthService returns refreshedToken from refreshToken")
    func mockAuthServiceReturnsRefreshedToken() async throws {
        let service = MockAuthService()
        service.refreshedToken = "new-refresh-token"
        let token = try await service.refreshToken()
        #expect(token == "new-refresh-token")
        #expect(service.refreshCallCount == 1)
    }

    @Test("MockAuthService throws tokenUnavailable when shouldThrowOnGetToken is true")
    func mockAuthServiceThrowsOnGetToken() async throws {
        let service = MockAuthService()
        service.shouldThrowOnGetToken = true

        do {
            _ = try await service.getAccessToken()
            #expect(Bool(false), "Should have thrown")
        } catch let error as AuthError {
            if case .tokenUnavailable = error { /* expected */ }
            else { #expect(Bool(false), "Expected tokenUnavailable") }
        }
    }

    @Test("MockAuthService throws tokenUnavailable when shouldThrowOnRefresh is true")
    func mockAuthServiceThrowsOnRefresh() async throws {
        let service = MockAuthService()
        service.shouldThrowOnRefresh = true

        do {
            _ = try await service.refreshToken()
            #expect(Bool(false), "Should have thrown")
        } catch let error as AuthError {
            if case .tokenUnavailable = error { /* expected */ }
            else { #expect(Bool(false), "Expected tokenUnavailable") }
        }
    }
}
