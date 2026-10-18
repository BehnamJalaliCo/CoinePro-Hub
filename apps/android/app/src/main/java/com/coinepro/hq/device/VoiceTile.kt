package com.coinepro.hq.device

import android.app.PendingIntent
import android.content.Intent
import android.os.Build
import android.service.quicksettings.TileService
import com.coinepro.hq.MainActivity

/** A voice order from the quick-settings panel (M12): two seconds from anywhere to the hub's voice order sheet. */
class VoiceTile : TileService() {
    override fun onClick() {
        val intent = Intent(this, MainActivity::class.java).putExtra(MainActivity.EXTRA_OPEN, "voice").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startActivityAndCollapse(PendingIntent.getActivity(this, 2, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE))
        } else {
            @Suppress("DEPRECATION", "StartActivityAndCollapseDeprecated") startActivityAndCollapse(intent)
        }
    }
}
