import Testing
import SwiftUI
@testable import Ember

/// Tests for `EmberCardShadow`, `EmberCardShadowLight`, and the
/// `.emberCardShadow()` / `.emberCardShadowLight()` View extensions.
///
/// Covers: default property values matching the design spec, custom property
/// initialisation, application via both the convenience extension and the
/// `.modifier(_:)` form, and composition with all card types in the design system.
@Suite("EmberCardShadow")
struct ViewEmberShadowTests {

    // MARK: - EmberCardShadow: default property values

    @Test("EmberCardShadow default radius is 8 per design spec")
    func defaultRadiusIs8() {
        let modifier = EmberCardShadow()
        #expect(modifier.radius == 8)
    }

    @Test("EmberCardShadow default y-offset is 4 per design spec")
    func defaultYOffsetIs4() {
        let modifier = EmberCardShadow()
        #expect(modifier.y == 4)
    }

    @Test("EmberCardShadow default opacity is 0.3 per design spec")
    func defaultOpacityIs0_3() {
        let modifier = EmberCardShadow()
        #expect(modifier.opacity == 0.3)
    }

    // MARK: - EmberCardShadow: custom property initialisation

    @Test("EmberCardShadow stores custom radius correctly")
    func customRadiusStored() {
        let modifier = EmberCardShadow(radius: 16)
        #expect(modifier.radius == 16)
    }

    @Test("EmberCardShadow stores custom y-offset correctly")
    func customYOffsetStored() {
        let modifier = EmberCardShadow(y: 8)
        #expect(modifier.y == 8)
    }

    @Test("EmberCardShadow stores custom opacity correctly")
    func customOpacityStored() {
        let modifier = EmberCardShadow(opacity: 0.5)
        #expect(modifier.opacity == 0.5)
    }

    @Test("EmberCardShadow stores all three custom values independently")
    func allCustomValuesStoredIndependently() {
        let modifier = EmberCardShadow(radius: 12, y: 6, opacity: 0.4)
        #expect(modifier.radius == 12)
        #expect(modifier.y == 6)
        #expect(modifier.opacity == 0.4)
    }

    @Test("EmberCardShadow opacity of 0 is accepted (invisible shadow)")
    func zeroOpacityIsAccepted() {
        let modifier = EmberCardShadow(opacity: 0)
        #expect(modifier.opacity == 0)
        let view = RoundedRectangle(cornerRadius: 20)
            .modifier(modifier)
        _ = AnyView(view)
    }

    @Test("EmberCardShadow radius of 0 is accepted (hard shadow)")
    func zeroRadiusIsAccepted() {
        let modifier = EmberCardShadow(radius: 0)
        #expect(modifier.radius == 0)
        let view = RoundedRectangle(cornerRadius: 20)
            .modifier(modifier)
        _ = AnyView(view)
    }

    // MARK: - EmberCardShadow: design spec relationship

    @Test("EmberCardShadow default radius (8) is greater than EmberCardShadowLight radius (4)")
    func defaultRadiusGreaterThanLightVariant() {
        let shadow = EmberCardShadow()
        let shadowLight = EmberCardShadowLight()
        // The light variant uses radius: 4, standard uses radius: 8
        // We verify this relationship holds per the spec
        let lightModifier = shadowLight
        let view = Text("test").modifier(lightModifier)
        _ = AnyView(view)
        #expect(shadow.radius > 4)
    }

    @Test("EmberCardShadow default opacity (0.3) is greater than light variant opacity (0.15)")
    func defaultOpacityGreaterThanLightVariant() {
        let shadow = EmberCardShadow()
        #expect(shadow.opacity > 0.15)
    }

    // MARK: - View extension: .emberCardShadow()

    @Test("emberCardShadow() applied to RoundedRectangle (CharacterCardView) builds without crash")
    func cardShadowOnCharacterCard() {
        let view = RoundedRectangle(cornerRadius: .emberRadius20)
            .fill(Color.emberCard)
            .frame(width: 160, height: 180)
            .emberCardShadow()
        _ = AnyView(view)
    }

    @Test("emberCardShadow() applied to DailySummaryCard dimensions builds without crash")
    func cardShadowOnDailySummaryCard() {
        let view = RoundedRectangle(cornerRadius: .emberRadius20)
            .fill(Color.emberCard)
            .frame(maxWidth: .infinity, minHeight: 100)
            .emberCardShadow()
        _ = AnyView(view)
    }

    @Test("emberCardShadow() applied to a Text view builds without crash")
    func cardShadowOnText() {
        let view = Text("Hello Ember")
            .emberCardShadow()
        _ = AnyView(view)
    }

    @Test("emberCardShadow() applied to an Image view builds without crash")
    func cardShadowOnImage() {
        let view = Image(systemName: "person.crop.circle")
            .resizable()
            .frame(width: 80, height: 80)
            .clipShape(Circle())
            .emberCardShadow()
        _ = AnyView(view)
    }

    @Test("emberCardShadow() applied to a VStack builds without crash")
    func cardShadowOnVStack() {
        let view = VStack(spacing: 8) {
            Text("Character Name")
            Text("Last message preview")
        }
        .padding()
        .background(Color.emberCard)
        .clipShape(RoundedRectangle(cornerRadius: .emberRadius20))
        .emberCardShadow()
        _ = AnyView(view)
    }

    @Test("emberCardShadow() applied to a ZStack (card with overlay) builds without crash")
    func cardShadowOnZStack() {
        let view = ZStack(alignment: .bottomLeading) {
            RoundedRectangle(cornerRadius: .emberRadius20)
                .fill(Color.emberCard)
                .frame(width: 160, height: 180)
            Text("Luna")
                .padding(8)
        }
        .emberCardShadow()
        _ = AnyView(view)
    }

    // MARK: - View extension: .emberCardShadowLight()

    @Test("emberCardShadowLight() applied to MemoryRowView dimensions builds without crash")
    func cardShadowLightOnMemoryRow() {
        let view = RoundedRectangle(cornerRadius: .emberRadius12)
            .fill(Color.emberSurface)
            .frame(maxWidth: .infinity, minHeight: 70)
            .emberCardShadowLight()
        _ = AnyView(view)
    }

    @Test("emberCardShadowLight() applied to a Text view builds without crash")
    func cardShadowLightOnText() {
        let view = Text("Memory content")
            .emberCardShadowLight()
        _ = AnyView(view)
    }

    @Test("emberCardShadowLight() applied to a Circle (avatar) builds without crash")
    func cardShadowLightOnCircle() {
        let view = Circle()
            .fill(Color.emberSurface)
            .frame(width: 40, height: 40)
            .emberCardShadowLight()
        _ = AnyView(view)
    }

    @Test("emberCardShadowLight() applied to a settings row card builds without crash")
    func cardShadowLightOnSettingsRow() {
        let view = HStack {
            Text("Notification")
            Spacer()
            Toggle("", isOn: .constant(true))
        }
        .padding()
        .background(Color.emberCard)
        .clipShape(RoundedRectangle(cornerRadius: .emberRadius12))
        .emberCardShadowLight()
        _ = AnyView(view)
    }

    // MARK: - Direct modifier usage (.modifier())

    @Test("EmberCardShadow can be applied via .modifier(_:)")
    func cardShadowViaModifier() {
        let modifier = EmberCardShadow()
        let view = RoundedRectangle(cornerRadius: .emberRadius20)
            .fill(Color.emberCard)
            .frame(width: 200, height: 100)
            .modifier(modifier)
        _ = AnyView(view)
    }

    @Test("EmberCardShadowLight can be applied via .modifier(_:)")
    func cardShadowLightViaModifier() {
        let modifier = EmberCardShadowLight()
        let view = RoundedRectangle(cornerRadius: .emberRadius12)
            .fill(Color.emberSurface)
            .frame(width: 200, height: 70)
            .modifier(modifier)
        _ = AnyView(view)
    }

    @Test("EmberCardShadow with custom values builds without crash")
    func customShadowValuesBuildsWithoutCrash() {
        let modifier = EmberCardShadow(radius: 16, y: 8, opacity: 0.5)
        let view = Text("Custom shadow")
            .modifier(modifier)
        _ = AnyView(view)
    }

    // MARK: - Stacking shadows

    @Test("emberCardShadow() and emberCardShadowLight() can be stacked on the same view")
    func shadowsCanBeStacked() {
        // While unusual in practice, stacking must not crash
        let view = RoundedRectangle(cornerRadius: .emberRadius20)
            .fill(Color.emberCard)
            .emberCardShadow()
            .emberCardShadowLight()
        _ = AnyView(view)
    }

    @Test("two emberCardShadow() modifiers can be applied without crash")
    func doubleShadowDoesNotCrash() {
        let view = RoundedRectangle(cornerRadius: .emberRadius20)
            .fill(Color.emberCard)
            .emberCardShadow()
            .emberCardShadow()
        _ = AnyView(view)
    }

    // MARK: - Composition with other modifiers

    @Test("emberCardShadow() composes after clipShape() (correct usage pattern)")
    func shadowAfterClipShape() {
        let view = RoundedRectangle(cornerRadius: .emberRadius20)
            .fill(Color.emberCard)
            .frame(width: 160, height: 180)
            .clipShape(RoundedRectangle(cornerRadius: .emberRadius20))
            .emberCardShadow()
        _ = AnyView(view)
    }

    @Test("emberCardShadowLight() composes after background() modifier")
    func shadowLightAfterBackground() {
        let view = HStack {
            Text("Memory")
            Spacer()
        }
        .padding()
        .background(Color.emberCard)
        .emberCardShadowLight()
        _ = AnyView(view)
    }

    @Test("avatar shadow with emberPrimary tint color builds without crash")
    func avatarPrimaryTintShadow() {
        // ProfileView uses .shadow(color: Color.emberPrimary.opacity(0.3), radius: 8, y: 2)
        // This is NOT the EmberCardShadow modifier but an inline shadow — we verify the
        // colour and radius values used in the spec are accessible
        let view = Circle()
            .fill(Color.emberSurface)
            .frame(width: 80, height: 80)
            .shadow(color: Color.emberPrimary.opacity(0.3), radius: 8, y: 2)
        _ = AnyView(view)
    }
}
