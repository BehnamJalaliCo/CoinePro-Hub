package com.coinepro.hq.device

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.coinepro.hq.MainActivity
import com.coinepro.hq.R
import com.coinepro.hq.core.data.NoticeKind
import com.coinepro.hq.core.data.OrderNotice

/**
 * The «فرمان‌ها» notification channel: an order that changes stage while the app is open (and connected to the stream) is told here too,
 * so it reaches the shade and the watch. No push service: nothing arrives while the app is closed (FCM was dropped by the owner).
 * A tap opens the order's page (or its output).
 */
object OrderNotify {
    const val CHANNEL = "orders"

    /** Whether the phone lets the app show it (Android 13+ asks; the owner can switch the channel off). */
    fun allowed(context: Context): Boolean {
        val granted = Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
        return granted && NotificationManagerCompat.from(context).areNotificationsEnabled()
    }

    private fun ensureChannel(context: Context) {
        val nm = context.getSystemService(NotificationManager::class.java) ?: return
        if (nm.getNotificationChannel(CHANNEL) != null) return
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL, context.getString(R.string.channel_orders), NotificationManager.IMPORTANCE_DEFAULT).apply {
                description = context.getString(R.string.channel_orders_description)
            },
        )
    }

    /** Where a tap takes the owner: the output of a delivery, otherwise the order. */
    fun routeOf(n: OrderNotice): String = when {
        n.kind == NoticeKind.DELIVERED && n.deliverable != null -> "outputs/${n.deliverable}"
        n.workId != null -> "work/${n.workId}"
        else -> "work/${n.ref}"
    }

    @android.annotation.SuppressLint("MissingPermission") // [allowed] checks it first
    fun post(context: Context, n: OrderNotice) {
        if (!allowed(context)) return
        runCatching {
            ensureChannel(context)
            val open = Intent(context, MainActivity::class.java)
                .putExtra(MainActivity.EXTRA_OPEN, routeOf(n))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            val id = n.key.hashCode()
            val tap = PendingIntent.getActivity(context, id, open, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
            val note = NotificationCompat.Builder(context, CHANNEL)
                .setSmallIcon(R.drawable.ic_stat_order)
                .setContentTitle(n.headline)
                .setContentText(n.text)
                .setStyle(NotificationCompat.BigTextStyle().bigText(n.text))
                .setCategory(NotificationCompat.CATEGORY_STATUS)
                .setContentIntent(tap)
                .setAutoCancel(true)
                .build()
            NotificationManagerCompat.from(context).notify(id, note)
        }
    }
}
