import Testing
@testable import Ember

/// Extended AppRouter tests that supplement the 5 basic tests in AppRouterTests.swift.
/// Covers: each Route case round-trips, sequential operations, path count invariants,
/// and initial state.
@Suite("AppRouter extended")
struct AppRouterExtendedTests {

    // MARK: - Initial State

    @Test("router starts with empty path")
    func initialStateEmpty() {
        let router = AppRouter()
        #expect(router.path.count == 0)
    }

    // MARK: - Each Route Case Can Be Pushed

    @Test("push .chat increases path count")
    func pushChatRoute() {
        let router = AppRouter()
        router.push(.chat(characterId: "char-emma", characterName: "Emma"))
        #expect(router.path.count == 1)
    }

    @Test("push .characterDetail increases path count")
    func pushCharacterDetailRoute() {
        let router = AppRouter()
        router.push(.characterDetail(characterId: "char-luna"))
        #expect(router.path.count == 1)
    }

    @Test("push .memoryList increases path count")
    func pushMemoryListRoute() {
        let router = AppRouter()
        router.push(.memoryList(characterId: "char-sage"))
        #expect(router.path.count == 1)
    }

    @Test("push .settings increases path count")
    func pushSettingsRoute() {
        let router = AppRouter()
        router.push(.settings)
        #expect(router.path.count == 1)
    }

    // MARK: - Sequential Push Operations

    @Test("pushing multiple routes increments count for each push")
    func pushMultipleIncrements() {
        let router = AppRouter()

        router.push(.chat(characterId: "c1", characterName: "Test"))
        #expect(router.path.count == 1)

        router.push(.settings)
        #expect(router.path.count == 2)

        router.push(.memoryList(characterId: "c1"))
        #expect(router.path.count == 3)

        router.push(.characterDetail(characterId: "c1"))
        #expect(router.path.count == 4)
    }

    // MARK: - Sequential Pop Operations

    @Test("each pop decrements count by exactly 1")
    func eachPopDecrementsOne() {
        let router = AppRouter()
        router.push(.chat(characterId: "c1", characterName: "Test"))
        router.push(.settings)
        router.push(.memoryList(characterId: "c1"))

        router.pop()
        #expect(router.path.count == 2)

        router.pop()
        #expect(router.path.count == 1)

        router.pop()
        #expect(router.path.count == 0)
    }

    @Test("pop after popToRoot does not crash")
    func popAfterPopToRootDoesNotCrash() {
        let router = AppRouter()
        router.push(.chat(characterId: "c1", characterName: "Test"))
        router.push(.settings)

        router.popToRoot()
        #expect(router.path.count == 0)

        // Must not crash — guard in pop() protects this
        router.pop()
        #expect(router.path.count == 0)
    }

    // MARK: - popToRoot After Exactly One Push

    @Test("popToRoot after single push results in count of 0")
    func popToRootAfterOnePush() {
        let router = AppRouter()
        router.push(.settings)

        router.popToRoot()

        #expect(router.path.count == 0)
    }

    // MARK: - Calling popToRoot Multiple Times

    @Test("calling popToRoot twice does not crash")
    func popToRootTwiceDoesNotCrash() {
        let router = AppRouter()
        router.push(.chat(characterId: "c1", characterName: "Test"))

        router.popToRoot()
        router.popToRoot()  // guard ensures this is a no-op

        #expect(router.path.count == 0)
    }

    // MARK: - Interleaved Push and Pop

    @Test("interleaved push and pop maintains correct count")
    func interleavedPushAndPop() {
        let router = AppRouter()

        router.push(.chat(characterId: "c1", characterName: "Test"))    // count = 1
        router.push(.settings)                   // count = 2
        router.pop()                             // count = 1
        router.push(.memoryList(characterId: "c1")) // count = 2
        router.push(.characterDetail(characterId: "c2")) // count = 3
        router.pop()                             // count = 2
        router.pop()                             // count = 1

        #expect(router.path.count == 1)
    }

    // MARK: - Route Enum Hashability

    @Test("Route cases are Hashable and can be stored in a Set")
    func routeCasesAreHashable() {
        let routes: Set<AppRouter.Route> = [
            .chat(characterId: "c1", characterName: "Test"),
            .characterDetail(characterId: "c2"),
            .memoryList(characterId: "c3"),
            .settings,
        ]
        #expect(routes.count == 4)
    }

    @Test("same Route values are equal")
    func sameRouteValuesAreEqual() {
        let r1 = AppRouter.Route.chat(characterId: "char-emma", characterName: "Emma")
        let r2 = AppRouter.Route.chat(characterId: "char-emma", characterName: "Emma")
        #expect(r1 == r2)
    }

    @Test("different characterIds produce different chat Route values")
    func differentCharacterIdProducesDifferentRoutes() {
        let r1 = AppRouter.Route.chat(characterId: "char-emma", characterName: "Emma")
        let r2 = AppRouter.Route.chat(characterId: "char-luna", characterName: "Luna")
        #expect(r1 != r2)
    }

    @Test("settings Route is equal to itself")
    func settingsRouteEqualToItself() {
        let r1 = AppRouter.Route.settings
        let r2 = AppRouter.Route.settings
        #expect(r1 == r2)
    }
}
