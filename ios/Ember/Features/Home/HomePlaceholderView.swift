import SwiftUI

struct HomePlaceholderView: View {
    var body: some View {
        VStack(spacing: .emberSpacing16) {
            Image(systemName: "house.fill")
                .font(.system(size: 48, weight: .medium))
                .foregroundStyle(Color.emberPrimary)
                .accessibilityHidden(true)

            Text("Home")
                .font(.emberTitle)
                .foregroundStyle(Color.emberTextPrimary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.emberBackground.ignoresSafeArea())
        .navigationTitle("Home")
        .navigationBarTitleDisplayMode(.inline)
    }
}
