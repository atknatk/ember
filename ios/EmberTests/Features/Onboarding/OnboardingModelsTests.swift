import Testing
import Foundation
@testable import Ember

/// Unit tests for `OnboardingAnswer`, `OnboardingRequest`, and `OnboardingResponse`.
/// Verifies that JSON encoding produces snake_case keys (required by the backend) and
/// that JSON decoding with snake_case keys round-trips correctly.
@Suite("OnboardingModels")
struct OnboardingModelsTests {

    // MARK: - Helpers

    private var encoder: JSONEncoder { JSONEncoder.ember }
    private var decoder: JSONDecoder { JSONDecoder.ember }

    // MARK: - OnboardingAnswer Encoding

    @Test("OnboardingAnswer encodes questionKey as question_key")
    func onboardingAnswerEncodesQuestionKey() throws {
        let answer = OnboardingAnswer(questionKey: "preferred_name", answer: "Alex")

        let data = try encoder.encode(answer)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: String]

        #expect(json?["question_key"] == "preferred_name")
        #expect(json?["answer"] == "Alex")
        // camelCase key must NOT appear in the encoded output
        #expect(json?["questionKey"] == nil)
    }

    @Test("OnboardingAnswer encodes answer value verbatim")
    func onboardingAnswerEncodesAnswerVerbatim() throws {
        let answer = OnboardingAnswer(questionKey: "occupation", answer: "Software engineer")

        let data = try encoder.encode(answer)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: String]

        #expect(json?["answer"] == "Software engineer")
    }

    @Test("OnboardingAnswer encodes Not provided fallback")
    func onboardingAnswerEncodesNotProvided() throws {
        let answer = OnboardingAnswer(questionKey: "daily_rhythm", answer: "Not provided")

        let data = try encoder.encode(answer)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: String]

        #expect(json?["answer"] == "Not provided")
    }

    // MARK: - OnboardingAnswer Decoding

    @Test("OnboardingAnswer decodes question_key to questionKey property")
    func onboardingAnswerDecodesQuestionKey() throws {
        let jsonString = """
        {"question_key": "sleep_schedule", "answer": "11pm to 7am"}
        """
        let data = Data(jsonString.utf8)

        let answer = try decoder.decode(OnboardingAnswer.self, from: data)

        #expect(answer.questionKey == "sleep_schedule")
        #expect(answer.answer == "11pm to 7am")
    }

    @Test("OnboardingAnswer round-trips through encode then decode")
    func onboardingAnswerRoundTrip() throws {
        let original = OnboardingAnswer(questionKey: "health_goal", answer: "Run a marathon")

        let data = try encoder.encode(original)
        let decoded = try decoder.decode(OnboardingAnswer.self, from: data)

        #expect(decoded.questionKey == original.questionKey)
        #expect(decoded.answer == original.answer)
    }

    // MARK: - OnboardingRequest Encoding

    @Test("OnboardingRequest encodes answers array with snake_case keys")
    func onboardingRequestEncoding() throws {
        let answers = [
            OnboardingAnswer(questionKey: "preferred_name", answer: "Alex"),
            OnboardingAnswer(questionKey: "occupation", answer: "Engineer"),
        ]
        let request = OnboardingRequest(answers: answers)

        let data = try encoder.encode(request)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        let answersArray = json?["answers"] as? [[String: String]]

        #expect(answersArray?.count == 2)
        #expect(answersArray?[0]["question_key"] == "preferred_name")
        #expect(answersArray?[0]["answer"] == "Alex")
        #expect(answersArray?[1]["question_key"] == "occupation")
        #expect(answersArray?[1]["answer"] == "Engineer")
    }

    @Test("OnboardingRequest encodes all 7 answers when built from questionKeys")
    func onboardingRequestSevenAnswers() throws {
        let answersArray = OnboardingViewModel.questionKeys.map { key in
            OnboardingAnswer(questionKey: key, answer: "Not provided")
        }
        let request = OnboardingRequest(answers: answersArray)

        let data = try encoder.encode(request)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        let encodedAnswers = json?["answers"] as? [[String: String]]

        #expect(encodedAnswers?.count == 7)
    }

    @Test("OnboardingRequest encodes empty answers array")
    func onboardingRequestEmptyAnswers() throws {
        let request = OnboardingRequest(answers: [])

        let data = try encoder.encode(request)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        let encodedAnswers = json?["answers"] as? [[String: String]]

        #expect(encodedAnswers?.count == 0)
    }

    @Test("OnboardingRequest round-trips through encode then decode")
    func onboardingRequestRoundTrip() throws {
        let answers = OnboardingViewModel.questionKeys.enumerated().map { index, key in
            OnboardingAnswer(questionKey: key, answer: "Answer \(index)")
        }
        let original = OnboardingRequest(answers: answers)

        let data = try encoder.encode(original)
        let decoded = try decoder.decode(OnboardingRequest.self, from: data)

        #expect(decoded.answers.count == original.answers.count)
        for (i, answer) in decoded.answers.enumerated() {
            #expect(answer.questionKey == original.answers[i].questionKey)
            #expect(answer.answer == original.answers[i].answer)
        }
    }

    // MARK: - OnboardingResponse Decoding

    @Test("OnboardingResponse decodes onboarding_completed as onboardingCompleted")
    func onboardingResponseDecodesOnboardingCompleted() throws {
        let jsonString = """
        {"onboarding_completed": true, "memories_seeded": 7}
        """
        let data = Data(jsonString.utf8)

        let response = try decoder.decode(OnboardingResponse.self, from: data)

        #expect(response.onboardingCompleted == true)
        #expect(response.memoriesSeeded == 7)
    }

    @Test("OnboardingResponse decodes when memories_seeded is zero")
    func onboardingResponseZeroMemories() throws {
        let jsonString = """
        {"onboarding_completed": true, "memories_seeded": 0}
        """
        let data = Data(jsonString.utf8)

        let response = try decoder.decode(OnboardingResponse.self, from: data)

        #expect(response.memoriesSeeded == 0)
        #expect(response.onboardingCompleted == true)
    }

    @Test("OnboardingResponse decodes when onboarding_completed is false")
    func onboardingResponseCompletedFalse() throws {
        let jsonString = """
        {"onboarding_completed": false, "memories_seeded": 0}
        """
        let data = Data(jsonString.utf8)

        let response = try decoder.decode(OnboardingResponse.self, from: data)

        #expect(response.onboardingCompleted == false)
    }

    @Test("OnboardingResponse round-trips through encode then decode")
    func onboardingResponseRoundTrip() throws {
        let original = OnboardingResponse(onboardingCompleted: true, memoriesSeeded: 5)

        let data = try encoder.encode(original)
        let decoded = try decoder.decode(OnboardingResponse.self, from: data)

        #expect(decoded.onboardingCompleted == original.onboardingCompleted)
        #expect(decoded.memoriesSeeded == original.memoriesSeeded)
    }

    @Test("OnboardingResponse encoding uses snake_case keys")
    func onboardingResponseEncodingUsesSnakeCase() throws {
        let response = OnboardingResponse(onboardingCompleted: true, memoriesSeeded: 3)

        let data = try encoder.encode(response)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]

        #expect(json?["onboarding_completed"] as? Bool == true)
        #expect(json?["memories_seeded"] as? Int == 3)
        // camelCase keys must NOT appear
        #expect(json?["onboardingCompleted"] == nil)
        #expect(json?["memoriesSeeded"] == nil)
    }

    // MARK: - Backend Key Contract

    @Test("OnboardingAnswer question_key matches backend VALID_QUESTION_KEYS format")
    func backendKeyContract() throws {
        // Verify all 7 question keys can be encoded and the JSON key name is question_key
        for key in OnboardingViewModel.questionKeys {
            let answer = OnboardingAnswer(questionKey: key, answer: "Test")
            let data = try encoder.encode(answer)
            let json = try JSONSerialization.jsonObject(with: data) as? [String: String]
            #expect(json?["question_key"] == key, "Key '\(key)' did not survive encode/decode as 'question_key'")
        }
    }
}
