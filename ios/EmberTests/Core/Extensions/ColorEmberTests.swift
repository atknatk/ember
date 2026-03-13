import Testing
import SwiftUI
@testable import Ember

/// Extended color tests that verify hex values match the design system spec (docs/14-tasarim.md).
/// The basic existence tests live in ColorTests.swift (written by ios-dev).
/// These tests verify the actual component values so a stale hex value is caught.
@Suite("Color+Ember extended")
struct ColorEmberTests {

    // MARK: - Hex Initializer — Component Verification

    /// Verify that the hex initializer correctly extracts red/green/blue for a known value.
    /// #5B4FE8 = R:91 G:79 B:232 in decimal (0x5B=91, 0x4F=79, 0xE8=232)
    @Test("hex init: #5B4FE8 resolves to correct sRGB components")
    func hexInitializerComponentsKnownValue() throws {
        // We can only verify the color is not .clear / completely transparent
        // (SwiftUI Color does not expose components in a testable way without UIColor)
        // Use UIColor bridge instead
        let uiColor = UIColor(Color(hex: "#5B4FE8"))
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        uiColor.getRed(&r, green: &g, blue: &b, alpha: &a)

        #expect(abs(r - (91.0 / 255.0)) < 0.01)
        #expect(abs(g - (79.0 / 255.0)) < 0.01)
        #expect(abs(b - (232.0 / 255.0)) < 0.01)
        #expect(abs(a - 1.0) < 0.01)
    }

    @Test("hex init: #0F0F14 resolves to correct sRGB components")
    func hexInitializerBackgroundComponents() throws {
        let uiColor = UIColor(Color(hex: "#0F0F14"))
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        uiColor.getRed(&r, green: &g, blue: &b, alpha: &a)

        #expect(abs(r - (15.0 / 255.0)) < 0.01)
        #expect(abs(g - (15.0 / 255.0)) < 0.01)
        #expect(abs(b - (20.0 / 255.0)) < 0.01)
        #expect(abs(a - 1.0) < 0.01)
    }

    @Test("hex init: 8-character hex applies alpha component")
    func hexInitializerEightCharAlpha() throws {
        // #805B4FE8 — alpha=128 (0x80), R=91, G=79, B=232
        let uiColor = UIColor(Color(hex: "#805B4FE8"))
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        uiColor.getRed(&r, green: &g, blue: &b, alpha: &a)

        #expect(abs(a - (128.0 / 255.0)) < 0.01)
        #expect(abs(r - (91.0 / 255.0)) < 0.01)
    }

    @Test("hex init: invalid hex falls back to black (R=0 G=0 B=0)")
    func hexInitializerInvalidFallsBackToBlack() throws {
        let uiColor = UIColor(Color(hex: "invalid"))
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        uiColor.getRed(&r, green: &g, blue: &b, alpha: &a)

        #expect(r == 0)
        #expect(g == 0)
        #expect(b == 0)
    }

    @Test("hex init: empty string falls back gracefully without crashing")
    func hexInitializerEmptyString() {
        // Must not crash
        _ = Color(hex: "")
    }

    @Test("hex init: hex without leading # is also handled")
    func hexInitializerWithoutHash() throws {
        // "5B4FE8" (no #) — the initializer strips non-alphanumerics so this should parse
        let uiColor = UIColor(Color(hex: "5B4FE8"))
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        uiColor.getRed(&r, green: &g, blue: &b, alpha: &a)

        #expect(abs(r - (91.0 / 255.0)) < 0.01)
        #expect(abs(g - (79.0 / 255.0)) < 0.01)
        #expect(abs(b - (232.0 / 255.0)) < 0.01)
    }

    // MARK: - Spec-Mandated Hex Values

    @Test("emberPrimary has correct hex value #5B4FE8")
    func emberPrimaryHexValue() throws {
        let uiColor = UIColor(Color.emberPrimary)
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        uiColor.getRed(&r, green: &g, blue: &b, alpha: &a)

        #expect(abs(r - (0x5B / 255.0)) < 0.01)  // 91
        #expect(abs(g - (0x4F / 255.0)) < 0.01)  // 79
        #expect(abs(b - (0xE8 / 255.0)) < 0.01)  // 232
    }

    @Test("emberAccent has correct hex value #FF6B6B")
    func emberAccentHexValue() throws {
        let uiColor = UIColor(Color.emberAccent)
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        uiColor.getRed(&r, green: &g, blue: &b, alpha: &a)

        #expect(abs(r - (0xFF / 255.0)) < 0.01)  // 255
        #expect(abs(g - (0x6B / 255.0)) < 0.01)  // 107
        #expect(abs(b - (0x6B / 255.0)) < 0.01)  // 107
    }

    @Test("emberBackground has correct hex value #0F0F14")
    func emberBackgroundHexValue() throws {
        let uiColor = UIColor(Color.emberBackground)
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        uiColor.getRed(&r, green: &g, blue: &b, alpha: &a)

        #expect(abs(r - (0x0F / 255.0)) < 0.01)
        #expect(abs(g - (0x0F / 255.0)) < 0.01)
        #expect(abs(b - (0x14 / 255.0)) < 0.01)
    }

    @Test("emberSurface has correct hex value #1A1A24")
    func emberSurfaceHexValue() throws {
        let uiColor = UIColor(Color.emberSurface)
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        uiColor.getRed(&r, green: &g, blue: &b, alpha: &a)

        #expect(abs(r - (0x1A / 255.0)) < 0.01)
        #expect(abs(g - (0x1A / 255.0)) < 0.01)
        #expect(abs(b - (0x24 / 255.0)) < 0.01)
    }

    @Test("emberTextPrimary has correct hex value #F0F0F8")
    func emberTextPrimaryHexValue() throws {
        let uiColor = UIColor(Color.emberTextPrimary)
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        uiColor.getRed(&r, green: &g, blue: &b, alpha: &a)

        #expect(abs(r - (0xF0 / 255.0)) < 0.01)
        #expect(abs(g - (0xF0 / 255.0)) < 0.01)
        #expect(abs(b - (0xF8 / 255.0)) < 0.01)
    }

    @Test("emberError has correct hex value #E85B5B")
    func emberErrorHexValue() throws {
        let uiColor = UIColor(Color.emberError)
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        uiColor.getRed(&r, green: &g, blue: &b, alpha: &a)

        #expect(abs(r - (0xE8 / 255.0)) < 0.01)  // 232
        #expect(abs(g - (0x5B / 255.0)) < 0.01)  // 91
        #expect(abs(b - (0x5B / 255.0)) < 0.01)  // 91
    }

    @Test("emberSuccess has correct hex value #4CAF87")
    func emberSuccessHexValue() throws {
        let uiColor = UIColor(Color.emberSuccess)
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        uiColor.getRed(&r, green: &g, blue: &b, alpha: &a)

        #expect(abs(r - (0x4C / 255.0)) < 0.01)
        #expect(abs(g - (0xAF / 255.0)) < 0.01)
        #expect(abs(b - (0x87 / 255.0)) < 0.01)
    }

    @Test("emberWarning has correct hex value #F5A623")
    func emberWarningHexValue() throws {
        let uiColor = UIColor(Color.emberWarning)
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        uiColor.getRed(&r, green: &g, blue: &b, alpha: &a)

        #expect(abs(r - (0xF5 / 255.0)) < 0.01)
        #expect(abs(g - (0xA6 / 255.0)) < 0.01)
        #expect(abs(b - (0x23 / 255.0)) < 0.01)
    }

    @Test("emberGradientStart matches emberPrimary (#5B4FE8)")
    func emberGradientStartMatchesPrimary() throws {
        let startUI = UIColor(Color.emberGradientStart)
        let primaryUI = UIColor(Color.emberPrimary)

        var r1: CGFloat = 0, g1: CGFloat = 0, b1: CGFloat = 0, a1: CGFloat = 0
        var r2: CGFloat = 0, g2: CGFloat = 0, b2: CGFloat = 0, a2: CGFloat = 0
        startUI.getRed(&r1, green: &g1, blue: &b1, alpha: &a1)
        primaryUI.getRed(&r2, green: &g2, blue: &b2, alpha: &a2)

        #expect(abs(r1 - r2) < 0.001)
        #expect(abs(g1 - g2) < 0.001)
        #expect(abs(b1 - b2) < 0.001)
    }

    @Test("emberGradientEnd matches emberAccent (#FF6B6B)")
    func emberGradientEndMatchesAccent() throws {
        let endUI = UIColor(Color.emberGradientEnd)
        let accentUI = UIColor(Color.emberAccent)

        var r1: CGFloat = 0, g1: CGFloat = 0, b1: CGFloat = 0, a1: CGFloat = 0
        var r2: CGFloat = 0, g2: CGFloat = 0, b2: CGFloat = 0, a2: CGFloat = 0
        endUI.getRed(&r1, green: &g1, blue: &b1, alpha: &a1)
        accentUI.getRed(&r2, green: &g2, blue: &b2, alpha: &a2)

        #expect(abs(r1 - r2) < 0.001)
        #expect(abs(g1 - g2) < 0.001)
        #expect(abs(b1 - b2) < 0.001)
    }

    // MARK: - All Colors Are Fully Opaque (alpha = 1.0)

    @Test("all design system colors are fully opaque")
    func allColorsAreFullyOpaque() {
        let colors: [Color] = [
            .emberPrimary, .emberPrimaryPressed, .emberPrimaryHover,
            .emberAccent,
            .emberBackground, .emberSurface, .emberSurface2, .emberSurface3,
            .emberTextPrimary, .emberTextSecondary, .emberTextDisabled,
            .emberSuccess, .emberWarning, .emberError,
            .emberGradientStart, .emberGradientEnd,
            .emberAIBubbleStart, .emberAIBubbleEnd
        ]

        for color in colors {
            let uiColor = UIColor(color)
            var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
            uiColor.getRed(&r, green: &g, blue: &b, alpha: &a)
            #expect(abs(a - 1.0) < 0.01, "Expected fully opaque color, got alpha=\(a)")
        }
    }

    // MARK: - Design System Color Count

    @Test("exactly 18 design system color constants are defined")
    func designSystemColorCount() {
        // Enumerate all expected constants to catch if one is accidentally removed
        let expectedColors: [Color] = [
            .emberPrimary,
            .emberPrimaryPressed,
            .emberPrimaryHover,
            .emberAccent,
            .emberBackground,
            .emberSurface,
            .emberSurface2,
            .emberSurface3,
            .emberTextPrimary,
            .emberTextSecondary,
            .emberTextDisabled,
            .emberSuccess,
            .emberWarning,
            .emberError,
            .emberGradientStart,
            .emberGradientEnd,
            .emberAIBubbleStart,
            .emberAIBubbleEnd,
        ]
        #expect(expectedColors.count == 18)
    }
}
