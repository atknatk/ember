import SwiftUI

/// A persistent banner displayed when the device is offline.
///
/// Unlike `ErrorBannerView`, this banner is not dismissible — it stays visible
/// until connectivity is restored. Place it in an overlay at the top of any
/// content view that requires network access.
///
/// Usage:
/// ```swift
/// .overlay(alignment: .top) {
///     OfflineBannerView(isOffline: !networkMonitor.isConnected)
/// }
/// ```
struct OfflineBannerView: View {
    let isOffline: Bool

    var body: some View {
        if isOffline {
            HStack(spacing: .emberSpacing8) {
                Image(systemName: "wifi.slash")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(Color.emberWarning)
                    .accessibilityHidden(true)

                Text("You're offline")
                    .font(.emberCaption)
                    .fontWeight(.medium)
                    .foregroundStyle(Color.emberTextPrimary)

                Spacer()
            }
            .padding(.horizontal, .emberSpacing16)
            .padding(.vertical, .emberSpacing8)
            .background(Color.emberWarning.opacity(0.15))
            .clipShape(RoundedRectangle(cornerRadius: .emberRadius12))
            .overlay(
                RoundedRectangle(cornerRadius: .emberRadius12)
                    .strokeBorder(Color.emberWarning.opacity(0.3), lineWidth: 1)
            )
            .padding(.horizontal, .emberSpacing16)
            .padding(.top, .emberSpacing8)
            .transition(.move(edge: .top).combined(with: .opacity))
            .accessibilityElement(children: .combine)
            .accessibilityLabel("You are offline. Check your internet connection.")
        }
    }
}
