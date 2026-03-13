package ai.ember.app.core.error

import kotlinx.coroutines.delay
import kotlin.math.min
import kotlin.random.Random

/**
 * Exponential backoff retry utility for transient errors.
 *
 * Only retries operations that fail with [EmberError.isRetryable] errors.
 * Non-retryable errors are thrown immediately without consuming attempts.
 *
 * Mirrors iOS RetryHelper behavior.
 */
object RetryHelper {

    /**
     * Executes [action] with exponential backoff retry logic.
     *
     * @param maxAttempts Maximum number of attempts (including initial).
     * @param baseDelayMs Base delay in milliseconds for exponential backoff.
     * @param maxDelayMs Maximum delay cap in milliseconds.
     * @param jitter Whether to add random jitter to delay.
     * @param action The suspending block to execute and potentially retry.
     * @return The result of [action] on success.
     * @throws EmberErrorException if all retries are exhausted or a non-retryable error occurs.
     */
    suspend fun <T> withRetry(
        maxAttempts: Int = DEFAULT_MAX_ATTEMPTS,
        baseDelayMs: Long = DEFAULT_BASE_DELAY_MS,
        maxDelayMs: Long = DEFAULT_MAX_DELAY_MS,
        jitter: Boolean = true,
        action: suspend () -> T,
    ): T {
        var lastError: EmberError? = null

        repeat(maxAttempts) { attempt ->
            try {
                return action()
            } catch (e: Exception) {
                val emberError = when (e) {
                    is EmberErrorException -> e.emberError
                    else -> EmberError.from(e)
                }

                if (!emberError.isRetryable) {
                    throw EmberErrorException(emberError)
                }

                lastError = emberError

                if (attempt < maxAttempts - 1) {
                    val delayMs = calculateDelay(attempt, baseDelayMs, maxDelayMs, jitter)
                    delay(delayMs)
                }
            }
        }

        throw EmberErrorException(lastError ?: EmberError.Unknown())
    }

    /**
     * Calculates the backoff delay for a given attempt.
     *
     * Uses exponential backoff: base * 2^attempt, capped at maxDelay.
     * Jitter adds random variance between 0 and the calculated delay.
     */
    internal fun calculateDelay(
        attempt: Int,
        baseDelayMs: Long,
        maxDelayMs: Long,
        jitter: Boolean,
    ): Long {
        val exponentialDelay = baseDelayMs * (1L shl attempt)
        val cappedDelay = min(exponentialDelay, maxDelayMs)
        return if (jitter) {
            Random.nextLong(cappedDelay / 2, cappedDelay + 1)
        } else {
            cappedDelay
        }
    }

    private const val DEFAULT_MAX_ATTEMPTS = 3
    private const val DEFAULT_BASE_DELAY_MS = 1000L
    private const val DEFAULT_MAX_DELAY_MS = 10000L
}
