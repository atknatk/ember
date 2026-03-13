import Observation
import SwiftUI

@Observable
final class AppRouter {
    var path = NavigationPath()

    enum Route: Hashable {
        case characterDetail(characterId: String)
        case chat(characterId: String, characterName: String)
        case memoryList(characterId: String)
        case settings
        case createCharacter
    }

    func push(_ route: Route) {
        path.append(route)
    }

    func pop() {
        guard path.count > 0 else { return }
        path.removeLast()
    }

    func popToRoot() {
        guard path.count > 0 else { return }
        path.removeLast(path.count)
    }
}
