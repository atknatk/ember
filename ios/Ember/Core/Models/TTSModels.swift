import Foundation

/// Request body for `POST /api/v1/tts`.
struct TTSRequest: Encodable {
    let text: String
    let characterId: String
}

/// Response from `POST /api/v1/tts`.
struct TTSResponse: Decodable {
    let audioUrl: String
    let durationSeconds: Double?
}
