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
        val graph = (application as HqApp).graph
        // A recreated activity (rotation, the process brought back) does not open its first page again.
        if (savedInstanceState == null) {
            launch = openOf(intent)
            markRead(intent)
        }
        intent?.removeExtra(EXTRA_OPEN)
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
        openOf(intent)?.let { launch = it }
        markRead(intent)
        intent.removeExtra(EXTRA_OPEN)
    }

    /** A page to open, only from the app's own launches and only a route the app has. */
    private fun openOf(i: Intent?): String? =
        i?.getStringExtra(EXTRA_OPEN)?.takeIf { com.coinepro.hq.device.LaunchKey.trusted(this, i) && com.coinepro.hq.device.LaunchKey.routeAllowed(it) }

    /** The app launched a picker, the camera or a share sheet: coming back from it is not leaving the app (the lock waits). */
    override fun startActivityForResult(intent: Intent, requestCode: Int, options: Bundle?) {
        (application as HqApp).graph.lock.leavingForResult()
        super.startActivityForResult(intent, requestCode, options)
    }

    override fun startActivity(intent: Intent, options: Bundle?) {
        (application as HqApp).graph.lock.leavingForResult()
        super.startActivity(intent, options)
    }

    /** A tap on an alert that came from a hub notification opens it, as a tap in the app's list does: it is read. */
    private fun markRead(i: Intent?) {
        val id = i?.getStringExtra(EXTRA_READ) ?: return
        i.removeExtra(EXTRA_READ)
        if (!com.coinepro.hq.device.LaunchKey.trusted(this, i)) return
        val env = (application as HqApp).graph.env.value
        if (env.auth.signedIn.value) env.reads.open(id)
    }

    companion object {
        const val EXTRA_OPEN = "com.coinepro.hq.OPEN"
        /** The hub notification an alert came from (marked read when the alert is tapped). */
        const val EXTRA_READ = "com.coinepro.hq.READ"
    }

    private fun tokenOf(i: Intent?): String? {
        val uri = i?.data ?: return null
        if (uri.host != "hq.coinepro.com" || uri.path?.startsWith("/enroll") != true) return null
        return uri.fragment?.split('&')?.firstOrNull { it.startsWith("token=") }?.removePrefix("token=")?.takeIf { it.length >= 16 }
    }
}
