import SwiftUI

struct LoginView: View {
    @Environment(AuthViewModel.self) private var viewModel
    @FocusState private var focusedField: Field?

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

                    // Password field
                    SecureField("Password", text: $viewModel.password)
                        .textContentType(.password)
                        .focused($focusedField, equals: .password)
                        .submitLabel(.go)
                        .onSubmit {
                            if viewModel.isSignInFormValid && !viewModel.isLoading {
                                Task { await viewModel.signIn() }
                            }
                        }
                        .accessibilityLabel("Password")
                        .modifier(AuthTextFieldStyle())
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
                .accessibilityLabel("Sign In")
                .padding(.horizontal, .emberSpacing20)

                // Sign Up link
                signUpLink
            }
            .padding(.bottom, .emberSpacing32)
        }
        .scrollDismissesKeyboard(.interactively)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.emberBackground.ignoresSafeArea())
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
