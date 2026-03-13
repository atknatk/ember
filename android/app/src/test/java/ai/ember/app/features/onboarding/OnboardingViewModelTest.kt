package ai.ember.app.features.onboarding

import app.cash.turbine.test
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Before
import org.junit.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertTrue

@OptIn(ExperimentalCoroutinesApi::class)
class OnboardingViewModelTest {

    private val testDispatcher = UnconfinedTestDispatcher()
    private lateinit var onboardingRepository: OnboardingRepository
    private lateinit var viewModel: OnboardingViewModel

    @Before
    fun setUp() {
        Dispatchers.setMain(testDispatcher)
        onboardingRepository = mockk()
        viewModel = OnboardingViewModel(onboardingRepository)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    // -- Initial State --

    @Test
    fun `initial state is Welcome with page 0`() = runTest {
        viewModel.uiState.test {
            val state = awaitItem()
            assertIs<OnboardingUiState.Welcome>(state)
            assertEquals(0, state.currentPage)
            cancelAndIgnoreRemainingEvents()
        }
    }

    // -- Welcome Phase --

    @Test
    fun `nextWelcomePage increments page`() = runTest {
        viewModel.nextWelcomePage()
        val state = viewModel.uiState.value
        assertIs<OnboardingUiState.Welcome>(state)
        assertEquals(1, state.currentPage)
    }

    @Test
    fun `nextWelcomePage stops at last page`() = runTest {
        viewModel.setWelcomePage(2)
        viewModel.nextWelcomePage()
        val state = viewModel.uiState.value
        assertIs<OnboardingUiState.Welcome>(state)
        assertEquals(2, state.currentPage)
    }

    @Test
    fun `setWelcomePage sets page directly`() = runTest {
        viewModel.setWelcomePage(2)
        val state = viewModel.uiState.value
        assertIs<OnboardingUiState.Welcome>(state)
        assertEquals(2, state.currentPage)
    }

    @Test
    fun `setWelcomePage clamps to valid range`() = runTest {
        viewModel.setWelcomePage(10)
        val state = viewModel.uiState.value
        assertIs<OnboardingUiState.Welcome>(state)
        assertEquals(2, state.currentPage)
    }

    @Test
    fun `skipToLastWelcomePage sets page to last`() = runTest {
        viewModel.skipToLastWelcomePage()
        val state = viewModel.uiState.value
        assertIs<OnboardingUiState.Welcome>(state)
        assertEquals(2, state.currentPage)
    }

    @Test
    fun `advanceToQuestions transitions to Questions phase`() = runTest {
        viewModel.advanceToQuestions()
        val state = viewModel.uiState.value
        assertIs<OnboardingUiState.Questions>(state)
        assertEquals(0, state.currentIndex)
        assertEquals(7, state.answers.size)
        assertTrue(state.answers.all { it.isEmpty() })
    }

    // -- Questions Phase --

    @Test
    fun `onAnswerChanged updates answer for current question`() = runTest {
        viewModel.advanceToQuestions()
        viewModel.onAnswerChanged("Alex")
        val state = viewModel.uiState.value
        assertIs<OnboardingUiState.Questions>(state)
        assertEquals("Alex", state.answers[0])
    }

    @Test
    fun `nextQuestion increments index`() = runTest {
        viewModel.advanceToQuestions()
        viewModel.nextQuestion()
        val state = viewModel.uiState.value
        assertIs<OnboardingUiState.Questions>(state)
        assertEquals(1, state.currentIndex)
    }

    @Test
    fun `nextQuestion stops at last question`() = runTest {
        viewModel.advanceToQuestions()
        repeat(10) { viewModel.nextQuestion() }
        val state = viewModel.uiState.value
        assertIs<OnboardingUiState.Questions>(state)
        assertEquals(6, state.currentIndex)
    }

    @Test
    fun `previousQuestion decrements index`() = runTest {
        viewModel.advanceToQuestions()
        viewModel.nextQuestion()
        viewModel.nextQuestion()
        viewModel.previousQuestion()
        val state = viewModel.uiState.value
        assertIs<OnboardingUiState.Questions>(state)
        assertEquals(1, state.currentIndex)
    }

    @Test
    fun `previousQuestion stops at zero`() = runTest {
        viewModel.advanceToQuestions()
        viewModel.previousQuestion()
        val state = viewModel.uiState.value
        assertIs<OnboardingUiState.Questions>(state)
        assertEquals(0, state.currentIndex)
    }

    @Test
    fun `skipCurrentQuestion clears answer and advances`() = runTest {
        viewModel.advanceToQuestions()
        viewModel.onAnswerChanged("test")
        viewModel.skipCurrentQuestion()
        val state = viewModel.uiState.value
        assertIs<OnboardingUiState.Questions>(state)
        assertEquals("", state.answers[0])
        assertEquals(1, state.currentIndex)
    }

    @Test
    fun `answers are preserved when navigating between questions`() = runTest {
        viewModel.advanceToQuestions()
        viewModel.onAnswerChanged("Alex")
        viewModel.nextQuestion()
        viewModel.onAnswerChanged("Engineer")
        viewModel.previousQuestion()
        val state = viewModel.uiState.value
        assertIs<OnboardingUiState.Questions>(state)
        assertEquals("Alex", state.answers[0])
        assertEquals("Engineer", state.answers[1])
    }

    // -- Can Submit --

    @Test
    fun `canSubmit returns false when all answers empty`() = runTest {
        viewModel.advanceToQuestions()
        assertFalse(viewModel.canSubmit())
    }

    @Test
    fun `canSubmit returns true when at least one answer provided`() = runTest {
        viewModel.advanceToQuestions()
        viewModel.onAnswerChanged("Alex")
        assertTrue(viewModel.canSubmit())
    }

    @Test
    fun `canSubmit returns false when answer is only whitespace`() = runTest {
        viewModel.advanceToQuestions()
        viewModel.onAnswerChanged("   ")
        assertFalse(viewModel.canSubmit())
    }

    // -- Submission --

    @Test
    fun `submitOnboarding emits Completed on success`() = runTest {
        val response = OnboardingResponse(onboardingCompleted = true, memoriesSeeded = 7)
        coEvery { onboardingRepository.completeOnboarding(any()) } returns Result.success(response)

        viewModel.advanceToQuestions()
        viewModel.onAnswerChanged("Alex")

        viewModel.uiState.test {
            awaitItem() // Questions state
            viewModel.submitOnboarding()
            // May get submitting state
            val items = cancelAndConsumeRemainingEvents()
            val lastItem = items.filterIsInstance<app.cash.turbine.Event.Item<OnboardingUiState>>()
                .lastOrNull()?.value
            assertIs<OnboardingUiState.Completed>(lastItem)
        }
    }

    @Test
    fun `submitOnboarding emits Error on failure`() = runTest {
        coEvery { onboardingRepository.completeOnboarding(any()) } returns
            Result.failure(OnboardingException("Service unavailable"))

        viewModel.advanceToQuestions()
        viewModel.onAnswerChanged("Alex")

        viewModel.uiState.test {
            awaitItem() // Questions state
            viewModel.submitOnboarding()
            val items = cancelAndConsumeRemainingEvents()
            val lastItem = items.filterIsInstance<app.cash.turbine.Event.Item<OnboardingUiState>>()
                .lastOrNull()?.value
            assertIs<OnboardingUiState.Error>(lastItem)
            assertEquals("Service unavailable", lastItem.message)
        }
    }

    @Test
    fun `submitOnboarding sets isSubmitting true during call`() = runTest {
        coEvery { onboardingRepository.completeOnboarding(any()) } returns
            Result.success(OnboardingResponse(onboardingCompleted = true, memoriesSeeded = 7))

        viewModel.advanceToQuestions()
        viewModel.onAnswerChanged("Alex")

        viewModel.uiState.test {
            awaitItem() // Questions
            viewModel.submitOnboarding()
            // The submitting state may be emitted
            val events = cancelAndConsumeRemainingEvents()
            val submittingEvent = events
                .filterIsInstance<app.cash.turbine.Event.Item<OnboardingUiState>>()
                .map { it.value }
                .filterIsInstance<OnboardingUiState.Questions>()
                .firstOrNull { it.isSubmitting }
            // Verify submission happened
            assertIs<OnboardingUiState.Questions>(submittingEvent)
            assertTrue(submittingEvent.isSubmitting)
        }
    }

    @Test
    fun `submitOnboarding sends Not provided for skipped questions`() = runTest {
        coEvery { onboardingRepository.completeOnboarding(any()) } returns
            Result.success(OnboardingResponse(onboardingCompleted = true, memoriesSeeded = 7))

        viewModel.advanceToQuestions()
        viewModel.onAnswerChanged("Alex") // Only answer question 0
        viewModel.submitOnboarding()

        coVerify {
            onboardingRepository.completeOnboarding(
                match { answers ->
                    answers[0].answer == "Alex" &&
                        answers[1].answer == "Not provided" &&
                        answers.size == 7 &&
                        answers.drop(1).all { it.answer == "Not provided" }
                },
            )
        }
    }

    @Test
    fun `submitOnboarding sends correct question keys`() = runTest {
        coEvery { onboardingRepository.completeOnboarding(any()) } returns
            Result.success(OnboardingResponse(onboardingCompleted = true, memoriesSeeded = 7))

        viewModel.advanceToQuestions()
        viewModel.onAnswerChanged("Alex")
        viewModel.submitOnboarding()

        coVerify {
            onboardingRepository.completeOnboarding(
                match { answers ->
                    answers.map { it.questionKey } == OnboardingViewModel.QUESTION_KEYS
                },
            )
        }
    }

    @Test
    fun `submitOnboarding does nothing when all answers empty`() = runTest {
        viewModel.advanceToQuestions()
        viewModel.submitOnboarding()
        val state = viewModel.uiState.value
        assertIs<OnboardingUiState.Questions>(state)
        assertFalse(state.isSubmitting)
    }

    // -- Error Handling --

    @Test
    fun `dismissError returns to Questions phase with preserved answers`() = runTest {
        coEvery { onboardingRepository.completeOnboarding(any()) } returns
            Result.failure(OnboardingException("Error"))

        viewModel.advanceToQuestions()
        viewModel.onAnswerChanged("Alex")
        viewModel.submitOnboarding()

        // Should be in error state now
        assertIs<OnboardingUiState.Error>(viewModel.uiState.value)

        viewModel.dismissError()
        val state = viewModel.uiState.value
        assertIs<OnboardingUiState.Questions>(state)
        assertEquals("Alex", state.answers[0])
    }

    @Test
    fun `error state preserves current question index`() = runTest {
        coEvery { onboardingRepository.completeOnboarding(any()) } returns
            Result.failure(OnboardingException("Error"))

        viewModel.advanceToQuestions()
        viewModel.onAnswerChanged("Alex")
        // Navigate to question 3
        viewModel.nextQuestion()
        viewModel.nextQuestion()
        viewModel.nextQuestion()
        // Go to last question for submit
        repeat(3) { viewModel.nextQuestion() }
        viewModel.submitOnboarding()

        val errorState = viewModel.uiState.value
        assertIs<OnboardingUiState.Error>(errorState)
        assertEquals(6, errorState.currentIndex)
    }

    // -- Skip on Last Question --

    @Test
    fun `skipCurrentQuestion on last question triggers submit`() = runTest {
        coEvery { onboardingRepository.completeOnboarding(any()) } returns
            Result.success(OnboardingResponse(onboardingCompleted = true, memoriesSeeded = 7))

        viewModel.advanceToQuestions()
        viewModel.onAnswerChanged("Alex")
        // Navigate to last question
        repeat(6) { viewModel.nextQuestion() }
        viewModel.skipCurrentQuestion()

        // Should attempt submission (answer[0] = "Alex" is non-empty)
        coVerify { onboardingRepository.completeOnboarding(any()) }
    }
}
