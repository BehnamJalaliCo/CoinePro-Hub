package com.coinepro.hq.ui.settings

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.coinepro.hq.BuildConfig
import com.coinepro.hq.core.AppGraph
import com.coinepro.hq.core.ThemeMode
import com.coinepro.hq.core.auth.Passkeys
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Loadable
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.refresher

/** Settings: devices and passkeys, hiring, theme, Khalvat, the owner's working settings, and this app's identity
 *  (the signing fingerprint the server needs for passkeys on Android). */
@Composable
fun SettingsScreen(graph: AppGraph) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val ctx = LocalContext.current
    val c = Divan.colors
    val devices = rememberQuery("devices", "devices") { devices() }
    val presence = rememberQuery("presence", "presence") { presence() }
    val owner = rememberQuery("owner-settings", "settings") { ownerSettings() }
    val r = refresher(devices, presence, owner)
    val theme by graph.prefs.theme.collectAsStateWithLifecycle()
    val action = rememberAction()
    val fingerprints = remember { runCatching { Passkeys.signingFingerprints(act) }.getOrDefault(emptyList()) }
    val origins = remember { runCatching { Passkeys.origins(act) }.getOrDefault(emptyList()) }

    fun copy(label: String, text: String) {
        (ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText(label, text))
        toasts.ok("کپی شد.")
    }

    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("تنظیمات") }
        item {
            HqCard(Modifier.fillMaxWidth()) {
                SectionTitle("دستگاه‌ها و passkeyها", note = "بدون رمز؛ دست‌کم دو دستگاه ثبت کن تا اگر یکی گم شد بیرون نمانی.")
                Loadable(devices) { list ->
                    Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        list.items.filter { it.revokedAt == null }.forEach { d ->
                            Row(
                                Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp),
                                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
                            ) {
                                DIcon(if (d.kind == "passkey") DivanIcon.LOCK else DivanIcon.TIME, size = 18.dp, tint = c.textSecondary)
                                Column(Modifier.weight(1f)) {
                                    Fig(d.name, style = Divan.type.figure)
                                    Text("${if (d.kind == "passkey") "passkey" else "نشست"}، آخرین استفاده ${ago(d.lastUsedAt)}", style = Divan.type.micro, color = c.textMuted)
                                }
                                if (d.current) Pill("همین دستگاه", Tone.GOLD)
                                else HqButton("باطل کن", {
                                    action.run {
                                        val token = env.auth.stepUp(act, "device.revoke", d.id)
                                        env.api.revokeDevice(d.id, token)
                                        env.cache.invalidate("devices")
                                        toasts.info("دستگاه باطل شد.")
                                    }
                                }, variant = BtnVariant.DANGER, size = BtnSize.SM)
                            }
                        }
                    }
                }
                HqButton("ثبت همین گوشی به‌عنوان passkey تازه", {
                    action.run {
                        val token = env.auth.stepUp(act, "passkey.register", "self")
                        env.auth.enrol(act, null, token)
                        env.cache.invalidate("devices")
                        toasts.ok("passkey این گوشی ثبت شد.")
                    }
                }, Modifier.fillMaxWidth().padding(top = 12.dp), icon = DivanIcon.ADD, loading = action.busy)
            }
        }
        item { HiringCard() }
        item {
            HqCard(Modifier.fillMaxWidth()) {
                SectionTitle("نما")
                Segmented(
                    listOf(SegOption(ThemeMode.NIGHT, "شب"), SegOption(ThemeMode.DAY, "روز"), SegOption(ThemeMode.SYSTEM, "مثل سیستم")),
                    theme, graph.prefs::setTheme, Modifier.fillMaxWidth().padding(top = 10.dp),
                )
            }
        }
        item {
            HqCard(Modifier.fillMaxWidth()) {
                SectionTitle("خلوت", note = "وقتی روشن است فقط فوری میرسد؛ بقیه برای «در نبودت چه گذشت» میمانند.")
                val on = presence.data?.khalvat == true
                Row(Modifier.fillMaxWidth().padding(top = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(if (on) "خلوت روشن است" else "خلوت خاموش است", style = Divan.type.body, modifier = Modifier.weight(1f))
                    HqSwitch(on, { v ->
                        action.run { presence.set(env.api.setKhalvat(v)); env.cache.invalidate("presence", "inbox") }
                    }, "خلوت", enabled = presence.data != null && !action.busy)
                }
            }
        }
        item {
            HqCard(Modifier.fillMaxWidth()) {
                SectionTitle("تنظیمات کار", note = "از سرور")
                Loadable(owner) { s ->
                    Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Line("گزارش صبحگاهی") { Fig(s.morningReportAt) }
                        Line("بسته‌ی اعلان‌ها") { Text("هر ${s.digestMinutes} دقیقه", style = Divan.type.small) }
                        Line("سهمیه‌ی توجه هر مدیرعامل") { Text("${s.ceoDailyAttention} در روز", style = Divan.type.small) }
                        Line("منطقه‌ی زمانی") { Fig(s.timezone) }
                    }
                }
            }
        }
        if (!env.demo) item { com.coinepro.hq.ui.owner.AppLockCard(graph) }
        item { com.coinepro.hq.ui.owner.NotificationMatrixCard() }
        item {
            HqCard(Modifier.fillMaxWidth()) {
                SectionTitle("این اپ", note = "برای فعال شدن passkey روی اندروید، این دو مقدار باید روی سرور ثبت شوند.")
                Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Line("نسخه") { Fig("${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})") }
                    Line("بسته") { Fig(BuildConfig.APPLICATION_ID) }
                    HorizontalDivider(color = c.lineDivider)
                    fingerprints.firstOrNull()?.let { fp ->
                        Text("اثر انگشت امضا (SHA-256) برای assetlinks.json", style = Divan.type.micro, color = c.textMuted)
                        Fig(fp, style = Divan.type.figureSmall, maxLines = 3)
                        HqButton("کپی اثر انگشت", { copy("sha256", fp) }, size = BtnSize.SM, icon = DivanIcon.SHARE)
                    }
                    origins.firstOrNull()?.let { o ->
                        Text("origin اندروید برای HQ_ANDROID_ORIGINS", style = Divan.type.micro, color = c.textMuted)
                        Fig(o, style = Divan.type.figureSmall, maxLines = 3)
                        HqButton("کپی origin", { copy("origin", o) }, size = BtnSize.SM, icon = DivanIcon.SHARE)
                    }
                }
            }
        }
        item {
            HqButton(if (env.demo) "خروج از نمایش آزمایشی" else "خروج", { action.run { env.auth.signOut() } }, Modifier.fillMaxWidth(), variant = BtnVariant.DANGER, icon = DivanIcon.BACK)
        }
    }
}

@Composable
private fun Line(label: String, value: @Composable () -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(label, style = Divan.type.small, color = Divan.colors.textSecondary, modifier = Modifier.weight(1f))
        value()
    }
}
