import Foundation

/// Request body for `POST /api/v1/stt`.
struct STTRequest: Encodable {
    let audioUrl: String
}

/// Response from `POST /api/v1/stt`.
struct STTResponse: Codable {
    let transcript: String
    let language: String
    let confidence: Double
}
