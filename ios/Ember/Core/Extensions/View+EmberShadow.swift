import SwiftUI

/// Standard card shadow modifier for Ember cards.
/// Creates a subtle lift effect consistent across all card components.
struct EmberCardShadow: ViewModifier {
    let radius: CGFloat
    let y: CGFloat
    let opacity: Double

    init(radius: CGFloat = 8, y: CGFloat = 4, opacity: Double = 0.3) {
        self.radius = radius
        self.y = y
        self.opacity = opacity
    }

    func body(content: Content) -> some View {
        content
            .shadow(color: Color.black.opacity(opacity), radius: radius, y: y)
    }
}

/// Lighter shadow variant for smaller elements like MemoryRowView.
struct EmberCardShadowLight: ViewModifier {
    func body(content: Content) -> some View {
        content
            .shadow(color: Color.black.opacity(0.15), radius: 4, y: 2)
    }
}

extension View {
    /// Applies the standard Ember card shadow (radius: 8, y: 4, opacity: 0.3).
    func emberCardShadow() -> some View {
        modifier(EmberCardShadow())
    }

    /// Applies a lighter Ember shadow for smaller elements (radius: 4, y: 2, opacity: 0.15).
    func emberCardShadowLight() -> some View {
        modifier(EmberCardShadowLight())
    }
}
