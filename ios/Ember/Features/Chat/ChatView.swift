import SwiftUI

struct ChatView: View {
    @Environment(AppRouter.self) private var router
    @State private var viewModel: ChatViewModel

    init(characterId: String, characterName: String = "", service: ChatServiceProtocol = ChatService()) {
        _viewModel = State(initialValue: ChatViewModel(
            characterId: characterId,
            characterName: characterName,
            service: service
        ))
    }

    var body: some View {
        VStack(spacing: 0) {
            messagesList
            ChatInputBar(
                text: $viewModel.inputText,
                isSending: viewModel.isStreaming,
                onSend: {
                    Task { await viewModel.sendMessage() }
                }
            )
        }
        .background(Color.emberBackground.ignoresSafeArea())
        .navigationTitle(viewModel.characterName)
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(Color.emberSurface, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .task {
            await viewModel.loadHistory()
        }
        .alert("Error", isPresented: Binding(
            get: { viewModel.errorMessage != nil },
            set: { if !$0 { viewModel.dismissError() } }
        )) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(viewModel.errorMessage ?? "")
        }
    }

    // MARK: - Message List

    @ViewBuilder
    private var messagesList: some View {
        if viewModel.isLoadingHistory && viewModel.messages.isEmpty {
            loadingView
        } else if !viewModel.isLoadingHistory && viewModel.messages.isEmpty {
            emptyStateView
        } else {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: .emberSpacing8) {
                        // Load-more indicator at the top
                        if viewModel.hasMore {
                            loadMoreTrigger
                        }

                        // Loading spinner for older messages
                        if viewModel.isLoadingMore {
                            ProgressView()
                                .tint(Color.emberPrimary)
                                .padding(.vertical, .emberSpacing8)
                        }

                        // Messages with date separators
                        ForEach(viewModel.chatListItems) { item in
                            switch item {
                            case .message(let message):
                                MessageBubbleView(message: message)
                                    .id(message.id)
                                    .transition(.opacity.combined(with: .move(edge: .bottom)))
                            case .dateSeparator(let separator):
                                DateSeparatorView(date: separator.date)
                                    .id(separator.id)
                            }
                        }
                    }
                    .padding(.vertical, .emberSpacing8)
                }
                .scrollDismissesKeyboard(.interactively)
                .defaultScrollAnchor(.bottom)
                .onChange(of: viewModel.messages.last?.id) { _, newId in
                    if let newId {
                        withAnimation(.easeOut(duration: 0.25)) {
                            proxy.scrollTo(newId, anchor: .bottom)
                        }
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var loadMoreTrigger: some View {
        Color.clear
            .frame(height: 1)
            .onAppear {
                Task { await viewModel.loadMoreIfNeeded() }
            }
    }

    @ViewBuilder
    private var loadingView: some View {
        VStack {
            Spacer()
            ProgressView()
                .tint(Color.emberPrimary)
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    @ViewBuilder
    private var emptyStateView: some View {
        VStack(spacing: .emberSpacing16) {
            Spacer()

            Image(systemName: "bubble.left.and.bubble.right")
                .font(.system(size: 48, weight: .medium))
                .foregroundStyle(Color.emberPrimary)
                .accessibilityHidden(true)

            Text("Start a conversation")
                .font(.emberTitle)
                .foregroundStyle(Color.emberTextPrimary)

            Text("Send a message to begin chatting")
                .font(.emberBody)
                .foregroundStyle(Color.emberTextSecondary)
                .multilineTextAlignment(.center)

            Spacer()
        }
        .padding(.horizontal, .emberSpacing20)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
