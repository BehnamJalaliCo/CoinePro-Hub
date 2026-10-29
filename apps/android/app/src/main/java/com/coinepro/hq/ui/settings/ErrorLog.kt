package com.coinepro.hq.ui.settings

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.background
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
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDirection
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.coinepro.hq.core.diag.ErrorEntry
import com.coinepro.hq.core.diag.ErrorLog
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FigureFace
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
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
    "crash" to KindFa("از کار افتادن اپ", Tone.NEG, DivanIcon.URGENT),
)

/**
 * «خطاخوان» (Settings): every failed call, every answer that did not match the contract (with the field the decoder stopped at),
 * and every crash, on this phone only, newest first. Copy all or share it as a text report for the developer; clear it once read.
 */
@Composable
fun ErrorLogScreen(log: ErrorLog) {
    val ctx = LocalContext.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val entries by log.entries.collectAsStateWithLifecycle()
    var confirm by remember { mutableStateOf(false) }
    Page {
        item {
            PageHeader("خطاخوان", eyebrow = "خطاهای API، ناسازگاری با قرارداد و از کار افتادن اپ؛ فقط روی همین گوشی") {
                HqButton("کپی همه", {
                    copyText(ctx, "error log", log.report(entries))
                    toasts.ok("گزارش کپی شد؛ برای توسعه‌دهنده بفرست.")
                }, size = BtnSize.SM, icon = DivanIcon.REPORT, enabled = entries.isNotEmpty())
                HqButton("اشتراک‌گذاری", { shareReport(ctx, log.report(entries)) }, size = BtnSize.SM, icon = DivanIcon.SHARE, enabled = entries.isNotEmpty())
                HqButton("پاک کردن", { confirm = true }, size = BtnSize.SM, variant = BtnVariant.GHOST, icon = DivanIcon.CLOSE, enabled = entries.isNotEmpty())
            }
        }
        item {
            Text(
                "هر خطا با زمان، نسخه‌ی اپ، صفحه، درخواست (شناسه‌ها پوشیده)، کد پاسخ و شناسه‌ی درخواست ثبت میشود؛ هیچ توکن، کلید، کوکی، متن پیام یا داده‌ی مشتری ثبت نمیشود. حداکثر ${ErrorLog.MAX} مورد آخر میماند.",
                style = Divan.type.caption, color = c.textMuted,
            )
        }
        if (entries.isEmpty()) item {
            HqCard(Modifier.fillMaxWidth()) { Empty("خطایی ثبت نشده", icon = DivanIcon.SEAL, body = "اگر جایی «پاسخ سرور با قرارداد نمیخواند» یا خطای دیگری دیدی، این‌جا با جزئیاتش میاید.") }
        }
        else {
            item {
                val counts = entries.groupingBy { it.kind }.eachCount()
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    for ((k, n) in counts) {
                        val kind = KINDS[k] ?: KindFa(k, Tone.NEUTRAL, DivanIcon.INFO)
                        Pill("${kind.fa}: $n", kind.tone, dot = true)
                    }
                }
            }
            items(entries, key = { it.id }) { e -> EntryCard(e) }
        }
    }
    if (confirm) AlertDialog(
        onDismissRequest = { confirm = false },
        containerColor = c.overlay,
        title = { Text("خطاخوان پاک شود؟", style = Divan.type.h3) },
        text = { Text("همه‌ی ${entries.size} مورد از همین گوشی پاک میشوند. اگر هنوز برای توسعه‌دهنده نفرستاده‌ای، اول اشتراک بگذار.", style = Divan.type.small, color = c.textSecondary) },
        confirmButton = { HqButton("پاک کن", { log.clear(); confirm = false; toasts.info("خطاخوان پاک شد.") }, variant = BtnVariant.DANGER) },
        dismissButton = { HqButton("نه", { confirm = false }, variant = BtnVariant.GHOST) },
    )
}

/** One failure: what it was and where, at a glance; the request, the field, the detail and the stack when opened. */
@Composable
fun EntryCard(e: ErrorEntry, open0: Boolean = false) {
    val c = Divan.colors
    var open by rememberSaveable(e.id) { mutableStateOf(open0) }
    val kind = KINDS[e.kind] ?: KindFa(e.kind, Tone.NEUTRAL, DivanIcon.INFO)
    HqCard(Modifier.fillMaxWidth().animateContentSize(), padding = androidx.compose.foundation.layout.PaddingValues(14.dp), onClick = { open = !open }) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            val (bg, fg) = com.coinepro.hq.designsystem.toneColors(kind.tone)
            Box(Modifier.size(32.dp).clip(CircleShape).background(bg), contentAlignment = Alignment.Center) { DIcon(kind.icon, size = 16.dp, tint = fg) }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(kind.fa, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                    if (e.count > 1) Text("${e.count} بار", style = Divan.type.micro, color = c.textMuted)
                }
                val line = when {
                    e.path != null -> listOfNotNull(e.method, e.path).joinToString(" ") + (e.status?.let { " → $it" } ?: "")
                    else -> e.detail.orEmpty()
                }
                Fig(line, style = Divan.type.figureSmall, color = c.textSecondary, maxLines = 2)
            }
            Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(ago(e.lastAt ?: e.at), style = Divan.type.micro, color = c.textMuted)
                e.code?.let { Fig(it, style = Divan.type.figureSmall, color = if (e.kind == "decode") c.negative else c.textMuted) }
            }
        }
        if (open) Column(Modifier.padding(top = 12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Fact("زمان", jDateTime(e.at) + (if (e.count > 1) "، آخرین بار ${jDateTime(e.lastAt)}" else ""), figure = false)
            Fact("نسخه‌ی اپ", e.app)
            e.screen?.let { Fact("صفحه", it) }
            if (e.path != null) Fact("درخواست", listOfNotNull(e.method, e.path).joinToString(" "))
            e.status?.let { Fact("کد پاسخ", it.toString()) }
            if (e.code != null || e.title != null) Fact("خطا", listOfNotNull(e.code, e.title).joinToString(" — "))
            e.field?.let { Fact("فیلد", it) }
            e.detail?.let { Fact("جزئیات", it) }
            e.requestId?.let { Fact("شناسه‌ی درخواست", it) }
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
        }
    }
}

@Composable
private fun Fact(label: String, value: String, figure: Boolean = true) {
    val c = Divan.colors
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Text(label, style = Divan.type.micro, color = c.textMuted, modifier = Modifier.padding(top = 1.dp).width(92.dp))
        if (figure) Text(value, Modifier.weight(1f), style = Divan.type.figureSmall.copy(fontFamily = FigureFace, textDirection = TextDirection.Ltr), color = c.textPrimary, maxLines = 6, overflow = TextOverflow.Ellipsis)
        else Text(value, Modifier.weight(1f), style = Divan.type.caption, color = c.textPrimary)
    }
}

/** The settings card: how many entries, and the way in. */
@Composable
fun ErrorLogCard(log: ErrorLog, onOpen: () -> Unit) {
    val c = Divan.colors
    val entries by log.entries.collectAsStateWithLifecycle()
    HqCard(Modifier.fillMaxWidth(), onClick = onOpen) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Box(Modifier.size(40.dp).clip(CircleShape).background(if (entries.isEmpty()) c.tile else c.softNegative), contentAlignment = Alignment.Center) {
                DIcon(DivanIcon.URGENT, size = 20.dp, tint = if (entries.isEmpty()) c.textSecondary else c.negative)
            }
            Column(Modifier.weight(1f)) {
                Text("خطاخوان", style = Divan.type.bodyStrong)
                Text(
                    if (entries.isEmpty()) "خطایی ثبت نشده" else buildAnnotatedString {
                        append("${entries.size} خطا ثبت شده؛ آخرین ${ago(entries.first().lastAt ?: entries.first().at)}")
                    }.text,
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
