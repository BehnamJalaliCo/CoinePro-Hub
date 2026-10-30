package com.coinepro.hq.ui.notifications

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.coinepro.hq.core.data.NotificationGroup
import com.coinepro.hq.core.data.NotificationGroups
import com.coinepro.hq.core.data.Refs
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.format.level
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.Notification
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.RichText
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.toneColors
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.itemMotion
import com.coinepro.hq.ui.outputs.SwipeToSee
import com.coinepro.hq.ui.outputs.Undo
import com.coinepro.hq.ui.outputs.UndoBar
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import kotlinx.coroutines.launch

private val LEVELS = listOf("urgent", "decision", "report", "info", "learning")

/**
 * Notifications (contract §6): «خوانده‌نشده» holds only what the owner has not read; a tap opens it and it leaves the list, a swipe or a
 * row's «خوانده شد» marks it read (with a few seconds to undo), «همه خوانده شد» moves everything there. «خوانده‌شده» keeps the rest. The
 * same alert raised again and again is one row with its count, opened to see each time. Approvals never happen here: a card only opens
 * the cartable.
 */
@Composable
fun NotificationsScreen(tab0: String = "unread", open0: Set<String> = emptySet()) {
    // [open0]: the groups shown open at first ("*": every one; the screenshots).
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val scope = androidx.compose.runtime.rememberCoroutineScope()
    var tab by rememberSaveable { mutableStateOf(tab0) }
    var lvl by rememberSaveable { mutableStateOf<String?>(null) }
    val unreadQ = rememberQuery("notifications:unread:${lvl ?: "all"}", "notifications") { notifications(unread = true, level = lvl, limit = 200) }
    val readQ = rememberQuery("notifications:read:${lvl ?: "all"}", "notifications") { notifications(unread = false, level = lvl, limit = 100) }
    val r = refresher(unreadQ, readQ)
    val marked by env.reads.marked.collectAsStateWithLifecycle()
    var undo by remember { mutableStateOf<Undo?>(null) }
    val open = remember { mutableStateListOf<String>().apply { addAll(open0) } }
    val more = remember(lvl) { mutableStateListOf<Notification>() }
    var cursor by remember(readQ.data) { mutableStateOf(readQ.data?.nextCursor) }
    var loadingMore by remember { mutableStateOf(false) }

    // What waits for its grace time is sent when the owner leaves; a refused send is said in Persian.
    DisposableEffect(env) { onDispose { env.reads.flush() } }
    LaunchedEffect(env) { env.reads.failures.collect { toasts.error(it) } }
    LaunchedEffect(readQ.data) { readQ.data?.items?.filter { it.readAt != null }?.map { it.id }?.let(env.reads::confirmed) }

    val loaded = unreadQ.data?.items
    val (unread, read) = NotificationGroups.split(loaded.orEmpty(), readQ.data?.items.orEmpty() + more, marked)
    val groups = NotificationGroups.group(if (tab == "unread") unread else read)

    fun markRead(g: NotificationGroup) {
        val ids = g.ids.filter { it !in marked }
        if (ids.isEmpty()) return
        val token = env.reads.mark(ids)
        undo = Undo(token, ids, true, if (g.folded) "${g.count} اعلان خوانده شد" else "خوانده شد")
    }

    fun openOne(n: Notification) {
        if (n.readAt == null) env.reads.open(n.id)
        val route = Refs.forLink(n.link?.kind, n.link?.ref)
        if (route != null) nav.go(route)
    }

    androidx.compose.foundation.layout.Box(Modifier.fillMaxSize()) {
        Page(onRefresh = r::refresh, refreshing = r.refreshing) {
            item {
                PageHeader("اعلان‌ها", eyebrow = "فوری هر جا باشی میرسد؛ بقیه این‌جا منتظر میمانند") {
                    if (tab == "unread" && unread.isNotEmpty()) HqButton("همه خوانده شد", {
                        val ids = unread.map { it.id }
                        // Up to the newest the owner sees, of the level on show: what arrives meanwhile stays unread.
                        val token = env.reads.mark(ids, unread.maxOf { it.createdAt } to lvl)
                        undo = Undo(token, ids, true, "${ids.size} اعلان خوانده شد")
                    }, size = BtnSize.SM, variant = BtnVariant.SECONDARY, icon = DivanIcon.SEAL)
                }
            }
            item {
                Segmented(
                    listOf(
                        // Rows, not raw notifications: the hourly finding raised five times is one row to read.
                        SegOption("unread", if (loaded != null && unread.isNotEmpty()) "خوانده‌نشده (${NotificationGroups.group(unread).size})" else "خوانده‌نشده"),
                        SegOption("read", "خوانده‌شده"),
                    ),
                    tab, { tab = it }, Modifier.fillMaxWidth(),
                )
            }
            item {
                com.coinepro.hq.designsystem.ScrollRow {
                    FilterChip("همه", lvl == null, { lvl = null })
                    for (l in LEVELS) FilterChip(level(l).fa, lvl == l, { lvl = if (lvl == l) null else l })
                }
            }
            val q = if (tab == "unread") unreadQ else readQ
            when {
                q.data == null && q.error == null -> items(4) { Skeleton(Modifier.fillMaxWidth().height(76.dp), radius = 14.dp) }
                q.data == null -> item { ErrorBlock(q.error, { q.refresh() }) }
                groups.isEmpty() && tab == "unread" -> item {
                    Empty("همه را خوانده‌ای", icon = DivanIcon.BELL, body = "اعلان تازه این‌جا میاید؛ خوانده‌شده‌ها در «خوانده‌شده» میمانند.")
                }
                groups.isEmpty() -> item { Empty("هنوز اعلانی خوانده نشده", icon = DivanIcon.BELL, body = "اعلانی را بزن یا بکش تا این‌جا بیاید.") }
                else -> {
                    if (tab == "unread") item {
                        Text("بزن تا باز شود، بکش تا خوانده شود؛ تکراری‌ها یک ردیف‌اند.", style = Divan.type.caption, color = c.textMuted)
                    }
                    items(groups, key = { it.key + ":" + it.latest.id }) { g -> Box(itemMotion()) {
                        val unreadTab = tab == "unread"
                        val row: @Composable () -> Unit = {
                            if (g.folded) GroupCard(g, g.key in open || "*" in open, unreadTab, onToggle = { if (g.key in open) open.remove(g.key) else open.add(g.key) }, onOpen = ::openOne, onRead = { markRead(g) })
                            else NotificationCard(g.latest, unreadTab, onOpen = { openOne(g.latest) }, onRead = { markRead(g) })
                        }
                        if (unreadTab) SwipeToSee(seen = false, onSwipe = { markRead(g) }) { row() } else row()
                    }}
                    if (tab == "read" && cursor != null) item {
                        HqButton("بیشتر", {
                            if (!loadingMore) scope.launch {
                                loadingMore = true
                                try {
                                    val page = env.api.notifications(unread = false, level = lvl, limit = 100, cursor = cursor)
                                    more.addAll(page.items.filter { n -> read.none { it.id == n.id } })
                                    cursor = page.nextCursor
                                } catch (e: ApiException) { toasts.error(e.messageFa) } finally { loadingMore = false }
                            }
                        }, Modifier.fillMaxWidth(), variant = BtnVariant.SECONDARY, loading = loadingMore, icon = DivanIcon.NEXT)
                    }
                }
            }
        }
        UndoBar(undo, Modifier.align(Alignment.BottomCenter), onTimeout = { if (undo?.id == it) undo = null }) { u ->
            undo = null
            env.reads.undo(u.id)
        }
    }
}

/** The top line of a row: its level's icon in its tone, what it is about, the company, when, and an unread dot. */
@Composable
private fun Head(n: Notification, unread: Boolean, time: String) {
    val c = Divan.colors
    val (_, fg) = toneColors(level(n.level).tone)
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(NotificationGroups.category(n), style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = fg)
        CompanyMark(n.company, height = 11.dp, mono = true, ink = c.textMuted)
        Text(time, style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
        if (unread) Box(Modifier.size(8.dp).clip(CircleShape).background(c.goldFill))
    }
}

@Composable
private fun LevelBadge(n: Notification) {
    val (bg, fg) = toneColors(level(n.level).tone)
    Box(Modifier.size(36.dp).clip(CircleShape).background(bg), contentAlignment = Alignment.Center) { DIcon(level(n.level).icon, size = 18.dp, tint = fg) }
}

/** One notification. On «خوانده‌نشده» a tap opens it (and it leaves the list); one with nowhere to go has «خوانده شد» instead. */
@Composable
private fun NotificationCard(n: Notification, unreadTab: Boolean, onOpen: () -> Unit, onRead: () -> Unit) {
    val env = LocalEnv.current
    val c = Divan.colors
    val answer = rememberAction()
    val unread = n.readAt == null
    val route = Refs.forLink(n.link?.kind, n.link?.ref)
    HqCard(
        Modifier.fillMaxWidth(), onClick = if (route != null || unread) onOpen else null,
        tahrir = unread && n.level == "urgent", onClickLabel = if (route != null) "باز کن" else "خوانده شد",
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            LevelBadge(n)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Head(n, unread, ago(n.createdAt))
                RichText(n.titleFa, style = Divan.type.small.copy(fontWeight = if (unread) FontWeight.Bold else FontWeight.SemiBold), color = if (unread) c.textPrimary else c.textSecondary)
                if (n.bodyFa.isNotBlank()) RichText(n.bodyFa, style = Divan.type.caption, color = c.textSecondary, maxLines = 3)
                val choices = n.choices
                if (!choices.isNullOrEmpty()) {
                    FlowRow(Modifier.padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        for (ch in choices) {
                            val chosen = n.answer == ch.id
                            Text(
                                ch.labelFa, style = Divan.type.small, color = if (chosen) c.goldInk else c.textSecondary,
                                modifier = Modifier.clip(RoundedCornerShape(16.dp)).background(if (chosen) c.softGold else c.tile)
                                    .clickable(enabled = n.answer == null, role = Role.Button) { answer.run { env.api.answer(n.id, ch.id); env.cache.invalidate("notifications", "inbox") } }
                                    .padding(horizontal = 12.dp, vertical = 6.dp),
                            )
                        }
                    }
                }
                if (unreadTab && route != null && choices.isNullOrEmpty()) Row(Modifier.padding(top = 2.dp), verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.weight(1f))
                    HqButton("خوانده شد", onRead, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.SEAL)
                }
            }
        }
    }
}

/** The same alert raised [NotificationGroup.count] times: its latest words, «۵ بار، آخرین …», and every time on opening the row. */
@Composable
private fun GroupCard(g: NotificationGroup, expanded: Boolean, unreadTab: Boolean, onToggle: () -> Unit, onOpen: (Notification) -> Unit, onRead: () -> Unit) {
    val c = Divan.colors
    val n = g.latest
    val unread = g.items.any { it.readAt == null }
    HqCard(Modifier.fillMaxWidth(), onClick = onToggle, onClickLabel = if (expanded) "بستن" else "همه‌ی دفعه‌ها") {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Box {
                LevelBadge(n)
                Box(
                    Modifier.align(Alignment.BottomStart).size(18.dp).clip(CircleShape).background(c.goldFill),
                    contentAlignment = Alignment.Center,
                ) { Text("${g.count}", style = Divan.type.micro.copy(fontWeight = FontWeight.Bold), color = c.onGold) }
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Head(n, unread, NotificationGroups.countLine(g))
                RichText(n.titleFa, style = Divan.type.small.copy(fontWeight = if (unread) FontWeight.Bold else FontWeight.SemiBold), color = if (unread) c.textPrimary else c.textSecondary)
                if (n.bodyFa.isNotBlank() && !expanded) RichText(n.bodyFa, style = Divan.type.caption, color = c.textSecondary, maxLines = 2)
                Row(Modifier.padding(top = 2.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    DIcon(DivanIcon.CHEVRON, if (expanded) Modifier.rotate(180f) else Modifier, size = 14.dp, tint = c.textMuted)
                    Text(if (expanded) "بستن" else "هر ${g.count} بار", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.weight(1f))
                    if (unreadTab) HqButton("همه خوانده شد", onRead, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.SEAL)
                }
            }
        }
        AnimatedVisibility(expanded, enter = com.coinepro.hq.designsystem.expandIn(), exit = com.coinepro.hq.designsystem.collapseOut()) {
            Column(Modifier.padding(top = 10.dp)) {
                g.items.forEachIndexed { i, x ->
                    if (i > 0) HorizontalDivider(color = c.lineDivider)
                    Occurrence(x) { onOpen(x) }
                }
            }
        }
    }
}

/** One time the alert was raised: when, its own body line, and its link. */
@Composable
private fun Occurrence(n: Notification, onOpen: () -> Unit) {
    val c = Divan.colors
    val route = Refs.forLink(n.link?.kind, n.link?.ref)
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).then(if (route != null) Modifier.clickable(role = Role.Button, onClick = onOpen) else Modifier).padding(vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        com.coinepro.hq.designsystem.Fig(jTime(n.createdAt), Modifier.width(44.dp), style = Divan.type.figureSmall, color = c.textSecondary)
        Text(ago(n.createdAt), style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f), maxLines = 1)
        if (n.readAt == null) Box(Modifier.size(6.dp).clip(CircleShape).background(c.goldFill))
        n.link?.ref?.let { com.coinepro.hq.designsystem.Fig(it, style = Divan.type.figureSmall, color = if (route != null) c.goldInk else c.textMuted) }
        if (route != null) DIcon(DivanIcon.NEXT, size = 14.dp, tint = c.textMuted)
    }
}
