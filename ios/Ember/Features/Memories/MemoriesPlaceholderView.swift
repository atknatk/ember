import SwiftUI

struct MemoriesPlaceholderView: View {
    var body: some View {
        VStack(spacing: .emberSpacing16) {
            Image(systemName: EmberSymbol.memoryTab)
                .font(.system(size: 48, weight: .medium))
                .foregroundStyle(Color.emberPrimary)
                .accessibilityHidden(true)

            Text("Memories")
                .font(.emberTitle)
                .foregroundStyle(Color.emberTextPrimary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.emberBackground.ignoresSafeArea())
        .navigationTitle("Memories")
        .navigationBarTitleDisplayMode(.inline)
    }
}
