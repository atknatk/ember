import Foundation

enum APIError: LocalizedError {
    case httpError(statusCode: Int)
    case decodingError(Error)
    case networkError(Error)

    var errorDescription: String? {
        switch self {
        case .httpError(let code):
            return "Server error: \(code)"
        case .decodingError(let error):
            return "Data error: \(error.localizedDescription)"
        case .networkError(let error):
            return "Network error: \(error.localizedDescription)"
        }
    }
}
