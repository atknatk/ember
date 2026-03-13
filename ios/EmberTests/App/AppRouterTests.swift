import Testing
@testable import Ember

@Suite("AppRouter")
struct AppRouterTests {

    @Test("push adds route to path")
    func pushAddsRouteToPath() {
        let router = AppRouter()

        router.push(.chat(characterId: "c1", characterName: "Test"))

        #expect(router.path.count == 1)
    }

    @Test("pop removes last route from path")
    func popRemovesLastRoute() {
        let router = AppRouter()
        router.push(.chat(characterId: "c1", characterName: "Test"))
        router.push(.settings)

        router.pop()

        #expect(router.path.count == 1)
    }

    @Test("popToRoot clears all routes")
    func popToRootClearsPath() {
        let router = AppRouter()
        router.push(.chat(characterId: "c1", characterName: "Test"))
        router.push(.settings)
        router.push(.memoryList(characterId: "c1"))

        router.popToRoot()

        #expect(router.path.count == 0)
    }

    @Test("pop on empty path does not crash")
    func popOnEmptyPathDoesNotCrash() {
        let router = AppRouter()

        router.pop()

        #expect(router.path.count == 0)
    }

    @Test("popToRoot on empty path does not crash")
    func popToRootOnEmptyPathDoesNotCrash() {
        let router = AppRouter()

        router.popToRoot()

        #expect(router.path.count == 0)
    }
}
