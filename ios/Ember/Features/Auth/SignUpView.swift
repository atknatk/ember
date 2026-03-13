import SwiftUI

struct SignUpView: View {
    @Environment(AuthViewModel.self) private var viewModel
    @FocusState private var focusedField: Field?
    @State private var isAppeared: Bool = false
    @State private var isPasswordVisible: Bool = false
    @State private var isConfirmPasswordVisible: Bool = false
    @State private var shakeOffset: CGFloat = 0

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

                    // Confirm Password field
                    VStack(alignment: .leading, spacing: .emberSpacing4) {
                        confirmPasswordField

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
                .accessibilityHint("Double tap to create your account")
                .offset(x: shakeOffset)
                .padding(.horizontal, .emberSpacing20)

                // Sign In link
                signInLink
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
                    TextField("Password (8+ characters)", text: Bindable(viewModel).password)
                        .textContentType(.newPassword)
                } else {
                    SecureField("Password (8+ characters)", text: Bindable(viewModel).password)
                        .textContentType(.newPassword)
                }
            }
            .focused($focusedField, equals: .password)
            .submitLabel(.next)
            .onSubmit { focusedField = .confirmPassword }
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
    private var confirmPasswordField: some View {
        ZStack(alignment: .trailing) {
            Group {
                if isConfirmPasswordVisible {
                    TextField("Confirm Password", text: Bindable(viewModel).confirmPassword)
                        .textContentType(.newPassword)
                } else {
                    SecureField("Confirm Password", text: Bindable(viewModel).confirmPassword)
                        .textContentType(.newPassword)
                }
            }
            .focused($focusedField, equals: .confirmPassword)
            .submitLabel(.go)
            .onSubmit {
                if viewModel.isSignUpFormValid && !viewModel.isLoading {
                    Task { await viewModel.signUp() }
                }
            }
            .accessibilityLabel("Confirm Password")
            .modifier(AuthTextFieldStyle())

            Button {
                isConfirmPasswordVisible.toggle()
            } label: {
                Image(systemName: isConfirmPasswordVisible ? "eye.slash.fill" : "eye.fill")
                    .font(.system(size: 17))
                    .foregroundStyle(Color.emberTextSecondary)
                    .frame(minWidth: 44, minHeight: 44)
            }
            .accessibilityLabel("Toggle confirm password visibility")
            .accessibilityHint(isConfirmPasswordVisible ? "Double tap to hide password" : "Double tap to show password")
            .padding(.trailing, .emberSpacing8)
        }
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
        .accessibilityHint("Double tap to navigate to sign in")
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
