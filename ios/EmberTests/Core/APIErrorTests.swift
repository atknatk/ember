import Testing
import Foundation
@testable import Ember

/// Tests for APIError enum defined in Core/Network/APIError.swift.
/// Verifies all three error cases conform to LocalizedError with meaningful descriptions.
@Suite("APIError")
struct APIErrorTests {

    // MARK: - httpError

    @Test("httpError 404 has non-empty error description")
    func httpError404Description() {
        let error = APIError.httpError(statusCode: 404)
        #expect(error.errorDescription != nil)
        #expect(!(error.errorDescription ?? "").isEmpty)
    }

    @Test("httpError 500 has non-empty error description")
    func httpError500Description() {
        let error = APIError.httpError(statusCode: 500)
        #expect(error.errorDescription != nil)
        #expect(!(error.errorDescription ?? "").isEmpty)
    }

    @Test("httpError description includes the status code")
    func httpErrorDescriptionIncludesCode() {
        let error = APIError.httpError(statusCode: 503)
        let description = error.errorDescription ?? ""
        #expect(description.contains("503"))
    }

    @Test("httpError 200 is representable without crashing")
    func httpError200DoesNotCrash() {
        _ = APIError.httpError(statusCode: 200)
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
        let error: any LocalizedError = APIError.httpError(statusCode: 401)
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
