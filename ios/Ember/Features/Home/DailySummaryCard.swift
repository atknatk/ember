import SwiftUI

struct DailySummaryCard: View {
    let characterName: String?
    let message: MessagePreview?
    let onTap: () -> Void

    var body: some View {
        Button(action: {
            HapticManager.selection()
            onTap()
        }) {
            HStack(spacing: 0) {
                // Left edge accent bar
                RoundedRectangle(cornerRadius: 2)
                    .fill(Color.emberPrimary)
                    .frame(width: 3)
                    .padding(.vertical, .emberSpacing8)

                VStack(alignment: .leading, spacing: .emberSpacing8) {
                    if let characterName {
                        Text(characterName)
                            .font(.emberCaption)
                            .foregroundStyle(Color.emberTextSecondary)
                    }

                    if let message {
                        Text(message.content)
                            .font(.emberBody)
                            .foregroundStyle(Color.emberTextPrimary)
                            .lineLimit(3)
                            .multilineTextAlignment(.leading)

                        HStack {
                            Spacer()
                            Text(relativeTimeString(from: message.createdAt))
                                .font(.emberMicro)
                                .foregroundStyle(Color.emberTextSecondary)
                        }
                    } else {
                        Text("Start a conversation with your companion")
                            .font(.emberBody)
                            .foregroundStyle(Color.emberTextSecondary)
                    }
                }
                .padding(.leading, .emberSpacing12)
                .padding(.trailing, .emberSpacing16)
                .padding(.vertical, .emberSpacing16)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                LinearGradient(
                    colors: [Color.emberSurface2, Color.emberSurface3],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .clipShape(RoundedRectangle(cornerRadius: .emberRadius20))
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilityText)
        .accessibilityHint(characterName != nil ? "Opens chat with \(characterName ?? "")" : "")
    }

    // MARK: - Private

    private var accessibilityText: String {
        if let characterName, let message {
            return "Daily summary from \(characterName): \(message.content)"
        }
        return "Start a conversation with your companion"
    }

    private func relativeTimeString(from date: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        return formatter.localizedString(for: date, relativeTo: Date())
    }
}
