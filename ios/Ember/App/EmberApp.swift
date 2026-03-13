import SwiftUI

@main
struct EmberApp: App {
    @State private var router = AppRouter()
    @State private var container = AppContainer()
    @State private var authViewModel = AuthViewModel()
    @State private var networkMonitor = NetworkMonitor()

    @AppStorage("hasCompletedOnboarding") private var hasCompletedOnboarding = false

    init() {
        AuthService.shared.configure()
    }

    var body: some Scene {
        WindowGroup {
            Group {
                if !authViewModel.isAuthenticated {
                    Group {
                        if authViewModel.isShowingSignUp {
                            SignUpView()
                                .transition(.asymmetric(
                                    insertion: .move(edge: .trailing).combined(with: .opacity),
                                    removal: .move(edge: .trailing).combined(with: .opacity)
                                ))
                        } else {
                            LoginView()
                                .transition(.asymmetric(
                                    insertion: .move(edge: .leading).combined(with: .opacity),
                                    removal: .move(edge: .leading).combined(with: .opacity)
                                ))
                        }
                    }
                    .animation(.easeInOut(duration: 0.3), value: authViewModel.isShowingSignUp)
                } else if !hasCompletedOnboarding {
                    OnboardingFlowView()
                        .transition(.opacity)
                } else {
                    MainTabView()
                        .transition(.opacity)
                }
            }
            .animation(.easeInOut(duration: 0.35), value: authViewModel.isAuthenticated)
            .environment(router)
            .environment(container)
            .environment(authViewModel)
            .environment(networkMonitor)
            .preferredColorScheme(.dark)
            .onAppear {
                networkMonitor.start()
            }
        }
    }
}
