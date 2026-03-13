import Testing
import SwiftUI
@testable import Ember

@Suite("ScaleButtonStyle")
struct ScaleButtonStyleTests {

    @Test("ScaleButtonStyle can be applied to a button")
    func canBeAppliedToButton() {
        let view = Button("Test") {}
            .buttonStyle(.ember)
        _ = AnyView(view)
    }

    @Test("ScaleButtonStyle can be applied to icon button")
    func canBeAppliedToIconButton() {
        let view = Button(action: {}) {
            Image(systemName: "arrow.up.circle.fill")
        }
        .buttonStyle(ScaleButtonStyle())
        _ = AnyView(view)
    }
}
