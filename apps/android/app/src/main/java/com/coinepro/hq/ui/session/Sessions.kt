package com.coinepro.hq.ui.session

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.badgeFa
import com.coinepro.hq.core.data.badgeTone
import com.coinepro.hq.core.data.isPlayer
import com.coinepro.hq.core.data.sessionLine
import com.coinepro.hq.core.data.sortSessions
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.SessionCard
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.toneColors
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.served

// Contract §35.3 ⟨1.17⟩: the owner's sessions. Every order is one, like a Claude Code session: open until he says it is done, then in
// the archive, from where it can be opened again. The list says, for each, whose turn it is and why, in one plain line; no refs.

/** The open sessions (the office and the bottom bar read the same query). Null: this hub does not serve sessions yet. */
@Composable
fun rememberSessions(state: String = "open") =
    rememberQuery("sessions:$state", "sessions", "orders", maxAgeMs = 15_000) { gated(HubFeature.SESSIONS) { sessions(state, limit = 100).items } }

/** A session's badge as a pill: «نوبت تو» in gold, «گیر» in red; the moving one breathes. */
@Composable
fun BadgePill(badge: String, modifier: Modifier = Modifier) {
    Pill(badgeFa(badge), badgeTone(badge), modifier, dot = badge != "moving", live = badge == "moving")
}

/** One session in a list: its words, its badge, why, who holds it, how far its plan is. */
@Composable
fun SessionRow(s: SessionCard, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val c = Divan.colors
    val (_, ink) = toneColors(badgeTone(s.badge))
    Row(
        modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).clickable(role = Role.Button, onClickLabel = "باز کردن جلسه", onClick = onClick).padding(vertical = 10.dp, horizontal = 4.dp),
        verticalAlignment = Alignment.Top,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Box(Modifier.padding(top = 7.dp).size(8.dp).clip(CircleShape).background(ink))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(plain(s.titleFa), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 2, overflow = TextOverflow.Ellipsis)
            sessionLine(s).takeIf { it.isNotBlank() }?.let { Text(plain(it), style = Divan.type.caption, color = if (s.badge == "your_turn") c.goldInk else c.textSecondary, maxLines = 2, overflow = TextOverflow.Ellipsis) }
            val who = listOfNotNull(
                // The holder in his own words; the company only when his title does not already say it.
                s.holder?.let { h -> listOfNotNull(h.titleFa.ifBlank { null }, h.companyFa?.ifBlank { null }?.takeIf { co -> !h.titleFa.contains(co) }).joinToString("، ") }?.ifBlank { null },
                s.participants.count { isPlayer(it.key) }.takeIf { it > 0 }?.let { "$it مدل" },
                s.tasks.total.takeIf { it > 0 }?.let { "${s.tasks.done} از $it کار" },
                (s.lastAt.ifBlank { s.openedAt }).takeIf { it.isNotBlank() }?.let { ago(it) },
            ).joinToString(" · ")
            if (who.isNotBlank()) Text(who, style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        BadgePill(s.badge)
    }
}

/** «جلسه‌ها»: the open ones (the owner's turn first) and the archive of closed ones, each opening its session. */
@Composable
fun SessionsScreen(tab0: String = "open") {
    val nav = LocalNav.current
    val c = Divan.colors
    var tab by rememberSaveable { mutableStateOf(tab0) }
    val open = rememberSessions("open")
    val closed = rememberSessions("closed")
    val r = refresher(open, closed)
    val has = served(HubFeature.SESSIONS)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item(key = "head") {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                PageHeader("جلسه‌ها", eyebrow = "هر فرمان یک جلسه است، تا وقتی تو بگویی تمام شد")
                Segmented(listOf(SegOption("open", "باز"), SegOption("closed", "بایگانی")), tab, { tab = it }, Modifier.fillMaxWidth())
            }
        }
        val q = if (tab == "open") open else closed
        val list = q.data?.let { if (tab == "open") sortSessions(it) else it.filter { s -> !s.hidden }.sortedByDescending { s -> s.closedAt ?: s.lastAt } }
        when {
            !has -> item(key = "none") { Empty("جلسه‌ها با به‌روزرسانی بعدی هاب میایند", icon = DivanIcon.MEETING, body = "تا آن موقع هر فرمان از دفتر و «فرمان‌های من» دنبال میشود.") }
            list == null && q.error != null -> item(key = "error") { ErrorBlock(q.error, { q.refresh() }) }
            list == null -> items(3, key = { "sk-$it" }) { Skeleton(Modifier.fillMaxWidth().height(84.dp), radius = 14.dp) }
            list.isEmpty() -> item(key = "empty") {
                if (tab == "open") Empty("جلسه‌ی بازی نیست", icon = DivanIcon.MEETING, body = "هر فرمان تازه همان لحظه یک جلسه باز میکند؛ دکمه‌ی طلایی پایین را بزن.")
                else Empty("بایگانی خالی است", icon = DivanIcon.DELIVERABLE, body = "جلسه‌ای که تأیید کنی و ببندی این‌جا میماند و میشود دوباره بازش کرد.")
            }
            else -> item(key = "list-$tab") {
                HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(horizontal = 12.dp, vertical = 6.dp)) {
                    list.forEachIndexed { i, s ->
                        if (i > 0) HorizontalDivider(color = c.lineDivider)
                        SessionRow(s) { nav.go("session/${s.ref}") }
                    }
                }
            }
        }
    }
}

/** The bottom bar's count on «جلسه‌ها»: sessions waiting for the owner. */
@Composable
fun yourTurnBadge(): Int = rememberSessions("open").data?.let { com.coinepro.hq.core.data.yourTurnCount(it) } ?: 0
