import SwiftUI

struct OnboardingPlaceholderView: View {
    @AppStorage("hasCompletedOnboarding") private var hasCompletedOnboarding = false

    var body: some View {
        VStack(spacing: .emberSpacing24) {
            Image(systemName: "sparkles")
                .font(.system(size: 64, weight: .medium))
                .foregroundStyle(
                    LinearGradient(
                        colors: [Color.emberGradientStart, Color.emberGradientEnd],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .accessibilityHidden(true)

            Text("Welcome to Ember")
                .font(.emberLargeTitle)
                .foregroundStyle(Color.emberTextPrimary)

            Text("Let's personalize your experience")
                .font(.emberSecondary)
                .foregroundStyle(Color.emberTextSecondary)

            Button {
                hasCompletedOnboarding = true
            } label: {
                Text("Complete Onboarding")
                    .font(.emberHeadline)
                    .foregroundStyle(Color.emberTextPrimary)
                    .frame(maxWidth: .infinity)
                    .frame(height: 52)
                    .background(
                        LinearGradient(
                            colors: [Color.emberGradientStart, Color.emberGradientEnd],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )
                    .clipShape(RoundedRectangle(cornerRadius: .emberRadius28))
            }
            .accessibilityLabel("Complete Onboarding")
            .padding(.horizontal, .emberSpacing20)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.emberBackground.ignoresSafeArea())
    }
}
