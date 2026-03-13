package ai.ember.app.core.auth

import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent

/**
 * Hilt module for authentication dependencies.
 *
 * [TokenManager] and [AuthRepository] are constructor-injected singletons,
 * so no explicit @Provides methods are needed here. This module exists as
 * a placeholder for future @Binds declarations (e.g., test doubles).
 */
@Module
@InstallIn(SingletonComponent::class)
object AuthModule
