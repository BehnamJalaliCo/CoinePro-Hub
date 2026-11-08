package com.coinepro.hq.ui.live

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateFloat
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
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
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.coinepro.hq.core.data.Beat
import com.coinepro.hq.core.data.LiveRules
import com.coinepro.hq.core.data.LiveState
import com.coinepro.hq.core.data.faNum
import com.coinepro.hq.core.data.heartbeatFa
import com.coinepro.hq.core.data.heartbeatOf
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.designsystem.Arc
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Grammar
import com.coinepro.hq.designsystem.LocalReducedMotion
import com.coinepro.hq.designsystem.Motion
import com.coinepro.hq.designsystem.beat
import com.coinepro.hq.designsystem.breath
import com.coinepro.hq.designsystem.collapseOut
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.rememberAppVisible
import com.coinepro.hq.designsystem.timesFig
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import kotlinx.coroutines.delay

// Contract §42 ⟨1.24⟩ ⟨0.20.0⟩, design/LIVE_VIEWS.md: the live views every screen shares. GL-1 the heartbeat (is what I see live?),
// GL-2 the kill-switch band (why everything is still), NO-1 what needs the owner arriving (the urgent banner), PE-1 a person's state by
// shape and word. Each reads the one live store of the stream ([com.coinepro.hq.core.data.LiveStore]).

// ------------------------------------------------------------------ the store, on screen --
/** The live store's state on screen; a view shown before the stream seeded it asks for the seed once. */
@Composable
fun rememberLive(): LiveState {
    val env = LocalEnv.current
    val s by env.stream.live.state.collectAsStateWithLifecycle()
    LaunchedEffect(env) { env.stream.ensureSeeded() }
    return s
}

/** The clock ([HqClock], fixed in the screenshot tests), read again every [periodMs] while [on] and the app is on screen. */
@Composable
fun rememberTicker(periodMs: Long, on: Boolean = true): Long {
    var now by remember { mutableLongStateOf(HqClock.millis()) }
    val visible = rememberAppVisible()
    LaunchedEffect(on, visible, periodMs) {
        now = HqClock.millis()
        while (on && visible) { delay(periodMs); now = HqClock.millis() }
    }
    return now
}

/** GL-1 now: the beat, since when it has not been live, and the clock it was read at. */
data class BeatNow(val beat: Beat, val downSince: Long?, val now: Long) {
    val fa: String get() = heartbeatFa(beat, downSince, now)
}

@Composable
fun rememberBeat(): BeatNow {
    val env = LocalEnv.current
    val state by env.stream.state.collectAsStateWithLifecycle()
    val down by env.stream.downSince.collectAsStateWithLifecycle()
    val online by env.stream.online.collectAsStateWithLifecycle()
    // While not live the age moves (and reconnecting turns old after 45 s): read the clock every few seconds then; nothing while live.
    val now = rememberTicker(5_000, on = state != com.coinepro.hq.core.data.StreamState.LIVE)
    return BeatNow(heartbeatOf(state, down, online, now), down, now)
}

// ------------------------------------------------------------------ GL-1 --
/**
 * GL-1 «زنده»: a dot and a word. Live: the dot breathes once on an event from the hub (at most one in two seconds); reconnecting: a thin
 * arc turns while it retries; old (no word from the hub for 45 s): amber and still, «قدیمی · ۲ دقیقه»; no network: a hollow dot,
 * «بی‌اتصال». Announced politely when it changes. [compact]: the corner of a live panel (the dot and the word, smaller).
 */
@Composable
fun LiveBeat(modifier: Modifier = Modifier, compact: Boolean = false) {
    val c = Divan.colors
    val b = rememberBeat()
    val live = rememberLive()
    val ink = when (b.beat) {
        Beat.LIVE -> c.positive
        Beat.RECONNECTING, Beat.STALE -> c.warning
        Beat.OFFLINE -> c.textMuted
    }
    val dot = if (compact) 7.dp else 8.dp
    Row(
        modifier.clip(CircleShape).border(1.dp, if (b.beat == Beat.STALE) c.warning.copy(alpha = 0.6f) else c.lineStrong, CircleShape)
            .padding(horizontal = if (compact) 8.dp else 10.dp, vertical = if (compact) 1.dp else 3.dp)
            .semantics(mergeDescendants = true) { liveRegion = LiveRegionMode.Polite; contentDescription = "پخش زنده: " + b.fa },
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        when (b.beat) {
            Beat.LIVE -> Box(Modifier.size(dot).beat(live.applied.takeIf { it > 0 }, LiveRules.BEAT_MS).clip(CircleShape).background(ink))
            Beat.RECONNECTING -> Arc(true, ink, size = dot + 2.dp, word = null)
            Beat.STALE -> Box(Modifier.size(dot).clip(CircleShape).background(ink))
            Beat.OFFLINE -> Box(Modifier.size(dot).clip(CircleShape).border(1.5.dp, ink, CircleShape))
        }
        Text(
            if (b.beat == Beat.STALE) timesFig(b.fa) else buildAnnotatedString { append(b.fa) },
            style = (if (compact) Divan.type.micro else Divan.type.caption).copy(fontWeight = FontWeight.Medium),
            color = if (b.beat == Beat.STALE) c.warning else c.textSecondary, maxLines = 1,
        )
    }
}

/** Rule 7: «۲۵ رویداد در نبودت» when more than twenty events arrived while the app was away (applied at once, not replayed); a tap,
 *  or eight seconds, puts it away. */
@Composable
fun MissedChip(modifier: Modifier = Modifier) {
    val env = LocalEnv.current
    val c = Divan.colors
    val live = rememberLive()
    val n = live.missed
    val show = n > LiveRules.MISSED_CHIP && live.foreground
    LaunchedEffect(show, n) { if (show) { delay(8_000); env.stream.live.clearMissed() } }
    if (!show) return
    Row(
        modifier.clip(CircleShape).border(1.dp, c.lineStrong, CircleShape).background(c.card)
            .clickable(role = Role.Button, onClickLabel = "دیدم") { env.stream.live.clearMissed() }
            .padding(horizontal = 10.dp, vertical = 3.dp)
            .semantics(mergeDescendants = true) { liveRegion = LiveRegionMode.Polite },
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        DIcon(DivanIcon.TIME, size = 12.dp, tint = c.textMuted)
        Text("${faNum(n)} رویداد در نبودت", style = Divan.type.micro, color = c.textSecondary)
    }
}

// ------------------------------------------------------------------ GL-2 --
/** Who changed a switch, in the owner's words: «به دستور تو» for the owner (or when the hub does not say). */
internal fun byFa(by: String?): String = when {
    by.isNullOrBlank() || by == "owner" || by.startsWith("owner") -> "به دستور تو"
    else -> "به دستور $by"
}

/**
 * GL-2: across the top of every screen while a kill switch is on — a 4 dp negative band and one line: «هلدینگ قفل است · از 14:02 · به
 * دستور تو», or the company (or companies) locked. It settles from the top edge on engage and folds away on release; a tap opens the
 * control room. The stillness everywhere then has a reason the owner can see.
 */
@Composable
fun KillBand(modifier: Modifier = Modifier) {
    val c = Divan.colors
    val nav = LocalNav.current
    val live = rememberLive()
    val control = rememberQuery("control", "control") { control() }.data
    val companies = rememberCompanies()
    val holding = if (live.seeded || live.control.holding) live.control.holding else control?.holding?.state == "engaged"
    val locked: List<String> = if (live.seeded) live.control.locked.keys.toList()
    else control?.companies.orEmpty().filter { it.state == "engaged" }.map { it.company }
    val on = holding || locked.isNotEmpty()
    val reduced = LocalReducedMotion.current
    AnimatedVisibility(
        on, modifier,
        enter = if (reduced) androidx.compose.animation.EnterTransition.None
        else androidx.compose.animation.expandVertically(androidx.compose.animation.core.tween(Grammar.SETTLE, easing = Motion.Standard), expandFrom = Alignment.Top) +
            androidx.compose.animation.fadeIn(androidx.compose.animation.core.tween(Grammar.SETTLE, easing = Motion.Standard)),
        exit = collapseOut(),
    ) {
        val text = buildAnnotatedString {
            if (holding) {
                append("هلدینگ قفل است")
                val since = live.control.holdingSince ?: control?.holding?.changedAt
                since?.let { append(" · از "); fig(jTime(it)) }
                append(" · " + byFa(live.control.holdingBy ?: control?.holding?.changedBy))
            } else {
                val names = locked.map { code -> companies.firstOrNull { it.code == code }?.nameFa ?: code }
                if (names.size == 1) {
                    append(names.first() + " قفل است")
                    val sw = control?.companies?.firstOrNull { it.company == locked.first() }
                    val since = live.control.locked[locked.first()] ?: sw?.changedAt
                    since?.let { append(" · از "); fig(jTime(it)) }
                    append(" · " + byFa(sw?.changedBy))
                } else append("${faNum(names.size)} شرکت قفل‌اند: " + names.joinToString("، "))
            }
        }
        Column(
            Modifier.fillMaxWidth().clickable(role = Role.Button, onClickLabel = "اتاق کنترل") { nav.go("control") }
                .semantics(mergeDescendants = true) { liveRegion = LiveRegionMode.Polite },
        ) {
            Box(Modifier.fillMaxWidth().height(4.dp).background(c.negative))
            Row(
                Modifier.fillMaxWidth().background(c.softNegative).padding(horizontal = 16.dp, vertical = 6.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                DIcon(DivanIcon.LOCK, size = 14.dp, tint = c.negative)
                Text(text, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.negative, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
            }
        }
    }
}

// ------------------------------------------------------------------ NO-1 --
/** NO-1 🔴: one urgent alert standing until the owner says «دیدم». */
data class UrgentNow(val title: String, val text: String, val route: String?)

/**
 * NO-1 🔴: the urgent banner. It settles from the top and stays until acknowledged («دیدم»), with one low bell (a haptic when animations
 * are removed); nothing shakes and nothing repeats. Announced assertively.
 */
@Composable
fun UrgentBanner(u: UrgentNow?, onSeen: () -> Unit, onOpen: (String) -> Unit, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val reduced = LocalReducedMotion.current
    AnimatedVisibility(
        u != null, modifier,
        enter = if (reduced) androidx.compose.animation.EnterTransition.None
        else androidx.compose.animation.expandVertically(androidx.compose.animation.core.tween(Grammar.SETTLE, easing = Motion.Standard), expandFrom = Alignment.Top) +
            androidx.compose.animation.fadeIn(androidx.compose.animation.core.tween(Grammar.SETTLE, easing = Motion.Standard)),
        exit = collapseOut(),
    ) {
        val x = u ?: return@AnimatedVisibility
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp).clip(RoundedCornerShape(14.dp)).background(c.softNegative)
                .border(1.dp, c.negative, RoundedCornerShape(14.dp))
                .then(if (x.route != null) Modifier.clickable(role = Role.Button, onClickLabel = "باز کن") { onOpen(x.route) } else Modifier)
                .padding(horizontal = 12.dp, vertical = 8.dp)
                .semantics(mergeDescendants = true) { liveRegion = LiveRegionMode.Assertive; contentDescription = "فوری: ${x.title}. ${x.text}" },
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Box(Modifier.size(10.dp).clip(CircleShape).background(c.negative))
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(1.dp)) {
                Text(timesFig(x.title), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
                if (x.text.isNotBlank()) Text(timesFig(x.text), style = Divan.type.caption, color = c.textSecondary, maxLines = 2, overflow = TextOverflow.Ellipsis)
            }
            com.coinepro.hq.designsystem.HqButton("دیدم", onSeen, variant = com.coinepro.hq.designsystem.BtnVariant.SECONDARY, size = com.coinepro.hq.designsystem.BtnSize.SM)
        }
    }
}

/** NO-1's one low bell: the phone's own notification sound, once (never for traffic, rule 6). */
fun lowBell(ctx: android.content.Context) {
    runCatching {
        val uri = android.media.RingtoneManager.getDefaultUri(android.media.RingtoneManager.TYPE_NOTIFICATION) ?: return
        android.media.RingtoneManager.getRingtone(ctx, uri)?.play()
    }
}

// ------------------------------------------------------------------ PE-1 --
/** A person's state in words (PE-1): shape and word, never colour alone. */
val PERSON_FA = linkedMapOf(
    "thinking" to "فکر میکند",
    "working" to "کار میکند",
    "waiting" to "منتظر",
    "stuck" to "گیر کرده",
    "done" to "تمام کرد",
    "idle" to "بیکار",
)

fun personFa(state: String): String = PERSON_FA[state] ?: PERSON_FA.getValue("idle")

/**
 * PE-1: a person's state by shape. Thinking: a silver dot that breathes (a model call in flight, M6); working: a silver ring turning slowly
 * (a tool or a server job, M7); waiting: a hollow lapis ring; stuck: a negative disc with «!»; done: a positive tick; idle: nothing
 * ([idleDot] draws a faint dot instead). Still glyphs when animations are removed.
 */
@Composable
fun PersonGlyph(state: String, modifier: Modifier = Modifier, size: Dp = 12.dp, idleDot: Boolean = false) {
    val c = Divan.colors
    val reduced = LocalReducedMotion.current || !rememberAppVisible()
    val label = personFa(state)
    val m = modifier.size(size).semantics { contentDescription = label }
    when (state) {
        "thinking" -> Box(m, contentAlignment = Alignment.Center) { Box(Modifier.size(size * 0.55f).breath(!reduced).clip(CircleShape).background(c.silverInk)) }
        "working" -> {
            val turn = if (reduced) null else androidx.compose.animation.core.rememberInfiniteTransition(label = "pe1")
                .animateFloat(0f, 360f, androidx.compose.animation.core.infiniteRepeatable(androidx.compose.animation.core.tween(2 * Grammar.ARC, easing = androidx.compose.animation.core.LinearEasing)), label = "pe1")
            Canvas(m) {
                val st = 1.6.dp.toPx()
                val r = this.size.minDimension / 2 - st
                drawCircle(c.silverInk, r * 0.3f)
                val a = turn?.value ?: 0f
                for (k in 0 until 2) drawArc(
                    c.silverInk, a + k * 180f, 120f, false, topLeft = Offset(center.x - r, center.y - r),
                    size = androidx.compose.ui.geometry.Size(2 * r, 2 * r), style = Stroke(st, cap = StrokeCap.Round),
                )
            }
        }
        "waiting" -> Canvas(m) { drawCircle(c.lapis, this.size.minDimension / 2 - 1.6.dp.toPx(), style = Stroke(1.6.dp.toPx())) }
        "stuck" -> Canvas(m) {
            val r = this.size.minDimension / 2
            drawCircle(c.negative, r)
            val w = 1.6.dp.toPx()
            drawLine(c.card, Offset(center.x, center.y - r * 0.5f), Offset(center.x, center.y + r * 0.12f), strokeWidth = w, cap = StrokeCap.Round)
            drawCircle(c.card, w * 0.6f, Offset(center.x, center.y + r * 0.45f))
        }
        "done" -> Canvas(m) {
            val w = this.size.width
            drawPath(Path().apply { moveTo(w * 0.16f, w * 0.55f); lineTo(w * 0.42f, w * 0.8f); lineTo(w * 0.86f, w * 0.24f) }, c.positive, style = Stroke(1.8.dp.toPx(), cap = StrokeCap.Round))
        }
        else -> if (idleDot) Box(m, contentAlignment = Alignment.Center) { Box(Modifier.size(size * 0.35f).clip(CircleShape).background(c.textMuted.copy(alpha = 0.6f))) }
    }
}

/** The legend of PE-1's shapes, each with its word (the colour-blind owner reads the word). */
@Composable
fun PersonLegend(modifier: Modifier = Modifier) {
    val c = Divan.colors
    androidx.compose.foundation.layout.FlowRow(modifier, horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        for ((s, fa) in PERSON_FA) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            PersonGlyph(s, size = 11.dp, idleDot = true)
            Text(fa, style = Divan.type.micro, color = c.textSecondary)
        }
    }
}

/** A tiny state dot for a company's people row: the glyph, or «+n» past [max]. */
@Composable
fun PeopleDots(states: List<String>, modifier: Modifier = Modifier, max: Int = 12) {
    val c = Divan.colors
    Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(2.dp)) {
        for (s in states.take(max)) PersonGlyph(s, size = 12.dp)
        if (states.size > max) Text("+" + faNum(states.size - max), style = Divan.type.micro, color = c.textMuted)
    }
}

/** A server's state by shape (HM-1, CO-1): online a solid positive outline; offline negative with ×; pending dashed warning; revoked muted. */
@Composable
fun ServerGlyph(state: String, modifier: Modifier = Modifier, size: Dp = 10.dp) {
    val c = Divan.colors
    Canvas(modifier.size(size).semantics { contentDescription = serverStateFa(state) }) {
        val st = 1.5.dp.toPx()
        val r = androidx.compose.ui.geometry.CornerRadius(2.5.dp.toPx())
        val tl = Offset(st / 2, st / 2)
        val sz = androidx.compose.ui.geometry.Size(this.size.width - st, this.size.height - st)
        when (state) {
            "offline" -> {
                drawRoundRect(c.softNegative, tl, sz, r)
                drawRoundRect(c.negative, tl, sz, r, style = Stroke(st))
                val k = this.size.width * 0.3f
                drawLine(c.negative, Offset(k, k), Offset(this.size.width - k, this.size.height - k), st, StrokeCap.Round)
                drawLine(c.negative, Offset(this.size.width - k, k), Offset(k, this.size.height - k), st, StrokeCap.Round)
            }
            "pending" -> drawRoundRect(c.warning, tl, sz, r, style = Stroke(st, pathEffect = androidx.compose.ui.graphics.PathEffect.dashPathEffect(floatArrayOf(2.5.dp.toPx(), 2.dp.toPx()))))
            "revoked" -> drawRoundRect(c.textMuted, tl, sz, r, style = Stroke(st))
            else -> drawRoundRect(c.positive, tl, sz, r, style = Stroke(st))
        }
    }
}

fun serverStateFa(state: String): String = when (state) {
    "online" -> "وصل"
    "offline" -> "قطع"
    "pending" -> "در انتظار جفت شدن"
    "revoked" -> "باطل"
    else -> "نامعلوم"
}
