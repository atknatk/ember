import SwiftUI

struct ProfilePlaceholderView: View {
    var body: some View {
        VStack(spacing: .emberSpacing16) {
            Image(systemName: EmberSymbol.profile)
                .font(.system(size: 48, weight: .medium))
                .foregroundStyle(Color.emberPrimary)
                .accessibilityHidden(true)

            Text("Profile")
                .font(.emberTitle)
                .foregroundStyle(Color.emberTextPrimary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.emberBackground.ignoresSafeArea())
        .navigationTitle("Profile")
        .navigationBarTitleDisplayMode(.inline)
    }
}
