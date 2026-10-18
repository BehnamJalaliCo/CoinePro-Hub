package com.coinepro.hq

import android.content.Intent
import android.os.Build
import android.view.WindowManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.coinepro.hq.designsystem.DivanTheme
import com.coinepro.hq.designsystem.isNight
import com.coinepro.hq.ui.HqRoot

class MainActivity : ComponentActivity() {
    /** The one-time enrolment token from an App Link (`/enroll#token=…`), consumed by the enrol screen. */
    private var enrolToken by mutableStateOf<String?>(null)
    /** Where the quick-settings tile or the widget asked to open ("voice", "cartable"). */
    private var launch by mutableStateOf<String?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        enrolToken = tokenOf(intent)
        launch = intent?.getStringExtra(EXTRA_OPEN)
        val graph = (application as HqApp).graph
        // Recents show no content (M11); screenshots stay possible on Android 13+, older phones get FLAG_SECURE with the lock on.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) setRecentsScreenshotEnabled(false)
        else if (graph.lock.enabled()) window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        setContent {
            val mode by graph.prefs.theme.collectAsStateWithLifecycle()
            val night = isNight(mode)
            DivanTheme(night) {
                HqRoot(graph, night, enrolToken, onEnrolConsumed = { enrolToken = null }, launch = launch, onLaunchConsumed = { launch = null })
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        tokenOf(intent)?.let { enrolToken = it }
        intent.getStringExtra(EXTRA_OPEN)?.let { launch = it }
    }

    companion object {
        const val EXTRA_OPEN = "com.coinepro.hq.OPEN"
    }

    private fun tokenOf(i: Intent?): String? {
        val uri = i?.data ?: return null
        if (uri.host != "hq.coinepro.com" || uri.path?.startsWith("/enroll") != true) return null
        return uri.fragment?.split('&')?.firstOrNull { it.startsWith("token=") }?.removePrefix("token=")?.takeIf { it.length >= 16 }
    }
}
