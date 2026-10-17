package com.coinepro.hq.ui.v14

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipRect
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.designsystem.BarTone
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.MeterBar
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.RichText
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import java.util.Locale

// Shared pieces of the v1.4 sections (contract §18), mirroring apps/web/src/components/v14/bits.tsx.

data class Label(val fa: String, val tone: Tone, val live: Boolean = false)

@Composable
fun LabelPill(l: Label?, fallback: String = "", modifier: Modifier = Modifier) {
    val v = l ?: Label(fallback, Tone.NEUTRAL)
    Pill(v.fa, v.tone, modifier, live = v.live, dot = !v.live)
}

val SEVERITY = linkedMapOf(
    "critical" to Label("بحرانی", Tone.NEG), "high" to Label("بالا", Tone.NEG), "medium" to Label("متوسط", Tone.WARN),
    "low" to Label("کم", Tone.NEUTRAL), "info" to Label("اطلاع", Tone.LAPIS),
)
val SEVERITY_ORDER = SEVERITY.keys.toList()

@Composable
fun SeverityPill(s: String) = LabelPill(SEVERITY[s], s)

val FINDING_STATUS = mapOf(
    "open" to Label("باز", Tone.NEG), "acknowledged" to Label("پذیرفته", Tone.WARN), "fixing" to Label("در حال رفع", Tone.LAPIS, live = true),
    "fixed" to Label("رفع شد؛ منتظر تأیید", Tone.GOLD), "verified" to Label("تأیید شد", Tone.POS), "disputed" to Label("مورد اعتراض", Tone.WARN), "closed" to Label("بسته", Tone.NEUTRAL),
)
val CHALLENGE_STATUS = mapOf(
    "issued" to Label("صادر شد", Tone.NEUTRAL), "accepted" to Label("پذیرفته", Tone.LAPIS), "submitted" to Label("تحویل شد", Tone.GOLD),
    "scored" to Label("داوری شد", Tone.POS), "missed" to Label("از دست رفت", Tone.NEG),
)
val ORDER_STATUS = mapOf("proposed" to Label("منتظر مُهر", Tone.GOLD), "sealed" to Label("مُهرشده", Tone.POS), "retired" to Label("بازنشسته", Tone.NEUTRAL))
val ERRAND_STATUS = mapOf(
    "queued" to Label("در صف", Tone.NEUTRAL), "working" to Label("در حال انجام", Tone.LAPIS, live = true), "waiting_owner" to Label("منتظر مُهر تو", Tone.GOLD),
    "done" to Label("انجام شد", Tone.POS), "failed" to Label("انجام نشد", Tone.NEG), "cancelled" to Label("لغو شد", Tone.NEUTRAL),
)
val SKILL_STATUS = mapOf(
    "draft" to Label("پیش‌نویس", Tone.NEUTRAL), "in_review" to Label("در بررسی ناظر", Tone.LAPIS), "approved" to Label("آماده‌ی مُهر", Tone.GOLD),
    "active" to Label("فعال", Tone.POS), "retired" to Label("بازنشسته", Tone.NEUTRAL),
)
val TEACH_STATUS = mapOf(
    "drafting" to Label("در حال نوشتن", Tone.LAPIS, live = true), "proposed" to Label("منتظر تأیید تو", Tone.GOLD),
    "approved" to Label("تأیید شد", Tone.POS), "rejected" to Label("رد شد", Tone.NEUTRAL),
)
val FOUNDING_STATE = linkedMapOf(
    "auditing" to Label("در حال ممیزی", Tone.LAPIS, live = true), "proposed" to Label("پیشنهاد، منتظر مُهر", Tone.GOLD), "sealed" to Label("مُهر شد", Tone.POS),
    "provisioning" to Label("ساخت سرور", Tone.LAPIS, live = true), "ready_for_login" to Label("آماده‌ی ورود تو", Tone.GOLD), "active" to Label("فعال", Tone.POS),
    "cancelled" to Label("لغو شد", Tone.WARN),
)

val AREA_FA = mapOf(
    "truth" to "حقیقت", "authority" to "اختیار", "money" to "پول و توکن", "safety" to "ایمنی", "quality" to "کیفیت", "delivery" to "تحویل",
    "security" to "امنیت", "data" to "داده", "people" to "آدم‌ها", "product" to "محصول", "owner" to "دستور مالک",
)
val METHOD_FA = mapOf(
    "rule" to "قاعده", "reconcile" to "تطبیق", "sample" to "نمونه‌برداری", "llm" to "تحلیل", "blind_test" to "آزمون کور", "mystery" to "مشتری ناشناس", "drill" to "مانور",
)

/** "FREQ=DAILY;BYHOUR=9" → "هر روز 09:00" (owner's zone), enough for a list. */
fun rruleFa(r: String): String {
    val k = r.split(';').mapNotNull { p -> p.split('=').takeIf { it.size == 2 }?.let { it[0] to it[1] } }.toMap()
    val hm = k["BYHOUR"]?.let { " ${it.padStart(2, '0')}:${(k["BYMINUTE"] ?: "0").padStart(2, '0')}" } ?: ""
    val days = mapOf("SA" to "شنبه", "SU" to "یکشنبه", "MO" to "دوشنبه", "TU" to "سه‌شنبه", "WE" to "چهارشنبه", "TH" to "پنجشنبه", "FR" to "جمعه")
    return when (k["FREQ"]) {
        "HOURLY" -> "هر ساعت"
        "DAILY" -> "هر روز$hm"
        "WEEKLY" -> (days[k["BYDAY"]]?.let { "$it\u200Cها" } ?: "هر هفته") + hm
        "MONTHLY" -> "ماهانه، روز ${k["BYMONTHDAY"] ?: "1"}$hm"
        else -> r
    }
}

/** 1.8 GB, 6.0 TB — a figure. */
fun bytes(b: Long): String = if (b >= 1_000_000_000_000L) String.format(Locale.US, "%.1f TB", b / 1e12) else String.format(Locale.US, "%.1f GB", b / 1e9)

/** The academy's score bands, used for every 0–100 score in the holding. */
fun scoreTone(v: Double): BarTone = when {
    v >= 80 -> BarTone.POS
    v >= 65 -> BarTone.WARN
    else -> BarTone.NEG
}

/** A 0–100 score as a number and a thin bar. */
@Composable
fun ScoreBar(value: Double, modifier: Modifier = Modifier) {
    Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Fig(value.toInt().toString(), Modifier.width(26.dp), style = Divan.type.figureSmall, color = Divan.colors.textPrimary)
        MeterBar(value, Modifier.weight(1f), tone = scoreTone(value), height = 5.dp)
    }
}

/** 0–5 stars filled to the value from the reading start; the value is also written out (never shape alone). */
@Composable
fun StarsRow(value: Double, modifier: Modifier = Modifier, size: Dp = 14.dp, label: Boolean = true) {
    val c = Divan.colors
    val v = value.coerceIn(0.0, 5.0)
    val frac = (v / 5).toFloat()
    Row(modifier.semantics { contentDescription = "${String.format(Locale.US, "%.1f", v)} از ۵ ستاره" }, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Box {
            Row { repeat(5) { DIcon(DivanIcon.STAR, size = size, tint = c.lineStrong) } }
            Row(
                Modifier.drawWithContent {
                    val w = this.size.width * frac
                    if (layoutDirection == LayoutDirection.Rtl) clipRect(left = this.size.width - w) { this@drawWithContent.drawContent() }
                    else clipRect(right = w) { this@drawWithContent.drawContent() }
                },
            ) { repeat(5) { DIcon(DivanIcon.STAR, size = size, tint = c.goldInk, active = true) } }
        }
        if (label) Fig(String.format(Locale.US, "%.1f", v), style = Divan.type.figureSmall, color = c.textSecondary)
    }
}

/** A small trend line: one series, no axes, the last point marked; time runs left to right. */
@Composable
fun Spark(values: List<Double>, modifier: Modifier = Modifier, width: Dp = 64.dp, height: Dp = 20.dp, min: Double? = null, max: Double? = null) {
    if (values.size < 2) return
    val c = Divan.colors
    val hi = max ?: values.max()
    val lo = min ?: values.min()
    val span = (hi - lo).takeIf { it > 0 } ?: 1.0
    val col = if (values.last() >= values.first()) c.positive else c.negative
    val ring = c.card
    Canvas(modifier.size(width, height)) {
        val pad = 3.dp.toPx()
        val pts = values.mapIndexed { i, v -> Offset(pad + i * (size.width - 2 * pad) / (values.size - 1), size.height - pad - ((v - lo) / span).toFloat() * (size.height - 2 * pad)) }
        val path = Path().apply { moveTo(pts[0].x, pts[0].y); for (p in pts.drop(1)) lineTo(p.x, p.y) }
        drawPath(path, col, style = Stroke(2.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
        drawCircle(ring, 4.dp.toPx(), pts.last())
        drawCircle(col, 2.8.dp.toPx(), pts.last())
    }
}

/** A small tag (a tool, a department, a criterion). */
@Composable
fun Tag(text: String, modifier: Modifier = Modifier, figure: Boolean = false) {
    val c = Divan.colors
    Box(modifier.clip(RoundedCornerShape(50)).background(c.tile).padding(horizontal = 8.dp, vertical = 2.dp)) {
        if (figure) Fig(text, style = Divan.type.figureSmall, color = c.textSecondary) else Text(text, style = Divan.type.micro, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

/** A bottom sheet with a title (its [ref] as a Latin figure above it), an optional line under it, scrolling content
 *  and the action at the end. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HqSheet(onDismiss: () -> Unit, title: String, sub: String? = null, ref: String? = null, content: @Composable ColumnScope.() -> Unit) {
    val c = Divan.colors
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true), containerColor = c.overlay) {
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).imePadding().padding(horizontal = 16.dp).padding(bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                if (ref != null) Fig(ref, style = Divan.type.figureSmall, color = c.textMuted)
                RichText(title, style = Divan.type.h2, color = c.textPrimary)
                if (sub != null) Text(sub, style = Divan.type.caption, color = c.textMuted)
            }
            content()
        }
    }
}

private val NUMBER = Regex("(?:[≥≤<>~±+−-]\\s?)?\\d[\\d.,/:]*(?:\\s?[%٪])?")

/** Mixed text such as a KPI target ("500 در 90 روز", "≥ 80%"): every number is a Latin figure, the words stay in
 *  their right-to-left order. */
fun figs(text: String): AnnotatedString = buildAnnotatedString {
    var last = 0
    for (m in NUMBER.findAll(text)) {
        append(text.substring(last, m.range.first))
        fig(m.value)
        last = m.range.last + 1
    }
    append(text.substring(last))
}

/** The owner's voice or text, as the composer hands it over: a lone file id without files allowed is the voice. */
data class Spoken(val text: String, val source: String, val fileId: String?)

fun spoken(body: String, attachments: List<String>): Spoken = Spoken(body, if (attachments.isNotEmpty()) "voice" else "text", attachments.firstOrNull())
