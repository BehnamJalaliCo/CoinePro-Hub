package com.coinepro.hq.ui.v16

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.InlineTextContent
import androidx.compose.foundation.text.appendInlineContent
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.Placeholder
import androidx.compose.ui.text.PlaceholderVerticalAlign
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.GUARD_FA
import com.coinepro.hq.core.net.NO_OVERRIDE
import com.coinepro.hq.core.net.RuleTrigger
import com.coinepro.hq.core.net.faError
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.ActionRunner
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Toasts
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.v14.Label
import com.coinepro.hq.ui.v14.rruleFa
import java.util.Locale
import kotlin.math.roundToInt

// Shared pieces of the v1.5 sections (contract §19), mirroring apps/web/src/components/v16/bits.tsx.

// ------------------------------------------------------------------ labels --
val CHANNEL_FA = mapOf(
    "telegram_business" to "تلگرام بیزینس", "telegram_bot" to "ربات پشتیبانی تلگرام", "chatwoot" to "چت سایت (Chatwoot)", "product_bot" to "ربات محصول",
    "mystery" to "مشتری ناشناس ناظر",
)
val CHANNEL_STATE = mapOf(
    "not_configured" to Label("راه‌اندازی نشده", Tone.NEUTRAL), "shadow" to Label("سایه، بی‌ارسال", Tone.LAPIS),
    "live" to Label("روشن", Tone.POS, live = true), "paused" to Label("متوقف", Tone.WARN),
)
/** What may leave without the owner, and what that means. */
val AUTO_SEND = mapOf(
    "kb_verbatim" to ("فقط عین دانشنامه" to "فقط جواب‌هایی که عیناً یک مقاله‌ی تأییدشده‌اند بی‌تو میروند."),
    "kb_grounded" to ("پیش‌نویس مستند هم" to "پیش‌نویسی هم که هر دو چک را پاس کرده و اطمینانش از آستانه بالاتر است بی‌تو میرود."),
    "off" to ("هیچ" to "هیچ چیز بی‌تو نمیرود؛ همه در صف آموزش میمانند."),
)
val CONV_STATE = mapOf(
    "open" to Label("باز", Tone.NEUTRAL), "waiting_owner" to Label("منتظر تو", Tone.GOLD), "answered" to Label("جواب داده شد", Tone.POS), "closed" to Label("بسته", Tone.NEUTRAL),
)
val HANDOFF_FA = mapOf(
    "no_kb" to Label("مقاله نبود", Tone.NEUTRAL), "low_confidence" to Label("اطمینان کم", Tone.WARN), "blocked" to Label("رد نگهبان", Tone.NEG),
    "asked_for_human" to Label("آدم خواست", Tone.LAPIS), "complaint" to Label("شکایت", Tone.WARN), "security" to Label("امنیتی", Tone.NEG),
)
val MSG_STATUS = mapOf(
    "draft" to Label("پیش‌نویس، منتظر تو", Tone.GOLD), "queued" to Label("در صف", Tone.NEUTRAL), "sent" to Label("فرستاده شد", Tone.POS),
    "blocked" to Label("رد نگهبان، فرستاده نشد", Tone.NEG), "failed" to Label("ناموفق", Tone.NEG),
)
val AUTHOR_FA = mapOf("customer" to "مشتری", "agent" to "ایجنت پشتیبانی", "owner" to "تو", "rule" to "قاعده")
val QUEUE_KIND = mapOf(
    "handoff" to Label("به تو سپرده شد", Tone.GOLD), "low_confidence" to Label("اطمینان کم", Tone.WARN), "blocked" to Label("رد نگهبان", Tone.NEG),
    "shadow_disagreement" to Label("اختلاف آزمون سایه", Tone.LAPIS),
)
val KB_KIND = linkedMapOf("faq" to "پرسش رایج", "policy" to "سیاست", "procedure" to "روال", "referral" to "رفرال", "official_link" to "لینک رسمی", "safety" to "ایمنی")
val KB_STATUS = linkedMapOf(
    "proposed" to Label("منتظر تأیید", Tone.GOLD), "approved" to Label("تأییدشده", Tone.POS), "expired" to Label("منقضی", Tone.WARN), "retired" to Label("بازنشسته", Tone.NEUTRAL),
)
val KB_SOURCE = mapOf("owner_answer" to "از جواب تو", "owner" to "نوشته‌ی تو", "doc" to "از سند", "agent" to "پیشنهاد ایجنت")
val PURPOSE_FA = linkedMapOf(
    "holding_reply" to "پاسخ انتظار", "safety" to "جمله‌ی ایمنی", "welcome" to "خوش‌آمد", "reactivation" to "بازگشت", "rescue" to "نجات رفرال", "nps" to "NPS", "csat" to "رضایت",
)
val TEMPLATE_STATUS = mapOf("proposed" to Label("منتظر مُهر", Tone.GOLD), "sealed" to Label("مُهرشده", Tone.POS), "retired" to Label("بازنشسته", Tone.NEUTRAL))
val RULE_STATUS = mapOf("proposed" to Label("منتظر مُهر", Tone.GOLD), "active" to Label("فعال", Tone.POS), "paused" to Label("متوقف", Tone.WARN))
val RESCUE_STATE = linkedMapOf(
    "open" to Label("باز", Tone.LAPIS), "contacted" to Label("پیگیری شد", Tone.GOLD), "rescued" to Label("نجات یافت", Tone.POS), "lost" to Label("از دست رفت", Tone.NEG),
    "opted_out" to Label("لغو کرد", Tone.NEUTRAL),
)
val RESCUE_STEP = mapOf("check" to "چک UID", "message" to "پیام", "follow_up" to "پیگیری", "note" to "یادداشت")
val FEEDBACK_KIND = linkedMapOf(
    "bug" to Label("باگ", Tone.NEG), "feature" to Label("قابلیت تازه", Tone.LAPIS), "confusion" to Label("ابهام", Tone.WARN), "complaint" to Label("شکایت", Tone.WARN),
    "praise" to Label("تعریف", Tone.POS),
)
val FEEDBACK_STATE = linkedMapOf(
    "new" to Label("تازه", Tone.GOLD), "triaged" to Label("بررسی شد", Tone.LAPIS), "in_backlog" to Label("در صف کار", Tone.NEUTRAL), "done" to Label("انجام شد", Tone.POS),
    "wont_do" to Label("انجام نمیشود", Tone.NEUTRAL),
)
val INTAKE_KIND = linkedMapOf("telegram" to "تلگرام", "chatwoot" to "Chatwoot", "product" to "رویداد محصول")
val ALERT_FA = mapOf("drop" to ("افت کمیسیون" to DivanIcon.CHART), "pull_failed" to ("pull ناموفق" to DivanIcon.REFRESH), "incomplete" to ("روز ناقص" to DivanIcon.TIME))
val EVENT_FA = mapOf("signup" to "ثبت‌نام", "referral_failed" to "رفرال ناموفق", "conversation_closed" to "بسته شدن گفت‌وگو")

/** A rule's trigger in one line: the event (and its delay), the inactivity, or the calendar. Hours and days are prose counts. */
fun triggerFa(t: RuleTrigger): String = when {
    t.rrule != null -> if ("FREQ=MONTHLY" in t.rrule && "INTERVAL=3" in t.rrule) "فصلی، روز اول" else rruleFa(t.rrule)
    t.inactiveDays != null -> "بعد از ${t.inactiveDays} روز بی‌فعالیتی"
    t.event != null -> "بعد از ${EVENT_FA[t.event] ?: t.event}" + (t.afterHours?.takeIf { it > 0 }?.let { "، $it ساعت بعد" } ?: "")
    else -> "—"
}

// ----------------------------------------------------------------- figures --
/** USDT and dollars from decimal strings: Latin, two decimals, grouped ("12,601.14"). */
fun money(v: String?): String = v?.toDoubleOrNull()?.let(::money) ?: "—"

fun money(v: Double): String = if (v.isFinite()) String.format(Locale.US, "%,.2f", v) else "—"

/** Axis ticks: 0 / 250 / 1.2K. */
fun compact(v: Double): String = when {
    v >= 1000 -> String.format(Locale.US, if (v >= 10_000) "%.0f" else "%.1f", v / 1000).removeSuffix(".0") + "K"
    else -> v.roundToInt().toString()
}

/** A 0..1 rate as a Latin figure ("38%"); null stays a dash, never an estimate. */
fun rate(r: Double?): String = if (r == null || !r.isFinite()) "—" else "${(r * 100).roundToInt()}%"

// A run of Latin: words, refs (CR-005, SC-000411, TM-0003@2), numbers with their unit ("94.16 USDT", "40%"), kept together left to right.
private val LATIN = Regex("[A-Za-z0-9$+−][\\w.$%/:+−@-]*(?:[ \\t]+[A-Za-z0-9$][\\w.$%/:+−@-]*)*")

/** Server prose (alerts, notes): Persian words read right to left; every Latin run and figure is one left-to-right figure. */
fun prose(text: String, color: Color? = null): AnnotatedString = buildAnnotatedString { appendProse(text, color) }

fun AnnotatedString.Builder.appendProse(text: String, color: Color? = null) {
    var last = 0
    for (m in LATIN.findAll(text)) {
        append(text.substring(last, m.range.first))
        // A full stop or comma after a figure ends the sentence; it stays outside the left-to-right run.
        val run = m.value.trimEnd('.', ',', ':')
        fig(run, color)
        append(m.value.substring(run.length))
        last = m.range.last + 1
    }
    append(text.substring(last))
}

private val MASK = Regex("\\[(?:ماسک|masked)[^\\]]*\\]")
private const val LOCK = "lock"

/** Customer text as stored: masked parts ([ماسک: …]) stand out with a lock, so a masked secret is never mistaken for text; links,
 *  codes and figures stay Latin. */
@Composable
fun Masked(text: String, modifier: Modifier = Modifier, style: TextStyle = Divan.type.body, color: Color = Divan.colors.textPrimary, maxLines: Int = Int.MAX_VALUE) {
    val c = Divan.colors
    val shown = remember(text, c) {
        buildAnnotatedString {
            var last = 0
            for (m in MASK.findAll(text)) {
                appendProse(text.substring(last, m.range.first))
                withStyle(SpanStyle(background = c.tile, color = c.textMuted, fontSize = 12.sp)) {
                    append(" ")
                    appendInlineContent(LOCK, "قفل")
                    append(" " + m.value.drop(1).dropLast(1) + " ")
                }
                last = m.range.last + 1
            }
            appendProse(text.substring(last))
        }
    }
    val inline = remember(c) {
        mapOf(LOCK to InlineTextContent(Placeholder(12.sp, 12.sp, PlaceholderVerticalAlign.TextCenter)) { DIcon(DivanIcon.LOCK, size = 12.dp, tint = c.textMuted) })
    }
    Text(shown, modifier, style = style, color = color, maxLines = maxLines, overflow = TextOverflow.Ellipsis, inlineContent = inline)
}

/** The outbound guard's refusals in Persian; the three without any exception say so. */
@Composable
fun GuardReasons(reasons: List<String>, modifier: Modifier = Modifier) {
    if (reasons.isEmpty()) return
    val c = Divan.colors
    val hard = reasons.any { it in NO_OVERRIDE }
    Column(modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.softNegative).padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DIcon(DivanIcon.LOCK, size = 16.dp, tint = c.negative)
            Text("نگهبان خروجی رد کرد", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.negative)
        }
        for (r in reasons) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Box(Modifier.padding(top = 8.dp).size(5.dp).clip(CircleShape).background(c.negative))
            Text(buildAnnotatedString { append((GUARD_FA[r] ?: r) + "  "); fig(r, c.textMuted) }, style = Divan.type.small, color = c.textPrimary, modifier = Modifier.weight(1f))
        }
        Text(
            if (hard) "برای این مورد هیچ استثنایی نیست، حتی برای تو؛ متن را عوض کن تا نگهبان دوباره بسنجد." else "متن را اصلاح کن و دوباره بفرست؛ نگهبان دوباره میسنجد.",
            style = Divan.type.caption, color = c.textSecondary,
        )
    }
}

/** A small tag of server text (a conversation tag, a question's variant): Persian words, any Latin run or figure kept Latin. */
@Composable
fun ProseTag(text: String, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Box(modifier.clip(RoundedCornerShape(50)).background(c.tile).padding(horizontal = 8.dp, vertical = 2.dp)) {
        Text(prose(text), style = Divan.type.micro, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

/** A labelled fact in a tile; [figure] sets the value as a Latin figure. */
@Composable
fun Fact(label: String, value: String, modifier: Modifier = Modifier, figure: Boolean = false, color: Color? = null) {
    val c = Divan.colors
    Column(modifier.clip(RoundedCornerShape(12.dp)).background(c.tile).padding(horizontal = 12.dp, vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(label, style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
        if (figure) Fig(value, style = Divan.type.figure, color = color ?: c.textPrimary, maxLines = 2)
        // Prose: counts and dates keep the text face's Persian digits; Latin words read as they are.
        else Text(com.coinepro.hq.designsystem.timesFig(value), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = color ?: c.textPrimary)
    }
}

/** Facts two to a row. */
@Composable
fun FactRows(facts: List<@Composable (Modifier) -> Unit>, perRow: Int = 2) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        for (row in facts.chunked(perRow)) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            for (f in row) f(Modifier.weight(1f))
            repeat(perRow - row.size) { Box(Modifier.weight(1f)) }
        }
    }
}

/** A filter chip in FilterChip's style with any content (a mark, a Latin figure); [ink] is the content colour for its state. */
@Composable
fun Chip(selected: Boolean, onClick: () -> Unit, content: @Composable RowScope.(ink: Color) -> Unit) {
    val c = Divan.colors
    Row(
        Modifier
            .height(32.dp)
            .clip(CircleShape)
            .background(if (selected) c.softGold else Color.Transparent)
            .border(1.dp, if (selected) c.lineTahrir else c.lineStrong, CircleShape)
            .selectable(selected, role = Role.Tab, onClick = onClick)
            .padding(horizontal = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) { content(if (selected) c.goldInk else c.textSecondary) }
}

/** A filter chip for one company: its mark and its name (companies are data; any number of them). */
@Composable
fun CoChip(code: String, name: String, selected: Boolean, onClick: () -> Unit) {
    Chip(selected, onClick) { ink ->
        CompanyMark(code, height = 12.dp, mono = true, ink = ink)
        Text(name, style = Divan.type.small.copy(fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal), color = ink, maxLines = 1)
    }
}

/** The company filter: the operating companies from the API, plus «همه‌ی شرکت‌ها» when [all]. Scrolls sideways on a phone. */
@Composable
fun CompanyChips(value: String?, onChange: (String?) -> Unit, all: Boolean = true) {
    val list = rememberCompanies().filter { it.kind != "holding" }
    ChipRow {
        if (all) FilterChip("همه‌ی شرکت‌ها", value == null, { onChange(null) })
        for (co in list) CoChip(co.code, co.nameFa ?: co.code, value == co.code) { onChange(co.code) }
    }
}

/** A company's chart colour: its stored slot in the categorical palette; none = neutral silver (never by rank). */
@Composable
fun companyColor(code: String): Color {
    val c = Divan.colors
    val i = rememberCompanies().firstOrNull { it.code == code }?.colorIndex
    return if (i != null && i in 1..c.chart.size) c.chart[i - 1] else c.silverInk
}

/** A row of chips that scrolls sideways (phone width). */
@Composable
fun ChipRow(content: @Composable () -> Unit) {
    com.coinepro.hq.designsystem.ScrollRow { content() }
}

/** A label above a field. */
@Composable
fun Labelled(label: String, modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(label, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = Divan.colors.textSecondary)
        content()
    }
}

/** A command the owner runs in their own terminal: left to right, one tap copies it. Never a secret, only its name and target. */
@Composable
fun TerminalCommand(text: String, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val ctx = LocalContext.current
    val toasts = LocalToasts.current
    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
        Row(
            modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.page).border(1.dp, c.lineDivider, RoundedCornerShape(10.dp)).padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Fig("$", style = Divan.type.figureSmall, color = c.textMuted)
            Fig(text, Modifier.weight(1f), style = Divan.type.figureSmall, color = c.textPrimary, maxLines = 2)
            Text("کپی", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk, modifier = Modifier.clip(RoundedCornerShape(6.dp)).clickable(role = Role.Button) {
                (ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText("command", text))
                toasts.ok("کپی شد.")
            }.padding(horizontal = 6.dp, vertical = 2.dp))
        }
    }
}

/** A soft box with an icon: a warning, a refusal, a note. */
@Composable
fun Notice(icon: DivanIcon, bg: Color, tint: Color, modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Row(modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(bg).padding(12.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        DIcon(icon, size = 18.dp, tint = tint, modifier = Modifier.padding(top = 2.dp))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp), content = content)
    }
}

/** A §19 action: a failed call says its §19.9 code in Persian ([faError]) instead of the server's sentence. */
fun ActionRunner.go(toasts: Toasts, onError: ((ApiException) -> Boolean)? = null, block: suspend () -> Unit) =
    run(onError = { e -> if (onError?.invoke(e) != true) toasts.error(faError(e)) }, block = block)
