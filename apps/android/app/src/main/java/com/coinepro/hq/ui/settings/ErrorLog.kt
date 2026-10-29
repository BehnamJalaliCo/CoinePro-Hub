package com.coinepro.hq.ui.settings

import com.coinepro.hq.ui.itemMotion
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDirection
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.coinepro.hq.core.diag.ErrorEntry
import com.coinepro.hq.core.diag.ErrorLog
import com.coinepro.hq.core.diag.LEVEL_ERROR
import com.coinepro.hq.core.diag.LEVEL_INFO
import com.coinepro.hq.core.diag.LEVEL_WARNING
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FigureFace
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.ScrollRow
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import java.io.File

/** What each kind of entry is, in the owner's words, with its tone and icon. */
private data class KindFa(val fa: String, val tone: Tone, val icon: DivanIcon)

private val KINDS = mapOf(
    "decode" to KindFa("ناسازگاری با قرارداد", Tone.NEG, DivanIcon.URGENT),
    "http" to KindFa("خطای سرور", Tone.WARN, DivanIcon.SERVER),
    "network" to KindFa("اتصال", Tone.NEUTRAL, DivanIcon.OFFLINE),
    "unreachable" to KindFa("هاب در دسترس نبود", Tone.WARN, DivanIcon.SERVER),
    "hub" to KindFa("هاب برگشت", Tone.POS, DivanIcon.SERVER),
    "stream" to KindFa("استریم زنده", Tone.NEUTRAL, DivanIcon.REFRESH),
    "crash" to KindFa("از کار افتادن اپ", Tone.NEG, DivanIcon.URGENT),
    "passkey" to KindFa("اثر انگشت و passkey", Tone.WARN, DivanIcon.LOCK),
    "speech" to KindFa("تشخیص گفتار", Tone.NEUTRAL, DivanIcon.MIC),
    "session" to KindFa("شروع اپ", Tone.LAPIS, DivanIcon.INFO),
)

private fun kindOf(e: ErrorEntry) = KINDS[e.kind] ?: KindFa(e.title ?: e.kind, Tone.NEUTRAL, DivanIcon.INFO)

private val LEVELS = listOf(LEVEL_ERROR to "خطا", LEVEL_WARNING to "هشدار", LEVEL_INFO to "اطلاع")
private fun levelFa(l: String) = LEVELS.firstOrNull { it.first == l }?.second ?: l
private fun levelTone(l: String) = when (l) { LEVEL_ERROR -> Tone.NEG; LEVEL_WARNING -> Tone.WARN; else -> Tone.LAPIS }

/** Whether an entry matches the search: its path, code, title, message, detail, screen or request id. */
fun matches(e: ErrorEntry, q: String): Boolean {
    val t = q.trim()
    if (t.isEmpty()) return true
    return listOfNotNull(e.path, e.code, e.title, e.message, e.detail, e.screen, e.requestId, e.field, e.method, e.status?.toString(), kindOf(e).fa, "#${e.id}")
        .any { it.contains(t, ignoreCase = true) } || e.paths.any { it.contains(t, ignoreCase = true) }
}

/**
 * «خطاخوان» (Settings, the tools sheet): this version's log, from the session that opened it, newest first, each entry with its exact time
 * (the owner's zone and UTC, to the millisecond), its sequence number and everything needed to trace it; filtered by level and searched.
 * A new version starts empty; the last versions' logs are kept apart under «نسخه‌های قبلی». Copy or share as a plain-text report.
 */
@Composable
fun ErrorLogScreen(log: ErrorLog, version0: String? = null) {
    val ctx = LocalContext.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val current by log.entries.collectAsStateWithLifecycle()
    var version by rememberSaveable { mutableStateOf(version0) }
    var level by rememberSaveable { mutableStateOf<String?>(null) }
    var q by rememberSaveable { mutableStateOf("") }
    var confirm by remember { mutableStateOf(false) }
    var versions by remember { mutableStateOf(false) }
    val archives = remember(version, current.size) { log.archives() }
    val entries = remember(version, current) { if (version == null) current else log.archived(version!!) }
    val shown = entries.filter { (level == null || it.level == level) && matches(it, q) }
    val report = { log.report(shown, version ?: log.app) }
    Page {
        item {
            PageHeader("خطاخوان", eyebrow = "ردّ هر خطا، با زمان دقیق و هرچه برای پیدا کردنش لازم است؛ فقط روی همین گوشی") {
                HqButton("کپی", {
                    copyText(ctx, "error log", report())
                    toasts.ok("گزارش کپی شد؛ برای توسعه‌دهنده بفرست.")
                }, size = BtnSize.SM, icon = DivanIcon.REPORT, enabled = shown.isNotEmpty())
                HqButton("اشتراک", { shareReport(ctx, report()) }, size = BtnSize.SM, icon = DivanIcon.SHARE, enabled = shown.isNotEmpty())
                if (version == null) HqButton("پاک کردن", { confirm = true }, size = BtnSize.SM, variant = BtnVariant.GHOST, icon = DivanIcon.CLOSE, enabled = current.isNotEmpty())
            }
        }
        item {
            // Which version this log belongs to, and the way to the ones before.
            HqCard(Modifier.fillMaxWidth(), padding = androidx.compose.foundation.layout.PaddingValues(horizontal = 14.dp, vertical = 12.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    DIcon(DivanIcon.CODE, size = 18.dp, tint = c.textSecondary)
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(buildAnnotatedString { append(if (version == null) "نسخه‌ی " else "نسخه‌ی قبلی "); fig(version ?: log.app) }, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                        Text(
                            if (version == null) "هر نسخه‌ی تازه با خطاخوان خالی شروع میشود؛ ${entries.size} مورد از شروع این نسخه."
                            else "فقط خواندنی؛ ${entries.size} مورد. خطاخوان نسخه‌ی فعلی جداست.",
                            style = Divan.type.caption, color = c.textMuted,
                        )
                    }
                    when {
                        version != null -> HqButton("نسخه‌ی فعلی", { version = null }, size = BtnSize.SM, variant = BtnVariant.TEXT)
                        archives.isNotEmpty() -> HqButton("نسخه‌های قبلی", { versions = !versions }, size = BtnSize.SM, variant = BtnVariant.TEXT)
                    }
                }
                com.coinepro.hq.designsystem.Expand(versions && version == null) {
                    Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        for (a in archives) Row(
                            Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).clickable(role = Role.Button) { version = a.app; versions = false }.padding(horizontal = 12.dp, vertical = 10.dp),
                            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            Fig(a.app, style = Divan.type.figureSmall, color = c.textPrimary, modifier = Modifier.weight(1f))
                            Text("${a.entries} مورد", style = Divan.type.caption, color = c.textMuted)
                            DIcon(DivanIcon.NEXT, size = 14.dp, tint = c.textMuted)
                        }
                    }
                }
            }
        }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                ScrollRow {
                    FilterChip("همه", level == null, { level = null }, count = entries.size)
                    for ((k, l) in LEVELS) FilterChip(l, level == k, { level = if (level == k) null else k }, count = entries.count { it.level == k })
                }
                HqTextField(q, { q = it }, "جست‌وجو: مسیر، کد، شناسه‌ی درخواست، صفحه…", Modifier.fillMaxWidth(), maxLength = 80)
            }
        }
        if (shown.isEmpty()) item {
            HqCard(Modifier.fillMaxWidth()) {
                if (entries.isEmpty()) Empty("خطایی ثبت نشده", icon = DivanIcon.SEAL, body = "اگر جایی «پاسخ سرور با قرارداد نمیخواند» یا خطای دیگری دیدی، این‌جا با جزئیاتش میاید.")
                else Empty("چیزی با این فیلتر نیست", icon = DivanIcon.FILTER)
            }
        }
        else items(shown, key = { "${version ?: "now"}-${it.id}" }) { e -> Box(itemMotion()) { EntryCard(e) } }
        item {
            Text(
                "هر مورد با زمان (تهران و UTC، تا هزارم ثانیه)، شماره‌ی ترتیب، نسخه، صفحه، شبکه، مسیر درخواست (شناسه‌ها پوشیده)، مدت، کد پاسخ، پیام سرور و شناسه‌ی درخواست ثبت میشود؛ " +
                    "هیچ توکن، کلید، رمز، کوکی، متن پیام یا داده‌ی مشتری ثبت نمیشود. حداکثر ${ErrorLog.MAX} مورد در هر نسخه، و خطاخوان ${ErrorLog.KEEP_VERSIONS} نسخه‌ی قبلی نگه داشته میشود.",
                style = Divan.type.micro, color = c.textMuted,
            )
        }
    }
    if (confirm) AlertDialog(
        onDismissRequest = { confirm = false },
        containerColor = c.overlay,
        title = { Text("خطاخوان این نسخه پاک شود؟", style = Divan.type.h3) },
        text = { Text("همه‌ی ${current.size} مورد این نسخه از همین گوشی پاک میشوند (نسخه‌های قبلی میمانند). اگر هنوز برای توسعه‌دهنده نفرستاده‌ای، اول اشتراک بگذار.", style = Divan.type.small, color = c.textSecondary) },
        confirmButton = { HqButton("پاک کن", { log.clear(); confirm = false; toasts.info("خطاخوان پاک شد.") }, variant = BtnVariant.DANGER) },
        dismissButton = { HqButton("نه", { confirm = false }, variant = BtnVariant.GHOST) },
    )
}

/** One entry: what it was and where, its level, number and time at a glance; everything else when opened. */
@Composable
fun EntryCard(e: ErrorEntry, open0: Boolean = false) {
    val c = Divan.colors
    var open by rememberSaveable(e.id, e.at) { mutableStateOf(open0) }
    val kind = kindOf(e)
    HqCard(Modifier.fillMaxWidth(), padding = androidx.compose.foundation.layout.PaddingValues(14.dp), onClick = { open = !open }) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            val (bg, fg) = com.coinepro.hq.designsystem.toneColors(kind.tone)
            Box(Modifier.size(32.dp).clip(CircleShape).background(bg), contentAlignment = Alignment.Center) { DIcon(kind.icon, size = 16.dp, tint = fg) }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(kind.fa, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    if (e.count > 1) Text(if (e.kind == "unreachable") "${e.count} درخواست" else "${e.count} بار", style = Divan.type.micro, color = c.textMuted)
                }
                val line = when {
                    e.kind == "unreachable" -> "${ErrorLog.local(e.at).substringAfter(' ')} – ${ErrorLog.local(e.lastAt ?: e.at).substringAfter(' ')} · " +
                        e.tally.entries.sortedByDescending { it.value }.joinToString(", ") { "${it.key}×${it.value}" }
                    e.path != null -> listOfNotNull(e.method, e.path).joinToString(" ") + (e.status?.let { " → $it" } ?: "")
                    else -> e.detail ?: e.title.orEmpty()
                }
                Fig(line, style = Divan.type.figureSmall, color = c.textSecondary, maxLines = 2)
            }
            Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Pill(levelFa(e.level), levelTone(e.level), dot = true)
                Fig("#${e.id} · ${ErrorLog.local(e.lastAt ?: e.at).substring(11, 19)}", style = Divan.type.figureSmall, color = c.textMuted)
            }
        }
        com.coinepro.hq.designsystem.Expand(open) { Column(Modifier.padding(top = 12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Fact("زمان (تهران)", ErrorLog.local(e.at) + if (e.lastAt != null && e.lastAt != e.at) "  →  ${ErrorLog.local(e.lastAt)}" else "")
            Fact("زمان (UTC)", ErrorLog.utc(e.at) + if (e.lastAt != null && e.lastAt != e.at) "  →  ${ErrorLog.utc(e.lastAt)}" else "")
            Fact("شماره و سطح", "#${e.id} · ${e.level}" + if (e.count > 1) " · ×${e.count}" else "")
            Fact("نسخه‌ی اپ", e.app)
            e.screen?.let { Fact("صفحه", it) }
            listOfNotNull(e.foreground?.let { if (it) "foreground" else "background" }, e.network).takeIf { it.isNotEmpty() }?.let { Fact("اپ و شبکه", it.joinToString(" · ")) }
            if (e.path != null) Fact("درخواست", listOfNotNull(e.method, e.path).joinToString(" "))
            e.status?.let { Fact("کد پاسخ", it.toString()) }
            e.durationMs?.let { Fact("مدت", "$it ms") }
            if (e.code != null || e.title != null) Fact("خطا", listOfNotNull(e.code, e.title).joinToString(" — "))
            e.message?.let { Fact("پیام سرور", it, figure = false) }
            if (e.tally.isNotEmpty()) Fact("شکست‌ها", e.tally.entries.sortedByDescending { it.value }.joinToString(", ") { "${it.key} ×${it.value}" })
            if (e.paths.isNotEmpty()) Fact("درخواست‌ها", e.paths.joinToString("\n"))
            e.field?.let { Fact("فیلد", it) }
            e.detail?.let { Fact("جزئیات", it) }
            e.requestId?.let { Fact("شناسه‌ی درخواست", it) }
            if (e.headers.isNotEmpty()) Fact("سرآیندها", e.headers.entries.joinToString("\n") { "${it.key}: ${it.value}" })
            if (e.breadcrumbs.isNotEmpty()) Fact("پیش از آن", e.breadcrumbs.joinToString("\n"))
            e.stack?.let { st ->
                Text("ردِ پشته", style = Divan.type.micro, color = c.textMuted)
                // A stack trace reads left to right and scrolls from its left edge.
                androidx.compose.runtime.CompositionLocalProvider(androidx.compose.ui.platform.LocalLayoutDirection provides androidx.compose.ui.unit.LayoutDirection.Ltr) {
                    Box(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(10.dp)) {
                        Text(
                            st.lines().take(30).joinToString("\n"), Modifier.horizontalScroll(rememberScrollState()),
                            style = Divan.type.figureSmall.copy(fontWeight = FontWeight.Normal, textDirection = TextDirection.Ltr), color = c.textSecondary, softWrap = false,
                        )
                    }
                }
            }
        } }
    }
}

@Composable
private fun Fact(label: String, value: String, figure: Boolean = true) {
    val c = Divan.colors
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Text(label, style = Divan.type.micro, color = c.textMuted, modifier = Modifier.padding(top = 1.dp).width(96.dp))
        if (figure) Text(value, Modifier.weight(1f), style = Divan.type.figureSmall.copy(fontFamily = FigureFace, textDirection = TextDirection.Ltr), color = c.textPrimary, maxLines = 12, overflow = TextOverflow.Ellipsis)
        else Text(value, Modifier.weight(1f), style = Divan.type.caption, color = c.textPrimary)
    }
}

/** The settings card: how many errors and warnings this version has, and the way in. */
@Composable
fun ErrorLogCard(log: ErrorLog, onOpen: () -> Unit) {
    val c = Divan.colors
    val entries by log.entries.collectAsStateWithLifecycle()
    val serious = entries.filter { it.level != LEVEL_INFO }
    HqCard(Modifier.fillMaxWidth(), onClick = onOpen) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Box(Modifier.size(40.dp).clip(CircleShape).background(if (serious.isEmpty()) c.tile else c.softNegative), contentAlignment = Alignment.Center) {
                DIcon(DivanIcon.URGENT, size = 20.dp, tint = if (serious.isEmpty()) c.textSecondary else c.negative)
            }
            Column(Modifier.weight(1f)) {
                Text("خطاخوان", style = Divan.type.bodyStrong)
                Text(
                    if (serious.isEmpty()) "در این نسخه خطایی ثبت نشده" else "${serious.size} خطا و هشدار در این نسخه؛ آخرین ${ago(serious.first().lastAt ?: serious.first().at)}",
                    style = Divan.type.caption, color = c.textSecondary,
                )
            }
            DIcon(DivanIcon.NEXT, size = 18.dp, tint = c.textMuted)
        }
    }
}

private fun copyText(context: Context, label: String, text: String) {
    (context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText(label, text))
}

/** The report as a .txt under cache/shared, offered to any app through the system's share sheet. */
private fun shareReport(context: Context, text: String) {
    runCatching {
        val dir = File(context.cacheDir, "shared").apply { mkdirs() }
        val stamp = java.time.LocalDateTime.now().format(java.time.format.DateTimeFormatter.ofPattern("yyyyMMdd-HHmm"))
        val file = File(dir, "coinepro-hq-errors-$stamp.txt").apply { writeText(text) }
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.files", file)
        val send = Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_STREAM, uri).putExtra(Intent.EXTRA_SUBJECT, "CoinePro HQ — error log")
            .putExtra(Intent.EXTRA_TEXT, text.take(4000)).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        context.startActivity(Intent.createChooser(send, "خطاخوان").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }
}
