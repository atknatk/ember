import SwiftUI

struct LoginPlaceholderView: View {
    @AppStorage("isAuthenticated") private var isAuthenticated = false

    var body: some View {
        VStack(spacing: .emberSpacing24) {
            Image(systemName: "lock.circle.fill")
                .font(.system(size: 64, weight: .medium))
                .foregroundStyle(Color.emberPrimary)
                .accessibilityHidden(true)

            Text("Login")
                .font(.emberLargeTitle)
                .foregroundStyle(Color.emberTextPrimary)

            Text("Sign in to continue")
                .font(.emberSecondary)
                .foregroundStyle(Color.emberTextSecondary)

            Button {
                isAuthenticated = true
            } label: {
                Text("Sign In")
                    .font(.emberHeadline)
                    .foregroundStyle(Color.emberTextPrimary)
                    .frame(maxWidth: .infinity)
                    .frame(height: 52)
                    .background(Color.emberPrimary)
                    .clipShape(RoundedRectangle(cornerRadius: .emberRadius28))
            }
            .accessibilityLabel("Sign In")
            .padding(.horizontal, .emberSpacing20)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.emberBackground.ignoresSafeArea())
    }
}
