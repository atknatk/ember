import Foundation

/// Protocol defining the generic network interface for the Ember app.
/// Uses `APIEndpoint` for type-safe routing. New features add cases to the enum
/// without modifying this protocol.
protocol APIClientProtocol: AnyObject, Sendable {
    /// Sends a request and decodes the JSON response as `T`.
    func request<T: Decodable>(
        endpoint: APIEndpoint,
        body: (any Encodable)?,
        responseType: T.Type
    ) async throws -> T

    /// Sends a request that expects no response body (e.g., DELETE returning 204).
    func requestVoid(
        endpoint: APIEndpoint,
        body: (any Encodable)?
    ) async throws

    /// Opens an SSE stream and yields parsed `SSEEvent` values.
    /// No automatic 401 retry -- the stream yields an error event and the caller handles re-auth.
    func streamSSE(
        endpoint: APIEndpoint,
        body: (any Encodable)?
    ) -> AsyncThrowingStream<SSEEvent, Error>
}

// MARK: - Protocol Extension (Default Parameters)

extension APIClientProtocol {
    func request<T: Decodable>(
        endpoint: APIEndpoint,
        responseType: T.Type
    ) async throws -> T {
        try await request(endpoint: endpoint, body: nil, responseType: responseType)
    }

    func requestVoid(endpoint: APIEndpoint) async throws {
        try await requestVoid(endpoint: endpoint, body: nil)
    }

    func streamSSE(endpoint: APIEndpoint) -> AsyncThrowingStream<SSEEvent, Error> {
        streamSSE(endpoint: endpoint, body: nil)
    }
}

// MARK: - APIClient

/// Production network client backed by URLSession.
/// - Thread safety: `@unchecked Sendable` because `URLSession` is thread-safe
///   and all mutable state (`encoder`/`decoder`) is initialized once in `init` and never mutated.
final class APIClient: APIClientProtocol, @unchecked Sendable {
    static let shared = APIClient()

    let baseURL: URL
    private let session: URLSession
    private let authService: AuthServiceProtocol
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder

    init(
        baseURL: URL? = nil,
        session: URLSession = .shared,
        authService: AuthServiceProtocol = AuthService.shared
    ) {
        if let baseURL {
            self.baseURL = baseURL
        } else {
            let urlString = ProcessInfo.processInfo.environment["API_BASE_URL"] ?? "https://api.ember.ai"
            self.baseURL = URL(string: urlString) ?? URL(string: "https://api.ember.ai")!
        }
        self.session = session
        self.authService = authService
        self.encoder = JSONEncoder.ember
        self.decoder = JSONDecoder.ember
    }

    // MARK: - APIClientProtocol

    func request<T: Decodable>(
        endpoint: APIEndpoint,
        body: (any Encodable)?,
        responseType: T.Type
    ) async throws -> T {
        var urlRequest = try buildRequest(endpoint: endpoint, body: body)

        // Inject auth header for protected endpoints
        if endpoint.requiresAuth {
            let token = try await authService.getAccessToken()
            urlRequest.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await session.data(for: urlRequest)
        } catch {
            throw APIError.networkError(error)
        }

        let (responseData, statusCode) = try handleResponse(data: data, response: response)

        // 401 retry path: refresh token and retry once (only for auth-required endpoints)
        if statusCode == 401 && endpoint.requiresAuth {
            return try await retryAfterTokenRefresh(endpoint: endpoint, body: body, responseType: responseType)
        }

        do {
            return try decoder.decode(T.self, from: responseData)
        } catch {
            throw APIError.decodingError(error)
        }
    }

    func requestVoid(
        endpoint: APIEndpoint,
        body: (any Encodable)?
    ) async throws {
        var urlRequest = try buildRequest(endpoint: endpoint, body: body)

        if endpoint.requiresAuth {
            let token = try await authService.getAccessToken()
            urlRequest.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await session.data(for: urlRequest)
        } catch {
            throw APIError.networkError(error)
        }

        let (_, statusCode) = try handleResponse(data: data, response: response)

        // 401 retry path for void requests
        if statusCode == 401 && endpoint.requiresAuth {
            try await retryVoidAfterTokenRefresh(endpoint: endpoint, body: body)
        }
    }

    func streamSSE(
        endpoint: APIEndpoint,
        body: (any Encodable)?
    ) -> AsyncThrowingStream<SSEEvent, Error> {
        AsyncThrowingStream { continuation in
            Task { [weak self] in
                guard let self else {
                    continuation.finish()
                    return
                }

                do {
                    var urlRequest = try self.buildRequest(endpoint: endpoint, body: body)
                    urlRequest.setValue("text/event-stream", forHTTPHeaderField: "Accept")

                    if endpoint.requiresAuth {
                        let token = try await self.authService.getAccessToken()
                        urlRequest.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
                    }

                    let delegate = SSEDelegate(continuation: continuation)
                    let config = URLSessionConfiguration.default
                    // SSE delegate session -- invalidated on termination to avoid retain cycles
                    let delegateSession = URLSession(
                        configuration: config,
                        delegate: delegate,
                        delegateQueue: nil
                    )
                    let dataTask = delegateSession.dataTask(with: urlRequest)
                    dataTask.resume()

                    continuation.onTermination = { @Sendable _ in
                        dataTask.cancel()
                        delegateSession.invalidateAndCancel()
                    }
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    // MARK: - Private Helpers

    /// Builds a URLRequest from an endpoint and optional body.
    private func buildRequest(endpoint: APIEndpoint, body: (any Encodable)?) throws -> URLRequest {
        var components = URLComponents()
        components.path = endpoint.path

        if let queryItems = endpoint.queryItems {
            components.queryItems = queryItems
        }

        guard let endpointURL = components.url(relativeTo: baseURL) else {
            throw APIError.serverError(statusCode: 0, detail: "Invalid URL for endpoint")
        }

        // Resolve the relative URL to an absolute URL
        guard let absoluteURL = URL(string: endpointURL.absoluteString) else {
            throw APIError.serverError(statusCode: 0, detail: "Invalid URL for endpoint")
        }

        var request = URLRequest(url: absoluteURL)
        request.httpMethod = endpoint.method.rawValue

        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try encoder.encode(AnyEncodable(body))
        }

        return request
    }

    /// Validates the HTTP response and returns the data with status code.
    /// Throws `APIError.serverError` for non-2xx status codes (except 401, handled by retry logic).
    private func handleResponse(data: Data, response: URLResponse) throws -> (Data, Int) {
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.networkError(
                NSError(domain: "APIClient", code: -1, userInfo: [NSLocalizedDescriptionKey: "Invalid response"])
            )
        }

        let statusCode = httpResponse.statusCode

        // 2xx: success
        if (200...299).contains(statusCode) {
            return (data, statusCode)
        }

        // 401: return data and status code for retry logic
        if statusCode == 401 {
            return (data, statusCode)
        }

        // Other errors: try to parse server error detail
        let detail = parseErrorDetail(from: data, statusCode: statusCode)
        throw APIError.serverError(statusCode: statusCode, detail: detail)
    }

    /// Attempts to decode the server error body as `{"detail": "..."}`.
    /// Falls back to a generic message.
    private func parseErrorDetail(from data: Data, statusCode: Int) -> String {
        struct ErrorBody: Decodable {
            let detail: String
        }
        if let errorBody = try? JSONDecoder().decode(ErrorBody.self, from: data) {
            return errorBody.detail
        }
        return "Server error: \(statusCode)"
    }

    /// 401 retry path: refresh the token, rebuild the request, retry once.
    private func retryAfterTokenRefresh<T: Decodable>(
        endpoint: APIEndpoint,
        body: (any Encodable)?,
        responseType: T.Type
    ) async throws -> T {
        let newToken: String
        do {
            newToken = try await authService.refreshToken()
        } catch {
            throw APIError.unauthorized
        }

        var urlRequest = try buildRequest(endpoint: endpoint, body: body)
        urlRequest.setValue("Bearer \(newToken)", forHTTPHeaderField: "Authorization")

        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await session.data(for: urlRequest)
        } catch {
            throw APIError.networkError(error)
        }

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.networkError(
                NSError(domain: "APIClient", code: -1, userInfo: [NSLocalizedDescriptionKey: "Invalid response"])
            )
        }

        if httpResponse.statusCode == 401 {
            throw APIError.unauthorized
        }

        if !(200...299).contains(httpResponse.statusCode) {
            let detail = parseErrorDetail(from: data, statusCode: httpResponse.statusCode)
            throw APIError.serverError(statusCode: httpResponse.statusCode, detail: detail)
        }

        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decodingError(error)
        }
    }

    /// 401 retry path for void requests.
    private func retryVoidAfterTokenRefresh(
        endpoint: APIEndpoint,
        body: (any Encodable)?
    ) async throws {
        let newToken: String
        do {
            newToken = try await authService.refreshToken()
        } catch {
            throw APIError.unauthorized
        }

        var urlRequest = try buildRequest(endpoint: endpoint, body: body)
        urlRequest.setValue("Bearer \(newToken)", forHTTPHeaderField: "Authorization")

        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await session.data(for: urlRequest)
        } catch {
            throw APIError.networkError(error)
        }

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.networkError(
                NSError(domain: "APIClient", code: -1, userInfo: [NSLocalizedDescriptionKey: "Invalid response"])
            )
        }

        if httpResponse.statusCode == 401 {
            throw APIError.unauthorized
        }

        if !(200...299).contains(httpResponse.statusCode) {
            let detail = parseErrorDetail(from: data, statusCode: httpResponse.statusCode)
            throw APIError.serverError(statusCode: httpResponse.statusCode, detail: detail)
        }
    }
}

// MARK: - AnyEncodable

/// Type-erased Encodable wrapper to allow `(any Encodable)?` parameters.
private struct AnyEncodable: Encodable {
    private let encodeClosure: (Encoder) throws -> Void

    init(_ value: any Encodable) {
        self.encodeClosure = { encoder in
            try value.encode(to: encoder)
        }
    }

    func encode(to encoder: Encoder) throws {
        try encodeClosure(encoder)
    }
}
