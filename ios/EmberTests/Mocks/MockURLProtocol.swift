import Foundation

/// A custom URLProtocol subclass for intercepting HTTP requests in tests.
/// Register with `URLSessionConfiguration.ephemeral` and set
/// `protocolClasses = [MockURLProtocol.self]`.
final class MockURLProtocol: URLProtocol {

    /// Handler called for each request. Returns the HTTP response and optional data.
    /// Set this before making requests.
    nonisolated(unsafe) static var requestHandler: ((URLRequest) throws -> (HTTPURLResponse, Data?))?

    /// Optional handler for SSE stream tests. Delivers data in chunks via the client.
    /// When set, takes priority over `requestHandler`.
    nonisolated(unsafe) static var streamHandler: ((URLRequest, URLProtocolClient?) -> Void)?

    /// Captures the last request for header/body inspection in tests.
    nonisolated(unsafe) static var lastRequest: URLRequest?

    override class func canInit(with request: URLRequest) -> Bool {
        true
    }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest {
        request
    }

    override func startLoading() {
        MockURLProtocol.lastRequest = request

        // Stream handler for SSE chunk delivery
        if let streamHandler = MockURLProtocol.streamHandler {
            streamHandler(request, client)
            return
        }

        guard let handler = MockURLProtocol.requestHandler else {
            client?.urlProtocol(self, didFailWithError: NSError(
                domain: "MockURLProtocol",
                code: -1,
                userInfo: [NSLocalizedDescriptionKey: "No request handler set"]
            ))
            return
        }

        do {
            let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            if let data {
                client?.urlProtocol(self, didLoad: data)
            }
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {
        // No-op: cleanup handled by URLSession
    }

    /// Resets all handlers and captured state. Call in test teardown.
    static func reset() {
        requestHandler = nil
        streamHandler = nil
        lastRequest = nil
    }
}
