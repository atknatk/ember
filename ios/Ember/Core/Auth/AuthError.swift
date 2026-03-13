import Foundation

enum AuthError: LocalizedError, Equatable {
    case signInFailed(String)
    case signUpFailed(String)
    case tokenUnavailable
    case keychainError
    case notImplemented

    var errorDescription: String? {
        switch self {
        case .signInFailed(let message):
            return message
        case .signUpFailed(let message):
            return message
        case .tokenUnavailable:
            return "Your session has expired. Please sign in again."
        case .keychainError:
            return "Failed to save authentication data securely."
        case .notImplemented:
            return "Authentication is not yet implemented"
        }
    }
}
