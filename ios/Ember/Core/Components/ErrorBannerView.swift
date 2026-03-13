import SwiftUI

/// A dismissible error banner that slides down from the top of the screen.
///
/// Usage:
/// ```swift
/// .overlay(alignment: .top) {
///     ErrorBannerView(
///         error: viewModel.currentError,
///         onDismiss: { viewModel.dismissError() },
///         onRetry: { Task { await viewModel.retryLastAction() } }
///     )
/// }
/// ```
struct ErrorBannerView: View {
    let error: EmberError?
    let onDismiss: () -> Void
    var onRetry: (() -> Void)?

    /// Auto-dismiss delay in seconds. Set to `nil` to disable auto-dismiss.
    var autoDismissDelay: TimeInterval? = 5.0

    @State private var dismissTask: Task<Void, Never>?

    var body: some View {
        if let error {
            HStack(spacing: .emberSpacing8) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(Color.emberError)
                    .accessibilityHidden(true)

                Text(error.errorDescription ?? "Something went wrong.")
                    .font(.emberCaption)
                    .foregroundStyle(Color.emberTextPrimary)
                    .lineLimit(2)

                Spacer(minLength: 0)

                if error.isRetryable, let onRetry {
                    Button {
                        HapticManager.impact(.light)
                        onRetry()
                    } label: {
                        Text("Retry")
                            .font(.emberCaption)
                            .fontWeight(.semibold)
                            .foregroundStyle(Color.emberPrimary)
                    }
                    .accessibilityLabel("Retry failed action")
                }

                Button {
                    dismissBanner()
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(Color.emberTextSecondary)
                        .frame(minWidth: 28, minHeight: 28)
                }
                .accessibilityLabel("Dismiss error")
            }
            .padding(.horizontal, .emberSpacing16)
            .padding(.vertical, .emberSpacing12)
            .background(Color.emberSurface2)
            .clipShape(RoundedRectangle(cornerRadius: .emberRadius12))
            .overlay(
                RoundedRectangle(cornerRadius: .emberRadius12)
                    .strokeBorder(Color.emberError.opacity(0.3), lineWidth: 1)
            )
            .padding(.horizontal, .emberSpacing16)
            .padding(.top, .emberSpacing8)
            .transition(.move(edge: .top).combined(with: .opacity))
            .onAppear {
                HapticManager.notification(.error)
                scheduleAutoDismiss()
            }
            .onDisappear {
                dismissTask?.cancel()
            }
        }
    }

    // MARK: - Private

    private func dismissBanner() {
        dismissTask?.cancel()
        onDismiss()
    }

    private func scheduleAutoDismiss() {
        guard let delay = autoDismissDelay else { return }
        dismissTask?.cancel()
        dismissTask = Task {
            try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
            guard !Task.isCancelled else { return }
            await MainActor.run {
                onDismiss()
            }
        }
    }
}
