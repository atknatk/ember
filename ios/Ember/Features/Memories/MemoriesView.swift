import SwiftUI

struct MemoriesView: View {
    @State private var viewModel: MemoriesViewModel

    init(apiClient: APIClientProtocol = APIClient.shared) {
        _viewModel = State(initialValue: MemoriesViewModel(apiClient: apiClient))
    }

    var body: some View {
        VStack(spacing: 0) {
            characterPicker
                .padding(.horizontal, .emberSpacing20)
                .padding(.vertical, .emberSpacing12)

            if viewModel.isLoading {
                loadingView
            } else if viewModel.memories.isEmpty {
                emptyStateView
            } else {
                memoryList
            }
        }
        .background(Color.emberBackground.ignoresSafeArea())
        .navigationTitle("Memories")
        .navigationBarTitleDisplayMode(.large)
        .task {
            await viewModel.loadInitialData()
        }
        .alert("Delete Memory?", isPresented: Binding(
            get: { viewModel.showDeleteConfirmation },
            set: { viewModel.showDeleteConfirmation = $0 }
        )) {
            Button("Cancel", role: .cancel) {}
            Button("Delete", role: .destructive) {
                Task { await viewModel.confirmDelete() }
            }
        } message: {
            Text("This memory will be permanently removed. This action cannot be undone.")
        }
        .alert("Error", isPresented: $viewModel.showError) {
            Button("OK", role: .cancel) {}
            Button("Retry") {
                Task { await viewModel.loadMemories() }
            }
        } message: {
            Text(viewModel.errorMessage ?? "")
        }
    }

    // MARK: - Character Picker

    @ViewBuilder
    private var characterPicker: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: .emberSpacing8) {
                segmentPill(label: "Global", segment: .global)

                ForEach(viewModel.characters) { character in
                    segmentPill(
                        label: character.name,
                        segment: .character(id: character.id, name: character.name)
                    )
                }
            }
        }
    }

    @ViewBuilder
    private func segmentPill(label: String, segment: MemorySegment) -> some View {
        let isSelected = viewModel.selectedSegment == segment

        Button {
            HapticManager.selection()
            Task { await viewModel.selectSegment(segment) }
        } label: {
            Text(label)
                .font(.emberCaption)
                .fontWeight(isSelected ? .semibold : .regular)
                .foregroundStyle(isSelected ? .white : Color.emberTextSecondary)
                .padding(.horizontal, .emberSpacing12)
                .padding(.vertical, .emberSpacing8)
                .background(
                    Capsule()
                        .fill(isSelected ? Color.emberPrimary : Color.emberSurface2)
                )
        }
        .accessibilityLabel("\(label) memories")
        .accessibilityAddTraits(.isButton)
        .accessibilityAddTraits(isSelected ? .isSelected : [])
        .animation(.easeInOut(duration: 0.2), value: isSelected)
    }

    // MARK: - Loading

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

    // MARK: - Empty State

    @ViewBuilder
    private var emptyStateView: some View {
        VStack(spacing: .emberSpacing16) {
            Spacer()

            Image(systemName: EmberSymbol.memory)
                .font(.system(size: 48, weight: .medium))
                .foregroundStyle(Color.emberTextSecondary)
                .accessibilityHidden(true)

            Text("No memories yet")
                .font(.emberTitle)
                .foregroundStyle(Color.emberTextPrimary)

            Text("Start chatting and I'll remember what matters.")
                .font(.emberBody)
                .foregroundStyle(Color.emberTextSecondary)
                .multilineTextAlignment(.center)

            Spacer()
        }
        .padding(.horizontal, .emberSpacing20)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Memory List

    @ViewBuilder
    private var memoryList: some View {
        List {
            ForEach(viewModel.memories) { memory in
                MemoryRowView(memory: memory)
                    .listRowBackground(Color.emberBackground)
                    .listRowSeparator(.hidden)
                    .listRowInsets(EdgeInsets(
                        top: .emberSpacing4,
                        leading: .emberSpacing20,
                        bottom: .emberSpacing4,
                        trailing: .emberSpacing20
                    ))
                    .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                        Button(role: .destructive) {
                            viewModel.memoryToDelete = memory
                        } label: {
                            Label("Delete", systemImage: "trash")
                        }
                    }
                    .transition(
                        .asymmetric(
                            insertion: .opacity,
                            removal: .move(edge: .trailing).combined(with: .opacity)
                        )
                    )
            }
        }
        .listStyle(.plain)
        .scrollContentBackground(.hidden)
    }
}
