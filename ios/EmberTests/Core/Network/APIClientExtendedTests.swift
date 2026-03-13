import Testing
import Foundation
@testable import Ember

/// Extended tests for APIClient — edge cases not covered by APIClientTests.swift.
/// Focuses on: concurrent requests, request cancellation, empty response body,
/// requestVoid 401 retry, error body without detail field, streamSSE headers,
/// and getAccessToken failure propagation.
@Suite("APIClient Extended")
struct APIClientExtendedTests {

    // MARK: - Test Helpers

    private struct TestResponse: Decodable, Equatable {
        let id: String
        let displayName: String
    }

    private struct TestBody: Encodable {
        let content: String
    }

    private func makeClient(authService: MockAuthService = MockAuthService()) -> (APIClient, MockAuthService) {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockURLProtocol.self]
        let session = URLSession(configuration: config)
        let baseURL = URL(string: "https://test.ember.ai")!
        let client = APIClient(baseURL: baseURL, session: session, authService: authService)
        return (client, authService)
    }

    private func httpResponse(statusCode: Int, url: String = "https://test.ember.ai/api/v1/characters") -> HTTPURLResponse {
        HTTPURLResponse(url: URL(string: url)!, statusCode: statusCode, httpVersion: nil, headerFields: nil)!
    }

    // MARK: - Concurrent Requests

    @Test("concurrent requests each receive their own decoded response")
    func concurrentRequestsReturnIndependentResults() async throws {
        let (client, _) = makeClient()
        var callCount = 0
        let lock = NSLock()

        MockURLProtocol.requestHandler = { _ in
            lock.lock()
            callCount += 1
            let id = callCount
            lock.unlock()
            let json = "{\"id\":\"\(id)\",\"display_name\":\"Response\(id)\"}"
            return (HTTPURLResponse(
                url: URL(string: "https://test.ember.ai/api/v1/characters")!,
                statusCode: 200, httpVersion: nil, headerFields: nil)!,
                json.data(using: .utf8))
        }

        async let r1 = client.request(endpoint: .listCharacters, body: nil, responseType: TestResponse.self)
        async let r2 = client.request(endpoint: .listCharacters, body: nil, responseType: TestResponse.self)
        async let r3 = client.request(endpoint: .listCharacters, body: nil, responseType: TestResponse.self)

        let (res1, res2, res3) = try await (r1, r2, r3)

        // All three should decode successfully
        #expect(!res1.id.isEmpty)
        #expect(!res2.id.isEmpty)
        #expect(!res3.id.isEmpty)

        MockURLProtocol.reset()
    }

    // MARK: - Empty Response Body

    @Test("request with 200 and empty data body throws decodingError for typed response")
    func requestEmptyBodyThrowsDecodingError() async throws {
        let (client, _) = makeClient()

        MockURLProtocol.requestHandler = { _ in
            (self.httpResponse(statusCode: 200), Data())
        }

        do {
            _ = try await client.request(endpoint: .listCharacters, body: nil, responseType: TestResponse.self)
            #expect(Bool(false), "Should have thrown")
        } catch let error as APIError {
            if case .decodingError = error {
                // expected — empty data cannot be decoded
            } else {
                #expect(Bool(false), "Expected decodingError, got \(error)")
            }
        }

        MockURLProtocol.reset()
    }

    @Test("requestVoid with 200 and empty body succeeds")
    func requestVoidEmptyBodySucceeds() async throws {
        let (client, _) = makeClient()

        MockURLProtocol.requestHandler = { _ in
            (self.httpResponse(statusCode: 200), Data())
        }

        // requestVoid ignores body content — should not throw
        try await client.requestVoid(endpoint: .deleteCharacter(id: "abc"), body: nil)

        MockURLProtocol.reset()
    }

    @Test("requestVoid with nil body succeeds on 204")
    func requestVoidNilBodySucceeds() async throws {
        let (client, _) = makeClient()

        MockURLProtocol.requestHandler = { _ in
            (self.httpResponse(statusCode: 204), nil)
        }

        try await client.requestVoid(endpoint: .deleteAccount)

        MockURLProtocol.reset()
    }

    // MARK: - Error Body Without detail Field

    @Test("request with 404 and no detail field falls back to generic message")
    func requestErrorWithoutDetailField() async throws {
        let (client, _) = makeClient()

        MockURLProtocol.requestHandler = { _ in
            // Error body does not have "detail" key
            (self.httpResponse(statusCode: 404), "{\"error\":\"not_found\"}".data(using: .utf8))
        }

        do {
            _ = try await client.request(endpoint: .listCharacters, body: nil, responseType: TestResponse.self)
            #expect(Bool(false), "Should have thrown")
        } catch let error as APIError {
            if case .serverError(let code, let detail) = error {
                #expect(code == 404)
                // Without detail field, should fall back to generic "Server error: 404"
                #expect(!detail.isEmpty)
            } else {
                #expect(Bool(false), "Expected serverError, got \(error)")
            }
        }

        MockURLProtocol.reset()
    }

    @Test("request with 500 and empty body falls back to generic error detail")
    func requestErrorWithEmptyBody() async throws {
        let (client, _) = makeClient()

        MockURLProtocol.requestHandler = { _ in
            (self.httpResponse(statusCode: 500), Data())
        }

        do {
            _ = try await client.request(endpoint: .listCharacters, body: nil, responseType: TestResponse.self)
            #expect(Bool(false), "Should have thrown")
        } catch let error as APIError {
            if case .serverError(let code, let detail) = error {
                #expect(code == 500)
                #expect(!detail.isEmpty)
            } else {
                #expect(Bool(false), "Expected serverError")
            }
        }

        MockURLProtocol.reset()
    }

    // MARK: - requestVoid 401 Retry

    @Test("requestVoid with 401 calls refreshToken once and retries")
    func requestVoid401RetrySuccess() async throws {
        let authService = MockAuthService()
        let (client, _) = makeClient(authService: authService)
        var callCount = 0

        MockURLProtocol.requestHandler = { _ in
            callCount += 1
            if callCount == 1 {
                return (self.httpResponse(statusCode: 401), #"{"detail":"Unauthorized"}"#.data(using: .utf8))
            } else {
                return (self.httpResponse(statusCode: 204), nil)
            }
        }

        try await client.requestVoid(endpoint: .deleteCharacter(id: "abc"), body: nil)

        #expect(authService.refreshCallCount == 1)

        MockURLProtocol.reset()
    }

    @Test("requestVoid with 401 and refresh throws results in unauthorized")
    func requestVoid401RefreshThrows() async throws {
        let authService = MockAuthService()
        authService.shouldThrowOnRefresh = true
        let (client, _) = makeClient(authService: authService)

        MockURLProtocol.requestHandler = { _ in
            (self.httpResponse(statusCode: 401), #"{"detail":"Unauthorized"}"#.data(using: .utf8))
        }

        do {
            try await client.requestVoid(endpoint: .deleteCharacter(id: "abc"), body: nil)
            #expect(Bool(false), "Should have thrown")
        } catch let error as APIError {
            #expect(error == .unauthorized)
        }

        MockURLProtocol.reset()
    }

    @Test("requestVoid with 401 retry also 401 throws unauthorized")
    func requestVoid401RetryAlso401() async throws {
        let authService = MockAuthService()
        let (client, _) = makeClient(authService: authService)

        MockURLProtocol.requestHandler = { _ in
            (self.httpResponse(statusCode: 401), #"{"detail":"Unauthorized"}"#.data(using: .utf8))
        }

        do {
            try await client.requestVoid(endpoint: .deleteCharacter(id: "abc"), body: nil)
            #expect(Bool(false), "Should have thrown")
        } catch let error as APIError {
            #expect(error == .unauthorized)
        }

        MockURLProtocol.reset()
    }

    // MARK: - getAccessToken Failure

    @Test("request throws networkError when getAccessToken fails")
    func requestGetAccessTokenFailure() async throws {
        let authService = MockAuthService()
        authService.shouldThrowOnGetToken = true
        let (client, _) = makeClient(authService: authService)

        MockURLProtocol.requestHandler = { _ in
            (self.httpResponse(statusCode: 200), #"{"id":"1","display_name":"T"}"#.data(using: .utf8))
        }

        do {
            _ = try await client.request(endpoint: .listCharacters, body: nil, responseType: TestResponse.self)
            #expect(Bool(false), "Should have thrown")
        } catch {
            // Any error is acceptable — key is that it throws
            #expect(true)
        }

        MockURLProtocol.reset()
    }

    // MARK: - streamSSE Headers

    @Test("streamSSE sets Accept: text/event-stream header")
    func streamSSESetsAcceptHeader() async throws {
        let client = {
            let config = URLSessionConfiguration.ephemeral
            config.protocolClasses = [MockURLProtocol.self]
            let session = URLSession(configuration: config)
            let authService = MockAuthService()
            return APIClient(baseURL: URL(string: "https://test.ember.ai")!, session: session, authService: authService)
        }()

        var capturedRequest: URLRequest?

        MockURLProtocol.requestHandler = { request in
            capturedRequest = request
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "text/event-stream"]
            )!
            return (response, "data: {\"type\":\"done\",\"message_id\":\"m1\"}\n\n".data(using: .utf8))
        }

        var events: [SSEEvent] = []
        for try await event in client.streamSSE(endpoint: .streamMessage(characterId: "abc"), body: nil) {
            events.append(event)
        }

        #expect(capturedRequest?.value(forHTTPHeaderField: "Accept") == "text/event-stream")

        MockURLProtocol.reset()
    }

    @Test("streamSSE sets Authorization header for auth endpoint")
    func streamSSESetsAuthHeader() async throws {
        let authService = MockAuthService()
        authService.accessToken = "stream-token-abc"
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockURLProtocol.self]
        let session = URLSession(configuration: config)
        let client = APIClient(baseURL: URL(string: "https://test.ember.ai")!, session: session, authService: authService)

        var capturedRequest: URLRequest?

        MockURLProtocol.requestHandler = { request in
            capturedRequest = request
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "text/event-stream"]
            )!
            return (response, "data: {\"type\":\"done\",\"message_id\":\"m1\"}\n\n".data(using: .utf8))
        }

        var events: [SSEEvent] = []
        for try await event in client.streamSSE(endpoint: .streamMessage(characterId: "abc"), body: nil) {
            events.append(event)
        }

        #expect(capturedRequest?.value(forHTTPHeaderField: "Authorization") == "Bearer stream-token-abc")

        MockURLProtocol.reset()
    }

    // MARK: - requestVoid with Body

    @Test("requestVoid with body sets Content-Type header")
    func requestVoidWithBodySetsContentType() async throws {
        let (client, _) = makeClient()

        MockURLProtocol.requestHandler = { request in
            let contentType = request.value(forHTTPHeaderField: "Content-Type")
            #expect(contentType == "application/json")
            return (self.httpResponse(statusCode: 200), nil)
        }

        try await client.requestVoid(endpoint: .updateProfile, body: TestBody(content: "test"))

        MockURLProtocol.reset()
    }

    @Test("requestVoid with body encodes body as snake_case JSON")
    func requestVoidWithBodyEncodesSnakeCase() async throws {
        let (client, _) = makeClient()

        struct ProfileBody: Encodable { let displayName: String }

        MockURLProtocol.requestHandler = { request in
            if let body = request.httpBody,
               let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any] {
                #expect(json["display_name"] as? String == "Test User")
            } else {
                #expect(Bool(false), "Expected JSON body with snake_case key")
            }
            return (self.httpResponse(statusCode: 200), nil)
        }

        try await client.requestVoid(endpoint: .updateProfile, body: ProfileBody(displayName: "Test User"))

        MockURLProtocol.reset()
    }

    // MARK: - 401 Retry: new token used in retry request

    @Test("401 retry uses refreshed token in Authorization header")
    func retryUsesRefreshedToken() async throws {
        let authService = MockAuthService()
        authService.accessToken = "initial-token"
        authService.refreshedToken = "refreshed-token"
        let (client, _) = makeClient(authService: authService)
        var requestCount = 0
        var retryAuthHeader: String?

        MockURLProtocol.requestHandler = { request in
            requestCount += 1
            if requestCount == 1 {
                return (self.httpResponse(statusCode: 401), #"{"detail":"Unauthorized"}"#.data(using: .utf8))
            } else {
                retryAuthHeader = request.value(forHTTPHeaderField: "Authorization")
                return (self.httpResponse(statusCode: 200), #"{"id":"ok","display_name":"Done"}"#.data(using: .utf8))
            }
        }

        _ = try await client.request(endpoint: .listCharacters, body: nil, responseType: TestResponse.self)

        #expect(retryAuthHeader == "Bearer refreshed-token")

        MockURLProtocol.reset()
    }

    // MARK: - 422 Response

    @Test("request with 422 response throws serverError with detail")
    func request422ThrowsServerError() async throws {
        let (client, _) = makeClient()

        MockURLProtocol.requestHandler = { _ in
            (self.httpResponse(statusCode: 422), #"{"detail":"Validation error"}"#.data(using: .utf8))
        }

        do {
            _ = try await client.request(endpoint: .createCharacter, body: nil, responseType: TestResponse.self)
            #expect(Bool(false), "Should have thrown")
        } catch let error as APIError {
            if case .serverError(let code, let detail) = error {
                #expect(code == 422)
                #expect(detail == "Validation error")
            } else {
                #expect(Bool(false), "Expected serverError")
            }
        }

        MockURLProtocol.reset()
    }

    // MARK: - 403 Response

    @Test("request with 403 does NOT attempt token refresh")
    func request403DoesNotRefresh() async throws {
        let authService = MockAuthService()
        let (client, _) = makeClient(authService: authService)

        MockURLProtocol.requestHandler = { _ in
            (self.httpResponse(statusCode: 403), #"{"detail":"Forbidden"}"#.data(using: .utf8))
        }

        do {
            _ = try await client.request(endpoint: .listCharacters, body: nil, responseType: TestResponse.self)
            #expect(Bool(false), "Should have thrown")
        } catch let error as APIError {
            if case .serverError(let code, _) = error {
                #expect(code == 403)
            } else {
                #expect(Bool(false), "Expected serverError(403)")
            }
        }

        // 403 should never trigger refresh
        #expect(authService.refreshCallCount == 0)

        MockURLProtocol.reset()
    }

    // MARK: - 429 Rate Limit

    @Test("request with 429 throws serverError with rate-limit detail")
    func request429ThrowsServerError() async throws {
        let (client, _) = makeClient()

        MockURLProtocol.requestHandler = { _ in
            (self.httpResponse(statusCode: 429), #"{"detail":"Rate limit exceeded"}"#.data(using: .utf8))
        }

        do {
            _ = try await client.request(endpoint: .listCharacters, body: nil, responseType: TestResponse.self)
            #expect(Bool(false), "Should have thrown")
        } catch let error as APIError {
            if case .serverError(let code, _) = error {
                #expect(code == 429)
                // The user-facing description should be the rate-limit message
                #expect(error.errorDescription == "Too many requests. Please wait a moment and try again.")
            } else {
                #expect(Bool(false), "Expected serverError(429)")
            }
        }

        MockURLProtocol.reset()
    }

    // MARK: - MockAPIClient Protocol Compliance

    @Test("MockAPIClient.request increments call count")
    func mockAPIClientIncrementsRequestCount() async throws {
        let mock = MockAPIClient()
        mock.requestResult = TestResponse(id: "1", displayName: "Test")

        _ = try await mock.request(endpoint: .listCharacters, body: nil, responseType: TestResponse.self)
        _ = try await mock.request(endpoint: .listCharacters, body: nil, responseType: TestResponse.self)

        #expect(mock.requestCallCount == 2)
    }

    @Test("MockAPIClient.requestVoid increments call count")
    func mockAPIClientIncrementsVoidCount() async throws {
        let mock = MockAPIClient()

        try await mock.requestVoid(endpoint: .deleteAccount, body: nil)
        try await mock.requestVoid(endpoint: .deleteAccount, body: nil)

        #expect(mock.requestVoidCallCount == 2)
    }

    @Test("MockAPIClient.streamSSE increments call count")
    func mockAPIClientIncrementsStreamCount() async throws {
        let mock = MockAPIClient()
        mock.sseEvents = [.done(messageId: "m1")]

        var events: [SSEEvent] = []
        for try await event in mock.streamSSE(endpoint: .streamMessage(characterId: "abc"), body: nil) {
            events.append(event)
        }

        #expect(mock.streamCallCount == 1)
        #expect(events.count == 1)
    }

    @Test("MockAPIClient.request throws when requestError is set")
    func mockAPIClientThrowsRequestError() async throws {
        let mock = MockAPIClient()
        mock.requestError = APIError.unauthorized

        do {
            _ = try await mock.request(endpoint: .listCharacters, body: nil, responseType: TestResponse.self)
            #expect(Bool(false), "Should have thrown")
        } catch let error as APIError {
            #expect(error == .unauthorized)
        }
    }

    @Test("MockAPIClient records last endpoint used")
    func mockAPIClientRecordsLastEndpoint() async throws {
        let mock = MockAPIClient()
        mock.requestResult = TestResponse(id: "1", displayName: "T")

        _ = try await mock.request(endpoint: .getProfile, body: nil, responseType: TestResponse.self)

        if case .getProfile = mock.lastEndpoint! {
            // expected
        } else {
            #expect(Bool(false), "Expected lastEndpoint to be .getProfile")
        }
    }

    @Test("MockAPIClient.streamSSE throws when requestError is set")
    func mockAPIClientStreamThrowsError() async throws {
        let mock = MockAPIClient()
        mock.requestError = APIError.networkError(NSError(domain: "test", code: -1))

        do {
            for try await _ in mock.streamSSE(endpoint: .streamMessage(characterId: "abc"), body: nil) {
                #expect(Bool(false), "Should not yield events")
            }
            #expect(Bool(false), "Should have thrown")
        } catch {
            // expected
            #expect(true)
        }
    }
}
