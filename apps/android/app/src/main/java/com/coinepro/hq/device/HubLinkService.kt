package com.coinepro.hq.device

import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.coinepro.hq.HqApp
import com.coinepro.hq.R
import com.coinepro.hq.core.link.LinkShown
import com.coinepro.hq.core.link.LinkView
import com.coinepro.hq.core.link.ServiceControl
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

/**
 * The background link's foreground service (owner's decision, 0.5.1: no FCM, no Google, no second app). It keeps the app's process in the
 * foreground so the stream's alert lane (`core/data/HoldingStream`, [com.coinepro.hq.core.link.HubLink]) stays open with the app closed,
 * and shows the link's state in one quiet notification: «وصل به ستاد · زنده», a tap opens the app, «قطع تا بازگشت» stops it until the app
 * is opened again.
 *
 * Type `specialUse` (Android 14+), with its reason in the manifest (`PROPERTY_SPECIAL_USE_FGS_SUBTYPE`): an always-on connection to the
 * owner's own server for its alerts is none of the typed uses, and `dataSync` is limited to six hours a day from Android 15. Sticky: if
 * the system ends the process, it starts the service again; the watchdog ([LinkWatchdog]) and a reboot ([LinkBoot]) cover the rest.
 */
class HubLinkService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val link get() = (application as HqApp).graph.link

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        if (!foreground(link.view.value)) return
        NotificationManagerCompat.from(this).cancel(PROMPT_ID)
        link.serviceUp()
        scope.launch {
            link.view.collect { v -> refresh(v) }
        }
    }

    /** The link's notification with its new state (the running service keeps it; without the permission it is simply not shown). */
    @android.annotation.SuppressLint("MissingPermission") // checked first
    private fun refresh(v: LinkView) {
        if (!AlertNotifier.allowed(this)) return
        runCatching { NotificationManagerCompat.from(this).notify(ONGOING_ID, ongoing(this, v)) }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_PAUSE) {
            link.pauseUntilReturn()
            stopSelf()
            return START_NOT_STICKY
        }
        // Every start asks for the foreground again (Android expects it after each startForegroundService).
        if (!foreground(link.view.value)) return START_NOT_STICKY
        return START_STICKY
    }

    override fun onDestroy() {
        scope.cancel()
        link.serviceDown()
        super.onDestroy()
    }

    /** Into the foreground with the link's notification; false (and stopped) when Android refuses. */
    private fun foreground(v: LinkView): Boolean = try {
        AlertNotifier.ensureChannels(this)
        ServiceCompat.startForeground(
            this, ONGOING_ID, ongoing(this, v),
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE else 0,
        )
        true
    } catch (e: Exception) {
        // ForegroundServiceStartNotAllowedException (Android 12+, a start from the background that is not exempt) and its kin.
        (application as HqApp).graph.errors.note("link", com.coinepro.hq.core.diag.LEVEL_INFO, "link start refused", "the foreground service could not start: ${e::class.simpleName}")
        stopSelf()
        false
    }

    companion object {
        const val ONGOING_ID = 4200
        const val PROMPT_ID = 4201
        const val ACTION_PAUSE = "com.coinepro.hq.link.PAUSE"

        /** The quiet notification of the running link: its state, a tap opens the app, «قطع تا بازگشت». */
        fun ongoing(context: Context, v: LinkView): Notification {
            val (title, text) = when (v.shown) {
                LinkShown.LIVE -> "وصل به ستاد · زنده" to null
                LinkShown.CONNECTING, LinkShown.OFF -> "در حال اتصال به ستاد…" to null
                else -> "قطع از ستاد" to v.fa.removePrefix("قطع: ")
            }
            val pause = PendingIntent.getService(
                context, 1, Intent(context, HubLinkService::class.java).setAction(ACTION_PAUSE), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
            )
            return NotificationCompat.Builder(context, AlertNotifier.CH_LINK)
                .setSmallIcon(R.drawable.ic_stat_hub)
                .setColor(0xFFC9A44C.toInt())
                .setContentTitle(title)
                .apply { if (text != null) setContentText(text) }
                .setContentIntent(AlertNotifier.open(context, null, null, "link"))
                .addAction(0, "قطع تا بازگشت", pause)
                .setOngoing(true)
                .setSilent(true)
                .setShowWhen(false)
                .setPriority(NotificationCompat.PRIORITY_LOW)
                .setCategory(NotificationCompat.CATEGORY_SERVICE)
                .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_DEFERRED)
                .build()
        }

        /** The device's [ServiceControl]: the service, its watchdog, and a tap-to-reconnect notice when Android refuses a background start. */
        fun control(context: Context): ServiceControl = object : ServiceControl {
            private val app = context.applicationContext
            private val prefs = app.getSharedPreferences("hq.link", Context.MODE_PRIVATE)

            override fun start(reason: String): Boolean = try {
                ContextCompat.startForegroundService(app, Intent(app, HubLinkService::class.java))
                true
            } catch (e: Exception) {
                // Android 12+ lets an app start a foreground service from the background only when exempt (a reboot, a tap on its
                // notification, battery optimisation off). Otherwise the owner gets one quiet notice: a tap starts it again.
                prompt()
                false
            }

            override fun stop() {
                app.stopService(Intent(app, HubLinkService::class.java))
            }

            override fun watchdog(on: Boolean) {
                // WorkManager is touched only when something changes: a watchdog never scheduled needs no cancelling.
                if (on == prefs.getBoolean(K_WATCHDOG, false)) return
                runCatching {
                    if (on) LinkWatchdog.schedule(app) else LinkWatchdog.cancel(app)
                    prefs.edit().putBoolean(K_WATCHDOG, on).apply()
                }
            }

            @android.annotation.SuppressLint("MissingPermission")
            private fun prompt() {
                if (!AlertNotifier.allowed(app)) return
                runCatching {
                    AlertNotifier.ensureChannels(app)
                    val start = PendingIntent.getForegroundService(app, 2, Intent(app, HubLinkService::class.java), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
                    NotificationManagerCompat.from(app).notify(
                        PROMPT_ID,
                        NotificationCompat.Builder(app, AlertNotifier.CH_LINK)
                            .setSmallIcon(R.drawable.ic_stat_hub)
                            .setColor(0xFFC9A44C.toInt())
                            .setContentTitle("اتصال به ستاد قطع شد")
                            .setContentText("اندروید اتصال را بست؛ برای وصل دوباره بزن.")
                            .setContentIntent(start)
                            .setAutoCancel(true)
                            .setSilent(true)
                            .setCategory(NotificationCompat.CATEGORY_STATUS)
                            .build(),
                    )
                }
            }
        }

        private const val K_WATCHDOG = "watchdog_scheduled"
    }
}
