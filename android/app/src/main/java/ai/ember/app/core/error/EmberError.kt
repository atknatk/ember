package ai.ember.app.core.error

import retrofit2.Response
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import javax.net.ssl.SSLException

/**
 * Centralized error type for all Ember Android screens.
 *
 * Maps raw exceptions and HTTP status codes into user-friendly error
 * categories with retry semantics and reauth detection.
 *
 * Mirrors iOS EmberError enum behavior and design.
 */
sealed class EmberError(
    val userMessage: String,
    val isRetryable: Boolean,
    val requiresReauth: Boolean = false,
) {

    /** Device has no internet connectivity. */
    data object Offline : EmberError(
        userMessage = "You appear to be offline. Check your connection and try again.",
        isRetryable = true,
    )

    /** Network request failed (DNS, SSL, connection reset). */
    data class NetworkError(val cause: Throwable? = null) : EmberError(
        userMessage = "Connection failed. Please check your internet.",
        isRetryable = true,
    )

    /** Server returned 5xx. */
    data class ServerError(val statusCode: Int = 500, val detail: String? = null) : EmberError(
        userMessage = "Something went wrong on our end. Please try again.",
        isRetryable = true,
    )

    /** 401 — access token expired or invalid. */
    data object Unauthorized : EmberError(
        userMessage = "Session expired. Please sign in again.",
        isRetryable = false,
        requiresReauth = true,
    )

    /** 404 — resource not found. */
    data class NotFound(val resource: String = "") : EmberError(
        userMessage = if (resource.isNotEmpty()) "$resource not found." else "Not found.",
        isRetryable = false,
    )

    /** 429 — too many requests. */
    data object RateLimited : EmberError(
        userMessage = "Too many requests. Please wait a moment and try again.",
        isRetryable = true,
    )

    /** Request timed out. */
    data object Timeout : EmberError(
        userMessage = "Request timed out. Please try again.",
        isRetryable = true,
    )

    /** Catch-all for unexpected errors. */
    data class Unknown(val cause: Throwable? = null) : EmberError(
        userMessage = "Something went wrong. Please try again.",
        isRetryable = true,
    )

    companion object {

        /**
         * Maps any [Throwable] to an [EmberError].
         *
         * Checks the exception type hierarchy to produce the most
         * specific error category possible.
         */
        fun from(error: Throwable): EmberError {
            return when (error) {
                is EmberErrorException -> error.emberError
                is UnknownHostException -> Offline
                is SocketTimeoutException -> Timeout
                is SSLException -> NetworkError(error)
                is java.net.ConnectException -> NetworkError(error)
                is java.io.IOException -> NetworkError(error)
                else -> Unknown(error)
            }
        }

        /**
         * Maps an HTTP response status code to an [EmberError].
         *
         * @param statusCode HTTP status code from the response.
         * @param detail Optional detail string from API error body.
         * @param resource Optional resource name for 404 messages.
         */
        fun fromHttpStatus(
            statusCode: Int,
            detail: String? = null,
            resource: String = "",
        ): EmberError {
            return when (statusCode) {
                HTTP_UNAUTHORIZED -> Unauthorized
                HTTP_NOT_FOUND -> NotFound(resource)
                HTTP_TOO_MANY_REQUESTS -> RateLimited
                HTTP_REQUEST_TIMEOUT -> Timeout
                in HTTP_SERVER_ERROR_RANGE -> ServerError(statusCode, detail)
                else -> Unknown()
            }
        }

        /**
         * Maps a Retrofit [Response] to an [EmberError].
         *
         * Should only be called when `response.isSuccessful` is false.
         */
        fun <T> fromResponse(response: Response<T>, resource: String = ""): EmberError {
            return fromHttpStatus(
                statusCode = response.code(),
                detail = null,
                resource = resource,
            )
        }

        private const val HTTP_UNAUTHORIZED = 401
        private const val HTTP_NOT_FOUND = 404
        private const val HTTP_REQUEST_TIMEOUT = 408
        private const val HTTP_TOO_MANY_REQUESTS = 429
        private val HTTP_SERVER_ERROR_RANGE = 500..599
    }
}

/**
 * Exception wrapper for [EmberError] to propagate typed errors through
 * standard Kotlin error channels (Result, Flow catch, etc.).
 */
class EmberErrorException(
    val emberError: EmberError,
) : Exception(emberError.userMessage)
