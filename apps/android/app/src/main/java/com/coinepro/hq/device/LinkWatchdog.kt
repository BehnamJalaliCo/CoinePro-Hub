package com.coinepro.hq.device

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import com.coinepro.hq.HqApp
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext

/**
 * Every 15 minutes (WorkManager's shortest period; in Doze, at the next maintenance window): if the background link should run and the
 * system stopped its service, start it again; if it runs, cut its reconnect wait short. Scheduled only while the link is wanted.
 */
class LinkWatchdog(context: Context, params: WorkerParameters) : Worker(context, params) {
    override fun doWork(): Result {
        val app = applicationContext as? HqApp ?: return Result.success()
        runBlocking { withContext(Dispatchers.Main) { app.graph.link.revive("watchdog") } }
        return Result.success()
    }

    companion object {
        private const val NAME = "hq-link-watchdog"

        fun schedule(context: Context) {
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                NAME, ExistingPeriodicWorkPolicy.KEEP, PeriodicWorkRequestBuilder<LinkWatchdog>(15, TimeUnit.MINUTES).build(),
            )
        }

        fun cancel(context: Context) {
            WorkManager.getInstance(context).cancelUniqueWork(NAME)
        }
    }
}

/**
 * After a reboot and after the app is updated (`BOOT_COMPLETED`, `MY_PACKAGE_REPLACED`, both exempt from Android's limits on starting a
 * foreground service from the background, `specialUse` included): the background link starts again if the owner wants it.
 */
class LinkBoot : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val reason = when (intent.action) {
            Intent.ACTION_BOOT_COMPLETED -> "boot"
            Intent.ACTION_MY_PACKAGE_REPLACED -> "app updated"
            else -> return
        }
        (context.applicationContext as? HqApp)?.graph?.link?.revive(reason)
    }
}
