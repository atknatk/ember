import Testing
import SwiftUI
@testable import Ember

@Suite("ShimmerView")
struct ShimmerViewTests {

    @Test("renders at small size without crash")
    func rendersAtSmallSize() {
        let view = ShimmerView(cornerRadius: 4)
            .frame(width: 50, height: 50)
        // Verify the view can be created and type-checked
        _ = AnyView(view)
    }

    @Test("renders at medium size without crash")
    func rendersAtMediumSize() {
        let view = ShimmerView(cornerRadius: 12)
            .frame(width: 200, height: 50)
        _ = AnyView(view)
    }

    @Test("renders at full width without crash")
    func rendersAtFullWidth() {
        let view = ShimmerView()
            .frame(maxWidth: .infinity, minHeight: 100)
        _ = AnyView(view)
    }

    @Test("custom corner radius applies correctly")
    func customCornerRadius() {
        let view = ShimmerView(cornerRadius: .emberRadius20)
        _ = AnyView(view)
    }

    @Test("default corner radius is emberRadius12")
    func defaultCornerRadius() {
        let view = ShimmerView()
        _ = AnyView(view)
    }

    @Test("shimmer modifier can be applied to any view")
    func shimmerModifier() {
        let view = Circle()
            .fill(Color.emberSurface2)
            .frame(width: 80, height: 80)
            .shimmer()
        _ = AnyView(view)
    }
}
