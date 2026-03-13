import Testing
@testable import Ember

@Suite("AppContainer")
struct AppContainerTests {

    @Test("default init creates container with non-nil dependencies")
    func defaultInitCreatesContainer() {
        let container = AppContainer()

        #expect(container.apiClient is APIClient)
        #expect(container.authService is AuthService)
    }
}
