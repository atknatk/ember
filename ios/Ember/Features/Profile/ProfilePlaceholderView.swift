import SwiftUI

struct ProfilePlaceholderView: View {
    @Environment(AuthViewModel.self) private var authViewModel

    var body: some View {
        VStack(spacing: .emberSpacing16) {
            Image(systemName: EmberSymbol.profile)
                .font(.system(size: 48, weight: .medium))
                .foregroundStyle(Color.emberPrimary)
                .accessibilityHidden(true)

            Text("Profile")
                .font(.emberTitle)
                .foregroundStyle(Color.emberTextPrimary)

            Spacer()
                .frame(height: .emberSpacing24)

            Button {
                Task {
                    await authViewModel.signOut()
                }
            } label: {
                Text("Sign Out")
                    .font(.emberHeadline)
                    .foregroundStyle(Color.emberError)
            }
            .accessibilityLabel("Sign Out")
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.emberBackground.ignoresSafeArea())
        .navigationTitle("Profile")
        .navigationBarTitleDisplayMode(.inline)
    }
}
