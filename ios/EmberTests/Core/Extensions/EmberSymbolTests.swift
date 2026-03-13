import Testing
import Foundation
@testable import Ember

/// Tests for EmberSymbol.swift SF Symbol name constants.
/// Verifies every constant is non-empty and matches the spec (docs/14-tasarim.md / docs/standards/ios.md).
@Suite("EmberSymbol")
struct EmberSymbolTests {

    // MARK: - Non-Empty String Checks

    @Test("send symbol name is non-empty")
    func sendNonEmpty() {
        #expect(!EmberSymbol.send.isEmpty)
    }

    @Test("microphone symbol name is non-empty")
    func microphoneNonEmpty() {
        #expect(!EmberSymbol.microphone.isEmpty)
    }

    @Test("memory symbol name is non-empty")
    func memoryNonEmpty() {
        #expect(!EmberSymbol.memory.isEmpty)
    }

    @Test("character symbol name is non-empty")
    func characterNonEmpty() {
        #expect(!EmberSymbol.character.isEmpty)
    }

    @Test("settings symbol name is non-empty")
    func settingsNonEmpty() {
        #expect(!EmberSymbol.settings.isEmpty)
    }

    @Test("back symbol name is non-empty")
    func backNonEmpty() {
        #expect(!EmberSymbol.back.isEmpty)
    }

    @Test("home symbol name is non-empty")
    func homeNonEmpty() {
        #expect(!EmberSymbol.home.isEmpty)
    }

    @Test("homeFill symbol name is non-empty")
    func homeFillNonEmpty() {
        #expect(!EmberSymbol.homeFill.isEmpty)
    }

    @Test("memoryTab symbol name is non-empty")
    func memoryTabNonEmpty() {
        #expect(!EmberSymbol.memoryTab.isEmpty)
    }

    @Test("memoryTabFill symbol name is non-empty")
    func memoryTabFillNonEmpty() {
        #expect(!EmberSymbol.memoryTabFill.isEmpty)
    }

    @Test("profile symbol name is non-empty")
    func profileNonEmpty() {
        #expect(!EmberSymbol.profile.isEmpty)
    }

    @Test("profileFill symbol name is non-empty")
    func profileFillNonEmpty() {
        #expect(!EmberSymbol.profileFill.isEmpty)
    }

    // MARK: - Spec-Mandated Symbol Names

    @Test("send symbol matches spec value")
    func sendSymbolMatchesSpec() {
        #expect(EmberSymbol.send == "arrow.up.circle.fill")
    }

    @Test("microphone symbol matches spec value")
    func microphoneSymbolMatchesSpec() {
        #expect(EmberSymbol.microphone == "mic.fill")
    }

    @Test("memory symbol matches spec value")
    func memorySymbolMatchesSpec() {
        #expect(EmberSymbol.memory == "brain.head.profile")
    }

    @Test("character symbol matches spec value")
    func characterSymbolMatchesSpec() {
        #expect(EmberSymbol.character == "person.crop.circle")
    }

    @Test("settings symbol matches spec value")
    func settingsSymbolMatchesSpec() {
        #expect(EmberSymbol.settings == "gearshape.fill")
    }

    @Test("back symbol matches spec value")
    func backSymbolMatchesSpec() {
        #expect(EmberSymbol.back == "chevron.left")
    }

    @Test("home symbol matches spec value")
    func homeSymbolMatchesSpec() {
        #expect(EmberSymbol.home == "bubble.left.and.bubble.right")
    }

    @Test("homeFill symbol matches spec value")
    func homeFillSymbolMatchesSpec() {
        #expect(EmberSymbol.homeFill == "bubble.left.and.bubble.right.fill")
    }

    @Test("memoryTab symbol matches spec value")
    func memoryTabSymbolMatchesSpec() {
        #expect(EmberSymbol.memoryTab == "brain")
    }

    @Test("memoryTabFill symbol matches spec value")
    func memoryTabFillSymbolMatchesSpec() {
        #expect(EmberSymbol.memoryTabFill == "brain.fill")
    }

    @Test("profile symbol matches spec value")
    func profileSymbolMatchesSpec() {
        #expect(EmberSymbol.profile == "person.circle")
    }

    @Test("profileFill symbol matches spec value")
    func profileFillSymbolMatchesSpec() {
        #expect(EmberSymbol.profileFill == "person.circle.fill")
    }

    // MARK: - Fill Variants Are Distinct From Outline Variants

    @Test("home and homeFill are different strings")
    func homeAndHomeFillAreDistinct() {
        #expect(EmberSymbol.home != EmberSymbol.homeFill)
    }

    @Test("memoryTab and memoryTabFill are different strings")
    func memoryTabAndMemoryTabFillAreDistinct() {
        #expect(EmberSymbol.memoryTab != EmberSymbol.memoryTabFill)
    }

    @Test("profile and profileFill are different strings")
    func profileAndProfileFillAreDistinct() {
        #expect(EmberSymbol.profile != EmberSymbol.profileFill)
    }

    // MARK: - Count Verification

    @Test("exactly 12 symbol constants are defined per spec")
    func symbolConstantCount() {
        let symbols = [
            EmberSymbol.send,
            EmberSymbol.microphone,
            EmberSymbol.memory,
            EmberSymbol.character,
            EmberSymbol.settings,
            EmberSymbol.back,
            EmberSymbol.home,
            EmberSymbol.homeFill,
            EmberSymbol.memoryTab,
            EmberSymbol.memoryTabFill,
            EmberSymbol.profile,
            EmberSymbol.profileFill,
        ]
        #expect(symbols.count == 12)
    }

    // MARK: - All Symbols Are Unique

    @Test("all symbol name constants are unique strings")
    func allSymbolNamesAreUnique() {
        let symbols = [
            EmberSymbol.send,
            EmberSymbol.microphone,
            EmberSymbol.memory,
            EmberSymbol.character,
            EmberSymbol.settings,
            EmberSymbol.back,
            EmberSymbol.home,
            EmberSymbol.homeFill,
            EmberSymbol.memoryTab,
            EmberSymbol.memoryTabFill,
            EmberSymbol.profile,
            EmberSymbol.profileFill,
        ]
        let unique = Set(symbols)
        #expect(unique.count == symbols.count)
    }
}
