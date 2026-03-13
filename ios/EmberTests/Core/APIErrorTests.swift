import Testing
import Foundation
@testable import Ember

/// Tests for APIError enum defined in Core/Network/APIError.swift.
/// Verifies all error cases conform to LocalizedError with meaningful descriptions.
@Suite("APIError")
struct APIErrorTests {

    // MARK: - serverError

    @Test("serverError 404 has non-empty error description")
    func serverError404Description() {
        let error = APIError.serverError(statusCode: 404, detail: "Not found")
        #expect(error.errorDescription != nil)
        #expect(!(error.errorDescription ?? "").isEmpty)
    }

    @Test("serverError 500 has non-empty error description")
    func serverError500Description() {
        let error = APIError.serverError(statusCode: 500, detail: "Internal")
        #expect(error.errorDescription != nil)
        #expect(!(error.errorDescription ?? "").isEmpty)
    }

    @Test("serverError 503 description contains useful info")
    func serverError503Description() {
        let error = APIError.serverError(statusCode: 503, detail: "Service unavailable")
        let description = error.errorDescription ?? ""
        #expect(!description.isEmpty)
    }

    @Test("serverError 200 is representable without crashing")
    func serverError200DoesNotCrash() {
        _ = APIError.serverError(statusCode: 200, detail: "OK")
    }

    // MARK: - unauthorized

    @Test("unauthorized has non-empty error description")
    func unauthorizedDescription() {
        let error = APIError.unauthorized
        #expect(error.errorDescription != nil)
        #expect(!(error.errorDescription ?? "").isEmpty)
    }

    // MARK: - decodingError

    @Test("decodingError has non-empty error description")
    func decodingErrorDescription() {
        struct FakeError: Error, LocalizedError {
            var errorDescription: String? { "Fake decode failure" }
        }
        let error = APIError.decodingError(FakeError())
        #expect(error.errorDescription != nil)
        #expect(!(error.errorDescription ?? "").isEmpty)
    }

    // MARK: - networkError

    @Test("networkError has non-empty error description")
    func networkErrorDescription() {
        struct FakeNetworkError: Error, LocalizedError {
            var errorDescription: String? { "Fake network failure" }
        }
        let error = APIError.networkError(FakeNetworkError())
        #expect(error.errorDescription != nil)
        #expect(!(error.errorDescription ?? "").isEmpty)
    }

    // MARK: - LocalizedError Conformance

    @Test("APIError conforms to LocalizedError")
    func apiErrorConformsToLocalizedError() {
        let error: any LocalizedError = APIError.unauthorized
        #expect(error.errorDescription != nil)
    }

    // MARK: - APIClient Stub

    @Test("APIClient.shared returns the same singleton instance")
    func apiClientSharedIsSingleton() {
        let a = APIClient.shared
        let b = APIClient.shared
        #expect(a === b)
    }

    @Test("APIClient has a non-nil baseURL")
    func apiClientHasBaseURL() {
        let client = APIClient.shared
        // baseURL is always set from environment or the default "https://api.ember.ai"
        #expect(client.baseURL.absoluteString.isEmpty == false)
    }

    @Test("APIClient baseURL has https scheme by default")
    func apiClientBaseURLHasHTTPS() {
        // When API_BASE_URL env var is not set (typical test environment),
        // the client falls back to https://api.ember.ai
        let client = APIClient.shared
        let scheme = client.baseURL.scheme ?? ""
        #expect(scheme == "https")
    }

    @Test("APIClient conforms to APIClientProtocol")
    func apiClientConformsToProtocol() {
        let client: any APIClientProtocol = APIClient.shared
        #expect(client is APIClient)
    }
}
