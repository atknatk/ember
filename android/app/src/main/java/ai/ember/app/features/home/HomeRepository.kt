package ai.ember.app.features.home

import ai.ember.app.core.models.ApiErrorBody
import ai.ember.app.core.models.Character
import ai.ember.app.core.models.MessagePreview
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.serialization.json.Json
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Repository handling character and message loading for the Home screen.
 *
 * Converts Retrofit responses into [Result] following the same
 * pattern as [AuthRepository] and [OnboardingRepository].
 */
@Singleton
class HomeRepository @Inject constructor(
    private val characterApi: CharacterApi,
    private val json: Json,
) {

    /**
     * Fetches all active characters for the current user.
     *
     * @return list of characters on success, or a descriptive error.
     */
    suspend fun getCharacters(): Result<List<Character>> {
        return try {
            val response = characterApi.listCharacters()
            if (response.isSuccessful) {
                val body = response.body()
                if (body != null) {
                    Result.success(body.characters)
                } else {
                    Result.failure(HomeException("Something went wrong. Please try again."))
                }
            } else {
                val errorMessage = parseErrorMessage(
                    response.errorBody()?.string(),
                    response.code(),
                )
                Result.failure(HomeException(errorMessage))
            }
        } catch (e: HomeException) {
            Result.failure(e)
        } catch (e: Exception) {
            Result.failure(
                HomeException("Connection failed. Please check your internet."),
            )
        }
    }

    /**
     * Fetches the most recent message for each character in parallel.
     *
     * Returns a map of character ID to their last message preview.
     * Failures for individual characters are silently ignored.
     */
    suspend fun getLastMessages(
        characterIds: List<String>,
    ): Map<String, MessagePreview> = coroutineScope {
        characterIds.map { characterId ->
            async {
                try {
                    val response = characterApi.listMessages(
                        characterId = characterId,
                        cursor = null,
                        limit = 1,
                    )
                    if (response.isSuccessful) {
                        val firstItem = response.body()?.items?.firstOrNull()
                        if (firstItem != null) characterId to firstItem else null
                    } else {
                        null
                    }
                } catch (e: Exception) {
                    null
                }
            }
        }.awaitAll().filterNotNull().toMap()
    }

    private fun parseErrorMessage(errorBody: String?, statusCode: Int): String {
        val detail = parseDetail(errorBody)
        return when (statusCode) {
            HTTP_UNAUTHORIZED -> "Session expired. Please sign in again."
            HTTP_SERVICE_UNAVAILABLE -> "Service temporarily unavailable. Please try again."
            else -> detail ?: "Something went wrong. Please try again."
        }
    }

    private fun parseDetail(errorBody: String?): String? {
        if (errorBody == null) return null
        return try {
            json.decodeFromString<ApiErrorBody>(errorBody).detail
        } catch (e: Exception) {
            null
        }
    }

    companion object {
        private const val HTTP_UNAUTHORIZED = 401
        private const val HTTP_SERVICE_UNAVAILABLE = 503
    }
}

/** Exception type for home screen errors with user-facing messages. */
class HomeException(message: String) : Exception(message)
