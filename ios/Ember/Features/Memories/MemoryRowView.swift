import SwiftUI

struct MemoryRowView: View {
    let memory: MemoryItem

    var body: some View {
        HStack(alignment: .top, spacing: .emberSpacing12) {
            leadingIcon
            memoryContent
        }
        .padding(.emberSpacing16)
        .background(
            RoundedRectangle(cornerRadius: .emberRadius12)
                .fill(Color.emberSurface2)
        )
        .emberCardShadowLight()
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilityText)
    }

    // MARK: - Subviews

    @ViewBuilder
    private var leadingIcon: some View {
        Image(systemName: EmberSymbol.memory)
            .font(.system(size: 16, weight: .medium))
            .foregroundStyle(Color.emberPrimary)
            .frame(width: 32, height: 32)
            .background(
                Circle()
                    .fill(Color.emberSurface3)
            )
            .accessibilityHidden(true)
    }

    @ViewBuilder
    private var memoryContent: some View {
        VStack(alignment: .leading, spacing: .emberSpacing4) {
            Text(memory.memory)
                .font(.emberBody)
                .foregroundStyle(Color.emberTextPrimary)
                .lineLimit(nil)
                .fixedSize(horizontal: false, vertical: true)

            if let createdAt = memory.createdAt {
                Text(createdAt, style: .relative)
                    .font(.emberMicro)
                    .foregroundStyle(Color.emberTextSecondary)
            }
        }
    }

    // MARK: - Accessibility

    private var accessibilityText: String {
        var text = "Memory: \(memory.memory)"
        if let createdAt = memory.createdAt {
            let formatter = RelativeDateTimeFormatter()
            formatter.unitsStyle = .full
            let relative = formatter.localizedString(for: createdAt, relativeTo: Date())
            text += ". Created \(relative)"
        }
        return text
    }
}
