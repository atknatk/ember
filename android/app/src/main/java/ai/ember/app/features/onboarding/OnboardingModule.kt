package ai.ember.app.features.onboarding

import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import retrofit2.Retrofit
import javax.inject.Singleton

/**
 * Hilt module providing onboarding dependencies.
 *
 * Provides [OnboardingApi] via Retrofit and [OnboardingRepository].
 */
@Module
@InstallIn(SingletonComponent::class)
object OnboardingModule {

    @Provides
    @Singleton
    fun provideOnboardingApi(retrofit: Retrofit): OnboardingApi =
        retrofit.create(OnboardingApi::class.java)
}
