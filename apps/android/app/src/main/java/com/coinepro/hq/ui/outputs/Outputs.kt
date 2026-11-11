package com.coinepro.hq.ui.outputs

import com.coinepro.hq.ui.itemMotion
import android.icu.util.Calendar
import android.icu.util.TimeZone
import android.icu.util.ULocale
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.SwipeToDismissBox
import androidx.compose.material3.SwipeToDismissBoxValue
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.continuity
import androidx.compose.material3.rememberSwipeToDismissBoxState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.layout.heightIn
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.data.faceOf
import com.coinepro.hq.core.data.goesOut
import com.coinepro.hq.core.data.isVideo
import com.coinepro.hq.core.data.leadFile
import com.coinepro.hq.core.data.summaryIsNew
import com.coinepro.hq.core.data.usageOf
import com.coinepro.hq.designsystem.DecisionBar
import com.coinepro.hq.designsystem.facts
import com.coinepro.hq.ui.look.FaceFrame
import com.coinepro.hq.ui.look.FileFace
import com.coinepro.hq.ui.look.FilesStrip
import com.coinepro.hq.ui.look.HeroMedia
import com.coinepro.hq.ui.look.HeroPlayer
import com.coinepro.hq.ui.look.goldEdge
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.coinepro.hq.core.Env
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.OWNER_TZ
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.format.jWeekday
import com.coinepro.hq.core.format.ownerDay
import com.coinepro.hq.core.format.tokens
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.Deliverable
import com.coinepro.hq.core.net.DeliverableQuery
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.RatingRow
import com.coinepro.hq.designsystem.RichText
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.Toasts
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v16.ChipRow
import com.coinepro.hq.ui.v17.RefChip
import java.time.LocalDate
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

// Outputs (contract §5.2, ⟨1.7.3⟩): what the agents and the hub's own reporting delivered. The owner reads one and marks it seen (a swipe,
// the button on its page, or all at once): it leaves «تازه» for «خوانده‌شده», so agents and the digital chief keep learning from it, search
// and the archive still find it, and it can be filed in the archive to be cited later. The rating stays separate.
// ⟨1.10⟩ §28.1: so they never pile up, a long press opens selection mode (a check beside every row, «۳ انتخاب‌شده» on top, all or none):
// file several in the archive, mark them seen, or delete them for good — the owner only, with the passkey on the SHA-256 of the sorted
// refs; only an Audit line stays, and archive records they were filed into stay. Back leaves the mode. The same on one output's ⋮.

/** The date ranges of the filter, in the owner's zone. */
private val RANGES = listOf("all" to "همه‌ی زمان‌ها", "today" to "امروز", "yesterday" to "دیروز", "7d" to "۷ روز اخیر", "30d" to "۳۰ روز اخیر", "month" to "این ماه")
private val CATEGORY_FA = mapOf("report" to "گزارش", "work" to "کار")

/** `from`/`to` (YYYY-MM-DD in the owner's zone) of a range; "this month" is the Jalali month. */
private fun span(range: String): Pair<String?, String?> {
    val today = HqClock.today()
    return when (range) {
        "today" -> today.toString() to today.toString()
        "yesterday" -> today.minusDays(1).toString() to today.minusDays(1).toString()
        "7d" -> today.minusDays(6).toString() to today.toString()
        "30d" -> today.minusDays(29).toString() to today.toString()
        "month" -> {
            val cal = Calendar.getInstance(TimeZone.getTimeZone(OWNER_TZ), ULocale("fa_IR@calendar=persian")).apply { timeInMillis = HqClock.millis() }
            today.minusDays((cal.get(Calendar.DAY_OF_MONTH) - 1).toLong()).toString() to today.toString()
        }
        else -> null to null
    }
}

/** A day's header: «امروز، ۲۵ مهر», «دیروز، ۲۴ مهر», otherwise the weekday and date (the year when it is another year). */
private fun dayFa(day: String): String {
    val today = HqClock.today()
    val d = runCatching { LocalDate.parse(day) }.getOrNull() ?: return day
    return when (d) {
        today -> "امروز، ${jDate(day)}"
        today.minusDays(1) -> "دیروز، ${jDate(day)}"
        else -> if (jDate(day, withYear = true).takeLast(4) == jDate(today.toString(), withYear = true).takeLast(4)) jWeekday(day) else "${jWeekday(day)} ${jDate(day, withYear = true).takeLast(4)}"
    }
}

/**
 * ⟨1.7.3⟩ Marks [refs] seen (or unseen again) on the hub. A hub before ⟨1.7.3⟩ answers 404 (or 405): the phone keeps it then, and says
 * once, quietly, that it syncs when the hub is updated. Returns false when only the phone keeps it.
 */
suspend fun markSeen(env: Env, toasts: Toasts, refs: List<String>, seen: Boolean = true): Boolean {
    if (refs.isEmpty()) return true
    return try {
        env.api.markSeen(refs, seen)
        env.seen.forget(refs)
        true
    } catch (e: ApiException) {
        if (e.status != 404 && e.status != 405) throw e
        e.logged?.let { env.api.failures?.forget(it) }
        env.seen.mark(refs, seen)
        if (!env.seen.told) {
            env.seen.told = true
            toasts.info("«خوانده‌شده» فعلاً روی همین گوشی نگه داشته میشود؛ با به‌روزرسانی هاب همگام میشود.")
        }
        false
    } finally {
        env.cache.invalidate("deliverables", "inbox")
    }
}

/** An undo the owner has a few seconds for: what was marked and how. */
internal data class Undo(val id: Long, val refs: List<String>, val seen: Boolean, val text: String)

/**
 * Outputs: «تازه», «خوانده‌شده» and «همه», with the unrated filter, category, company, producer, date range and search, by day.
 * ⟨1.0.1⟩ Part C (C3.3): each output is a media card (its poster when it carries a video or a picture; a new one with the thin gold
 * edge, «بی‌امتیاز» a silver dot), and the header with its tabs, search and filters folds into one bar as the list scrolls (M18).
 */
@Composable
fun OutputsScreen(tab0: String = "new", filters0: Boolean = false, select0: Set<String> = emptySet()) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val scope = rememberCoroutineScope()
    val companies = rememberCompanies()
    var tab by rememberSaveable { mutableStateOf(tab0) }
    var unrated by rememberSaveable { mutableStateOf(false) }
    var category by rememberSaveable { mutableStateOf<String?>(null) }
    var company by rememberSaveable { mutableStateOf<String?>(null) }
    var producer by rememberSaveable { mutableStateOf<String?>(null) }
    var range by rememberSaveable { mutableStateOf("all") }
    var search by rememberSaveable { mutableStateOf("") }
    var applied by rememberSaveable { mutableStateOf("") }
    var filters by remember { mutableStateOf(filters0) }
    LaunchedEffect(search) { delay(350); applied = search }
    val (from, to) = span(range)
    val query = DeliverableQuery(
        seen = when (tab) { "new" -> false; "seen" -> true; else -> null },
        category = category, unrated = unrated, company = company, producer = producer, text = applied.ifBlank { null }, from = from, to = to,
    )
    val q = rememberQuery("deliverables:${query.key}", "deliverables") { deliverables(query, limit = 100) }
    val inbox = rememberQuery("inbox", "inbox", maxAgeMs = 30_000) { inbox() }
    val r = refresher(q, inbox)
    val local by env.seen.refs.collectAsStateWithLifecycle()
    // Marked a moment ago, before the next answer confirms it: ref → seen.
    val optimistic = remember { mutableStateMapOf<String, Boolean>() }
    val more = remember(query.key) { mutableStateListOf<Deliverable>() }
    var cursor by remember(query.key) { mutableStateOf<String?>(null) }
    var loadingMore by remember { mutableStateOf(false) }
    var undo by remember { mutableStateOf<Undo?>(null) }
    // ⟨1.10⟩ §28.1 selection mode, what the owner deleted a moment ago (hidden before the next answer), and the delete's sheet.
    var sel by remember { mutableStateOf(com.coinepro.hq.core.data.Selection(select0, select0.isNotEmpty())) }
    val gone = remember { mutableStateListOf<String>() }
    var deleting by remember { mutableStateOf<List<Deliverable>?>(null) }
    var bulk by remember { mutableStateOf<String?>(null) }
    val gaps by env.api.gaps.missing.collectAsStateWithLifecycle()
    androidx.activity.compose.BackHandler(sel.active) { sel = sel.exit() }
    LaunchedEffect(q.data) {
        optimistic.clear()
        cursor = q.data?.nextCursor
        more.clear()
    }
    // A hub that now keeps «seen» gets what the phone kept meanwhile, in one call.
    LaunchedEffect(q.data, local) {
        val items = q.data?.items ?: return@LaunchedEffect
        if (local.isNotEmpty() && items.any { it.hubKnowsSeen }) runCatching {
            env.api.markSeen(local.keys.toList(), true)
            env.seen.forget(local.keys)
            env.cache.invalidate("deliverables", "inbox")
        }
    }

    fun seenAt(d: Deliverable): String? = when (optimistic[d.ref]) {
        true -> d.seenAt ?: local[d.ref] ?: HqClock.now().toString()
        false -> null
        null -> d.seenAt ?: local[d.ref]
    }

    val haptics = com.coinepro.hq.designsystem.rememberHaptics()
    fun mark(refs: List<String>, seen: Boolean, text: String) {
        if (refs.isEmpty()) return
        // A light tick: marked seen (or new again), at once; the hub follows.
        haptics.tick()
        refs.forEach { optimistic[it] = seen }
        val u = Undo(System.nanoTime(), refs, seen, text)
        undo = u
        scope.launch {
            try { markSeen(env, toasts, refs, seen) } catch (e: ApiException) {
                refs.forEach { optimistic.remove(it) }
                if (undo == u) undo = null
                toasts.error(e.messageFa)
            }
        }
    }

    val loaded = (q.data?.items.orEmpty() + more).filter { it.ref !in gone }
    val list = loaded.filter { query.matches(it, seenAt(it)) }
    val visible = list.map { it.ref }
    LaunchedEffect(visible) { if (q.data != null) sel = sel.retain(visible) }

    fun select(next: com.coinepro.hq.core.data.Selection) {
        if (next.active && !sel.active) undo = null
        if (next != sel) haptics.tick()
        sel = next
    }

    /** «بایگانی» for the selection: one call (§28.1), or one per output from a hub before ⟨1.10⟩. */
    fun fileSelected() {
        val refs = sel.sorted
        if (refs.isEmpty() || bulk != null) return
        bulk = "file"
        scope.launch {
            try {
                // A hub before ⟨1.10⟩ has no bulk route: each one is filed on its own route instead, quietly.
                val n = env.api.gated(com.coinepro.hq.core.net.HubFeature.BULK_FILE) { fileDeliverables(refs) }?.records?.size
                    ?: refs.count { r -> runCatching { env.api.fileDeliverable(r) }.isSuccess }
                env.cache.invalidate("deliverables", "archive")
                haptics.confirm()
                toasts.ok("$n خروجی در بایگانی ثبت شد؛ پیش‌نویس‌اند تا بایگان کاملشان کند.")
                sel = sel.exit()
            } catch (e: ApiException) {
                haptics.reject()
                toasts.error(e.messageFa)
            } finally { bulk = null }
        }
    }
    val unseenCount = inbox.data?.deliverablesUnseen ?: if (tab == "new" && q.data != null) list.size else null

    val listState = androidx.compose.foundation.lazy.rememberLazyListState()
    val collapse = com.coinepro.hq.designsystem.rememberCollapse(listState)
    val newFa = if (unseenCount != null && unseenCount > 0) "تازه ($unseenCount)" else "تازه"
    val tabFa = when (tab) { "new" -> newFa; "seen" -> "خوانده‌شده"; else -> "همه" }

    Box(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize()) {
            // In selection mode its bar takes the header's place.
            if (sel.active) Box(Modifier.height(52.dp))
            else com.coinepro.hq.designsystem.CollapsingHeader(
                { collapse.value }, Modifier.fillMaxWidth().background(c.page).testTag("outputs-header"),
                line = {
                    Row(Modifier.fillMaxWidth().height(52.dp).padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text("خروجی‌ها", style = Divan.type.bodyStrong, color = c.textPrimary)
                        com.coinepro.hq.designsystem.Sep()
                        Text(tabFa, style = Divan.type.caption, color = c.textSecondary, maxLines = 1, modifier = Modifier.weight(1f))
                        FilterChip("فیلترها", query.active > 0, { filters = true }, count = query.active.takeIf { it > 0 })
                    }
                },
                full = {
                    Column(Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 4.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        PageHeader("خروجی‌ها", eyebrow = "آنچه ایجنت‌ها و گزارش‌های هاب تحویل داده‌اند")
                        // ⟨1.0.1⟩ C2.3 «میز انتشار» lives beside the outputs (nothing on a hub without the desk).
                        com.coinepro.hq.ui.look.OutputsTabs("outputs")
                        Segmented(listOf(SegOption("new", newFa), SegOption("seen", "خوانده‌شده"), SegOption("all", "همه")), tab, { tab = it }, Modifier.fillMaxWidth())
                        HqTextField(search, { search = it }, "جستجو در عنوان و خلاصه", Modifier.fillMaxWidth(), maxLength = 100)
                        ChipRow {
                            FilterChip("فیلترها", query.active > 0, { filters = true }, count = query.active.takeIf { it > 0 })
                            FilterChip("بی‌امتیاز", unrated, { unrated = !unrated })
                            FilterChip("گزارش", category == "report", { category = if (category == "report") null else "report" })
                            FilterChip("کار", category == "work", { category = if (category == "work") null else "work" })
                            company?.let { co -> FilterChip("× ${companyOf(companies, co).nameFa}", true, { company = null }) }
                            producer?.let { p -> FilterChip("× ${loaded.firstOrNull { it.producer.code == p }?.producer?.titleFa ?: p}", true, { producer = null }) }
                            if (range != "all") FilterChip("× ${RANGES.first { it.first == range }.second}", true, { range = "all" })
                        }
                    }
                },
            )
            Box(Modifier.weight(1f)) {
                Page(onRefresh = r::refresh, refreshing = r.refreshing, state = listState) {
                    when {
                        q.data == null && q.error == null -> items(3) { Skeleton(Modifier.fillMaxWidth().height(116.dp), radius = 16.dp) }
                        q.data == null -> item { ErrorBlock(q.error, { q.refresh() }) }
                        list.isEmpty() -> item {
                            when {
                                tab == "new" && query.active == 0 && applied.isBlank() ->
                                    Empty("چیز تازه‌ای نمانده", icon = DivanIcon.SEAL, body = "هر خروجی تازه این‌جا میاید؛ خوانده‌شده‌ها در «خوانده‌شده» میمانند تا خودت بایگانی یا پاکشان کنی.")
                                tab == "seen" && query.active == 0 && applied.isBlank() ->
                                    Empty("هنوز چیزی خوانده‌شده نیست", icon = DivanIcon.DELIVERABLE, body = "خروجی را به چپ یا راست بکش، یا در صفحه‌اش «خوانده شد» را بزن.")
                                else -> Empty("خروجی‌ای با این فیلترها نیست", icon = DivanIcon.FILTER)
                            }
                        }
                        else -> {
                            if (tab == "new") item {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Text("بکش تا خوانده‌شده شود؛ نگه دار تا چندتا را انتخاب کنی", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.weight(1f))
                                    HqButton("همه را خوانده‌شده کن", {
                                        val refs = list.map { it.ref }
                                        mark(refs, true, "${refs.size} خروجی خوانده شد")
                                    }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.SEAL)
                                }
                            }
                            for ((day, rows) in list.groupBy { ownerDay(it.createdAt) }) {
                                item(key = "day:$day") {
                                    Row(Modifier.fillMaxWidth().padding(top = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                        Text(dayFa(day), style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                                        HorizontalDivider(Modifier.weight(1f), color = c.lineDivider)
                                        Text("${rows.size} خروجی", style = Divan.type.micro, color = c.textMuted)
                                    }
                                }
                                items(rows, key = { it.ref }) { d -> Box(itemMotion()) {
                                    val seen = seenAt(d) != null
                                    val companyFa = companyOf(companies, d.company).nameFa
                                    if (sel.active) OutputRow(d, seen, companyFa, selecting = true, selected = d.ref in sel, onLongClick = { select(sel.start(d.ref)) }) { select(sel.toggle(d.ref)) }
                                    else SwipeToSee(seen, onSwipe = { mark(listOf(d.ref), !seen, if (seen) "${d.ref} دوباره تازه شد" else "${d.ref} خوانده شد") }) {
                                        OutputRow(d, seen, companyFa, onLongClick = { select(sel.start(d.ref)) }) { nav.go("outputs/${d.ref}") }
                                    }
                                }}
                            }
                            if (cursor != null) item {
                                HqButton("بیشتر", {
                                    if (!loadingMore) scope.launch {
                                        loadingMore = true
                                        try {
                                            val page = env.api.deliverables(query, cursor = cursor, limit = 100)
                                            more.addAll(page.items.filter { n -> loaded.none { it.ref == n.ref } })
                                            cursor = page.nextCursor
                                        } catch (e: ApiException) { toasts.error(e.messageFa) } finally { loadingMore = false }
                                    }
                                }, Modifier.fillMaxWidth(), variant = BtnVariant.SECONDARY, loading = loadingMore, icon = DivanIcon.NEXT)
                            }
                            // Room under the last row for the selection's actions.
                            if (sel.active) item(key = "sel-room") { Box(Modifier.height(64.dp)) }
                        }
                    }
                }
            }
        }
        UndoBar(undo, Modifier.align(Alignment.BottomCenter), onTimeout = { if (undo?.id == it) undo = null }) { u ->
            undo = null
            u.refs.forEach { optimistic[it] = !u.seen }
            scope.launch {
                try { markSeen(env, toasts, u.refs, !u.seen) } catch (e: ApiException) { toasts.error(e.messageFa) }
            }
        }
        // ⟨1.10⟩ §28.1 selection mode: its bar on top, its actions at the bottom.
        SelectionTop(
            sel, sel.allOf(visible), Modifier.align(Alignment.TopCenter),
            onClose = { select(sel.exit()) },
            onAll = { select(if (sel.allOf(visible)) sel.none() else sel.all(visible)) },
        )
        SelectionActions(
            sel, bulk, Modifier.align(Alignment.BottomCenter), canDelete = com.coinepro.hq.core.net.HubFeature.DELETE_OUTPUTS !in gaps,
            onFile = ::fileSelected,
            onSeen = {
                val refs = sel.sorted
                sel = sel.exit()
                mark(refs, true, "${refs.size} خروجی خوانده شد")
            },
            onDelete = { deleting = loaded.filter { it.ref in sel } },
        )
    }
    deleting?.let { ds ->
        HqSheet({ deleting = null }, "حذف ${ds.size} خروجی برای همیشه", sub = "فقط تو میتوانی؛ با اثر انگشت یا چهره") {
            DeleteOutputsContent(ds, onCancel = { deleting = null }) { n ->
                gone.addAll(ds.map { it.ref })
                deleting = null
                sel = sel.exit()
                toasts.ok("$n خروجی برای همیشه پاک شد؛ یک خط در دفتر Audit ماند.")
            }
        }
    }
    if (filters) HqSheet({ filters = false }, "فیلترها", sub = "روی هر سه زبانه اعمال میشوند") {
        OutputFilters(
            category, { category = it }, company, { company = it }, producer, { producer = it },
            loaded.map { it.producer }.distinctBy { it.code }.sortedBy { it.titleFa }, range, { range = it },
            onClear = { category = null; company = null; producer = null; range = "all"; unrated = false },
            onDone = { filters = false },
        )
    }
}

/** The filter sheet's content: category, company, producer and the date range. */
@Composable
fun OutputFilters(
    category: String?, onCategory: (String?) -> Unit,
    company: String?, onCompany: (String?) -> Unit,
    producer: String?, onProducer: (String?) -> Unit,
    producers: List<com.coinepro.hq.core.net.EmployeeRef>,
    range: String, onRange: (String) -> Unit,
    onClear: () -> Unit, onDone: () -> Unit,
) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        @Composable fun Label(t: String) = Text(t, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Label("دسته")
            ChipRow {
                FilterChip("همه", category == null, { onCategory(null) })
                FilterChip("گزارش", category == "report", { onCategory("report") })
                FilterChip("کار", category == "work", { onCategory("work") })
            }
            Text("گزارش: آنچه خود هاب مینویسد (گزارش صبحگاهی، نامه‌ها)؛ کار: خروجی ایجنت برای یک کار.", style = Divan.type.micro, color = c.textMuted)
        }
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Label("شرکت")
            com.coinepro.hq.ui.v17.ScopeChips(company, onCompany)
        }
        if (producers.isNotEmpty() || producer != null) Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Label("سازنده")
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip("همه", producer == null, { onProducer(null) })
                for (p in producers) FilterChip(p.titleFa, producer == p.code, { onProducer(p.code) })
            }
        }
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Label("بازه‌ی زمانی")
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                for ((k, fa) in RANGES) FilterChip(fa, range == k, { onRange(k) })
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            HqButton("نمایش", onDone, Modifier.weight(1f), variant = BtnVariant.PRIMARY, icon = DivanIcon.FILTER)
            HqButton("پاک کردن فیلترها", onClear, variant = BtnVariant.GHOST)
        }
    }
}

/** A row the owner swipes either way to mark it seen (or new again); the background says which. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun SwipeToSee(seen: Boolean, onSwipe: () -> Unit, content: @Composable () -> Unit) {
    val c = Divan.colors
    val state = rememberSwipeToDismissBoxState()
    LaunchedEffect(seen) { state.snapTo(SwipeToDismissBoxValue.Settled) }
    SwipeToDismissBox(
        state,
        backgroundContent = {
            val toStart = state.dismissDirection == SwipeToDismissBoxValue.EndToStart
            Row(
                Modifier.fillMaxSize().clip(RoundedCornerShape(16.dp)).background(if (seen) c.raised else c.softPositive).padding(horizontal = 20.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = if (toStart) Arrangement.End else Arrangement.Start,
            ) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    DIcon(if (seen) DivanIcon.REFRESH else DivanIcon.SEAL, size = 18.dp, tint = if (seen) c.silverInk else c.positive)
                    Text(if (seen) "دوباره تازه" else "خوانده شد", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = if (seen) c.silverInk else c.positive)
                }
            }
        },
        onDismiss = { onSwipe() },
    ) { content() }
}

/**
 * One output in the list, a media card: its poster when it carries a video or a picture, the company and its kind, the rating (or the
 * silver dot of «بی‌امتیاز»), the title, the summary, who made it and when. A new one carries the thin gold edge and full ink; a seen
 * one is quieter. In selection mode a check slides in beside it and a tap toggles it; a long press opens the mode.
 */
@Composable
internal fun OutputRow(
    d: Deliverable, seen: Boolean, companyFa: String,
    selecting: Boolean = false, selected: Boolean = false, onLongClick: (() -> Unit)? = null, onOpen: () -> Unit,
) {
    val c = Divan.colors
    val reduced = com.coinepro.hq.designsystem.LocalReducedMotion.current
    val tint by androidx.compose.animation.animateColorAsState(if (selected) c.raised else c.card, com.coinepro.hq.designsystem.Motion.short(reduced), label = "row-selected")
    val face = remember(d.attachments) { faceOf(d.attachments.map(::kindFromMime)) }
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
    AnimatedVisibility(
        selecting,
        enter = if (reduced) androidx.compose.animation.EnterTransition.None else fadeIn(com.coinepro.hq.designsystem.Motion.medium()) + androidx.compose.animation.expandHorizontally(com.coinepro.hq.designsystem.Motion.medium()),
        exit = if (reduced) androidx.compose.animation.ExitTransition.None else fadeOut(com.coinepro.hq.designsystem.Motion.exit()) + androidx.compose.animation.shrinkHorizontally(com.coinepro.hq.designsystem.Motion.exit()),
    ) {
        Box(Modifier.padding(end = 10.dp)) { SelectCheck(selected) }
    }
    Box(Modifier.weight(1f).testTag("output-row")) {
        HqCard(
            // ⟨1.0.1⟩ M14: the card grows into the page of its output. C0.1: a selected row carries a silver hairline, never gold.
            Modifier.fillMaxWidth().continuity("outputs/${d.ref}").then(if (selected) Modifier.border(1.dp, com.coinepro.hq.designsystem.silverLine(), RoundedCornerShape(com.coinepro.hq.designsystem.Radius.card)) else Modifier),
            onClick = onOpen, color = tint, onLongClick = onLongClick, padding = PaddingValues(12.dp),
            onClickLabel = if (selecting) (if (selected) "برداشتن از انتخاب" else "انتخاب") else "باز کردن", onLongClickLabel = "انتخاب چندتایی",
        ) {
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                if (face != null) FaceFrame(Modifier.size(width = 58.dp, height = 76.dp), radius = 10.dp) { FileFace(face, sign = 22.dp) }
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        CompanyMark(d.company, height = 12.dp, mono = true, ink = c.textSecondary)
                        Text(remember(companyFa, d.kind) { facts(companyFa, CATEGORY_FA[d.kind] ?: d.kind) }, style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                        if (d.rating != null) Text("${d.rating.score} از ۱۰", style = Divan.type.micro, color = c.textSecondary, maxLines = 1)
                        else Box(Modifier.size(8.dp).clip(CircleShape).background(c.silverInk).semantics { contentDescription = "بی‌امتیاز" })
                    }
                    RichText(d.title, style = Divan.type.bodyStrong, color = if (seen) c.textSecondary else c.textPrimary, maxLines = 2)
                    if (d.summary.isNotBlank()) RichText(d.summary, style = Divan.type.caption, color = if (seen) c.textMuted else c.textSecondary, maxLines = 2)
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text("${d.producer.titleFa}، ${jTime(d.createdAt)}", style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                        if (d.filedAs != null) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            DIcon(DivanIcon.DELIVERABLE, size = 12.dp, tint = c.textMuted)
                            Text("در بایگانی", style = Divan.type.micro, color = c.textMuted, maxLines = 1)
                        }
                    }
                }
            }
        }
        // what he has not seen yet: the thin gold line at its start edge, never a filled dot
        if (!seen) Box(Modifier.matchParentSize().goldEdge(c.goldInk))
    }
    }
}

/** The round check of selection mode: an empty ring, or the disc with its tick. ⟨1.0.1⟩ C0.1: a selection is silver, never gold. */
@Composable
internal fun SelectCheck(on: Boolean) {
    val c = Divan.colors
    val reduced = com.coinepro.hq.designsystem.LocalReducedMotion.current
    val fill by androidx.compose.animation.animateColorAsState(if (on) c.silverFill else androidx.compose.ui.graphics.Color.Transparent, com.coinepro.hq.designsystem.Motion.short(reduced), label = "check-fill")
    val ring = if (on) c.silverFill else c.textMuted
    val ink = c.page
    androidx.compose.foundation.Canvas(Modifier.size(24.dp).semantics { contentDescription = if (on) "انتخاب‌شده" else "انتخاب‌نشده" }) {
        val r = size.minDimension / 2
        drawCircle(fill, r)
        drawCircle(ring, r - 1.dp.toPx(), style = androidx.compose.ui.graphics.drawscope.Stroke(1.6.dp.toPx()))
        if (on) {
            val p = androidx.compose.ui.graphics.Path().apply {
                moveTo(size.width * 0.28f, size.height * 0.52f)
                lineTo(size.width * 0.44f, size.height * 0.67f)
                lineTo(size.width * 0.72f, size.height * 0.36f)
            }
            drawPath(p, ink, style = androidx.compose.ui.graphics.drawscope.Stroke(2.dp.toPx(), cap = androidx.compose.ui.graphics.StrokeCap.Round, join = androidx.compose.ui.graphics.StrokeJoin.Round))
        }
    }
}

/** Selection mode's top bar: close, «۳ انتخاب‌شده», and all or none. */
@Composable
internal fun SelectionTop(
    sel: com.coinepro.hq.core.data.Selection, all: Boolean, modifier: Modifier, onClose: () -> Unit, onAll: () -> Unit,
    allLabel: String = "همه", noneLabel: String = "هیچ",
) {
    val c = Divan.colors
    val reduced = com.coinepro.hq.designsystem.LocalReducedMotion.current
    AnimatedVisibility(
        sel.active, modifier,
        enter = if (reduced) androidx.compose.animation.EnterTransition.None else fadeIn(com.coinepro.hq.designsystem.Motion.emphasised()) + slideInVertically(com.coinepro.hq.designsystem.Motion.emphasised()) { -it },
        exit = if (reduced) androidx.compose.animation.ExitTransition.None else fadeOut(com.coinepro.hq.designsystem.Motion.exit()) + slideOutVertically(com.coinepro.hq.designsystem.Motion.exit()) { -it },
    ) {
        Row(
            Modifier.fillMaxWidth().background(c.raised).padding(horizontal = 8.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            com.coinepro.hq.designsystem.IconBtn(DivanIcon.CLOSE, "بیرون از انتخاب", onClose)
            Text(
                if (sel.count == 0) "هیچ‌کدام انتخاب نشده" else "${sel.count} انتخاب‌شده",
                style = Divan.type.bodyStrong, color = c.textPrimary, modifier = Modifier.weight(1f).semantics { liveRegion = androidx.compose.ui.semantics.LiveRegionMode.Polite },
            )
            HqButton(if (all) noneLabel else allLabel, onAll, variant = BtnVariant.TEXT, size = BtnSize.SM)
        }
    }
}

/** Selection mode's actions: file in the archive, mark seen, delete for good. */
@Composable
internal fun SelectionActions(
    sel: com.coinepro.hq.core.data.Selection, busy: String?, modifier: Modifier,
    onFile: () -> Unit, onSeen: () -> Unit, onDelete: () -> Unit, canDelete: Boolean = true,
) {
    val c = Divan.colors
    val reduced = com.coinepro.hq.designsystem.LocalReducedMotion.current
    AnimatedVisibility(
        sel.active, modifier,
        enter = if (reduced) androidx.compose.animation.EnterTransition.None else fadeIn(com.coinepro.hq.designsystem.Motion.emphasised()) + slideInVertically(com.coinepro.hq.designsystem.Motion.emphasised()) { it },
        exit = if (reduced) androidx.compose.animation.ExitTransition.None else fadeOut(com.coinepro.hq.designsystem.Motion.exit()) + slideOutVertically(com.coinepro.hq.designsystem.Motion.exit()) { it },
    ) {
        val some = sel.count > 0
        Row(
            Modifier.padding(12.dp).widthIn(max = 560.dp).fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(c.raised).padding(8.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically,
        ) {
            HqButton("بایگانی", onFile, Modifier.weight(1f), variant = BtnVariant.SECONDARY, size = BtnSize.SM, enabled = some && busy == null, loading = busy == "file")
            HqButton("خوانده‌شده", onSeen, Modifier.weight(1f), variant = BtnVariant.SECONDARY, size = BtnSize.SM, enabled = some && busy == null)
            // A hub before ⟨1.10⟩ has no delete: the action is not offered.
            if (canDelete) HqButton("حذف برای همیشه", onDelete, Modifier.weight(1.45f), variant = BtnVariant.DANGER, size = BtnSize.SM, enabled = some && busy == null)
        }
    }
}

/**
 * ⟨1.10⟩ §28.1 deleting outputs for good: what goes and what stays, said plainly, then the passkey on the SHA-256 of the sorted refs.
 * A hub before ⟨1.10⟩ (404/405) keeps them, and the sheet says so.
 */
@Composable
fun DeleteOutputsContent(items: List<Deliverable>, onCancel: () -> Unit, onDeleted: (Int) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val scope = rememberCoroutineScope()
    val haptics = com.coinepro.hq.designsystem.rememberHaptics()
    var busy by remember { mutableStateOf(false) }
    val act = if (androidx.activity.compose.LocalActivity.current != null) com.coinepro.hq.ui.activity() else null
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text("از دیتابیس پاک میشود و برنمیگردد؛ فقط یک خط در دفتر Audit میماند.", style = Divan.type.bodyStrong, color = c.textPrimary)
        com.coinepro.hq.ui.companies.Consequences(
            listOfNotNull(
                DivanIcon.CLOSE to "خود خروجی، فایل‌هایش و امتیازهایش از دیتابیس و انبار فایل پاک میشوند.",
                DivanIcon.REPORT to "در دفتر Audit فقط شماره، عنوان، شرکت، این‌که تو پاکش کردی و زمانش میماند.",
                items.mapNotNull { it.filedAs }.takeIf { it.isNotEmpty() }?.let { DivanIcon.DELIVERABLE to "سند بایگانی‌شده‌شان (${it.joinToString("، ")}) سر جایش میماند؛ بایگانی سابقه‌ی توست." },
                DivanIcon.LOCK to "تأیید آخر با اثر انگشت یا چهره است.",
            ),
            c.negative,
        )
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            for (d in items.take(6)) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Fig(d.ref, style = Divan.type.figureSmall, color = c.textMuted)
                RichText(d.title, Modifier.weight(1f), style = Divan.type.small, color = c.textPrimary, maxLines = 1)
            }
            if (items.size > 6) Text("و ${items.size - 6} خروجی دیگر", style = Divan.type.caption, color = c.textMuted)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            HqButton("حذف برای همیشه", {
                if (busy || act == null) return@HqButton
                busy = true
                scope.launch {
                    try {
                        val out = env.api.gated(com.coinepro.hq.core.net.HubFeature.DELETE_OUTPUTS) {
                            deleteDeliverables(items.map { it.ref }) { a, t -> env.auth.stepUp(act, a, t) }
                        }
                        if (out == null) {
                            // A hub before ⟨1.10⟩: nothing was deleted; the action leaves the screens, without an error.
                            onCancel()
                        } else {
                            env.cache.invalidate("deliverables", "inbox", "employees")
                            haptics.confirm()
                            onDeleted(out.deleted)
                        }
                    } catch (e: ApiException) {
                        haptics.reject()
                        toasts.error(e.messageFa)
                    } finally { busy = false }
                }
            }, Modifier.weight(1f), variant = BtnVariant.DANGER, icon = DivanIcon.LOCK, loading = busy)
            HqButton("انصراف", onCancel, Modifier.weight(1f), variant = BtnVariant.GHOST)
        }
    }
}

/** "Marked · برگردان" for five seconds at the bottom of the list. */
@Composable
internal fun UndoBar(u: Undo?, modifier: Modifier, onTimeout: (Long) -> Unit, onUndo: (Undo) -> Unit) {
    val c = Divan.colors
    var last by remember { mutableStateOf(u) }
    if (u != null) last = u
    LaunchedEffect(u?.id) { val id = u?.id ?: return@LaunchedEffect; delay(5_000); onTimeout(id) }
    val reduced = com.coinepro.hq.designsystem.LocalReducedMotion.current
    AnimatedVisibility(
        u != null, modifier,
        enter = if (reduced) androidx.compose.animation.EnterTransition.None else fadeIn(com.coinepro.hq.designsystem.Motion.emphasised()) + slideInVertically(com.coinepro.hq.designsystem.Motion.emphasised()) { it / 2 },
        exit = if (reduced) androidx.compose.animation.ExitTransition.None else fadeOut(com.coinepro.hq.designsystem.Motion.exit()) + slideOutVertically(com.coinepro.hq.designsystem.Motion.exit()) { it / 2 },
    ) {
        val shown = last ?: return@AnimatedVisibility
        Row(
            Modifier.padding(16.dp).widthIn(max = 520.dp).fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.raised).padding(start = 14.dp, end = 6.dp, top = 6.dp, bottom = 6.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            DIcon(DivanIcon.SEAL, size = 18.dp, tint = c.positive)
            RichText(shown.text, Modifier.weight(1f), style = Divan.type.small, color = c.textPrimary, maxLines = 1)
            HqButton("برگردان", { onUndo(shown) }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.BACK)
        }
    }
}

// ------------------------------------------------------------------ one output --
/**
 * One output (C3.3): it opens with the thing itself (a video large and playable in place, a picture in its own shape, a document's
 * first lines), then its numbers in one row, the quiet «خوانده شد» and «بایگانی», the text (the summary only where the text does not
 * already say it), its files as a strip and where each one's publication stands, and the owner's rating. The page's decision bar
 * carries «تأیید و انتشار» of the first file that waits (the one full gold) with the quiet «اصلاح»; without it the rating is the
 * page's action. The header folds to the title as the page scrolls (M18).
 */
@Composable
fun OutputScreen(ref: String) {
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val scope = rememberCoroutineScope()
    val companies = rememberCompanies()
    val q = rememberQuery("deliverable:$ref", "deliverables") { deliverable(ref) }
    val r = refresher(q)
    val d = q.data
    val files = remember(d?.attachments) { d?.attachments.orEmpty().map(::kindFromMime).filter { it.id.isNotBlank() } }
    // §44.5 the publish panel is asked only for an output that carries something to publish.
    val panel = if (files.any(::goesOut)) rememberPublishPanel(ref).data else null
    val lead = leadFile(panel, files)
    var asking by remember { mutableStateOf<String?>(null) }
    var deleting by remember { mutableStateOf<Deliverable?>(null) }
    var erasing by remember { mutableStateOf(false) }
    val listState = androidx.compose.foundation.lazy.rememberLazyListState()
    val collapse = com.coinepro.hq.designsystem.rememberCollapse(listState)
    val noteFocus = remember { androidx.compose.ui.focus.FocusRequester() }
    // «اصلاح»: the composer of its session with this output named; an output of no session: the note to its maker.
    fun amend() {
        val order = panel?.order
        if (order != null && d != null) {
            com.coinepro.hq.ui.session.ComposerSeeds.put(order, "درباره‌ی «${com.coinepro.hq.core.data.quietLine(d.title)}»: ")
            nav.go("session/$order")
        } else scope.launch {
            listState.animateScrollToItem((listState.layoutInfo.totalItemsCount - 1).coerceAtLeast(0))
            runCatching { noteFocus.requestFocus() }
        }
    }
    com.coinepro.hq.designsystem.DecisionPage(
        bar = if (d != null && lead != null) ({
            val best = com.coinepro.hq.core.data.bestHourOf(com.coinepro.hq.core.data.bestChoice(panel?.best, panel?.accounts?.singleOrNull()))
            DecisionBar(
                "تأیید و انتشار", { asking = lead.id },
                context = listOfNotNull(
                    KIND_FA[if (isVideo(lead)) "reel" else "post"], panel?.accounts?.singleOrNull()?.let { "@$it" } ?: "اینستاگرام",
                    best?.let { "بهترین ساعت $it" }, "بی کارت و بی اثر انگشت",
                ).joinToString(" · "),
                quiet = listOf(com.coinepro.hq.designsystem.QuietAction("اصلاح") { amend() }), icon = DivanIcon.SEND, place = com.coinepro.hq.designsystem.DecisionPlace.PAGE,
            )
        }) else null,
    ) {
        Column(Modifier.fillMaxSize()) {
            // ⟨1.0.1⟩ M14: the card that was tapped grows into this header.
            if (d != null) OutputHeader(d, companyOf(companies, d.company).nameFa, { collapse.value }, Modifier.continuity("outputs/$ref"), onDelete = { deleting = d }, onErase = { erasing = true })
            Box(Modifier.weight(1f)) {
                Page(onRefresh = r::refresh, refreshing = r.refreshing, state = listState) {
                    when {
                        d != null -> outputItems(d, files, lead?.id, noteFocus) { q.set(it) }
                        q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
                        else -> item { Skeleton(Modifier.fillMaxWidth().height(300.dp), radius = 16.dp) }
                    }
                }
            }
        }
    }
    asking?.let { f -> PublishFor(ref, f, onDismiss = { asking = null }) }
    // ⟨1.19⟩ §37.2 one output and its files, after the preview and the passkey; the work it belongs to stays.
    if (erasing) com.coinepro.hq.ui.session.EraseSheet(com.coinepro.hq.core.net.EraseKind.OUTPUT, ref, onDismiss = { erasing = false }) {
        erasing = false
        nav.back()
    }
    deleting?.let { x ->
        HqSheet({ deleting = null }, "حذف ${x.ref} برای همیشه", sub = "فقط تو میتوانی؛ با اثر انگشت یا چهره") {
            DeleteOutputsContent(listOf(x), onCancel = { deleting = null }) {
                deleting = null
                toasts.ok("${x.ref} برای همیشه پاک شد؛ یک خط در دفتر Audit ماند.")
                nav.back()
            }
        }
    }
}

/** The header of an output's page: whose it is and who made it, then the title; folded, the title alone. «⋮» keeps what is rare. */
@Composable
private fun OutputHeader(d: Deliverable, companyFa: String, fraction: () -> Float, modifier: Modifier = Modifier, onDelete: () -> Unit, onErase: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    val local by env.seen.refs.collectAsStateWithLifecycle()
    val gaps by env.api.gaps.missing.collectAsStateWithLifecycle()
    val seenAt = d.seenAt ?: local[d.ref]
    val menu: @Composable () -> Unit = {
        Box {
            var open by remember { mutableStateOf(false) }
            com.coinepro.hq.designsystem.IconBtn(DivanIcon.MORE, "کارهای این خروجی", { open = true }, tint = c.textSecondary)
            androidx.compose.material3.DropdownMenu(open, { open = false }, containerColor = c.overlay) {
                androidx.compose.material3.DropdownMenuItem({ Text(if (seenAt == null) "خوانده‌شده" else "دوباره تازه", style = Divan.type.small) }, {
                    open = false
                    action.run { markSeen(env, toasts, listOf(d.ref), seenAt == null) }
                }, leadingIcon = { DIcon(if (seenAt == null) DivanIcon.SEAL else DivanIcon.REFRESH, size = 18.dp) })
                // ⟨1.19⟩ §37.2 «پاک کردن برای همیشه» shows what goes first; a hub before it keeps §28.1's delete.
                if (com.coinepro.hq.core.net.HubFeature.ERASE !in gaps) androidx.compose.material3.DropdownMenuItem({ Text("پاک کردن برای همیشه", style = Divan.type.small, color = c.negative) }, {
                    open = false
                    onErase()
                }, leadingIcon = { DIcon(DivanIcon.REJECT, size = 18.dp, tint = c.negative) })
                else if (com.coinepro.hq.core.net.HubFeature.DELETE_OUTPUTS !in gaps) androidx.compose.material3.DropdownMenuItem({ Text("حذف برای همیشه", style = Divan.type.small, color = c.negative) }, {
                    open = false
                    onDelete()
                }, leadingIcon = { DIcon(DivanIcon.DISMISS, size = 18.dp, tint = c.negative) })
            }
        }
    }
    com.coinepro.hq.designsystem.CollapsingHeader(
        fraction, modifier.fillMaxWidth().background(c.page).testTag("output-header"),
        line = {
            Row(Modifier.fillMaxWidth().height(52.dp).padding(start = 16.dp, end = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                RichText(d.title, Modifier.weight(1f), style = Divan.type.bodyStrong, color = c.textPrimary, maxLines = 1)
                menu()
            }
        },
        full = {
            Column(Modifier.fillMaxWidth().padding(start = 16.dp, end = 4.dp, top = 8.dp, bottom = 4.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    CompanyMark(d.company, height = 13.dp, mono = true, ink = c.textSecondary)
                    Text(
                        remember(d, companyFa) { facts(companyFa, CATEGORY_FA[d.kind] ?: d.kind, "${d.producer.titleFa}، ${jDateTime(d.createdAt)}") },
                        style = Divan.type.micro, color = c.textMuted, maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f),
                    )
                    menu()
                }
                RichText(d.title, Modifier.padding(end = 12.dp), style = Divan.type.h2, color = c.textPrimary)
            }
        },
    )
}

/** A number of the output with its label over it. */
@Composable
private fun Figure(label: String, modifier: Modifier = Modifier, onClick: (() -> Unit)? = null, value: @Composable () -> Unit) {
    Column(
        modifier.then(if (onClick != null) Modifier.clip(RoundedCornerShape(8.dp)).clickable(role = Role.Button, onClickLabel = label, onClick = onClick) else Modifier),
        verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        Text(label, style = Divan.type.micro, color = Divan.colors.textMuted)
        value()
    }
}

/** A document's text: its first lines, and «همه‌ی متن» for the rest (an output that shows no picture or video opens with it). */
@Composable
private fun OutputText(body: String, fold: Boolean) {
    val c = Divan.colors
    var whole by rememberSaveable(body.length) { mutableStateOf(false) }
    val page = c.page
    Column(Modifier.fillMaxWidth().testTag("output-text"), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        com.coinepro.hq.ui.Selectable {
            if (fold && !whole) Box(
                Modifier.fillMaxWidth().heightIn(max = 216.dp).clip(androidx.compose.ui.graphics.RectangleShape).drawWithContent {
                    drawContent()
                    // the last lines fade into the page: there is more under them
                    drawRect(androidx.compose.ui.graphics.Brush.verticalGradient(0.7f to androidx.compose.ui.graphics.Color.Transparent, 1f to page))
                },
            ) { Md(body) } else Md(body)
        }
        if (fold) HqButton(if (whole) "کمتر" else "همه‌ی متن", { whole = !whole }, variant = BtnVariant.TEXT, size = BtnSize.SM)
    }
}

/** The body of an output's page, one row of the list each (so «اصلاح» can bring the note into view). */
private fun androidx.compose.foundation.lazy.LazyListScope.outputItems(
    d: Deliverable, files: List<com.coinepro.hq.core.net.FileRef>, lead: String?, noteFocus: androidx.compose.ui.focus.FocusRequester, onChanged: (Deliverable) -> Unit,
) {
    val face = faceOf(files)
    // The thing itself.
    if (face != null) item(key = "face") {
        Box(Modifier.fillMaxWidth().testTag("output-face")) {
            if (isVideo(face)) HeroPlayer(face)
            else HeroMedia(face, ratio = (face.width ?: 0).let { w -> (face.height ?: 0).let { h -> if (w > 0 && h > 0) (w.toFloat() / h).coerceIn(0.5f, 2f) else 4f / 5f } }, maxHeight = 440.dp)
        }
    }
    item(key = "figures") { OutputFigures(d) }
    item(key = "quiet") { OutputQuiet(d) }
    // The text; the summary only where the text does not already say it.
    if (summaryIsNew(d.summary, d.body)) item(key = "summary") {
        com.coinepro.hq.ui.Selectable { Md(d.summary, style = Divan.type.body.copy(fontWeight = FontWeight.SemiBold, lineHeight = 28.sp), color = Divan.colors.textPrimary) }
    }
    val body = d.body
    if (!body.isNullOrBlank()) item(key = "text") { OutputText(body, fold = face == null && body.length > 700) }
    if (files.isNotEmpty()) item(key = "files") {
        Column(Modifier.testTag("output-files"), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("فایل‌ها", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = Divan.colors.textPrimary)
            FilesStrip(files)
        }
    }
    // ⟨0.19.8⟩ §44.5 where each video or picture's publication stands; the first one to publish is in the decision bar.
    if (files.any(::goesOut)) item(key = "publish") { PublishSection(d, lead = lead) }
    item(key = "rate") { RatePanel(d, gold = lead == null, noteFocus = noteFocus, onChanged = onChanged) }
}

/** The numbers, in one row: how it was made, what it used, who made it, the owner's score. */
@Composable
private fun OutputFigures(d: Deliverable) {
    val nav = LocalNav.current
    val c = Divan.colors
    // ⟨1.0.1⟩ §53 what made it, by the app's own name for it, and how hard it thought («بیشترین دقت»), when the hub says both
    val made = com.coinepro.hq.core.data.madeWithFa(d.producedWith)
    val (used, cost) = usageOf(d)
    val value = Divan.type.small.copy(fontWeight = FontWeight.SemiBold)
    FlowRow(
        Modifier.fillMaxWidth().testTag("output-figures").clip(RoundedCornerShape(14.dp)).background(c.tile).padding(horizontal = 14.dp, vertical = 12.dp),
        horizontalArrangement = Arrangement.spacedBy(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        if (made != null) Figure("ساخت") { Text(made, style = value, color = c.textPrimary) }
        if (used != null) Figure("مصرف") {
            Text(buildAnnotatedString { fig(tokens(used)); append(" واحد"); if (cost != null) { append("، "); fig(usd(cost)) } }, style = value, color = c.textPrimary)
        }
        Figure("سازنده", onClick = { nav.go("employees/${d.producer.code}") }) { Text(d.producer.titleFa, style = value, color = c.textPrimary) }
        Figure("امتیاز تو") { Text(d.rating?.let { "${it.score} از ۱۰" } ?: "—", style = value, color = c.textPrimary) }
    }
}

/** Seen and filed: the two things done with an output once read. Quiet, never the page's gold. */
@Composable
private fun OutputQuiet(d: Deliverable) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val action = rememberAction()
    val filing = rememberAction()
    val local by env.seen.refs.collectAsStateWithLifecycle()
    var filed by rememberSaveable(d.ref) { mutableStateOf(d.filedAs) }
    val seenAt = d.seenAt ?: local[d.ref]
    FlowRow(
        Modifier.testTag("output-quiet"), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp),
        itemVerticalAlignment = Alignment.CenterVertically,
    ) {
        if (seenAt == null) HqButton("خوانده شد", {
            action.run { markSeen(env, toasts, listOf(d.ref), true); toasts.ok("${d.ref} به «خوانده‌شده» رفت.") }
        }, variant = BtnVariant.SECONDARY, size = BtnSize.SM, icon = DivanIcon.SEAL, loading = action.busy)
        else {
            Pill("خوانده شد، ${jDateTime(seenAt)}", Tone.NEUTRAL, icon = DivanIcon.SEAL)
            HqButton("دوباره تازه کن", { action.run { markSeen(env, toasts, listOf(d.ref), false) } }, variant = BtnVariant.TEXT, size = BtnSize.SM, loading = action.busy)
        }
        val f = filed
        if (f != null) RefChip(f, "در بایگانی", tone = com.coinepro.hq.ui.v17.RefTone.NEUTRAL)
        else HqButton("بایگانی کن", {
            filing.run {
                try {
                    val out = env.api.fileDeliverable(d.ref)
                    filed = out.record
                    env.cache.invalidate("deliverables", "archive")
                    toasts.ok("در بایگانی ثبت شد: ${out.record}؛ پیش‌نویس است تا بایگان کاملش کند.")
                } catch (e: ApiException) {
                    if (e.status == 404 || e.status == 405) {
                        e.logged?.let { env.api.failures?.forget(it) }
                        toasts.info("بایگانی خروجی با به‌روزرسانی هاب فعال میشود.")
                    } else throw e
                }
            }
        }, variant = BtnVariant.SECONDARY, size = BtnSize.SM, icon = DivanIcon.DELIVERABLE, loading = filing.busy)
        d.workId?.let { w -> HqButton("کار مربوط", { nav.go("work/$w") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.TASK) }
    }
}

/** «امتیاز تو»: the score, a note for its maker, «ثبت امتیاز». [gold]: the page has no decision bar, so this is its one action. */
@Composable
private fun RatePanel(d: Deliverable, gold: Boolean, noteFocus: androidx.compose.ui.focus.FocusRequester, onChanged: (Deliverable) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    var score by rememberSaveable(d.ref) { mutableIntStateOf(d.rating?.score ?: 0) }
    var comment by rememberSaveable(d.ref) { mutableStateOf(d.rating?.comment.orEmpty()) }
    Column(
        // the card surface: the score's own marks sit on the tile surface
        Modifier.fillMaxWidth().testTag("output-rate").clip(RoundedCornerShape(16.dp)).background(c.card).padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(if (d.rating == null) "امتیاز تو" else "امتیاز تو (قابل تغییر)", style = Divan.type.h3)
            Text("در نمره و یادگیری سازنده‌اش اثر دارد؛ جدا از «خوانده شد».", style = Divan.type.caption, color = c.textMuted)
        }
        com.coinepro.hq.designsystem.ScrollX { RatingRow(score, { score = it }) }
        HqTextField(comment, { comment = it }, "نکته برای سازنده (اختیاری)", Modifier.fillMaxWidth().focusRequester(noteFocus), singleLine = false, minLines = 2)
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(d.rating?.let { "${it.score} از ۱۰، ${jDateTime(it.ratedAt)}" }.orEmpty(), style = Divan.type.micro, color = c.textSecondary, modifier = Modifier.weight(1f))
            HqButton("ثبت امتیاز", {
                action.run {
                    val out = env.api.rate(d.ref, score, comment.ifBlank { null })
                    onChanged(out)
                    env.cache.invalidate("deliverables", "inbox", "employees")
                    toasts.ok("امتیاز $score ثبت شد.")
                }
            }, variant = if (gold) BtnVariant.PRIMARY else BtnVariant.SECONDARY, enabled = score > 0, loading = action.busy, icon = DivanIcon.RATE)
        }
    }
}

/** ⟨0.19.6⟩ An attachment whose kind was not sent (an output's file): image, video or audio by its mime, else as it is. */
internal fun kindFromMime(f: com.coinepro.hq.core.net.FileRef): com.coinepro.hq.core.net.FileRef =
    if (f.kind != "document") f else when {
        f.mime.startsWith("video/") -> f.copy(kind = "video")
        f.mime.startsWith("image/") -> f.copy(kind = "image")
        f.mime.startsWith("audio/") -> f.copy(kind = "audio")
        else -> f
    }
