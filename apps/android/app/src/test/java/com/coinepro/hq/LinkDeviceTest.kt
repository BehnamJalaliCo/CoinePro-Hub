package com.coinepro.hq

import android.Manifest
import android.app.Notification
import android.app.NotificationManager
import android.content.Intent
import android.os.Looper
import androidx.test.core.app.ApplicationProvider
import com.coinepro.hq.core.link.Alert
import com.coinepro.hq.core.link.AlertChannel
import com.coinepro.hq.device.AlertNotifier
import com.coinepro.hq.device.HubLinkService
import com.coinepro.hq.device.LinkBoot
import java.time.Duration
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config

/**
 * The background link on a (Robolectric) phone: a reboot starts the service only when the owner wants it, the service's one quiet
 * notification and its «قطع تا بازگشت», the alerts' channels, groups and lock-screen version, and the demo playing what the link hears
 * with the app closed (a card, an order delivered, an urgent alert) — offline.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class LinkDeviceTest {
    private val app = ApplicationProvider.getApplicationContext<HqApp>()
    private val nm get() = app.getSystemService(NotificationManager::class.java)

    @Before
    fun setUp() {
        shadowOf(app).grantPermissions(Manifest.permission.POST_NOTIFICATIONS)
    }

    private fun idle(times: Int, ms: Long = 600) = repeat(times) {
        Thread.sleep(60)
        shadowOf(Looper.getMainLooper()).idleFor(Duration.ofMillis(ms))
    }

    private fun Notification.title() = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString()

    @Test
    fun aRebootStartsTheServiceOnlyWhenWanted() {
        app.graph.enterDemo()
        idle(2)
        while (shadowOf(app).nextStartedService != null) Unit
        LinkBoot().onReceive(app, Intent(Intent.ACTION_BOOT_COMPLETED))
        assertEquals(HubLinkService::class.java.name, shadowOf(app).nextStartedService?.component?.className)
        // Switched off: an update of the app (or a reboot) leaves it off.
        app.graph.link.setEnabled(false)
        while (shadowOf(app).nextStartedService != null) Unit
        LinkBoot().onReceive(app, Intent(Intent.ACTION_MY_PACKAGE_REPLACED))
        assertNull(shadowOf(app).nextStartedService)
    }

    @Test
    fun theServiceShowsOneQuietNotificationAndCanBePausedUntilTheAppReturns() {
        app.graph.enterDemo()
        idle(2)
        val controller = Robolectric.buildService(HubLinkService::class.java).create()
        idle(2)
        val n = shadowOf(nm).getNotification(HubLinkService.ONGOING_ID)
        assertNotNull(n)
        assertEquals("وصل به ستاد · زنده", n.title())
        assertEquals(AlertNotifier.CH_LINK, n.channelId)
        assertTrue(n.flags and Notification.FLAG_ONGOING_EVENT != 0)
        assertEquals("قطع تا بازگشت", n.actions.single().title.toString())
        assertEquals(NotificationManager.IMPORTANCE_LOW, nm.getNotificationChannel(AlertNotifier.CH_LINK).importance)
        assertTrue(app.graph.link.serviceRunning.value)

        controller.get().onStartCommand(Intent(app, HubLinkService::class.java).setAction(HubLinkService.ACTION_PAUSE), 0, 2)
        assertTrue(app.graph.linkStore.pausedUntilReturn)
        assertTrue(shadowOf(controller.get()).isStoppedBySelf)
        controller.destroy()
        assertTrue(!app.graph.link.serviceRunning.value)
        // Opening the app ends the pause.
        app.graph.link.setForeground(true)
        assertTrue(!app.graph.linkStore.pausedUntilReturn)
    }

    @Test
    fun alertsAreGroupedOpenTheirPageAndHideTheirWordsOnTheLockScreenWithTheAppLock() {
        val notifier = AlertNotifier(app) { true }
        notifier.post(Alert(AlertChannel.URGENT, "n:1", "دیسک هاب پر است", "۹۵٪ پر", "notifications", "HQ", notificationId = "n1"))
        notifier.post(Alert(AlertChannel.URGENT, "control:holding", "کل هلدینگ متوقف شد", "کلید توقف را ناظر کل زد", "control", "HQ"))
        val active = nm.activeNotifications
        assertEquals(3, active.size)
        val summary = active.single { it.id == AlertNotifier.SUMMARY_ID }.notification
        assertEquals("۲ مورد تازه", summary.extras.getCharSequence(Notification.EXTRA_SUMMARY_TEXT)?.toString())
        assertEquals(setOf("دیسک هاب پر است", "کل هلدینگ متوقف شد"), summary.extras.getCharSequenceArray(Notification.EXTRA_TEXT_LINES)!!.map { it.toString() }.toSet())
        val first = active.single { it.tag == "n:1" }.notification
        assertEquals(AlertChannel.URGENT.id, first.channelId)
        assertEquals(Notification.VISIBILITY_PRIVATE, first.visibility)
        assertEquals(AlertNotifier.PUBLIC_TITLE, first.publicVersion.title())
        // A tap opens the page through the ref router and marks the hub's notification read.
        val tap = shadowOf(first.contentIntent).savedIntent
        assertEquals("notifications", tap.getStringExtra(MainActivity.EXTRA_OPEN))
        assertEquals("n1", tap.getStringExtra(MainActivity.EXTRA_READ))
        // Channels and their importance.
        assertEquals(NotificationManager.IMPORTANCE_HIGH, nm.getNotificationChannel("urgent").importance)
        assertEquals(NotificationManager.IMPORTANCE_DEFAULT, nm.getNotificationChannel("cartable").importance)
        assertEquals(NotificationManager.IMPORTANCE_DEFAULT, nm.getNotificationChannel("orders").importance)
        assertEquals(NotificationManager.IMPORTANCE_LOW, nm.getNotificationChannel("outputs").importance)
        // Read in the app: the alert leaves, and with one left the summary goes too.
        notifier.cancelRead(listOf("n1"))
        assertEquals(listOf("control:holding"), nm.activeNotifications.map { it.tag })
    }

    @Test
    fun theLockScreenShowsOnlyThePublicLineEvenWithoutTheAppLock() {
        // 0.6.0's promise: on the lock screen only «پیام تازه از ستاد», whatever the app lock.
        AlertNotifier(app) { false }.post(Alert(AlertChannel.CARTABLE, "decision:D-1", "تصمیم تازه D-1", "پیشنهاد", "cartable/D-1"))
        val n = nm.activeNotifications.single().notification
        assertEquals(Notification.VISIBILITY_PRIVATE, n.visibility)
        assertEquals(AlertNotifier.PUBLIC_TITLE, n.publicVersion.title())
    }

    @Test
    fun aBurstSoundsOnce() {
        assertTrue(!AlertNotifier.quiet(null, 0))
        assertTrue(AlertNotifier.quiet(1_000, 5_000))
        assertTrue(!AlertNotifier.quiet(1_000, 1_000 + AlertNotifier.QUIET_MS))
    }

    @Test
    fun theDemoPlaysWhatTheLinkHearsWithTheAppClosed() {
        // The app is not on screen and notifications are allowed: the demo's link opens the alert lane only and plays its script.
        app.graph.enterDemo()
        val wanted = setOf(
            "تصمیم تازه D-000085: ایمیل دوم به پشتیبانی تجاری اینستاگرام",
            "فرمان W-000211 تحویل شد",
            "دیسک سرور هاب از ۹۵٪ گذشت",
        )
        var titles = emptyList<String?>()
        for (i in 0 until 80) {
            idle(1)
            titles = nm.activeNotifications.filter { it.id == AlertNotifier.ALERT_ID }.map { it.notification.title() }
            if (titles.containsAll(wanted)) break
        }
        assertTrue("$titles", titles.containsAll(wanted))
        val byTitle = nm.activeNotifications.filter { it.id == AlertNotifier.ALERT_ID }.associateBy { it.notification.title() }
        assertEquals("cartable", byTitle.getValue("تصمیم تازه D-000085: ایمیل دوم به پشتیبانی تجاری اینستاگرام").notification.channelId)
        assertEquals("orders", byTitle.getValue("فرمان W-000211 تحویل شد").notification.channelId)
        assertEquals("urgent", byTitle.getValue("دیسک سرور هاب از ۹۵٪ گذشت").notification.channelId)
        // The card opens on the cartable; the order's delivery on its output.
        assertEquals("cartable/D-000085", shadowOf(byTitle.getValue("تصمیم تازه D-000085: ایمیل دوم به پشتیبانی تجاری اینستاگرام").notification.contentIntent).savedIntent.getStringExtra(MainActivity.EXTRA_OPEN))
        assertTrue(shadowOf(byTitle.getValue("فرمان W-000211 تحویل شد").notification.contentIntent).savedIntent.getStringExtra(MainActivity.EXTRA_OPEN)!!.startsWith("outputs/O-"))
    }
}
