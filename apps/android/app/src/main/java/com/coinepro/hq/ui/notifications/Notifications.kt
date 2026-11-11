package com.coinepro.hq.ui.notifications

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.border
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.data.LEVEL3_FA
import com.coinepro.hq.core.data.LEVELS3
import com.coinepro.hq.core.data.asksOwner
import com.coinepro.hq.core.data.dayLabelFa
import com.coinepro.hq.core.data.humanize
import com.coinepro.hq.core.data.level3
import com.coinepro.hq.core.net.Decision
import com.coinepro.hq.designsystem.facts
import com.coinepro.hq.designsystem.settle
import com.coinepro.hq.designsystem.stagger
import com.coinepro.hq.ui.look.goldEdge
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
import com.coinepro.hq.designsystem.Text
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
import com.coinepro.hq.core.net.gated
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

/**
 * Notifications (contract §6, §25), ⟨1.0.1⟩ rebuilt (part C, C3.5): three levels only («فوری» red, «تصمیم» gold, «خبر» silent: the
 * hub's report, info and learning together), one filter bar, and one list. On top, fixed, «از تو کاری میخواهد»: what is urgent or a
 * decision and not answered yet, each with its own action right there («تأیید», «ببین», the ready answers) and its deadline as a ring
 * that empties. Then everything else by day («امروز», «دیروز», the date). A row is compact: the level's sign, the title, one line,
 * the time; unread is a thin gold line at its edge and nothing else. A swipe is «خوانده شد», with a drawn tick and a light haptic,
 * and a few seconds to take it back. The same alert raised again and again is one row with its count. A title the machine wrote is
 * said in Persian; its raw text is one tap away. A long press chooses rows (read, or deleted for good where the hub has it).
 */
@Composable
fun NotificationsScreen(level0: String? = null, open0: Set<String> = emptySet(), selectAll0: Boolean = false) {
    // [level0]: the filter it opens on (`urgent` · `decision` · `news`); [open0]: the rows shown open at first ("*": every one; the screenshots).
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val act = com.coinepro.hq.ui.activity()
    val scope = androidx.compose.runtime.rememberCoroutineScope()
    var filter by rememberSaveable { mutableStateOf(level0) }
    val unreadQ = rememberQuery("notifications:unread:all", "notifications") { notifications(unread = true, level = null, limit = 200) }
    val readQ = rememberQuery("notifications:read:all", "notifications") { notifications(unread = false, level = null, limit = 100) }
    val r = refresher(unreadQ, readQ)
    val marked by env.reads.marked.collectAsStateWithLifecycle()
    var undo by remember { mutableStateOf<Undo?>(null) }
    val open = remember { mutableStateListOf<String>().apply { addAll(open0) } }
    val more = remember { mutableStateListOf<Notification>() }
    var cursor by remember(readQ.data) { mutableStateOf(readQ.data?.nextCursor) }
    var loadingMore by remember { mutableStateOf(false) }
    val companies = com.coinepro.hq.ui.rememberCompanies()
    val nameOf = remember(companies) { { code: String -> companies.firstOrNull { it.code == code }?.nameFa } }

    // What waits for its grace time is sent when the owner leaves; a refused send is said in Persian.
    DisposableEffect(env) { onDispose { env.reads.flush() } }
    LaunchedEffect(env) { env.reads.failures.collect { toasts.error(it) } }
    LaunchedEffect(readQ.data) { readQ.data?.items?.filter { it.readAt != null }?.map { it.id }?.let(env.reads::confirmed) }

    // ⟨1.10.1⟩ §28.5 selection: a long press on a row (a folded row stands for all its times), «انتخاب همه», then «خوانده‌شده» or
    // «حذف». Deleting is for good; a hub without it (404/405) hides «حذف».
    var sel by remember { mutableStateOf(com.coinepro.hq.core.data.Selection()) }
    var deleting by remember { mutableStateOf<List<NotificationGroup>?>(null) }
    val gone = remember { mutableStateListOf<String>() }
    val gaps by env.api.gaps.missing.collectAsStateWithLifecycle()
    val canDelete = com.coinepro.hq.core.net.HubFeature.DELETE_NOTIFICATIONS !in gaps
    val haptics = com.coinepro.hq.designsystem.rememberHaptics()
    LaunchedEffect(filter) { sel = sel.exit() }
    androidx.activity.compose.BackHandler(sel.active) { sel = sel.exit() }
    fun keyOf(g: NotificationGroup) = g.key + ":" + g.latest.id
    fun select(next: com.coinepro.hq.core.data.Selection) {
        if (next != sel) haptics.tick()
        if (next.active && !sel.active) undo = null
        sel = next
    }

    // ⟨1.16⟩ §34.4 only what is the owner's: owner-visible, and nothing technical unless it is critical.
    val loaded = unreadQ.data?.items?.filter { com.coinepro.hq.core.data.forOwner(it) }
    val (unread0, read0) = NotificationGroups.split(loaded.orEmpty(), (readQ.data?.items.orEmpty() + more).filter { com.coinepro.hq.core.data.forOwner(it) }, marked)
    fun shown(n: Notification) = n.id !in gone && (filter == null || level3(n.level) == filter)
    val unread = unread0.filter(::shown)
    val read = read0.filter(::shown)
    // «از تو کاری میخواهد» stays on top whatever the day; the rest, unread and read together, by day.
    val asking = NotificationGroups.group(unread.filter(::asksOwner))
    val rest = NotificationGroups.group(unread.filterNot(::asksOwner) + read)
    val days = remember(rest) {
        val out = mutableListOf<Pair<String, MutableList<NotificationGroup>>>()
        for (g in rest) {
            val label = dayLabelFa(g.latest.createdAt)
            if (out.lastOrNull()?.first == label) out.last().second += g else out += label to mutableListOf(g)
        }
        out
    }
    val groups = asking + rest
    val keys = groups.map(::keyOf)
    var autoSelected by remember { mutableStateOf(false) }
    LaunchedEffect(keys) {
        // [selectAll0]: the screenshots open with every row selected.
        sel = if (selectAll0 && !autoSelected && keys.isNotEmpty()) { autoSelected = true; sel.all(keys) } else sel.retain(keys)
    }

    // The cards the decision rows speak of: «تأیید» in place needs the card itself (its kind, whether the hub asks for the passkey).
    val wantsCards = asking.any { it.latest.link?.kind == "decision" }
    val cards = if (wantsCards) rememberQuery("decisions:pending", "decisions") { decisions("pending") } else null
    fun cardOf(n: Notification): Decision? = if (n.link?.kind == "decision") cards?.data?.items?.firstOrNull { it.ref == n.link?.ref } else null
    val leadKey = asking.firstOrNull { g -> cardOf(g.latest)?.let { it.kind !in OWN_PAGE } == true }?.let(::keyOf)

    fun markRead(g: NotificationGroup) {
        val ids = g.ids.filter { it !in marked && unread0.any { n -> n.id == it } }
        if (ids.isEmpty()) return
        haptics.tick()
        val token = env.reads.mark(ids)
        undo = Undo(token, ids, true, if (g.folded) "${ids.size} اعلان خوانده شد" else "خوانده شد")
    }

    fun openOne(n: Notification) {
        if (n.readAt == null) env.reads.open(n.id)
        val route = Refs.forLink(n.link?.kind, n.link?.ref)
        if (route != null) nav.go(route)
    }

    /** «تأیید» on a decision's row: one tap (the passkey only where the hub's rule asks for it), and the row is read. */
    fun approve(n: Notification, d: Decision, busy: (Boolean) -> Unit) {
        busy(true)
        scope.launch {
            try {
                val token = if (com.coinepro.hq.ui.cartable.needsStepUp(d)) env.auth.stepUp(act, com.coinepro.hq.core.net.sealAction(d), com.coinepro.hq.core.net.sealTarget(d)) else null
                env.api.approve(d.ref, null, token)
                haptics.seal()
                env.reads.open(n.id)
                toasts.ok("تأیید شد.")
                env.cache.invalidate("decisions", "inbox", "office")
            } catch (e: ApiException) {
                haptics.error()
                toasts.error(e.messageFa)
            } catch (e: kotlin.coroutines.cancellation.CancellationException) {
                throw e
            } catch (e: Exception) {
                // A passkey the owner cancelled, or a state the phone refused: said, never a crash.
                haptics.error()
                toasts.error("این کار انجام نشد؛ دوباره امتحان کن.")
            } finally {
                busy(false)
            }
        }
    }

    @Composable
    fun RowOf(g: NotificationGroup, index: Int, ask: Boolean) {
        val k = keyOf(g)
        val isUnread = g.items.any { it.readAt == null }
        val longPress: (() -> Unit)? = if (isUnread || canDelete) ({ select(sel.start(k)) }) else null
        val expanded = g.key in open || "*" in open
        val card = if (ask) cardOf(g.latest) else null
        val row: @Composable () -> Unit = {
            NotificationRow(
                g, index, ask = ask, lead = ask && k == leadKey, expanded = expanded, nameOf = nameOf, decision = card,
                onToggle = { if (g.key in open) open.remove(g.key) else open.add(g.key) }, onOpen = ::openOne, onLongClick = longPress,
                onApprove = { d, busy -> approve(g.latest, d, busy) },
                onAnswer = { n, choice -> scope.launch { try { env.api.answer(n.id, choice); haptics.tick(); env.cache.invalidate("notifications", "inbox") } catch (e: ApiException) { toasts.error(e.messageFa) } } },
            )
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            AnimatedVisibility(sel.active, enter = com.coinepro.hq.designsystem.expandIn(), exit = com.coinepro.hq.designsystem.collapseOut()) {
                Box(Modifier.padding(end = 10.dp)) { com.coinepro.hq.ui.outputs.SelectCheck(k in sel) }
            }
            Box(Modifier.weight(1f)) {
                if (isUnread && !sel.active) SwipeRead(onRead = { markRead(g) }) { row() } else row()
                // In selection mode a tap anywhere on the row selects it (a folded row: all its times).
                if (sel.active) Box(Modifier.matchParentSize().clickable(role = Role.Checkbox, onClickLabel = if (k in sel) "برداشتن از انتخاب" else "انتخاب") { select(sel.toggle(k)) })
            }
        }
    }

    androidx.compose.foundation.layout.Box(Modifier.fillMaxSize()) {
        Page(onRefresh = r::refresh, refreshing = r.refreshing) {
            item(key = "head") {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    PageHeader("اعلان‌ها")
                    // One bar: «همه | فوری | تصمیم | خبر».
                    Segmented(
                        listOf(SegOption<String?>(null, "همه")) + LEVELS3.map { SegOption<String?>(it, LEVEL3_FA.getValue(it)) },
                        filter, { filter = it }, Modifier.fillMaxWidth(),
                    )
                }
            }
            when {
                unreadQ.data == null && readQ.data == null && unreadQ.error == null && readQ.error == null -> items(5, key = { "sk-$it" }) { Skeleton(Modifier.fillMaxWidth().height(68.dp), radius = 12.dp) }
                unreadQ.data == null && readQ.data == null -> item(key = "error") { ErrorBlock(unreadQ.error ?: readQ.error, { r.refresh() }) }
                groups.isEmpty() -> item(key = "empty") {
                    Empty(if (filter == null) "اعلانی نیست" else "اعلان «${LEVEL3_FA[filter]}» نیست", icon = DivanIcon.BELL, body = "هر چه تازه برسد همین‌جا میاید.")
                }
                else -> {
                    item(key = "status") {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            val n = NotificationGroups.group(unread).size
                            Text(if (n > 0) "${com.coinepro.hq.core.data.faNum(n)} خوانده‌نشده" else "همه را خوانده‌ای", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.weight(1f))
                            if (unread.isNotEmpty() && !sel.active) HqButton("همه خوانده شد", {
                                val ids = unread.map { it.id }
                                haptics.tick()
                                // Everything on show, up to the newest the owner sees: what arrives meanwhile stays unread. One level's rows go by their ids.
                                val token = if (filter == null) env.reads.mark(ids, unread.maxOf { it.createdAt } to null) else env.reads.mark(ids)
                                undo = Undo(token, ids, true, "${ids.size} اعلان خوانده شد")
                            }, size = BtnSize.SM, variant = BtnVariant.TEXT)
                        }
                    }
                    if (asking.isNotEmpty()) {
                        item(key = "asks-title") {
                            Row(Modifier.padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Box(Modifier.size(6.dp).clip(CircleShape).background(c.goldInk))
                                Text("از تو کاری میخواهد", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, modifier = Modifier.semantics { heading() })
                            }
                        }
                        itemsIndexed(asking, key = { _, g -> "ask:" + g.key + ":" + g.latest.id }) { i, g -> Box(itemMotion()) { RowOf(g, i, ask = true) } }
                    }
                    for ((label, list) in days) {
                        item(key = "day:$label") { Text(label, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted, modifier = Modifier.padding(start = 4.dp, end = 4.dp, top = 4.dp).semantics { heading() }) }
                        itemsIndexed(list, key = { _, g -> g.key + ":" + g.latest.id }) { i, g -> Box(itemMotion()) { RowOf(g, i, ask = false) } }
                    }
                    if (sel.active) item(key = "sel-room") { Box(Modifier.height(64.dp)) }
                    if (cursor != null) item(key = "more") {
                        HqButton("بیشتر", {
                            if (!loadingMore) scope.launch {
                                loadingMore = true
                                try {
                                    val page = env.api.notifications(unread = false, level = null, limit = 100, cursor = cursor)
                                    more.addAll(page.items.filter { n -> read0.none { it.id == n.id } })
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
        com.coinepro.hq.ui.outputs.SelectionTop(
            sel, sel.allOf(keys), Modifier.align(Alignment.TopCenter), onClose = { select(sel.exit()) },
            onAll = { select(if (sel.allOf(keys)) sel.none() else sel.all(keys)) }, allLabel = "انتخاب همه",
        )
        val chosen = groups.filter { keyOf(it) in sel }
        val chosenUnread = chosen.flatMap { it.ids }.filter { id -> unread0.any { it.id == id } && id !in marked }
        NotificationActions(
            sel.active, chosen.isNotEmpty(), chosenUnread.isNotEmpty(), canDelete, Modifier.align(Alignment.BottomCenter),
            onRead = {
                sel = sel.exit()
                if (chosenUnread.isNotEmpty()) {
                    val token = env.reads.mark(chosenUnread)
                    undo = Undo(token, chosenUnread, true, "${chosenUnread.size} اعلان خوانده شد")
                }
            },
            onDelete = { deleting = chosen },
        )
    }
    deleting?.let { ds ->
        val n = ds.sumOf { it.count }
        com.coinepro.hq.ui.v14.HqSheet({ deleting = null }, "حذف $n اعلان") {
            DeleteNotificationsContent(
                n, false,
                onCancel = { deleting = null },
                delete = {
                    val ids = ds.flatMap { it.ids }
                    val out = env.api.gated(com.coinepro.hq.core.net.HubFeature.DELETE_NOTIFICATIONS) { deleteNotifications(ids) }
                    deleting = null
                    sel = sel.exit()
                    if (out != null) {
                        gone.addAll(ids)
                        env.cache.invalidate("notifications", "inbox")
                        haptics.confirm()
                        toasts.ok("${out.deleted} اعلان برای همیشه پاک شد.")
                    }
                },
            )
        }
    }
}

/** Kinds sealed on their own page against a digest: the row leads there instead of approving in place. */
private val OWN_PAGE = setOf("server_plan", "media_series", "server_destructive")

/** A swipe along the row is «خوانده شد»: the row follows the finger, a tick draws itself behind it once it is far enough, and past the
 *  threshold it is read (the caller ticks the haptic and offers «برگردان»). */
@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
private fun SwipeRead(onRead: () -> Unit, content: @Composable () -> Unit) {
    val c = Divan.colors
    val state = androidx.compose.material3.rememberSwipeToDismissBoxState()
    androidx.compose.material3.SwipeToDismissBox(
        state,
        backgroundContent = {
            val toStart = state.dismissDirection == androidx.compose.material3.SwipeToDismissBoxValue.EndToStart
            val past = state.targetValue != androidx.compose.material3.SwipeToDismissBoxValue.Settled
            Row(
                Modifier.fillMaxSize().clip(RoundedCornerShape(12.dp)).background(if (past) c.softPositive else c.tile).padding(horizontal = 20.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = if (toStart) Arrangement.End else Arrangement.Start,
            ) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    if (past) com.coinepro.hq.designsystem.DrawnMark(true, c.positive, size = 16.dp)
                    Text("خوانده شد", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = if (past) c.positive else c.textMuted)
                }
            }
        },
        onDismiss = { onRead() },
    ) { content() }
}

/** Selection mode's actions: «خوانده‌شده» on the unread tab, and «حذف» on both (while the hub has it). */
@Composable
private fun NotificationActions(active: Boolean, some: Boolean, unreadTab: Boolean, canDelete: Boolean, modifier: Modifier, onRead: () -> Unit, onDelete: () -> Unit) {
    val c = Divan.colors
    val reduced = com.coinepro.hq.designsystem.LocalReducedMotion.current
    AnimatedVisibility(
        active, modifier,
        enter = if (reduced) androidx.compose.animation.EnterTransition.None else androidx.compose.animation.fadeIn(com.coinepro.hq.designsystem.Motion.emphasised()) + androidx.compose.animation.slideInVertically(com.coinepro.hq.designsystem.Motion.emphasised()) { it },
        exit = if (reduced) androidx.compose.animation.ExitTransition.None else androidx.compose.animation.fadeOut(com.coinepro.hq.designsystem.Motion.exit()) + androidx.compose.animation.slideOutVertically(com.coinepro.hq.designsystem.Motion.exit()) { it },
    ) {
        Row(
            Modifier.padding(12.dp).fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(c.raised).padding(8.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically,
        ) {
            if (unreadTab) HqButton("خوانده‌شده", onRead, Modifier.weight(1f), variant = BtnVariant.SECONDARY, size = BtnSize.SM, enabled = some)
            if (canDelete) HqButton("حذف", onDelete, Modifier.weight(1f), variant = BtnVariant.DANGER, size = BtnSize.SM, enabled = some)
        }
    }
}

/** «حذف»'s confirmation: what goes, said plainly; no Audit line is needed (a notification copies an event kept elsewhere). */
@Composable
internal fun DeleteNotificationsContent(n: Int, all: Boolean, onCancel: () -> Unit, delete: suspend () -> Unit) {
    val c = Divan.colors
    val action = rememberAction()
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text("از دیتابیس پاک میشود و برنمیگردد.", style = Divan.type.bodyStrong, color = c.textPrimary)
        Text(
            if (all) "همه‌ی اعلان‌های خوانده‌شده تا همین لحظه پاک میشوند، حتی آن‌هایی که هنوز در فهرست بارگذاری نشده‌اند."
            else "$n اعلان پاک میشود. خود رویدادها (کارت‌ها، کارها، یافته‌ها) سر جایشان میمانند؛ فقط اعلانشان میرود.",
            style = Divan.type.small, color = c.textSecondary,
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            HqButton("حذف برای همیشه", { action.run { delete() } }, Modifier.weight(1f), variant = BtnVariant.DANGER, icon = DivanIcon.CLOSE, loading = action.busy)
            HqButton("انصراف", onCancel, Modifier.weight(1f), variant = BtnVariant.GHOST)
        }
    }
}

/** The level's sign: a shape and its word (for a reader), with the count of a folded row. Red for urgent, a thin gold ring for a
 *  decision, quiet for news. */
@Composable
private fun LevelSign(level: String, count: Int) {
    val c = Divan.colors
    val (icon, ink) = when (level) {
        "urgent" -> DivanIcon.URGENT to c.negative
        "decision" -> DivanIcon.LEVEL_DECISION to c.goldInk
        else -> DivanIcon.INFO to c.textMuted
    }
    Box {
        Box(
            Modifier.size(32.dp).clip(CircleShape)
                .then(when (level) { "urgent" -> Modifier.background(c.softNegative); "decision" -> Modifier.border(1.dp, c.lineTahrir, CircleShape); else -> Modifier.background(c.tile) }),
            contentAlignment = Alignment.Center,
        ) { DIcon(icon, size = 16.dp, tint = ink, label = LEVEL3_FA[level]) }
        if (count > 1) Box(
            Modifier.align(Alignment.BottomStart).offset(x = (-4).dp, y = 4.dp).size(16.dp).clip(CircleShape).background(c.raised),
            contentAlignment = Alignment.Center,
        ) { Text(com.coinepro.hq.core.data.faNum(count), style = Divan.type.micro.copy(fontSize = 10.sp, lineHeight = 14.sp, fontWeight = FontWeight.Bold), color = c.textPrimary) }
    }
}

/** A deadline as a ring that empties, with how long is left in words. */
@Composable
private fun Deadline(from: String, to: String) {
    val c = Divan.colors
    val now = com.coinepro.hq.ui.live.rememberTicker(30_000)
    val t0 = com.coinepro.hq.core.format.instant(from)?.toEpochMilli()
    val t1 = com.coinepro.hq.core.format.instant(to)?.toEpochMilli() ?: return
    val total = if (t0 != null) t1 - t0 else 0L
    val share = if (total > 0) ((t1 - now).toFloat() / total).coerceIn(0f, 1f) else 0f
    val words = com.coinepro.hq.core.format.until(to, now)
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        com.coinepro.hq.designsystem.Ring(share, size = 18.dp, stroke = 2.5.dp, tone = when { share < 0.2f -> com.coinepro.hq.designsystem.RingTone.NEG; share < 0.5f -> com.coinepro.hq.designsystem.RingTone.WARN; else -> com.coinepro.hq.designsystem.RingTone.SILVER }, label = "مهلت: $words")
        Text(words, style = Divan.type.micro, color = c.textSecondary, maxLines = 1)
    }
}

/**
 * One row: the sign, the title, one line, the time. In «از تو کاری میخواهد» ([ask]) it sits on a card and carries its own action and
 * its deadline; [lead]: its «تأیید» is the page's one full gold. Unread: a thin gold line at its start edge, nothing else.
 */
@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class, androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun NotificationRow(
    g: NotificationGroup, index: Int, ask: Boolean, lead: Boolean, expanded: Boolean, nameOf: (String) -> String?, decision: Decision?,
    onToggle: () -> Unit, onOpen: (Notification) -> Unit, onLongClick: (() -> Unit)?, onApprove: (Decision, (Boolean) -> Unit) -> Unit, onAnswer: (Notification, String) -> Unit,
) {
    val c = Divan.colors
    val n = g.latest
    val lv = level3(n.level)
    val unread = g.items.any { it.readAt == null }
    val route = Refs.forLink(n.link?.kind, n.link?.ref)
    val said = remember(n.titleFa, n.bodyFa, nameOf) { humanize(n.titleFa, nameOf) to humanize(n.bodyFa, nameOf) }
    // The owner never reads a ref (§34.4): it goes from the row (the page it opens knows it).
    val title = remember(said) { com.coinepro.hq.core.format.withoutCodes(said.first).ifBlank { said.first } }
    val body = remember(said) { com.coinepro.hq.core.format.withoutCodes(com.coinepro.hq.core.format.plainOfMd(said.second).replace('\n', ' ')) }
    // The raw text is offered only when the machine's own words were said otherwise (a dropped ref alone is not that).
    val raw = if (said.first != n.titleFa || said.second != n.bodyFa) listOf(n.titleFa, n.bodyFa).filter { it.isNotBlank() }.joinToString(" — ") else null
    val choices = n.choices.orEmpty()
    var busy by remember { mutableStateOf(false) }
    val canApprove = decision != null && decision.kind !in OWN_PAGE
    // A tap opens what it is about; a row with nothing to open (or a folded one) opens itself.
    val tap = { if (g.folded || route == null) onToggle() else onOpen(n) }
    val wide = expanded || ask
    Row(
        Modifier.fillMaxWidth().stagger(index).clip(RoundedCornerShape(12.dp)).background(if (ask) c.card else c.page)
            .then(if (unread) Modifier.goldEdge(c.goldInk) else Modifier)
            .combinedClickable(role = Role.Button, onClickLabel = if (g.folded || route == null) (if (expanded) "بستن" else "باز کن") else "باز کن", onLongClickLabel = "انتخاب چندتایی", onLongClick = onLongClick, onClick = tap)
            .padding(horizontal = 12.dp, vertical = 10.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        LevelSign(lv, g.count)
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                RichText(title, Modifier.weight(1f), style = Divan.type.small.copy(fontWeight = if (unread) FontWeight.SemiBold else FontWeight.Normal), color = if (unread) c.textPrimary else c.textSecondary, maxLines = if (wide) 3 else 1)
                Text(ago(n.createdAt), style = Divan.type.micro, color = c.textMuted, maxLines = 1, modifier = Modifier.padding(top = 3.dp))
            }
            Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Box(Modifier.padding(top = 3.dp)) {
                    if (com.coinepro.hq.ui.rememberCompanies().firstOrNull { it.code == n.company }?.kind == "holding") com.coinepro.hq.designsystem.Monogram(11.dp, ink = c.textMuted)
                    else CompanyMark(n.company, height = 10.dp, mono = true, ink = c.textMuted)
                }
                Text(
                    remember(g, body) { facts(NotificationGroups.category(n), if (g.folded) "${com.coinepro.hq.core.data.faNum(g.count)} بار" else null, body.trim().trimStart('،', '؛', ' ').ifBlank { null }) },
                    Modifier.weight(1f), style = Divan.type.caption, color = c.textMuted, maxLines = if (wide) 4 else 1, overflow = TextOverflow.Ellipsis,
                )
            }
            if (choices.isNotEmpty()) FlowRow(Modifier.padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                for (ch in choices) {
                    val chosen = n.answer == ch.id
                    val shape = RoundedCornerShape(16.dp)
                    Text(
                        ch.labelFa, style = Divan.type.small.copy(fontWeight = if (chosen) FontWeight.SemiBold else FontWeight.Normal), color = if (chosen) c.textPrimary else c.textSecondary,
                        modifier = Modifier.clip(shape).background(if (chosen) c.raised else c.page).border(1.dp, if (chosen) com.coinepro.hq.designsystem.silverLine() else c.lineStrong, shape)
                            .clickable(enabled = n.answer == null, role = Role.Button) { onAnswer(n, ch.id) }
                            .padding(horizontal = 12.dp, vertical = 6.dp),
                    )
                }
            }
            if (ask && choices.isEmpty()) Row(Modifier.padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (canApprove) HqButton(
                    "تأیید", { decision?.let { d -> onApprove(d) { busy = it } } }, variant = if (lead) BtnVariant.PRIMARY else BtnVariant.SECONDARY, size = BtnSize.SM,
                    icon = if (decision != null && com.coinepro.hq.ui.cartable.needsStepUp(decision)) DivanIcon.SEAL else null, loading = busy,
                )
                if (route != null) HqButton("ببین", { onOpen(n) }, variant = if (canApprove) BtnVariant.GHOST else BtnVariant.SECONDARY, size = BtnSize.SM)
                Box(Modifier.weight(1f))
                decision?.expiresAt?.let { Deadline(decision.createdAt, it) }
            }
            if (expanded) Column(Modifier.padding(top = 6.dp).settle(row = true), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                if (g.folded) Column {
                    g.items.forEachIndexed { i, x ->
                        if (i > 0) HorizontalDivider(color = c.lineDivider)
                        Occurrence(x) { onOpen(x) }
                    }
                }
                raw?.let { com.coinepro.hq.designsystem.TechDetails(it, title = "متن خام", open0 = false) }
            }
        }
    }
}

/** One time the alert was raised: when (the clock, Latin), how long ago, and its own page. */
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
        if (route != null) Text("ببین", style = Divan.type.caption, color = c.silverInk)
    }
}
