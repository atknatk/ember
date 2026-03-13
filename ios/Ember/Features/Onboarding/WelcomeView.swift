import SwiftUI

struct WelcomeView: View {
    @Bindable var viewModel: OnboardingViewModel

    // MARK: - Page Data

    private struct WelcomePage {
        let lottieAsset: String
        let fallbackSymbol: String
        let title: String
        let description: String
    }

    private let pages: [WelcomePage] = [
        WelcomePage(
            lottieAsset: "onboarding-welcome",
            fallbackSymbol: "sparkles",
            title: "Meet Ember",
            description: "Your personal AI companion that remembers, understands, and grows with you."
        ),
        WelcomePage(
            lottieAsset: "onboarding-memory",
            fallbackSymbol: "brain.head.profile",
            title: "Built on Memory",
            description: "Every conversation builds a deeper understanding. Ember remembers what matters to you."
        ),
        WelcomePage(
            lottieAsset: "onboarding-companion",
            fallbackSymbol: "heart.fill",
            title: "Always Here for You",
            description: "Get personalized support, motivation, and genuine connection -- anytime you need it."
        ),
    ]

    var body: some View {
        VStack(spacing: 0) {
            TabView(selection: $viewModel.currentWelcomePage) {
                ForEach(0..<pages.count, id: \.self) { index in
                    pageContent(for: pages[index])
                        .tag(index)
                }
            }
            .tabViewStyle(.page(indexDisplayMode: .never))
            .onChange(of: viewModel.currentWelcomePage) { _, _ in
                HapticManager.selection()
            }

            // Page indicator dots
            pageIndicator
                .padding(.bottom, .emberSpacing24)
                .accessibilityHidden(true)

            // CTA button
            ctaButton
                .padding(.horizontal, .emberSpacing20)

            // Skip link (visible on pages 0 and 1)
            if viewModel.currentWelcomePage < 2 {
                Button {
                    withAnimation(.spring(response: 0.4)) {
                        viewModel.currentWelcomePage = 2
                    }
                } label: {
                    Text("Skip")
                        .font(.emberSecondary)
                        .foregroundStyle(Color.emberTextSecondary)
                }
                .accessibilityLabel("Skip to last welcome page")
                .padding(.top, .emberSpacing12)
            }

            Spacer()
                .frame(height: .emberSpacing48)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.emberBackground.ignoresSafeArea())
    }

    // MARK: - Page Content

    @ViewBuilder
    private func pageContent(for page: WelcomePage) -> some View {
        VStack(spacing: .emberSpacing24) {
            Spacer()

            // Lottie animation or fallback SF Symbol
            if Bundle.main.url(forResource: page.lottieAsset, withExtension: "json") != nil {
                LottieAnimationViewWrapper(animationName: page.lottieAsset)
                    .frame(height: 200)
                    .accessibilityHidden(true)
            } else {
                Image(systemName: page.fallbackSymbol)
                    .font(.system(size: 80, weight: .medium))
                    .foregroundStyle(
                        LinearGradient(
                            colors: [Color.emberGradientStart, Color.emberGradientEnd],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .frame(height: 200)
                    .accessibilityHidden(true)
            }

            Text(page.title)
                .font(.emberLargeTitle)
                .foregroundStyle(Color.emberTextPrimary)
                .multilineTextAlignment(.center)

            Text(page.description)
                .font(.emberBody)
                .foregroundStyle(Color.emberTextSecondary)
                .multilineTextAlignment(.center)
                .lineLimit(3)
                .padding(.horizontal, .emberSpacing20)

            Spacer()
        }
    }

    // MARK: - Page Indicator

    @ViewBuilder
    private var pageIndicator: some View {
        HStack(spacing: .emberSpacing8) {
            ForEach(0..<3, id: \.self) { index in
                Circle()
                    .fill(index == viewModel.currentWelcomePage ? Color.emberPrimary : Color.emberTextDisabled)
                    .frame(width: 8, height: 8)
                    .scaleEffect(index == viewModel.currentWelcomePage ? 1.0 : 0.8)
                    .animation(.spring(response: 0.3), value: viewModel.currentWelcomePage)
            }
        }
    }

    // MARK: - CTA Button

    @ViewBuilder
    private var ctaButton: some View {
        if viewModel.currentWelcomePage < 2 {
            // "Next" secondary button
            Button {
                withAnimation(.spring(response: 0.4)) {
                    viewModel.currentWelcomePage += 1
                }
            } label: {
                Text("Next")
                    .font(.emberHeadline)
                    .foregroundStyle(Color.emberPrimary)
                    .frame(maxWidth: .infinity)
                    .frame(height: 52)
                    .background(Color.clear)
                    .overlay(
                        RoundedRectangle(cornerRadius: .emberRadius28)
                            .stroke(Color.emberPrimary, lineWidth: 1)
                    )
                    .clipShape(RoundedRectangle(cornerRadius: .emberRadius28))
            }
            .accessibilityLabel("Next page")
        } else {
            // "Get Started" primary button
            Button {
                HapticManager.impact(.medium)
                withAnimation(.spring(response: 0.4)) {
                    viewModel.advanceToQuestions()
                }
            } label: {
                Text("Get Started")
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
            .accessibilityLabel("Get Started")
        }
    }
}
