package ai.ember.app.features.memories

import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import retrofit2.Retrofit
import javax.inject.Singleton

/**
 * Hilt module providing Memories screen dependencies.
 *
 * Provides [MemoryApi] via Retrofit.
 * [MemoriesRepository] is constructor-injected via @Inject.
 */
@Module
@InstallIn(SingletonComponent::class)
object MemoriesModule {

    @Provides
    @Singleton
    fun provideMemoryApi(retrofit: Retrofit): MemoryApi =
        retrofit.create(MemoryApi::class.java)
}
