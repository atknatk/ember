package ai.ember.app.features.home

import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import retrofit2.Retrofit
import javax.inject.Singleton

/**
 * Hilt module providing Home screen dependencies.
 *
 * Provides [CharacterApi] via Retrofit.
 * [HomeRepository] is constructor-injected via @Inject.
 */
@Module
@InstallIn(SingletonComponent::class)
object HomeModule {

    @Provides
    @Singleton
    fun provideCharacterApi(retrofit: Retrofit): CharacterApi =
        retrofit.create(CharacterApi::class.java)
}
