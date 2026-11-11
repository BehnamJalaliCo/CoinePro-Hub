package com.coinepro.hq.ui.look

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.data.DECIDE_YOURSELF_FA
import com.coinepro.hq.core.data.PACE_FA
import com.coinepro.hq.core.data.STATE3_FA
import com.coinepro.hq.core.data.faNum
import com.coinepro.hq.core.data.readyAnswers
import com.coinepro.hq.core.data.sortSessions
import com.coinepro.hq.core.data.standingFa
import com.coinepro.hq.core.data.state3
import com.coinepro.hq.core.data.taskLineFa
import com.coinepro.hq.core.data.turnCount
import com.coinepro.hq.core.data.waitedFa
import com.coinepro.hq.core.format.decisionKind
import com.coinepro.hq.core.format.risk
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.Decision
import com.coinepro.hq.core.net.Office
import com.coinepro.hq.core.net.SessionCard
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.DrawnMark
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Radius
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.continuity
import com.coinepro.hq.designsystem.facts
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.rememberHaptics
import com.coinepro.hq.designsystem.settle
import com.coinepro.hq.designsystem.stagger
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.v29.plain
import kotlinx.coroutines.launch
import java.util.UUID

// ⟨1.0.1⟩ Part C, the home rebuilt (C3.1). The top of the office is the «نوبت تو» row: one large gold count and, under it, what waits
// for the owner as cards that are answered right there (a session's question with its ready answers, one tap; a decision with its
// own action). Then open sessions as cards with three states only («منتظر تو», «در کار», «تمام»), each opening out of itself (M14).
// Nothing here sends the owner elsewhere to answer; the first decision's «تأیید» is the page's only full gold.
//
// Shared pieces a later screen may use: [StateMark] (the three states as a shape and a word), [goldEdge] (the thin gold line at the
// start edge of what waits for him), [SessionCards].

// ============================================================================================== the three states ==
/** A shape and a word, never colour alone: a gold dot (it waits for him), a silver ring (work), a tick (done). */
@Composable
fun StateMark(state: String, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val ink = when (state) { "waiting" -> c.goldInk; "working" -> c.silverInk; else -> c.textMuted }
    Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        when (state) {
            "waiting" -> Box(Modifier.size(8.dp).clip(CircleShape).background(ink))
            "working" -> Canvas(Modifier.size(10.dp)) { drawCircle(ink, size.minDimension / 2 - 0.75.dp.toPx(), style = Stroke(1.5.dp.toPx())) }
            else -> DrawnMark(true, ink, size = 11.dp)
        }
        Text(STATE3_FA[state] ?: state, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = ink, maxLines = 1)
    }
}

/** «منتظر تو» and an unread row: a thin line at the start edge, the only gold such a row carries ([color]: red for an urgent one). */
fun Modifier.goldEdge(color: Color, inset: Dp = 12.dp, width: Dp = 2.dp): Modifier = drawBehind {
    val w = width.toPx()
    val pad = inset.toPx().coerceAtMost(size.height / 3)
    val x = if (layoutDirection == LayoutDirection.Rtl) size.width - w else 0f
    drawRoundRect(color, Offset(x, pad), Size(w, size.height - 2 * pad), CornerRadius(w / 2))
}

/** A card that waits for him: the card surface with the gold line at its start edge. */
@Composable
private fun WaitCard(index: Int, modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    val c = Divan.colors
    Box(modifier.fillMaxWidth().stagger(index).clip(RoundedCornerShape(14.dp)).background(c.card).goldEdge(c.goldInk).padding(14.dp)) { content() }
}

private val answerShape = RoundedCornerShape(12.dp)

// ====================================================================================== a session that waits for him ==
/**
 * A session in his turn: the full question, its ready answers (one tap sends that answer through the session's own reply), how long
 * it has waited and which task stands still. Anything else that waits (ready for his approval) says why and opens.
 */
@Composable
private fun WaitingSession(s: SessionCard, index: Int) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val haptics = rememberHaptics()
    val scope = androidx.compose.runtime.rememberCoroutineScope()
    // The question itself is in the session's report (the card carries only its first words): the same cached read the session uses.
    val report = if (s.badge == "your_turn") com.coinepro.hq.ui.v29.rememberOrderReport(s.ref) else null
    val turn = report?.data?.turn
    val question = turn?.questionFa?.trim()?.ifBlank { null }
    val asks = s.badge == "your_turn" && question != null
    var sent by rememberSaveable(s.ref) { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf<String?>(null) }
    val key = remember(s.ref) { UUID.randomUUID().toString() }
    val who = turn?.whoFa?.ifBlank { null } ?: s.holder?.let { h -> listOfNotNull(h.titleFa.ifBlank { null }, h.companyFa?.takeIf { co -> co.isNotBlank() && !h.titleFa.contains(co) }).joinToString(" ") }?.ifBlank { null } ?: "مشاور کل"
    val open = { nav.go("session/${s.ref}") }
    fun reply(text: String) {
        if (busy != null) return
        busy = text
        scope.launch {
            try {
                env.api.orderReply(s.ref, text, key)
                haptics.seal()
                sent = text
                env.cache.invalidate("sessions", "office", "orders", "order-report", "home")
            } catch (e: ApiException) {
                haptics.error()
                toasts.error(e.messageFa)
            } finally {
                busy = null
            }
        }
    }
    // (The card of the same session further down the page carries the continuity key: one element per key on a screen.)
    WaitCard(index, Modifier.testTag("wait-session")) {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).clickable(role = Role.Button, onClickLabel = "باز کردن جلسه", onClick = open), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    s.holder?.company?.takeIf { it.isNotBlank() }?.let { CompanyMark(it, height = 11.dp, mono = true, ink = c.textMuted) }
                    Text(
                        remember(s, who, asks) { facts(if (asks) "$who میپرسد" else who, waitedFa(turn?.at?.ifBlank { null } ?: s.lastAt.ifBlank { s.openedAt }), standingFa(s)) },
                        style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f),
                    )
                }
                Text(plain(question ?: s.reasonFa.ifBlank { s.titleFa }), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = if (asks) Int.MAX_VALUE else 2, overflow = TextOverflow.Ellipsis)
                if (asks) Text(plain(s.titleFa), style = Divan.type.caption, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            when {
                sent != null -> Row(Modifier.settle(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    DrawnMark(true, c.positive, size = 14.dp)
                    Text("جوابت رفت: $sent", style = Divan.type.caption, color = c.textSecondary)
                }
                asks -> ReadyAnswers(readyAnswers(question), busy, ::reply)
                // Nothing to answer in a word (ready for his approval, or a block of his to lift): it opens the session.
                else -> HqButton("ببین", open, variant = BtnVariant.SECONDARY, size = BtnSize.SM)
            }
        }
    }
}

/** The two or three answers a question offers as buttons, then the quiet «خودت تصمیم بگیر و ادامه بده». One tap sends it. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ReadyAnswers(answers: List<String>, busy: String?, onAnswer: (String) -> Unit, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Column(modifier, verticalArrangement = Arrangement.spacedBy(4.dp)) {
        if (answers.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            for (a in answers) HqButton(a, { onAnswer(a) }, variant = BtnVariant.SECONDARY, size = BtnSize.MD, enabled = busy == null, loading = busy == a)
        }
        HqButton(DECIDE_YOURSELF_FA, { onAnswer(DECIDE_YOURSELF_FA) }, variant = BtnVariant.TEXT, size = BtnSize.SM, enabled = busy == null, loading = busy == DECIDE_YOURSELF_FA)
    }
}

// ============================================================================================ a decision, in place ==
/** Kinds that are sealed on their own page against a digest: the card leads there instead of sealing in place. */
private val OWN_PAGE = setOf("server_plan", "media_series", "server_destructive")

/**
 * One card of the cartable, answered here: «تأیید» is one tap (the passkey only where the hub's rule asks for it: money, a permanent
 * delete, keys and access, a destructive server command), «رد» asks a short reason. [lead]: the page's one full gold.
 */
@Composable
private fun WaitingDecision(d: Decision, lead: Boolean, index: Int) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val haptics = rememberHaptics()
    val seal = rememberAction()
    val k = decisionKind(d.kind)
    val r = risk(d.risk)
    var done by remember(d.ref) { mutableStateOf<String?>(null) }
    var rejecting by remember { mutableStateOf(false) }
    val own = d.kind in OWN_PAGE
    val passkey = com.coinepro.hq.ui.cartable.needsStepUp(d)
    val open = { nav.go("cartable/${d.ref}") }
    WaitCard(index, Modifier.testTag("wait-decision")) {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).clickable(role = Role.Button, onClickLabel = "جزئیات", onClick = open), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    CompanyMark(d.company, height = 11.dp, mono = true, ink = c.textMuted)
                    Text(
                        remember(d) { facts(k.fa, waitedFa(d.createdAt), r.fa) },
                        style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f),
                    )
                }
                Text(plain(d.title), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 3, overflow = TextOverflow.Ellipsis)
            }
            if (done != null) Row(Modifier.settle(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                DrawnMark(true, c.positive, size = 14.dp)
                Text(done.orEmpty(), style = Divan.type.caption, color = c.textSecondary)
            } else Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (own) HqButton("ببین و تأیید کن", open, variant = BtnVariant.SECONDARY, size = BtnSize.SM)
                else {
                    HqButton("تأیید", {
                        seal.run(onError = { e -> haptics.error(); toasts.error(e.messageFa) }) {
                            val token = if (passkey) env.auth.stepUp(act, com.coinepro.hq.core.net.sealAction(d), com.coinepro.hq.core.net.sealTarget(d)) else null
                            env.api.approve(d.ref, null, token)
                            done = "تأیید شد."
                            env.cache.invalidate("decisions", "inbox", "office")
                        }
                    }, variant = if (lead) BtnVariant.PRIMARY else BtnVariant.SECONDARY, size = BtnSize.SM, icon = if (passkey) DivanIcon.SEAL else null, loading = seal.busy, label = if (passkey) "تأیید با اثر انگشت" else "تأیید")
                    HqButton("رد", { rejecting = true }, variant = BtnVariant.GHOST, size = BtnSize.SM)
                }
                Box(Modifier.weight(1f))
                HqButton("جزئیات", open, variant = BtnVariant.TEXT, size = BtnSize.SM)
            }
        }
    }
    if (rejecting) RejectSheet(d, onDismiss = { rejecting = false }) { rejecting = false; done = "رد شد." }
}

/** «رد این کارت»: one short reason, and «رد کن». */
@Composable
private fun RejectSheet(d: Decision, onDismiss: () -> Unit, onDone: () -> Unit) {
    val env = LocalEnv.current
    val c = Divan.colors
    val go = rememberAction()
    var note by rememberSaveable(d.ref) { mutableStateOf("") }
    com.coinepro.hq.ui.v14.HqSheet(onDismiss, "رد این کارت") {
        Text(plain(d.title), style = Divan.type.small, color = c.textSecondary, maxLines = 2, overflow = TextOverflow.Ellipsis)
        HqTextField(note, { note = it }, "چرا؟ (کوتاه)", Modifier.fillMaxWidth(), maxLength = 300)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            HqButton("رد کن", {
                go.run {
                    env.api.reject(d.ref, note.trim().ifBlank { null }, null)
                    env.cache.invalidate("decisions", "inbox", "office")
                    onDone()
                }
            }, Modifier.weight(1f), variant = BtnVariant.DANGER, loading = go.busy)
            HqButton("انصراف", onDismiss, Modifier.weight(1f), variant = BtnVariant.GHOST)
        }
    }
}

// ==================================================================================================== «نوبت تو» ==
private const val SHOWN = 3

/** The top of the home: how many things wait for him, and each of them answered right there. */
@Composable
fun TurnRow(o: Office, modifier: Modifier = Modifier) {
    val nav = LocalNav.current
    val c = Divan.colors
    var all by rememberSaveable { mutableStateOf(false) }
    val waiting = sortSessions(o.sessions).filter { state3(it.badge) == "waiting" }
    val mine = waiting.filter { it.badge == "your_turn" }
    val ready = waiting.filter { it.badge != "your_turn" }
    val total = turnCount(o)
    if (total == 0) {
        Row(modifier.fillMaxWidth().testTag("turn-row"), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DrawnMark(true, c.positive, size = 14.dp)
            Text("چیزی منتظر تو نیست.", style = Divan.type.small, color = c.textSecondary)
        }
        return
    }
    // A question he can answer in a word comes first, then the cards for his decision; then what he must open to approve.
    val items: List<Any> = mine + o.approvals + ready
    val shown = if (all) items else items.take(SHOWN)
    val lead = o.approvals.firstOrNull { it.kind !in OWN_PAGE }?.ref
    val elsewhere = total - items.size
    Column(modifier.fillMaxWidth().testTag("turn-row"), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            // A count inside the page's sentence («۱۲ … نوبت تو»): Persian digits; the gold of the number is a mark, not a button.
            Text(faNum(total), style = Divan.type.display.copy(fontSize = 44.sp, lineHeight = 48.sp, fontWeight = FontWeight.Bold), color = c.goldInk)
            Column(Modifier.weight(1f).padding(bottom = 4.dp)) {
                Text("نوبت تو", style = Divan.type.h3, modifier = Modifier.semantics { heading() })
                Text("همین‌جا جواب بده؛ کار از همان‌جا ادامه پیدا میکند.", style = Divan.type.caption, color = c.textMuted)
            }
        }
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            shown.forEachIndexed { i, x ->
                when (x) {
                    is SessionCard -> WaitingSession(x, i)
                    is Decision -> WaitingDecision(x, lead = x.ref == lead, index = i)
                }
            }
        }
        when {
            !all && items.size > SHOWN -> HqButton("${faNum(items.size - SHOWN)} مورد دیگر", { all = true }, variant = BtnVariant.TEXT, size = BtnSize.SM)
            elsewhere > 0 -> HqButton("${faNum(elsewhere)} کارت دیگر در کارتابل", { nav.go("cartable") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.NEXT)
        }
    }
}

// ============================================================================================== the open sessions ==
/** One open session as a card: its words, its state (three only), why, whose it is and how far its tasks are. It opens out of itself (M14). */
@Composable
fun SessionCardRow(s: SessionCard, index: Int, onClick: () -> Unit) {
    val c = Divan.colors
    val st = state3(s.badge)
    Column(
        Modifier.fillMaxWidth().stagger(index).continuity("session/${s.ref}")
            .clip(RoundedCornerShape(Radius.tile)).background(c.card)
            .then(if (st == "waiting") Modifier.goldEdge(c.goldInk) else Modifier)
            .clickable(role = Role.Button, onClickLabel = "باز کردن جلسه", onClick = onClick)
            .padding(PaddingValues(horizontal = 14.dp, vertical = 12.dp)),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(plain(s.titleFa), Modifier.weight(1f), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 2, overflow = TextOverflow.Ellipsis)
            StateMark(st, Modifier.padding(top = 2.dp))
        }
        com.coinepro.hq.core.data.sessionLine(s).takeIf { it.isNotBlank() }?.let { Text(plain(it), style = Divan.type.caption, color = c.textSecondary, maxLines = 2, overflow = TextOverflow.Ellipsis) }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            s.holder?.company?.takeIf { it.isNotBlank() }?.let { CompanyMark(it, height = 11.dp, mono = true, ink = c.textMuted) }
            val holder = s.holder?.let { h -> listOfNotNull(h.titleFa.ifBlank { null }, h.companyFa?.takeIf { co -> co.isNotBlank() && !h.titleFa.contains(co) }).joinToString(" ") }?.ifBlank { null } ?: "مشاور کل"
            Text(
                remember(s) { facts(holder, taskLineFa(s), PACE_FA["step"].takeIf { s.pace == "step" }) },
                style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

/** The open sessions, the owner's turn first; at most [limit] here, the rest behind «n جلسه‌ی دیگر». */
@Composable
fun SessionCards(sessions: List<SessionCard>, limit: Int = 6, onMore: () -> Unit, onOpen: (SessionCard) -> Unit) {
    val c = Divan.colors
    val list = sortSessions(sessions)
    if (list.isEmpty()) {
        Text("جلسه‌ی بازی نیست؛ بنویس چه میخواهی تا جلسه‌اش باز شود.", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.padding(vertical = 6.dp))
        return
    }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        list.take(limit).forEachIndexed { i, s -> SessionCardRow(s, i) { onOpen(s) } }
        if (list.size > limit) HqButton("${faNum(list.size - limit)} جلسه‌ی دیگر", onMore, variant = BtnVariant.TEXT, size = BtnSize.SM)
    }
}

/** A sign of the page's top with its name under it (an icon alone says nothing). */
@Composable
fun NamedIcon(icon: DivanIcon, label: String, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Column(
        modifier.width(54.dp).clip(RoundedCornerShape(10.dp)).clickable(role = Role.Button, onClickLabel = label, onClick = onClick).padding(vertical = 4.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        DIcon(icon, size = 20.dp, tint = c.textSecondary)
        Text(label, style = Divan.type.micro.copy(fontSize = 10.sp, lineHeight = 14.sp), color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}
