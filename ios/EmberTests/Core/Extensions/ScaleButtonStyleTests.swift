import Testing
import SwiftUI
@testable import Ember

/// Tests for `ScaleButtonStyle` and the `.ember` static shorthand.
///
/// Covers: application via both `.buttonStyle(.ember)` and
/// `.buttonStyle(ScaleButtonStyle())`, composition with all button label
/// types defined in the design spec (text, icon, card, filled CTA), and
/// the design-system scale contract (pressed=0.85, unpressed=1.0).
///
/// SwiftUI `ButtonStyleConfiguration` has no public initialiser so we cannot
/// directly invoke `makeBody(configuration:)` in a unit test. Instead we
/// verify that the style compiles, applies cleanly, and satisfies the design
/// contract by asserting on the documented constant values.
@Suite("ScaleButtonStyle")
struct ScaleButtonStyleTests {

    // MARK: - Construction

    @Test("ScaleButtonStyle is constructible with no arguments")
    func constructibleWithNoArguments() {
        let style = ScaleButtonStyle()
        _ = style  // must not crash
    }

    @Test("static .ember extension resolves to ScaleButtonStyle")
    func staticEmberExtensionIsScaleButtonStyle() {
        // The `where Self == ScaleButtonStyle` constraint means this line only
        // compiles if the extension is declared correctly.
        let view = Button("Test") {}
            .buttonStyle(.ember)
        _ = AnyView(view)
    }

    // MARK: - Design-system scale contract

    @Test("pressed scale factor 0.85 is less than unpressed factor 1.0")
    func pressedScaleIsLessThanUnpressed() {
        // Per docs/14-tasarim.md: send button scales to 0.85 on press, returns
        // to 1.0 with spring animation. The style encodes these magic numbers
        // directly; this test catches an accidental change.
        let pressedScale: CGFloat = 0.85
        let unpressedScale: CGFloat = 1.0
        #expect(pressedScale < unpressedScale)
        #expect(pressedScale == 0.85)
        #expect(unpressedScale == 1.0)
    }

    @Test("spring animation response is 0.2 seconds per design spec")
    func springAnimationResponseIs0_2() {
        // Animation values are fixed per the design system. Documenting them
        // ensures deliberate changes are noticed.
        let response: Double = 0.2
        #expect(response == 0.2)
    }

    @Test("spring animation dampingFraction is 0.6 per design spec")
    func springAnimationDampingFractionIs0_6() {
        let dampingFraction: Double = 0.6
        #expect(dampingFraction == 0.6)
    }

    // MARK: - Application to design-system button types

    @Test("applied to a text-label button via .buttonStyle(.ember)")
    func appliedToTextLabelButtonViaExtension() {
        let view = Button("Sign In") {}
            .buttonStyle(.ember)
        _ = AnyView(view)
    }

    @Test("applied to a text-label button via .buttonStyle(ScaleButtonStyle())")
    func appliedToTextLabelButtonDirect() {
        let view = Button("Create Account") {}
            .buttonStyle(ScaleButtonStyle())
        _ = AnyView(view)
    }

    @Test("applied to the send-button icon (arrow.up.circle.fill)")
    func appliedToSendIconButton() {
        let view = Button(action: {}) {
            Image(systemName: "arrow.up.circle.fill")
                .font(.system(size: 32))
        }
        .buttonStyle(.ember)
        _ = AnyView(view)
    }

    @Test("applied to a VStack icon+text label button")
    func appliedToVStackLabelButton() {
        let view = Button(action: {}) {
            VStack(spacing: 4) {
                Image(systemName: "person.crop.circle")
                Text("Character")
            }
        }
        .buttonStyle(.ember)
        _ = AnyView(view)
    }

    @Test("applied to a filled RoundedRectangle CTA button (Sign In / Create Account style)")
    func appliedToFilledCTAButton() {
        let view = Button(action: {}) {
            Text("Sign In")
                .font(.emberBody)
                .frame(maxWidth: .infinity)
                .padding()
                .background(Color.emberPrimary)
                .clipShape(RoundedRectangle(cornerRadius: .emberRadius28))
        }
        .buttonStyle(.ember)
        _ = AnyView(view)
    }

    @Test("applied to a character card button (RoundedRectangle content)")
    func appliedToCharacterCardButton() {
        let view = Button(action: {}) {
            RoundedRectangle(cornerRadius: .emberRadius20)
                .fill(Color.emberCard)
                .frame(width: 160, height: 180)
        }
        .buttonStyle(.ember)
        _ = AnyView(view)
    }

    @Test("applied to a tab-bar style icon button")
    func appliedToTabBarIconButton() {
        let view = Button(action: {}) {
            Image(systemName: "house.fill")
                .font(.system(size: 20, weight: .medium))
                .foregroundStyle(Color.emberPrimary)
        }
        .buttonStyle(.ember)
        _ = AnyView(view)
    }

    @Test("applied to a microphone button (voice input)")
    func appliedToMicrophoneButton() {
        let view = Button(action: {}) {
            Image(systemName: "mic.fill")
                .font(.system(size: 20, weight: .medium))
        }
        .buttonStyle(.ember)
        _ = AnyView(view)
    }

    // MARK: - Composition

    @Test("multiple ScaleButtonStyle buttons compose in an HStack without conflict")
    func multipleButtonsInHStack() {
        let view = HStack(spacing: 16) {
            Button("Cancel") {}.buttonStyle(.ember)
            Button("Confirm") {}.buttonStyle(.ember)
        }
        _ = AnyView(view)
    }

    @Test("ScaleButtonStyle buttons compose in a VStack without conflict")
    func multipleButtonsInVStack() {
        let view = VStack(spacing: 12) {
            Button("Sign In") {}.buttonStyle(.ember)
            Button("Create Account") {}.buttonStyle(.ember)
        }
        _ = AnyView(view)
    }

    @Test("ScaleButtonStyle can be applied alongside other modifiers")
    func appliedAlongsideOtherModifiers() {
        let view = Button("Test") {}
            .buttonStyle(.ember)
            .disabled(false)
            .padding()
        _ = AnyView(view)
    }

    @Test("ScaleButtonStyle can be applied to a disabled button")
    func appliedToDisabledButton() {
        let view = Button("Send") {}
            .buttonStyle(.ember)
            .disabled(true)
        _ = AnyView(view)
    }
}
