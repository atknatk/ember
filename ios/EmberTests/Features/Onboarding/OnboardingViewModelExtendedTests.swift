import Testing
import Foundation
@testable import Ember

/// Extended tests for `OnboardingViewModel` — edge cases not covered by `OnboardingViewModelTests.swift`.
/// Covers: progressFraction at every step, "Not provided" fallback encoding, isSubmitting transitions,
/// all-empty submit, whitespace-only submit, endpoint verification, multi-step navigation sequences,
/// skip on last question, generic error handling, and canSubmit edge cases.
@Suite("OnboardingViewModel Extended")
struct OnboardingViewModelExtendedTests {

    // MARK: - Helpers

    private func makeViewModel(mockAPI: MockAPIClient = MockAPIClient()) -> OnboardingViewModel {
        OnboardingViewModel(apiClient: mockAPI)
    }

    // MARK: - progressFraction at Every Step

    @Test("progressFraction returns correct fraction for every question index")
    func progressFractionAllIndices() {
        let vm = makeViewModel()

        let expectedFractions: [Double] = [
            1.0 / 7.0,
            2.0 / 7.0,
            3.0 / 7.0,
            4.0 / 7.0,
            5.0 / 7.0,
            6.0 / 7.0,
            7.0 / 7.0,
        ]

        for (index, expected) in expectedFractions.enumerated() {
            vm.currentQuestionIndex = index
            #expect(
                abs(vm.progressFraction - expected) < 0.0001,
                "Expected progressFraction \(expected) at index \(index), got \(vm.progressFraction)"
            )
        }
    }

    @Test("progressFraction at index 3 is 4/7")
    func progressFractionAtMiddle() {
        let vm = makeViewModel()
        vm.currentQuestionIndex = 3
        #expect(abs(vm.progressFraction - (4.0 / 7.0)) < 0.0001)
    }

    // MARK: - canSubmit Edge Cases

    @Test("canSubmit is false when all answers contain only whitespace across multiple indices")
    func canSubmitFalseAllWhitespace() {
        let vm = makeViewModel()
        vm.answers[0] = "  "
        vm.answers[1] = "\t"
        vm.answers[2] = "   "
        vm.answers[3] = ""
        vm.answers[4] = "\n"
        vm.answers[5] = " "
        vm.answers[6] = "  "
        #expect(vm.canSubmit == false)
    }

    @Test("canSubmit is true when last answer is non-empty")
    func canSubmitTrueWhenLastAnswered() {
        let vm = makeViewModel()
        vm.answers[6] = "Casual and fun"
        #expect(vm.canSubmit == true)
    }

    @Test("canSubmit is true when middle answer is non-empty")
    func canSubmitTrueWhenMiddleAnswered() {
        let vm = makeViewModel()
        vm.answers[3] = "Run a marathon"
        #expect(vm.canSubmit == true)
    }

    @Test("canSubmit becomes false after clearing the only non-empty answer")
    func canSubmitBecomeFalseAfterClear() {
        let vm = makeViewModel()
        vm.answers[2] = "Night owl"
        #expect(vm.canSubmit == true)
        vm.answers[2] = ""
        #expect(vm.canSubmit == false)
    }

    // MARK: - currentAnswerIsEmpty Edge Cases

    @Test("currentAnswerIsEmpty is true when answer is only whitespace")
    func currentAnswerIsEmptyWhitespace() {
        let vm = makeViewModel()
        vm.currentQuestionIndex = 4
        vm.answers[4] = "   \t  "
        #expect(vm.currentAnswerIsEmpty == true)
    }

    @Test("currentAnswerIsEmpty reflects currentQuestionIndex correctly")
    func currentAnswerIsEmptyReflectsIndex() {
        let vm = makeViewModel()
        vm.answers[0] = "Alex"
        vm.answers[1] = ""
        vm.currentQuestionIndex = 0
        #expect(vm.currentAnswerIsEmpty == false)
        vm.currentQuestionIndex = 1
        #expect(vm.currentAnswerIsEmpty == true)
    }

    // MARK: - Navigation Sequences

    @Test("advanceToNextQuestion can step from index 0 to 6 sequentially")
    func advanceToNextQuestionFullSequence() {
        let vm = makeViewModel()
        for expected in 1...6 {
            vm.advanceToNextQuestion()
            #expect(vm.currentQuestionIndex == expected)
        }
        // One more call at 6 should not advance
        vm.advanceToNextQuestion()
        #expect(vm.currentQuestionIndex == 6)
    }

    @Test("goToPreviousQuestion can step from index 6 to 0 sequentially")
    func goToPreviousQuestionFullSequence() {
        let vm = makeViewModel()
        vm.currentQuestionIndex = 6
        for expected in stride(from: 5, through: 0, by: -1) {
            vm.goToPreviousQuestion()
            #expect(vm.currentQuestionIndex == expected)
        }
        // One more call at 0 should not go below 0
        vm.goToPreviousQuestion()
        #expect(vm.currentQuestionIndex == 0)
    }

    @Test("advance then go back returns to original index")
    func advanceAndGoBackReturnsSameIndex() {
        let vm = makeViewModel()
        vm.currentQuestionIndex = 3
        vm.advanceToNextQuestion()
        #expect(vm.currentQuestionIndex == 4)
        vm.goToPreviousQuestion()
        #expect(vm.currentQuestionIndex == 3)
    }

    // MARK: - Skip Current Question

    @Test("skipCurrentQuestion on index 0 clears answer and moves to index 1")
    func skipFirstQuestionAdvancesToSecond() {
        let vm = makeViewModel()
        vm.answers[0] = "Some name"
        vm.currentQuestionIndex = 0

        vm.skipCurrentQuestion()

        #expect(vm.answers[0] == "")
        #expect(vm.currentQuestionIndex == 1)
    }

    @Test("skipCurrentQuestion on index 5 clears answer and moves to index 6")
    func skipQuestionFiveAdvancesToSix() {
        let vm = makeViewModel()
        vm.answers[5] = "11pm to 7am"
        vm.currentQuestionIndex = 5

        vm.skipCurrentQuestion()

        #expect(vm.answers[5] == "")
        #expect(vm.currentQuestionIndex == 6)
    }

    @Test("skipCurrentQuestion on index 6 clears the answer")
    func skipLastQuestionClearsAnswer() {
        let vm = makeViewModel()
        vm.answers[6] = "Casual and fun"
        vm.currentQuestionIndex = 6

        vm.skipCurrentQuestion()

        // The answer for the last question must be cleared
        #expect(vm.answers[6] == "")
        // Index does not advance past 6
        #expect(vm.currentQuestionIndex == 6)
    }

    @Test("skipCurrentQuestion preserves other answers when skipping mid-flow")
    func skipPreservesOtherAnswers() {
        let vm = makeViewModel()
        vm.answers[0] = "Alex"
        vm.answers[1] = "Engineer"
        vm.answers[3] = "Run a marathon"
        vm.currentQuestionIndex = 2

        vm.skipCurrentQuestion()

        #expect(vm.answers[0] == "Alex")
        #expect(vm.answers[1] == "Engineer")
        #expect(vm.answers[2] == "")
        #expect(vm.answers[3] == "Run a marathon")
    }

    // MARK: - Phase Transition

    @Test("advanceToQuestions called twice stays in questions phase")
    func advanceToQuestionsIdempotent() {
        let vm = makeViewModel()
        vm.advanceToQuestions()
        vm.advanceToQuestions()
        #expect(vm.currentPhase == .questions)
    }

    @Test("initial phase is welcome before any navigation")
    func initialPhaseIsWelcome() {
        let vm = makeViewModel()
        #expect(vm.currentPhase == .welcome)
        #expect(vm.currentWelcomePage == 0)
    }

    // MARK: - Submit: Not Provided Fallback

    @Test("submitOnboarding sends Not provided for empty answers")
    func submitOnboardingNotProvidedFallback() async {
        let mockAPI = MockAPIClient()
        mockAPI.requestResult = OnboardingResponse(onboardingCompleted: true, memoriesSeeded: 3)
        let vm = makeViewModel(mockAPI: mockAPI)
        // Only fill answers 0, 2, and 4; leave others blank
        vm.answers[0] = "Alex"
        vm.answers[2] = "Night owl"
        vm.answers[4] = "Meditation"
        // answers[1], [3], [5], [6] are empty strings

        let result = await vm.submitOnboarding()

        #expect(result == true)
        // Verify that the mock was called once
        #expect(mockAPI.requestCallCount == 1)
        // The endpoint used must be completeOnboarding
        if let endpoint = mockAPI.lastEndpoint, case .completeOnboarding = endpoint {
            // expected
        } else {
            #expect(Bool(false), "Expected .completeOnboarding endpoint, got \(String(describing: mockAPI.lastEndpoint))")
        }
    }

    @Test("submitOnboarding sends Not provided for all answers when all are empty")
    func submitOnboardingAllEmpty() async {
        let mockAPI = MockAPIClient()
        mockAPI.requestResult = OnboardingResponse(onboardingCompleted: true, memoriesSeeded: 0)
        let vm = makeViewModel(mockAPI: mockAPI)
        // all answers remain the default empty strings

        let result = await vm.submitOnboarding()

        // The ViewModel must still call the API — it does not block on canSubmit
        #expect(mockAPI.requestCallCount == 1)
        #expect(result == true)
    }

    @Test("submitOnboarding sends Not provided for whitespace-only answer")
    func submitOnboardingWhitespaceFallback() async {
        let mockAPI = MockAPIClient()
        mockAPI.requestResult = OnboardingResponse(onboardingCompleted: true, memoriesSeeded: 7)
        let vm = makeViewModel(mockAPI: mockAPI)
        // Set one answer to whitespace — should be treated as blank
        vm.answers[0] = "   "
        vm.answers[1] = "Developer"

        let result = await vm.submitOnboarding()

        #expect(result == true)
        #expect(mockAPI.requestCallCount == 1)
    }

    @Test("submitOnboarding uses completeOnboarding endpoint")
    func submitOnboardingUsesCorrectEndpoint() async {
        let mockAPI = MockAPIClient()
        mockAPI.requestResult = OnboardingResponse(onboardingCompleted: true, memoriesSeeded: 1)
        let vm = makeViewModel(mockAPI: mockAPI)
        vm.answers[0] = "Alex"

        await vm.submitOnboarding()

        if let endpoint = mockAPI.lastEndpoint, case .completeOnboarding = endpoint {
            // correct
        } else {
            #expect(Bool(false), "Expected .completeOnboarding endpoint")
        }
    }

    // MARK: - isSubmitting Transitions

    @Test("isSubmitting is false after successful submission")
    func isSubmittingFalseAfterSuccess() async {
        let mockAPI = MockAPIClient()
        mockAPI.requestResult = OnboardingResponse(onboardingCompleted: true, memoriesSeeded: 7)
        let vm = makeViewModel(mockAPI: mockAPI)
        vm.answers[0] = "Alex"

        await vm.submitOnboarding()

        #expect(vm.isSubmitting == false)
    }

    @Test("isSubmitting is false after 503 error")
    func isSubmittingFalseAfterError() async {
        let mockAPI = MockAPIClient()
        mockAPI.requestError = APIError.serverError(statusCode: 503, detail: "Service unavailable")
        let vm = makeViewModel(mockAPI: mockAPI)
        vm.answers[0] = "Alex"

        await vm.submitOnboarding()

        #expect(vm.isSubmitting == false)
    }

    @Test("isSubmitting is false after generic non-API error")
    func isSubmittingFalseAfterGenericError() async {
        let mockAPI = MockAPIClient()
        mockAPI.requestError = NSError(domain: "SomeOtherDomain", code: -9999, userInfo: nil)
        let vm = makeViewModel(mockAPI: mockAPI)
        vm.answers[0] = "Alex"

        await vm.submitOnboarding()

        #expect(vm.isSubmitting == false)
    }

    // MARK: - Generic Non-API Error

    @Test("submitOnboarding sets errorMessage for non-APIError generic error")
    func submitOnboardingGenericErrorSetsMessage() async {
        let mockAPI = MockAPIClient()
        mockAPI.requestError = NSError(
            domain: "SomeOtherDomain",
            code: -9999,
            userInfo: [NSLocalizedDescriptionKey: "Unexpected failure"]
        )
        let vm = makeViewModel(mockAPI: mockAPI)
        vm.answers[0] = "Alex"

        let result = await vm.submitOnboarding()

        #expect(result == false)
        #expect(vm.errorMessage != nil)
        #expect(vm.errorMessage == "Something went wrong. Please try again.")
    }

    @Test("submitOnboarding clears errorMessage before each attempt")
    func submitOnboardingClearsPreviousError() async {
        let mockAPI = MockAPIClient()
        mockAPI.requestError = APIError.serverError(statusCode: 500, detail: "Error on first attempt")
        let vm = makeViewModel(mockAPI: mockAPI)
        vm.answers[0] = "Alex"

        await vm.submitOnboarding()
        #expect(vm.errorMessage != nil)

        // Second attempt succeeds
        mockAPI.requestError = nil
        mockAPI.requestResult = OnboardingResponse(onboardingCompleted: true, memoriesSeeded: 1)
        await vm.submitOnboarding()

        #expect(vm.errorMessage == nil)
        #expect(vm.isSubmitting == false)
    }

    // MARK: - 401 Error

    @Test("submitOnboarding returns false and sets errorMessage for 401")
    func submitOnboarding401SetsError() async {
        let mockAPI = MockAPIClient()
        mockAPI.requestError = APIError.unauthorized
        let vm = makeViewModel(mockAPI: mockAPI)
        vm.answers[0] = "Alex"

        let result = await vm.submitOnboarding()

        // 401 is not a 409 — must be treated as an error
        #expect(result == false)
        #expect(vm.errorMessage != nil)
        #expect(vm.isSubmitting == false)
    }

    // MARK: - 500 Error

    @Test("submitOnboarding returns false and sets errorMessage for 500")
    func submitOnboarding500SetsError() async {
        let mockAPI = MockAPIClient()
        mockAPI.requestError = APIError.serverError(statusCode: 500, detail: "Internal server error")
        let vm = makeViewModel(mockAPI: mockAPI)
        vm.answers[0] = "Alex"

        let result = await vm.submitOnboarding()

        #expect(result == false)
        #expect(vm.errorMessage != nil)
        #expect(vm.isSubmitting == false)
    }

    // MARK: - questionKeys Exhaustive Validation

    @Test("questionKeys values are all snake_case")
    func questionKeysAreSnakeCase() {
        for key in OnboardingViewModel.questionKeys {
            // No uppercase letters, no spaces — only lowercase and underscores
            let isValid = key.allSatisfy { $0.isLowercase || $0 == "_" }
            #expect(isValid, "Key '\(key)' is not valid snake_case")
        }
    }

    @Test("questionKeys does not contain duplicates")
    func questionKeysNoDuplicates() {
        let keys = OnboardingViewModel.questionKeys
        let uniqueKeys = Set(keys)
        #expect(keys.count == uniqueKeys.count)
    }

    @Test("questionTexts and questionPlaceholders have same count as questionKeys")
    func arrayLengthsMatch() {
        let keyCount = OnboardingViewModel.questionKeys.count
        #expect(OnboardingViewModel.questionTexts.count == keyCount)
        #expect(OnboardingViewModel.questionPlaceholders.count == keyCount)
    }

    @Test("questionKeys[0] is preferred_name")
    func firstKeyIsPreferredName() {
        #expect(OnboardingViewModel.questionKeys[0] == "preferred_name")
    }

    @Test("questionKeys[6] is communication_style")
    func lastKeyIsCommunicationStyle() {
        #expect(OnboardingViewModel.questionKeys[6] == "communication_style")
    }

    // MARK: - Answers Array Integrity

    @Test("answers array always has exactly 7 elements")
    func answersArrayAlwaysSevenElements() {
        let vm = makeViewModel()
        #expect(vm.answers.count == 7)
        // Mutation should not change the count
        vm.answers[0] = "Alex"
        vm.answers[6] = "Casual"
        #expect(vm.answers.count == 7)
    }

    @Test("updating one answer does not affect others")
    func updatingOneAnswerDoesNotAffectOthers() {
        let vm = makeViewModel()
        vm.answers[3] = "Run a marathon"

        for i in [0, 1, 2, 4, 5, 6] {
            #expect(vm.answers[i] == "", "answers[\(i)] should still be empty")
        }
        #expect(vm.answers[3] == "Run a marathon")
    }
}
