package com.coinepro.hq.ui.meetings

import com.coinepro.hq.ui.work.priorityText
import com.coinepro.hq.designsystem.fadingEdges
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.layout.widthIn
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.instant
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.format.jWeekday
import com.coinepro.hq.core.format.tokens
import com.coinepro.hq.core.format.until
import com.coinepro.hq.core.net.Actor
import com.coinepro.hq.core.net.ItemOrder
import com.coinepro.hq.core.net.Meeting
import com.coinepro.hq.core.net.MeetingItem
import com.coinepro.hq.core.net.Turn
import com.coinepro.hq.core.net.Whisper
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.MeterBar
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Seal
import com.coinepro.hq.designsystem.SealState
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.budgetTone
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanFixed
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Loadable
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.media.Composer
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v16.Notice
import com.coinepro.hq.ui.v16.prose
import com.coinepro.hq.ui.v17.CLAIM_ICON
import com.coinepro.hq.ui.v17.CLAIM_STATUS
import com.coinepro.hq.ui.v17.ActorAvatar
import com.coinepro.hq.ui.v17.MEETING_STATE
import com.coinepro.hq.ui.v17.MEETING_TYPE
import com.coinepro.hq.ui.v17.PRESENCE_FA
import com.coinepro.hq.ui.v17.RefChip
import com.coinepro.hq.ui.v17.RefTone
import com.coinepro.hq.ui.v17.VOTE_FA
import com.coinepro.hq.ui.v17.budgetFig
import com.coinepro.hq.ui.v17.gov
import com.coinepro.hq.ui.v17.mmss
import com.coinepro.hq.ui.v17.pctOf
import com.coinepro.hq.ui.v17.rememberSecond
import java.util.UUID
import kotlinx.coroutines.delay

private val SPEAKING = setOf("statement", "challenge", "vote")

/** Who spoke in the current round of an item, and who is still in the queue (the devil's advocate last, by rule). */
private fun queueOf(m: Meeting, it: MeetingItem?, turns: List<Turn>): Pair<Set<String>, List<Actor>> {
    if (it == null) return emptySet<String>() to emptyList()
    val spoke = turns.filter { t -> t.item == it.id && t.round == it.round && t.kind in SPEAKING }.map { t -> t.speaker.code }.toSet()
    val devils = m.participants.filter { p -> p.devil }.map { p -> p.actor.code }.toSet()
    val order = it.speakers.sortedBy { s -> if (s.code in devils) 1 else 0 }
    return spoke to order.filter { s -> s.code !in spoke }
}

/** One meeting (contract §20.1): before `live` the owner sees and edits the agenda and the budget; live, the round table; after,
 *  the minutes; a war room is its own room. */
@Composable
fun MeetingScreen(ref: String) {
    val q = rememberQuery("meetings:one:$ref", "meetings") { meeting(ref) }
    val t = rememberQuery("meetings:turns:$ref", "meetings") { turns(ref) }
    val settings = rememberQuery("meetings:settings", "meetings", maxAgeMs = 60_000) { meetingSettings() }
    val live = q.data?.live == true
    // The room polls while it is live (the stream also refreshes it on meeting.turn).
    val onScreen = com.coinepro.hq.ui.rememberOnScreen()
    LaunchedEffect(live, onScreen) { while (live && onScreen) { delay(4_000); t.refresh(); q.refresh() } }
    val r = refresher(q, t)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        val m = q.data
        if (m == null) item { Loadable(q, skeleton = { Skeleton(Modifier.fillMaxWidth().height(360.dp), radius = 16.dp) }) {} }
        else {
            val turns = t.data?.items.orEmpty()
            val rounds = settings.data?.firstOrNull { it.key == m.type }?.maxRounds ?: 2
            val speakers = settings.data?.firstOrNull { it.key == m.type }?.maxSpeakers ?: 6
            when {
                m.type == "war_room" -> warRoom(m, turns)
                m.live -> liveRoom(m, turns, t.data?.whispers.orEmpty(), rounds, speakers)
                m.before -> prepRoom(m)
                else -> minutesRoom(m, turns)
            }
        }
    }
}

// ------------------------------------------------------------------- header --
@Composable
internal fun RoomSeal(m: Meeting, size: Dp) {
    val co = companyOf(rememberCompanies(), m.company)
    Seal(m.company, co.nameFa, co.nameEn, holding = co.holding, state = SealState.SEALED, size = size)
}

@Composable
private fun RoomHeader(m: Meeting, war: Boolean = false, actions: (@Composable () -> Unit)? = null) {
    val c = Divan.colors
    val now = rememberSecond()
    val cap = m.budget.cap
    val used = if (m.before) m.budget.estimate else m.budget.used
    val share = pctOf(used, cap)
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(if (war) c.softNegative else c.card)
            .then(if (war) Modifier.border(1.dp, c.negative.copy(alpha = 0.45f), RoundedCornerShape(16.dp)) else Modifier).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            RoomSeal(m, 44.dp)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(buildAnnotatedString {
                    append("اتاق جلسه · ${MEETING_TYPE[m.type]?.fa ?: m.type} · ${jWeekday(m.startsAt)}، "); fig(jTime(m.startsAt)); append("  "); fig(m.ref)
                }, style = Divan.type.caption, color = c.textMuted)
                Text(m.titleFa, style = Divan.type.h2)
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            LiveClockPill(m, now)
            if (m.mode == "written") Pill("نوشتاری", Tone.WARN, icon = DivanIcon.REPORT)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(if (m.before) "برآورد توکن" else "بودجه‌ی توکن جلسه", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f))
                    Fig(if (cap == null) tokens(used) else budgetFig(used, cap), style = Divan.type.figureSmall, color = c.textSecondary)
                    if (cap == null) Text(" · بی‌سقف", style = Divan.type.micro, color = c.textSecondary)
                }
                MeterBar(if (cap == null) 0.0 else share, tone = if (cap == null) com.coinepro.hq.designsystem.BarTone.SILVER else budgetTone(share))
            }
        }
        if (actions != null) FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) { actions() }
    }
}

// --------------------------------------------------------------- round table --
private data class Seat(val actor: Actor, val role: String, val status: String, val tone: Color, val speaking: Boolean = false)

@Composable
private fun seatsOf(m: Meeting, it: MeetingItem?, turns: List<Turn>): List<Seat> {
    val c = Divan.colors
    val (spoke, queue) = queueOf(m, it, turns)
    val liveNow = m.state == "live" && m.mode == "discussion"
    fun status(a: Actor, devil: Boolean): Seat {
        if (liveNow && queue.getOrNull(0)?.code == a.code) return Seat(a, "", "در حال صحبت", c.goldInk, speaking = true)
        if (liveNow && queue.getOrNull(1)?.code == a.code) return Seat(a, "", "نوبت بعد", c.textSecondary)
        if (devil) return Seat(a, "", "مخالف‌خوان", c.learning)
        val mine = turns.filter { t -> it != null && t.item == it.id && t.speaker.code == a.code }.flatMap { t -> t.claims }
        if (a.code in spoke && mine.isNotEmpty()) return Seat(a, "", "${mine.size} ادعا، ${mine.count { x -> x.status == "sourced" }} منبع", c.textMuted)
        return Seat(a, "", if (it?.speakers?.any { s -> s.code == a.code } == true) "منتظر نوبت" else "بیانیه‌ی نوشته", c.textMuted)
    }
    val owner = Seat(Actor("owner", "owner", "مالک"), "مالک", "گوش میدهد · ${PRESENCE_FA[m.ownerPresence]?.first ?: m.ownerPresence}", c.goldInk)
    val ps = m.participants
    fun seat(p: com.coinepro.hq.core.net.Participant) = if (p.speaker) status(p.actor, p.devil).copy(role = p.roleFa) else Seat(p.actor, p.roleFa, "فقط برای تو", c.goldInk)
    return listOf(owner) + ps.filter { p -> p.speaker && !p.devil }.map(::seat) + ps.filter { p -> !p.speaker }.map(::seat) + ps.filter { p -> p.devil }.map(::seat)
}

@Composable
private fun SeatView(s: Seat) {
    val c = Divan.colors
    Column(Modifier.width(92.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Box(
            Modifier.clip(CircleShape).then(if (s.speaking) Modifier.border(2.dp, c.goldInk, CircleShape) else Modifier).padding(3.dp),
            contentAlignment = Alignment.Center,
        ) { ActorAvatar(s.actor, 40.dp) }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(2.dp)) {
            if (s.speaking) DIcon(DivanIcon.MIC, size = 12.dp, tint = c.goldInk)
            Text(s.actor.displayFa ?: s.actor.code, style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, textAlign = TextAlign.Center, maxLines = 2)
        }
        Text(s.status, style = Divan.type.micro, color = s.tone, textAlign = TextAlign.Center, maxLines = 2)
    }
}

private val DISC_TEXT = Color(0xFFAEB8CF)
private val DISC_INK = Color(0xFFEEF1F8)

/** The table's centre on the phone: the item, its round and the time left of its box, on the lapis disc with a gold rim. */
@Composable
private fun TableCenter(m: Meeting, it: MeetingItem?, start: Long?, rounds: Int) {
    val c = Divan.colors
    val now = rememberSecond()
    val items = m.sortedItems.filter { x -> x.state != "skipped" }
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(DivanFixed.lapisDisc)
            .border(1.5.dp, c.goldInk, RoundedCornerShape(18.dp)).padding(4.dp).border(1.dp, c.goldInk.copy(alpha = 0.35f), RoundedCornerShape(15.dp))
            .padding(horizontal = 16.dp, vertical = 18.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        if (it != null) {
            Text("دستور ${it.n} از ${items.size}، دور ${it.round} از $rounds", style = Divan.type.micro, color = DISC_TEXT)
            Text(prose(it.titleFa), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = DISC_INK, textAlign = TextAlign.Center, maxLines = 2, overflow = TextOverflow.Ellipsis)
            val begin = start ?: instant(m.startsAt)?.toEpochMilli() ?: now
            Fig(mmss(it.timeBoxMin * 60_000L - (now - begin)), style = Divan.type.figureM.copy(fontSize = 24.sp, lineHeight = 32.sp, fontWeight = FontWeight.Bold), color = c.goldBright)
            Text("باقی‌مانده از وقت این دستور", style = Divan.type.micro.copy(fontSize = 10.sp), color = DISC_TEXT)
        } else Text(if (m.state == "live") "همه‌ی دستورها تمام شد؛ جلسه را ببند." else MEETING_STATE[m.state]?.fa.orEmpty(), style = Divan.type.small, color = DISC_TEXT, textAlign = TextAlign.Center)
    }
}

/** The round table, compact for the phone: the centre, then every seat in a row that scrolls (owner first, the devil's advocate last). */
@Composable
private fun RoundTable(m: Meeting, it: MeetingItem?, turns: List<Turn>, rounds: Int) {
    val seats = seatsOf(m, it, turns)
    // The item's clock starts at its first turn (the hub runs the time box; the room reads it from the turns).
    val start = it?.let { x -> turns.filter { t -> t.item == x.id }.mapNotNull { t -> instant(t.at)?.toEpochMilli() }.minOrNull() }
    HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(12.dp)) {
        TableCenter(m, it, start, rounds)
        Spacer(Modifier.height(12.dp))
        // The seats scroll sideways; a soft fade, not a hard cut, at the side that has more.
        val seatsScroll = rememberScrollState()
        Row(Modifier.fillMaxWidth().fadingEdges(seatsScroll).horizontalScroll(seatsScroll).semantics { contentDescription = "حاضران" }, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            for (s in seats) SeatView(s)
        }
    }
}

// --------------------------------------------------------------- the three cards --
@Composable
private fun QueueCard(m: Meeting, it: MeetingItem?, turns: List<Turn>) {
    val c = Divan.colors
    val now = rememberSecond()
    val (_, queue) = queueOf(m, it, turns)
    val devils = m.participants.filter { p -> p.devil }.map { p -> p.actor.code }.toSet()
    val last = turns.lastOrNull { t -> it != null && t.item == it.id }
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("صف نوبت", note = it?.let { x -> "دور ${x.round}" })
        Spacer(Modifier.height(8.dp))
        if (queue.isEmpty()) Text(if (it != null) "این دور تمام شد؛ دور بعد یا دستور بعد با توست." else "دستوری در جریان نیست.", style = Divan.type.caption, color = c.textMuted)
        queue.take(5).forEachIndexed { i, a ->
            Row(Modifier.padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("${i + 1}", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.width(14.dp), textAlign = TextAlign.Center)
                ActorAvatar(a, 28.dp)
                Column(Modifier.weight(1f)) {
                    Text(a.displayFa ?: a.code, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(
                        if (i == 0 && m.state == "live") "در حال صحبت" else if (a.code in devils) "جمع‌بندی دور ${it?.round ?: 1}" else if (i == 1) "نوبت بعد" else "منتظر",
                        style = Divan.type.micro, color = c.textMuted,
                    )
                }
                if (i == 0 && m.state == "live" && last != null) instant(last.at)?.let { at -> Fig(mmss(now - at.toEpochMilli()), style = Divan.type.figureSmall, color = c.textSecondary) }
            }
        }
    }
}

@Composable
private fun ClaimsCard(it: MeetingItem?, turns: List<Turn>) {
    val c = Divan.colors
    val claims = turns.filter { t -> it != null && t.item == it.id }.flatMap { t -> t.claims }
    val rows = listOf("sourced", "challenged", "unsourced").map { k -> k to claims.count { x -> x.status == k } }
    val total = claims.size.coerceAtLeast(1)
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("ادعاها", note = "${claims.size} ادعا در این دستور")
        Spacer(Modifier.height(10.dp))
        CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
            Row(Modifier.fillMaxWidth().height(8.dp).clip(CircleShape), horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                for ((k, n) in rows) if (n > 0) Box(Modifier.weight(n.toFloat() / total).height(8.dp).background(if (k == "sourced") c.silverInk else if (k == "challenged") c.warning else c.negative))
            }
        }
        Spacer(Modifier.height(10.dp))
        for ((k, n) in rows) Row(Modifier.padding(vertical = 3.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DIcon(CLAIM_ICON.getValue(k), size = 14.dp, tint = if (k == "sourced") c.textSecondary else if (k == "challenged") c.warning else c.negative)
            Text(CLAIM_STATUS[k]?.fa.orEmpty(), style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.weight(1f))
            Text("$n", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
        }
    }
}

@Composable
private fun TokensCard(turns: List<Turn>) {
    val c = Divan.colors
    val rows = turns.filter { it.tokens > 0 }.groupBy { it.speaker.code }.map { (_, ts) -> ts.first().speaker to ts.sumOf { it.tokens } }.sortedByDescending { it.second }
    val max = (rows.maxOfOrNull { it.second } ?: 1L).coerceAtLeast(1L)
    HqCard(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.Bottom) {
            Text("توکن هر نفر", style = Divan.type.h3, modifier = Modifier.weight(1f))
            Fig(tokens(rows.sumOf { it.second }), style = Divan.type.figureSmall, color = c.textMuted)
        }
        Spacer(Modifier.height(10.dp))
        for ((a, n) in rows.take(6)) Row(Modifier.padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(a.displayFa ?: a.code, style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
            MeterBar(n * 100.0 / max, Modifier.weight(1.2f), height = 8.dp, color = c.silverInk)
            Fig(tokens(n), Modifier.width(40.dp), style = Divan.type.figureSmall, color = c.textPrimary)
        }
    }
}

// --------------------------------------------------------------- transcript --
@Composable
private fun Agenda(m: Meeting, pick: String?, onPick: (String) -> Unit) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        for (x in m.sortedItems) {
            val cur = x.current
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(if (pick == x.id) c.hover else Color.Transparent)
                    .clickable(role = Role.Tab) { onPick(x.id) }.padding(horizontal = 6.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Box(
                    Modifier.size(26.dp).clip(CircleShape).then(
                        when { x.state == "done" -> Modifier.background(c.silverInk); cur -> Modifier.border(2.dp, c.goldInk, CircleShape); else -> Modifier.border(1.dp, c.lineStrong, CircleShape) },
                    ),
                    contentAlignment = Alignment.Center,
                ) {
                    when {
                        x.state == "done" -> DIcon(DivanIcon.SEAL, size = 14.dp, tint = c.onSilver)
                        cur -> Box(Modifier.size(9.dp).clip(CircleShape).background(c.goldInk))
                        else -> Text("${x.n}", style = Divan.type.micro, color = c.textMuted)
                    }
                }
                Text(
                    prose(x.titleFa), Modifier.weight(1f),
                    style = Divan.type.small.copy(fontWeight = if (cur) FontWeight.SemiBold else FontWeight.Normal, textDecoration = if (x.state == "skipped") TextDecoration.LineThrough else null),
                    color = if (cur) c.textPrimary else if (x.state == "skipped") c.textMuted else c.textSecondary,
                )
                Text("${x.timeBoxMin} دقیقه", style = Divan.type.micro, color = c.textMuted)
            }
        }
    }
}

@Composable
private fun WhisperCard(w: Whisper) {
    val c = Divan.colors
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.softGold).border(1.dp, c.goldInk, RoundedCornerShape(14.dp)).padding(12.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        ActorAvatar(Actor("HQ-ADV", "agent", "مشاور کل"), 24.dp)
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("نجوای مشاور · فقط برای تو", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
            Md(w.textMd)
            if (w.sources.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                for (s in w.sources) RefChip(s.ref, s.note.ifBlank { null }, RefTone.NEUTRAL)
            }
        }
    }
}

@Composable
private fun TurnView(t: Turn, devil: Boolean) {
    val c = Divan.colors
    val flagged = t.claims.filter { it.status == "unsourced" || it.status == "challenged" }
    val v = t.stance?.let { VOTE_FA[it.vote] }
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(if (t.kind == "owner") c.softGold else Color.Transparent).padding(vertical = 10.dp, horizontal = if (t.kind == "owner") 8.dp else 0.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        ActorAvatar(t.speaker, 28.dp)
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(if (t.kind == "owner") "تو" else t.speaker.displayFa ?: t.speaker.code, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.widthIn(max = 150.dp))
                if (devil) Pill("مخالف‌خوان", Tone.LEARN)
                if (t.kind == "challenge") Pill("چالش", Tone.WARN)
                if (v != null) Pill(v.fa, v.tone, dot = true)
                Spacer(Modifier.weight(1f))
                Fig(jTime(t.at), style = Divan.type.figureSmall, color = c.textMuted)
            }
            Md(t.statementMd)
            t.stance?.reasonFa?.takeIf { it.isNotBlank() }?.let { Text("«$it»", style = Divan.type.caption, color = c.textMuted) }
            t.draftMd?.let { d ->
                Text(buildAnnotatedString {
                    withStyleGold(c.goldInk) { append("پیش‌نویس مصوبه: ") }
                    append(prose(d))
                }, Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(8.dp), style = Divan.type.caption.copy(lineHeight = 22.sp), color = c.textPrimary)
            }
            val sourced = t.claims.filter { it.status == "sourced" && it.source != null }
            if (sourced.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                for (x in sourced) RefChip(x.source!!.ref)
            }
            for (x in flagged) Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).background(c.softNegative).padding(horizontal = 8.dp, vertical = 6.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                DIcon(DivanIcon.URGENT, Modifier.padding(top = 3.dp), size = 12.dp, tint = c.negative)
                Text(prose("«${x.textFa}» ${if (x.status == "challenged") "به چالش کشیده شد" else "منبع ندارد"}؛ تا منبع نیاید در صورت‌جلسه و مصوبه نمیاید."), style = Divan.type.caption, color = c.textPrimary)
            }
        }
    }
}

private inline fun androidx.compose.ui.text.AnnotatedString.Builder.withStyleGold(color: Color, block: androidx.compose.ui.text.AnnotatedString.Builder.() -> Unit) {
    val i = pushStyle(androidx.compose.ui.text.SpanStyle(color = color, fontWeight = FontWeight.SemiBold))
    block()
    pop(i)
}

@Composable
private fun Transcript(m: Meeting, turns: List<Turn>, item: String?) {
    val c = Divan.colors
    val devils = m.participants.filter { it.devil }.map { it.actor.code }.toSet()
    val xs = turns.filter { item == null || it.item == item }
    if (xs.isEmpty()) { Text("در این دستور هنوز کسی حرف نزده.", style = Divan.type.caption, color = c.textMuted); return }
    Column {
        xs.forEachIndexed { i, t ->
            if (i > 0 && t.kind != "owner" && xs[i - 1].kind != "owner") Box(Modifier.fillMaxWidth().height(1.dp).background(c.lineDivider))
            TurnView(t, t.speaker.code in devils)
        }
    }
}

@Composable
private fun Drafts(m: Meeting) {
    val c = Divan.colors
    if (m.drafts.isEmpty()) { Text("هنوز پیش‌نویسی نیامده.", style = Divan.type.caption, color = c.textMuted); return }
    val co = companyOf(rememberCompanies(), "HQ")
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        m.drafts.forEachIndexed { i, d ->
            val it = m.items.firstOrNull { x -> x.id == d.item }
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("پیش‌نویس مصوبه ${i + 1}", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk, modifier = Modifier.weight(1f))
                    Text(
                        if (d.votes.total > 0) "رأی‌ها: ${d.votes.support} موافق، ${d.votes.oppose} مخالف، ${d.votes.abstain} ممتنع"
                        else when (it?.state) { "round_1" -> "رأی در دور ۲"; "round_2" -> "در حال رأی"; else -> "بی‌رأی" },
                        style = Divan.type.micro, color = c.textMuted,
                    )
                }
                Md(d.textMd, style = Divan.type.small.copy(lineHeight = 24.sp), color = c.textPrimary)
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Seal("HQ", co.nameFa.ifBlank { "هلدینگ" }, co.nameEn.ifBlank { "Holding" }, holding = true, state = if (d.decision != null) SealState.SEALED else SealState.READY, size = 28.dp)
                    if (d.decision != null) {
                        Text("به کارتابل رفت:", style = Divan.type.micro, color = c.textMuted)
                        RefChip(d.decision)
                    } else Text("بعد از رأی به کارتابل میرود؛ مُهر هلدینگ", style = Divan.type.micro, color = c.textMuted)
                }
            }
        }
    }
}

// --------------------------------------------------------------- live room --
private fun LazyListScope.liveRoom(m: Meeting, turns: List<Turn>, whispers: List<Whisper>, rounds: Int, speakers: Int) {
    item(key = "head") {
        var speak by remember { mutableStateOf(false) }
        RoomHeader(m, actions = if (m.state == "live") ({ LiveControls(m, rounds) { speak = true } }) else null)
        if (speak) HqSheet({ speak = false }, "ورود تو به جلسه", sub = "نوبت تو · صف را جلو میزند") { SpeakBox(m) { speak = false } }
    }
    if (m.mode == "written") item(key = "written") {
        Notice(DivanIcon.REPORT, Divan.colors.softWarning, Divan.colors.warning) {
            Text("این جلسه نوشتاری است: از سهم روزانه‌ی جلسه‌ها چیزی نمانده بود؛ فقط بیانیه‌های نوشته‌شده، بی‌دور بحث.", style = Divan.type.small, color = Divan.colors.textPrimary)
        }
    }
    item(key = "table") { RoundTable(m, m.currentItem, turns, rounds) }
    item(key = "queue") { QueueCard(m, m.currentItem, turns) }
    item(key = "claims") { ClaimsCard(m.currentItem, turns) }
    item(key = "tokens") { TokensCard(turns) }
    item(key = "rules") {
        val c = Divan.colors
        FlowRow(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text("قاعده‌های این جلسه", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            for (r in listOf("حداکثر $rounds دور بحث", "حداکثر $speakers سخنگو در هر دستور", "هر ادعا با منبع", "مخالف‌خوان از نظارت", "تو هر وقت بخواهی نوبت را میگیری")) Text(r, style = Divan.type.caption, color = c.textMuted)
        }
    }
    item(key = "side") {
        val c = Divan.colors
        val cur = m.currentItem
        var pick by rememberSaveable(m.ref) { mutableStateOf<String?>(null) }
        val shown = pick ?: cur?.id
        val whisper = whispers.lastOrNull { it.item == (cur?.id ?: shown) } ?: whispers.lastOrNull()
        HqCard(Modifier.fillMaxWidth()) {
            Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("دستور جلسه", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                    Agenda(m, shown) { pick = it }
                }
                whisper?.let { WhisperCard(it) }
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(buildAnnotatedString {
                        append("متن زنده")
                        if (shown != null && shown != cur?.id) append(" · دستور ${m.items.firstOrNull { it.id == shown }?.n ?: ""}")
                    }, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                    Transcript(m, turns, shown)
                }
                if (m.state == "live") Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("نوبت تو · صف را جلو میزند", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                    SpeakBox(m)
                }
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("مصوبه‌ها", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                    Drafts(m)
                }
                Text("رأی مدیرها جای امضای تو را نمیگیرد؛ هر مصوبه با مُهر تو قانونی و وارد پلنرها میشود.", style = Divan.type.micro, color = c.textMuted)
            }
        }
    }
}

@Composable
private fun LiveControls(m: Meeting, rounds: Int, onWrite: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    var busy by remember { mutableStateOf<String?>(null) }
    var raise by remember { mutableStateOf(false) }
    var end by remember { mutableStateOf(false) }
    var extra by remember { mutableStateOf(20_000L) }
    val it = m.currentItem
    val hasDraft = it != null && m.drafts.any { d -> d.item == it.id }
    val toRound2 = it != null && it.round < rounds && it.round < 2 && hasDraft
    fun run(name: String, ok: String, tokens: Long? = null, after: () -> Unit = {}) {
        busy = name
        action.gov(toasts, onError = { busy = null; false }) {
            env.api.meetingControl(m.ref, name, tokens)
            env.cache.invalidate("meetings", "decisions", "planner", "inbox")
            busy = null
            toasts.ok(ok)
            after()
        }
    }
    HqButton("نوشتن", onWrite, size = BtnSize.SM, icon = DivanIcon.EDIT)
    HqButton(if (toRound2) "رفتن به دور ۲" else "دستور بعد", { run("next_round", if (toRound2) "دور ۲ شروع شد: رأی روی پیش‌نویس." else "دستور بعد شروع شد.") }, size = BtnSize.SM, icon = DivanIcon.NEXT, enabled = it != null, loading = busy == "next_round" && action.busy)
    HqButton("رد کردن دستور", { run("skip_item", "این دستور رد شد.") }, variant = BtnVariant.GHOST, size = BtnSize.SM, enabled = it != null, loading = busy == "skip_item" && action.busy)
    HqButton("افزایش بودجه", { raise = true }, variant = BtnVariant.GHOST, size = BtnSize.SM, icon = DivanIcon.BUDGET)
    HqButton("پایان جلسه", { end = true }, variant = BtnVariant.DANGER, size = BtnSize.SM)
    HqButton("ورود صوتی", onWrite, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.MIC)
    if (raise) AlertDialog(
        onDismissRequest = { raise = false },
        containerColor = c.overlay,
        title = { Text("افزایش بودجه‌ی جلسه", style = Divan.type.h3) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("فقط تو بودجه را بالا میبری. مقدار تازه از سقف روزانه‌ی ایجنت‌ها رزرو میشود.", style = Divan.type.small, color = c.textSecondary)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    for (n in listOf(10_000L, 20_000L, 40_000L)) com.coinepro.hq.ui.v16.Chip(extra == n, { extra = n }) { ink -> Fig("+${tokens(n)}", style = Divan.type.figureSmall, color = ink) }
                }
            }
        },
        confirmButton = { HqButton("اضافه کن", { run("raise_budget", "بودجه بیشتر شد.", extra) { raise = false } }, variant = BtnVariant.PRIMARY, loading = busy == "raise_budget" && action.busy) },
        dismissButton = { HqButton("انصراف", { raise = false }, variant = BtnVariant.GHOST) },
    )
    if (end) AlertDialog(
        onDismissRequest = { end = false },
        containerColor = c.overlay,
        title = { Text("پایان جلسه", style = Divan.type.h3) },
        text = { Text("صورت‌جلسه را کد میسازد و منشی خلاصه را فقط از ادعاهای منبع‌دار مینویسد. هر پیش‌نویس یک کارت «مصوبه‌ی جلسه» در کارتابل میشود و فقط با مُهر تو مصوبه است.", style = Divan.type.small, color = c.textSecondary) },
        confirmButton = { HqButton("ببند", { run("end", "جلسه بسته شد؛ صورت‌جلسه و کارت مصوبه‌ها ساخته شد.") { end = false } }, variant = BtnVariant.DANGER, loading = busy == "end" && action.busy) },
        dismissButton = { HqButton("انصراف", { end = false }, variant = BtnVariant.GHOST) },
    )
}

/** The owner's turn: text or voice, jumping the queue. One key per text, kept across retries. */
@Composable
private fun SpeakBox(m: Meeting, onSent: () -> Unit = {}) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    var key by remember { mutableStateOf<String?>(null) }
    Composer("با متن یا صدا وارد شو…", { body, files ->
        val k = key ?: UUID.randomUUID().toString().also { key = it }
        try {
            env.api.speak(m.ref, body.ifBlank { null }, files.firstOrNull(), k)
            key = null
            env.cache.invalidate("meetings")
            toasts.ok("حرفت در جلسه ثبت شد؛ نوبت بعد جواب میدهد.")
            onSent()
        } catch (e: com.coinepro.hq.core.net.ApiException) {
            toasts.error(com.coinepro.hq.core.net.govError(e)); throw e
        }
    }, allowFiles = false, purpose = "message", draftKey = "speak:${m.ref}")
}

// --------------------------------------------------------------- prep room --
private fun LazyListScope.prepRoom(m: Meeting) {
    item(key = "prep") { PrepRoom(m) }
}

@Composable
private fun PrepRoom(m: Meeting) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    var order by remember(m.version) { mutableStateOf<List<String>?>(null) }
    val skip = remember(m.version) { mutableStateMapOf<String, Boolean>() }
    var cap by remember(m.version) { mutableStateOf("") }
    var presence by remember(m.version) { mutableStateOf<String?>(null) }
    val base = m.sortedItems
    val ids = order ?: base.map { it.id }
    val items = ids.mapNotNull { id -> base.firstOrNull { it.id == id } }
    fun skipped(x: MeetingItem) = skip[x.id] ?: (x.state == "skipped")
    val capN = cap.trim().takeIf { it.isNotEmpty() }?.toDoubleOrNull()?.let { (it * 1000).toLong() }
    val capBad = cap.isNotBlank() && (capN == null || capN <= 0 || (m.budget.cap != null && capN > m.budget.cap))
    val dirty = order != null || skip.isNotEmpty() || capN != null || (presence != null && presence != m.ownerPresence)
    fun move(i: Int, d: Int) {
        val xs = ids.toMutableList(); val j = i + d
        if (j < 0 || j >= xs.size) return
        xs[i] = xs[j].also { xs[j] = xs[i] }
        order = xs
    }
    val share = pctOf(m.budget.estimate, m.budget.cap)
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        RoomHeader(m, actions = {
            HqButton("ذخیره‌ی دستور", {
                action.gov(toasts) {
                    env.api.patchMeeting(
                        m,
                        items = if (order != null || skip.isNotEmpty()) items.mapIndexed { i, x -> ItemOrder(x.id, i + 1, skipped(x)) } else null,
                        budgetCap = capN,
                        ownerPresence = presence?.takeIf { it != m.ownerPresence },
                    )
                    env.cache.invalidate("meetings", "planner")
                    toasts.ok("دستور جلسه ذخیره شد؛ برآورد دوباره حساب شد.")
                }
            }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.SEAL, enabled = dirty && !capBad, loading = action.busy)
        })
        HqCard(Modifier.fillMaxWidth()) {
            SectionTitle("دستور جلسه", note = "دستور را کد ساخته؛ تو جابه‌جا یا حذفش میکنی")
            Spacer(Modifier.height(10.dp))
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items.forEachIndexed { i, x ->
                    val off = skipped(x)
                    Column(
                        Modifier.fillMaxWidth().alpha(if (off) 0.55f else 1f).clip(RoundedCornerShape(14.dp)).border(1.dp, c.lineDivider, RoundedCornerShape(14.dp)).padding(12.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Box(Modifier.size(26.dp).clip(CircleShape).border(1.dp, c.lineStrong, CircleShape), contentAlignment = Alignment.Center) { Text("${i + 1}", style = Divan.type.micro, color = c.textSecondary) }
                            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                Text(prose(x.titleFa), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold, textDecoration = if (off) TextDecoration.LineThrough else null))
                                Md(x.briefMd, style = Divan.type.caption.copy(lineHeight = 20.sp))
                            }
                            Column {
                                // The chevron points down; turned over it points up.
                                com.coinepro.hq.designsystem.IconBtn(DivanIcon.CHEVRON, "بالاتر", { move(i, -1) }, Modifier.size(36.dp).rotate(180f), tint = if (i == 0) c.disabledText else c.textSecondary)
                                Box(Modifier.offset(y = (-4).dp)) {
                                    com.coinepro.hq.designsystem.IconBtn(DivanIcon.CHEVRON, "پایین‌تر", { move(i, 1) }, Modifier.size(36.dp), tint = if (i == items.size - 1) c.disabledText else c.textSecondary)
                                }
                            }
                        }
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                            Text("${x.timeBoxMin} دقیقه", style = Divan.type.micro, color = c.textMuted)
                            Row(horizontalArrangement = Arrangement.spacedBy((-6).dp)) { for (s in x.speakers) ActorAvatar(s, 22.dp) }
                            for (s in x.sources) RefChip(s.ref, s.note.ifBlank { null }, RefTone.NEUTRAL)
                        }
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Spacer(Modifier.weight(1f))
                            Text("در دستور", style = Divan.type.caption, color = c.textMuted)
                            HqSwitch(!off, { v -> skip[x.id] = !v }, "در دستور: ${x.titleFa}")
                        }
                    }
                }
            }
        }
        HqCard(Modifier.fillMaxWidth()) {
            SectionTitle("بودجه، پیش از شروع", note = "شروع ${until(m.startsAt)}")
            Spacer(Modifier.height(10.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("برآورد", style = Divan.type.small, color = c.textSecondary, modifier = Modifier.weight(1f))
                Fig(budgetFig(m.budget.estimate, m.budget.cap), style = Divan.type.figure, color = c.textPrimary)
            }
            Spacer(Modifier.height(6.dp))
            MeterBar(share, tone = budgetTone(share))
            m.trimmedFa?.let { tr ->
                Spacer(Modifier.height(10.dp))
                Notice(DivanIcon.INFO, c.softWarning, c.warning) { Text(prose(tr), style = Divan.type.caption.copy(lineHeight = 22.sp), color = c.textPrimary) }
            }
            Spacer(Modifier.height(10.dp))
            Text("کم کردن بودجه (هزار توکن)", style = Divan.type.caption, color = c.textSecondary)
            Spacer(Modifier.height(6.dp))
            CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                HqTextField(cap, { cap = it.filter { ch -> ch.isDigit() || ch == '.' } }, m.budget.cap?.let { (it / 1000).toString() } ?: "—", Modifier.fillMaxWidth(), maxLength = 6, figure = true)
            }
            Spacer(Modifier.height(4.dp))
            Text(if (capBad) "فقط کمتر از سقف فعلی؛ افزایش فقط در جلسه‌ی زنده و با خود تو." else "موقع شروع از سقف روزانه‌ی ایجنت‌ها رزرو میشود.", style = Divan.type.micro, color = if (capBad) c.negative else c.textMuted)
        }
        HqCard(Modifier.fillMaxWidth()) {
            SectionTitle("حضور تو")
            Spacer(Modifier.height(8.dp))
            com.coinepro.hq.ui.v16.ChipRow { for ((k, v) in PRESENCE_FA) FilterChip(v.first, (presence ?: m.ownerPresence) == k, { presence = k }) }
            Spacer(Modifier.height(6.dp))
            Text(PRESENCE_FA[presence ?: m.ownerPresence]?.second.orEmpty(), style = Divan.type.caption, color = c.textMuted)
        }
        HqCard(Modifier.fillMaxWidth()) {
            SectionTitle("حاضران", note = "سخنگوها با قاعده؛ بقیه بیانیه‌ی نوشته")
            Spacer(Modifier.height(8.dp))
            for (p in m.participants) Row(Modifier.padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                ActorAvatar(p.actor, 28.dp)
                Text(p.roleFa, style = Divan.type.small, modifier = Modifier.weight(1f))
                if (p.devil) Pill("مخالف‌خوان", Tone.LEARN) else if (!p.speaker) Pill("فقط برای تو", Tone.NEUTRAL)
            }
        }
    }
}

// --------------------------------------------------------------- minutes --
private fun LazyListScope.minutesRoom(m: Meeting, turns: List<Turn>) {
    item(key = "head") { RoomHeader(m) }
    item(key = "summary") {
        val c = Divan.colors
        HqCard(Modifier.fillMaxWidth()) {
            SectionTitle("خلاصه‌ی جلسه", note = "نوشته‌ی منشی، فقط از ادعاهای منبع‌دار") { m.minutes?.deliverable?.let { RefChip(it, "صورت‌جلسه") } }
            Spacer(Modifier.height(10.dp))
            m.minutes?.summaryMd?.takeIf { it.isNotBlank() }?.let { Md(it) } ?: Empty(if (m.state == "cancelled") "جلسه لغو شد" else "صورت‌جلسه هنوز ساخته نشده", icon = DivanIcon.REPORT)
            Spacer(Modifier.height(10.dp))
            FlowRow(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text("${m.items.count { it.state == "done" }} دستور بررسی شد", style = Divan.type.caption, color = c.textMuted)
                Text(buildAnnotatedString { append("توکن "); fig(budgetFig(m.budget.used, m.budget.cap), c.textSecondary) }, style = Divan.type.caption, color = c.textMuted)
                Text(jDate(m.startsAt, withYear = true), style = Divan.type.caption, color = c.textMuted)
            }
        }
    }
    item(key = "transcript") {
        val c = Divan.colors
        val first = turns.firstOrNull { it.item != null }?.item
        val open = remember(m.ref) { mutableStateMapOf<String, Boolean>() }
        HqCard(Modifier.fillMaxWidth()) {
            SectionTitle("متن جلسه", note = "با ادعاها و پرچم‌های بازرس")
            Spacer(Modifier.height(10.dp))
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                for (x in m.sortedItems) {
                    val on = open[x.id] ?: (x.id == first)
                    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).border(1.dp, c.lineDivider, RoundedCornerShape(12.dp)).padding(horizontal = 12.dp, vertical = 4.dp)) {
                        Row(
                            Modifier.fillMaxWidth().clickable(role = Role.Button) { open[x.id] = !on }.padding(vertical = 8.dp),
                            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            Text("${x.n}.", style = Divan.type.small, color = c.textMuted)
                            Text(prose(x.titleFa), Modifier.weight(1f), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold, textDecoration = if (x.state == "skipped") TextDecoration.LineThrough else null), color = if (x.state == "skipped") c.textMuted else c.textPrimary)
                            Text("${turns.count { it.item == x.id }} نوبت", style = Divan.type.micro, color = c.textMuted)
                            DIcon(DivanIcon.CHEVRON, if (on) Modifier.rotate(180f) else Modifier, size = 16.dp, tint = c.textMuted)
                        }
                        if (on) Transcript(m, turns, x.id)
                    }
                }
            }
        }
    }
    item(key = "drafts") {
        HqCard(Modifier.fillMaxWidth()) {
            Text("مصوبه‌ها", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
            Spacer(Modifier.height(8.dp))
            Drafts(m)
            Spacer(Modifier.height(8.dp))
            Text("هر پیش‌نویس یک کارت «مصوبه‌ی جلسه» است؛ فقط مُهر تو مصوبه و کار پیگیری میسازد.", style = Divan.type.micro, color = Divan.colors.textMuted)
        }
    }
}

// --------------------------------------------------------------- war room --
private fun LazyListScope.warRoom(m: Meeting, turns: List<Turn>) {
    item(key = "head") { RoomHeader(m, war = true) }
    item(key = "war") { WarRoom(m, turns) }
}

@Composable
private fun WarRoom(m: Meeting, turns: List<Turn>) {
    val c = Divan.colors
    val nav = LocalNav.current
    val pm = rememberQuery("meetings:list:postmortem:", "meetings") { meetings("postmortem") }
    val post = pm.data?.firstOrNull { it.incident != null && it.incident == m.incident && it.ref != m.ref }
    val co = companyOf(rememberCompanies(), m.company)
    fun icon(t: Turn) = when {
        t.speaker.kind == "system" -> DivanIcon.URGENT
        Regex("مهار|تأیید").containsMatchIn(t.statementMd) -> DivanIcon.SEAL
        "علت" in t.statementMd -> DivanIcon.SEARCH
        else -> DivanIcon.SERVER
    }
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(c.card).border(1.dp, c.negative.copy(alpha = 0.45f), RoundedCornerShape(16.dp)).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DIcon(DivanIcon.URGENT, size = 20.dp, tint = c.negative)
            Text("اتاق جنگ · ${co.nameFa}", style = Divan.type.bodyStrong, modifier = Modifier.weight(1f))
            m.incident?.let { RefChip(it, tone = RefTone.NEG) }
            Pill(if (m.state == "ended") "مهار شد" else "در جریان", if (m.state == "ended") Tone.POS else Tone.NEG, dot = m.state != "live", live = m.state == "live")
        }
        Text(com.coinepro.hq.designsystem.timesFig(buildAnnotatedString { append("از ${jTime(m.startsAt)} · اولویت "); priorityText("P0"); append(" · بی‌سقف جلسه، داخل سقف روزانه و کلید توقف") }), style = Divan.type.caption, color = c.textMuted)
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("خط زمانی", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
            for (t in turns) Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Fig(jTime(t.at), Modifier.width(40.dp).padding(top = 2.dp), style = Divan.type.figureSmall, color = c.textMuted)
                DIcon(icon(t), Modifier.padding(top = 2.dp), size = 16.dp, tint = if (t.speaker.kind == "system") c.negative else c.goldInk)
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Md(t.statementMd, color = c.textPrimary)
                    val src = t.claims.filter { it.source != null }
                    if (src.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) { for (x in src) RefChip(x.source!!.ref, tone = RefTone.NEUTRAL) }
                }
            }
        }
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("حاضران", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
            for (p in m.participants) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                ActorAvatar(p.actor, 28.dp)
                Text(p.roleFa, style = Divan.type.small)
            }
            Text(buildAnnotatedString {
                if (post != null) { append("کالبدشکافی ${jWeekday(post.startsAt)} "); fig(jTime(post.startsAt)); append(" در پلنر ثبت شد ("); fig(post.ref, c.goldInk); append("). ") }
                append(prose("هر مهار بیرونی یک کارت A3 است. هشدار فوری حتی در خلوت میرسد."))
            }, Modifier.clickable(enabled = post != null, role = Role.Button) { post?.let { nav.go("meetings/${it.ref}") } }, style = Divan.type.caption, color = c.textMuted)
        }
        m.minutes?.summaryMd?.let { Md(it, Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp)) }
        if (m.state == "live") SpeakBox(m)
    }
}
