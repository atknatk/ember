import SwiftUI

/// Animated three-dot "typing" indicator shown while the AI is generating a response.
/// Each dot bounces up and down with a staggered delay (400ms cycle per docs/14-tasarim.md).
struct TypingIndicatorView: View {
    @State private var isAnimating = false

    private let dotSize: CGFloat = 6
    private let bounceHeight: CGFloat = 4
    private let dotCount = 3
    private let animationDuration: Double = 0.4

    var body: some View {
        HStack(spacing: dotSize) {
            ForEach(0..<dotCount, id: \.self) { index in
                Circle()
                    .fill(Color.emberTextSecondary)
                    .frame(width: dotSize, height: dotSize)
                    .offset(y: isAnimating ? -bounceHeight : bounceHeight)
                    .animation(
                        .easeInOut(duration: animationDuration)
                            .repeatForever(autoreverses: true)
                            .delay(Double(index) * 0.15),
                        value: isAnimating
                    )
            }
        }
        .onAppear {
            isAnimating = true
        }
        .accessibilityLabel("Typing")
        .accessibilityHidden(false)
    }
}
