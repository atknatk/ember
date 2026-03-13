import SwiftUI

struct ChatView: View {
    @Environment(AppRouter.self) private var router
    @Environment(NetworkMonitor.self) private var networkMonitor
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

            // Voice recording overlay replaces input bar when recording or processing
            if viewModel.voiceRecorder.isRecording || viewModel.isProcessingVoice {
                VoiceRecordingOverlay(
                    audioLevels: viewModel.voiceRecorder.audioLevels,
                    duration: viewModel.voiceRecorder.recordingDuration,
                    isProcessing: viewModel.isProcessingVoice,
                    onCancel: { viewModel.cancelRecording() }
                )
                .transition(.move(edge: .bottom).combined(with: .opacity))
            } else {
                ChatInputBar(
                    text: $viewModel.inputText,
                    isSending: viewModel.isStreaming,
                    isRecording: viewModel.voiceRecorder.isRecording,
                    isProcessingVoice: viewModel.isProcessingVoice,
                    onSend: {
                        Task { await viewModel.sendMessage() }
                    },
                    onStartRecording: {
                        Task { await viewModel.startRecording() }
                    },
                    onStopRecording: {
                        viewModel.stopRecording()
                    }
                )
                .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .animation(.easeInOut(duration: 0.25), value: viewModel.voiceRecorder.isRecording)
        .animation(.easeInOut(duration: 0.25), value: viewModel.isProcessingVoice)
        .background(Color.emberBackground.ignoresSafeArea())
        .navigationTitle(viewModel.characterName)
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(Color.emberSurface, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .task {
            await viewModel.loadHistory()
        }
        .overlay(alignment: .top) {
            VStack(spacing: .emberSpacing4) {
                OfflineBannerView(isOffline: !networkMonitor.isConnected)

                ErrorBannerView(
                    error: viewModel.currentError,
                    onDismiss: { viewModel.dismissError() },
                    onRetry: viewModel.currentError?.isRetryable == true
                        ? { Task { await viewModel.loadHistory() } }
                        : nil
                )
            }
            .animation(.easeInOut(duration: 0.3), value: viewModel.currentError)
            .animation(.easeInOut(duration: 0.3), value: networkMonitor.isConnected)
        }
        .alert(
            "Microphone Access Required",
            isPresented: $viewModel.showMicPermissionAlert
        ) {
            Button("Open Settings") {
                viewModel.openSettings()
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Ember needs microphone access to record voice messages. Please enable it in Settings.")
        }
        .onReceive(NotificationCenter.default.publisher(for: UIApplication.willResignActiveNotification)) { _ in
            // Stop recording if user backgrounds the app
            if viewModel.voiceRecorder.isRecording {
                viewModel.cancelRecording()
            }
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
                                    .transition(.move(edge: .bottom).combined(with: .opacity))
                            case .dateSeparator(let separator):
                                DateSeparatorView(date: separator.date)
                                    .id(separator.id)
                            }
                        }
                        .animation(
                            .spring(response: 0.35, dampingFraction: 0.8),
                            value: viewModel.messages.count
                        )
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
        VStack(spacing: .emberSpacing8) {
            Spacer()

            // Skeleton chat bubbles mimicking a conversation
            skeletonBubble(alignment: .leading, widthFraction: 0.7)
            skeletonBubble(alignment: .trailing, widthFraction: 0.5)
            skeletonBubble(alignment: .leading, widthFraction: 0.6)
            skeletonBubble(alignment: .trailing, widthFraction: 0.45)
        }
        .padding(.horizontal, .emberSpacing16)
        .padding(.bottom, .emberSpacing16)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    @ViewBuilder
    private func skeletonBubble(alignment: HorizontalAlignment, widthFraction: CGFloat) -> some View {
        HStack {
            if alignment == .trailing { Spacer(minLength: 60) }

            ShimmerView(cornerRadius: .emberRadius16)
                .frame(height: 44)
                .frame(maxWidth: .infinity)

            if alignment == .leading { Spacer(minLength: 60) }
        }
    }

    @ViewBuilder
    private var emptyStateView: some View {
        VStack(spacing: .emberSpacing16) {
            Spacer()

            EmptyChatIconView()
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

// MARK: - Empty Chat Icon with Pulse

/// Gentle scale pulse animation for the empty chat state icon.
private struct EmptyChatIconView: View {
    @State private var isPulsing: Bool = false

    var body: some View {
        Image(systemName: "bubble.left.and.bubble.right")
            .font(.system(size: 48, weight: .medium))
            .foregroundStyle(Color.emberPrimary)
            .scaleEffect(isPulsing ? 1.05 : 0.95)
            .animation(
                .easeInOut(duration: 2.0)
                .repeatForever(autoreverses: true),
                value: isPulsing
            )
            .onAppear { isPulsing = true }
    }
}
