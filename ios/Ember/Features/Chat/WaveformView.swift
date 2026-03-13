import SwiftUI

/// Animated waveform visualization driven by audio power levels.
/// Displays a row of vertical bars whose heights reflect the current audio input.
struct WaveformView: View {
    /// Normalized audio levels (0.0 to 1.0). The view displays one bar per element.
    let levels: [CGFloat]

    /// Total height available for the tallest bar.
    var maxBarHeight: CGFloat = 28

    /// Width of each individual bar.
    var barWidth: CGFloat = 3

    /// Spacing between bars.
    var barSpacing: CGFloat = 2

    var body: some View {
        HStack(alignment: .center, spacing: barSpacing) {
            ForEach(Array(levels.enumerated()), id: \.offset) { _, level in
                RoundedRectangle(cornerRadius: barWidth / 2)
                    .fill(Color.emberPrimary)
                    .frame(width: barWidth, height: barHeight(for: level))
                    .animation(
                        .spring(response: 0.15, dampingFraction: 0.6),
                        value: level
                    )
            }
        }
    }

    // MARK: - Private

    /// Maps a normalized level (0.0-1.0) to a bar height with a minimum floor.
    private func barHeight(for level: CGFloat) -> CGFloat {
        let minHeight: CGFloat = 4
        return minHeight + (maxBarHeight - minHeight) * level
    }
}
