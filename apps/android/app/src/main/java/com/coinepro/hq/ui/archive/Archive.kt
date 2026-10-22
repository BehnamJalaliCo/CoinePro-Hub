package com.coinepro.hq.ui.archive

import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
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
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.net.ArchiveRecord
import com.coinepro.hq.core.net.RecordFilters
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v17.ScopeChips
import kotlinx.coroutines.delay

// بایگانی (contract §23), mirroring apps/web/src/app/(app)/archive/page.tsx: search with snippets, the filters (scope, class, folder, level,
// party, dates), drafts waiting to be filed, what expires soonest, the last fixity run, and «سند تازه» (intake).

/** The archive's home. [party0] or [folder0] arrive from a party chip or a folder of a path; [q0] a search already typed. */
@Composable
fun ArchiveScreen(q0: String? = null, party0: String? = null, folder0: String? = null, scope0: String? = null, new0: Boolean = false, picked0: List<Uri> = emptyList()) {
    val c = Divan.colors
    val nav = LocalNav.current
    val arch = rememberArchive()
    val m = arch.m
    var scope by rememberSaveable { mutableStateOf(scope0) }
    var cls by rememberSaveable { mutableStateOf<String?>(null) }
    var folder by rememberSaveable { mutableStateOf(folder0) }
    var level by rememberSaveable { mutableStateOf<String?>(null) }
    var party by rememberSaveable { mutableStateOf(party0) }
    var from by rememberSaveable { mutableStateOf<String?>(null) }
    var to by rememberSaveable { mutableStateOf<String?>(null) }
    var text by rememberSaveable { mutableStateOf(q0.orEmpty()) }
    var q by rememberSaveable { mutableStateOf(q0.orEmpty()) }
    var open by rememberSaveable { mutableStateOf(false) }
    var making by remember { mutableStateOf(new0) }
    // The search writes the query a moment after typing stops.
    LaunchedEffect(text) { if (text.trim() != q) { delay(350); q = text.trim() } }
    val searching = q.length >= 2
    val f = RecordFilters(scope = scope, cls = cls, folder = folder, level = level, party = party, from = from, to = to, q = q.takeIf { searching })
    val list = rememberQuery("archive:records:${f.key}", "archive") { records(f) }
    val hits = if (searching) rememberQuery("archive:search:$q:${scope ?: ""}:${cls ?: ""}:${level ?: ""}:${from ?: ""}:${to ?: ""}", "archive") { archiveSearch(q, scope, cls, level, from, to) } else null
    val holds = rememberQuery("archive:holds:active:", "archive") { legalHolds("active") }
    val more = remember(f.key) { mutableStateListOf<ArchiveRecord>() }
    var cursor by remember(f.key, list.data) { mutableStateOf(list.data?.nextCursor) }
    val snippet = hits?.data.orEmpty().associate { it.ref to it.snippetFa }
    val rows = (list.data?.items.orEmpty() + more).filter { searching || it.state != "draft" }
    val active = listOf(cls, folder, level, party, from, to).count { it != null }
    val filtered = active > 0 || scope != null || searching
    val r = refresher(list, arch.q)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            PageHeader("بایگانی", eyebrow = "هر سند یک بار ثبت میشود، نسخه دارد و بعد از مُهر دست نمیخورد") {
                HqButton("سند تازه", { making = true }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.ADD)
            }
        }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                FixityLine()
                Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    val n = holds.data?.size ?: 0
                    NavChip("توقیف‌ها", DivanIcon.LOCK, if (n > 0) "$n فعال" else null) { nav.go("archive-holds") }
                    NavChip("یادآورها", DivanIcon.TIME) { nav.go("archive-reminders") }
                    NavChip("پایان نگهداری", DivanIcon.MEMORY) { nav.go("archive-retention") }
                    NavChip("طرح بایگانی", DivanIcon.SETTINGS) { nav.go("archive-settings") }
                }
            }
        }
        item { ExpiringStrip(m) }
        item { DraftsBlock(scope, m) }
        item {
            HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(12.dp)) {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        SearchBox(text, { text = it }, Modifier.weight(1f))
                        HqButton(if (active > 0) "$active" else null, { open = !open }, variant = if (active > 0) BtnVariant.SILVER else BtnVariant.SECONDARY, icon = DivanIcon.FILTER, label = "فیلترها")
                    }
                    ScopeChips(scope, { scope = it; folder = null }, allLabel = "همه")
                    if (open || active > 0) Filters(m, scope, cls, { cls = it }, folder, { folder = it }, level, { level = it }, party, { party = it }, from, { from = it }, to, { to = it })
                }
            }
        }
        party?.let { p -> item { PartyCard(p, m) { party = null } } }
        item {
            HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(horizontal = 8.dp, vertical = 8.dp)) {
                val data = list.data
                when {
                    data == null && list.error != null -> ErrorBlock(list.error, { list.refresh() })
                    data == null || arch.q.data == null -> Column(verticalArrangement = Arrangement.spacedBy(8.dp)) { repeat(4) { Skeleton(Modifier.fillMaxWidth().height(64.dp), radius = 12.dp) } }
                    rows.isEmpty() -> RecordsEmpty(filtered)
                    else -> Column {
                        Text(
                            (if (searching) "${rows.size} نتیجه برای «$q»" else "${rows.size} سند") + if (filtered && !searching) " با این فیلترها" else "",
                            Modifier.padding(horizontal = 8.dp, vertical = 6.dp), style = Divan.type.caption, color = c.textMuted,
                        )
                        rows.forEachIndexed { i, x ->
                            if (i > 0) HorizontalDivider(color = c.lineDivider)
                            RecordRow(x, m, snippet = if (searching) snippet[x.ref] else null, q = q.takeIf { searching })
                        }
                        val next = cursor
                        if (next != null) LoadMore(f, next) { page -> more.addAll(page.items); cursor = page.nextCursor }
                    }
                }
            }
        }
    }
    if (making) HqSheet({ making = false }, "سند تازه", sub = "فایل‌ها اول از نظر رمز و کلید بررسی میشوند، hash میگیرند و متنشان خوانده میشود؛ پیشنهاد نوع و مشخصات فقط پیشنهاد است.") {
        IntakeContent(scope, { making = false }, picked0)
    }
}

@Composable
private fun LoadMore(f: RecordFilters, cursor: String, onPage: (com.coinepro.hq.core.net.Page<ArchiveRecord>) -> Unit) {
    val env = LocalEnv.current
    val toasts = com.coinepro.hq.ui.LocalToasts.current
    val action = rememberAction()
    HqButton("بیشتر", { action.archive(toasts) { onPage(env.api.records(f, cursor)) } }, Modifier.fillMaxWidth().padding(8.dp), variant = BtnVariant.GHOST, loading = action.busy)
}

@Composable
private fun NavChip(label: String, icon: DivanIcon, note: String? = null, onClick: () -> Unit) {
    val c = Divan.colors
    Row(
        Modifier.height(34.dp).clip(CircleShape).border(1.dp, c.lineStrong, CircleShape).clickable(role = Role.Button, onClick = onClick).padding(horizontal = 12.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        DIcon(icon, size = 14.dp, tint = c.textSecondary)
        Text(label, style = Divan.type.caption, color = c.textSecondary)
        if (note != null) Text(note, style = Divan.type.micro, color = c.textMuted)
    }
}

@Composable
private fun SearchBox(value: String, onChange: (String) -> Unit, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val shape = RoundedCornerShape(12.dp)
    Row(
        modifier.heightIn(min = 44.dp).clip(shape).background(c.tile).border(1.dp, c.lineStrong, shape).padding(horizontal = 12.dp).semantics { contentDescription = "جستجو در بایگانی" },
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        DIcon(DivanIcon.SEARCH, size = 18.dp, tint = c.textSecondary)
        Box(Modifier.weight(1f).padding(vertical = 10.dp)) {
            if (value.isEmpty()) Text("جستجو در عنوان، مشخصات و متن فایل‌ها", style = Divan.type.small, color = c.textMuted, maxLines = 1)
            BasicTextField(value, onChange, Modifier.fillMaxWidth(), singleLine = true, textStyle = Divan.type.small.copy(color = c.textPrimary), cursorBrush = SolidColor(c.goldInk))
        }
        if (value.isNotEmpty()) DIcon(DivanIcon.CLOSE, Modifier.clickable(role = Role.Button, onClickLabel = "پاک کردن جستجو") { onChange("") }, size = 14.dp, tint = c.textMuted)
    }
}

@Composable
private fun Filters(
    m: ArchiveMaps, scope: String?,
    cls: String?, setCls: (String?) -> Unit, folder: String?, setFolder: (String?) -> Unit, level: String?, setLevel: (String?) -> Unit,
    party: String?, setParty: (String?) -> Unit, from: String?, setFrom: (String?) -> Unit, to: String?, setTo: (String?) -> Unit,
) {
    val folders = m.folders.filter { scope == null || it.scope == scope }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Labelled("نوع سند", Modifier.weight(1f)) { Select(cls, m.classes.map { Opt(it.key, it.titleFa + if (it.status == "retired") " (بازنشسته)" else "") }, setCls, "نوع سند", Modifier.fillMaxWidth(), nullable = true, none = "همه") }
            Labelled("پوشه", Modifier.weight(1f)) {
                Select(folder, folders.map { Opt(it.ref, "— ".repeat((m.folderPath(it.ref).size - 1).coerceAtLeast(0)) + it.titleFa + if (scope == null) " · ${it.scope}" else "") }, setFolder, "پوشه", Modifier.fillMaxWidth(), nullable = true, none = "همه")
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Labelled("سطح", Modifier.weight(1f)) { Select(level, m.levels.map { Opt(it.key, it.titleFa) }, setLevel, "سطح", Modifier.fillMaxWidth(), nullable = true, none = "همه") }
            Labelled("طرف", Modifier.weight(1f)) { Select(party, m.parties.map { Opt(it.ref, it.nameFa) }, setParty, "طرف", Modifier.fillMaxWidth(), nullable = true, none = "همه") }
        }
        Labelled("تاریخ سند از") { DateField(from, setFrom, "تاریخ سند از") }
        Labelled("تا") { DateField(to, setTo, "تاریخ سند تا") }
    }
}

@Composable
internal fun Labelled(label: String, modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(label, style = Divan.type.micro, color = Divan.colors.textMuted)
        content()
    }
}
