package ai.ember.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import ai.ember.app.core.navigation.EmberNavHost
import ai.ember.app.core.network.NetworkMonitor
import ai.ember.app.core.ui.theme.EmberTheme
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    @Inject
    lateinit var networkMonitor: NetworkMonitor

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            EmberTheme {
                EmberNavHost(networkMonitor = networkMonitor)
            }
        }
    }
}
