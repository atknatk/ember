import SwiftUI

struct TimezonePickerSheet: View {
    let selectedTimezone: String
    let onSelect: (String) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var searchText: String = ""

    private var filteredTimezones: [String] {
        let all = TimeZone.knownTimeZoneIdentifiers.sorted()
        if searchText.trimmingCharacters(in: .whitespaces).isEmpty {
            return all
        }
        let query = searchText.lowercased()
        return all.filter { $0.lowercased().contains(query) }
    }

    var body: some View {
        NavigationStack {
            List(filteredTimezones, id: \.self) { identifier in
                Button {
                    HapticManager.selection()
                    onSelect(identifier)
                } label: {
                    HStack {
                        VStack(alignment: .leading, spacing: .emberSpacing4) {
                            Text(identifier)
                                .font(.emberBody)
                                .foregroundStyle(Color.emberTextPrimary)

                            Text(utcOffset(for: identifier))
                                .font(.emberCaption)
                                .foregroundStyle(Color.emberTextSecondary)
                        }

                        Spacer()

                        if identifier == selectedTimezone {
                            Image(systemName: "checkmark")
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundStyle(Color.emberPrimary)
                                .accessibilityHidden(true)
                        }
                    }
                }
                .listRowBackground(Color.emberSurface)
                .accessibilityLabel("\(identifier), \(utcOffset(for: identifier))")
            }
            .listStyle(.plain)
            .searchable(
                text: $searchText,
                prompt: "Search timezones"
            )
            .navigationTitle("Select Timezone")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                    .foregroundStyle(Color.emberPrimary)
                }
            }
            .background(Color.emberBackground.ignoresSafeArea())
            .scrollContentBackground(.hidden)
        }
    }

    // MARK: - Helpers

    private func utcOffset(for identifier: String) -> String {
        guard let tz = TimeZone(identifier: identifier) else {
            return ""
        }
        let seconds = tz.secondsFromGMT()
        let hours = seconds / 3600
        let minutes = abs(seconds % 3600) / 60
        let sign = hours >= 0 ? "+" : ""
        if minutes == 0 {
            return "UTC\(sign)\(hours)"
        }
        return String(format: "UTC%@%d:%02d", sign, hours, minutes)
    }
}
