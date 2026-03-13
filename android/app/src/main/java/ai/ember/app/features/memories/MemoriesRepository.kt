package ai.ember.app.features.memories

import ai.ember.app.core.models.ApiErrorBody
import ai.ember.app.core.models.Character
import ai.ember.app.core.models.MemoryItem
import kotlinx.serialization.json.Json
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Repository handling memory and character loading for the Memories screen.
 *
 * Converts Retrofit responses into [Result] following the same
 * pattern as [HomeRepository].
 */
@Singleton
class MemoriesRepository @Inject constructor(
    private val memoryApi: MemoryApi,
    private val json: Json,
) {

    /**
     * Fetches all active characters for the current user.
     */
    suspend fun getCharacters(): Result<List<Character>> {
        return try {
            val response = memoryApi.listCharacters()
            if (response.isSuccessful) {
                val body = response.body()
                if (body != null) {
                    Result.success(body.characters)
                } else {
                    Result.failure(MemoriesException("Something went wrong. Please try again."))
                }
            } else {
                val errorMessage = parseErrorMessage(
                    response.errorBody()?.string(),
                    response.code(),
                )
                Result.failure(MemoriesException(errorMessage))
            }
        } catch (e: MemoriesException) {
            Result.failure(e)
        } catch (e: Exception) {
            Result.failure(
                MemoriesException("Connection failed. Please check your internet."),
            )
        }
    }

    /**
     * Fetches memories for a specific character.
     */
    suspend fun getCharacterMemories(characterId: String): Result<List<MemoryItem>> {
        return try {
            val response = memoryApi.listCharacterMemories(characterId)
            if (response.isSuccessful) {
                val body = response.body()
                if (body != null) {
                    Result.success(body.memories)
                } else {
                    Result.failure(MemoriesException("Something went wrong. Please try again."))
                }
            } else {
                val errorMessage = parseErrorMessage(
                    response.errorBody()?.string(),
                    response.code(),
                )
                Result.failure(MemoriesException(errorMessage))
            }
        } catch (e: MemoriesException) {
            Result.failure(e)
        } catch (e: Exception) {
            Result.failure(
                MemoriesException("Connection failed. Please check your internet."),
            )
        }
    }

    /**
     * Fetches global (non-character-scoped) memories.
     */
    suspend fun getGlobalMemories(): Result<List<MemoryItem>> {
        return try {
            val response = memoryApi.listGlobalMemories()
            if (response.isSuccessful) {
                val body = response.body()
                if (body != null) {
                    Result.success(body.memories)
                } else {
                    Result.failure(MemoriesException("Something went wrong. Please try again."))
                }
            } else {
                val errorMessage = parseErrorMessage(
                    response.errorBody()?.string(),
                    response.code(),
                )
                Result.failure(MemoriesException(errorMessage))
            }
        } catch (e: MemoriesException) {
            Result.failure(e)
        } catch (e: Exception) {
            Result.failure(
                MemoriesException("Connection failed. Please check your internet."),
            )
        }
    }

    /**
     * Deletes a character-scoped memory.
     */
    suspend fun deleteCharacterMemory(
        characterId: String,
        memoryId: String,
    ): Result<Unit> {
        return try {
            val response = memoryApi.deleteCharacterMemory(characterId, memoryId)
            if (response.isSuccessful || response.code() == HTTP_NO_CONTENT) {
                Result.success(Unit)
            } else {
                val errorMessage = parseErrorMessage(
                    response.errorBody()?.string(),
                    response.code(),
                )
                Result.failure(MemoriesException(errorMessage))
            }
        } catch (e: MemoriesException) {
            Result.failure(e)
        } catch (e: Exception) {
            Result.failure(
                MemoriesException("Connection failed. Please check your internet."),
            )
        }
    }

    /**
     * Deletes a global memory.
     */
    suspend fun deleteGlobalMemory(memoryId: String): Result<Unit> {
        return try {
            val response = memoryApi.deleteGlobalMemory(memoryId)
            if (response.isSuccessful || response.code() == HTTP_NO_CONTENT) {
                Result.success(Unit)
            } else {
                val errorMessage = parseErrorMessage(
                    response.errorBody()?.string(),
                    response.code(),
                )
                Result.failure(MemoriesException(errorMessage))
            }
        } catch (e: MemoriesException) {
            Result.failure(e)
        } catch (e: Exception) {
            Result.failure(
                MemoriesException("Connection failed. Please check your internet."),
            )
        }
    }

    private fun parseErrorMessage(errorBody: String?, statusCode: Int): String {
        val detail = parseDetail(errorBody)
        return when (statusCode) {
            HTTP_UNAUTHORIZED -> "Session expired. Please sign in again."
            HTTP_SERVICE_UNAVAILABLE -> "Memory service unavailable. Please try again."
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
        private const val HTTP_NO_CONTENT = 204
        private const val HTTP_SERVICE_UNAVAILABLE = 503
    }
}

/** Exception type for memories screen errors with user-facing messages. */
class MemoriesException(message: String) : Exception(message)
