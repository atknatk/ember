package ai.ember.app.core.auth

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKeys
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Securely stores JWT tokens using EncryptedSharedPreferences.
 *
 * Android equivalent of iOS KeychainTokenStore.
 * Uses AES-256 encryption via the Android Keystore system.
 */
@Singleton
class TokenManager @Inject constructor(
    @ApplicationContext context: Context,
) {
    private val prefs: SharedPreferences

    init {
        val masterKeyAlias = MasterKeys.getOrCreate(MasterKeys.AES256_GCM_SPEC)
        prefs = EncryptedSharedPreferences.create(
            PREFS_FILE_NAME,
            masterKeyAlias,
            context,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    /** Saves both access and refresh tokens. */
    fun saveTokens(accessToken: String, refreshToken: String) {
        prefs.edit()
            .putString(KEY_ACCESS_TOKEN, accessToken)
            .putString(KEY_REFRESH_TOKEN, refreshToken)
            .apply()
    }

    /** Updates only the access token. */
    fun updateAccessToken(token: String) {
        prefs.edit()
            .putString(KEY_ACCESS_TOKEN, token)
            .apply()
    }

    /** Reads the stored access token, or null if not present. */
    fun getAccessToken(): String? = prefs.getString(KEY_ACCESS_TOKEN, null)

    /** Reads the stored refresh token, or null if not present. */
    fun getRefreshToken(): String? = prefs.getString(KEY_REFRESH_TOKEN, null)

    /** Deletes both tokens and onboarding flag. */
    fun clearTokens() {
        prefs.edit()
            .remove(KEY_ACCESS_TOKEN)
            .remove(KEY_REFRESH_TOKEN)
            .remove(KEY_ONBOARDING_COMPLETED)
            .apply()
    }

    /** Returns true if both access and refresh tokens are stored. */
    val hasTokens: Boolean
        get() = getAccessToken() != null && getRefreshToken() != null

    /** Saves onboarding completion flag. */
    fun setOnboardingCompleted(completed: Boolean) {
        prefs.edit()
            .putBoolean(KEY_ONBOARDING_COMPLETED, completed)
            .apply()
    }

    /** Returns true if onboarding has been completed. */
    val hasCompletedOnboarding: Boolean
        get() = prefs.getBoolean(KEY_ONBOARDING_COMPLETED, false)

    /** Saves the user's display name. */
    fun saveUserName(name: String) {
        prefs.edit()
            .putString(KEY_USER_NAME, name)
            .apply()
    }

    /** Returns the stored user display name, or empty string. */
    fun getUserName(): String = prefs.getString(KEY_USER_NAME, "") ?: ""

    companion object {
        private const val PREFS_FILE_NAME = "ember_auth_prefs"
        private const val KEY_ACCESS_TOKEN = "access_token"
        private const val KEY_REFRESH_TOKEN = "refresh_token"
        private const val KEY_ONBOARDING_COMPLETED = "onboarding_completed"
        private const val KEY_USER_NAME = "user_name"
    }
}
