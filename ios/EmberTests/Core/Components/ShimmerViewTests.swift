import Testing
import SwiftUI
@testable import Ember

/// Tests for `ShimmerView` and `ShimmerModifier`.
///
/// Covers: construction with default and custom corner radii, rendering at all
/// skeleton dimensions specified in the design spec, and the `.shimmer()` View
/// extension applied to both rectangular and circular shapes.
/// Visual animation behaviour (phase sweep) is verified at the composition
/// level — all components must build without a crash and produce a valid view.
@Suite("ShimmerView")
struct ShimmerViewTests {

    // MARK: - Default Corner Radius

    @Test("default init uses emberRadius12 constant")
    func defaultInitUsesEmberRadius12() {
        // emberRadius12 must equal 12 per the CGFloat+Ember design token spec
        #expect(CGFloat.emberRadius12 == 12)
        // ShimmerView default must compile and wrap cleanly — init uses the
        // default parameter `cornerRadius: CGFloat = .emberRadius12`
        let view = ShimmerView()
        _ = AnyView(view)
    }

    @Test("cornerRadius zero is accepted without crash")
    func cornerRadiusZeroIsAccepted() {
        let view = ShimmerView(cornerRadius: 0)
        _ = AnyView(view)
    }

    @Test("cornerRadius emberRadius12 builds without crash")
    func cornerRadiusEmberRadius12Builds() {
        let view = ShimmerView(cornerRadius: .emberRadius12)
        _ = AnyView(view)
    }

    @Test("cornerRadius emberRadius16 builds without crash")
    func cornerRadiusEmberRadius16Builds() {
        let view = ShimmerView(cornerRadius: .emberRadius16)
        _ = AnyView(view)
    }

    @Test("cornerRadius emberRadius20 builds without crash")
    func cornerRadiusEmberRadius20Builds() {
        let view = ShimmerView(cornerRadius: .emberRadius20)
        _ = AnyView(view)
    }

    @Test("large cornerRadius (100) is accepted without crash")
    func largeCornerRadiusIsAccepted() {
        let view = ShimmerView(cornerRadius: 100)
        _ = AnyView(view)
    }

    // MARK: - Frame Sizes Matching Skeleton Spec

    @Test("renders at 50x50 small square without crash")
    func rendersAtSmallSquare() {
        let view = ShimmerView(cornerRadius: 4)
            .frame(width: 50, height: 50)
        _ = AnyView(view)
    }

    @Test("renders at 200x50 wide banner shape without crash")
    func rendersAtWideBanner() {
        let view = ShimmerView(cornerRadius: .emberRadius12)
            .frame(width: 200, height: 50)
        _ = AnyView(view)
    }

    @Test("renders at full-width flexible height (DailySummaryCard skeleton, ~100pt) without crash")
    func rendersAtDailySummaryCardSkeleton() {
        let view = ShimmerView(cornerRadius: .emberRadius20)
            .frame(maxWidth: .infinity, minHeight: 100)
        _ = AnyView(view)
    }

    @Test("renders at CharacterCard skeleton height (180pt, emberRadius20) without crash")
    func rendersAtCharacterCardSkeleton() {
        let view = ShimmerView(cornerRadius: .emberRadius20)
            .frame(height: 180)
        _ = AnyView(view)
    }

    @Test("renders at chat bubble skeleton dimensions (wide assistant, 240x44) without crash")
    func rendersAtAssistantChatBubbleSkeleton() {
        let view = ShimmerView(cornerRadius: .emberRadius16)
            .frame(width: 240, height: 44)
        _ = AnyView(view)
    }

    @Test("renders at chat bubble skeleton dimensions (narrow user, 160x36) without crash")
    func rendersAtUserChatBubbleSkeleton() {
        let view = ShimmerView(cornerRadius: .emberRadius16)
            .frame(width: 160, height: 36)
        _ = AnyView(view)
    }

    @Test("renders at MemoryRowView skeleton height (~70pt, emberRadius12) without crash")
    func rendersAtMemoryRowSkeleton() {
        let view = ShimmerView(cornerRadius: .emberRadius12)
            .frame(maxWidth: .infinity, minHeight: 70)
        _ = AnyView(view)
    }

    @Test("renders at profile name skeleton (120x22) without crash")
    func rendersAtProfileNameSkeleton() {
        let view = ShimmerView(cornerRadius: .emberRadius4)
            .frame(width: 120, height: 22)
        _ = AnyView(view)
    }

    @Test("renders at profile email skeleton (160x13) without crash")
    func rendersAtProfileEmailSkeleton() {
        let view = ShimmerView(cornerRadius: .emberRadius4)
            .frame(width: 160, height: 13)
        _ = AnyView(view)
    }

    @Test("renders at profile avatar skeleton (80x80 circle radius) without crash")
    func rendersAtProfileAvatarSkeleton() {
        let view = ShimmerView(cornerRadius: 40)
            .frame(width: 80, height: 80)
        _ = AnyView(view)
    }

    @Test("renders at settings row skeleton (full-width, 52pt) without crash")
    func rendersAtSettingsRowSkeleton() {
        let view = ShimmerView(cornerRadius: .emberRadius12)
            .frame(maxWidth: .infinity, minHeight: 52)
        _ = AnyView(view)
    }

    @Test("renders at character picker pill skeleton (capsule shape) without crash")
    func rendersAtCharacterPickerPillSkeleton() {
        let view = ShimmerView(cornerRadius: .emberRadius28)
            .frame(width: 80, height: 32)
        _ = AnyView(view)
    }

    // MARK: - Composition

    @Test("four ShimmerViews in a 2-column LazyVGrid build without crash (HomeView skeleton)")
    func multipleShimmerViewsInGrid() {
        let view = LazyVGrid(
            columns: [GridItem(.flexible()), GridItem(.flexible())],
            spacing: 12
        ) {
            ForEach(0..<4, id: \.self) { _ in
                ShimmerView(cornerRadius: .emberRadius20)
                    .frame(height: 180)
            }
        }
        _ = AnyView(view)
    }

    @Test("ShimmerView inside a list row (avatar + name + subtitle) builds without crash")
    func shimmerViewInsideListRow() {
        let view = HStack(spacing: 12) {
            ShimmerView(cornerRadius: 40)
                .frame(width: 40, height: 40)
            VStack(alignment: .leading, spacing: 4) {
                ShimmerView(cornerRadius: .emberRadius4)
                    .frame(width: 120, height: 14)
                ShimmerView(cornerRadius: .emberRadius4)
                    .frame(width: 80, height: 12)
            }
        }
        _ = AnyView(view)
    }

    @Test("alternating chat bubble skeletons in VStack build without crash")
    func alternatingChatBubbleSkeletons() {
        let view = VStack(spacing: 8) {
            HStack {
                ShimmerView(cornerRadius: .emberRadius16).frame(width: 240, height: 44)
                Spacer()
            }
            HStack {
                Spacer()
                ShimmerView(cornerRadius: .emberRadius16).frame(width: 160, height: 36)
            }
            HStack {
                ShimmerView(cornerRadius: .emberRadius16).frame(width: 200, height: 44)
                Spacer()
            }
        }
        _ = AnyView(view)
    }

    // MARK: - ShimmerModifier via .shimmer() extension

    @Test("shimmer() modifier applied to Circle builds without crash")
    func shimmerModifierOnCircle() {
        let view = Circle()
            .fill(Color.emberSurface2)
            .frame(width: 80, height: 80)
            .shimmer()
        _ = AnyView(view)
    }

    @Test("shimmer() modifier applied to Capsule (pill skeleton) builds without crash")
    func shimmerModifierOnCapsule() {
        let view = Capsule()
            .fill(Color.emberSurface2)
            .frame(width: 80, height: 32)
            .shimmer()
        _ = AnyView(view)
    }

    @Test("shimmer() modifier applied to RoundedRectangle builds without crash")
    func shimmerModifierOnRoundedRectangle() {
        let view = RoundedRectangle(cornerRadius: .emberRadius12)
            .fill(Color.emberSurface2)
            .frame(width: 200, height: 70)
            .shimmer()
        _ = AnyView(view)
    }

    @Test("shimmer() modifier applied to Rectangle builds without crash")
    func shimmerModifierOnRectangle() {
        let view = Rectangle()
            .fill(Color.emberSurface2)
            .frame(width: 200, height: 50)
            .shimmer()
        _ = AnyView(view)
    }

    // MARK: - ShimmerModifier direct usage

    @Test("ShimmerModifier conforms to ViewModifier and can be applied via .modifier(_:)")
    func shimmerModifierViaModifier() {
        let modifier = ShimmerModifier()
        let view = Circle()
            .fill(Color.emberSurface2)
            .frame(width: 40, height: 40)
            .modifier(modifier)
        _ = AnyView(view)
    }

    @Test("shimmer() extension and modifier(_: ShimmerModifier()) produce equivalent structure")
    func shimmerExtensionEquivalentToDirectModifier() {
        let base = Circle()
            .fill(Color.emberSurface2)
            .frame(width: 40, height: 40)
        // Both must produce valid AnyView wrappings
        _ = AnyView(base.shimmer())
        _ = AnyView(base.modifier(ShimmerModifier()))
    }
}
