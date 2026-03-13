import Foundation

/// Retries an async throwing operation with exponential backoff.
///
/// Usage:
/// ```swift
/// let result = try await RetryHelper.withExponentialBackoff {
///     try await apiClient.request(endpoint: .listCharacters, responseType: CharacterListResponse.self)
/// }
/// ```
enum RetryHelper {
    /// Default configuration for retry behavior.
    struct Configuration {
        /// Maximum number of retry attempts (not counting the initial attempt).
        let maxRetries: Int

        /// Base delay between retries (doubles each attempt).
        let baseDelay: TimeInterval

        /// Maximum delay cap.
        let maxDelay: TimeInterval

        /// Whether to add jitter (random variation) to delays.
        let jitter: Bool

        static let `default` = Configuration(
            maxRetries: 3,
            baseDelay: 1.0,
            maxDelay: 16.0,
            jitter: true
        )

        static let aggressive = Configuration(
            maxRetries: 5,
            baseDelay: 0.5,
            maxDelay: 30.0,
            jitter: true
        )

        static let gentle = Configuration(
            maxRetries: 2,
            baseDelay: 2.0,
            maxDelay: 8.0,
            jitter: false
        )
    }

    /// Executes the operation, retrying on failure with exponential backoff.
    ///
    /// Only retries for errors where `EmberError.isRetryable` is `true`.
    /// Non-retryable errors (unauthorized, not found, decoding) throw immediately.
    ///
    /// - Parameters:
    ///   - configuration: Retry timing configuration.
    ///   - operation: The async throwing closure to execute.
    /// - Returns: The result of a successful operation.
    /// - Throws: The last error if all retries are exhausted, or immediately for non-retryable errors.
    static func withExponentialBackoff<T>(
        configuration: Configuration = .default,
        operation: () async throws -> T
    ) async throws -> T {
        var lastError: Error?
        var attempt = 0

        while attempt <= configuration.maxRetries {
            do {
                return try await operation()
            } catch {
                lastError = error

                let emberError = EmberError.from(error)

                // Non-retryable errors throw immediately
                guard emberError.isRetryable else {
                    throw error
                }

                // Exhausted retries
                if attempt == configuration.maxRetries {
                    break
                }

                // Calculate delay with exponential backoff
                let delay = calculateDelay(
                    attempt: attempt,
                    baseDelay: configuration.baseDelay,
                    maxDelay: configuration.maxDelay,
                    jitter: configuration.jitter
                )

                try await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
                attempt += 1
            }
        }

        throw lastError ?? EmberError.unknown("Retry failed")
    }

    // MARK: - Private

    private static func calculateDelay(
        attempt: Int,
        baseDelay: TimeInterval,
        maxDelay: TimeInterval,
        jitter: Bool
    ) -> TimeInterval {
        // Exponential: baseDelay * 2^attempt
        let exponentialDelay = baseDelay * pow(2.0, Double(attempt))
        let cappedDelay = min(exponentialDelay, maxDelay)

        if jitter {
            // Add random jitter: 50% to 100% of the calculated delay
            let jitterFraction = Double.random(in: 0.5...1.0)
            return cappedDelay * jitterFraction
        }

        return cappedDelay
    }
}
