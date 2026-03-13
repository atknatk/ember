import SwiftUI

extension Font {
    /// Display — large titles, onboarding headers (28pt, bold)
    static let emberLargeTitle = Font.system(size: 28, weight: .bold, design: .default)

    /// Title — screen titles (22pt, semibold)
    static let emberTitle = Font.system(size: 22, weight: .semibold, design: .default)

    /// Headline — section headings (16pt, semibold)
    static let emberHeadline = Font.system(size: 16, weight: .semibold, design: .default)

    /// Body — chat messages, main text (15pt, regular)
    static let emberBody = Font.system(size: 15, weight: .regular, design: .default)

    /// Secondary — secondary text, descriptions (13pt, regular)
    static let emberSecondary = Font.system(size: 13, weight: .regular, design: .default)

    /// Caption — labels, chips (12pt, medium)
    static let emberCaption = Font.system(size: 12, weight: .medium, design: .default)

    /// Micro — timestamps, tiny text (11pt, regular)
    static let emberMicro = Font.system(size: 11, weight: .regular, design: .default)
}
