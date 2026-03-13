import Testing
import SwiftUI
@testable import Ember

@Suite("EmberCardShadow")
struct ViewEmberShadowTests {

    @Test("emberCardShadow modifier can be applied to any view")
    func cardShadowModifier() {
        let view = RoundedRectangle(cornerRadius: 20)
            .fill(Color.emberSurface2)
            .frame(width: 200, height: 100)
            .emberCardShadow()
        _ = AnyView(view)
    }

    @Test("emberCardShadowLight modifier can be applied to any view")
    func cardShadowLightModifier() {
        let view = RoundedRectangle(cornerRadius: 12)
            .fill(Color.emberSurface2)
            .frame(width: 200, height: 70)
            .emberCardShadowLight()
        _ = AnyView(view)
    }

    @Test("EmberCardShadow with custom values")
    func customShadowValues() {
        let modifier = EmberCardShadow(radius: 16, y: 8, opacity: 0.5)
        let view = Text("Test")
            .modifier(modifier)
        _ = AnyView(view)
    }
}
