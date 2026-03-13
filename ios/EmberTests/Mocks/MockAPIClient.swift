import Foundation
@testable import Ember

/// Mock implementation of `APIClientProtocol` for ViewModel testing.
/// Set `requestResult`, `requestError`, or `sseEvents` to control behavior.
final class MockAPIClient: APIClientProtocol, @unchecked Sendable {
    var requestResult: Any?
    var requestError: Error?
    var sseEvents: [SSEEvent] = []
    var requestCallCount: Int = 0
    var requestVoidCallCount: Int = 0
    var streamCallCount: Int = 0
    var lastEndpoint: APIEndpoint?

    func request<T: Decodable>(
        endpoint: APIEndpoint,
        body: (any Encodable)?,
        responseType: T.Type
    ) async throws -> T {
        requestCallCount += 1
        lastEndpoint = endpoint
        if let error = requestError {
            throw error
        }
        guard let result = requestResult as? T else {
            throw APIError.decodingError(
                NSError(domain: "MockAPIClient", code: -1, userInfo: [NSLocalizedDescriptionKey: "No mock result set"])
            )
        }
        return result
    }

    func requestVoid(
        endpoint: APIEndpoint,
        body: (any Encodable)?
    ) async throws {
        requestVoidCallCount += 1
        lastEndpoint = endpoint
        if let error = requestError {
            throw error
        }
    }

    func streamSSE(
        endpoint: APIEndpoint,
        body: (any Encodable)?
    ) -> AsyncThrowingStream<SSEEvent, Error> {
        streamCallCount += 1
        lastEndpoint = endpoint
        let events = sseEvents
        let error = requestError
        return AsyncThrowingStream { continuation in
            Task {
                if let error {
                    continuation.finish(throwing: error)
                    return
                }
                for event in events {
                    continuation.yield(event)
                    try? await Task.sleep(nanoseconds: 1_000_000)
                }
                continuation.finish()
            }
        }
    }
}
