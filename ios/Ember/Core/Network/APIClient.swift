import Foundation

protocol APIClientProtocol: AnyObject, Sendable {}

final class APIClient: APIClientProtocol, @unchecked Sendable {
    static let shared = APIClient()

    let baseURL: URL

    private init() {
        let urlString = ProcessInfo.processInfo.environment["API_BASE_URL"] ?? "https://api.ember.ai"
        guard let url = URL(string: urlString) else {
            self.baseURL = URL(string: "https://api.ember.ai")!
            return
        }
        self.baseURL = url
    }
}
