package com.coinepro.hq.device

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.coinepro.hq.MainActivity
import com.coinepro.hq.R
import com.coinepro.hq.core.link.Alert
import com.coinepro.hq.core.link.AlertChannel
import com.coinepro.hq.core.link.AlertSink

/**
 * The alerts on the phone's notifications. Each [AlertChannel] is a channel of its own importance; the alerts of a channel form a group
 * with an InboxStyle summary once there are two or more; the same subject again replaces its notification ([Alert.key] is the tag) and
 * does not sound twice; a burst sounds once ([QUIET_MS]). A tap opens the alert's page through the app's ref router and marks the hub's
 * notification read. With the app lock on, the lock screen shows only «پیام تازه از ستاد» (the public version).
 */
class AlertNotifier(private val context: Context, private val lockOn: () -> Boolean) : AlertSink {
    private val lastSound = HashMap<AlertChannel, Long>()

    override fun allowed(): Boolean = allowed(context)

    @android.annotation.SuppressLint("MissingPermission") // [allowed] checks it first
    override fun post(alert: Alert) {
        if (!allowed()) return
        runCatching {
            ensureChannels(context)
            val now = System.currentTimeMillis()
            val silent = synchronized(lastSound) { quiet(lastSound[alert.channel], now).also { if (!it) lastSound[alert.channel] = now } }
            val b = NotificationCompat.Builder(context, alert.channel.id)
                .setSmallIcon(iconOf(alert.channel))
                .setColor(GOLD)
                .setContentTitle(alert.title)
                .setContentText(alert.text)
                .setStyle(NotificationCompat.BigTextStyle().bigText(alert.text))
                .setWhen(alert.at?.let { runCatching { java.time.Instant.parse(it).toEpochMilli() }.getOrNull() } ?: now)
                .setShowWhen(true)
                .setCategory(categoryOf(alert.channel))
                .setContentIntent(open(context, alert.route, alert.notificationId, alert.key))
                .setAutoCancel(true)
                .setOnlyAlertOnce(true)
                .setSilent(silent)
                .setGroup(groupOf(alert.channel))
                .setGroupAlertBehavior(NotificationCompat.GROUP_ALERT_CHILDREN)
                .addExtras(Bundle().apply { putString(EXTRA_NID, alert.notificationId); putString(EXTRA_KEY, alert.key) })
            if (lockOn()) b.setVisibility(NotificationCompat.VISIBILITY_PRIVATE).setPublicVersion(publicVersion(alert.channel))
            NotificationManagerCompat.from(context).notify(alert.key, ALERT_ID, b.build())
            summarize(alert.channel)
        }
    }

    override fun cancel(key: String) {
        runCatching {
            NotificationManagerCompat.from(context).cancel(key, ALERT_ID)
            AlertChannel.entries.forEach(::summarize)
        }
    }

    override fun cancelRead(notificationIds: Collection<String>) {
        runCatching {
            val ids = notificationIds.toSet()
            val nm = context.getSystemService(NotificationManager::class.java) ?: return
            for (sbn in nm.activeNotifications) {
                if (sbn.id != ALERT_ID) continue
                if (sbn.notification.extras.getString(EXTRA_NID)?.let { it in ids } == true) nm.cancel(sbn.tag, ALERT_ID)
            }
            AlertChannel.entries.forEach(::summarize)
        }
    }

    @android.annotation.SuppressLint("MissingPermission")
    override fun sessionExpired(show: Boolean) {
        runCatching {
            val nm = NotificationManagerCompat.from(context)
            if (!show) return nm.cancel(EXPIRED_ID)
            if (!allowed()) return
            ensureChannels(context)
            nm.notify(
                EXPIRED_ID,
                NotificationCompat.Builder(context, CH_ACCOUNT)
                    .setSmallIcon(R.drawable.ic_stat_hub)
                    .setColor(GOLD)
                    .setContentTitle("برای ادامه‌ی اعلان‌ها وارد شو")
                    .setContentText("نشست ستاد روی این گوشی تمام شد؛ تا دوباره وارد نشوی، اعلان‌ها با اپ بسته نمیرسند.")
                    .setStyle(NotificationCompat.BigTextStyle().bigText("نشست ستاد روی این گوشی تمام شد؛ تا دوباره وارد نشوی، اعلان‌ها با اپ بسته نمیرسند."))
                    .setContentIntent(open(context, null, null, "expired"))
                    .setAutoCancel(true)
                    .setCategory(NotificationCompat.CATEGORY_STATUS)
                    .build(),
            )
        }
    }

    /** The channel's group: one summary (InboxStyle, the newest first) while two or more of its alerts stand, none otherwise. */
    @android.annotation.SuppressLint("MissingPermission")
    private fun summarize(channel: AlertChannel) {
        val nm = context.getSystemService(NotificationManager::class.java) ?: return
        val group = groupOf(channel)
        val standing = nm.activeNotifications
            .filter { it.id == ALERT_ID && it.notification.group == group }
            .sortedByDescending { it.notification.`when` }
        if (standing.size < 2) {
            nm.cancel(group, SUMMARY_ID)
            return
        }
        val name = context.getString(nameOf(channel))
        val style = NotificationCompat.InboxStyle().setSummaryText(countFa(standing.size))
        for (s in standing.take(6)) {
            val e = s.notification.extras
            style.addLine(e.getCharSequence(android.app.Notification.EXTRA_TITLE) ?: continue)
        }
        val b = NotificationCompat.Builder(context, channel.id)
            .setSmallIcon(iconOf(channel))
            .setColor(GOLD)
            .setContentTitle(name)
            .setContentText(countFa(standing.size))
            .setStyle(style)
            .setGroup(group)
            .setGroupSummary(true)
            .setGroupAlertBehavior(NotificationCompat.GROUP_ALERT_CHILDREN)
            .setSilent(true)
            .setAutoCancel(true)
            .setContentIntent(open(context, listRouteOf(channel), null, "summary:${channel.id}"))
        if (lockOn()) b.setVisibility(NotificationCompat.VISIBILITY_PRIVATE).setPublicVersion(publicVersion(channel))
        NotificationManagerCompat.from(context).notify(group, SUMMARY_ID, b.build())
    }

    private fun publicVersion(channel: AlertChannel) = NotificationCompat.Builder(context, channel.id)
        .setSmallIcon(iconOf(channel))
        .setColor(GOLD)
        .setContentTitle(PUBLIC_TITLE)
        .build()

    companion object {
        const val ALERT_ID = 4100
        const val SUMMARY_ID = 4101
        const val EXPIRED_ID = 4102
        const val CH_LINK = "link"
        const val CH_ACCOUNT = "account"
        const val EXTRA_NID = "com.coinepro.hq.NID"
        const val EXTRA_KEY = "com.coinepro.hq.KEY"
        /** What the lock screen shows of an alert while the app lock is on. */
        const val PUBLIC_TITLE = "پیام تازه از ستاد"
        /** A second alert on the same channel within this long is silent: a burst (a replay, the holding's switch) sounds once. */
        const val QUIET_MS = 15_000L
        private const val GOLD = 0xFFC9A44C.toInt()

        /** Whether the phone lets the app show notifications (Android 13+ asks; the owner can switch them off). */
        fun allowed(context: Context): Boolean {
            val granted = Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
                ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
            return granted && NotificationManagerCompat.from(context).areNotificationsEnabled()
        }

        /** Whether this alert should be silent: another on its channel sounded less than [QUIET_MS] ago. */
        fun quiet(lastSoundAt: Long?, now: Long): Boolean = lastSoundAt != null && now - lastSoundAt in 0 until QUIET_MS

        fun groupOf(channel: AlertChannel) = "com.coinepro.hq.${channel.id}"

        /** «۳ مورد تازه»: the system's own font draws the figures, so they are written Persian here. */
        fun countFa(n: Int) = "${com.coinepro.hq.core.link.AlertRules.faDigits(n.toString())} مورد تازه"

        /** Where a channel's summary opens: the list its alerts belong to. */
        fun listRouteOf(channel: AlertChannel) = when (channel) {
            AlertChannel.URGENT -> "notifications"
            AlertChannel.CARTABLE -> "cartable"
            AlertChannel.ORDERS -> "orders"
            AlertChannel.OUTPUTS -> "outputs"
        }

        private fun iconOf(channel: AlertChannel) = when (channel) {
            AlertChannel.URGENT -> R.drawable.ic_stat_urgent
            AlertChannel.CARTABLE -> R.drawable.ic_stat_cartable
            AlertChannel.ORDERS -> R.drawable.ic_stat_order
            AlertChannel.OUTPUTS -> R.drawable.ic_stat_output
        }

        private fun nameOf(channel: AlertChannel) = when (channel) {
            AlertChannel.URGENT -> R.string.channel_urgent
            AlertChannel.CARTABLE -> R.string.channel_cartable
            AlertChannel.ORDERS -> R.string.channel_orders
            AlertChannel.OUTPUTS -> R.string.channel_outputs
        }

        private fun categoryOf(channel: AlertChannel) = when (channel) {
            AlertChannel.URGENT -> NotificationCompat.CATEGORY_ERROR
            AlertChannel.CARTABLE -> NotificationCompat.CATEGORY_REMINDER
            else -> NotificationCompat.CATEGORY_STATUS
        }

        /** The app opened on [route] (the ref router decides the page); [notificationId], when there is one, is marked read. */
        fun open(context: Context, route: String?, notificationId: String?, key: String): PendingIntent {
            val i = Intent(context, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
                .apply {
                    route?.let { putExtra(MainActivity.EXTRA_OPEN, it) }
                    notificationId?.let { putExtra(MainActivity.EXTRA_READ, it) }
                }
            return PendingIntent.getActivity(context, key.hashCode(), i, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        }

        /** Every channel, created once (an existing channel keeps the owner's own settings). */
        fun ensureChannels(context: Context) {
            val nm = context.getSystemService(NotificationManager::class.java) ?: return
            fun ch(id: String, name: Int, desc: Int, importance: Int, badge: Boolean = true) {
                if (nm.getNotificationChannel(id) != null) return
                nm.createNotificationChannel(
                    NotificationChannel(id, context.getString(name), importance).apply {
                        description = context.getString(desc)
                        setShowBadge(badge)
                    },
                )
            }
            ch(AlertChannel.URGENT.id, R.string.channel_urgent, R.string.channel_urgent_description, NotificationManager.IMPORTANCE_HIGH)
            ch(AlertChannel.CARTABLE.id, R.string.channel_cartable, R.string.channel_cartable_description, NotificationManager.IMPORTANCE_DEFAULT)
            ch(AlertChannel.ORDERS.id, R.string.channel_orders, R.string.channel_orders_description, NotificationManager.IMPORTANCE_DEFAULT)
            ch(AlertChannel.OUTPUTS.id, R.string.channel_outputs, R.string.channel_outputs_description, NotificationManager.IMPORTANCE_LOW)
            ch(CH_LINK, R.string.channel_link, R.string.channel_link_description, NotificationManager.IMPORTANCE_LOW, badge = false)
            ch(CH_ACCOUNT, R.string.channel_account, R.string.channel_account_description, NotificationManager.IMPORTANCE_DEFAULT)
        }
    }
}

/** Keeps the CPU awake for a moment while an alert is read from the hub and told (a packet woke the phone; it may sleep again at once). */
class Wake(context: Context) {
    private val lock = runCatching {
        context.getSystemService(android.os.PowerManager::class.java)
            ?.newWakeLock(android.os.PowerManager.PARTIAL_WAKE_LOCK, "coinepro:alert")
            ?.apply { setReferenceCounted(false) }
    }.getOrNull()

    /** Holds for at most [ms]; another call extends it. */
    @android.annotation.SuppressLint("WakelockTimeout")
    fun hold(ms: Long) { runCatching { lock?.acquire(ms) } }
}
