import Testing
import Foundation
@testable import Ember

/// Tests for APIClient using MockURLProtocol and MockAuthService.
@Suite("APIClient")
struct APIClientTests {

    // MARK: - Test Helpers

    /// Simple Decodable struct for testing.
    private struct TestResponse: Decodable, Equatable {
        let id: String
        let displayName: String  // maps from display_name via snake_case decoding
    }

    /// Simple Encodable struct for testing request bodies.
    private struct TestBody: Encodable {
        let userName: String  // encodes to user_name via snake_case encoding
    }

    /// Creates an APIClient configured with MockURLProtocol and MockAuthService.
    private func makeClient(authService: MockAuthService = MockAuthService()) -> (APIClient, MockAuthService) {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockURLProtocol.self]
        let session = URLSession(configuration: config)
        let baseURL = URL(string: "https://test.ember.ai")!
        let client = APIClient(baseURL: baseURL, session: session, authService: authService)
        return (client, authService)
    }

    /// Creates an HTTPURLResponse with the given status code.
    private func httpResponse(statusCode: Int, url: String = "https://test.ember.ai/api/v1/characters") -> HTTPURLResponse {
        HTTPURLResponse(url: URL(string: url)!, statusCode: statusCode, httpVersion: nil, headerFields: nil)!
    }

    // MARK: - request<T> Tests

    @Test("request with 200 response and valid JSON returns decoded object")
    func requestSuccess() async throws {
        let (client, _) = makeClient()
        let json = #"{"id":"123","display_name":"Test"}"#

        MockURLProtocol.requestHandler = { _ in
            (self.httpResponse(statusCode: 200), json.data(using: .utf8))
        }

        let result = try await client.request(
            endpoint: .listCharacters,
            body: nil,
            responseType: TestResponse.self
        )

        #expect(result.id == "123")
        #expect(result.displayName == "Test")

        MockURLProtocol.reset()
    }

    @Test("request with 200 response and invalid JSON throws decodingError")
    func requestDecodingError() async throws {
        let (client, _) = makeClient()

        MockURLProtocol.requestHandler = { _ in
            (self.httpResponse(statusCode: 200), "not json".data(using: .utf8))
        }

        await #expect(throws: APIError.self) {
            _ = try await client.request(
                endpoint: .listCharacters,
                body: nil,
                responseType: TestResponse.self
            )
        }

        MockURLProtocol.reset()
    }

    @Test("request with 404 response and detail throws serverError")
    func request404() async throws {
        let (client, _) = makeClient()
        let errorJSON = #"{"detail":"Not found"}"#

        MockURLProtocol.requestHandler = { _ in
            (self.httpResponse(statusCode: 404), errorJSON.data(using: .utf8))
        }

        do {
            _ = try await client.request(
                endpoint: .listCharacters,
                body: nil,
                responseType: TestResponse.self
            )
            #expect(Bool(false), "Should have thrown")
        } catch let error as APIError {
            if case .serverError(let code, let detail) = error {
                #expect(code == 404)
                #expect(detail == "Not found")
            } else {
                #expect(Bool(false), "Expected serverError, got \(error)")
            }
        }

        MockURLProtocol.reset()
    }

    @Test("request with 500 response throws serverError")
    func request500() async throws {
        let (client, _) = makeClient()

        MockURLProtocol.requestHandler = { _ in
            (self.httpResponse(statusCode: 500), #"{"detail":"Internal error"}"#.data(using: .utf8))
        }

        do {
            _ = try await client.request(
                endpoint: .listCharacters,
                body: nil,
                responseType: TestResponse.self
            )
            #expect(Bool(false), "Should have thrown")
        } catch let error as APIError {
            if case .serverError(let code, _) = error {
                #expect(code == 500)
            } else {
                #expect(Bool(false), "Expected serverError")
            }
        }

        MockURLProtocol.reset()
    }

    @Test("request with 401 then refresh succeeds and retry returns 200")
    func request401RetrySuccess() async throws {
        let authService = MockAuthService()
        let (client, _) = makeClient(authService: authService)
        var requestCount = 0

        MockURLProtocol.requestHandler = { _ in
            requestCount += 1
            if requestCount == 1 {
                return (self.httpResponse(statusCode: 401), #"{"detail":"Unauthorized"}"#.data(using: .utf8))
            } else {
                return (self.httpResponse(statusCode: 200), #"{"id":"456","display_name":"Refreshed"}"#.data(using: .utf8))
            }
        }

        let result = try await client.request(
            endpoint: .listCharacters,
            body: nil,
            responseType: TestResponse.self
        )

        #expect(result.id == "456")
        #expect(authService.refreshCallCount == 1)

        MockURLProtocol.reset()
    }

    @Test("request with 401 then refresh succeeds but retry also 401 throws unauthorized")
    func request401RetryAlso401() async throws {
        let authService = MockAuthService()
        let (client, _) = makeClient(authService: authService)

        MockURLProtocol.requestHandler = { _ in
            (self.httpResponse(statusCode: 401), #"{"detail":"Unauthorized"}"#.data(using: .utf8))
        }

        do {
            _ = try await client.request(
                endpoint: .listCharacters,
                body: nil,
                responseType: TestResponse.self
            )
            #expect(Bool(false), "Should have thrown")
        } catch let error as APIError {
            #expect(error == .unauthorized)
        }

        MockURLProtocol.reset()
    }

    @Test("request with 401 and refreshToken throws results in unauthorized")
    func request401RefreshThrows() async throws {
        let authService = MockAuthService()
        authService.shouldThrowOnRefresh = true
        let (client, _) = makeClient(authService: authService)

        MockURLProtocol.requestHandler = { _ in
            (self.httpResponse(statusCode: 401), #"{"detail":"Unauthorized"}"#.data(using: .utf8))
        }

        do {
            _ = try await client.request(
                endpoint: .listCharacters,
                body: nil,
                responseType: TestResponse.self
            )
            #expect(Bool(false), "Should have thrown")
        } catch let error as APIError {
            #expect(error == .unauthorized)
        }

        MockURLProtocol.reset()
    }

    @Test("request on public endpoint with 401 does NOT attempt refresh")
    func request401PublicEndpoint() async throws {
        let authService = MockAuthService()
        let (client, _) = makeClient(authService: authService)

        MockURLProtocol.requestHandler = { _ in
            (self.httpResponse(statusCode: 401), #"{"detail":"Bad credentials"}"#.data(using: .utf8))
        }

        do {
            _ = try await client.request(
                endpoint: .register,
                body: nil,
                responseType: TestResponse.self
            )
            #expect(Bool(false), "Should have thrown")
        } catch let error as APIError {
            // Should be serverError, not unauthorized
            if case .serverError(let code, _) = error {
                #expect(code == 401)
            } else {
                #expect(Bool(false), "Expected serverError for public endpoint 401, got \(error)")
            }
        }
        #expect(authService.refreshCallCount == 0)

        MockURLProtocol.reset()
    }

    // MARK: - requestVoid Tests

    @Test("requestVoid with 204 response completes without error")
    func requestVoid204() async throws {
        let (client, _) = makeClient()

        MockURLProtocol.requestHandler = { _ in
            (self.httpResponse(statusCode: 204), nil)
        }

        try await client.requestVoid(endpoint: .deleteCharacter(id: "abc"), body: nil)

        MockURLProtocol.reset()
    }

    @Test("requestVoid with 403 response throws serverError")
    func requestVoid403() async throws {
        let (client, _) = makeClient()

        MockURLProtocol.requestHandler = { _ in
            (self.httpResponse(statusCode: 403), #"{"detail":"Forbidden"}"#.data(using: .utf8))
        }

        do {
            try await client.requestVoid(endpoint: .deleteCharacter(id: "abc"), body: nil)
            #expect(Bool(false), "Should have thrown")
        } catch let error as APIError {
            if case .serverError(let code, _) = error {
                #expect(code == 403)
            } else {
                #expect(Bool(false), "Expected serverError")
            }
        }

        MockURLProtocol.reset()
    }

    // MARK: - Header Tests

    @Test("request sets Authorization header for auth endpoints")
    func requestSetsAuthHeader() async throws {
        let authService = MockAuthService()
        authService.accessToken = "test-token-xyz"
        let (client, _) = makeClient(authService: authService)

        MockURLProtocol.requestHandler = { request in
            let authHeader = request.value(forHTTPHeaderField: "Authorization")
            #expect(authHeader == "Bearer test-token-xyz")
            return (self.httpResponse(statusCode: 200), #"{"id":"1","display_name":"T"}"#.data(using: .utf8))
        }

        _ = try await client.request(
            endpoint: .listCharacters,
            body: nil,
            responseType: TestResponse.self
        )

        MockURLProtocol.reset()
    }

    @Test("request sets Content-Type for POST with body")
    func requestSetsContentType() async throws {
        let (client, _) = makeClient()

        MockURLProtocol.requestHandler = { request in
            let contentType = request.value(forHTTPHeaderField: "Content-Type")
            #expect(contentType == "application/json")
            #expect(request.httpMethod == "POST")
            return (self.httpResponse(statusCode: 200), #"{"id":"1","display_name":"T"}"#.data(using: .utf8))
        }

        _ = try await client.request(
            endpoint: .createCharacter,
            body: TestBody(userName: "test"),
            responseType: TestResponse.self
        )

        MockURLProtocol.reset()
    }

    @Test("request does NOT set Authorization header for public endpoints")
    func requestNoAuthForPublicEndpoints() async throws {
        let (client, _) = makeClient()

        MockURLProtocol.requestHandler = { request in
            let authHeader = request.value(forHTTPHeaderField: "Authorization")
            #expect(authHeader == nil)
            return (self.httpResponse(statusCode: 200), #"{"id":"1","display_name":"T"}"#.data(using: .utf8))
        }

        _ = try await client.request(
            endpoint: .register,
            body: TestBody(userName: "test"),
            responseType: TestResponse.self
        )

        MockURLProtocol.reset()
    }

    @Test("request encodes body with snake_case keys")
    func requestEncodesSnakeCase() async throws {
        let (client, _) = makeClient()

        MockURLProtocol.requestHandler = { request in
            if let body = request.httpBody,
               let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any] {
                #expect(json["user_name"] as? String == "test_user")
            } else {
                #expect(Bool(false), "Expected JSON body")
            }
            return (self.httpResponse(statusCode: 200), #"{"id":"1","display_name":"T"}"#.data(using: .utf8))
        }

        _ = try await client.request(
            endpoint: .createCharacter,
            body: TestBody(userName: "test_user"),
            responseType: TestResponse.self
        )

        MockURLProtocol.reset()
    }

    @Test("request decodes response with snake_case keys to camelCase properties")
    func requestDecodesSnakeCase() async throws {
        let (client, _) = makeClient()

        MockURLProtocol.requestHandler = { _ in
            (self.httpResponse(statusCode: 200), #"{"id":"42","display_name":"Ember Test"}"#.data(using: .utf8))
        }

        let result = try await client.request(
            endpoint: .listCharacters,
            body: nil,
            responseType: TestResponse.self
        )

        #expect(result.displayName == "Ember Test")

        MockURLProtocol.reset()
    }

    // MARK: - Network Error

    @Test("network error throws APIError.networkError")
    func networkErrorThrowsNetworkError() async throws {
        let (client, _) = makeClient()

        MockURLProtocol.requestHandler = { _ in
            throw NSError(domain: NSURLErrorDomain, code: NSURLErrorNotConnectedToInternet)
        }

        do {
            _ = try await client.request(
                endpoint: .listCharacters,
                body: nil,
                responseType: TestResponse.self
            )
            #expect(Bool(false), "Should have thrown")
        } catch let error as APIError {
            if case .networkError = error {
                // expected
            } else {
                #expect(Bool(false), "Expected networkError, got \(error)")
            }
        }

        MockURLProtocol.reset()
    }

    // MARK: - Default Parameter Extensions

    @Test("request without body parameter compiles and works")
    func requestDefaultBody() async throws {
        let (client, _) = makeClient()

        MockURLProtocol.requestHandler = { _ in
            (self.httpResponse(statusCode: 200), #"{"id":"1","display_name":"T"}"#.data(using: .utf8))
        }

        let result = try await client.request(
            endpoint: .listCharacters,
            responseType: TestResponse.self
        )
        #expect(result.id == "1")

        MockURLProtocol.reset()
    }

    @Test("requestVoid without body parameter compiles and works")
    func requestVoidDefaultBody() async throws {
        let (client, _) = makeClient()

        MockURLProtocol.requestHandler = { _ in
            (self.httpResponse(statusCode: 204), nil)
        }

        try await client.requestVoid(endpoint: .deleteCharacter(id: "abc"))

        MockURLProtocol.reset()
    }

    // MARK: - Singleton

    @Test("APIClient.shared returns the same singleton instance")
    func sharedSingleton() {
        let a = APIClient.shared
        let b = APIClient.shared
        #expect(a === b)
    }

    @Test("APIClient has a non-nil baseURL with https scheme")
    func baseURLIsValid() {
        let client = APIClient.shared
        #expect(client.baseURL.absoluteString.isEmpty == false)
        #expect(client.baseURL.scheme == "https")
    }
}
