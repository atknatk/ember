import SwiftUI

struct MainTabView: View {
    @Environment(AppRouter.self) private var router
    @State private var selectedTab: Tab = .home

    enum Tab: String, CaseIterable {
        case home
        case memories
        case profile
    }

    var body: some View {
        @Bindable var router = router

        TabView(selection: $selectedTab) {
            NavigationStack(path: $router.path) {
                HomeView()
                    .navigationDestination(for: AppRouter.Route.self) { route in
                        destinationView(for: route)
                    }
            }
            .tabItem {
                Label(
                    "Home",
                    systemImage: selectedTab == .home
                        ? EmberSymbol.homeFill
                        : EmberSymbol.home
                )
            }
            .tag(Tab.home)

            NavigationStack {
                MemoriesView()
                    .navigationDestination(for: AppRouter.Route.self) { route in
                        destinationView(for: route)
                    }
            }
            .tabItem {
                Label(
                    "Memories",
                    systemImage: selectedTab == .memories
                        ? EmberSymbol.memoryTabFill
                        : EmberSymbol.memoryTab
                )
            }
            .tag(Tab.memories)

            NavigationStack {
                ProfilePlaceholderView()
                    .navigationDestination(for: AppRouter.Route.self) { route in
                        destinationView(for: route)
                    }
            }
            .tabItem {
                Label(
                    "Profile",
                    systemImage: selectedTab == .profile
                        ? EmberSymbol.profileFill
                        : EmberSymbol.profile
                )
            }
            .tag(Tab.profile)
        }
        .tint(Color.emberPrimary)
        .onAppear {
            let appearance = UITabBarAppearance()
            appearance.configureWithOpaqueBackground()
            appearance.backgroundColor = UIColor(Color.emberSurface)
            UITabBar.appearance().standardAppearance = appearance
            UITabBar.appearance().scrollEdgeAppearance = appearance
        }
    }

    @ViewBuilder
    private func destinationView(for route: AppRouter.Route) -> some View {
        switch route {
        case .characterDetail:
            Text("Character Detail")
                .foregroundStyle(Color.emberTextPrimary)
        case .chat(let characterId, let characterName):
            ChatView(characterId: characterId, characterName: characterName)
        case .memoryList:
            Text("Memory List")
                .foregroundStyle(Color.emberTextPrimary)
        case .settings:
            Text("Settings")
                .foregroundStyle(Color.emberTextPrimary)
        case .createCharacter:
            Text("Create Character — Coming Soon")
                .font(.emberTitle)
                .foregroundStyle(Color.emberTextPrimary)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Color.emberBackground.ignoresSafeArea())
        }
    }
}
