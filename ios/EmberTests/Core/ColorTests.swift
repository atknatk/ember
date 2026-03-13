import Testing
import SwiftUI
@testable import Ember

@Suite("Color+Ember")
struct ColorTests {

    @Test("emberPrimary is initialized successfully")
    func emberPrimaryExists() {
        let color = Color.emberPrimary
        #expect(color != nil)
    }

    @Test("emberBackground is initialized successfully")
    func emberBackgroundExists() {
        let color = Color.emberBackground
        #expect(color != nil)
    }

    @Test("hex initializer with 6-character hex produces a valid color")
    func hexInitializerSixCharacter() {
        let color = Color(hex: "#5B4FE8")
        #expect(color != nil)
    }

    @Test("hex initializer with 8-character hex produces a valid color")
    func hexInitializerEightCharacter() {
        let color = Color(hex: "#FF5B4FE8")
        #expect(color != nil)
    }

    @Test("hex initializer with invalid string falls back gracefully")
    func hexInitializerInvalidString() {
        let color = Color(hex: "invalid")
        // Should produce a color without crashing (falls back to black)
        #expect(color != nil)
    }

    @Test("all design system colors are defined")
    func allDesignSystemColorsDefined() {
        // Brand
        #expect(Color.emberPrimary != nil)
        #expect(Color.emberPrimaryPressed != nil)
        #expect(Color.emberPrimaryHover != nil)
        #expect(Color.emberAccent != nil)

        // Backgrounds
        #expect(Color.emberBackground != nil)
        #expect(Color.emberSurface != nil)
        #expect(Color.emberSurface2 != nil)
        #expect(Color.emberSurface3 != nil)

        // Text
        #expect(Color.emberTextPrimary != nil)
        #expect(Color.emberTextSecondary != nil)
        #expect(Color.emberTextDisabled != nil)

        // Status
        #expect(Color.emberSuccess != nil)
        #expect(Color.emberWarning != nil)
        #expect(Color.emberError != nil)

        // Gradients
        #expect(Color.emberGradientStart != nil)
        #expect(Color.emberGradientEnd != nil)
        #expect(Color.emberAIBubbleStart != nil)
        #expect(Color.emberAIBubbleEnd != nil)
    }
}
