import SwiftUI

@main
struct EmberApp: App {
    @State private var router = AppRouter()
    @State private var container = AppContainer()
    @State private var authViewModel = AuthViewModel()

    @AppStorage("hasCompletedOnboarding") private var hasCompletedOnboarding = false

    init() {
        AuthService.shared.configure()
    }

    var body: some Scene {
        WindowGroup {
            Group {
                if !authViewModel.isAuthenticated {
                    if authViewModel.isShowingSignUp {
                        SignUpView()
                    } else {
                        LoginView()
                    }
                } else if !hasCompletedOnboarding {
                    OnboardingPlaceholderView()
                } else {
                    MainTabView()
                }
            }
            .environment(router)
            .environment(container)
            .environment(authViewModel)
            .preferredColorScheme(.dark)
        }
    }
}
