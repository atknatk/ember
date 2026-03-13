package ai.ember.app.features.home

import android.content.Context
import android.content.SharedPreferences
import ai.ember.app.core.models.Character
import dagger.hilt.android.qualifiers.ApplicationContext
import java.time.Instant
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Tracks when the user last opened each character's chat.
 *
 * Uses SharedPreferences to store timestamps. Compares against
 * the character's [Character.lastMessageAt] to determine if
 * there are unread messages.
 *
 * This is a local heuristic — mirrors iOS UserDefaults approach.
 */
@Singleton
class UnreadTracker @Inject constructor(
    @ApplicationContext context: Context,
) {
    private val prefs: SharedPreferences =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    /**
     * Stores the current time as the last-opened timestamp for a character.
     */
    fun markAsOpened(characterId: String) {
        prefs.edit()
            .putLong(characterId, System.currentTimeMillis())
            .apply()
    }

    /**
     * Returns the epoch millis when the character was last opened, or null.
     */
    fun getLastOpenedMillis(characterId: String): Long? {
        val value = prefs.getLong(characterId, NEVER_OPENED)
        return if (value == NEVER_OPENED) null else value
    }

    /**
     * Returns true if the character has messages newer than the last
     * time the user opened that character's chat.
     */
    fun hasUnread(character: Character): Boolean {
        val lastMessageAt = character.lastMessageAt ?: return false
        val lastOpenedMillis = getLastOpenedMillis(character.id)
            ?: return true // Never opened — any message is unread

        return try {
            val messageInstant = Instant.parse(lastMessageAt)
            messageInstant.toEpochMilli() > lastOpenedMillis
        } catch (e: Exception) {
            false
        }
    }

    companion object {
        private const val PREFS_NAME = "ember_character_last_opened"
        private const val NEVER_OPENED = -1L
    }
}
