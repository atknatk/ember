import Foundation

/// Typed SSE event enum matching the backend's five event types.
/// Uses `payloadJSON: Data` instead of `[String: Any]` for `Sendable` conformance.
enum SSEEvent: Sendable {
    case chunk(content: String)
    case action(action: String, payloadJSON: Data)
    case done(messageId: String)
    case error(message: String)
    case moderation(message: String)

    /// Convenience method to decode the action payload as a dictionary.
    func actionPayload() -> [String: Any]? {
        guard case .action(_, let data) = self else { return nil }
        return try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    }
}

/// Internal Decodable struct for initial SSE JSON type discrimination.
/// The `messageId` property maps from `message_id` via `JSONDecoder.ember`'s
/// `.convertFromSnakeCase` strategy.
private struct SSEPayload: Decodable {
    let type: String
    let content: String?
    let action: String?
    let payload: [String: AnyCodableValue]?
    let messageId: String?
    let message: String?
}

/// A type-erased Codable wrapper for arbitrary JSON values in SSE action payloads.
private enum AnyCodableValue: Decodable {
    case string(String)
    case int(Int)
    case double(Double)
    case bool(Bool)
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode(Int.self) {
            self = .int(value)
        } else if let value = try? container.decode(Double.self) {
            self = .double(value)
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if container.decodeNil() {
            self = .null
        } else {
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unsupported JSON value")
        }
    }
}

/// URLSession delegate that receives SSE data chunks and parses them into `SSEEvent` values.
/// NOT `Sendable` -- confined to the URLSession delegate queue.
final class SSEDelegate: NSObject, URLSessionDataDelegate {
    private let continuation: AsyncThrowingStream<SSEEvent, Error>.Continuation
    private var buffer = ""
    private let decoder = JSONDecoder.ember

    init(continuation: AsyncThrowingStream<SSEEvent, Error>.Continuation) {
        self.continuation = continuation
    }

    func urlSession(
        _ session: URLSession,
        dataTask: URLSessionDataTask,
        didReceive response: URLResponse,
        completionHandler: @escaping (URLSession.ResponseDisposition) -> Void
    ) {
        if let httpResponse = response as? HTTPURLResponse,
           !(200...299).contains(httpResponse.statusCode) {
            continuation.yield(.error(message: "HTTP \(httpResponse.statusCode)"))
            continuation.finish()
            completionHandler(.cancel)
            return
        }
        completionHandler(.allow)
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        guard let text = String(data: data, encoding: .utf8) else { return }
        buffer += text

        while let range = buffer.range(of: "\n\n") {
            let event = String(buffer[buffer.startIndex..<range.lowerBound])
            buffer.removeSubrange(buffer.startIndex..<range.upperBound)

            // Process each line in the event block
            for line in event.components(separatedBy: "\n") {
                guard line.hasPrefix("data: ") else { continue }
                let jsonString = String(line.dropFirst(6))

                // Skip empty data lines (keep-alive)
                guard !jsonString.trimmingCharacters(in: .whitespaces).isEmpty else { continue }

                // Check for [DONE] sentinel
                if jsonString == "[DONE]" {
                    continuation.finish()
                    return
                }

                guard let jsonData = jsonString.data(using: .utf8) else { continue }

                guard let payload = try? decoder.decode(SSEPayload.self, from: jsonData) else { continue }

                let sseEvent = mapPayloadToEvent(payload, rawJSON: jsonData)
                if let sseEvent {
                    continuation.yield(sseEvent)
                }
            }
        }
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        if let error {
            // Ignore cancellation errors (user-initiated stream termination)
            if (error as NSError).code == NSURLErrorCancelled {
                continuation.finish()
            } else {
                continuation.finish(throwing: APIError.networkError(error))
            }
        } else {
            continuation.finish()
        }
    }

    // MARK: - Private

    private func mapPayloadToEvent(_ payload: SSEPayload, rawJSON: Data) -> SSEEvent? {
        switch payload.type {
        case "chunk":
            guard let content = payload.content else { return nil }
            return .chunk(content: content)

        case "action":
            guard let action = payload.action else { return nil }
            // Re-serialize the payload dictionary to Data for Sendable safety
            let payloadData: Data
            if let payloadDict = payload.payload {
                // Convert AnyCodableValue dictionary to regular dictionary for serialization
                var dict: [String: Any] = [:]
                for (key, value) in payloadDict {
                    switch value {
                    case .string(let s): dict[key] = s
                    case .int(let i): dict[key] = i
                    case .double(let d): dict[key] = d
                    case .bool(let b): dict[key] = b
                    case .null: dict[key] = NSNull()
                    }
                }
                payloadData = (try? JSONSerialization.data(withJSONObject: dict)) ?? Data()
            } else {
                payloadData = Data()
            }
            return .action(action: action, payloadJSON: payloadData)

        case "done":
            guard let messageId = payload.messageId else { return nil }
            return .done(messageId: messageId)

        case "error":
            return .error(message: payload.message ?? "Unknown error")

        case "moderation":
            return .moderation(message: payload.message ?? "Content moderated")

        default:
            return nil
        }
    }
}
