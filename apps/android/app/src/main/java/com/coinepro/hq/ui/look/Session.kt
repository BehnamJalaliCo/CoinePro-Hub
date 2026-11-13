package com.coinepro.hq.ui.look

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.data.HELD_FA
import com.coinepro.hq.core.data.HELD_HINT_FA
import com.coinepro.hq.core.data.MOOD_FA
import com.coinepro.hq.core.data.STILL_FA
import com.coinepro.hq.core.data.Still
import com.coinepro.hq.core.data.callModel
import com.coinepro.hq.core.data.holdable
import com.coinepro.hq.core.data.isCall
import com.coinepro.hq.core.data.isTurn
import com.coinepro.hq.core.data.leadKnot
import com.coinepro.hq.core.data.leadWorker
import com.coinepro.hq.core.data.nowFacts
import com.coinepro.hq.core.data.quietLine
import com.coinepro.hq.core.data.segmentsFa
import com.coinepro.hq.core.data.sentenceOf
import com.coinepro.hq.core.data.stillLastFa
import com.coinepro.hq.core.data.stillSentenceFa
import com.coinepro.hq.core.data.timerFig
import com.coinepro.hq.core.data.turnTime
import com.coinepro.hq.core.data.waitedFa
import com.coinepro.hq.core.data.workerKindFa
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.format.tokens
import com.coinepro.hq.core.net.ActivityLine
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.Blocker
import com.coinepro.hq.core.net.OrderCard
import com.coinepro.hq.core.net.SessionActivity
import com.coinepro.hq.core.net.SessionWorker
import com.coinepro.hq.designsystem.Arc
import com.coinepro.hq.designsystem.Avatar
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.DrawnMark
import com.coinepro.hq.designsystem.Expand
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.ModelMark
import com.coinepro.hq.designsystem.Ring
import com.coinepro.hq.designsystem.RingTone
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.WorkBand
import com.coinepro.hq.designsystem.facts
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.rememberHaptics
import com.coinepro.hq.designsystem.ringColor
import com.coinepro.hq.designsystem.settle
import com.coinepro.hq.designsystem.silverLine
import com.coinepro.hq.designsystem.smoothSize
import com.coinepro.hq.designsystem.timesFig
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.v29.FixButton
import com.coinepro.hq.ui.v29.plain
import kotlinx.coroutines.launch

// ⟨1.0.1⟩ Part C, the session redesigned (C2.2; features 13, 14, 15, 28 and 75), the pieces the session's page is built from:
// - [MoodLight]: «چراغ حال», a small shape and one word, never colour alone («فکر میکند», «کار میکند», «منتظر تو», «گیر کرده», «آرام»,
//   «تمام»);
// - [SegmentLine]: the plan under the header: what is done is silver, what waits for the owner is gold, the rest is empty;
// - [NowBar]: «الان», above the composer while something works: who, for which company, the whole sentence of what it does, the time,
//   and «نگه دار» always at the same edge (one tap stops the live work; it then reads «ادامه بده»). A workshop turn or the holder's
//   own direct turn shows [BuildRing]: real elapsed time out of the turn's cap, amber from 90 percent;
// - [WaitingCard]: the ONE place of the holder's question, with its ready answers (one tap answers); [AnswerSent] for a moment after;
// - [KnotCard]: one sentence of why the session stands still, and one action;
// - [StillCard]: ⟨2026-11-11⟩ an open session nobody works on and the hub has not explained: «ایستاده», one sentence, «ادامه بده»;
// - [SessionCards]: the cards of the session that wait for his word, answered in place;
// - [LiveTail], [LiveSheetBody]: the live steps as thin lines; [EndLeaf]: the end of a closed session; [IdleNudge] for its details.
// One full gold per page: none of these is gold but the knot's action, or the still card's, when the page has no decision bar (`lead`).

// ====================================================================================================== the mood ==
/** «چراغ حال»: a shape and a word. The arc of «کار میکند» turns only while this is shown, which is only while work is live. */
@Composable
fun MoodLight(mood: String, modifier: Modifier = Modifier, word: String? = null, size: Dp = 14.dp) {
    val c = Divan.colors
    val ink = when (mood) { "waiting" -> c.goldInk; "stuck" -> c.negative; "thinking", "working" -> c.silverInk; else -> c.textMuted }
    val said = word ?: MOOD_FA[mood] ?: MOOD_FA.getValue("idle")
    Row(
        modifier.testTag("mood-light").semantics(mergeDescendants = true) { contentDescription = said },
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Box(Modifier.size(size), contentAlignment = Alignment.Center) {
            when (mood) {
                "working" -> {
                    val track = c.lineStrong
                    Canvas(Modifier.size(size)) { drawCircle(track, this.size.minDimension / 2 - 1.dp.toPx(), style = Stroke(1.6.dp.toPx())) }
                    Arc(true, ink, size = size, word = null)
                }
                "done" -> DrawnMark(true, ink, size = size * 0.8f)
                else -> Canvas(Modifier.size(size)) {
                    val r = this.size.minDimension / 2
                    when (mood) {
                        "thinking" -> drawCircle(ink, r - 1.dp.toPx(), style = Stroke(1.6.dp.toPx()))
                        // «ایستاده»: a grey hollow ring, nothing turning in it
                        "still" -> drawCircle(ink, r - 1.dp.toPx(), style = Stroke(1.6.dp.toPx()))
                        "waiting" -> drawCircle(ink, r * 0.52f)
                        "stuck" -> drawCircle(ink, r - 1.dp.toPx(), style = Stroke(1.8.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(r * 0.75f, r * 0.38f))))
                        else -> drawCircle(ink.copy(alpha = 0.7f), r * 0.43f)
                    }
                }
            }
        }
        Text(said, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = ink, maxLines = 1)
    }
}

// ============================================================================================ the plan, in a line ==
/** The plan as a line of parts ([parts]: `done`, `waiting`, `todo` from `segmentsOf`): done is silver, the owner's is gold, the rest empty. */
@Composable
fun SegmentLine(parts: List<String>, modifier: Modifier = Modifier) {
    if (parts.isEmpty()) return
    val c = Divan.colors
    Row(
        modifier.fillMaxWidth().testTag("segment-line").semantics { contentDescription = segmentsFa(parts) },
        horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        for (p in parts) Box(
            Modifier.weight(1f).height(3.dp).clip(CircleShape).background(when (p) { "done" -> c.silverInk; "waiting" -> c.goldInk; else -> c.lineStrong.copy(alpha = 0.4f) }),
        )
    }
}

// ================================================================================================ the «الان» bar ==
/** The build ring of a workshop or direct turn: real elapsed time out of its cap, the minute in its middle; amber from 90 percent. */
@Composable
fun BuildRing(w: SessionWorker, now: Long, modifier: Modifier = Modifier, size: Dp = 76.dp) {
    val c = Divan.colors
    val t = turnTime(w, now)
    val late = ringColor(RingTone.NEAR)
    Ring(
        t.share, modifier.testTag("build-ring"), size = size, stroke = 5.dp, tone = if (t.late) RingTone.NEAR else RingTone.SILVER,
        label = "${t.min} دقیقه از ${t.capMin} دقیقه گذشته" + if (t.late) "؛ نزدیک سقف زمان" else "",
    ) {
        Text(t.min.toString(), style = Divan.type.h2.copy(fontSize = (size.value * 0.27f).sp, lineHeight = (size.value * 0.32f).sp, fontWeight = FontWeight.Bold), color = if (t.late) late else c.textPrimary, maxLines = 1)
        Text("از ${t.capMin} دقیقه", style = Divan.type.micro.copy(fontSize = (size.value * 0.125f).coerceAtLeast(8f).sp, lineHeight = (size.value * 0.17f).sp), color = c.textMuted, maxLines = 1)
    }
}

/** One worker's mark: the holder's own turn wears the manager's ring, an outside call its model's logo on a tile, the rest a colleague. */
@Composable
private fun WorkerMark(w: SessionWorker, size: Dp) {
    val c = Divan.colors
    if (isCall(w)) Box(
        Modifier.size(size).clip(CircleShape).background(c.tile).border(1.dp, c.lineDivider, CircleShape).testTag("call-mark")
            .semantics { contentDescription = w.whoFa },
        contentAlignment = Alignment.Center,
    ) { ModelMark(callModel(w), size = size * 0.52f) }
    else Avatar(if (w.kind == "direct") "manager" else "employee", size = size, state = "working", label = w.whoFa)
}

/** The marks of those at work, side by side (at most three). */
@Composable
private fun WorkerMarks(working: List<SessionWorker>) {
    val c = Divan.colors
    Row(verticalAlignment = Alignment.CenterVertically) {
        working.take(3).forEachIndexed { i, w ->
            Box(Modifier.offset(x = if (i == 0) 0.dp else (-10 * i).dp).clip(CircleShape).background(c.card).padding(1.dp)) { WorkerMark(w, 32.dp) }
        }
    }
}

/**
 * «الان»: above the composer while something works. A tap on it opens the live-work sheet; «نگه دار» stops the live work, and the same
 * place then reads «ادامه بده». [held]: the owner stopped it and nobody works now. [canHold]: the report names the work to stop and
 * the hub takes the stop.
 */
@Composable
fun NowBar(
    working: List<SessionWorker>, held: Boolean, now: Long, onOpen: () -> Unit, modifier: Modifier = Modifier,
    canHold: Boolean = true, holding: Boolean = false, onHold: () -> Unit = {}, resuming: Boolean = false, onResume: () -> Unit = {},
) {
    val c = Divan.colors
    val live = working.isNotEmpty()
    if (!live && !held) return
    val w = leadWorker(working)
    val stopped = held && !live
    Column(modifier.fillMaxWidth().testTag("now-bar").settle().clip(RoundedCornerShape(14.dp)).background(c.card)) {
        Row(Modifier.padding(start = 12.dp, end = 10.dp, top = 10.dp, bottom = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(
                Modifier.weight(1f).clip(RoundedCornerShape(10.dp)).clickable(role = Role.Button, onClickLabel = "کار زنده را باز کن", onClick = onOpen),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                when {
                    stopped || w == null -> Box(Modifier.size(32.dp).clip(CircleShape).background(c.tile), contentAlignment = Alignment.Center) {
                        Box(Modifier.size(10.dp).clip(RoundedCornerShape(2.dp)).background(c.textMuted))
                    }
                    isTurn(w) -> BuildRing(w, now)
                    else -> WorkerMarks(working)
                }
                Column(Modifier.weight(1f).semantics { liveRegion = LiveRegionMode.Polite }, verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    if (stopped || w == null) {
                        Text(HELD_FA, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                        Text(HELD_HINT_FA, style = Divan.type.caption, color = c.textSecondary)
                    } else {
                        Text(remember(w, working.size) { facts(*nowFacts(w, working.size).toTypedArray()) }, style = Divan.type.micro, color = c.textMuted, maxLines = 2)
                        // The whole sentence: it wraps, it is never cut.
                        Text(plain(quietLine(sentenceOf(w))), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                        if (isTurn(w) && turnTime(w, now).late) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            com.coinepro.hq.designsystem.DIcon(DivanIcon.TIME, size = 12.dp, tint = ringColor(RingTone.NEAR))
                            Text("نزدیک سقف زمان", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = ringColor(RingTone.NEAR))
                        }
                    }
                }
                if (!stopped && w != null && !isTurn(w)) Fig(timerFig(working.minOf { it.startedAt.ifBlank { w.startedAt } }, now), style = Divan.type.figureSmall, color = c.textSecondary)
            }
            when {
                stopped -> HqButton("ادامه بده", onResume, variant = BtnVariant.SECONDARY, size = BtnSize.LG, loading = resuming)
                // an outside call that is all that works is not the hub's to stop
                canHold && holdable(working) -> HqButton("نگه دار", onHold, variant = BtnVariant.DANGER, size = BtnSize.LG, loading = holding, label = "کار زنده را نگه دار")
            }
        }
        // The silver work line moves only while the work is live.
        WorkBand(live && !stopped, c.silverInk, Modifier.fillMaxWidth(), height = 4.dp, word = null)
    }
}

// ============================================================================================ the «منتظر تو» card ==
/** A card of the owner's above the composer: the card surface with a thin line at its start edge (gold: it waits for him). */
@Composable
private fun EdgeCard(tag: String, modifier: Modifier = Modifier, edge: androidx.compose.ui.graphics.Color = Divan.colors.goldInk, content: @Composable () -> Unit) {
    val c = Divan.colors
    Box(modifier.fillMaxWidth().testTag(tag).settle().clip(RoundedCornerShape(14.dp)).background(c.card).goldEdge(edge).padding(start = 14.dp, end = 12.dp, top = 12.dp, bottom = 10.dp)) { content() }
}

/**
 * The holder's open question, in ONE place, right above the composer: who asks, how long it has waited and which task stands still;
 * the question; its ready answers as buttons (from the question itself when it names two or three options with «یا»), always a last
 * quiet «خودت تصمیم بگیر و ادامه بده». One tap sends that answer through the session's own reply; typing still works.
 *
 * ⟨1.36⟩ §58.1 it never hides what he writes: at most three lines of the question, «بیشتر» opens it in place (at most 40% of the
 * screen, scrolling inside itself); while he writes ([folded]: the composer has the keyboard or words) it is one line, a tap opens it
 * again. [latest]: the chip of the session's newest output («خروجی آخر: …»), [onLatest] opens it over the session.
 */
@Composable
fun WaitingCard(
    whoFa: String, questionFa: String, askedAt: String?, standingFa: String?, answers: List<String>, busy: String?, onAnswer: (String) -> Unit,
    modifier: Modifier = Modifier, folded: Boolean = false, latest: String? = null, onLatest: (() -> Unit)? = null, open0: Boolean = false,
) {
    val c = Divan.colors
    var open by rememberSaveable(questionFa) { mutableStateOf(open0) }
    // he started to write: the card steps back to its first line (it opens again with a tap)
    androidx.compose.runtime.LaunchedEffect(folded) { if (folded) open = false }
    var long by remember(questionFa) { mutableStateOf(false) }
    val style = Divan.type.small.copy(fontSize = 14.5.sp, lineHeight = 26.sp, fontWeight = FontWeight.SemiBold)
    val chip: (@Composable () -> Unit)? = if (latest != null && onLatest != null) ({ LatestChip(latest, onLatest) }) else null
    EdgeCard("waiting-card", modifier.smoothSize()) {
        if (folded && !open) {
            Row(
                Modifier.fillMaxWidth().testTag("waiting-folded").clickable(role = Role.Button, onClickLabel = "دیدن همه‌ی سؤال") { open = true },
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(
                    remember(whoFa, questionFa) { facts("$whoFa میپرسد", com.coinepro.hq.core.data.questionFirstLine(questionFa)) },
                    style = Divan.type.caption, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f),
                )
                chip?.invoke()
            }
            return@EdgeCard
        }
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(remember(whoFa, askedAt, standingFa) { facts("$whoFa میپرسد", waitedFa(askedAt), standingFa) }, style = Divan.type.micro, color = c.textMuted, maxLines = 2)
            if (open) {
                val most = (androidx.compose.ui.platform.LocalConfiguration.current.screenHeightDp * com.coinepro.hq.core.data.QUESTION_MAX_SHARE).dp
                Box(Modifier.fillMaxWidth().heightIn(max = most).testTag("waiting-open").verticalScroll(rememberScrollState())) {
                    Text(plain(questionFa), style = style, color = c.textPrimary)
                }
            } else Text(
                plain(questionFa), style = style, color = c.textPrimary, maxLines = com.coinepro.hq.core.data.QUESTION_LINES, overflow = TextOverflow.Ellipsis,
                onTextLayout = { r -> if (r.hasVisualOverflow) long = true },
            )
            if (long || open || chip != null) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (long || open) Text(
                    if (open) "کمتر" else "بیشتر",
                    Modifier.testTag("question-more").clip(RoundedCornerShape(8.dp)).clickable(role = Role.Button) { open = !open }.padding(vertical = 4.dp, horizontal = 2.dp),
                    style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.silverInk,
                )
                Spacer(Modifier.weight(1f))
                chip?.invoke()
            }
            ReadyAnswers(answers, busy, onAnswer)
        }
    }
}

/** «خروجی آخر: …»: the session's newest output, one tap from the question (it opens over the session; the draft stays). */
@Composable
private fun LatestChip(label: String, onClick: () -> Unit) {
    val c = Divan.colors
    Row(
        Modifier.widthIn(max = 220.dp).height(30.dp).testTag("latest-output").clip(RoundedCornerShape(50)).border(1.dp, c.lineStrong, RoundedCornerShape(50))
            .clickable(role = Role.Button, onClickLabel = "باز کردن خروجی آخر", onClick = onClick).padding(horizontal = 10.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp),
    ) {
        com.coinepro.hq.designsystem.DIcon(DivanIcon.DELIVERABLE, size = 13.dp, tint = c.textSecondary)
        Text(timesFig(label), style = Divan.type.micro, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

/** «جوابت رفت: …»: said for a moment where the question was, once the hub has taken the answer. */
@Composable
fun AnswerSent(text: String, modifier: Modifier = Modifier) {
    val c = Divan.colors
    EdgeCard("answer-sent", modifier) {
        Row(Modifier.semantics { liveRegion = LiveRegionMode.Polite }, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            DrawnMark(true, c.positive, size = 16.dp)
            Text("جوابت رفت: $text", style = Divan.type.small, color = c.textSecondary)
        }
    }
}

// =================================================================================================== the «گره» card ==
/**
 * A session that stands still: ONE card, one whole sentence of why ([why]), and one action: the fix the hub offers (its own words),
 * else «ادامه بده». Further knots fold under the first, each with its own quiet fix. [lead]: this card carries the page's full gold.
 */
@Composable
fun KnotCard(
    why: String, blockers: List<Blocker>, company: String?, orderRef: String?, budgetTokens: Long?, lead: Boolean,
    canNudge: Boolean, nudging: Boolean, onNudge: () -> Unit, modifier: Modifier = Modifier, open0: Boolean = false, onFixed: () -> Unit = {},
) {
    val c = Divan.colors
    val first = leadKnot(blockers)
    val rest = blockers.filter { it !== first }
    var open by rememberSaveable(orderRef) { mutableStateOf(open0) }
    fun budgetOf(b: Blocker): Long? = if (b.fix?.action == "budget.add") maxOf(100_000L, (budgetTokens ?: 0L) / 4) else null
    EdgeCard("knot", modifier.smoothSize(), edge = c.negative) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(Modifier.semantics { liveRegion = LiveRegionMode.Assertive }, verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                MoodLight("stuck", Modifier.padding(top = 3.dp), word = "گره")
                Text(plain(quietLine(why)), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, modifier = Modifier.weight(1f))
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                val fix = first?.fix
                if (fix != null) FixButton(fix, company, orderRef, budgetTokens = budgetOf(first), variant = if (lead) BtnVariant.PRIMARY else BtnVariant.SECONDARY, onDone = onFixed)
                else if (canNudge) HqButton("ادامه بده", onNudge, variant = if (lead) BtnVariant.PRIMARY else BtnVariant.SECONDARY, size = BtnSize.SM, loading = nudging)
                if (rest.isNotEmpty()) HqButton(if (open) "کمتر" else "و ${rest.size} گره‌ی دیگر", { open = !open }, variant = BtnVariant.TEXT, size = BtnSize.SM)
            }
            Expand(open && rest.isNotEmpty()) {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    HorizontalDivider(color = c.lineDivider)
                    for (b in rest) Row(Modifier.testTag("knot-more"), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Column(Modifier.weight(1f)) {
                            Text(plain(quietLine(b.titleFa)), style = Divan.type.small, color = c.textPrimary)
                            quietLine(b.detailFa).ifBlank { null }?.let { Text(plain(it), style = Divan.type.micro, color = c.textMuted) }
                        }
                        b.fix?.let { FixButton(it, company, orderRef, budgetTokens = budgetOf(b), variant = BtnVariant.SECONDARY, onDone = onFixed) }
                    }
                }
            }
        }
    }
}

// ========================================================================== the session's cards that wait for his word ==
/**
 * The cards of this session that wait for a decision, answered where he sees them: one that takes a tap is approved here with one
 * tap; one the hub seals with the passkey (money, a permanent delete, keys and access, a destructive server command) opens that card.
 */
@Composable
fun SessionCards(cards: List<OrderCard>, modifier: Modifier = Modifier, onDecided: () -> Unit = {}) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val haptics = rememberHaptics()
    val scope = rememberCoroutineScope()
    val c = Divan.colors
    var done by remember { mutableStateOf(emptySet<String>()) }
    var busy by remember { mutableStateOf<String?>(null) }
    val list = cards.filter { it.ref !in done }
    if (list.isEmpty()) return
    EdgeCard("waiting-cards", modifier) {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            list.forEachIndexed { i, card ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(plain(quietLine(card.titleFa)), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                        val sub = remember(card) { facts(card.byFa?.let(::quietLine)?.ifBlank { null }, quietLine(card.waitsFa).ifBlank { null }) }
                        if (sub.isNotEmpty()) Text(sub, style = Divan.type.micro, color = c.textMuted)
                    }
                    if (card.seal == "tap") HqButton("تأیید", {
                        if (busy != null) return@HqButton
                        busy = card.ref
                        scope.launch {
                            try {
                                env.api.approve(card.ref, null, null)
                                haptics.seal()
                                done = done + card.ref
                                toasts.ok("تأیید شد.")
                                env.cache.invalidate("decisions", "inbox", "office", "order-report")
                                onDecided()
                            } catch (e: ApiException) { haptics.error(); toasts.error(e.messageFa) } finally { busy = null }
                        }
                    }, variant = BtnVariant.SECONDARY, size = BtnSize.SM, loading = busy == card.ref)
                    else HqButton("ببین و تأیید کن", { nav.go("cartable/${card.ref}") }, variant = BtnVariant.SECONDARY, size = BtnSize.SM)
                }
            }
        }
    }
}

// ============================================================================================= the live steps ==
/** One step of live work: its real clock time, who and for which company, what; a running one turns, a finished one is ticked. */
@Composable
fun LiveLine(l: ActivityLine, companyFa: String?, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val who = l.whoFa.trim()
    val text = quietLine(l.textFa)
    Row(modifier.fillMaxWidth().testTag("live-line"), verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Box(Modifier.width(38.dp).padding(top = 1.dp)) { if (l.at.isNotBlank()) Fig(jTime(l.at), style = Divan.type.figureSmall.copy(fontSize = 11.sp), color = c.textMuted) }
        Text(
            buildAnnotatedString {
                if (who.isNotEmpty() && !text.startsWith(who)) withStyle(SpanStyle(color = c.silverInk)) {
                    append(who)
                    if (!companyFa.isNullOrBlank() && companyFa !in who) append("، $companyFa")
                    append(": ")
                }
                append(plain(text))
            },
            style = Divan.type.caption, color = if (l.state == "failed") c.negative else c.textSecondary, modifier = Modifier.weight(1f),
        )
        Box(Modifier.padding(top = 3.dp).size(13.dp), contentAlignment = Alignment.Center) {
            when (l.state) {
                "running" -> Arc(true, c.silverInk, size = 13.dp, word = null)
                "done" -> DrawnMark(true, c.positive, size = 12.dp)
                "failed" -> DrawnMark(false, c.negative, size = 12.dp)
                else -> Unit
            }
        }
    }
}

/** The newest steps of the work that is live, as thin lines at the end of the thread. Nothing while nothing works. */
@Composable
fun LiveTail(a: SessionActivity?, companyName: (String?) -> String?, modifier: Modifier = Modifier, shown: Int = 3) {
    val lines = if (a != null && a.working.isNotEmpty()) a.last.takeLast(shown) else emptyList()
    if (lines.isEmpty()) return
    Column(modifier.fillMaxWidth().testTag("live-tail"), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        for (l in lines) LiveLine(l, companyName(l.company))
    }
}

/** The live-work sheet: who works on what, each with its own line and time, then every step so far. */
@Composable
fun LiveSheetBody(a: SessionActivity, now: Long, companyName: (String?) -> String? = { null }) {
    val c = Divan.colors
    if (a.working.isEmpty()) Text("الان کسی روی این جلسه کار نمیکند.", style = Divan.type.small, color = c.textMuted)
    else Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        for (w in a.working) Row(
            Modifier.fillMaxWidth().testTag("live-worker").clip(RoundedCornerShape(12.dp)).background(c.card).padding(12.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (isTurn(w)) BuildRing(w, now, size = 64.dp) else WorkerMark(w, 36.dp)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(
                    remember(w) { facts(w.whoFa.trim().ifBlank { "یک همکار" }, w.companyFa?.trim()?.ifBlank { null }?.takeIf { it !in w.whoFa }, workerKindFa(w)) },
                    style = Divan.type.micro, color = c.textMuted,
                )
                Text(plain(quietLine(sentenceOf(w))), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                if (w.workTitleFa.isNotBlank() && w.workTitleFa != sentenceOf(w)) Text(plain(quietLine(w.workTitleFa)), style = Divan.type.micro, color = c.textMuted)
            }
            Fig(timerFig(w.startedAt, now), style = Divan.type.figureSmall, color = c.textSecondary)
        }
    }
    if (a.last.isEmpty()) Text("هنوز قدمی ثبت نشده.", style = Divan.type.small, color = c.textMuted)
    else Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("قدم‌ها", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
        for (l in a.last) LiveLine(l, companyName(l.company))
    }
}

/**
 * A quiet session, in its details and the live sheet: when it last worked, and one tap that tells its holder to take the work up again
 * (the hub's nudge). Nothing while someone works. [button] false: the page's still card already carries «ادامه بده»; the line stays.
 */
@Composable
fun IdleNudge(a: SessionActivity?, nudging: Boolean, onNudge: () -> Unit, modifier: Modifier = Modifier, button: Boolean = true) {
    if (a == null || a.working.isNotEmpty()) return
    val c = Divan.colors
    Row(modifier.fillMaxWidth().testTag("idle-nudge"), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(a.idleSince?.let { "آخرین کار ${ago(it)}" } ?: "$STILL_FA.", style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.weight(1f))
        if (button) HqButton("ادامه بده", onNudge, variant = BtnVariant.SECONDARY, size = BtnSize.SM, loading = nudging)
    }
}

// ================================================================================================= «ایستاده» ==
/**
 * An open session nobody works on, and the hub has not said why ([com.coinepro.hq.core.data.stillOf]): ONE calm card right above the
 * composer, the shape of the knot's with a silver edge: «ایستاده», one sentence (the hub's reason, else «الان کسی روی این جلسه کار
 * نمیکند؛ آخرین کار: … (دیشب 22:28)»), and «ادامه بده», the page's one full gold when nothing else holds it ([lead]). [canNudge] false:
 * a hub that does not take the nudge; the card only says it.
 */
@Composable
fun StillCard(still: Still, now: Long, canNudge: Boolean, nudging: Boolean, onNudge: () -> Unit, modifier: Modifier = Modifier, lead: Boolean = true) {
    val c = Divan.colors
    val sentence = remember(still, now / 60_000) { stillSentenceFa(still, now) }
    // with the hub's own reason as its sentence, the last work is a quiet line under it
    val last = remember(still, now / 60_000) { if (still.reasonFa != null) stillLastFa(still, now) else null }
    EdgeCard("still-card", modifier.smoothSize(), edge = silverLine()) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(Modifier.semantics { liveRegion = LiveRegionMode.Polite }, verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                MoodLight("still", Modifier.padding(top = 3.dp))
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(plain(sentence), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                    last?.let { Text(plain(it), style = Divan.type.micro, color = c.textMuted) }
                }
            }
            if (canNudge) HqButton("ادامه بده", onNudge, variant = if (lead) BtnVariant.PRIMARY else BtnVariant.SECONDARY, size = BtnSize.SM, loading = nudging)
        }
    }
}

// =================================================================================================== the end leaf ==
@Composable
private fun LeafFigure(label: String, modifier: Modifier = Modifier, value: @Composable () -> Unit) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(label, style = Divan.type.micro, color = Divan.colors.textMuted)
        value()
    }
}

/**
 * The end of a closed session: what was made (its files, as [made]), how long it took ([tookFa]), how many tokens ([used]; null
 * while they are not known); never half an empty screen. [onReopen] null: the hub has no way back.
 */
@Composable
fun EndLeaf(
    cancelled: Boolean, outputs: Int, tookFa: String?, used: Long?, onReopen: (() -> Unit)?, modifier: Modifier = Modifier, reopening: Boolean = false,
    made: (@Composable () -> Unit)? = null,
    /** ⟨1.36⟩ §58.2 the session left its working group in the library ([keptFa]: the hub's line for it; [onKept] opens it). */
    kept: Boolean = false, onKept: (() -> Unit)? = null, keptFa: String? = null,
) {
    val c = Divan.colors
    val shape = RoundedCornerShape(16.dp)
    val figure = Divan.type.small.copy(fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
    Column(
        modifier.fillMaxWidth().testTag("end-leaf").settle().clip(shape).background(c.tile).border(1.dp, c.lineDivider, shape).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            MoodLight("done")
            Text(if (cancelled) "این فرمان لغو و بایگانی شد." else "این جلسه تأیید و بایگانی شد.", style = Divan.type.small, color = c.textSecondary, modifier = Modifier.weight(1f))
            if (onReopen != null) HqButton("دوباره باز کن", onReopen, variant = BtnVariant.SECONDARY, size = BtnSize.SM, icon = DivanIcon.REFRESH, loading = reopening)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            LeafFigure("ساخته شد", Modifier.weight(0.9f)) { Text(if (outputs > 0) "$outputs خروجی" else "—", style = figure, color = c.textPrimary) }
            LeafFigure("طول کشید", Modifier.weight(1.6f)) { Text(tookFa ?: "—", style = figure, color = c.textPrimary) }
            LeafFigure("مصرف", Modifier.weight(1f)) {
                Text(if (used != null && used > 0) buildAnnotatedString { fig(tokens(used)); append(" واحد") } else buildAnnotatedString { append("—") }, style = figure, color = c.textPrimary)
            }
        }
        made?.invoke()
        if (kept) KeptLine(onKept, text = keptFa)
    }
}

/** «کارگروه این جلسه در کتابخانه ماند»: one line; a tap opens the library, where «برای شرکت تازه» gives it to another company. */
@Composable
fun KeptLine(onOpen: (() -> Unit)?, modifier: Modifier = Modifier, text: String? = null) {
    val c = Divan.colors
    Row(
        modifier.testTag("playbook-kept").clip(RoundedCornerShape(8.dp))
            .then(if (onOpen != null) Modifier.clickable(role = Role.Button, onClickLabel = "کتابخانه‌ی کارگروه‌ها", onClick = onOpen) else Modifier)
            .padding(vertical = 2.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        com.coinepro.hq.designsystem.DIcon(DivanIcon.DEPARTMENT, size = 14.dp, tint = c.silverInk)
        Text(text?.trim()?.ifBlank { null } ?: com.coinepro.hq.core.data.PLAYBOOK_KEPT_FA, style = Divan.type.caption, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}
