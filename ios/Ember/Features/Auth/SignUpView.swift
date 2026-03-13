import SwiftUI

struct SignUpView: View {
    @Environment(AuthViewModel.self) private var viewModel
    @FocusState private var focusedField: Field?

    private enum Field: Hashable {
        case name
        case email
        case password
        case confirmPassword
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
                    Text("Create Account")
                        .font(.emberTitle)
                        .foregroundStyle(Color.emberTextPrimary)

                    Text("Join Ember to get started")
                        .font(.emberSecondary)
                        .foregroundStyle(Color.emberTextSecondary)
                }

                // Form fields
                VStack(spacing: .emberSpacing16) {
                    // Name field
                    TextField("Full Name", text: $viewModel.name)
                        .textContentType(.name)
                        .focused($focusedField, equals: .name)
                        .submitLabel(.next)
                        .onSubmit { focusedField = .email }
                        .accessibilityLabel("Full Name")
                        .modifier(AuthTextFieldStyle())

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
                    SecureField("Password (8+ characters)", text: $viewModel.password)
                        .textContentType(.newPassword)
                        .focused($focusedField, equals: .password)
                        .submitLabel(.next)
                        .onSubmit { focusedField = .confirmPassword }
                        .accessibilityLabel("Password")
                        .modifier(AuthTextFieldStyle())

                    // Confirm Password field
                    VStack(alignment: .leading, spacing: .emberSpacing4) {
                        SecureField("Confirm Password", text: $viewModel.confirmPassword)
                            .textContentType(.newPassword)
                            .focused($focusedField, equals: .confirmPassword)
                            .submitLabel(.go)
                            .onSubmit {
                                if viewModel.isSignUpFormValid && !viewModel.isLoading {
                                    Task { await viewModel.signUp() }
                                }
                            }
                            .accessibilityLabel("Confirm Password")
                            .modifier(AuthTextFieldStyle())

                        if viewModel.passwordsDoNotMatch {
                            Text("Passwords do not match")
                                .font(.emberCaption)
                                .foregroundStyle(Color.emberError)
                                .padding(.leading, .emberSpacing4)
                        }
                    }
                }
                .padding(.horizontal, .emberSpacing20)

                // Create Account button
                Button {
                    focusedField = nil
                    Task { await viewModel.signUp() }
                } label: {
                    Group {
                        if viewModel.isLoading {
                            ProgressView()
                                .tint(Color.emberTextPrimary)
                        } else {
                            Text("Create Account")
                                .font(.emberHeadline)
                                .foregroundStyle(Color.emberTextPrimary)
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .frame(height: 52)
                    .background(
                        viewModel.isSignUpFormValid && !viewModel.isLoading
                            ? Color.emberPrimary
                            : Color.emberTextDisabled
                    )
                    .clipShape(RoundedRectangle(cornerRadius: .emberRadius28))
                }
                .disabled(!viewModel.isSignUpFormValid || viewModel.isLoading)
                .accessibilityLabel("Create Account")
                .padding(.horizontal, .emberSpacing20)

                // Sign In link
                signInLink
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
    private var signInLink: some View {
        Button {
            viewModel.isShowingSignUp = false
        } label: {
            HStack(spacing: .emberSpacing4) {
                Text("Already have an account?")
                    .foregroundStyle(Color.emberTextSecondary)
                Text("Sign In")
                    .foregroundStyle(Color.emberPrimary)
            }
            .font(.emberSecondary)
        }
        .accessibilityLabel("Sign In")
    }
}
