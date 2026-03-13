import Testing
import Foundation
@testable import Ember

/// Tests for CGFloat+Ember.swift design system spacing and corner radius constants.
/// Verifies all 8 spacing values and 5 corner radius values match docs/14-tasarim.md.
@Suite("CGFloat+Ember")
struct CGFloatEmberTests {

    // MARK: - Spacing Constants Exist and Have Correct Values

    @Test("emberSpacing4 equals 4")
    func emberSpacing4Value() {
        #expect(CGFloat.emberSpacing4 == 4)
    }

    @Test("emberSpacing8 equals 8")
    func emberSpacing8Value() {
        #expect(CGFloat.emberSpacing8 == 8)
    }

    @Test("emberSpacing12 equals 12")
    func emberSpacing12Value() {
        #expect(CGFloat.emberSpacing12 == 12)
    }

    @Test("emberSpacing16 equals 16")
    func emberSpacing16Value() {
        #expect(CGFloat.emberSpacing16 == 16)
    }

    @Test("emberSpacing20 equals 20")
    func emberSpacing20Value() {
        #expect(CGFloat.emberSpacing20 == 20)
    }

    @Test("emberSpacing24 equals 24")
    func emberSpacing24Value() {
        #expect(CGFloat.emberSpacing24 == 24)
    }

    @Test("emberSpacing32 equals 32")
    func emberSpacing32Value() {
        #expect(CGFloat.emberSpacing32 == 32)
    }

    @Test("emberSpacing48 equals 48")
    func emberSpacing48Value() {
        #expect(CGFloat.emberSpacing48 == 48)
    }

    // MARK: - Corner Radius Constants Exist and Have Correct Values

    @Test("emberRadius4 equals 4")
    func emberRadius4Value() {
        #expect(CGFloat.emberRadius4 == 4)
    }

    @Test("emberRadius12 equals 12")
    func emberRadius12Value() {
        #expect(CGFloat.emberRadius12 == 12)
    }

    @Test("emberRadius16 equals 16")
    func emberRadius16Value() {
        #expect(CGFloat.emberRadius16 == 16)
    }

    @Test("emberRadius20 equals 20")
    func emberRadius20Value() {
        #expect(CGFloat.emberRadius20 == 20)
    }

    @Test("emberRadius28 equals 28")
    func emberRadius28Value() {
        #expect(CGFloat.emberRadius28 == 28)
    }

    // MARK: - Spacing Hierarchy

    @Test("spacing constants are in strictly ascending order")
    func spacingAscendingOrder() {
        let spacings: [CGFloat] = [
            .emberSpacing4,
            .emberSpacing8,
            .emberSpacing12,
            .emberSpacing16,
            .emberSpacing20,
            .emberSpacing24,
            .emberSpacing32,
            .emberSpacing48,
        ]
        for i in 0..<(spacings.count - 1) {
            #expect(spacings[i] < spacings[i + 1],
                    "Expected spacings[\(i)]=\(spacings[i]) < spacings[\(i+1)]=\(spacings[i+1])")
        }
    }

    @Test("corner radius constants are in strictly ascending order")
    func cornerRadiusAscendingOrder() {
        let radii: [CGFloat] = [
            .emberRadius4,
            .emberRadius12,
            .emberRadius16,
            .emberRadius20,
            .emberRadius28,
        ]
        for i in 0..<(radii.count - 1) {
            #expect(radii[i] < radii[i + 1],
                    "Expected radii[\(i)]=\(radii[i]) < radii[\(i+1)]=\(radii[i+1])")
        }
    }

    // MARK: - All Constants Are Positive

    @Test("all spacing constants are positive")
    func allSpacingPositive() {
        let spacings: [CGFloat] = [
            .emberSpacing4, .emberSpacing8, .emberSpacing12, .emberSpacing16,
            .emberSpacing20, .emberSpacing24, .emberSpacing32, .emberSpacing48,
        ]
        for spacing in spacings {
            #expect(spacing > 0, "Expected positive spacing, got \(spacing)")
        }
    }

    @Test("all corner radius constants are positive")
    func allCornerRadiiPositive() {
        let radii: [CGFloat] = [
            .emberRadius4, .emberRadius12, .emberRadius16, .emberRadius20, .emberRadius28,
        ]
        for radius in radii {
            #expect(radius > 0, "Expected positive radius, got \(radius)")
        }
    }

    // MARK: - Count Verification

    @Test("exactly 8 spacing constants are defined per spec")
    func spacingConstantCount() {
        let spacings: [CGFloat] = [
            .emberSpacing4, .emberSpacing8, .emberSpacing12, .emberSpacing16,
            .emberSpacing20, .emberSpacing24, .emberSpacing32, .emberSpacing48,
        ]
        #expect(spacings.count == 8)
    }

    @Test("exactly 5 corner radius constants are defined per spec")
    func cornerRadiusConstantCount() {
        let radii: [CGFloat] = [
            .emberRadius4, .emberRadius12, .emberRadius16, .emberRadius20, .emberRadius28,
        ]
        #expect(radii.count == 5)
    }

    // MARK: - Named Constant Semantics

    /// These verify the constants are in the correct slots by name.
    /// A refactor that swaps two values would be caught here.
    @Test("emberRadius28 is the largest corner radius (pill button)")
    func radius28IsLargest() {
        let all: [CGFloat] = [
            .emberRadius4, .emberRadius12, .emberRadius16, .emberRadius20, .emberRadius28,
        ]
        #expect(CGFloat.emberRadius28 == all.max())
    }

    @Test("emberSpacing48 is the largest spacing (screen top padding)")
    func spacing48IsLargest() {
        let all: [CGFloat] = [
            .emberSpacing4, .emberSpacing8, .emberSpacing12, .emberSpacing16,
            .emberSpacing20, .emberSpacing24, .emberSpacing32, .emberSpacing48,
        ]
        #expect(CGFloat.emberSpacing48 == all.max())
    }

    @Test("emberSpacing4 is the smallest spacing (icon-text gap)")
    func spacing4IsSmallest() {
        let all: [CGFloat] = [
            .emberSpacing4, .emberSpacing8, .emberSpacing12, .emberSpacing16,
            .emberSpacing20, .emberSpacing24, .emberSpacing32, .emberSpacing48,
        ]
        #expect(CGFloat.emberSpacing4 == all.min())
    }
}
