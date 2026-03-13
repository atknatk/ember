import SwiftUI

@main
struct EmberApp: App {
    @State private var router = AppRouter()
    @State private var container = AppContainer()

    @AppStorage("isAuthenticated") private var isAuthenticated = false
    @AppStorage("hasCompletedOnboarding") private var hasCompletedOnboarding = false

    init() {
        AuthService.shared.configure()
    }

    var body: some Scene {
        WindowGroup {
            Group {
                if !isAuthenticated {
                    LoginPlaceholderView()
                } else if !hasCompletedOnboarding {
                    OnboardingPlaceholderView()
                } else {
                    MainTabView()
                }
            }
            .environment(router)
            .environment(container)
            .preferredColorScheme(.dark)
        }
    }
}
