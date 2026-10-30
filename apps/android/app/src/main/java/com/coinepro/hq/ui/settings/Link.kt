package com.coinepro.hq.ui.settings

import android.Manifest
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.coinepro.hq.core.AppGraph
import com.coinepro.hq.core.link.LinkPolicy
import com.coinepro.hq.core.link.LinkShown
import com.coinepro.hq.core.link.LinkView
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.LiveDot
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.generated.DivanIcon

/** What «اعلان‌ها وقتی اپ بسته است» shows (the screenshot tests pass one directly). */
data class LinkUi(
    /** The owner's switch as it stands (their choice, or on by default once notifications are allowed). */
    val on: Boolean,
    val view: LinkView,
    /** The phone lets the app notify (Android 13+ asks). */
    val allowed: Boolean,
    /** The app is exempt from battery optimisation. */
    val batteryFree: Boolean,
    /** A Samsung phone: its own "sleeping apps" list stops background apps on top of Android's. */
    val samsung: Boolean,
)

/** The settings' section for the background link: the switch, its state, the notification permission and the battery. */
@Composable
fun BackgroundLinkCard(graph: AppGraph) {
    val ctx = LocalContext.current
    val view by graph.link.view.collectAsStateWithLifecycle()
    // Read again whenever the settings come back on screen (the owner may have changed the permission or the battery in the system).
    var seen by remember { mutableIntStateOf(0) }
    LifecycleResumeEffect(Unit) {
        seen++
        graph.link.refresh()
        onPauseOrDispose { }
    }
    val ui = remember(view, seen) {
        val i = graph.link.inputs()
        LinkUi(LinkPolicy.switchOn(i) || (i.pref == true), view, i.allowed, batteryFree(ctx), Build.MANUFACTURER.equals("samsung", ignoreCase = true))
    }
    val ask = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        graph.link.refresh()
        seen++
    }
    fun allow() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU && !ui.allowed && !deniedForGood(ctx)) ask.launch(Manifest.permission.POST_NOTIFICATIONS)
        else open(ctx, Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, ctx.packageName))
    }
    BackgroundLinkContent(
        ui,
        onToggle = { on ->
            graph.link.setEnabled(on)
            if (on && !ui.allowed) allow()
            seen++
        },
        onAllow = ::allow,
        onBattery = {
            @android.annotation.SuppressLint("BatteryLife") // a sideloaded app whose job is an always-on link to its own server
            val i = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:${ctx.packageName}"))
            if (!open(ctx, i)) open(ctx, Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
        },
        onAppBattery = { open(ctx, Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:${ctx.packageName}"))) },
    )
}

@Composable
fun BackgroundLinkContent(ui: LinkUi, onToggle: (Boolean) -> Unit, onAllow: () -> Unit, onBattery: () -> Unit, onAppBattery: () -> Unit) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle(
            "اعلان‌ها وقتی اپ بسته است",
            note = "اپ یک اتصال سبک به ستاد باز نگه میدارد تا فوری‌ها، کارت‌های منتظر مُهر، فرمان‌ها و خروجی‌های تازه حتی با اپ بسته برسند؛ " +
                "بدون سرویس گوگل و بدون اپ دیگر. کمی باتری مصرف میکند.",
        )
        Column(Modifier.padding(top = 12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (!ui.allowed) {
                Notice(
                    DivanIcon.BELL, c.softLapis, c.lapis, "اجازه‌ی اعلان لازم است",
                    "تا اجازه ندهی، هیچ اعلانی روی گوشی نمیرسد و این اتصال خاموش میماند.",
                ) { HqButton("اجازه بده", onAllow, size = BtnSize.SM, variant = BtnVariant.PRIMARY) }
            }
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(if (ui.on) "روشن" else "خاموش", style = Divan.type.body)
                    Text(
                        if (ui.on) "یک اعلان آرام «اتصال به ستاد» همیشه در کشوی اعلان‌ها میماند." else "اعلان‌ها فقط وقتی اپ باز است میرسند.",
                        style = Divan.type.caption, color = c.textMuted,
                    )
                }
                HqSwitch(ui.on, onToggle, "اعلان‌ها وقتی اپ بسته است")
            }
            Status(ui.view)
            if (ui.on && ui.allowed) {
                if (!ui.batteryFree) {
                    Notice(
                        DivanIcon.SLEEPING, c.softWarning, c.warning, "بهینه‌سازی باتری ممکن است اتصال را ببندد",
                        "اندروید برای صرفه‌جویی، اتصال اپ‌های بسته را گاهی میبندد. اجازه بده ستاد از این محدودیت بیرون بماند.",
                    ) { HqButton("اجازه بده", onBattery, size = BtnSize.SM) }
                } else {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        DIcon(DivanIcon.SEAL, size = 16.dp, tint = c.positive)
                        Text("بهینه‌سازی باتری برای ستاد خاموش است.", style = Divan.type.caption, color = c.textSecondary)
                    }
                }
                if (ui.samsung) {
                    Notice(
                        DivanIcon.INFO, c.tile, c.textSecondary, "روی گوشی سامسونگ",
                        "تنظیمات ← باتری ← محدودیت‌های استفاده در پس‌زمینه ← «برنامه‌هایی که هرگز به خواب نمیروند» (\u2066Never sleeping apps\u2069) و ستاد را اضافه کن؛ " +
                            "وگرنه سامسونگ پس از چند روز اتصال را میخواباند.",
                    ) { HqButton("باتری اپ", onAppBattery, size = BtnSize.SM, variant = BtnVariant.GHOST) }
                }
            }
            Text(
                "در اعلان «اتصال به ستاد»، «قطع تا بازگشت» اتصال را تا باز کردن دوباره‌ی اپ میبندد. با اپ باز، اعلان‌ها همان پیام‌های داخل اپ‌اند و دوبار نمیرسند.",
                style = Divan.type.micro, color = c.textMuted,
            )
        }
    }
}

@Composable
private fun Status(v: LinkView) {
    val c = Divan.colors
    val (dot, live) = when (v.shown) {
        LinkShown.LIVE -> c.positive to true
        LinkShown.CONNECTING -> c.warning to false
        LinkShown.DOWN -> c.negative to false
        LinkShown.NO_PERMISSION -> c.warning to false
        else -> c.textMuted to false
    }
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(horizontal = 12.dp, vertical = 10.dp)
            .semantics { contentDescription = "وضعیت اتصال: ${v.fa}" },
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        LiveDot(dot, live = live, size = 8.dp)
        Text("وضعیت", style = Divan.type.small, color = c.textSecondary)
        Text(v.fa, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), modifier = Modifier.weight(1f))
    }
}

@Composable
private fun Notice(icon: DivanIcon, bg: Color, tint: Color, title: String, body: String, action: @Composable () -> Unit) {
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(bg).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            DIcon(icon, size = 20.dp, tint = tint)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(title, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                Text(body, style = Divan.type.caption, color = Divan.colors.textSecondary)
            }
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) { action() }
    }
}

private fun batteryFree(ctx: Context): Boolean =
    runCatching { ctx.getSystemService(PowerManager::class.java)?.isIgnoringBatteryOptimizations(ctx.packageName) == true }.getOrDefault(false)

/** Android 13+: after two refusals the system no longer asks; the app's notification settings are the way then. */
private fun deniedForGood(ctx: Context): Boolean {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return false
    val a = ctx as? android.app.Activity ?: (ctx as? android.content.ContextWrapper)?.baseContext as? android.app.Activity ?: return false
    val asked = a.getSharedPreferences("hq.link", Context.MODE_PRIVATE).getBoolean("asked_notifications", false)
    a.getSharedPreferences("hq.link", Context.MODE_PRIVATE).edit().putBoolean("asked_notifications", true).apply()
    return asked && !a.shouldShowRequestPermissionRationale(Manifest.permission.POST_NOTIFICATIONS)
}

private fun open(ctx: Context, i: Intent): Boolean = runCatching {
    ctx.startActivity(i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    true
}.getOrDefault(false)
