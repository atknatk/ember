import Testing
@testable import Ember

@Suite("OnboardingViewModel")
struct OnboardingViewModelTests {

    // MARK: - Helpers

    private func makeViewModel(mockAPI: MockAPIClient = MockAPIClient()) -> OnboardingViewModel {
        OnboardingViewModel(apiClient: mockAPI)
    }

    // MARK: - Initial State

    @Test("initial state is correct")
    func initialState() {
        let vm = makeViewModel()

        #expect(vm.currentPhase == .welcome)
        #expect(vm.currentWelcomePage == 0)
        #expect(vm.currentQuestionIndex == 0)
        #expect(vm.answers.count == 7)
        #expect(vm.answers.allSatisfy { $0.isEmpty })
        #expect(vm.isSubmitting == false)
        #expect(vm.errorMessage == nil)
    }

    // MARK: - Phase Navigation

    @Test("advanceToQuestions sets phase to questions")
    func advanceToQuestions() {
        let vm = makeViewModel()

        vm.advanceToQuestions()

        #expect(vm.currentPhase == .questions)
    }

    // MARK: - Question Navigation

    @Test("advanceToNextQuestion increments index")
    func advanceToNextQuestionIncrementsIndex() {
        let vm = makeViewModel()
        vm.currentQuestionIndex = 2

        vm.advanceToNextQuestion()

        #expect(vm.currentQuestionIndex == 3)
    }

    @Test("advanceToNextQuestion stops at six")
    func advanceToNextQuestionStopsAtSix() {
        let vm = makeViewModel()
        vm.currentQuestionIndex = 6

        vm.advanceToNextQuestion()

        #expect(vm.currentQuestionIndex == 6)
    }

    @Test("goToPreviousQuestion decrements index")
    func goToPreviousQuestionDecrementsIndex() {
        let vm = makeViewModel()
        vm.currentQuestionIndex = 3

        vm.goToPreviousQuestion()

        #expect(vm.currentQuestionIndex == 2)
    }

    @Test("goToPreviousQuestion stops at zero")
    func goToPreviousQuestionStopsAtZero() {
        let vm = makeViewModel()
        vm.currentQuestionIndex = 0

        vm.goToPreviousQuestion()

        #expect(vm.currentQuestionIndex == 0)
    }

    // MARK: - Skip

    @Test("skipCurrentQuestion clears answer and advances")
    func skipCurrentQuestionClearsAnswerAndAdvances() {
        let vm = makeViewModel()
        vm.answers[2] = "test"
        vm.currentQuestionIndex = 2

        vm.skipCurrentQuestion()

        #expect(vm.answers[2] == "")
        #expect(vm.currentQuestionIndex == 3)
    }

    // MARK: - canSubmit

    @Test("canSubmit is false when all answers are empty")
    func canSubmitFalseWhenAllEmpty() {
        let vm = makeViewModel()

        #expect(vm.canSubmit == false)
    }

    @Test("canSubmit is true when at least one answer is provided")
    func canSubmitTrueWhenOneAnswered() {
        let vm = makeViewModel()
        vm.answers[0] = "Alex"

        #expect(vm.canSubmit == true)
    }

    @Test("canSubmit is false when answers are only whitespace")
    func canSubmitFalseWhenOnlyWhitespace() {
        let vm = makeViewModel()
        vm.answers[0] = "   "

        #expect(vm.canSubmit == false)
    }

    // MARK: - currentAnswerIsEmpty

    @Test("currentAnswerIsEmpty is true for blank answer")
    func currentAnswerIsEmptyTrue() {
        let vm = makeViewModel()
        vm.currentQuestionIndex = 3
        vm.answers[3] = ""

        #expect(vm.currentAnswerIsEmpty == true)
    }

    @Test("currentAnswerIsEmpty is false for non-blank answer")
    func currentAnswerIsEmptyFalse() {
        let vm = makeViewModel()
        vm.currentQuestionIndex = 0
        vm.answers[0] = "Alex"

        #expect(vm.currentAnswerIsEmpty == false)
    }

    // MARK: - progressFraction

    @Test("progressFraction is correct for each index")
    func progressFraction() {
        let vm = makeViewModel()

        vm.currentQuestionIndex = 0
        #expect(vm.progressFraction == 1.0 / 7.0)

        vm.currentQuestionIndex = 6
        #expect(vm.progressFraction == 1.0)
    }

    // MARK: - Submit Success

    @Test("submitOnboarding returns true on success")
    func submitOnboardingSuccess() async {
        let mockAPI = MockAPIClient()
        mockAPI.requestResult = OnboardingResponse(onboardingCompleted: true, memoriesSeeded: 7)
        let vm = makeViewModel(mockAPI: mockAPI)
        vm.answers[0] = "Alex"

        let result = await vm.submitOnboarding()

        #expect(result == true)
        #expect(vm.isSubmitting == false)
        #expect(vm.errorMessage == nil)
        #expect(mockAPI.requestCallCount == 1)
    }

    // MARK: - Submit 409 Treated as Success

    @Test("submitOnboarding treats 409 as success")
    func submitOnboarding409TreatedAsSuccess() async {
        let mockAPI = MockAPIClient()
        mockAPI.requestError = APIError.serverError(statusCode: 409, detail: "Onboarding already completed")
        let vm = makeViewModel(mockAPI: mockAPI)
        vm.answers[0] = "Alex"

        let result = await vm.submitOnboarding()

        #expect(result == true)
        #expect(vm.errorMessage == nil)
        #expect(vm.isSubmitting == false)
    }

    // MARK: - Submit 503 Sets Error

    @Test("submitOnboarding sets error on 503")
    func submitOnboarding503SetsError() async {
        let mockAPI = MockAPIClient()
        mockAPI.requestError = APIError.serverError(statusCode: 503, detail: "Service unavailable")
        let vm = makeViewModel(mockAPI: mockAPI)
        vm.answers[0] = "Alex"

        let result = await vm.submitOnboarding()

        #expect(result == false)
        #expect(vm.errorMessage != nil)
        #expect(vm.isSubmitting == false)
    }

    // MARK: - Submit Network Error

    @Test("submitOnboarding sets error on network failure")
    func submitOnboardingNetworkErrorSetsError() async {
        let mockAPI = MockAPIClient()
        mockAPI.requestError = APIError.networkError(
            NSError(domain: "NSURLErrorDomain", code: -1009, userInfo: nil)
        )
        let vm = makeViewModel(mockAPI: mockAPI)
        vm.answers[0] = "Alex"

        let result = await vm.submitOnboarding()

        #expect(result == false)
        #expect(vm.errorMessage != nil)
        #expect(vm.isSubmitting == false)
    }

    // MARK: - Question Keys

    @Test("questionKeys has 7 entries matching backend")
    func questionKeysCount() {
        #expect(OnboardingViewModel.questionKeys.count == 7)
        #expect(OnboardingViewModel.questionTexts.count == 7)
        #expect(OnboardingViewModel.questionPlaceholders.count == 7)
    }

    @Test("questionKeys match backend valid keys")
    func questionKeysMatchBackend() {
        let expectedKeys = [
            "preferred_name",
            "occupation",
            "daily_rhythm",
            "health_goal",
            "stress_management",
            "sleep_schedule",
            "communication_style",
        ]
        #expect(OnboardingViewModel.questionKeys == expectedKeys)
    }
}
