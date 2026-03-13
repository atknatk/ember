import Foundation

/// Centralized error type for all Ember iOS screens.
///
/// Wraps `APIError`, `AuthError`, and other domain errors into a single type
/// with user-friendly messages and retry semantics.
enum EmberError: LocalizedError, Equatable {
    /// No internet connection (detected by NetworkMonitor or transport error).
    case offline

    /// Network request failed (timeout, DNS, TLS, etc.).
    case networkError(underlyingDescription: String)

    /// Server returned a non-2xx status code.
    case serverError(statusCode: Int, detail: String)

    /// 401 after token refresh failed — user must re-authenticate.
    case unauthorized

    /// Requested resource was not found (404).
    case notFound(String)

    /// Rate limit exceeded (429).
    case rateLimited

    /// Request timed out.
    case timeout

    /// JSON decoding failure.
    case decodingError

    /// An unexpected error occurred.
    case unknown(String)

    // MARK: - User-Friendly Messages

    var errorDescription: String? {
        switch self {
        case .offline:
            return "You're offline. Please check your connection and try again."
        case .networkError:
            return "Connection failed. Please check your internet and try again."
        case .serverError(let statusCode, _):
            if statusCode >= 500 {
                return "Something went wrong on our end. Please try again."
            }
            return "Something went wrong. Please try again."
        case .unauthorized:
            return "Your session has expired. Please sign in again."
        case .notFound(let resource):
            return "\(resource) was not found."
        case .rateLimited:
            return "Too many requests. Please wait a moment and try again."
        case .timeout:
            return "Request timed out. Please try again."
        case .decodingError:
            return "Something went wrong. Please try again."
        case .unknown(let message):
            return message
        }
    }

    // MARK: - Retry Semantics

    /// Whether this error is likely transient and retrying may succeed.
    var isRetryable: Bool {
        switch self {
        case .offline, .networkError, .timeout, .rateLimited:
            return true
        case .serverError(let statusCode, _):
            return statusCode >= 500 || statusCode == 429
        case .unauthorized, .notFound, .decodingError, .unknown:
            return false
        }
    }

    /// Whether this error requires the user to re-authenticate.
    var requiresReauth: Bool {
        self == .unauthorized
    }

    // MARK: - Factory

    /// Creates an `EmberError` from any `Error`, mapping known types.
    static func from(_ error: Error) -> EmberError {
        // Already an EmberError
        if let emberError = error as? EmberError {
            return emberError
        }

        // Map APIError
        if let apiError = error as? APIError {
            return mapAPIError(apiError)
        }

        // Map AuthError
        if let authError = error as? AuthError {
            return mapAuthError(authError)
        }

        // Map URLError
        if let urlError = error as? URLError {
            return mapURLError(urlError)
        }

        return .unknown(error.localizedDescription)
    }

    // MARK: - Private Mappers

    private static func mapAPIError(_ error: APIError) -> EmberError {
        switch error {
        case .unauthorized:
            return .unauthorized
        case .serverError(let statusCode, let detail):
            if statusCode == 404 {
                return .notFound(detail)
            }
            if statusCode == 429 {
                return .rateLimited
            }
            return .serverError(statusCode: statusCode, detail: detail)
        case .decodingError:
            return .decodingError
        case .networkError(let underlyingError):
            if let urlError = underlyingError as? URLError {
                return mapURLError(urlError)
            }
            return .networkError(underlyingDescription: underlyingError.localizedDescription)
        }
    }

    private static func mapAuthError(_ error: AuthError) -> EmberError {
        switch error {
        case .tokenUnavailable:
            return .unauthorized
        case .signInFailed(let message):
            return .unknown(message)
        case .signUpFailed(let message):
            return .unknown(message)
        case .keychainError:
            return .unknown(error.errorDescription ?? "Authentication error")
        case .notImplemented:
            return .unknown(error.errorDescription ?? "Not implemented")
        }
    }

    private static func mapURLError(_ error: URLError) -> EmberError {
        switch error.code {
        case .notConnectedToInternet, .networkConnectionLost, .dataNotAllowed:
            return .offline
        case .timedOut:
            return .timeout
        case .cannotFindHost, .cannotConnectToHost, .dnsLookupFailed:
            return .networkError(underlyingDescription: error.localizedDescription)
        default:
            return .networkError(underlyingDescription: error.localizedDescription)
        }
    }

    // MARK: - Equatable

    static func == (lhs: EmberError, rhs: EmberError) -> Bool {
        switch (lhs, rhs) {
        case (.offline, .offline):
            return true
        case (.networkError(let lDesc), .networkError(let rDesc)):
            return lDesc == rDesc
        case (.serverError(let lCode, let lDetail), .serverError(let rCode, let rDetail)):
            return lCode == rCode && lDetail == rDetail
        case (.unauthorized, .unauthorized):
            return true
        case (.notFound(let lRes), .notFound(let rRes)):
            return lRes == rRes
        case (.rateLimited, .rateLimited):
            return true
        case (.timeout, .timeout):
            return true
        case (.decodingError, .decodingError):
            return true
        case (.unknown(let lMsg), .unknown(let rMsg)):
            return lMsg == rMsg
        default:
            return false
        }
    }
}
