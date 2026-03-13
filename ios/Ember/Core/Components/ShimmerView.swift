import SwiftUI

/// A view that renders a rounded rectangle with a sweeping gradient animation
/// to simulate content loading. The gradient moves from leading to trailing
/// over 1.2 seconds and repeats.
struct ShimmerView: View {
    let cornerRadius: CGFloat

    @State private var phase: CGFloat = -1

    init(cornerRadius: CGFloat = .emberRadius12) {
        self.cornerRadius = cornerRadius
    }

    var body: some View {
        RoundedRectangle(cornerRadius: cornerRadius)
            .fill(Color.emberSurface2)
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius)
                    .fill(shimmerGradient)
                    .mask(RoundedRectangle(cornerRadius: cornerRadius))
            )
            .onAppear {
                withAnimation(
                    .linear(duration: 1.2)
                    .repeatForever(autoreverses: false)
                ) {
                    phase = 1
                }
            }
    }

    private var shimmerGradient: LinearGradient {
        LinearGradient(
            gradient: Gradient(colors: [
                Color.clear,
                Color.emberSurface3.opacity(0.6),
                Color.clear
            ]),
            startPoint: UnitPoint(x: phase - 0.5, y: 0.5),
            endPoint: UnitPoint(x: phase + 0.5, y: 0.5)
        )
    }
}

/// Applies the shimmer gradient overlay to any view shape.
/// Used by skeleton views that need non-rectangular shapes (e.g., circles for avatars).
struct ShimmerModifier: ViewModifier {
    @State private var phase: CGFloat = -1

    func body(content: Content) -> some View {
        content
            .overlay(
                LinearGradient(
                    gradient: Gradient(colors: [
                        Color.clear,
                        Color.emberSurface3.opacity(0.6),
                        Color.clear
                    ]),
                    startPoint: UnitPoint(x: phase - 0.5, y: 0.5),
                    endPoint: UnitPoint(x: phase + 0.5, y: 0.5)
                )
                .mask(content)
            )
            .onAppear {
                withAnimation(
                    .linear(duration: 1.2)
                    .repeatForever(autoreverses: false)
                ) {
                    phase = 1
                }
            }
    }
}

extension View {
    /// Applies a shimmer animation overlay to the view.
    func shimmer() -> some View {
        modifier(ShimmerModifier())
    }
}
