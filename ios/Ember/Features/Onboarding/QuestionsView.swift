import SwiftUI

struct QuestionsView: View {
    @Bindable var viewModel: OnboardingViewModel
    var onComplete: () -> Void

    @FocusState private var isTextFieldFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
            // Progress indicator
            progressSection
                .padding(.top, .emberSpacing16)
                .padding(.horizontal, .emberSpacing20)

            // Question cards
            TabView(selection: $viewModel.currentQuestionIndex) {
                ForEach(0..<7, id: \.self) { index in
                    questionCard(at: index)
                        .tag(index)
                }
            }
            .tabViewStyle(.page(indexDisplayMode: .never))
            .disabled(true) // Disable swipe -- navigation via buttons only

            // Navigation buttons
            navigationButtons
                .padding(.horizontal, .emberSpacing20)
                .padding(.bottom, .emberSpacing32)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.emberBackground.ignoresSafeArea())
        .onChange(of: viewModel.currentQuestionIndex) { _, _ in
            HapticManager.selection()
            // Auto-focus text field after a brief delay
            isTextFieldFocused = false
            Task {
                try? await Task.sleep(nanoseconds: 300_000_000)
                isTextFieldFocused = true
            }
        }
        .alert("Error", isPresented: Binding(
            get: { viewModel.errorMessage != nil },
            set: { if !$0 { viewModel.errorMessage = nil } }
        )) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(viewModel.errorMessage ?? "")
        }
    }

    // MARK: - Progress Section

    @ViewBuilder
    private var progressSection: some View {
        VStack(spacing: .emberSpacing8) {
            Text("\(viewModel.currentQuestionIndex + 1)/7")
                .font(.emberCaption)
                .foregroundStyle(Color.emberTextSecondary)
                .accessibilityLabel("Question \(viewModel.currentQuestionIndex + 1) of 7")

            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Color.emberSurface3)
                        .frame(height: 4)

                    RoundedRectangle(cornerRadius: 2)
                        .fill(Color.emberPrimary)
                        .frame(width: geometry.size.width * viewModel.progressFraction, height: 4)
                        .animation(.easeInOut(duration: 0.3), value: viewModel.currentQuestionIndex)
                }
            }
            .frame(height: 4)
        }
    }

    // MARK: - Question Card

    @ViewBuilder
    private func questionCard(at index: Int) -> some View {
        ScrollView {
            VStack(spacing: .emberSpacing24) {
                Spacer()
                    .frame(height: .emberSpacing48)

                // Question number badge
                Circle()
                    .fill(Color.emberPrimary)
                    .frame(width: 32, height: 32)
                    .overlay(
                        Text("\(index + 1)")
                            .font(.emberHeadline)
                            .foregroundStyle(Color.white)
                    )

                // Question text
                Text(OnboardingViewModel.questionTexts[index])
                    .font(.emberTitle)
                    .foregroundStyle(Color.emberTextPrimary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, .emberSpacing20)

                // Text input
                TextField(
                    OnboardingViewModel.questionPlaceholders[index],
                    text: Binding(
                        get: { viewModel.answers[index] },
                        set: { viewModel.answers[index] = $0 }
                    )
                )
                .modifier(AuthTextFieldStyle())
                .focused($isTextFieldFocused)
                .submitLabel(index == 6 ? .done : .next)
                .onSubmit {
                    if index < 6 {
                        viewModel.advanceToNextQuestion()
                    }
                }
                .disabled(viewModel.isSubmitting)
                .accessibilityLabel("Answer for question \(index + 1)")
                .padding(.horizontal, .emberSpacing20)

                // Skip link
                Button {
                    HapticManager.selection()
                    if index == 6 {
                        Task {
                            let success = await viewModel.submitOnboarding()
                            if success {
                                HapticManager.notification(.success)
                                onComplete()
                            } else {
                                HapticManager.notification(.error)
                            }
                        }
                    } else {
                        viewModel.answers[index] = ""
                        viewModel.advanceToNextQuestion()
                    }
                } label: {
                    Text("Skip")
                        .font(.emberSecondary)
                        .foregroundStyle(Color.emberTextSecondary)
                }
                .disabled(viewModel.isSubmitting)
                .accessibilityLabel("Skip this question")

                Spacer()
            }
        }
        .scrollDismissesKeyboard(.interactively)
    }

    // MARK: - Navigation Buttons

    @ViewBuilder
    private var navigationButtons: some View {
        HStack(spacing: .emberSpacing16) {
            // Back button
            if viewModel.currentQuestionIndex > 0 {
                Button {
                    viewModel.goToPreviousQuestion()
                } label: {
                    HStack(spacing: .emberSpacing4) {
                        Image(systemName: EmberSymbol.back)
                        Text("Back")
                    }
                    .font(.emberHeadline)
                    .foregroundStyle(Color.emberTextSecondary)
                    .frame(height: 52)
                    .frame(maxWidth: .infinity)
                    .background(Color.emberSurface2)
                    .clipShape(RoundedRectangle(cornerRadius: .emberRadius28))
                }
                .disabled(viewModel.isSubmitting)
                .accessibilityLabel("Go to previous question")
            }

            // Next / Submit button
            if viewModel.currentQuestionIndex < 6 {
                Button {
                    viewModel.advanceToNextQuestion()
                } label: {
                    Text("Next")
                        .font(.emberHeadline)
                        .foregroundStyle(Color.emberTextPrimary)
                        .frame(height: 52)
                        .frame(maxWidth: .infinity)
                        .background(Color.emberPrimary)
                        .clipShape(RoundedRectangle(cornerRadius: .emberRadius28))
                }
                .disabled(viewModel.isSubmitting)
                .accessibilityLabel("Go to next question")
            } else {
                Button {
                    HapticManager.impact(.medium)
                    Task {
                        let success = await viewModel.submitOnboarding()
                        if success {
                            HapticManager.notification(.success)
                            onComplete()
                        } else {
                            HapticManager.notification(.error)
                        }
                    }
                } label: {
                    Group {
                        if viewModel.isSubmitting {
                            ProgressView()
                                .tint(Color.emberTextPrimary)
                        } else {
                            Text("Submit")
                                .font(.emberHeadline)
                                .foregroundStyle(Color.emberTextPrimary)
                        }
                    }
                    .frame(height: 52)
                    .frame(maxWidth: .infinity)
                    .background(
                        viewModel.canSubmit && !viewModel.isSubmitting
                            ? LinearGradient(
                                colors: [Color.emberGradientStart, Color.emberGradientEnd],
                                startPoint: .leading,
                                endPoint: .trailing
                            )
                            : LinearGradient(
                                colors: [Color.emberTextDisabled, Color.emberTextDisabled],
                                startPoint: .leading,
                                endPoint: .trailing
                            )
                    )
                    .clipShape(RoundedRectangle(cornerRadius: .emberRadius28))
                }
                .disabled(!viewModel.canSubmit || viewModel.isSubmitting)
                .accessibilityLabel("Submit onboarding answers")
            }
        }
    }
}
