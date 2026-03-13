import SwiftUI

extension Color {
    // MARK: - Brand

    /// Primary brand color — buttons, user message bubbles
    static let emberPrimary = Color(hex: "#5B4FE8")

    /// Pressed state of primary
    static let emberPrimaryPressed = Color(hex: "#4B3FD8")

    /// Hover/highlight state of primary
    static let emberPrimaryHover = Color(hex: "#6B5FF8")

    /// Proactive notifications, special events
    static let emberAccent = Color(hex: "#FF6B6B")

    // MARK: - Backgrounds

    /// Main background
    static let emberBackground = Color(hex: "#0F0F14")

    /// Surface-level containers, tab bar
    static let emberSurface = Color(hex: "#1A1A24")

    /// Cards, input fields, AI message bubbles
    static let emberSurface2 = Color(hex: "#22223A")

    /// Hover, active states
    static let emberSurface3 = Color(hex: "#2C2C4A")

    // MARK: - Text

    /// Primary text
    static let emberTextPrimary = Color(hex: "#F0F0F8")

    /// Secondary text, timestamps
    static let emberTextSecondary = Color(hex: "#9090B0")

    /// Disabled buttons, placeholders
    static let emberTextDisabled = Color(hex: "#5A5A7A")

    // MARK: - Status

    /// Success states
    static let emberSuccess = Color(hex: "#4CAF87")

    /// Warning states
    static let emberWarning = Color(hex: "#F5A623")

    /// Error states
    static let emberError = Color(hex: "#E85B5B")

    // MARK: - Gradients

    /// Onboarding gradient start
    static let emberGradientStart = Color(hex: "#5B4FE8")

    /// Onboarding gradient end
    static let emberGradientEnd = Color(hex: "#FF6B6B")

    /// AI message bubble gradient start
    static let emberAIBubbleStart = Color(hex: "#1E1E35")

    /// AI message bubble gradient end
    static let emberAIBubbleEnd = Color(hex: "#252545")

    // MARK: - Hex Initializer

    /// Creates a Color from a hex string.
    /// Supports 6-character (`#5B4FE8`) and 8-character (`#FF5B4FE8`) hex strings.
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)

        let alpha, red, green, blue: UInt64
        switch hex.count {
        case 6: // RGB (no alpha)
            (alpha, red, green, blue) = (255, (int >> 16) & 0xFF, (int >> 8) & 0xFF, int & 0xFF)
        case 8: // ARGB
            (alpha, red, green, blue) = ((int >> 24) & 0xFF, (int >> 16) & 0xFF, (int >> 8) & 0xFF, int & 0xFF)
        default:
            (alpha, red, green, blue) = (255, 0, 0, 0)
        }

        self.init(
            .sRGB,
            red: Double(red) / 255,
            green: Double(green) / 255,
            blue: Double(blue) / 255,
            opacity: Double(alpha) / 255
        )
    }
}
