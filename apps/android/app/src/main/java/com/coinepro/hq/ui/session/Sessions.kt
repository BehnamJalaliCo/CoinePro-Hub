package com.coinepro.hq.ui.session

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
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
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.continuity
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
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

/** A session's badge as a pill: «نوبت تو» in gold, «گیر» in red; the moving one breathes. ⟨1.24⟩ SS-1: a new badge crossfades in (M2),
 *  and turning to «نوبت تو» glints its gold edge once (M13); instant when animations are removed. */
@Composable
fun BadgePill(badge: String, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val reduced = com.coinepro.hq.designsystem.LocalReducedMotion.current
    val glint = remember { androidx.compose.animation.core.Animatable(0f) }
    var first by remember { mutableStateOf(true) }
    androidx.compose.runtime.LaunchedEffect(badge) {
        if (first || reduced || badge != "your_turn") { first = false; return@LaunchedEffect }
        glint.animateTo(1f, androidx.compose.animation.core.tween(com.coinepro.hq.designsystem.Grammar.GLINT * 2 / 5, easing = com.coinepro.hq.designsystem.Motion.Standard))
        glint.animateTo(0f, androidx.compose.animation.core.tween(com.coinepro.hq.designsystem.Grammar.GLINT * 3 / 5, easing = com.coinepro.hq.designsystem.Motion.Standard))
    }
    com.coinepro.hq.designsystem.Crossfading(badge, modifier.semantics { liveRegion = androidx.compose.ui.semantics.LiveRegionMode.Polite }.then(if (glint.value > 0f) Modifier.border(1.dp, c.goldInk.copy(alpha = glint.value), CircleShape) else Modifier)) { b ->
        Pill(badgeFa(b), badgeTone(b), dot = b != "moving", live = b == "moving")
    }
}

/** One session in a list: its words, its badge, why, who holds it, how far its plan is. ⟨1.19⟩ With [onErase] (the archive), a long
 *  press offers «پاک کردن برای همیشه». */
@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
fun SessionRow(s: SessionCard, modifier: Modifier = Modifier, onErase: (() -> Unit)? = null, onClick: () -> Unit) {
    val c = Divan.colors
    val (_, ink) = toneColors(badgeTone(s.badge))
    var menu by remember { mutableStateOf(false) }
    val press = if (onErase == null) Modifier.clickable(role = Role.Button, onClickLabel = "باز کردن جلسه", onClick = onClick)
    else Modifier.combinedClickable(role = Role.Button, onClickLabel = "باز کردن جلسه", onLongClickLabel = "پاک کردن برای همیشه", onLongClick = { menu = true }, onClick = onClick)
    Row(
        modifier.fillMaxWidth().continuity("session/${s.ref}").clip(RoundedCornerShape(12.dp)).then(press).padding(vertical = 10.dp, horizontal = 4.dp),
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
                // ⟨1.24⟩ SS-1: a moving session says when its last step was on its own line (with the idle ring), below.
                (s.lastAt.ifBlank { s.openedAt }).takeIf { it.isNotBlank() && s.badge != "moving" }?.let { ago(it) },
            ).joinToString(" · ")
            if (who.isNotBlank()) Text(who, style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
            StallWatch(s.badge, s.lastAt.ifBlank { s.openedAt })
            // ⟨1.36⟩ §58.2 a closed session that left its working group in the library says so in one line
            if (s.closedAt != null && com.coinepro.hq.core.data.playbookKept(s.playbookKept, s.playbook)) com.coinepro.hq.ui.look.KeptLine(null)
        }
        BadgePill(s.badge)
        // The long press's menu: a popup, it takes no room in the row.
        if (onErase != null) androidx.compose.material3.DropdownMenu(menu, { menu = false }, containerColor = c.overlay) {
            androidx.compose.material3.DropdownMenuItem(
                text = { Text("پاک کردن برای همیشه", style = Divan.type.body, color = c.negative) },
                leadingIcon = { com.coinepro.hq.designsystem.DIcon(DivanIcon.REJECT, size = 20.dp, tint = c.negative) },
                onClick = { menu = false; onErase() },
            )
        }
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
    val eraseOn = served(HubFeature.ERASE)
    var erasing by rememberSaveable { mutableStateOf<String?>(null) }
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
                        // ⟨1.19⟩ §37.1 a closed session is erased from the archive with a long press.
                        SessionRow(s, onErase = if (tab == "closed" && eraseOn) ({ erasing = s.ref }) else null) { nav.go("session/${s.ref}") }
                    }
                }
            }
        }
    }
    erasing?.let { ref ->
        EraseSheet(com.coinepro.hq.core.net.EraseKind.SESSION, ref, onDismiss = { erasing = null }) {
            erasing = null
            closed.refresh()
        }
    }
}

/** The bottom bar's count on «جلسه‌ها»: sessions waiting for the owner. */
@Composable
fun yourTurnBadge(): Int = rememberSessions("open").data?.let { com.coinepro.hq.core.data.yourTurnCount(it) } ?: 0
