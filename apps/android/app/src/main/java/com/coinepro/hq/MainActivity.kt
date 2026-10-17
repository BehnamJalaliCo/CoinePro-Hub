package com.coinepro.hq

import android.content.Intent
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

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        enrolToken = tokenOf(intent)
        val graph = (application as HqApp).graph
        setContent {
            val mode by graph.prefs.theme.collectAsStateWithLifecycle()
            val night = isNight(mode)
            DivanTheme(night) {
                HqRoot(graph, night, enrolToken, onEnrolConsumed = { enrolToken = null })
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        tokenOf(intent)?.let { enrolToken = it }
    }

    private fun tokenOf(i: Intent?): String? {
        val uri = i?.data ?: return null
        if (uri.host != "hq.coinepro.com" || uri.path?.startsWith("/enroll") != true) return null
        return uri.fragment?.split('&')?.firstOrNull { it.startsWith("token=") }?.removePrefix("token=")?.takeIf { it.length >= 16 }
    }
}
