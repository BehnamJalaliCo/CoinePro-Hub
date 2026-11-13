package com.coinepro.hq.ui.session

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.TEAM_FA
import com.coinepro.hq.core.data.faNum
import com.coinepro.hq.core.data.hireAskFa
import com.coinepro.hq.core.data.mergeSideLines
import com.coinepro.hq.core.data.narratorChipFa
import com.coinepro.hq.core.data.seatChipFa
import com.coinepro.hq.core.data.sideTitleFa
import com.coinepro.hq.core.data.sideTurn
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.Page
import com.coinepro.hq.core.net.SessionSeat
import com.coinepro.hq.core.net.SessionTeam
import com.coinepro.hq.core.net.SideLine
import com.coinepro.hq.core.net.TeamNarrator
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.DecisionBar
import com.coinepro.hq.designsystem.DecisionState
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.IconBtn
import com.coinepro.hq.designsystem.LiveDot
import com.coinepro.hq.designsystem.Ring
import com.coinepro.hq.designsystem.RingTone
import com.coinepro.hq.designsystem.ScrollRow
import com.coinepro.hq.designsystem.SheetBar
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.SpringSheetFrame
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.facts
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.rememberHaptics
import com.coinepro.hq.designsystem.silverLine
import com.coinepro.hq.designsystem.timesFig
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.media.Composer
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v32.TalkBubble
import java.util.UUID
import kotlinx.coroutines.delay

// Contract §57 ⟨1.35⟩ «تیم این جلسه» (1.0.3). The owner, 2026-11-13: «مستقیم بزنم روی کارمند باهاش توی یه فضای کوچیک حرف بزنم و ببندم و اون
// ادامه بده کارشو ولی نمیخوام خیلی تو ابعاد گسترده باز باشه که … گیج بشم». So:
// - under the session's header ONE row: a chip per seat (its mark, its name, a ring while he works, a dot while his lines wait), an empty
//   media seat as a dashed «+ نویسنده», and «گوینده: …» when the company's narrator is set;
// - a filled seat opens a half-height sheet «با …»: his side lines as the session's own bubbles, a composer, close. While it is open it
//   reads the lines again every four seconds, and at once on the stream's `session.team` (the query's tag);
// - an empty seat asks once «… استخدام شود؟» → «استخدام کن» (no passkey); «گوینده» opens §48's picker; the holder's chip goes to the
//   session's own composer.
// The main thread stays the holder's: nothing of a side talk is drawn in it (the hub writes one line per burst there itself).

/** The query of the session's team (tag `session-team`: the stream's `session.team` refreshes it). Null data on a hub without `/team`. */
@Composable
internal fun rememberSessionTeam(ref: String) =
    rememberQuery("session-team:$ref", "session-team", maxAgeMs = 10_000) { gated(HubFeature.SESSION_TEAM) { sessionTeam(ref) } }

/** How often an open side talk reads its lines again. */
private const val SIDE_POLL_MS = 4_000L

// ------------------------------------------------------------------ the row --
/** «تیم این جلسه»: the seats in the hub's order (the holder first), then the narrator. A tap on a chip is the caller's ([onSeat]). */
@Composable
internal fun TeamRow(team: SessionTeam, onSeat: (SessionSeat) -> Unit, onNarrator: (TeamNarrator) -> Unit, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Row(
        modifier.fillMaxWidth().testTag("session-team").padding(start = 16.dp, end = 8.dp, bottom = 8.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(TEAM_FA, style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted, maxLines = 1)
        ScrollRow(Modifier.weight(1f), spacing = 6.dp) {
            for (s in team.seats) if (s.empty) EmptySeatChip(s) { onSeat(s) } else SeatChip(s) { onSeat(s) }
            team.narrator?.let { n -> NarratorChip(n) { onNarrator(n) } }
        }
    }
}

/** The mark of a seat: the holder's, the writer's pen, the director's camera, the motion designer's picture, anyone else's. */
private fun seatIcon(s: SessionSeat): DivanIcon = when {
    s.holder -> DivanIcon.OWNER
    s.roleKey == "scriptwriter" -> DivanIcon.EDIT
    s.roleKey == "video_director" -> DivanIcon.VIDEO
    s.roleKey == "motion_designer" -> DivanIcon.IMAGE
    else -> DivanIcon.AGENT
}

/** A filled seat: its mark in a small disc (a ring turns round it while he works; still when animations are removed), its name, and a
 *  dot while lines of his wait for the owner. The holder's carries the silver hairline: the main thread is his. */
@Composable
private fun SeatChip(s: SessionSeat, onClick: () -> Unit) {
    val c = Divan.colors
    val working = s.state == "working"
    val said = listOfNotNull("در کار".takeIf { working }, if (s.unread > 0) "${faNum(s.unread)} حرف تازه" else null).joinToString("، ")
    Row(
        Modifier.height(34.dp).clip(CircleShape).background(c.tile).border(1.dp, if (s.holder) silverLine() else c.lineDivider, CircleShape)
            .clickable(role = Role.Button, onClickLabel = if (s.holder) "نوشتن به مسئول جلسه" else sideTitleFa(s), onClick = onClick)
            .semantics { if (said.isNotEmpty()) stateDescription = said }
            .padding(start = 4.dp, end = 10.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Box(Modifier.size(26.dp), contentAlignment = Alignment.Center) {
            if (working) Ring(null, size = 26.dp, stroke = 2.dp, tone = RingTone.SILVER, live = true)
            Box(Modifier.size(20.dp).clip(CircleShape).background(c.raised), contentAlignment = Alignment.Center) {
                DIcon(seatIcon(s), size = 12.dp, tint = if (s.holder) c.textPrimary else c.silverInk)
            }
        }
        Text(s.roleFa, style = Divan.type.micro.copy(fontWeight = if (s.holder) FontWeight.SemiBold else FontWeight.Normal), color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
        if (s.unread > 0) LiveDot(c.goldInk, live = false, size = 7.dp)
    }
}

/** An empty media seat: a dashed «+ نویسنده». */
@Composable
private fun EmptySeatChip(s: SessionSeat, onClick: () -> Unit) {
    val c = Divan.colors
    Row(
        Modifier.height(34.dp).clip(CircleShape).dashedPill(c.lineStrong)
            .clickable(role = Role.Button, onClickLabel = hireAskFa(s), onClick = onClick).padding(horizontal = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(seatChipFa(s), style = Divan.type.micro, color = c.textSecondary, maxLines = 1)
    }
}

/** «گوینده: Kore، محکم»: the company's narrator; a tap opens §48's picker. */
@Composable
private fun NarratorChip(n: TeamNarrator, onClick: () -> Unit) {
    val c = Divan.colors
    Row(
        Modifier.height(34.dp).clip(CircleShape).border(1.dp, c.lineDivider, CircleShape)
            .clickable(role = Role.Button, onClickLabel = "گوینده‌ی محتوا", onClick = onClick).padding(horizontal = 10.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp),
    ) {
        DIcon(DivanIcon.MIC, size = 13.dp, tint = c.textSecondary)
        Text(timesFig(narratorChipFa(n)), style = Divan.type.micro, color = c.textSecondary, maxLines = 1)
    }
}

/** A pill's dashed hairline, inside its bounds. */
private fun Modifier.dashedPill(color: Color) = drawBehind {
    val w = 1.dp.toPx()
    drawRoundRect(
        color, topLeft = Offset(w / 2, w / 2), size = Size(size.width - w, size.height - w), cornerRadius = CornerRadius((size.height - w) / 2),
        style = Stroke(w, pathEffect = PathEffect.dashPathEffect(floatArrayOf(4.dp.toPx(), 3.dp.toPx()))),
    )
}

// ------------------------------------------------------------- a side talk --
/** The half-height sheet of one seat: [SideTalk] in the app's one sheet. */
@Composable
internal fun SideTalkSheet(ref: String, seat: SessionSeat, closed: Boolean, onDismiss: () -> Unit) {
    SpringSheetFrame(onDismiss) { SideTalk(ref, seat, closed, onDismiss) }
}

/**
 * «با سناریست پرو-چارت»: half the screen tall. His side lines, newest at the bottom (the owner's on his side with the gold edge, the
 * seat's opposite: the session's own bubbles), read again every four seconds and on `session.team`; older ones one tap away; a quiet
 * line while he is at work on the owner's last word; the composer (his word goes to this person alone, with the press's own key), close.
 */
@Composable
internal fun SideTalk(ref: String, seat: SessionSeat, closed: Boolean, onClose: () -> Unit, modifier: Modifier = Modifier) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val code = seat.code
    val q = rememberQuery("session-team-lines:$ref:$code", "session-team", maxAgeMs = 2_000) { gated(HubFeature.SESSION_TEAM) { sideLines(ref, code) } }
    LaunchedEffect(ref, code) { while (true) { delay(SIDE_POLL_MS); q.refresh() } }
    // Older pages asked for here, the owner's own lines until the hub's page carries them, and the press's key (kept across a retry).
    var older by remember(ref, code) { mutableStateOf<Page<SideLine>?>(null) }
    var olderLines by remember(ref, code) { mutableStateOf(emptyList<SideLine>()) }
    var mine by remember(ref, code) { mutableStateOf(emptyList<SideLine>()) }
    var key by remember(ref, code) { mutableStateOf(UUID.randomUUID().toString()) }
    val more = if (older == null) q.data?.nextCursor else older?.nextCursor
    val loadingOlder = rememberAction()
    val lines = remember(olderLines, q.data, mine) { mergeSideLines(olderLines, q.data?.items.orEmpty() + mine) }
    val height = (LocalConfiguration.current.screenHeightDp * 0.5f).dp
    Column(modifier.fillMaxWidth().imePadding().height(height).testTag("side-talk").padding(horizontal = 16.dp).padding(bottom = 12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(timesFig(sideTitleFa(seat)), style = Divan.type.h3, color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(
                    remember(seat) { facts(seat.roleFa.takeIf { it != seat.whoFa }, if (seat.state == "working") "در کار" else null, "گفتگوی کوتاه؛ جلسه همان است") },
                    style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis,
                )
            }
            IconBtn(DivanIcon.CLOSE, "بستن", onClose, tint = c.textSecondary)
        }
        Box(Modifier.weight(1f).fillMaxWidth()) {
            when {
                lines.isNotEmpty() -> LazyColumn(Modifier.fillMaxSize().testTag("side-lines"), reverseLayout = true, verticalArrangement = Arrangement.spacedBy(10.dp, Alignment.Bottom)) {
                    // While he is at work on the owner's last word: one quiet line, never a spinner of its own.
                    if (seat.state == "working" && lines.last().owner) item(key = "at-work") {
                        Text("${seat.whoFa} روی حرفت کار میکند؛ جوابش همین‌جا می‌آید.", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.fillMaxWidth(), textAlign = TextAlign.Center)
                    }
                    items(lines.asReversed(), key = { it.idText.ifBlank { it.at + it.text.hashCode() } }) { l ->
                        TalkBubble(sideTurn(l, code), null, emptyList(), showName = false, onReplay = null, onRun = { _, _ -> }, onDismiss = {}, timeAtEnd = true, quiet = true)
                    }
                    if (more != null) item(key = "older") {
                        Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                            Text(
                                if (loadingOlder.busy) "…" else "حرف‌های پیش‌تر",
                                Modifier.clip(CircleShape).clickable(role = Role.Button, enabled = !loadingOlder.busy) {
                                    loadingOlder.run {
                                        val p = env.api.sideLines(ref, code, before = more)
                                        olderLines = mergeSideLines(p.items, olderLines)
                                        older = p
                                    }
                                }.padding(horizontal = 12.dp, vertical = 6.dp),
                                style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.silverInk,
                            )
                        }
                    }
                }
                q.loading -> Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Skeleton(Modifier.fillMaxWidth(0.6f).height(44.dp), radius = 16.dp)
                    Skeleton(Modifier.fillMaxWidth(0.45f).height(44.dp).align(Alignment.End), radius = 16.dp)
                }
                else -> Text(
                    "هنوز با او حرفی نزده‌ای. هر چه اینجا بگویی به خود او میرسد و کارش را ادامه میدهد؛ جلسه‌ی اصلی همان است.",
                    Modifier.fillMaxWidth().align(Alignment.Center).padding(horizontal = 12.dp), style = Divan.type.caption, color = c.textMuted, textAlign = TextAlign.Center,
                )
            }
        }
        if (!closed) Composer(
            "به ${seat.whoFa} بگو…",
            onSend = { body, _ ->
                if (body.isBlank()) return@Composer
                try {
                    val out = env.api.sayToSeat(ref, code, body, key)
                    key = UUID.randomUUID().toString()
                    mine = mine + out.line
                    // his line in the list now; the row's dot and ring and this list from the hub right after
                    env.cache.invalidate("session-team")
                } catch (e: ApiException) {
                    toasts.error(e.messageFa)
                    throw e
                }
            },
            allowFiles = false, draftKey = "side:$ref:$code",
        )
    }
}

// ----------------------------------------------------------------- a hire --
/** «نویسنده استخدام شود؟»: the one question before an empty seat is filled; «استخدام کن» in the sheet's bar (no passkey). */
@Composable
internal fun HireSeatSheet(ref: String, seat: SessionSeat, onDismiss: () -> Unit, onHired: (SessionTeam) -> Unit) {
    com.coinepro.hq.ui.v14.HqSheet(onDismiss, hireAskFa(seat), sub = HIRE_SUB_FA) { HireSeatBody(ref, seat, onHired) }
}

/** What the hire sheet says under its question. */
internal const val HIRE_SUB_FA = "همین‌جا در جلسه، با تنظیم پیش‌فرض همین نقش؛ در سقف پاکت ماه."

/** The hire's few words and its bar: the hub's answer is the team with the seat filled; its refusal, its own Persian words. */
@Composable
internal fun HireSeatBody(ref: String, seat: SessionSeat, onHired: (SessionTeam) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val haptics = rememberHaptics()
    val c = Divan.colors
    val hire = rememberAction()
    // One key per press, kept across a retry of the same press.
    val key = remember(ref, seat.key) { UUID.randomUUID().toString() }
    Text(
        "${seat.roleFa} به همین جلسه می‌آید و از همین حالا کنار مسئول کار میکند. هر وقت خواستی رویش بزن و مستقیم با خودش حرف بزن.",
        style = Divan.type.small, color = c.textSecondary,
    )
    SheetBar {
        DecisionBar(
            "استخدام کن", {
                val role = seat.roleKey ?: return@DecisionBar
                hire.run(onError = { e: ApiException -> haptics.error(); toasts.error(e.messageFa) }) {
                    val out = env.api.hireSeat(ref, role, key)
                    haptics.seal()
                    toasts.ok("${seat.roleFa} استخدام شد و به جلسه آمد.")
                    env.cache.invalidate("sessions", "office", "employees")
                    onHired(out)
                }
            },
            icon = DivanIcon.HIRE, state = if (hire.busy) DecisionState.WORKING else DecisionState.IDLE,
        )
    }
}

// ------------------------------------------------------------- the narrator --
/** «گوینده» of the order's company: §48's own picker, as on the working group and the company's page. */
@Composable
internal fun TeamNarratorSheet(company: String, onDismiss: () -> Unit, onSaved: () -> Unit) {
    val c = Divan.colors
    com.coinepro.hq.ui.v14.HqSheet(onDismiss, "گوینده‌ی محتوا", sub = "یک بار برای همیشه: هر ریلز و ویدیوی این شرکت با همین صدا و همین سبک گفته میشود.") {
        val q = com.coinepro.hq.ui.playbook.rememberNarrator(company)
        val n = q.data
        when {
            n != null -> com.coinepro.hq.ui.playbook.NarratorPicker(n) { out -> q.set(out); onSaved() }
            q.loading -> Skeleton(Modifier.fillMaxWidth().height(120.dp), radius = 12.dp)
            else -> Text("گوینده‌ی این شرکت با به‌روزرسانی بعدی هاب از اینجا عوض میشود.", style = Divan.type.caption, color = c.textMuted)
        }
    }
}
