import SwiftUI

/// Displays a date header between message groups on different days.
/// Shows "Today", "Yesterday", or the full date for older messages.
struct DateSeparatorView: View {
    let date: Date

    var body: some View {
        HStack(spacing: .emberSpacing12) {
            separator
            Text(formattedDate)
                .font(.emberCaption)
                .foregroundStyle(Color.emberTextSecondary)
            separator
        }
        .padding(.horizontal, .emberSpacing20)
        .padding(.vertical, .emberSpacing8)
        .accessibilityLabel("Messages from \(formattedDate)")
    }

    // MARK: - Private

    @ViewBuilder
    private var separator: some View {
        Rectangle()
            .fill(Color.emberSurface3)
            .frame(height: 0.5)
    }

    private var formattedDate: String {
        let calendar = Calendar.current

        if calendar.isDateInToday(date) {
            return "Today"
        } else if calendar.isDateInYesterday(date) {
            return "Yesterday"
        } else {
            let formatter = DateFormatter()
            // Show year only if the date is not in the current year
            if calendar.component(.year, from: date) == calendar.component(.year, from: Date()) {
                formatter.dateFormat = "d MMMM"
            } else {
                formatter.dateFormat = "d MMMM yyyy"
            }
            return formatter.string(from: date)
        }
    }
}
