import SwiftUI
import UIKit

/// Displays a single chat message bubble.
/// User messages appear on the right with primary color background.
/// Assistant messages appear on the left with surface2 background.
/// AI messages include a "Listen" button for TTS playback.
struct MessageBubbleView: View {
    let message: ChatMessage
    var audioPlayer: AudioPlayerManager?
    var isRequestingTTS: Bool = false
    var ttsRequestMessageId: String? = nil
    var onListenTapped: (() -> Void)? = nil

    var body: some View {
        HStack(alignment: .bottom, spacing: .emberSpacing8) {
            if message.role == .user {
                Spacer(minLength: 60)
            }

            VStack(alignment: message.role == .user ? .trailing : .leading, spacing: .emberSpacing4) {
                // Message content with optional TTS controls
                if message.isStreaming && message.content.isEmpty {
                    TypingIndicatorView()
                        .padding(.horizontal, .emberSpacing16)
                        .padding(.vertical, .emberSpacing12)
                        .background(bubbleBackground)
                        .clipShape(bubbleShape)
                } else {
                    VStack(alignment: .leading, spacing: 0) {
                        Text(message.content)
                            .font(.emberBody)
                            .foregroundStyle(textColor)
                            .lineSpacing(4)
                            .textSelection(.enabled)

                        // TTS controls for assistant messages
                        if message.role == .assistant && !message.isStreaming {
                            ttsSection
                        }
                    }
                    .padding(.horizontal, .emberSpacing16)
                    .padding(.vertical, .emberSpacing12)
                    .background(bubbleBackground)
                    .clipShape(bubbleShape)
                }

                // Timestamp
                Text(timestampString)
                    .font(.emberMicro)
                    .foregroundStyle(Color.emberTextSecondary)
                    .padding(.horizontal, .emberSpacing4)
            }

            if message.role == .assistant {
                Spacer(minLength: 60)
            }
        }
        .padding(.horizontal, .emberSpacing16)
        .contextMenu {
            Button {
                UIPasteboard.general.string = message.content
                HapticManager.notification(.success)
            } label: {
                Label("Copy", systemImage: EmberSymbol.copy)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilityText)
        .accessibilityHint("Long press to copy")
        .accessibilityAction(named: "Copy message") {
            UIPasteboard.general.string = message.content
        }
    }

    // MARK: - TTS Section

    @ViewBuilder
    private var ttsSection: some View {
        if let audioPlayer, audioPlayer.isActiveFor(messageId: message.id) {
            // Show full audio progress when this message is active
            AudioProgressView(
                isPlaying: audioPlayer.isPlaying,
                isLoading: audioPlayer.isLoading,
                currentTime: audioPlayer.currentTime,
                duration: audioPlayer.duration,
                playbackSpeed: audioPlayer.playbackSpeed,
                onPlayPause: { onListenTapped?() },
                onSeek: { time in audioPlayer.seek(to: time) },
                onCycleSpeed: { audioPlayer.cycleSpeed() }
            )
        } else {
            // Show compact listen button
            Button {
                onListenTapped?()
            } label: {
                HStack(spacing: .emberSpacing4) {
                    if isRequestingTTS && ttsRequestMessageId == message.id {
                        ProgressView()
                            .tint(Color.emberTextSecondary)
                            .scaleEffect(0.7)
                            .frame(width: 14, height: 14)
                    } else {
                        Image(systemName: EmberSymbol.speaker)
                            .font(.system(size: 12, weight: .medium))
                    }
                    Text("Listen")
                        .font(.emberMicro)
                }
                .foregroundStyle(Color.emberTextSecondary)
                .padding(.top, .emberSpacing8)
            }
            .disabled(isRequestingTTS)
            .accessibilityLabel("Listen to message")
            .accessibilityHint("Converts this message to speech and plays it")
        }
    }

    // MARK: - Styling

    @ViewBuilder
    private var bubbleBackground: some View {
        if message.role == .user {
            Color.emberPrimary
        } else {
            LinearGradient(
                colors: [Color.emberAIBubbleStart, Color.emberAIBubbleEnd],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        }
    }

    private var bubbleShape: UnevenRoundedRectangle {
        if message.role == .user {
            // User bubble: bottom-right corner is less rounded
            UnevenRoundedRectangle(
                topLeadingRadius: .emberRadius16,
                bottomLeadingRadius: .emberRadius16,
                bottomTrailingRadius: .emberRadius4,
                topTrailingRadius: .emberRadius16
            )
        } else {
            // Assistant bubble: bottom-left corner is less rounded
            UnevenRoundedRectangle(
                topLeadingRadius: .emberRadius16,
                bottomLeadingRadius: .emberRadius4,
                bottomTrailingRadius: .emberRadius16,
                topTrailingRadius: .emberRadius16
            )
        }
    }

    private var textColor: Color {
        message.role == .user ? .white : Color.emberTextPrimary
    }

    private var timestampString: String {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm"
        return formatter.string(from: message.createdAt)
    }

    private var accessibilityText: String {
        let sender = message.role == .user ? "You" : "Assistant"
        return "\(sender) said: \(message.content). \(timestampString)"
    }
}
