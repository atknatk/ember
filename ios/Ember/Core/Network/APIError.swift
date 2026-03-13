import Foundation

/// Network layer error types with user-facing error messages.
///
/// - `unauthorized`: 401 after token refresh retry failed. Signals the caller should navigate to login.
/// - `serverError`: Non-2xx response with a parsed error body from the backend.
/// - `decodingError`: JSON decoding failure.
/// - `networkError`: Transport-level failure (no connection, timeout, etc.).
enum APIError: LocalizedError, Equatable {
    case unauthorized
    case serverError(statusCode: Int, detail: String)
    case decodingError(Error)
    case networkError(Error)

    var errorDescription: String? {
        switch self {
        case .unauthorized:
            return "Your session has expired. Please sign in again."
        case .serverError(let statusCode, let detail):
            if statusCode == 429 {
                return "Too many requests. Please wait a moment and try again."
            } else if statusCode >= 500 {
                return "Something went wrong. Please try again."
            } else {
                return detail
            }
        case .decodingError:
            return "Something went wrong. Please try again."
        case .networkError:
            return "Connection failed. Please check your internet and try again."
        }
    }

    // MARK: - Equatable

    /// Custom Equatable conformance because `Error` is not `Equatable`.
    /// `decodingError` and `networkError` compare by `localizedDescription`.
    static func == (lhs: APIError, rhs: APIError) -> Bool {
        switch (lhs, rhs) {
        case (.unauthorized, .unauthorized):
            return true
        case (.serverError(let lCode, let lDetail), .serverError(let rCode, let rDetail)):
            return lCode == rCode && lDetail == rDetail
        case (.decodingError(let lError), .decodingError(let rError)):
            return lError.localizedDescription == rError.localizedDescription
        case (.networkError(let lError), .networkError(let rError)):
            return lError.localizedDescription == rError.localizedDescription
        default:
            return false
        }
    }
}
