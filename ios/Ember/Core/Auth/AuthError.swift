import Foundation

enum AuthError: LocalizedError {
    case signInFailed(String)
    case tokenUnavailable
    case notImplemented

    var errorDescription: String? {
        switch self {
        case .signInFailed(let message):
            return message
        case .tokenUnavailable:
            return "Authentication token unavailable"
        case .notImplemented:
            return "Authentication is not yet implemented"
        }
    }
}
