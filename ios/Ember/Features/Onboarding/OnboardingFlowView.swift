import SwiftUI

struct OnboardingFlowView: View {
    @AppStorage("hasCompletedOnboarding") private var hasCompletedOnboarding = false
    @State private var viewModel = OnboardingViewModel()

    var body: some View {
        Group {
            switch viewModel.currentPhase {
            case .welcome:
                WelcomeView(viewModel: viewModel)
                    .transition(.move(edge: .leading))

            case .questions:
                QuestionsView(viewModel: viewModel) {
                    hasCompletedOnboarding = true
                }
                .transition(.move(edge: .trailing))
            }
        }
        .animation(.spring(response: 0.4), value: viewModel.currentPhase)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.emberBackground.ignoresSafeArea())
    }
}
