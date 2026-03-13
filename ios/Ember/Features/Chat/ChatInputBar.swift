import SwiftUI

/// Text input bar at the bottom of the chat screen.
/// Contains a multiline text field, a send button, and a mic button for voice recording.
/// The mic button appears when the text field is empty; the send button appears when text is present.
struct ChatInputBar: View {
    @Binding var text: String
    let isSending: Bool
    let isRecording: Bool
    let isProcessingVoice: Bool
    let onSend: () -> Void
    let onStartRecording: () -> Void
    let onStopRecording: () -> Void

    @FocusState private var isFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
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
                    .disabled(isRecording || isProcessingVoice)

                // Send or Mic button
                if showMicButton {
                    micButton
                } else {
                    sendButton
                }
            }
            .padding(.horizontal, .emberSpacing12)
            .padding(.vertical, .emberSpacing8)
            .background(Color.emberSurface)
            .shadow(color: Color.black.opacity(0.2), radius: 4, y: -2)
        }
    }

    // MARK: - Subviews

    @ViewBuilder
    private var sendButton: some View {
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
        .buttonStyle(.ember)
        .accessibilityLabel("Send message")
    }

    @ViewBuilder
    private var micButton: some View {
        Button(action: {}) {
            Image(systemName: EmberSymbol.microphone)
                .font(.system(size: 22))
                .foregroundStyle(micButtonColor)
                .frame(width: 36, height: 36)
        }
        .disabled(isSending || isProcessingVoice)
        .buttonStyle(.ember)
        .accessibilityLabel(isRecording ? "Stop recording" : "Record voice message")
        .accessibilityHint(isRecording ? "Release to stop recording" : "Press and hold to record a voice message")
        .simultaneousGesture(
            LongPressGesture(minimumDuration: 0.3)
                .onEnded { _ in
                    if !isRecording && !isSending && !isProcessingVoice {
                        onStartRecording()
                    }
                }
        )
        .onLongPressGesture(minimumDuration: .infinity, pressing: { isPressing in
            // When the user releases after a long press has started
            if !isPressing && isRecording {
                onStopRecording()
            }
        }, perform: {})
    }

    // MARK: - Private

    private var canSend: Bool {
        !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !isSending
    }

    /// Show mic button when text is empty and not currently sending.
    private var showMicButton: Bool {
        text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private var micButtonColor: Color {
        if isRecording {
            return Color.emberError
        } else if isSending || isProcessingVoice {
            return Color.emberTextDisabled
        } else {
            return Color.emberPrimary
        }
    }
}
