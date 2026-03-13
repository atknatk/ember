import Foundation
import Observation

@Observable
final class OnboardingViewModel {
    // MARK: - Phase

    enum Phase {
        case welcome
        case questions
    }

    var currentPhase: Phase = .welcome

    // MARK: - Welcome

    var currentWelcomePage: Int = 0

    // MARK: - Questions

    var currentQuestionIndex: Int = 0
    var answers: [String] = Array(repeating: "", count: 7)

    // MARK: - Submission

    var isSubmitting: Bool = false
    var errorMessage: String? = nil

    // MARK: - Dependencies

    private let apiClient: APIClientProtocol

    // MARK: - Question Definitions

    static let questionKeys = [
        "preferred_name",
        "occupation",
        "daily_rhythm",
        "health_goal",
        "stress_management",
        "sleep_schedule",
        "communication_style",
    ]

    static let questionTexts = [
        "What should I call you?",
        "What do you do for work?",
        "Are you a morning person or a night owl?",
        "What are your health or fitness goals?",
        "How do you manage stress?",
        "What is your sleep schedule like?",
        "What kind of friendship do you expect from me?",
    ]

    static let questionPlaceholders = [
        "Your preferred name",
        "Your occupation or field",
        "e.g., Early bird, Night owl",
        "e.g., Run a marathon, eat healthier",
        "e.g., Exercise, meditation, walks",
        "e.g., 11pm to 7am",
        "e.g., Casual and fun, supportive coach",
    ]

    // MARK: - Init

    init(apiClient: APIClientProtocol = APIClient.shared) {
        self.apiClient = apiClient
    }

    // MARK: - Computed Properties

    var canSubmit: Bool {
        answers.contains { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
    }

    var currentAnswerIsEmpty: Bool {
        answers[currentQuestionIndex].trimmingCharacters(in: .whitespaces).isEmpty
    }

    var progressFraction: Double {
        Double(currentQuestionIndex + 1) / 7.0
    }

    // MARK: - Welcome Actions

    func advanceToQuestions() {
        currentPhase = .questions
    }

    // MARK: - Question Navigation

    func advanceToNextQuestion() {
        guard currentQuestionIndex < 6 else { return }
        currentQuestionIndex += 1
    }

    func goToPreviousQuestion() {
        guard currentQuestionIndex > 0 else { return }
        currentQuestionIndex -= 1
    }

    func skipCurrentQuestion() {
        answers[currentQuestionIndex] = ""
        if currentQuestionIndex == 6 {
            Task { await submitOnboarding() }
        } else {
            advanceToNextQuestion()
        }
    }

    // MARK: - Submission

    @discardableResult
    func submitOnboarding() async -> Bool {
        isSubmitting = true
        errorMessage = nil

        let answersArray = Self.questionKeys.enumerated().map { index, key in
            let answer = answers[index].trimmingCharacters(in: .whitespaces)
            return OnboardingAnswer(
                questionKey: key,
                answer: answer.isEmpty ? "Not provided" : answer
            )
        }

        let requestBody = OnboardingRequest(answers: answersArray)

        do {
            let _ = try await apiClient.request(
                endpoint: .completeOnboarding,
                body: requestBody,
                responseType: OnboardingResponse.self
            )
            isSubmitting = false
            return true
        } catch let error as APIError {
            // 409 Conflict means onboarding already completed -- treat as success
            if case .serverError(let statusCode, _) = error, statusCode == 409 {
                isSubmitting = false
                return true
            }
            errorMessage = error.localizedDescription
            isSubmitting = false
            return false
        } catch {
            errorMessage = "Something went wrong. Please try again."
            isSubmitting = false
            return false
        }
    }
}
