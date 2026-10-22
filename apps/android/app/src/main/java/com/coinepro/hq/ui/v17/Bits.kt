package com.coinepro.hq.ui.v17

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.agentKindOf
import com.coinepro.hq.core.format.deptOf
import com.coinepro.hq.core.format.instant
import com.coinepro.hq.core.format.tokens
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.core.net.Actor
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.govError
import com.coinepro.hq.designsystem.Avatar
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.Monogram
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.ActionRunner
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.Toasts
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.v14.Label
import com.coinepro.hq.ui.v16.Chip
import com.coinepro.hq.ui.v16.ChipRow
import java.util.Locale
import kotlin.math.abs
import kotlin.math.roundToInt
import kotlin.math.roundToLong
import kotlinx.coroutines.delay

// Shared pieces of the governance sections (contract §20), mirroring apps/web/src/components/v17/bits.tsx.

// ------------------------------------------------------------------ labels --
data class Named(val fa: String, val icon: DivanIcon)

val MEETING_TYPE = linkedMapOf(
    "board" to Named("هیئت‌مدیره", DivanIcon.HOLDING), "company" to Named("مدیریت شرکت", DivanIcon.COMPANIES), "standup" to Named("استندآپ", DivanIcon.TIME),
    "war_room" to Named("اتاق جنگ", DivanIcon.URGENT), "postmortem" to Named("کالبدشکافی", DivanIcon.SEARCH), "strategy" to Named("استراتژی", DivanIcon.CHART),
)
val MEETING_STATE = mapOf(
    "scheduled" to Label("زمان‌بندی‌شده", Tone.NEUTRAL), "prep" to Label("دستور آماده", Tone.LAPIS), "live" to Label("زنده", Tone.POS, live = true),
    "closing" to Label("جمع‌بندی", Tone.WARN, live = true), "ended" to Label("تمام شد", Tone.NEUTRAL), "cancelled" to Label("لغو شد", Tone.NEUTRAL),
)
val CLAIM_STATUS = mapOf(
    "sourced" to Label("با منبع", Tone.POS), "unsourced" to Label("بی‌منبع؛ بیرون از مصوبه", Tone.NEG),
    "challenged" to Label("به چالش کشیده شد", Tone.WARN), "withdrawn" to Label("پس گرفته شد", Tone.NEUTRAL),
)
val CLAIM_ICON = mapOf("sourced" to DivanIcon.SEAL, "unsourced" to DivanIcon.URGENT, "challenged" to DivanIcon.SEARCH, "withdrawn" to DivanIcon.CLOSE)
val VOTE_FA = mapOf("support" to Label("موافق", Tone.POS), "oppose" to Label("مخالف", Tone.NEG), "abstain" to Label("ممتنع", Tone.NEUTRAL))
val PRESENCE_FA = linkedMapOf(
    "live" to ("زنده" to "استریم و ورود صوتی"), "summary" to ("خلاصه" to "فقط خلاصه بعد از جلسه"), "audio" to ("نسخه‌ی صوتی" to "تا text-to-speech بیاید مثل خلاصه"),
)
val CHARTER_STATUS = mapOf("proposed" to Label("پیشنهادی، منتظر مُهر", Tone.GOLD), "sealed" to Label("مُهرشده", Tone.POS), "superseded" to Label("جایگزین شد", Tone.NEUTRAL))
val LAYER_FA = linkedMapOf(
    "holding" to Named("هلدینگ", DivanIcon.HOLDING), "company" to Named("شرکت", DivanIcon.COMPANIES), "department" to Named("دپارتمان", DivanIcon.DEPARTMENT),
    "employee" to Named("کارمند", DivanIcon.MEMORY),
)
val KNOWLEDGE_KIND = linkedMapOf("principle" to "اصل", "policy" to "سیاست", "fact" to "واقعیت", "faq" to "پرسش رایج", "playbook" to "روش کار (Playbook)", "support" to "مقاله‌ی پشتیبانی")
val KNOWLEDGE_STATUS = linkedMapOf(
    "draft" to Label("پیش‌نویس", Tone.NEUTRAL), "in_review" to Label("در بازبینی", Tone.LAPIS), "approved" to Label("تأییدشده", Tone.POS),
    "expired" to Label("منقضی", Tone.WARN), "retired" to Label("بازنشسته", Tone.NEUTRAL),
)
val REVIEW_VERDICT = mapOf("pass" to Label("قبول", Tone.POS), "changes" to Label("اصلاح لازم", Tone.WARN), "reject" to Label("رد", Tone.NEG))
val REVIEW_CHECK = linkedMapOf("injection" to "تزریق دستور", "secrets" to "رمز و کلید", "conflicts" to "تناقض با اساسنامه", "policy" to "اختیار و سیاست")
data class CardMeta(val fa: String, val icon: DivanIcon, val note: String)
val CARD_FA = linkedMapOf(
    "stability" to CardMeta("پایداری", DivanIcon.SERVER, "سلامت سرویس‌ها و حادثه‌ها"),
    "growth" to CardMeta("رشد", DivanIcon.CHART, "درآمد، کاربر و قیف"),
    "safety_cost" to CardMeta("ایمنی و هزینه", DivanIcon.TREASURY, "توکن، بودجه و نظارت"),
)
val KPI_STATE = mapOf("ok" to Label("تازه", Tone.POS), "stale" to Label("قدیمی", Tone.WARN), "no_source" to Label("منبع وصل نیست", Tone.NEUTRAL))
val OBJECTIVE_STATUS = mapOf("draft" to Label("پیش‌نویس", Tone.NEUTRAL), "proposed" to Label("منتظر مُهر", Tone.GOLD), "active" to Label("فعال", Tone.POS), "closed" to Label("بسته", Tone.NEUTRAL))
val VERDICT = linkedMapOf(
    "pending" to Label("منتظر سنجش", Tone.NEUTRAL), "met" to Label("رسید", Tone.POS), "partly" to Label("نیمه‌راه", Tone.WARN), "missed" to Label("نرسید", Tone.NEG),
    "unmeasurable" to Label("سنجش‌ناپذیر", Tone.LAPIS),
)
val OUTCOME_STATUS = mapOf("due" to "موعد سنجش", "answered" to "یادداشت پیشنهاددهنده رسید", "verified" to "تأییدشده")
val RISK_CATEGORY = linkedMapOf(
    "product" to "محصول", "security" to "امنیت", "data" to "داده", "money" to "پول", "people" to "آدم‌ها", "vendor" to "تأمین‌کننده", "ops" to "عملیات", "reputation" to "اعتبار",
)
val RISK_STATUS = linkedMapOf("open" to Label("باز", Tone.NEG), "mitigating" to Label("در حال کاهش", Tone.LAPIS), "accepted" to Label("پذیرفته‌شده", Tone.GOLD), "closed" to Label("بسته", Tone.NEUTRAL))
val CAL_KIND = linkedMapOf(
    "deploy" to Named("انتشار", DivanIcon.SERVER), "freeze" to Named("فریز", DivanIcon.PAUSE), "campaign" to Named("کمپین", DivanIcon.SEND), "event" to Named("رویداد", DivanIcon.STAR),
    "maintenance" to Named("نگه‌داری", DivanIcon.SETTINGS), "meeting" to Named("جلسه", DivanIcon.MEETING), "holiday" to Named("تعطیل", DivanIcon.SLEEPING),
)
val CAL_STATUS = mapOf("planned" to "برنامه", "done" to "انجام شد", "cancelled" to "لغو شد")
val CAL_RISK = mapOf("low" to Label("ریسک کم", Tone.POS), "medium" to Label("ریسک متوسط", Tone.WARN), "high" to Label("ریسک بالا", Tone.NEG))
val CONFLICT_RULE = mapOf(
    "deploy_in_freeze" to "انتشار داخل فریز", "deploy_in_campaign" to "انتشار هم‌زمان با کمپین یا رویداد", "two_deploys" to "دو انتشار هم‌زمان",
    "deploy_on_blackout_day" to "انتشار در روز ممنوع", "deploy_on_holiday" to "انتشار در تعطیلی", "maintenance_during_deploy" to "نگه‌داری هم‌زمان با انتشار",
)
val WEEKDAY_FA = linkedMapOf("SA" to "شنبه", "SU" to "یکشنبه", "MO" to "دوشنبه", "TU" to "سه‌شنبه", "WE" to "چهارشنبه", "TH" to "پنجشنبه", "FR" to "جمعه")
val ACTOR_ROLE_FA = mapOf("ceo" to "مدیرعامل", "manager" to "مدیر", "agent" to "ایجنت", "owner" to "مدیر کل", "sre" to "SRE", "inspector" to "بازرس", "advisor" to "مشاور کل", "*" to "هر کس")

/** The colour of a calendar kind (the chart palette by role, a freeze in warning, a meeting silver, a holiday muted). */
@Composable
fun calColor(kind: String): Color {
    val c = Divan.colors
    return when (kind) {
        "deploy" -> c.chart[0]; "campaign" -> c.chart[2]; "event" -> c.chart[1]; "maintenance" -> c.chart[3]
        "freeze" -> c.warning; "holiday" -> c.textMuted; else -> c.silverInk
    }
}

// --------------------------------------------------------------- figures --
/** A KPI value with its unit, always a Latin figure. */
fun kpiFig(v: Double?, unit: String): String {
    if (v == null || !v.isFinite()) return "—"
    if (unit == "USD") return usd(v)
    val n = if (abs(v) >= 1000) String.format(Locale.US, "%,.0f", v) else trimZeros(String.format(Locale.US, "%,.2f", v))
    return when (unit) { "%" -> "$n%"; "" -> n; else -> "$n $unit" }
}

private fun trimZeros(s: String): String = if ('.' in s) s.trimEnd('0').trimEnd('.') else s

/** A number as it is: whole without decimals, else one or two ("1.8", "2.9"). */
fun num(v: Double): String = if (v % 1.0 == 0.0) v.roundToLong().toString() else trimZeros(String.format(Locale.US, "%.2f", v))

/** Is a KPI at or beyond its target, given its direction? Null when there is nothing to judge. */
fun onTarget(v: Double?, target: Double?, direction: String?): Boolean? =
    if (v == null || target == null || direction == null) null else if (direction == "down") v <= target else v >= target

/** Tokens of a budget: "61K / 120K"; without a cap only what was used. */
fun budgetFig(used: Long, cap: Long?): String = if (cap == null) tokens(used) else "${tokens(used)} / ${tokens(cap)}"

fun pctOf(used: Long, cap: Long?): Double = if (cap == null || cap <= 0) 0.0 else minOf(100.0, used * 100.0 / cap)

/** A 0..1 as a Latin percentage. */
fun pct01(v: Double?): String = if (v == null) "—" else "${(v * 100).roundToInt()}%"

/** Risk score tone: ≥ 15 high, ≥ 8 medium. */
fun scoreTone(s: Int): Tone = if (s >= 15) Tone.NEG else if (s >= 8) Tone.WARN else Tone.NEUTRAL

/** Days from now (negative = past), whole days. */
fun daysFrom(iso: String?, now: Long = HqClock.millis()): Int? = instant(iso)?.let { ((it.toEpochMilli() - now) / 86_400_000.0).roundToInt() }

/** The end of a date in Tehran (a knowledge entry is valid through that day). */
fun dayEnd(date: String): String = "${date}T20:29:00Z"

/** mm:ss of a span. */
fun mmss(ms: Long): String {
    val s = maxOf(0L, (ms / 1000.0).roundToLong())
    return "%02d:%02d".format(Locale.US, s / 60, s % 60)
}

/** A clock for timers that ticks once a second (the app's clock, so the screenshot tests stay still). */
@Composable
fun rememberSecond(): Long {
    var t by remember { mutableLongStateOf(HqClock.millis()) }
    LaunchedEffect(Unit) { while (true) { delay(1000); t = HqClock.millis() } }
    return t
}

// ------------------------------------------------------------ actors and refs --
/** The medallion an actor gets: the owner's disc, the advisor's orb, the overseer's sentinel, a CEO, a manager, the inspector,
 *  an employee; the system is the monogram. */
@Composable
fun ActorAvatar(a: Actor?, size: Dp = 32.dp) {
    val c = Divan.colors
    val kind = when {
        a == null || a.kind == "system" || a.kind == "service" -> "system"
        a.kind == "owner" -> "owner"
        a.code == "HQ-OVS-MGR" || a.kind == "inspector" -> "inspector"
        else -> agentKindOf(a.code, a.kind)
    }
    if (kind == "system") {
        Box(Modifier.size(size).clip(CircleShape).background(c.tile), contentAlignment = Alignment.Center) { Monogram(size * 0.5f, ink = c.textSecondary) }
    } else Avatar(kind, dept = a?.code?.let(::deptOf), size = size, label = a?.displayFa ?: a?.code)
}

/** Where a reference opens in the app, when it has a page. */
fun refRoute(ref: String): String? = when {
    Regex("^D-\\d+$").matches(ref) -> "cartable/$ref"
    Regex("^O-\\d+$").matches(ref) -> "outputs/$ref"
    Regex("^W-\\d+$").matches(ref) -> "work/$ref"
    Regex("^S-\\d+$").matches(ref) -> "workshop/$ref"
    Regex("^SC-\\d+$").matches(ref) -> "support/$ref"
    Regex("^MT-\\d+$").matches(ref) -> "meetings/$ref"
    Regex("^(?:K|KB)-\\d+$").matches(ref) -> "knowledge/$ref"
    Regex("^(?:OB|KR)-\\d+$").matches(ref) -> "okr"
    Regex("^RK-\\d+$").matches(ref) -> "risks/$ref"
    Regex("^CE-\\d+$").matches(ref) -> "calendar"
    Regex("^M-\\d+$").matches(ref) -> "resolutions"
    Regex("^(?:[A-Z]{2,5}|holding)@\\d+$").matches(ref) -> "charter"
    else -> null
}

enum class RefTone { GOLD, NEUTRAL, NEG }

/** A source or reference as a small Latin chip; one with a page opens it. */
@Composable
fun RefChip(ref: String, note: String? = null, tone: RefTone = RefTone.GOLD, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val nav = LocalNav.current
    val route = refRoute(ref)
    val (bg, fg) = when (tone) { RefTone.GOLD -> c.softGold to c.goldInk; RefTone.NEG -> c.softNegative to c.negative; RefTone.NEUTRAL -> c.tile to c.textSecondary }
    Row(
        modifier.clip(CircleShape).background(bg).then(if (route != null) Modifier.clickable(role = Role.Button) { nav.go(route) } else Modifier).padding(horizontal = 8.dp, vertical = 2.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Fig(ref, style = Divan.type.figureSmall, color = fg)
        if (!note.isNullOrBlank()) Text("· $note", style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

/** A company's mark; the holding's is the monogram. */
@Composable
fun CoMark(code: String?, height: Dp = 12.dp, ink: Color = Divan.colors.textSecondary) {
    if (code == null) return
    val holding = rememberCompanies().firstOrNull { it.code == code }?.kind == "holding"
    if (holding) Monogram(height + 2.dp, ink = ink) else CompanyMark(code, height = height, mono = true, ink = ink)
}

/** The holding and every company from the API (any number); [holding] false leaves the holding out, [all] adds «همه». */
@Composable
fun ScopeChips(value: String?, onChange: (String?) -> Unit, all: Boolean = true, holding: Boolean = true, allLabel: String = "همه") {
    val list = rememberCompanies().filter { holding || it.kind != "holding" }
    ChipRow {
        if (all) FilterChip(allLabel, value == null, { onChange(null) })
        for (co in list) Chip(value == co.code, { onChange(co.code) }) { ink ->
            if (co.kind == "holding") Monogram(14.dp, ink = ink) else CompanyMark(co.code, height = 12.dp, mono = true, ink = ink)
            Text(co.nameFa ?: co.code, style = Divan.type.small.copy(fontWeight = if (value == co.code) FontWeight.SemiBold else FontWeight.Normal), color = ink, maxLines = 1)
        }
    }
}

/** A row of filter chips over a label map, with «همه…» first. */
@Composable
fun <T> FilterRow(all: String, value: T?, options: Map<T, String>, onChange: (T?) -> Unit) {
    ChipRow {
        FilterChip(all, value == null, { onChange(null) })
        for ((k, fa) in options) FilterChip(fa, value == k, { onChange(k) })
    }
}

/** A labelled number in a tile (the web's Stat): the value a Latin figure. */
@Composable
fun Stat(label: String, value: String, modifier: Modifier = Modifier, sub: String? = null, tone: Tone? = null) {
    val c = Divan.colors
    Column(modifier.clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(label, style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
        Fig(value, style = Divan.type.figureM.copy(fontSize = 18.sp, lineHeight = 26.sp), color = when (tone) { Tone.POS -> c.positive; Tone.NEG -> c.negative; Tone.WARN -> c.warning; else -> c.textPrimary })
        if (sub != null) Text(sub, style = Divan.type.micro, color = c.textSecondary)
    }
}

/** A small section heading inside a card (gold, like the decision page's). */
@Composable
fun Heading(text: String, modifier: Modifier = Modifier) {
    Text(text, modifier, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = Divan.colors.goldInk)
}

/** A titled block of a card. */
@Composable
fun Block(title: String, content: @Composable ColumnScope.() -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Heading(title)
        content()
    }
}

/** A KPI's 30 days as one recessive silver line (a gap where a day has no value, never a zero); the last point says whether the
 *  KPI is at its target (positive), short of it (warning), or carries no judgement (silver). Time runs left to right. */
@Composable
fun Trend(values: List<Double?>, hit: Boolean?, width: Dp = 68.dp, height: Dp = 24.dp) {
    val xs = values.withIndex().filter { it.value != null }
    if (xs.size < 2) return
    val c = Divan.colors
    val hi = xs.maxOf { it.value!! }
    val lo = xs.minOf { it.value!! }
    val span = (hi - lo).takeIf { it > 0 } ?: 1.0
    val dot = when (hit) { null -> c.silverInk; true -> c.positive; false -> c.warning }
    val ring = c.card
    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
        Canvas(Modifier.size(width, height)) {
            val pad = 2.dp.toPx()
            fun x(i: Int) = pad + i.toFloat() / maxOf(values.size - 1, 1) * (size.width - 2 * pad)
            fun y(v: Double) = size.height - pad - ((v - lo) / span).toFloat() * (size.height - 2 * pad)
            val path = Path()
            var pen = false
            values.forEachIndexed { i, v ->
                if (v == null) pen = false
                else { if (pen) path.lineTo(x(i), y(v)) else path.moveTo(x(i), y(v)); pen = true }
            }
            drawPath(path, c.silverInk.copy(alpha = 0.7f), style = Stroke(1.6.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
            val last = xs.last()
            drawCircle(ring, 4.5.dp.toPx(), Offset(x(last.index), y(last.value!!)))
            drawCircle(dot, 3.dp.toPx(), Offset(x(last.index), y(last.value!!)))
        }
    }
}

/** A unified diff, line by line: additions and removals marked by sign and colour, each line in its own direction. */
@Composable
fun DiffView(text: String, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Column(modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.page).padding(6.dp), verticalArrangement = Arrangement.spacedBy(1.dp)) {
        for (l in text.split('\n')) {
            val head = l.startsWith("@@") || l.startsWith("---") || l.startsWith("+++")
            val add = !head && l.startsWith("+")
            val del = !head && l.startsWith("-")
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(4.dp)).background(if (add) c.softPositive else if (del) c.softNegative else Color.Transparent).padding(horizontal = 6.dp, vertical = 1.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Fig(if (head) "" else if (add) "+" else if (del) "−" else "", Modifier.width(10.dp), style = Divan.type.figureSmall, color = if (add) c.positive else if (del) c.negative else c.textMuted)
                val body = if (head) l else l.drop(1).ifEmpty { " " }
                if (head) Fig(body, Modifier.weight(1f), style = Divan.type.figureSmall, color = c.textMuted, maxLines = 2)
                else Text(
                    com.coinepro.hq.ui.v16.prose(body), Modifier.weight(1f),
                    style = Divan.type.caption.copy(textDecoration = if (del) TextDecoration.LineThrough else null), color = c.textPrimary,
                )
            }
        }
    }
}

/** A row of small pills that scrolls sideways. */
@Composable
fun PillRow(content: @Composable () -> Unit) {
    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) { content() }
}

/** A figure inside Persian text, as an annotated string on its own. */
fun figText(prefix: String, figure: String, suffix: String = ""): AnnotatedString =
    buildAnnotatedString { append(prefix); fig(figure); append(suffix) }

/** A §20 action: a failed call says its §20.11 code in Persian ([govError]) instead of the server's sentence. */
fun ActionRunner.gov(toasts: Toasts, onError: ((ApiException) -> Boolean)? = null, block: suspend () -> Unit) =
    run(onError = { e -> if (onError?.invoke(e) != true) toasts.error(govError(e)) }, block = block)

/** A small icon in a tinted square (a meeting type, a calendar kind). */
@Composable
fun IconTile(icon: DivanIcon, tint: Color, bg: Color = Divan.colors.tile, size: Dp = 36.dp) {
    Box(Modifier.size(size).clip(RoundedCornerShape(10.dp)).background(bg), contentAlignment = Alignment.Center) { DIcon(icon, size = size * 0.5f, tint = tint) }
}
