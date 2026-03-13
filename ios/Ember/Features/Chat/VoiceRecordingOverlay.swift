import SwiftUI

/// Recording state overlay displayed over the ChatInputBar when voice recording is active.
/// Shows a pulsing record indicator, waveform visualization, duration timer,
/// and a "Slide up to cancel" hint.
struct VoiceRecordingOverlay: View {
    let audioLevels: [CGFloat]
    let duration: TimeInterval
    let isProcessing: Bool
    let onCancel: () -> Void

    /// Tracks the vertical drag offset for the cancel gesture.
    @State private var dragOffset: CGFloat = 0

    /// Pulsing animation state for the record dot.
    @State private var isPulsing: Bool = false

    /// Threshold (in points) for the upward swipe to cancel.
    private let cancelThreshold: CGFloat = 60

    var body: some View {
        VStack(spacing: .emberSpacing8) {
            // Cancel hint at the top
            if !isProcessing {
                cancelHint
                    .opacity(cancelProgress)
            }

            // Main recording bar
            HStack(spacing: .emberSpacing12) {
                // Recording dot
                recordingDot

                if isProcessing {
                    processingView
                } else {
                    // Waveform
                    WaveformView(levels: audioLevels)
                        .frame(maxWidth: .infinity)
                        .frame(height: 28)

                    // Duration timer
                    Text(formattedDuration)
                        .font(.emberCaption)
                        .foregroundStyle(Color.emberTextPrimary)
                        .monospacedDigit()
                }
            }
            .padding(.horizontal, .emberSpacing16)
            .padding(.vertical, .emberSpacing12)
            .background(Color.emberSurface)
            .shadow(color: Color.black.opacity(0.3), radius: 4, y: -2)
        }
        .offset(y: min(0, dragOffset))
        .opacity(isCancelling ? 0.5 : 1.0)
        .gesture(
            DragGesture(minimumDistance: 10)
                .onChanged { value in
                    // Only track upward drags (negative y translation)
                    dragOffset = min(0, value.translation.height)
                }
                .onEnded { value in
                    if value.translation.height < -cancelThreshold {
                        HapticManager.notification(.warning)
                        onCancel()
                    }
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                        dragOffset = 0
                    }
                }
        )
    }

    // MARK: - Subviews

    @ViewBuilder
    private var recordingDot: some View {
        Circle()
            .fill(Color.emberError)
            .frame(width: 10, height: 10)
            .scaleEffect(isPulsing ? 1.2 : 0.8)
            .opacity(isPulsing ? 1.0 : 0.6)
            .animation(
                .easeInOut(duration: 0.6)
                .repeatForever(autoreverses: true),
                value: isPulsing
            )
            .onAppear { isPulsing = true }
            .accessibilityHidden(true)
    }

    @ViewBuilder
    private var cancelHint: some View {
        VStack(spacing: .emberSpacing4) {
            Image(systemName: "chevron.up")
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(Color.emberTextSecondary)

            Text("Slide up to cancel")
                .font(.emberMicro)
                .foregroundStyle(Color.emberTextSecondary)
        }
        .padding(.top, .emberSpacing4)
    }

    @ViewBuilder
    private var processingView: some View {
        HStack(spacing: .emberSpacing8) {
            ProgressView()
                .tint(Color.emberPrimary)
                .scaleEffect(0.8)

            Text("Transcribing...")
                .font(.emberSecondary)
                .foregroundStyle(Color.emberTextSecondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: - Computed Properties

    private var formattedDuration: String {
        let minutes = Int(duration) / 60
        let seconds = Int(duration) % 60
        return String(format: "%d:%02d", minutes, seconds)
    }

    private var isCancelling: Bool {
        dragOffset < -cancelThreshold
    }

    /// Progress value (0.0 to 1.0) for how close the drag is to triggering cancel.
    private var cancelProgress: Double {
        guard dragOffset < 0 else { return 0 }
        return min(1.0, Double(abs(dragOffset)) / Double(cancelThreshold))
    }
}
