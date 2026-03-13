import SwiftUI

/// Compact audio progress bar displayed inside an AI message bubble during TTS playback.
/// Shows play/pause button, current time, scrubber slider, total duration, and speed toggle.
struct AudioProgressView: View {
    let isPlaying: Bool
    let isLoading: Bool
    let currentTime: Double
    let duration: Double
    let playbackSpeed: Float
    let onPlayPause: () -> Void
    let onSeek: (Double) -> Void
    let onCycleSpeed: () -> Void

    @State private var isDragging: Bool = false
    @State private var dragValue: Double = 0

    var body: some View {
        VStack(spacing: .emberSpacing4) {
            HStack(spacing: .emberSpacing8) {
                // Play / Pause button
                playPauseButton

                // Current time label
                Text(formatTime(isDragging ? dragValue : currentTime))
                    .font(.emberMicro)
                    .foregroundStyle(Color.emberTextSecondary)
                    .monospacedDigit()
                    .frame(width: 32, alignment: .trailing)

                // Scrubber slider
                scrubberSlider

                // Duration label
                Text(formatTime(duration))
                    .font(.emberMicro)
                    .foregroundStyle(Color.emberTextSecondary)
                    .monospacedDigit()
                    .frame(width: 32, alignment: .leading)

                // Speed button
                speedButton
            }
        }
        .padding(.top, .emberSpacing8)
    }

    // MARK: - Subviews

    @ViewBuilder
    private var playPauseButton: some View {
        Button(action: onPlayPause) {
            Group {
                if isLoading {
                    ProgressView()
                        .tint(Color.emberTextPrimary)
                        .scaleEffect(0.8)
                } else {
                    Image(systemName: isPlaying ? EmberSymbol.audioPause : EmberSymbol.audioPlay)
                        .font(.system(size: 18, weight: .medium))
                        .foregroundStyle(Color.emberTextPrimary)
                }
            }
            .frame(width: 28, height: 28)
        }
        .accessibilityLabel(isPlaying ? "Pause audio" : "Play audio")
    }

    @ViewBuilder
    private var scrubberSlider: some View {
        GeometryReader { geometry in
            let totalWidth = geometry.size.width
            let progress = duration > 0 ? (isDragging ? dragValue : currentTime) / duration : 0
            let clampedProgress = min(max(progress, 0), 1)

            ZStack(alignment: .leading) {
                // Track background
                Capsule()
                    .fill(Color.emberSurface3)
                    .frame(height: 3)

                // Filled portion
                Capsule()
                    .fill(Color.emberPrimary)
                    .frame(width: totalWidth * clampedProgress, height: 3)

                // Thumb indicator
                Circle()
                    .fill(Color.emberTextPrimary)
                    .frame(width: 10, height: 10)
                    .offset(x: totalWidth * clampedProgress - 5)
            }
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { gesture in
                        isDragging = true
                        let fraction = gesture.location.x / totalWidth
                        let clampedFraction = min(max(fraction, 0), 1)
                        dragValue = clampedFraction * duration
                    }
                    .onEnded { gesture in
                        let fraction = gesture.location.x / totalWidth
                        let clampedFraction = min(max(fraction, 0), 1)
                        let seekTime = clampedFraction * duration
                        onSeek(seekTime)
                        isDragging = false
                    }
            )
        }
        .frame(height: 16)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Audio progress")
        .accessibilityValue("\(formatTime(currentTime)) of \(formatTime(duration))")
    }

    @ViewBuilder
    private var speedButton: some View {
        Button(action: onCycleSpeed) {
            Text(speedLabel)
                .font(.system(size: 10, weight: .semibold, design: .monospaced))
                .foregroundStyle(Color.emberPrimary)
                .frame(width: 34, height: 20)
                .background(Color.emberPrimary.opacity(0.15))
                .clipShape(Capsule())
        }
        .accessibilityLabel("Playback speed \(speedLabel)")
        .accessibilityHint("Tap to change speed")
    }

    // MARK: - Helpers

    private var speedLabel: String {
        switch playbackSpeed {
        case 0.75: return ".75x"
        case 1.0:  return "1x"
        case 1.25: return "1.25x"
        case 1.5:  return "1.5x"
        default:   return "1x"
        }
    }

    /// Formats seconds into "M:SS" string.
    private func formatTime(_ seconds: Double) -> String {
        guard seconds.isFinite && seconds >= 0 else { return "0:00" }
        let totalSeconds = Int(seconds)
        let minutes = totalSeconds / 60
        let secs = totalSeconds % 60
        return String(format: "%d:%02d", minutes, secs)
    }
}
