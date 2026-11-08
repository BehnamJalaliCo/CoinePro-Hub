package com.coinepro.hq.ui.session

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.LivePanel
import com.coinepro.hq.core.data.PACE_FA
import com.coinepro.hq.core.data.PlanProgress
import com.coinepro.hq.core.data.elapsedFa
import com.coinepro.hq.core.data.idleFa
import com.coinepro.hq.core.data.lineFa
import com.coinepro.hq.core.data.lineKey
import com.coinepro.hq.core.data.livePanelOf
import com.coinepro.hq.core.data.quietLine
import com.coinepro.hq.core.data.othersFa
import com.coinepro.hq.core.data.planProgressFa
import com.coinepro.hq.core.data.recentLines
import com.coinepro.hq.core.data.workingHeadFa
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.net.ActivityLine
import com.coinepro.hq.core.net.SessionActivity
import com.coinepro.hq.core.net.SessionWorker
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Chevron
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.LiveDot
import com.coinepro.hq.designsystem.LocalReducedMotion
import com.coinepro.hq.designsystem.Motion
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.motionMedium
import com.coinepro.hq.designsystem.smoothSize
import com.coinepro.hq.designsystem.timesFig
import kotlinx.coroutines.delay

// Contract §41 ⟨1.23⟩ ⟨0.19.0⟩ «مثل خود کلود کد»: the owner sees the work happen. A slim panel pinned over the composer (it takes its
// own room, so it never covers the chat's last word): who works and at which step, for how long, and the last lines of the work arriving
// one by one (the newest at the bottom, the older ones fading); a tap opens «کار زنده», every line. When nobody works it says why: he is
// asked, it is stuck (warm, with «ادامه بده»), or it is quiet since a time (and «ادامه بده», small). The pace («با من | خودکار») and the
// plan's progress («کار ۳ از ۹») are in the head again.

/** The clock the panel reads, a second at a time while someone works (still in the screenshot tests: [HqClock] is fixed there). */
@Composable
private fun rememberNow(ticking: Boolean): Long {
    var now by remember { mutableLongStateOf(HqClock.millis()) }
    LaunchedEffect(ticking) {
        now = HqClock.millis()
        while (ticking) { delay(1_000); now = HqClock.millis() }
    }
    return now
}

/** ⟨1.24⟩ SE-1: more than five lines in a second arrive without motion (a burst is read, not watched). True while the lines come calmly. */
@Composable
private fun rememberCalm(keys: List<String>): Boolean {
    val arrivals = remember { ArrayDeque<Long>() }
    val known = remember { HashSet<String>() }
    val now = android.os.SystemClock.uptimeMillis()
    for (k in keys) if (known.add(k)) arrivals.addLast(now)
    while (arrivals.isNotEmpty() && now - arrivals.first() > 1_000) arrivals.removeFirst()
    return arrivals.size <= 5
}

/** A new line arrives softly (M1, 200 ms; still when animations are removed or in a burst); [alpha] is its place among the lines. */
@Composable
private fun Arriving(alpha: Float, calm: Boolean = true, content: @Composable () -> Unit) {
    val reduced = LocalReducedMotion.current || !calm
    val shown = remember { Animatable(if (reduced) 1f else 0f) }
    LaunchedEffect(Unit) { if (!reduced) shown.animateTo(1f, androidx.compose.animation.core.tween(com.coinepro.hq.designsystem.Grammar.SETTLE_ROW, easing = Motion.Standard)) }
    val a by animateFloatAsState(alpha, motionMedium(), label = "line-age")
    Box(Modifier.graphicsLayer { this.alpha = a * shown.value; translationY = (1f - shown.value) * 6.dp.toPx() }) { content() }
}

/** How faint a line is by its age in the panel: the newest whole, each older one fainter. */
private fun ageAlpha(i: Int, n: Int): Float = when (n - 1 - i) { 0 -> 1f; 1 -> 0.74f; 2 -> 0.52f; else -> 0.36f }

// ------------------------------------------------------------------- panel --
/**
 * The live panel over the composer. [canNudge]: the hub takes «ادامه بده» (and the session is not waiting for his OK, [ready]).
 * [onOpen] opens «کار زنده».
 */
@Composable
internal fun LiveWorkPanel(a: SessionActivity, ready: Boolean, canNudge: Boolean, nudging: Boolean, onNudge: () -> Unit, onOpen: () -> Unit, nudgeFirst: Boolean = true) {
    when (livePanelOf(a)) {
        LivePanel.WORKING -> WorkingPanel(a, onOpen)
        LivePanel.WAITING -> StateRow(
            DivanIcon.OWNER, Divan.colors.softGold, Divan.colors.goldInk, "منتظر شما", quietLine(a.waitingFa.orEmpty()), onOpen,
        )
        LivePanel.STUCK -> StateRow(
            DivanIcon.URGENT, Divan.colors.softWarning, Divan.colors.warning, "گیر کرده", quietLine(a.stuckFa.orEmpty()), onOpen,
        ) { if (canNudge) HqButton("ادامه بده", onNudge, variant = if (nudgeFirst) BtnVariant.PRIMARY else BtnVariant.SECONDARY, size = BtnSize.SM, icon = DivanIcon.RESUME, loading = nudging) }
        LivePanel.IDLE -> IdleRow(a, canNudge && !ready, nudging, onNudge, onOpen)
    }
}

@Composable
private fun WorkingPanel(a: SessionActivity, onOpen: () -> Unit) {
    val c = Divan.colors
    val lead = a.working.first()
    val now = rememberNow(true)
    var open by rememberSaveable { mutableStateOf(true) }
    val shape = RoundedCornerShape(14.dp)
    val lines = recentLines(a)
    Column(
        Modifier.fillMaxWidth().testTag("live-work").clip(shape).background(c.card).border(1.dp, c.lineDivider, shape)
            .clickable(role = Role.Button, onClickLabel = "همه‌ی کار زنده", onClick = onOpen)
            .padding(start = 12.dp, end = 4.dp, top = 6.dp, bottom = 8.dp).smoothSize(),
        verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            com.coinepro.hq.ui.live.PersonGlyph("working", size = 12.dp)
            Text(
                workingHeadFa(lead), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary,
                maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f),
            )
            elapsedFa(lead.startedAt, now)?.let { Text(it, style = Divan.type.micro, color = c.textMuted, maxLines = 1) }
            Box(
                Modifier.size(32.dp).clip(CircleShape).clickable(role = Role.Button, onClickLabel = if (open) "خط‌ها را ببند" else "خط‌ها را باز کن") { open = !open },
                contentAlignment = Alignment.Center,
            ) { Chevron(open, size = 14.dp, tint = c.textMuted) }
        }
        othersFa(a.working)?.let { Text(it, style = Divan.type.micro, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(end = 8.dp)) }
        val calm = rememberCalm(a.last.map(::lineKey))
        if (open && lines.isNotEmpty()) Column(Modifier.padding(top = 4.dp, end = 8.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            lines.forEachIndexed { i, l -> key(lineKey(l)) { Arriving(ageAlpha(i, lines.size), calm) { PanelLine(l, lead.whoFa, newest = i == lines.lastIndex, now = now) } } }
        } else if (!open && lead.doingFa.isNotBlank()) {
            Text(timesFig(quietLine(lead.doingFa)), style = Divan.type.micro, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(end = 8.dp))
        }
    }
}

/**
 * ⟨1.24⟩ SE-1: a line's mark by its state (§42.2 `line.state`): a step in progress carries a turning arc (M7; «در حال انجام» with
 * animations removed), a step that ended a tick drawn in (M8), one that failed a cross; a hub without the state, the quiet dot as before.
 */
@Composable
private fun LineMark(l: ActivityLine, newest: Boolean) {
    val c = Divan.colors
    when (l.state) {
        "running" -> com.coinepro.hq.designsystem.Arc(true, c.silverInk, size = 10.dp, word = null)
        "done" -> com.coinepro.hq.designsystem.DrawnMark(true, c.positive, size = 10.dp)
        "failed" -> com.coinepro.hq.designsystem.DrawnMark(false, c.negative, size = 10.dp)
        else -> Box(Modifier.size(10.dp), contentAlignment = Alignment.Center) {
            Box(Modifier.size(5.dp).clip(CircleShape).background(if (newest) c.positive else c.lineStrong))
        }
    }
}

/** One line in the panel: its mark, its words in one line, its clock time (a step in progress: for how long it has run). */
@Composable
private fun PanelLine(l: ActivityLine, lead: String?, newest: Boolean, now: Long = HqClock.millis()) {
    val c = Divan.colors
    val reduced = LocalReducedMotion.current
    val running = com.coinepro.hq.core.data.lineRunning(l)
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        LineMark(l, newest)
        Text(
            timesFig(lineFa(l, lead)), style = Divan.type.micro.copy(fontWeight = if (newest) FontWeight.Medium else FontWeight.Normal),
            color = if (l.state == "failed") c.negative else if (newest) c.textPrimary else c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f),
        )
        if (running) Text(listOfNotNull(if (reduced) "در حال انجام" else null, elapsedFa(l.at, now)).joinToString(" · "), style = Divan.type.micro, color = c.textMuted, maxLines = 1)
        else if (l.at.isNotBlank()) Text(timesFig(jTime(l.at)), style = Divan.type.micro, color = c.textMuted, maxLines = 1)
    }
}

/** Waiting for him, or stuck: one tinted row, its words in at most two lines, and its action. */
@Composable
private fun StateRow(icon: DivanIcon, bg: Color, ink: Color, lead: String, body: String, onOpen: () -> Unit, action: @Composable () -> Unit = {}) {
    val c = Divan.colors
    Row(
        Modifier.fillMaxWidth().testTag("live-work").clip(RoundedCornerShape(14.dp)).background(bg)
            .clickable(role = Role.Button, onClickLabel = "همه‌ی کار زنده", onClick = onOpen).padding(start = 12.dp, end = 8.dp, top = 8.dp, bottom = 8.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        DIcon(icon, size = 18.dp, tint = ink)
        Text(
            buildAnnotatedString {
                withStyle(SpanStyle(fontWeight = FontWeight.SemiBold, color = ink)) { append(lead) }
                if (body.isNotBlank()) { append(": "); append(timesFig(body)) }
            },
            style = Divan.type.small, color = c.textPrimary, maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f),
        )
        action()
    }
}

/** Quiet: since when, and «ادامه بده» as a small text button. */
@Composable
private fun IdleRow(a: SessionActivity, canNudge: Boolean, nudging: Boolean, onNudge: () -> Unit, onOpen: () -> Unit) {
    val c = Divan.colors
    val now = rememberNow(false)
    Row(
        Modifier.fillMaxWidth().testTag("live-work").clip(RoundedCornerShape(12.dp)).clickable(role = Role.Button, onClickLabel = "همه‌ی کار زنده", onClick = onOpen)
            .padding(start = 8.dp, end = 0.dp, top = 2.dp, bottom = 2.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        LiveDot(c.textMuted, live = false, size = 7.dp)
        Text(idleFa(a, now), style = Divan.type.caption, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
        if (canNudge) HqButton("ادامه بده", onNudge, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.RESUME, loading = nudging)
    }
}

// ------------------------------------------------------------------- sheet --
/** «کار زنده»: every line of the work, oldest first like a terminal, and at the end what is happening now (who works, or why nobody does,
 *  with «ادامه بده»); the end is brought into view on opening and as lines arrive. */
@Composable
internal fun LiveWorkSheetBody(a: SessionActivity, ready: Boolean, canNudge: Boolean, nudging: Boolean, onNudge: () -> Unit) {
    val c = Divan.colors
    val panel = livePanelOf(a)
    val now = rememberNow(panel == LivePanel.WORKING)
    val end = remember { BringIntoViewRequester() }
    LaunchedEffect(a.last.size, a.last.lastOrNull()?.let(::lineKey)) { delay(250); end.bringIntoView() }
    if (a.last.isEmpty()) Text("هنوز قدمی از کار این جلسه ثبت نشده.", style = Divan.type.small, color = c.textMuted)
    else Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        var prev: String? = null
        for (l in a.last) {
            val who = l.whoFa.trim()
            SheetLine(l, showWho = who.isNotBlank() && who != prev)
            prev = who
        }
    }
    Column(Modifier.bringIntoViewRequester(end), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        androidx.compose.material3.HorizontalDivider(color = c.lineDivider)
        when (panel) {
            LivePanel.WORKING -> for (w in a.working) WorkerCard(w, now)
            else -> LiveWorkPanel(a, ready, canNudge, nudging, onNudge, onOpen = {})
        }
    }
}

@Composable
private fun SheetLine(l: ActivityLine, showWho: Boolean) {
    val c = Divan.colors
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.Top) {
        Text(timesFig(if (l.at.isBlank()) "" else jTime(l.at)), style = Divan.type.micro, color = c.textMuted, maxLines = 1, modifier = Modifier.width(40.dp).padding(top = 2.dp))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(1.dp)) {
            if (showWho) Text(l.whoFa.trim(), style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary, maxLines = 1)
            // ⟨1.24⟩ SE-1: a step's state beside its words (in progress, done, failed) once the hub says it.
            if (l.state != null) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                LineMark(l, newest = false)
                Text(timesFig(quietLine(l.textFa)), style = Divan.type.small, color = if (l.state == "failed") c.negative else c.textPrimary, modifier = Modifier.weight(1f))
            } else Text(timesFig(quietLine(l.textFa)), style = Divan.type.small, color = c.textPrimary)
        }
    }
}

/** One at work: who (of which company), on which work, «قدم ۳ · ۱۲ دقیقه», and what he is doing now. */
@Composable
private fun WorkerCard(w: SessionWorker, now: Long) {
    val c = Divan.colors
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.card).padding(12.dp),
        verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Box(Modifier.padding(top = 4.dp)) { com.coinepro.hq.ui.live.PersonGlyph("working", size = 12.dp) }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(
                listOfNotNull(w.whoFa.trim().ifBlank { "یک همکار" }, w.companyFa?.trim()?.ifBlank { null }?.takeIf { it !in w.whoFa }).joinToString(" · "),
                style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis,
            )
            if (w.workTitleFa.isNotBlank()) Text(timesFig(quietLine(w.workTitleFa)), style = Divan.type.micro, color = c.textMuted, maxLines = 2, overflow = TextOverflow.Ellipsis)
            if (w.doingFa.isNotBlank()) Text(timesFig(quietLine(w.doingFa)), style = Divan.type.small, color = c.textSecondary)
        }
        Text(
            // The time first: a «·» between two figures reads as a Persian zero («۱۴۰۶»).
            listOfNotNull(elapsedFa(w.startedAt, now), w.step.takeIf { it > 0 }?.let { "قدم ${com.coinepro.hq.core.data.faNum(it)}" }).joinToString(" · "),
            style = Divan.type.micro, color = c.textMuted, maxLines = 1,
        )
    }
}

// -------------------------------------------------------------------- head --
/** «با من | خودکار» in the head: small, two parts, the chosen one in gold; switching it is the hub's pace route. */
@Composable
internal fun PaceChip(pace: String, enabled: Boolean, onPace: (String) -> Unit, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Row(
        modifier.height(30.dp).clip(CircleShape).background(c.tile).padding(3.dp).selectableGroup()
            .semantics { contentDescription = "روش کار: ${PACE_FA[pace] ?: PACE_FA.getValue("auto")}" },
        verticalAlignment = Alignment.CenterVertically,
    ) {
        for (p in listOf("step", "auto")) {
            val on = (pace.takeIf { it in PACE_FA } ?: "auto") == p
            Box(
                Modifier.fillMaxHeight().clip(CircleShape).background(if (on) c.softGold else Color.Transparent)
                    .then(if (on) Modifier.border(1.dp, c.lineTahrir, CircleShape) else Modifier)
                    .selectable(on, enabled = enabled, role = Role.RadioButton) { if (!on) onPace(p) }
                    .padding(horizontal = 10.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    PACE_FA.getValue(p), style = Divan.type.micro.copy(fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal),
                    color = if (on) c.goldInk else c.textSecondary, maxLines = 1,
                )
            }
        }
    }
}

/** «کار ۳ از ۹» and a thin bar of what is done; a tap opens the details at the plan. */
@Composable
internal fun PlanProgressRow(p: PlanProgress, current: String?, onPlan: () -> Unit) {
    val c = Divan.colors
    val f by animateFloatAsState(p.fraction, motionMedium(), label = "plan")
    Row(
        Modifier.fillMaxWidth().testTag("plan-progress").clip(RoundedCornerShape(8.dp))
            .clickable(role = Role.Button, onClickLabel = "برنامه", onClick = onPlan).padding(end = 8.dp, top = 2.dp, bottom = 2.dp)
            .semantics { contentDescription = planProgressFa(p) + (current?.let { "، $it" } ?: "") },
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        DIcon(DivanIcon.TASK, size = 14.dp, tint = if (p.finished) c.positive else c.textMuted)
        Text(planProgressFa(p), style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary, maxLines = 1)
        Box(Modifier.weight(1f).height(4.dp).clip(CircleShape).background(c.lineStrong.copy(alpha = 0.45f))) {
            Box(Modifier.fillMaxWidth(f).fillMaxHeight().clip(CircleShape).background(if (p.finished) c.positive else c.goldFill))
        }
    }
}
