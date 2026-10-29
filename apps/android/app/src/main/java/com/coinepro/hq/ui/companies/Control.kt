package com.coinepro.hq.ui.companies

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.coinepro.hq.core.data.CoState
import com.coinepro.hq.core.data.CompanyControl
import com.coinepro.hq.core.data.Pulse
import com.coinepro.hq.core.data.coState
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.instant
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.format.tokens
import com.coinepro.hq.core.format.until
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.core.net.Actor
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.BreakdownRow
import com.coinepro.hq.core.net.BudgetUse
import com.coinepro.hq.core.net.Company
import com.coinepro.hq.core.net.ControlState
import com.coinepro.hq.core.net.Run
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.CountingText
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.Haptics
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.IconBtn
import com.coinepro.hq.designsystem.LiveDot
import com.coinepro.hq.designsystem.LocalReducedMotion
import com.coinepro.hq.designsystem.Monogram
import com.coinepro.hq.designsystem.Motion
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Radius
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.Space
import com.coinepro.hq.designsystem.collapseOut
import com.coinepro.hq.designsystem.expandIn
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.motionShort
import com.coinepro.hq.designsystem.rememberBreath
import com.coinepro.hq.designsystem.rememberHaptics
import com.coinepro.hq.designsystem.rememberOrbit
import com.coinepro.hq.designsystem.smoothSize
import androidx.compose.ui.draw.drawWithContent
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Loadable
import com.coinepro.hq.ui.Toasts
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.settings.parseMillions
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v16.appendProse
import com.coinepro.hq.ui.work.NewOrderSheet
import kotlin.math.max
import kotlin.math.min
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

// ======================================================================= the control layer on screen ==
/** The company (or the holding) an action is about. */
@Immutable
data class CoTarget(val code: String, val nameFa: String, val holding: Boolean)

/** Which control sheet is open. */
sealed interface ControlSheet {
    val t: CoTarget
    data class Actions(override val t: CoTarget) : ControlSheet
    data class Stop(override val t: CoTarget) : ControlSheet
    data class Resume(override val t: CoTarget) : ControlSheet
    data class Freeze(override val t: CoTarget) : ControlSheet
    data class Unfreeze(override val t: CoTarget) : ControlSheet
    data class Order(override val t: CoTarget) : ControlSheet
}

/**
 * The owner's control actions as the screens run them: optimistic (the card changes the moment the owner confirms), rolled back with
 * a Persian error when the hub refuses (the call's failure is already in «خطاخوان»), with a firm haptic on stopping and a confirming
 * one when it is done. Releasing a switch and opening deploys ask for the passkey first; a cancelled passkey changes nothing.
 */
@Stable
class ControlUi internal constructor(private val control: CompanyControl, private val scope: CoroutineScope, private val toasts: Toasts, private val haptics: Haptics) {
    var sheet by mutableStateOf<ControlSheet?>(null)
    var busy by mutableStateOf(false)
        private set

    fun open(s: ControlSheet) { sheet = s }
    fun close() { sheet = null }

    fun stop(t: CoTarget, reason: String) {
        haptics.firm()
        act {
            control.stop(t.code, t.holding, reason)
            toasts.info(if (t.holding) "همه‌چیز متوقف شد؛ فقط کارهای اضطراری (P0) اجرا میشوند." else "${t.nameFa} متوقف شد؛ هیچ چیز از دست نرفت.")
        }
    }

    fun resume(t: CoTarget, reason: String) = act {
        control.resume(t.code, t.holding, reason)
        toasts.ok(if (t.holding) "هلدینگ دوباره کار میکند." else "${t.nameFa} دوباره کار میکند.")
    }

    fun freeze(t: CoTarget, hours: Int, reason: String) = act {
        control.freeze(t.code, hours, reason)
        toasts.info("deploy ${t.nameFa} بسته شد؛ کارهای دیگر ادامه دارند.")
    }

    fun unfreeze(t: CoTarget, reason: String) = act {
        control.unfreeze(t.code, reason)
        toasts.ok("deploy ${t.nameFa} باز شد.")
    }

    fun budget(t: CoTarget, tokenLimit: Long?, usdLimit: String?, done: () -> Unit) = act {
        control.setMonthBudget(t.code, t.holding, tokenLimit, usdLimit)
        toasts.ok("بودجه‌ی ماه ${t.nameFa} ذخیره شد.")
        done()
    }

    private fun act(block: suspend () -> Unit) {
        if (busy) return
        busy = true
        sheet = null
        scope.launch {
            try {
                block()
                haptics.confirm()
            } catch (e: ApiException) {
                haptics.reject()
                toasts.error(e.messageFa)
            } finally {
                busy = false
            }
        }
    }
}

@Composable
fun rememberControlUi(): ControlUi {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    return remember(env, toasts, scope) { ControlUi(CompanyControl(env.api, env.cache, { a, t -> env.auth.stepUp(act, a, t) }), scope, toasts, haptics) }
}

// ========================================================================================== live data ==
/** What the companies list and the control room read: the switches, what runs now, today's spend per company, the stream's pulses. */
@Stable
class ControlData(
    val control: ControlState?,
    val running: List<Run>,
    val spend: List<BreakdownRow>,
    val pulses: Map<String, Pulse>,
) {
    fun state(code: String, holding: Boolean, company: Company? = null): CoState = coState(code, holding, control, company)

    /** Runs in progress: what was running when the screen loaded, plus what the stream says started since, less what finished. */
    fun runs(code: String): Int {
        val p = pulses[code]
        val loaded = running.filter { it.company == code && it.state == "running" }.map { it.id }.toSet()
        return (loaded + p?.runs.orEmpty()).size
    }

    fun busy(code: String): Boolean = runs(code) > 0 || pulses[code]?.working?.isNotEmpty() == true
    fun stirred(code: String): Boolean = pulses[code]?.stirred() == true

    /** Today's equivalent spend; the holding's card sums every company. */
    fun spendOf(code: String?): Double =
        spend.filter { code == null || it.key == code }.sumOf { (it.equivCostUsd.toDoubleOrNull() ?: 0.0) + (it.costUsd.toDoubleOrNull() ?: 0.0) }
}

@Composable
fun rememberControlData(): ControlData {
    val env = LocalEnv.current
    val control = rememberQuery("control", "control") { control() }
    val running = rememberQuery("runs:running", "runs", maxAgeMs = 15_000) { runs(state = "running", limit = 100) }
    val today = HqClock.today().toString()
    val spend = rememberQuery("treasury:company:$today", "treasury", maxAgeMs = 60_000) { breakdown("company", today, today) }
    val pulses by env.stream.activity.state.collectAsStateWithLifecycle()
    return ControlData(control.data, running.data?.items.orEmpty(), spend.data.orEmpty(), pulses)
}

// ============================================================================================ chips ==
/** The state at a glance: a coloured chip with its icon and its word (colour never alone). */
@Composable
fun StateChip(s: CoState, busy: Boolean, modifier: Modifier = Modifier) {
    when {
        s.stopped -> Pill("متوقف", Tone.NEG, modifier, icon = DivanIcon.PAUSE)
        s.holdingStopped -> Pill("متوقف با هلدینگ", Tone.NEG, modifier, icon = DivanIcon.PAUSE)
        s.frozen -> Pill("deploy بسته", Tone.WARN, modifier, icon = DivanIcon.LOCK)
        busy -> Pill("در حال کار", Tone.POS, modifier, live = true)
        else -> Pill("فعال", Tone.POS, modifier, dot = true)
    }
}

private enum class Lamp { RUN, STOP, FREEZE }

private fun lampOf(s: CoState) = when { !s.running -> Lamp.STOP; s.frozen -> Lamp.FREEZE; else -> Lamp.RUN }

@Composable
private fun lampColor(l: Lamp): Color = with(Divan.colors) { when (l) { Lamp.RUN -> positive; Lamp.STOP -> negative; Lamp.FREEZE -> warning } }

/** The company's mark in a ring that says what its agents are doing: a gold comet orbits while they work, the ring breathes once
 *  when something has just happened, it is still when they are idle, and red and dim when the company is stopped. The motion lives in
 *  the draw phase (no recomposition) and is still when animations are removed. */
@Composable
fun ActivityRing(code: String, holding: Boolean, stopped: Boolean, busy: Boolean, stirred: Boolean, size: Dp = 56.dp) {
    val c = Divan.colors
    val orbit = rememberOrbit(busy && !stopped)
    val breath = rememberBreath((busy || stirred) && !stopped, periodMs = Motion.BREATH + 600)
    val ring by animateColorAsState(if (stopped) c.negative else if (busy) c.goldFill else c.lineStrong, motionShort(), label = "ring")
    val gold = c.goldFill
    Box(
        Modifier
            .size(size)
            .semantics { contentDescription = if (stopped) "متوقف" else if (busy) "ایجنت‌ها در حال کارند" else "آرام" }
            .drawBehind {
                val r = this.size.minDimension / 2
                val sw = 1.5.dp.toPx()
                if (busy && !stopped) drawCircle(gold.copy(alpha = 0.10f + 0.12f * breath.value), r)
                drawCircle(ring, r - sw / 2, style = Stroke(sw))
                if (busy && !stopped) rotate(orbit.value) {
                    // A comet: its tail fades into the ring, its head is gold (the gradient spans exactly the arc, 250° → 360°).
                    drawArc(
                        Brush.sweepGradient(0.69f to gold.copy(alpha = 0f), 1f to gold, center = center), 250f, 110f, false,
                        topLeft = Offset(sw / 2, sw / 2), size = Size(this.size.width - sw, this.size.height - sw), style = Stroke(sw * 1.8f, cap = StrokeCap.Round),
                    )
                }
            },
        contentAlignment = Alignment.Center,
    ) {
        Box(
            Modifier.size(size - 10.dp).clip(CircleShape).background(c.tile).graphicsLayer { alpha = if (stopped) 0.55f else 1f },
            contentAlignment = Alignment.Center,
        ) { if (holding) Monogram(size * 0.42f) else CompanyMark(code, height = size * 0.36f, ink = c.textPrimary) }
    }
}

// ============================================================================================ cards ==
/** The line under a company's name: why it is stopped, until when its deploys are closed, or what its agents are doing. */
@Composable
private fun StateLine(s: CoState, d: ControlData, holdingName: String?) {
    val c = Divan.colors
    val runs = d.runs(s.code)
    val working = d.pulses[s.code]?.working?.size ?: 0
    val (dot, text) = when {
        s.stopped -> c.negative to "متوقف از ${ago(s.switch?.changedAt)}، ${byFa(s.switch?.changedBy)}"
        s.holdingStopped -> c.negative to "کلید ${holdingName ?: "هلدینگ"} همه را نگه داشته است"
        d.busy(s.code) -> c.positive to when {
            runs > 0 -> "$runs اجرا در جریان"
            else -> "$working نفر سر کار"
        }
        d.stirred(s.code) -> c.silverInk to "همین الان خبری رسید"
        else -> c.textMuted to "آرام؛ ایجنت‌ها تا رسیدن کار خواب‌اند"
    }
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        LiveDot(dot, live = s.running && d.busy(s.code), size = 6.dp)
        Text(text, style = Divan.type.caption, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
    s.freeze?.let { f ->
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            DIcon(DivanIcon.LOCK, size = 12.dp, tint = c.warning)
            // A time is a figure (Latin); how long is left is a prose count (Persian).
            Text(buildAnnotatedString { append("deploy بسته تا "); appendProse(jTime(f.until)); append("، ${until(f.until)}") }, style = Divan.type.caption, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

/** "مدیر کل", "مدیرعامل" (an agent's code as its role), "خط انتشار". */
fun byFa(code: String?): String = when {
    code.isNullOrBlank() -> "—"
    code == "owner" -> "به دستور تو"
    code == "pipeline" -> "خط انتشار"
    code.endsWith("-CEO") -> "به دستور مدیرعامل"
    code == "HQ-OVR" -> "به دستور ناظر کل"
    else -> "به دستور $code"
}

/** Four figures of a company: today's spend (Latin), open work, cards waiting on the owner and active staff (counts, Persian). */
@Composable
private fun Figures(spend: Double?, work: Int, pending: Int, staff: Int, count: Boolean) {
    val c = Divan.colors
    Row(
        Modifier.fillMaxWidth().height(IntrinsicSize.Min).clip(RoundedCornerShape(Radius.tile)).background(c.tile).padding(vertical = Space.sm),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Figure("مصرف امروز", spend?.let { usd(it) } ?: "—", figure = true, count = count)
        Split()
        Figure("کار باز", work.toString(), count = count)
        Split()
        Figure("منتظر مُهر", pending.toString(), gold = pending > 0, count = count)
        Split()
        Figure("کارمند فعال", staff.toString(), count = count)
    }
}

@Composable
private fun androidx.compose.foundation.layout.RowScope.Figure(label: String, value: String, figure: Boolean = false, gold: Boolean = false, count: Boolean = false) {
    val c = Divan.colors
    Column(Modifier.weight(1f).padding(horizontal = 6.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(2.dp)) {
        val style = if (figure) Divan.type.figure.copy(fontWeight = FontWeight.SemiBold) else Divan.type.h3.copy(lineHeight = Divan.type.figure.lineHeight)
        val color = if (gold) c.goldInk else c.textPrimary
        if (count) CountingText(value, style, color = color) else Text(value, style = style, color = color, maxLines = 1)
        Text(label, style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
private fun Split() = Box(Modifier.width(1.dp).fillMaxHeight().padding(vertical = 4.dp).background(Divan.colors.lineDivider))

/** A thin bar of the state's colour on the card's start edge, over its surface, so a long list reads at a glance. */
private fun Modifier.stateEdge(color: Color): Modifier = drawWithContent {
    drawContent()
    val w = 3.dp.toPx()
    val inset = 18.dp.toPx()
    val x = if (layoutDirection == LayoutDirection.Rtl) size.width - w else 0f
    drawRoundRect(color, Offset(x, inset), Size(w, size.height - 2 * inset), CornerRadius(w / 2))
}

/**
 * One company in the list: its mark in the activity ring, its state chip, the line that says why or what, four figures and the two
 * switches. A tap opens the company; a long press (or ⋯) opens every action: stop or resume, deploys, the cartable filtered to it, an
 * order to its CEO, a message.
 */
@Composable
fun CompanyControlCard(co: Company, d: ControlData, ui: ControlUi, holdingName: String?, modifier: Modifier = Modifier, onOpen: () -> Unit) {
    val c = Divan.colors
    val s = d.state(co.code, false, co)
    val t = CoTarget(co.code, co.nameFa ?: co.code, false)
    val lamp by animateColorAsState(lampColor(lampOf(s)), motionShort(), label = "lamp")
    HqCard(
        modifier.fillMaxWidth().stateEdge(lamp),
        onClick = onOpen, onLongClick = { ui.open(ControlSheet.Actions(t)) },
        onClickLabel = "باز کردن ${t.nameFa}", onLongClickLabel = "کارهای ${t.nameFa}",
    ) {
        // The chip shares the name's line; the lines under it get the card's whole width, so nothing is cut short.
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Space.sm)) {
            ActivityRing(co.code, false, !s.running, d.busy(co.code), d.stirred(co.code))
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Space.xs)) {
                    // The name takes what it needs; only a name longer than the line gives way (one weighted part, so it is not halved).
                    Row(Modifier.weight(1f), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Space.xs)) {
                        Text(t.nameFa, style = Divan.type.bodyStrong, modifier = Modifier.weight(1f, fill = false), maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Text(buildAnnotatedString { fig(co.code) }, style = Divan.type.micro, color = c.textMuted)
                    }
                    StateChip(s, d.busy(co.code))
                }
                StateLine(s, d, holdingName)
            }
        }
        Spacer(Modifier.height(Space.sm))
        Figures(d.spendOf(co.code), co.counts.workOpen, co.counts.decisionsPending, co.counts.employeesActive, count = true)
        Spacer(Modifier.height(Space.sm))
        Switches(s, t, ui)
    }
}

/** Stop or resume, close or open deploys, and ⋯ for the rest. */
@Composable
private fun Switches(s: CoState, t: CoTarget, ui: ControlUi) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Space.xs)) {
        if (s.stopped) HqButton("ادامه", { ui.open(ControlSheet.Resume(t)) }, Modifier.weight(1f), size = BtnSize.SM, icon = DivanIcon.RESUME, label = "ادامه با اثر انگشت")
        else HqButton(if (t.holding) "توقف همه‌چیز" else "توقف", { ui.open(ControlSheet.Stop(t)) }, Modifier.weight(1f), variant = BtnVariant.DANGER, size = BtnSize.SM, icon = DivanIcon.PAUSE)
        if (!t.holding) {
            if (s.frozen) HqButton("باز کردن deploy", { ui.open(ControlSheet.Unfreeze(t)) }, Modifier.weight(1f), size = BtnSize.SM, icon = DivanIcon.RESUME)
            else HqButton("بستن deploy", { ui.open(ControlSheet.Freeze(t)) }, Modifier.weight(1f), size = BtnSize.SM, icon = DivanIcon.LOCK)
        }
        IconBtn(DivanIcon.MORE, "کارهای ${t.nameFa}", { ui.open(ControlSheet.Actions(t)) })
    }
}

/**
 * The holding at the top of the list: the same at a glance (totals across the holding) and its own kill switch, the one that stops
 * everything. When it is engaged the card says so plainly and offers only the way back.
 */
@Composable
fun HoldingControlCard(holding: Company, all: List<Company>, d: ControlData, ui: ControlUi, modifier: Modifier = Modifier, onOpen: () -> Unit) {
    val c = Divan.colors
    val s = d.state(holding.code, true, holding)
    val t = CoTarget(holding.code, holding.nameFa ?: "هلدینگ", true)
    val busy = all.any { d.busy(it.code) }
    val stirred = all.any { d.stirred(it.code) }
    val runs = all.sumOf { d.runs(it.code) }
    val stopped = all.count { it.kind != "holding" && d.state(it.code, false, it).stopped }
    val bg by animateColorAsState(if (s.stopped) c.softNegative else c.card, motionShort(), label = "holding-bg")
    HqCard(
        modifier.fillMaxWidth(), tahrir = !s.stopped, color = bg,
        onClick = onOpen, onLongClick = { ui.open(ControlSheet.Actions(t)) }, onClickLabel = "باز کردن هلدینگ", onLongClickLabel = "کارهای هلدینگ",
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Space.sm)) {
            ActivityRing(holding.code, true, s.stopped, busy, stirred, size = 60.dp)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Space.xs)) {
                    Text(t.nameFa, style = Divan.type.h3, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                    StateChip(s, busy)
                }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    LiveDot(if (s.stopped) c.negative else if (busy) c.positive else c.textMuted, live = !s.stopped && busy)
                    Text(
                        when {
                            s.stopped -> "همه متوقف‌اند از ${ago(s.switch?.changedAt)}؛ فقط کار اضطراری"
                            runs > 0 -> "$runs اجرا در جریان در کل هلدینگ" + if (stopped > 0) "، $stopped شرکت متوقف" else ""
                            stopped > 0 -> "$stopped شرکت متوقف؛ بقیه آرام"
                            else -> "همه‌ی شرکت‌ها روشن و آرام"
                        },
                        style = Divan.type.caption, color = c.textSecondary, maxLines = 2, overflow = TextOverflow.Ellipsis,
                    )
                }
            }
        }
        Spacer(Modifier.height(Space.sm))
        Figures(
            d.spendOf(null).takeIf { d.spend.isNotEmpty() },
            all.sumOf { it.counts.workOpen }, all.sumOf { it.counts.decisionsPending }, all.sumOf { it.counts.employeesActive }, count = true,
        )
        Spacer(Modifier.height(Space.sm))
        if (s.stopped) {
            s.switch?.reason?.takeIf { it.isNotBlank() }?.let { Text("«$it»", style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.padding(bottom = Space.xs)) }
            HqButton("ادامه‌ی همه با اثر انگشت", { ui.open(ControlSheet.Resume(t)) }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.RESUME)
        } else Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Space.xs)) {
            HqButton("کلید توقف کل هلدینگ", { ui.open(ControlSheet.Stop(t)) }, Modifier.weight(1f), variant = BtnVariant.DANGER, icon = DivanIcon.PAUSE)
            IconBtn(DivanIcon.MORE, "کارهای هلدینگ", { ui.open(ControlSheet.Actions(t)) })
        }
    }
}

// ============================================================================================ sheets ==
/** Hosts whichever control sheet is open (the companies list, the company page). */
@Composable
fun ControlSheets(ui: ControlUi) {
    val s = ui.sheet ?: return
    val nav = LocalNav.current
    val control = rememberQuery("control", "control") { control() }
    val st = coState(s.t.code, s.t.holding, control.data)
    when (s) {
        is ControlSheet.Actions -> HqSheet(ui::close, s.t.nameFa, sub = stateFa(st), ref = s.t.code) {
            ActionsContent(s.t, st, ui) { route -> ui.close(); nav.go(route) }
        }
        is ControlSheet.Stop -> HqSheet(ui::close, if (s.t.holding) "توقف کل هلدینگ" else "توقف ${s.t.nameFa}") {
            StopContent(s.t, busy = ui.busy, onStop = { ui.stop(s.t, it) }, onCancel = ui::close)
        }
        is ControlSheet.Resume -> HqSheet(ui::close, if (s.t.holding) "ادامه‌ی کار هلدینگ" else "ادامه‌ی کار ${s.t.nameFa}") {
            ResumeContent(s.t, st, busy = ui.busy, onResume = { ui.resume(s.t, it) }, onCancel = ui::close)
        }
        is ControlSheet.Freeze -> HqSheet(ui::close, "بستن deploy ${s.t.nameFa}") {
            FreezeContent(s.t, busy = ui.busy, onFreeze = { h, r -> ui.freeze(s.t, h, r) }, onCancel = ui::close)
        }
        is ControlSheet.Unfreeze -> HqSheet(ui::close, "باز کردن deploy ${s.t.nameFa}") {
            UnfreezeContent(s.t, st, busy = ui.busy, onOpen = { ui.unfreeze(s.t, it) }, onCancel = ui::close)
        }
        is ControlSheet.Order -> NewOrderSheet(onDismiss = ui::close, company0 = s.t.code)
    }
}

private fun stateFa(s: CoState): String = when {
    s.stopped -> "متوقف از ${ago(s.switch?.changedAt)}، ${byFa(s.switch?.changedBy)}"
    s.holdingStopped -> "با کلید کل هلدینگ متوقف است"
    s.frozen -> "روشن؛ deploy بسته، ${until(s.freeze?.until)}"
    else -> "روشن؛ همه‌چیز عادی است"
}

/** Every action on one company (the long press, ⋯). */
@Composable
fun ActionsContent(t: CoTarget, s: CoState, ui: ControlUi, go: (String) -> Unit) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        if (s.stopped) ActionRow(DivanIcon.RESUME, "ادامه‌ی کار", "با اثر انگشت یا چهره", c.positive) { ui.open(ControlSheet.Resume(t)) }
        else ActionRow(DivanIcon.PAUSE, if (t.holding) "توقف همه‌چیز" else "توقف فوری", "بی‌اثر انگشت؛ هیچ چیز از دست نمیرود", c.negative) { ui.open(ControlSheet.Stop(t)) }
        if (!t.holding) {
            if (s.frozen) ActionRow(DivanIcon.RESUME, "باز کردن deploy", "با اثر انگشت یا چهره", c.warning) { ui.open(ControlSheet.Unfreeze(t)) }
            else ActionRow(DivanIcon.LOCK, "بستن deploy", "تا زمانی که تعیین میکنی؛ بقیه‌ی کارها ادامه دارند", c.warning) { ui.open(ControlSheet.Freeze(t)) }
        }
        ActionRow(DivanIcon.CARTABLE, "کارتابل ${if (t.holding) "هلدینگ" else "این شرکت"}", "فقط کارت‌های ${t.nameFa}", c.goldInk) { go("cartable-co/${t.code}") }
        ActionRow(DivanIcon.COMMAND, if (t.holding) "فرمان به هلدینگ" else "فرمان به مدیرعامل", "کار تازه؛ مدیرعامل آن را به دپارتمان درست میسپارد", c.goldInk) { ui.open(ControlSheet.Order(t)) }
        if (!t.holding) ActionRow(DivanIcon.MESSAGES, "پیام به مدیرعامل", "گفت‌وگوی ${t.code}-CEO", c.textSecondary) { go("messages/${t.code}-CEO") }
        ActionRow(DivanIcon.SETTINGS, "اتاق کنترل", "وضعیت و تاریخچه، بودجه، استخدام، فعالیت زنده", c.textSecondary) { go("companies/${t.code}") }
    }
}

@Composable
private fun ActionRow(icon: DivanIcon, title: String, note: String, tint: Color, onClick: () -> Unit) {
    val c = Divan.colors
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(Radius.tile)).clickable(role = Role.Button, onClick = onClick).padding(horizontal = Space.xs, vertical = Space.sm),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(Space.sm),
    ) {
        Box(Modifier.size(40.dp).clip(RoundedCornerShape(Radius.tile)).background(c.tile), contentAlignment = Alignment.Center) { DIcon(icon, size = 20.dp, tint = tint) }
        Column(Modifier.weight(1f)) {
            Text(title, style = Divan.type.bodyStrong)
            Text(note, style = Divan.type.caption, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        DIcon(DivanIcon.NEXT, size = 16.dp, tint = c.textMuted)
    }
}

/** What will happen, line by line, with an icon each: the confirmation says exactly what the owner is about to do. */
@Composable
private fun Consequences(lines: List<Pair<DivanIcon, String>>, tint: Color) {
    val c = Divan.colors
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(Radius.tile)).background(c.tile).padding(Space.sm), verticalArrangement = Arrangement.spacedBy(Space.xs)) {
        for ((icon, text) in lines) Row(horizontalArrangement = Arrangement.spacedBy(Space.xs)) {
            Box(Modifier.height(Divan.type.small.lineHeight.value.dp), contentAlignment = Alignment.Center) { DIcon(icon, size = 16.dp, tint = tint) }
            Text(com.coinepro.hq.ui.v14.figs(text), style = Divan.type.small, color = c.textPrimary)
        }
    }
}

private val STOP_REASONS = listOf("رفتار غیرعادی", "مصرف بالا", "بررسی امنیتی", "خطا در تولید")

/**
 * Stopping (OPERATING_MODEL §1.12): no passkey, because speed matters. The sheet says exactly what will happen, offers a one-tap
 * «فوری» that needs no reason, and otherwise a short reason (a chip or a line) for the audit book.
 */
@Composable
fun StopContent(t: CoTarget, busy: Boolean, onStop: (String) -> Unit, onCancel: () -> Unit) {
    val c = Divan.colors
    var reason by rememberSaveable { mutableStateOf("") }
    Column(verticalArrangement = Arrangement.spacedBy(Space.md)) {
        Text(
            if (t.holding) "همه‌ی ایجنت‌های همه‌ی شرکت‌ها همین حالا متوقف میشوند. هیچ چیز از دست نمیرود و هر وقت بخواهی ادامه میدهی."
            else "همه‌ی ایجنت‌های ${t.nameFa} همین حالا متوقف میشوند. هیچ چیز از دست نمیرود و هر وقت بخواهی ادامه میدهی.",
            style = Divan.type.body, color = c.textPrimary,
        )
        Consequences(
            listOf(
                DivanIcon.PAUSE to "هیچ ایجنتی اقدام نوشتنی نمیکند؛ اجراهای در جریان همان‌جا میایستند.",
                DivanIcon.URGENT to "فقط کارهای اضطراری (P0) اجرا میشوند.",
                DivanIcon.MEMORY to "کارها، پیام‌ها و کارت‌ها سر جایشان میمانند؛ چیزی پاک نمیشود.",
                DivanIcon.LOCK to "ادامه دادن با اثر انگشت یا چهره است.",
            ),
            c.negative,
        )
        HqButton("فوری، بدون دلیل", { onStop("توقف فوری به دستور مدیر کل") }, Modifier.fillMaxWidth(), variant = BtnVariant.DANGER, size = BtnSize.LG, icon = DivanIcon.PAUSE, enabled = !busy)
        Text("یا با دلیلی کوتاه برای دفتر Audit:", style = Divan.type.caption, color = c.textMuted)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(Space.xs), verticalArrangement = Arrangement.spacedBy(Space.xs)) {
            for (r in STOP_REASONS) FilterChip(r, reason == r, { reason = if (reason == r) "" else r })
        }
        HqTextField(reason, { reason = it }, "دلیل (یک خط)", Modifier.fillMaxWidth(), maxLength = 300)
        Row(horizontalArrangement = Arrangement.spacedBy(Space.xs)) {
            HqButton("متوقف کن", { onStop(reason.trim()) }, Modifier.weight(1f), variant = BtnVariant.DANGER, icon = DivanIcon.PAUSE, enabled = reason.isNotBlank() && !busy, loading = busy)
            HqButton("انصراف", onCancel, Modifier.weight(1f), variant = BtnVariant.GHOST)
        }
    }
}

/** Releasing a switch: who stopped it and why, what resumes, and the passkey (`kill_switch.release` on the scope). */
@Composable
fun ResumeContent(t: CoTarget, s: CoState, busy: Boolean, onResume: (String) -> Unit, onCancel: () -> Unit) {
    val c = Divan.colors
    var reason by rememberSaveable { mutableStateOf("") }
    Column(verticalArrangement = Arrangement.spacedBy(Space.md)) {
        s.switch?.let { k ->
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(Radius.tile)).background(c.softNegative).padding(Space.sm), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text("متوقف از ${ago(k.changedAt)}، ${byFa(k.changedBy)}", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                k.reason?.takeIf { it.isNotBlank() }?.let { Text("«$it»", style = Divan.type.small, color = c.textSecondary) }
            }
        }
        Consequences(
            listOf(
                DivanIcon.RESUME to (if (t.holding) "همه‌ی شرکت‌ها از همان‌جا که ایستاده بودند ادامه میدهند؛ کلید هر شرکت سر جای خودش میماند." else "ایجنت‌های ${t.nameFa} از همان‌جا که ایستاده بودند ادامه میدهند."),
                DivanIcon.SEAL to "با اثر انگشت یا چهره تأیید میشود و در دفتر Audit میماند.",
            ),
            c.positive,
        )
        HqTextField(reason, { reason = it }, "یادداشت (اختیاری)", Modifier.fillMaxWidth(), maxLength = 300)
        Row(horizontalArrangement = Arrangement.spacedBy(Space.xs)) {
            HqButton("ادامه با اثر انگشت", { onResume(reason.trim().ifBlank { "ادامه به دستور مدیر کل" }) }, Modifier.weight(1f), variant = BtnVariant.PRIMARY, icon = DivanIcon.RESUME, loading = busy)
            HqButton("انصراف", onCancel, Modifier.weight(1f), variant = BtnVariant.GHOST)
        }
    }
}

private val SPANS = listOf(1 to "یک ساعت", 4 to "چهار ساعت", 24 to "یک روز", 72 to "سه روز")

@Composable
fun FreezeContent(t: CoTarget, busy: Boolean, onFreeze: (Int, String) -> Unit, onCancel: () -> Unit) {
    val c = Divan.colors
    var span by rememberSaveable { mutableStateOf(4) }
    var reason by rememberSaveable { mutableStateOf("") }
    Column(verticalArrangement = Arrangement.spacedBy(Space.md)) {
        Text("تا پایان این مدت هیچ deployی در ${t.nameFa} انجام نمیشود؛ کارهای دیگر ادامه دارند.", style = Divan.type.body)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(Space.xs), verticalArrangement = Arrangement.spacedBy(Space.xs)) {
            for ((h, l) in SPANS) FilterChip(l, span == h, { span = h })
        }
        Consequences(
            listOf(
                DivanIcon.LOCK to "هیچ انتشاری بیرون نمیرود؛ کارت‌های deploy منتظر میمانند.",
                DivanIcon.RESUME to "زودتر باز کردن با اثر انگشت یا چهره است.",
            ),
            c.warning,
        )
        HqTextField(reason, { reason = it }, "دلیل (یک خط)", Modifier.fillMaxWidth(), maxLength = 300)
        Row(horizontalArrangement = Arrangement.spacedBy(Space.xs)) {
            HqButton("ببند", { onFreeze(span, reason.trim().ifBlank { "توقف deploy به دستور مدیر کل" }) }, Modifier.weight(1f), variant = BtnVariant.PRIMARY, icon = DivanIcon.LOCK, loading = busy)
            HqButton("انصراف", onCancel, Modifier.weight(1f), variant = BtnVariant.GHOST)
        }
    }
}

@Composable
fun UnfreezeContent(t: CoTarget, s: CoState, busy: Boolean, onOpen: (String) -> Unit, onCancel: () -> Unit) {
    val c = Divan.colors
    var reason by rememberSaveable { mutableStateOf("") }
    Column(verticalArrangement = Arrangement.spacedBy(Space.md)) {
        s.freeze?.let { f ->
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(Radius.tile)).background(c.softWarning).padding(Space.sm), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(buildAnnotatedString { append("بسته تا "); appendProse(jTime(f.until)); append("، ${until(f.until)}، ${byFa(f.createdBy)}") }, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                f.reason.takeIf { it.isNotBlank() }?.let { Text("«$it»", style = Divan.type.small, color = c.textSecondary) }
            }
        }
        Consequences(
            listOf(
                DivanIcon.RESUME to "همه‌ی توقف‌های deploy ${t.nameFa} برداشته میشود، حتی آن‌هایی که خط انتشار یا مدیرعامل گذاشته‌اند.",
                DivanIcon.SEAL to "با اثر انگشت یا چهره تأیید میشود.",
            ),
            c.warning,
        )
        HqTextField(reason, { reason = it }, "یادداشت (اختیاری)", Modifier.fillMaxWidth(), maxLength = 300)
        Row(horizontalArrangement = Arrangement.spacedBy(Space.xs)) {
            HqButton("باز کن با اثر انگشت", { onOpen(reason.trim().ifBlank { "deploy به دستور مدیر کل باز شد" }) }, Modifier.weight(1f), variant = BtnVariant.PRIMARY, icon = DivanIcon.RESUME, loading = busy)
            HqButton("انصراف", onCancel, Modifier.weight(1f), variant = BtnVariant.GHOST)
        }
    }
}

// ==================================================================================== control room ==
/** One change of a switch or of deploys, as the history shows it. */
@Immutable
data class ControlEvent(val at: String, val kind: String, val by: Actor, val reason: String?, val until: String? = null, val stepUp: Boolean = false)

/**
 * A company's control history (newest first): the audit rows of its kill switch and deploy freezes (who and when, every actor), with
 * the owner's reasons from `GET /owner/interactions?kind=control` (an agent's reason is known only for the switch as it stands).
 */
suspend fun Api.controlHistory(code: String, holding: Boolean, limit: Int = 12): List<ControlEvent> = coroutineScope {
    val scope = com.coinepro.hq.core.data.scopeOf(code, holding)
    val engage = async { audit(code, "kill_switch.engage", limit).items }
    val release = async { audit(code, "kill_switch.release", limit).items }
    val freeze = async { if (holding) emptyList() else audit(code, "deploy_freeze.set", limit).items }
    val mine = async { runCatching { ownerInteractions("control", 100).items }.getOrDefault(emptyList()) }
    val owner = mine.await()
    fun reasonOf(at: String, action: String, ref: String): Pair<String?, String?> {
        val t = instant(at)?.toEpochMilli() ?: return null to null
        val hit = owner.filter { it.action == action && it.target["ref"] == ref }.minByOrNull { kotlin.math.abs((instant(it.at)?.toEpochMilli() ?: 0) - t) }
            ?.takeIf { kotlin.math.abs((instant(it.at)?.toEpochMilli() ?: 0) - t) < 5_000 }
        val d = hit?.data ?: return null to null
        return (d["reason"] as? JsonPrimitive)?.contentOrNull to (d["until"] as? JsonPrimitive)?.contentOrNull
    }
    val switches = (engage.await() + release.await()).filter { (it.target["ref"] ?: scope) == scope }.map { e ->
        val (why, _) = if (e.actor.kind == "owner") reasonOf(e.at, "kill_switch.set", scope) else null to null
        ControlEvent(e.at, if (e.action.endsWith("engage")) "engage" else "release", e.actor, why, stepUp = e.stepUp)
    }
    val freezes = freeze.await().filter { (it.target["ref"] ?: code) == code }.map { e ->
        val (why, until) = if (e.actor.kind == "owner") reasonOf(e.at, "deploy_freeze.set", code) else null to null
        ControlEvent(e.at, if (e.summary == "lifted") "unfreeze" else "freeze", e.actor, why, until)
    }
    (switches + freezes).sortedByDescending { instant(it.at)?.toEpochMilli() ?: 0 }.take(limit)
}

/**
 * The company page's control room, one card per item of the page: the state and its switches, who changed them, when and why, the
 * month's budget with a quick edit, the live activity of its agents, hiring, and its sites' health.
 */
fun androidx.compose.foundation.lazy.LazyListScope.controlRoom(co: Company?, d: ControlData, ui: ControlUi) {
    if (co == null) {
        item(key = "control-loading") { Skeleton(Modifier.fillMaxWidth().height(260.dp), radius = Radius.card) }
        return
    }
    val holding = co.kind == "holding"
    val t = CoTarget(co.code, co.nameFa ?: co.code, holding)
    item(key = "control-state") { StateCard(co, d.state(co.code, holding, co), t, d, ui) }
    item(key = "control-history") { HistoryCard(co.code, holding, d.state(co.code, holding, co)) }
    item(key = "control-budget") { BudgetCard(t, ui) }
    item(key = "control-live") { LiveFeedCard(co.code, holding, d) }
    item(key = "control-hiring") { HiringCard(co.code, holding) }
    if (!holding) item(key = "control-sites") { SitesCard(co.code) }
}

@Composable
private fun StateCard(co: Company, s: CoState, t: CoTarget, d: ControlData, ui: ControlUi) {
    val c = Divan.colors
    val lamp = lampOf(s)
    val tint = lampColor(lamp)
    val bg by animateColorAsState(when (lamp) { Lamp.STOP -> c.softNegative; Lamp.FREEZE -> c.card; Lamp.RUN -> c.card }, motionShort(), label = "state-bg")
    HqCard(Modifier.fillMaxWidth(), color = bg) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Space.sm)) {
            ActivityRing(co.code, t.holding, !s.running, d.busy(co.code), d.stirred(co.code), size = 64.dp)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(
                    when { s.stopped -> "متوقف"; s.holdingStopped -> "متوقف با هلدینگ"; d.busy(co.code) -> "در حال کار"; else -> "روشن و آرام" },
                    style = Divan.type.h2, color = if (s.running) c.textPrimary else tint,
                )
                StateLine(s, d, null)
            }
        }
        if (s.stopped) s.switch?.reason?.takeIf { it.isNotBlank() }?.let {
            Text("«$it»", style = Divan.type.small, color = c.textSecondary, modifier = Modifier.padding(top = Space.xs))
        }
        Spacer(Modifier.height(Space.md))
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(Radius.tile)).background(c.tile)) {
            SwitchRow(
                DivanIcon.PAUSE, "کلید توقف",
                AnnotatedString(if (s.stopped) "روشن: ایجنت‌ها ایستاده‌اند" else "خاموش: ایجنت‌ها کار میکنند"),
                if (s.stopped) c.negative else c.silverInk,
            ) {
                if (s.stopped) HqButton("ادامه", { ui.open(ControlSheet.Resume(t)) }, size = BtnSize.SM, variant = BtnVariant.PRIMARY, icon = DivanIcon.RESUME)
                else HqButton("توقف", { ui.open(ControlSheet.Stop(t)) }, size = BtnSize.SM, variant = BtnVariant.DANGER, icon = DivanIcon.PAUSE)
            }
            if (!t.holding) {
                Box(Modifier.fillMaxWidth().padding(horizontal = Space.sm).height(1.dp).background(c.lineDivider))
                SwitchRow(
                    DivanIcon.LOCK, "deploy",
                    s.freeze?.let { buildAnnotatedString { append("بسته تا "); appendProse(jTime(it.until)); append("، ${until(it.until)}") } } ?: AnnotatedString("باز: انتشارها با مُهر تو بیرون میروند"),
                    if (s.frozen) c.warning else c.silverInk,
                ) {
                    if (s.frozen) HqButton("باز کن", { ui.open(ControlSheet.Unfreeze(t)) }, size = BtnSize.SM, icon = DivanIcon.RESUME)
                    else HqButton("ببند", { ui.open(ControlSheet.Freeze(t)) }, size = BtnSize.SM, variant = BtnVariant.GHOST, icon = DivanIcon.LOCK)
                }
            }
        }
    }
}

@Composable
private fun SwitchRow(icon: DivanIcon, title: String, note: AnnotatedString, tint: Color, action: @Composable () -> Unit) {
    val c = Divan.colors
    Row(Modifier.fillMaxWidth().padding(Space.sm), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Space.sm)) {
        Box(Modifier.size(36.dp).clip(CircleShape).background(tint.copy(alpha = 0.14f)), contentAlignment = Alignment.Center) { DIcon(icon, size = 18.dp, tint = tint) }
        Column(Modifier.weight(1f)) {
            Text(title, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
            Text(note, style = Divan.type.caption, color = c.textMuted, maxLines = 2, overflow = TextOverflow.Ellipsis)
        }
        action()
    }
}

@Composable
private fun HistoryCard(code: String, holding: Boolean, s: CoState) {
    val c = Divan.colors
    val q = rememberQuery("control:history:$code", "control", maxAgeMs = 30_000) { controlHistory(code, holding) }
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("تاریخچه‌ی کلیدها", note = "چه کسی، کی و چرا")
        Spacer(Modifier.height(Space.sm))
        Loadable(q, skeleton = { Skeleton(Modifier.fillMaxWidth().height(120.dp), radius = Radius.tile) }) { rows ->
            if (rows.isEmpty()) Text("هنوز هیچ کلیدی زده نشده.", style = Divan.type.caption, color = c.textMuted)
            else Column {
                rows.forEachIndexed { i, e ->
                    // The switch as it stands carries its reason, whoever pulled it.
                    val why = e.reason ?: s.switch?.takeIf { k ->
                        i == rows.indexOfFirst { it.kind == "engage" || it.kind == "release" } && k.changedBy == e.by.code && (k.state == "engaged") == (e.kind == "engage")
                    }?.reason
                    HistoryRow(e, why, last = i == rows.lastIndex)
                }
            }
        }
    }
}

@Composable
private fun HistoryRow(e: ControlEvent, why: String?, last: Boolean) {
    val c = Divan.colors
    val (icon, tint, title) = when (e.kind) {
        "engage" -> Triple(DivanIcon.PAUSE, c.negative, "متوقف شد")
        "release" -> Triple(DivanIcon.RESUME, c.positive, "ادامه داد")
        "freeze" -> Triple(DivanIcon.LOCK, c.warning, "deploy بسته شد")
        else -> Triple(DivanIcon.RESUME, c.silverInk, "deploy باز شد")
    }
    val line = c.lineDivider
    Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(Space.sm)) {
        // The timeline: a dot per change on a thin line.
        Box(Modifier.width(24.dp).fillMaxHeight().drawBehind {
            if (!last) drawLine(line, Offset(size.width / 2, 24.dp.toPx()), Offset(size.width / 2, size.height), 1.dp.toPx())
        }) {
            Box(Modifier.padding(top = 2.dp).size(24.dp).clip(CircleShape).background(tint.copy(alpha = 0.14f)), contentAlignment = Alignment.Center) { DIcon(icon, size = 13.dp, tint = tint) }
        }
        Column(Modifier.weight(1f).padding(bottom = if (last) 0.dp else Space.sm), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(title, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), modifier = Modifier.weight(1f, fill = false))
                Text(actorLabel(e.by), style = Divan.type.caption, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                if (e.stepUp) DIcon(DivanIcon.SEAL, size = 12.dp, tint = c.goldInk)
            }
            // When: how long ago (a prose count), then the date and time (figures).
            Text(
                buildAnnotatedString {
                    append(ago(e.at)); append("، "); appendProse(jDateTime(e.at))
                    e.until?.let { append("، تا "); appendProse(jTime(it)) }
                },
                style = Divan.type.micro, color = c.textMuted,
            )
            why?.takeIf { it.isNotBlank() }?.let { Text("«$it»", style = Divan.type.caption, color = c.textSecondary) }
        }
    }
}

private fun actorLabel(a: Actor): AnnotatedString = buildAnnotatedString {
    when {
        a.kind == "owner" -> append("تو")
        a.code == "pipeline" -> append("خط انتشار")
        !a.displayFa.isNullOrBlank() -> append(a.displayFa)
        else -> fig(a.code)
    }
}

/** The month's budget as a gauge, with a quick edit sealed with the passkey on the exact body (PUT /budgets, `budgets.update`). */
@Composable
private fun BudgetCard(t: CoTarget, ui: ControlUi) {
    val c = Divan.colors
    val q = rememberQuery("treasury:budgets", "treasury") { budgets() }
    var editing by rememberSaveable { mutableStateOf(false) }
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("بودجه‌ی ماه", note = if (t.holding) "سقف کل هلدینگ؛ هشدار در ۷۰٪ و ۹۰٪" else "پاکت ماه؛ هشدار در ۷۰٪ و ۹۰٪") {
            HqButton(if (editing) "بستن" else "ویرایش", { editing = !editing }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = if (editing) DivanIcon.CLOSE else DivanIcon.EDIT)
        }
        Spacer(Modifier.height(Space.sm))
        Loadable(q, skeleton = { Skeleton(Modifier.fillMaxWidth().height(150.dp), radius = Radius.tile) }) { list ->
            val b = list.firstOrNull { it.company == t.code && it.scopeType == (if (t.holding) "holding" else "company") && it.period == "month" }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Space.md)) {
                Gauge(b?.pct, Modifier.size(width = 132.dp, height = 96.dp))
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(Space.xs)) {
                    BudgetFact("توکن", "${tokens(b?.tokensUsed ?: 0)} / ${tokens(b?.tokenLimit)}")
                    BudgetFact(if (b?.usdLimit == null) "دلار معادل (بی‌سقف)" else "دلار معادل", b?.usdLimit?.let { "${usd(b.usdUsed)} / ${usd(it)}" } ?: usd(b?.usdUsed ?: "0"))
                    if (b?.tokenLimit == null && b?.usdLimit == null) Text("سقفی تعیین نشده؛ این شرکت بی‌پاکت است.", style = Divan.type.caption, color = c.warning)
                }
            }
            AnimatedVisibility(editing, enter = expandIn(), exit = collapseOut()) {
                BudgetEditor(b, ui.busy) { tok, usdLimit -> ui.budget(t, tok, usdLimit) { editing = false } }
            }
        }
    }
}

@Composable
private fun BudgetFact(label: String, value: String) {
    Column {
        Text(label, style = Divan.type.micro, color = Divan.colors.textMuted)
        com.coinepro.hq.designsystem.Fig(value, style = Divan.type.figure)
    }
}

/** A half-ring meter: silver below 70%, warning to 90%, red above; it fills when it appears. */
@Composable
fun Gauge(pct: Double?, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val reduced = LocalReducedMotion.current
    val target = ((pct ?: 0.0) / 100.0).coerceIn(0.0, 1.0).toFloat()
    val v = remember { androidx.compose.animation.core.Animatable(if (reduced) target else 0f) }
    androidx.compose.runtime.LaunchedEffect(target, reduced) { v.animateTo(target, Motion.emphasised(reduced)) }
    val tone = com.coinepro.hq.designsystem.barColor(com.coinepro.hq.designsystem.budgetTone(pct))
    val track = c.tile
    Box(modifier, contentAlignment = Alignment.BottomCenter) {
        Canvas(Modifier.matchParentSize()) {
            val sw = 10.dp.toPx()
            val d = min(size.width, size.height * 2) - sw
            val tl = Offset((size.width - d) / 2, sw / 2)
            drawArc(track, 180f, 180f, false, tl, Size(d, d), style = Stroke(sw, cap = StrokeCap.Round))
            // Right to left: the fill grows from the start of the reading direction (the right).
            if (v.value > 0f) drawArc(tone, 0f, -180f * v.value, false, tl, Size(d, d), style = Stroke(sw, cap = StrokeCap.Round))
        }
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(pct?.let { "${it.toInt()}٪" } ?: "—", style = Divan.type.h2, color = if ((pct ?: 0.0) >= 90) c.negative else if ((pct ?: 0.0) >= 70) c.warning else c.textPrimary)
            Text("از سقف ماه", style = Divan.type.micro, color = c.textMuted)
        }
    }
}

@Composable
private fun BudgetEditor(b: BudgetUse?, busy: Boolean, save: (Long?, String?) -> Unit) {
    val c = Divan.colors
    val base = b?.tokenLimit
    var text by rememberSaveable(base) { mutableStateOf(base?.let { millions(it) }.orEmpty()) }
    val parsed = parseMillions(text)
    Column(Modifier.padding(top = Space.md), verticalArrangement = Arrangement.spacedBy(Space.sm)) {
        Text("سقف تازه به میلیون توکن", style = Divan.type.caption, color = c.textMuted)
        if (base != null) FlowRow(horizontalArrangement = Arrangement.spacedBy(Space.xs), verticalArrangement = Arrangement.spacedBy(Space.xs)) {
            for ((k, l) in listOf(0.8 to "−۲۰٪", 1.2 to "+۲۰٪", 1.5 to "+۵۰٪", 2.0 to "دو برابر")) {
                val v = Math.round(base * k)
                FilterChip(l, parsed == v, { text = millions(v) })
            }
        }
        HqTextField(text, { text = it }, "مثلاً 6", Modifier.fillMaxWidth(), maxLength = 10, figure = true)
        val diff = if (parsed != null && base != null) parsed - base else null
        diff?.takeIf { it != 0L }?.let {
            Text(buildAnnotatedString { append(if (it > 0) "افزایش " else "کاهش "); fig(tokens(kotlin.math.abs(it))); append(" توکن در ماه") }, style = Divan.type.caption, color = if (it > 0) c.warning else c.positive)
        }
        HqButton("ذخیره با اثر انگشت", { save(parsed, b?.usdLimit) }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, enabled = parsed != null && parsed != base, loading = busy)
    }
}

private fun millions(tokens: Long): String = (tokens / 1_000_000.0).let { if (it == Math.floor(it)) it.toLong().toString() else String.format(java.util.Locale.US, "%.2f", it).trimEnd('0').trimEnd('.') }

/** What its agents are doing: runs started and finished, outputs, cards, from the stream as they happen and the latest before. */
@Composable
private fun LiveFeedCard(code: String, holding: Boolean, d: ControlData) {
    val c = Divan.colors
    val nav = LocalNav.current
    val runs = rememberQuery("runs:company:$code", "runs", maxAgeMs = 15_000) { runs(company = code, limit = 12) }
    val outs = rememberQuery("deliverables:company:$code", "deliverables", maxAgeMs = 30_000) { deliverables(company = code, limit = 6) }
    val cards = rememberQuery("decisions:company:$code", "decisions", maxAgeMs = 30_000) { decisions(status = null, company = code, limit = 20) }
    val rows = remember(d.pulses[code], runs.data, outs.data, cards.data) {
        feedOf(d.pulses[code]?.recent.orEmpty().map { FeedRow(it.at, it.type, it.ref, it.data["employee"].str(), it.data["state"].str()) }, runs.data?.items.orEmpty(), outs.data?.items.orEmpty().filter { it.company == code }, cards.data?.items.orEmpty().filter { it.company == code })
    }
    val live = d.busy(code)
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("فعالیت زنده", note = if (holding) "مشاور، ناظر، دستیار و کارهای خود هلدینگ" else "اجراها، خروجی‌ها و کارت‌ها، همان لحظه") {
            Pill(if (live) "در حال کار" else "آرام", if (live) Tone.POS else Tone.NEUTRAL, live = live, dot = !live)
        }
        Spacer(Modifier.height(Space.sm))
        when {
            rows.isEmpty() && runs.data == null -> Skeleton(Modifier.fillMaxWidth().height(160.dp), radius = Radius.tile)
            rows.isEmpty() -> Text("هنوز خبری نیست؛ ایجنت‌ها تا رسیدن کار خواب‌اند.", style = Divan.type.caption, color = c.textMuted)
            else -> Column(Modifier.smoothSize()) {
                rows.take(8).forEach { r -> FeedLine(r) { ref -> com.coinepro.hq.ui.v17.refRoute(ref)?.let(nav::go) } }
            }
        }
    }
}

@Immutable
data class FeedRow(val at: String, val type: String, val ref: String?, val employee: String?, val state: String?)

/** The feed: the stream's events and the latest runs, outputs and cards, newest first, each once. */
fun feedOf(live: List<FeedRow>, runs: List<Run>, outs: List<com.coinepro.hq.core.net.Deliverable>, cards: List<com.coinepro.hq.core.net.Decision>): List<FeedRow> {
    val loaded = runs.flatMap { r ->
        listOfNotNull(
            r.startedAt?.let { FeedRow(it, "run.started", r.id, r.employee, null) },
            r.finishedAt?.let { FeedRow(it, "run.finished", r.id, r.employee, r.state) },
        )
    } + outs.map { FeedRow(it.createdAt, "deliverable.created", it.ref, it.producer.code, null) } +
        cards.flatMap { k -> listOfNotNull(FeedRow(k.createdAt, "decision.created", k.ref, null, null), k.decidedAt?.let { FeedRow(it, "decision.decided", k.ref, null, k.status) }) }
    return (live + loaded).distinctBy { "${it.type}|${it.ref}" }.sortedByDescending { instant(it.at)?.toEpochMilli() ?: 0 }
}

@Composable
fun FeedLine(r: FeedRow, open: (String) -> Unit) {
    val c = Divan.colors
    val (icon, tint) = when {
        r.type == "run.started" -> DivanIcon.AGENT to c.goldInk
        r.type == "run.finished" && r.state == "done" -> DivanIcon.SEAL to c.positive
        r.type == "run.finished" -> DivanIcon.URGENT to c.warning
        r.type.startsWith("deliverable") -> DivanIcon.DELIVERABLE to c.silverInk
        r.type.startsWith("decision") -> DivanIcon.CARTABLE to c.goldInk
        r.type.startsWith("control") -> DivanIcon.LOCK to c.negative
        else -> DivanIcon.TASK to c.silverInk
    }
    val text = buildAnnotatedString {
        fun who() { r.employee?.let { append(" "); fig(it) } }
        when (r.type) {
            "run.started" -> { append("اجرای"); who(); append(" شروع شد") }
            "run.finished" -> { append("اجرای"); who(); append(when (r.state) { "done" -> " تمام شد"; "failed" -> " شکست خورد"; "refused" -> " ایستاد"; else -> " بسته شد" }) }
            "deliverable.created" -> { append("خروجی تازه "); r.ref?.let { fig(it, c.goldInk) } }
            "deliverable.rated" -> { append("امتیاز تو به "); r.ref?.let { fig(it, c.goldInk) } }
            "decision.created" -> { append("کارت تازه در کارتابل "); r.ref?.let { fig(it, c.goldInk) } }
            "decision.decided" -> { append("تصمیم "); r.ref?.let { fig(it, c.goldInk) }; append(" گرفته شد") }
            "control.changed" -> append("کلیدها تغییر کرد")
            else -> { append("کار "); r.ref?.let { fig(it, c.goldInk) }; append(" به‌روز شد") }
        }
    }
    val ref = r.ref?.takeIf { r.type.startsWith("deliverable") || r.type.startsWith("decision") || r.type.startsWith("work") }
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(Radius.small)).then(if (ref != null) Modifier.clickable { open(ref) } else Modifier).padding(vertical = 7.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(Space.sm),
    ) {
        Box(Modifier.size(28.dp).clip(CircleShape).background(tint.copy(alpha = 0.12f)), contentAlignment = Alignment.Center) { DIcon(icon, size = 14.dp, tint = tint) }
        Text(text, style = Divan.type.small, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
        Text(ago(r.at), style = Divan.type.micro, color = c.textMuted)
    }
}

private fun kotlinx.serialization.json.JsonElement?.str(): String? = (this as? JsonPrimitive)?.contentOrNull

/** Hiring: whether it is open and how, and this company's envelope this month (§18.11). */
@Composable
private fun HiringCard(code: String, holding: Boolean) {
    val c = Divan.colors
    val nav = LocalNav.current
    val q = rememberQuery("hiring", "hiring") { hiring() }
    HqCard(Modifier.fillMaxWidth(), onClick = { nav.go("settings") }, onClickLabel = "تنظیمات استخدام") {
        SectionTitle("استخدام") { DIcon(DivanIcon.NEXT, size = 16.dp, tint = c.textMuted) }
        Spacer(Modifier.height(Space.xs))
        Loadable(q, skeleton = { Skeleton(Modifier.fillMaxWidth().height(64.dp), radius = Radius.tile) }) { h ->
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Space.xs)) {
                when {
                    h.state != "open" -> Pill("بسته", Tone.NEUTRAL, icon = DivanIcon.LOCK)
                    h.mode == "delegated" -> Pill("باز؛ مدیرعامل‌ها در پاکت", Tone.POS, dot = true)
                    else -> Pill("باز؛ هر استخدام کارت تو", Tone.GOLD, dot = true)
                }
                h.changedAt?.let { Text("از ${ago(it)}", style = Divan.type.caption, color = c.textMuted) }
            }
            val e = h.envelopes.firstOrNull { it.company == code }
            if (!holding && e != null) {
                Spacer(Modifier.height(Space.sm))
                val limit = e.tokensMonth
                Text(
                    buildAnnotatedString {
                        append("پاکت ماه "); fig(tokens(limit)); append("؛ تعهد "); fig(tokens(e.committedMonth)); append("، مصرف "); fig(tokens(e.usedMonth))
                        append("؛ ${e.hiresMonth} استخدام این ماه")
                    },
                    style = Divan.type.caption, color = c.textSecondary,
                )
                if (limit != null && limit > 0) com.coinepro.hq.designsystem.MeterBar(100.0 * e.committedMonth / limit, Modifier.padding(top = Space.xs), tone = com.coinepro.hq.designsystem.budgetTone(100.0 * e.committedMonth / limit))
                else Text("بی‌پاکت: استخدام واگذارشده برای این شرکت ممکن نیست.", style = Divan.type.caption, color = c.warning)
            }
        }
    }
}

/** The company's sites (§16.4): up or down, the last check, the day's uptime, and open incidents. Nothing when it has none. */
@Composable
private fun SitesCard(code: String) {
    val c = Divan.colors
    val nav = LocalNav.current
    val sites = rememberQuery("ops:sites:$code", "ops", maxAgeMs = 60_000) { sites(code) }
    val incidents = rememberQuery("ops:incidents:$code:open", "ops", maxAgeMs = 60_000) { incidents(code, open = true) }
    val list = sites.data?.filter { it.enabled } ?: return
    if (list.isEmpty()) return
    val open = incidents.data.orEmpty()
    HqCard(Modifier.fillMaxWidth(), onClick = { nav.go("sites") }, onClickLabel = "پایش سایت‌ها") {
        SectionTitle("سلامت سایت‌ها", note = if (open.isEmpty()) "هیچ رخداد بازی نیست" else "${open.size} رخداد باز") {
            if (open.isEmpty()) Pill("سالم", Tone.POS, dot = true) else Pill("رخداد", Tone.NEG, icon = DivanIcon.URGENT)
        }
        Spacer(Modifier.height(Space.xs))
        list.forEach { s ->
            val ok = s.last?.ok != false && s.consecutiveFailures == 0
            Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Space.xs)) {
                LiveDot(if (ok) c.positive else c.negative, live = false, size = 8.dp)
                com.coinepro.hq.designsystem.Fig(s.url.removePrefix("https://").removePrefix("http://"), Modifier.weight(1f), style = Divan.type.figureSmall, color = c.textPrimary)
                s.last?.ms?.let { com.coinepro.hq.designsystem.Fig("${it}ms", style = Divan.type.figureSmall, color = if (it > 1500) c.warning else c.textMuted) }
                s.uptime24h?.let { com.coinepro.hq.designsystem.Fig(String.format(java.util.Locale.US, "%.1f%%", it * 100), style = Divan.type.figureSmall, color = c.textSecondary) }
            }
        }
    }
}
