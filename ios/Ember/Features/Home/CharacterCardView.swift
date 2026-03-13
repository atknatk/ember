import SwiftUI

struct CharacterCardView: View {
    let character: Character
    let lastMessage: MessagePreview?
    let hasUnread: Bool
    let onTap: () -> Void

    var body: some View {
        Button(action: {
            HapticManager.selection()
            onTap()
        }) {
            VStack(spacing: .emberSpacing8) {
                // Avatar circle
                ZStack {
                    Circle()
                        .fill(Color.emberSurface3)
                        .frame(width: 56, height: 56)

                    Image(systemName: HomeViewModel.templateIcon(for: character.template))
                        .font(.system(size: 22))
                        .foregroundStyle(Color.emberPrimary)
                }
                .accessibilityHidden(true)

                // Character name
                Text(character.name)
                    .font(.emberHeadline)
                    .foregroundStyle(Color.emberTextPrimary)
                    .lineLimit(1)

                // Last message preview
                if let lastMessage {
                    Text(lastMessage.content)
                        .font(.emberSecondary)
                        .foregroundStyle(Color.emberTextSecondary)
                        .lineLimit(2)
                        .multilineTextAlignment(.center)
                } else {
                    Text("No messages yet")
                        .font(.emberSecondary)
                        .foregroundStyle(Color.emberTextDisabled)
                        .lineLimit(1)
                }

                // Time badge
                if let lastMessageAt = character.lastMessageAt {
                    Text(relativeTimeString(from: lastMessageAt))
                        .font(.emberMicro)
                        .foregroundStyle(Color.emberTextSecondary)
                }
            }
            .padding(.emberSpacing16)
            .frame(maxWidth: .infinity)
            .background(Color.emberSurface2)
            .clipShape(RoundedRectangle(cornerRadius: .emberRadius20))
            .overlay(alignment: .topTrailing) {
                // Unread dot
                if hasUnread {
                    Circle()
                        .fill(Color.emberAccent)
                        .frame(width: 8, height: 8)
                        .padding(.emberSpacing8)
                        .transition(.scale.combined(with: .opacity))
                }
            }
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(cardAccessibilityLabel)
    }

    // MARK: - Private

    private var cardAccessibilityLabel: String {
        var label = "\(character.name), \(character.template) character"
        if let lastMessage {
            label += ". Last message: \(lastMessage.content)"
        }
        if let lastMessageAt = character.lastMessageAt {
            label += ". \(relativeTimeString(from: lastMessageAt))"
        }
        if hasUnread {
            label += ", new message"
        }
        return label
    }

    private func relativeTimeString(from date: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        return formatter.localizedString(for: date, relativeTo: Date())
    }
}

// MARK: - Add Character Card

struct AddCharacterCardView: View {
    let onTap: () -> Void

    var body: some View {
        Button(action: {
            HapticManager.impact(.light)
            onTap()
        }) {
            VStack(spacing: .emberSpacing8) {
                Image(systemName: EmberSymbol.addCharacter)
                    .font(.system(size: 28))
                    .foregroundStyle(Color.emberPrimary)

                Text("Add Character")
                    .font(.emberCaption)
                    .foregroundStyle(Color.emberTextSecondary)
            }
            .padding(.emberSpacing16)
            .frame(maxWidth: .infinity)
            .frame(minHeight: 140)
            .background(Color.clear)
            .overlay(
                RoundedRectangle(cornerRadius: .emberRadius20)
                    .strokeBorder(
                        Color.emberTextDisabled,
                        style: StrokeStyle(lineWidth: 1.5, dash: [8])
                    )
            )
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Add a new character")
    }
}
