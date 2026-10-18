package com.coinepro.hq.device

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.widget.RemoteViews
import com.coinepro.hq.MainActivity
import com.coinepro.hq.R
import com.coinepro.hq.core.format.jTime
import java.time.Instant

/** The cartable on the home screen (M12): what waits for the owner's seal and what is urgent, as the app last saw it.
 *  The widget never calls the hub itself (no token outside the app); the app writes the counts whenever it reads them. */
class CartableWidget : AppWidgetProvider() {
    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        val p = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        render(context, manager, ids, p.getInt(K_PENDING, -1), p.getInt(K_URGENT, 0), p.getString(K_AT, null))
    }

    companion object {
        private const val PREFS = "hq.widget"
        private const val K_PENDING = "pending"
        private const val K_URGENT = "urgent"
        private const val K_AT = "at"

        fun update(context: Context, pending: Int, urgent: Int) {
            val at = Instant.now().toString()
            context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putInt(K_PENDING, pending).putInt(K_URGENT, urgent).putString(K_AT, at).apply()
            val manager = AppWidgetManager.getInstance(context)
            val ids = manager.getAppWidgetIds(ComponentName(context, CartableWidget::class.java))
            if (ids.isNotEmpty()) render(context, manager, ids, pending, urgent, at)
        }

        private fun render(context: Context, manager: AppWidgetManager, ids: IntArray, pending: Int, urgent: Int, at: String?) {
            val open = PendingIntent.getActivity(
                context, 1, Intent(context, MainActivity::class.java).putExtra(MainActivity.EXTRA_OPEN, "cartable").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
            val v = RemoteViews(context.packageName, R.layout.widget_cartable).apply {
                setTextViewText(R.id.widget_count, if (pending < 0) "—" else pending.toString())
                setTextViewText(R.id.widget_urgent, if (urgent > 0) "$urgent فوری" else "فوری ندارد")
                setTextViewText(R.id.widget_at, at?.let { "به‌روز ${jTime(it)}" } ?: "اپ را یک بار باز کن")
                setOnClickPendingIntent(R.id.widget_root, open)
            }
            manager.updateAppWidget(ids, v)
        }
    }
}
