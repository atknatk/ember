import SwiftUI

/// A `ButtonStyle` that scales the button content to 0.85 on press
/// and returns to 1.0 with a spring animation.
/// Used for the send button in ChatInputBar and primary CTA buttons.
struct ScaleButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.85 : 1.0)
            .animation(
                .spring(response: 0.2, dampingFraction: 0.6),
                value: configuration.isPressed
            )
    }
}

extension ButtonStyle where Self == ScaleButtonStyle {
    /// Scale button style per Ember design system: 1.0 -> 0.85 -> 1.0 on tap.
    static var ember: ScaleButtonStyle { ScaleButtonStyle() }
}
