import Observation
import Foundation

@Observable
final class AppContainer {
    let apiClient: APIClientProtocol
    let authService: AuthServiceProtocol

    init(
        apiClient: APIClientProtocol = APIClient.shared,
        authService: AuthServiceProtocol = AuthService.shared
    ) {
        self.apiClient = apiClient
        self.authService = authService
    }
}
