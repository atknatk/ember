import SwiftUI

struct LoginView: View {
    @Environment(AuthViewModel.self) private var viewModel
    @FocusState private var focusedField: Field?
    @State private var isAppeared: Bool = false
    @State private var isPasswordVisible: Bool = false
    @State private var shakeOffset: CGFloat = 0

    private enum Field: Hashable {
        case email
        case password
    }

    var body: some View {
        @Bindable var viewModel = viewModel

        ScrollView {
            VStack(spacing: .emberSpacing24) {
                Spacer()
                    .frame(height: .emberSpacing48)

                // Logo area
                logoSection

                // Title
                VStack(spacing: .emberSpacing8) {
                    Text("Welcome Back")
                        .font(.emberTitle)
                        .foregroundStyle(Color.emberTextPrimary)

                    Text("Sign in to continue")
                        .font(.emberSecondary)
                        .foregroundStyle(Color.emberTextSecondary)
                }

                // Form fields
                VStack(spacing: .emberSpacing16) {
                    // Email field
                    VStack(alignment: .leading, spacing: .emberSpacing4) {
                        TextField("Email", text: $viewModel.email)
                            .keyboardType(.emailAddress)
                            .textContentType(.emailAddress)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled(true)
                            .focused($focusedField, equals: .email)
                            .submitLabel(.next)
                            .onSubmit { focusedField = .password }
                            .accessibilityLabel("Email address")
                            .modifier(AuthTextFieldStyle())

                        if viewModel.showEmailValidationError {
                            Text("Please enter a valid email")
                                .font(.emberCaption)
                                .foregroundStyle(Color.emberError)
                                .padding(.leading, .emberSpacing4)
                                .transition(.opacity.combined(with: .move(edge: .top)))
                        }
                    }

                    // Password field
                    passwordField
                }
                .padding(.horizontal, .emberSpacing20)

                // Sign In button
                Button {
                    focusedField = nil
                    Task { await viewModel.signIn() }
                } label: {
                    Group {
                        if viewModel.isLoading {
                            ProgressView()
                                .tint(Color.emberTextPrimary)
                        } else {
                            Text("Sign In")
                                .font(.emberHeadline)
                                .foregroundStyle(Color.emberTextPrimary)
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .frame(height: 52)
                    .background(
                        viewModel.isSignInFormValid && !viewModel.isLoading
                            ? Color.emberPrimary
                            : Color.emberTextDisabled
                    )
                    .clipShape(RoundedRectangle(cornerRadius: .emberRadius28))
                }
                .disabled(!viewModel.isSignInFormValid || viewModel.isLoading)
                .buttonStyle(.ember)
                .accessibilityLabel("Sign In")
                .accessibilityHint("Double tap to sign in with your email and password")
                .offset(x: shakeOffset)
                .padding(.horizontal, .emberSpacing20)

                // Sign Up link
                signUpLink
            }
            .padding(.bottom, .emberSpacing32)
        }
        .scrollDismissesKeyboard(.interactively)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.emberBackground.ignoresSafeArea())
        .opacity(isAppeared ? 1 : 0)
        .onAppear {
            withAnimation(.easeOut(duration: 0.3)) {
                isAppeared = true
            }
        }
        .onChange(of: focusedField) { oldValue, _ in
            if oldValue == .email {
                viewModel.emailHasBeenEdited = true
            }
        }
        .onChange(of: viewModel.showErrorShake) { _, newValue in
            if newValue {
                performShakeAnimation()
            }
        }
        .animation(.easeInOut(duration: 0.2), value: viewModel.showEmailValidationError)
        .alert("Error", isPresented: Binding(
            get: { viewModel.errorMessage != nil },
            set: { if !$0 { viewModel.clearError() } }
        )) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(viewModel.errorMessage ?? "")
        }
    }

    // MARK: - Subviews

    @ViewBuilder
    private var logoSection: some View {
        Image(systemName: "sparkles")
            .font(.system(size: 56, weight: .medium))
            .foregroundStyle(
                LinearGradient(
                    colors: [Color.emberGradientStart, Color.emberGradientEnd],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .accessibilityHidden(true)
    }

    @ViewBuilder
    private var passwordField: some View {
        ZStack(alignment: .trailing) {
            Group {
                if isPasswordVisible {
                    TextField("Password", text: Bindable(viewModel).password)
                        .textContentType(.password)
                } else {
                    SecureField("Password", text: Bindable(viewModel).password)
                        .textContentType(.password)
                }
            }
            .focused($focusedField, equals: .password)
            .submitLabel(.go)
            .onSubmit {
                if viewModel.isSignInFormValid && !viewModel.isLoading {
                    Task { await viewModel.signIn() }
                }
            }
            .accessibilityLabel("Password")
            .modifier(AuthTextFieldStyle())

            Button {
                isPasswordVisible.toggle()
            } label: {
                Image(systemName: isPasswordVisible ? "eye.slash.fill" : "eye.fill")
                    .font(.system(size: 17))
                    .foregroundStyle(Color.emberTextSecondary)
                    .frame(minWidth: 44, minHeight: 44)
            }
            .accessibilityLabel("Toggle password visibility")
            .accessibilityHint(isPasswordVisible ? "Double tap to hide password" : "Double tap to show password")
            .padding(.trailing, .emberSpacing8)
        }
    }

    @ViewBuilder
    private var signUpLink: some View {
        Button {
            viewModel.isShowingSignUp = true
        } label: {
            HStack(spacing: .emberSpacing4) {
                Text("Don't have an account?")
                    .foregroundStyle(Color.emberTextSecondary)
                Text("Sign Up")
                    .foregroundStyle(Color.emberPrimary)
            }
            .font(.emberSecondary)
        }
        .accessibilityLabel("Sign Up")
        .accessibilityHint("Double tap to navigate to sign up")
    }

    // MARK: - Animations

    private func performShakeAnimation() {
        withAnimation(.spring(response: 0.1, dampingFraction: 0.2)) {
            shakeOffset = -8
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
            withAnimation(.spring(response: 0.1, dampingFraction: 0.2)) {
                shakeOffset = 8
            }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
            withAnimation(.spring(response: 0.1, dampingFraction: 0.2)) {
                shakeOffset = -8
            }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
            withAnimation(.spring(response: 0.1, dampingFraction: 0.5)) {
                shakeOffset = 0
            }
        }
    }
}

// MARK: - Shared Text Field Style

struct AuthTextFieldStyle: ViewModifier {
    func body(content: Content) -> some View {
        content
            .font(.emberBody)
            .foregroundStyle(Color.emberTextPrimary)
            .padding(.horizontal, .emberSpacing16)
            .frame(height: 52)
            .background(Color.emberSurface2)
            .clipShape(RoundedRectangle(cornerRadius: .emberRadius12))
    }
}
