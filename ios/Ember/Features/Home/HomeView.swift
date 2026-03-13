import SwiftUI

struct HomeView: View {
    @Environment(AppRouter.self) private var router
    @State private var viewModel: HomeViewModel
    @State private var hasAppeared: Bool = false

    init(apiClient: APIClientProtocol = APIClient.shared) {
        _viewModel = State(initialValue: HomeViewModel(apiClient: apiClient))
    }

    var body: some View {
        Group {
            if viewModel.isLoading && viewModel.characters.isEmpty {
                loadingView
                    .transition(.opacity)
            } else if !viewModel.isLoading && viewModel.characters.isEmpty && viewModel.errorMessage == nil {
                emptyStateView
            } else {
                characterListContent
                    .transition(.opacity)
            }
        }
        .background(Color.emberBackground.ignoresSafeArea())
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button {
                    router.push(.settings)
                } label: {
                    Image(systemName: EmberSymbol.settings)
                        .symbolRenderingMode(.hierarchical)
                        .foregroundStyle(Color.emberTextSecondary)
                }
                .accessibilityLabel("Settings")
            }
        }
        .animation(.easeInOut(duration: 0.3), value: viewModel.isLoading)
        .task {
            await viewModel.loadCharacters()
        }
        .alert("Error", isPresented: Binding(
            get: { viewModel.errorMessage != nil },
            set: { if !$0 { viewModel.errorMessage = nil } }
        )) {
            Button("OK", role: .cancel) {}
            Button("Retry") {
                Task { await viewModel.loadCharacters() }
            }
        } message: {
            Text(viewModel.errorMessage ?? "")
        }
    }

    // MARK: - Subviews

    @ViewBuilder
    private var loadingView: some View {
        ScrollView {
            VStack(spacing: .emberSpacing24) {
                // Greeting skeleton
                VStack(alignment: .leading, spacing: .emberSpacing4) {
                    ShimmerView(cornerRadius: .emberRadius4)
                        .frame(width: 180, height: 22)
                    ShimmerView(cornerRadius: .emberRadius4)
                        .frame(width: 140, height: 13)
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                // Daily summary skeleton
                ShimmerView(cornerRadius: .emberRadius20)
                    .frame(height: 100)

                // Character grid skeleton
                LazyVGrid(
                    columns: [
                        GridItem(.flexible(), spacing: .emberSpacing16),
                        GridItem(.flexible(), spacing: .emberSpacing16)
                    ],
                    spacing: .emberSpacing16
                ) {
                    ForEach(0..<4, id: \.self) { _ in
                        ShimmerView(cornerRadius: .emberRadius20)
                            .frame(height: 160)
                    }
                }
            }
            .padding(.horizontal, .emberSpacing20)
            .padding(.top, .emberSpacing8)
            .padding(.bottom, .emberSpacing32)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    @ViewBuilder
    private var emptyStateView: some View {
        VStack(spacing: .emberSpacing16) {
            Spacer()

            Image(systemName: "person.3.fill")
                .font(.system(size: 48, weight: .medium))
                .foregroundStyle(Color.emberPrimary)
                .accessibilityHidden(true)

            Text("No characters yet")
                .font(.emberTitle)
                .foregroundStyle(Color.emberTextPrimary)

            Text("Start chatting by adding your first character")
                .font(.emberBody)
                .foregroundStyle(Color.emberTextSecondary)
                .multilineTextAlignment(.center)

            Button {
                HapticManager.impact(.light)
                router.push(.createCharacter)
            } label: {
                Text("Add Character")
                    .font(.emberHeadline)
                    .foregroundStyle(.white)
                    .padding(.horizontal, .emberSpacing24)
                    .padding(.vertical, .emberSpacing12)
                    .background(Color.emberPrimary)
                    .clipShape(RoundedRectangle(cornerRadius: .emberRadius28))
            }
            .padding(.top, .emberSpacing8)

            Spacer()
        }
        .padding(.horizontal, .emberSpacing20)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    @ViewBuilder
    private var characterListContent: some View {
        ScrollView {
            VStack(spacing: .emberSpacing24) {
                greetingHeader
                dailySummarySection
                characterGrid
            }
            .padding(.horizontal, .emberSpacing20)
            .padding(.top, .emberSpacing8)
            .padding(.bottom, .emberSpacing32)
        }
        .refreshable {
            await viewModel.loadCharacters()
        }
    }

    @ViewBuilder
    private var greetingHeader: some View {
        VStack(alignment: .leading, spacing: .emberSpacing4) {
            Text(greetingText)
                .font(.emberTitle)
                .foregroundStyle(Color.emberTextPrimary)

            Text(dateString)
                .font(.emberSecondary)
                .foregroundStyle(Color.emberTextSecondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
        .opacity(hasAppeared ? 1 : 0)
        .offset(y: hasAppeared ? 0 : 10)
        .onAppear {
            withAnimation(.easeOut(duration: 0.4)) {
                hasAppeared = true
            }
        }
    }

    @ViewBuilder
    private var dailySummarySection: some View {
        DailySummaryCard(
            characterName: viewModel.defaultCharacter?.name,
            message: viewModel.defaultCharacterLastMessage,
            onTap: {
                if let defaultChar = viewModel.defaultCharacter {
                    HomeViewModel.markCharacterAsOpened(defaultChar.id)
                    router.push(.chat(characterId: defaultChar.id, characterName: defaultChar.name))
                }
            }
        )
    }

    @ViewBuilder
    private var characterGrid: some View {
        LazyVGrid(
            columns: [
                GridItem(.flexible(), spacing: .emberSpacing16),
                GridItem(.flexible(), spacing: .emberSpacing16)
            ],
            spacing: .emberSpacing16
        ) {
            ForEach(Array(viewModel.characters.enumerated()), id: \.element.id) { index, character in
                CharacterCardView(
                    character: character,
                    lastMessage: viewModel.lastMessages[character.id],
                    hasUnread: HomeViewModel.hasUnreadMessages(for: character),
                    onTap: {
                        HomeViewModel.markCharacterAsOpened(character.id)
                        router.push(.chat(characterId: character.id, characterName: character.name))
                    }
                )
                .transition(.opacity)
                .animation(
                    .easeIn(duration: 0.25).delay(Double(index) * 0.05),
                    value: viewModel.characters.count
                )
            }

            AddCharacterCardView {
                router.push(.createCharacter)
            }
        }
    }

    // MARK: - Computed

    private var greetingText: String {
        let greeting = HomeViewModel.greeting()
        if viewModel.userName.isEmpty {
            return greeting
        }
        return "\(greeting), \(viewModel.userName)"
    }

    private var dateString: String {
        let formatter = DateFormatter()
        formatter.dateFormat = "EEEE, d MMMM"
        return formatter.string(from: Date())
    }
}
