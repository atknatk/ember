import SwiftUI

/// Text input bar at the bottom of the chat screen.
/// Contains a multiline text field and a send button.
struct ChatInputBar: View {
    @Binding var text: String
    let isSending: Bool
    let onSend: () -> Void

    @FocusState private var isFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
            Divider()
                .background(Color.emberSurface3)

            HStack(alignment: .bottom, spacing: .emberSpacing8) {
                // Text field
                TextField("Message...", text: $text, axis: .vertical)
                    .font(.emberBody)
                    .foregroundStyle(Color.emberTextPrimary)
                    .lineLimit(1...5)
                    .padding(.horizontal, .emberSpacing12)
                    .padding(.vertical, .emberSpacing8)
                    .background(Color.emberSurface2)
                    .clipShape(RoundedRectangle(cornerRadius: .emberRadius20))
                    .focused($isFocused)
                    .submitLabel(.send)
                    .onSubmit {
                        if canSend {
                            onSend()
                        }
                    }

                // Send button
                Button(action: {
                    guard canSend else { return }
                    HapticManager.impact(.light)
                    onSend()
                }) {
                    Image(systemName: EmberSymbol.send)
                        .font(.system(size: 28))
                        .foregroundStyle(canSend ? Color.emberPrimary : Color.emberTextDisabled)
                        .frame(width: 36, height: 36)
                }
                .disabled(!canSend)
                .accessibilityLabel("Send message")
            }
            .padding(.horizontal, .emberSpacing12)
            .padding(.vertical, .emberSpacing8)
            .background(Color.emberSurface)
        }
    }

    // MARK: - Private

    private var canSend: Bool {
        !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !isSending
    }
}
