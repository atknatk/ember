import Testing
import Foundation
@testable import Ember

@Suite("EmberError")
struct EmberErrorTests {

    // MARK: - User-Friendly Messages

    @Test("offline error provides connection message")
    func offlineMessage() {
        let error = EmberError.offline
        #expect(error.errorDescription?.contains("offline") == true)
    }

    @Test("networkError provides connection message")
    func networkErrorMessage() {
        let error = EmberError.networkError(underlyingDescription: "DNS failed")
        #expect(error.errorDescription?.contains("Connection failed") == true)
    }

    @Test("serverError 500+ provides server-side message")
    func serverError500Message() {
        let error = EmberError.serverError(statusCode: 500, detail: "Internal error")
        #expect(error.errorDescription?.contains("our end") == true)
    }

    @Test("serverError 4xx provides generic message")
    func serverError400Message() {
        let error = EmberError.serverError(statusCode: 400, detail: "Bad request")
        #expect(error.errorDescription?.contains("Something went wrong") == true)
    }

    @Test("unauthorized provides session expired message")
    func unauthorizedMessage() {
        let error = EmberError.unauthorized
        #expect(error.errorDescription?.contains("session") == true)
    }

    @Test("notFound provides resource-specific message")
    func notFoundMessage() {
        let error = EmberError.notFound("Character")
        #expect(error.errorDescription?.contains("Character") == true)
        #expect(error.errorDescription?.contains("not found") == true)
    }

    @Test("rateLimited provides wait message")
    func rateLimitedMessage() {
        let error = EmberError.rateLimited
        #expect(error.errorDescription?.contains("Too many requests") == true)
    }

    @Test("timeout provides retry message")
    func timeoutMessage() {
        let error = EmberError.timeout
        #expect(error.errorDescription?.contains("timed out") == true)
    }

    @Test("decodingError provides generic message")
    func decodingErrorMessage() {
        let error = EmberError.decodingError
        #expect(error.errorDescription?.contains("Something went wrong") == true)
    }

    @Test("unknown error preserves custom message")
    func unknownMessage() {
        let error = EmberError.unknown("Custom error text")
        #expect(error.errorDescription == "Custom error text")
    }

    // MARK: - Retry Semantics

    @Test("offline is retryable")
    func offlineIsRetryable() {
        #expect(EmberError.offline.isRetryable == true)
    }

    @Test("networkError is retryable")
    func networkErrorIsRetryable() {
        #expect(EmberError.networkError(underlyingDescription: "timeout").isRetryable == true)
    }

    @Test("timeout is retryable")
    func timeoutIsRetryable() {
        #expect(EmberError.timeout.isRetryable == true)
    }

    @Test("rateLimited is retryable")
    func rateLimitedIsRetryable() {
        #expect(EmberError.rateLimited.isRetryable == true)
    }

    @Test("serverError 500 is retryable")
    func serverError500IsRetryable() {
        #expect(EmberError.serverError(statusCode: 500, detail: "").isRetryable == true)
    }

    @Test("serverError 429 is retryable")
    func serverError429IsRetryable() {
        #expect(EmberError.serverError(statusCode: 429, detail: "").isRetryable == true)
    }

    @Test("serverError 400 is NOT retryable")
    func serverError400IsNotRetryable() {
        #expect(EmberError.serverError(statusCode: 400, detail: "").isRetryable == false)
    }

    @Test("unauthorized is NOT retryable")
    func unauthorizedIsNotRetryable() {
        #expect(EmberError.unauthorized.isRetryable == false)
    }

    @Test("notFound is NOT retryable")
    func notFoundIsNotRetryable() {
        #expect(EmberError.notFound("x").isRetryable == false)
    }

    @Test("decodingError is NOT retryable")
    func decodingErrorIsNotRetryable() {
        #expect(EmberError.decodingError.isRetryable == false)
    }

    @Test("unknown is NOT retryable")
    func unknownIsNotRetryable() {
        #expect(EmberError.unknown("msg").isRetryable == false)
    }

    // MARK: - requiresReauth

    @Test("unauthorized requires reauth")
    func unauthorizedRequiresReauth() {
        #expect(EmberError.unauthorized.requiresReauth == true)
    }

    @Test("offline does NOT require reauth")
    func offlineDoesNotRequireReauth() {
        #expect(EmberError.offline.requiresReauth == false)
    }

    // MARK: - Factory: from(Error)

    @Test("from: maps APIError.unauthorized to .unauthorized")
    func fromAPIErrorUnauthorized() {
        let result = EmberError.from(APIError.unauthorized)
        #expect(result == .unauthorized)
    }

    @Test("from: maps APIError.serverError to .serverError")
    func fromAPIErrorServerError() {
        let result = EmberError.from(APIError.serverError(statusCode: 503, detail: "Unavailable"))
        #expect(result == .serverError(statusCode: 503, detail: "Unavailable"))
    }

    @Test("from: maps APIError.serverError 404 to .notFound")
    func fromAPIError404() {
        let result = EmberError.from(APIError.serverError(statusCode: 404, detail: "Not found"))
        #expect(result == .notFound("Not found"))
    }

    @Test("from: maps APIError.serverError 429 to .rateLimited")
    func fromAPIError429() {
        let result = EmberError.from(APIError.serverError(statusCode: 429, detail: "Rate limit"))
        #expect(result == .rateLimited)
    }

    @Test("from: maps APIError.decodingError to .decodingError")
    func fromAPIErrorDecoding() {
        let decodingErr = NSError(domain: "test", code: 1)
        let result = EmberError.from(APIError.decodingError(decodingErr))
        #expect(result == .decodingError)
    }

    @Test("from: maps APIError.networkError with URLError.notConnectedToInternet to .offline")
    func fromAPIErrorNetworkOffline() {
        let urlError = URLError(.notConnectedToInternet)
        let result = EmberError.from(APIError.networkError(urlError))
        #expect(result == .offline)
    }

    @Test("from: maps APIError.networkError with URLError.timedOut to .timeout")
    func fromAPIErrorNetworkTimeout() {
        let urlError = URLError(.timedOut)
        let result = EmberError.from(APIError.networkError(urlError))
        #expect(result == .timeout)
    }

    @Test("from: maps AuthError.tokenUnavailable to .unauthorized")
    func fromAuthErrorTokenUnavailable() {
        let result = EmberError.from(AuthError.tokenUnavailable)
        #expect(result == .unauthorized)
    }

    @Test("from: maps AuthError.signInFailed to .unknown with message")
    func fromAuthErrorSignInFailed() {
        let result = EmberError.from(AuthError.signInFailed("Invalid credentials"))
        #expect(result == .unknown("Invalid credentials"))
    }

    @Test("from: maps URLError.notConnectedToInternet to .offline")
    func fromURLErrorOffline() {
        let result = EmberError.from(URLError(.notConnectedToInternet))
        #expect(result == .offline)
    }

    @Test("from: maps URLError.networkConnectionLost to .offline")
    func fromURLErrorConnectionLost() {
        let result = EmberError.from(URLError(.networkConnectionLost))
        #expect(result == .offline)
    }

    @Test("from: maps URLError.timedOut to .timeout")
    func fromURLErrorTimeout() {
        let result = EmberError.from(URLError(.timedOut))
        #expect(result == .timeout)
    }

    @Test("from: passes through existing EmberError unchanged")
    func fromEmberErrorPassthrough() {
        let original = EmberError.rateLimited
        let result = EmberError.from(original)
        #expect(result == .rateLimited)
    }

    @Test("from: maps unknown errors to .unknown")
    func fromUnknownError() {
        let genericError = NSError(domain: "test", code: 42, userInfo: [NSLocalizedDescriptionKey: "Test error"])
        let result = EmberError.from(genericError)
        #expect(result == .unknown("Test error"))
    }

    // MARK: - Equatable

    @Test("equatable: same cases are equal")
    func equatable() {
        #expect(EmberError.offline == EmberError.offline)
        #expect(EmberError.unauthorized == EmberError.unauthorized)
        #expect(EmberError.timeout == EmberError.timeout)
        #expect(EmberError.rateLimited == EmberError.rateLimited)
        #expect(EmberError.decodingError == EmberError.decodingError)
    }

    @Test("equatable: different cases are not equal")
    func notEquatable() {
        #expect(EmberError.offline != EmberError.timeout)
        #expect(EmberError.unauthorized != EmberError.rateLimited)
        #expect(EmberError.notFound("A") != EmberError.notFound("B"))
    }
}
