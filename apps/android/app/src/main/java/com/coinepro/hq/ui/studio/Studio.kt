package com.coinepro.hq.ui.studio

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.actorFa
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.format.tokens
import com.coinepro.hq.core.format.until
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.core.net.MediaItem
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
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
import com.coinepro.hq.designsystem.RichText
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.cartable.SealButton
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v16.Chip
import com.coinepro.hq.ui.v16.ChipRow
import com.coinepro.hq.ui.v16.prose
import com.coinepro.hq.ui.v17.ActorAvatar
import com.coinepro.hq.ui.v17.CoMark
import com.coinepro.hq.ui.v17.RefChip
import com.coinepro.hq.ui.v17.RefTone
import com.coinepro.hq.ui.v17.ScopeChips
import com.coinepro.hq.ui.v18.AudioPlayer
import com.coinepro.hq.ui.v19.Block
import com.coinepro.hq.ui.v19.CheckGrid
import com.coinepro.hq.ui.v19.FileChip
import com.coinepro.hq.ui.v19.ITEM_STATE
import com.coinepro.hq.ui.v19.KIND_FA
import com.coinepro.hq.ui.v19.LicenceBadge
import com.coinepro.hq.ui.v19.PublishRows
import com.coinepro.hq.ui.v19.QC_VERDICT
import com.coinepro.hq.ui.v19.RenderPreview
import com.coinepro.hq.ui.v19.SERIES_STATUS
import com.coinepro.hq.ui.v19.STAGES
import com.coinepro.hq.ui.v19.STOPPED
import com.coinepro.hq.ui.v19.StageTrack
import com.coinepro.hq.ui.v19.aspectOfItem
import com.coinepro.hq.ui.v19.media
import com.coinepro.hq.ui.v19.secs
import com.coinepro.hq.ui.v19.shareFile
import java.util.UUID
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

// The media studio (contract §22.2), mirroring apps/web/src/app/(app)/media/page.tsx and components/v19/studio.tsx: each company's
// pipeline, item by item, from the script to the official API. A sealed series publishes by itself; any failed check, and anything
// outside a series, is the owner's card.

private val SOURCE_FA = mapOf("market_data" to "داده‌ی بازار", "deliverable" to "خروجی", "knowledge" to "دانشنامه", "url" to "صفحه")

/** استودیوی رسانه: what is coming, the series and the voice; then every item of every company, by step. [open0] opens one item. */
@Composable
fun StudioScreen(open0: String? = null) {
    val nav = LocalNav.current
    val c = Divan.colors
    var company by rememberSaveable { mutableStateOf<String?>(null) }
    var kind by rememberSaveable { mutableStateOf<String?>(null) }
    var open by rememberSaveable { mutableStateOf(open0) }
    var making by remember { mutableStateOf(false) }
    val q = rememberQuery("media:items:${company ?: ""}", "media") { mediaItems(company).items }
    val series = rememberQuery("media:series::", "media") { series() }
    val voices = rememberQuery("media:voices", "media") { voices() }
    val live = q.data?.any { it.live } == true
    LaunchedEffect(live) { while (live) { delay(15_000); q.refresh() } }
    val r = refresher(q, series, voices)
    val all = q.data.orEmpty()
    val items = if (kind == null) all else all.filter { it.kind == kind }
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            PageHeader("استودیوی رسانه", eyebrow = "هر شرکت، هر روز، بی‌دست تو؛ انتشار فقط از API رسمی تلگرام و اینستاگرام") {
                HqButton("آیتم یک‌باره", { making = true }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.ADD)
            }
        }
        item {
            Text(
                prose("سناریو، کارگردانی، موشن‌گرافیک به‌صورت کد، صدای ساخته‌ی خود هاب، رندر در سندباکس، چک‌های کدی و بازبینی مدیر رسانه. برنامه‌ی مُهرشده خودش منتشر میکند؛ هر چک ردشده یا هر چیزی بیرون از برنامه کارت توست."),
                style = Divan.type.small, color = c.textSecondary,
            )
        }
        item { Overview(series.data, voices.data, loading = series.loading || voices.loading) { nav.go(it) } }
        item { ScopeChips(company, { company = it }, holding = false, allLabel = "همه‌ی شرکت‌ها") }
        item {
            ChipRow {
                FilterChip("همه‌ی نوع‌ها", kind == null, { kind = null })
                for ((k, m) in KIND_FA) FilterChip(m.fa, kind == k, { kind = k })
            }
        }
        when {
            q.data == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            q.data == null -> item { Skeleton(Modifier.fillMaxWidth().height(420.dp), radius = 16.dp) }
            else -> {
                item { StageCounts(items) }
                if (items.any { it.state == "waiting_owner" || it.state == "held" }) item { NeedsYou(items) { open = it } }
                item { PipelineBoard(items) { open = it } }
            }
        }
    }
    open?.let { ref ->
        HqSheet({ open = null }, all.firstOrNull { it.ref == ref }?.titleFa ?: "آیتم رسانه", ref = ref) { ItemView(ref) }
    }
    if (making) HqSheet({ making = false }, "آیتم یک‌باره", sub = "بیرون از برنامه‌ها؛ از همان خط تولید میگذرد و آخرش همیشه کارت انتشار برای توست. طراحی رابط منتشر نمیشود و به مدیر فنی میرسد.") {
        NewItem { ref -> making = false; open = ref }
    }
}

/** Three cards: the next automatic publication, the series by status, the hub's active voice. */
@Composable
private fun Overview(series: List<com.coinepro.hq.core.net.Series>?, voices: List<com.coinepro.hq.core.net.Voice>?, loading: Boolean, go: (String) -> Unit) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        HqCard(Modifier.fillMaxWidth(), radius = 14.dp) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                DIcon(DivanIcon.TIME, size = 14.dp, tint = c.textMuted)
                Text("انتشار خودکار بعدی", style = Divan.type.caption, color = c.textMuted)
            }
            val next = series.orEmpty().flatMap { s -> s.nextAt.map { it to s } }.minByOrNull { it.first }
            when {
                series == null && loading -> Skeleton(Modifier.fillMaxWidth().height(40.dp).padding(top = 6.dp))
                next != null -> {
                    Text(next.second.titleFa, Modifier.padding(top = 4.dp), style = Divan.type.bodyStrong, color = c.textPrimary)
                    Text(com.coinepro.hq.designsystem.timesFig(buildAnnotatedString { append("${jDateTime(next.first)}، ${until(next.first)} · "); fig(next.second.ref) }), style = Divan.type.caption, color = c.textSecondary)
                }
                else -> Text("برنامه‌ی مُهرشده‌ای در صف نیست.", Modifier.padding(top = 4.dp), style = Divan.type.small, color = c.textSecondary)
            }
        }
        HqCard(Modifier.fillMaxWidth(), radius = 14.dp, onClick = { go("series") }) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                DIcon(DivanIcon.SEND, size = 14.dp, tint = c.textMuted)
                Text("برنامه‌های انتشار", Modifier.weight(1f), style = Divan.type.caption, color = c.textMuted)
                DIcon(DivanIcon.NEXT, size = 16.dp, tint = c.textMuted)
            }
            val counts = listOf("sealed", "proposed", "draft", "paused").map { k -> k to series.orEmpty().count { it.status == k } }.filter { it.second > 0 }
            FlowRow(Modifier.padding(vertical = 6.dp), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                if (counts.isEmpty()) Text("هنوز برنامه‌ای نیست.", style = Divan.type.small, color = c.textSecondary)
                for ((k, n) in counts) SERIES_STATUS[k]?.let { Pill("$n ${it.fa}", it.tone, icon = it.icon) }
            }
            Text("مُهر روی برنامه است، نه روی هر پست؛ فقط آیتمی که همه‌ی چک‌ها را رد کند خودکار میرود.", style = Divan.type.micro, color = c.textMuted)
        }
        HqCard(Modifier.fillMaxWidth(), radius = 14.dp, onClick = { go("voice") }) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                DIcon(DivanIcon.MIC, size = 14.dp, tint = c.textMuted)
                Text("صدای فعال هاب", Modifier.weight(1f), style = Divan.type.caption, color = c.textMuted)
                DIcon(DivanIcon.NEXT, size = 16.dp, tint = c.textMuted)
            }
            val active = voices?.firstOrNull { it.status == "active" }
            when {
                voices == null && loading -> Skeleton(Modifier.fillMaxWidth().height(40.dp).padding(top = 6.dp))
                active != null -> Column(Modifier.padding(top = 4.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(prose(active.nameFa), style = Divan.type.bodyStrong, color = c.textPrimary)
                    LicenceBadge(active.licenceCommercial, active.licence)
                }
                else -> Text("هنوز صدایی فعال نیست.", Modifier.padding(top = 4.dp), style = Divan.type.small, color = c.textSecondary)
            }
        }
    }
}

/** One count per step: where the work is piling up. Four to a row on the phone. */
@Composable
private fun StageCounts(items: List<MediaItem>) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        for (row in STAGES.chunked(4)) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            for (s in row) {
                val n = items.count { it.state in s.states }
                val mine = s.key == "ready" && items.any { it.state == "waiting_owner" }
                Column(
                    Modifier.weight(1f).clip(RoundedCornerShape(12.dp)).background(if (mine) c.softGold else c.card)
                        .then(if (mine) Modifier.border(1.dp, c.lineTahrir, RoundedCornerShape(12.dp)) else Modifier).padding(10.dp),
                    verticalArrangement = Arrangement.spacedBy(2.dp),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        DIcon(s.icon, size = 12.dp, tint = c.textMuted)
                        Text(s.fa, style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                    // A count of items: the text face draws its digits Persian.
                    Text(n.toString(), style = Divan.type.h2.copy(fontSize = 20.sp, lineHeight = 28.sp), color = if (n > 0) c.textPrimary else c.textMuted)
                }
            }
        }
    }
}

/** What the studio needs from the owner right now: a card to seal, a hold to decide. */
@Composable
private fun NeedsYou(items: List<MediaItem>, onOpen: (String) -> Unit) {
    val c = Divan.colors
    val nav = LocalNav.current
    val xs = items.filter { it.state == "waiting_owner" || it.state == "held" }
    HqCard(Modifier.fillMaxWidth(), tahrir = true) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DIcon(DivanIcon.SEAL, size = 18.dp, tint = c.goldInk)
            Text("منتظر تو", style = Divan.type.bodyStrong, color = c.textPrimary)
        }
        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            for (x in xs) {
                val st = ITEM_STATE[x.state]
                Column(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).clickable(role = Role.Button) { onOpen(x.ref) }.padding(horizontal = 12.dp, vertical = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        CoMark(x.company, height = 11.dp)
                        Text(x.titleFa, Modifier.weight(1f), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Fig(x.ref, style = Divan.type.figureSmall, color = c.textMuted)
                    }
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        LabelPill(st, x.state)
                        Text(if (x.state == "held") "ناظر نگه داشته؛ تصمیم با توست" else "کارت انتشار", Modifier.weight(1f), style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        x.decisionRef?.let { d -> Fig(d, Modifier.clip(CircleShape).clickable(role = Role.Button) { nav.go("cartable/$d") }.padding(horizontal = 4.dp), style = Divan.type.figureSmall, color = c.goldInk) }
                    }
                }
            }
        }
    }
}

/** The pipeline as lanes, one per step (§22.2): an item moves down as code moves it on. Stopped items have a lane of their own. */
@Composable
private fun PipelineBoard(items: List<MediaItem>, onOpen: (String) -> Unit) {
    val c = Divan.colors
    if (items.isEmpty()) return HqCard(Modifier.fillMaxWidth()) {
        Empty("آیتمی نیست", icon = DivanIcon.VIDEO, body = "برنامه‌ی مُهرشده هر بار طبق زمان‌بندی‌اش یک آیتم میسازد؛ آیتم یک‌باره را خودت میسازی.")
    }
    val stopped = items.filter { it.state in STOPPED }
    HqCard(Modifier.fillMaxWidth(), padding = androidx.compose.foundation.layout.PaddingValues(horizontal = 12.dp, vertical = 6.dp)) {
        STAGES.forEachIndexed { i, s ->
            if (i > 0) HorizontalDivider(color = c.lineDivider)
            val xs = items.filter { it.state in s.states }
            Lane(s.icon, s.fa, s.who, xs.size, if (xs.isEmpty()) null else c.softGold to c.goldInk) { for (x in xs) ItemCard(x) { onOpen(x.ref) } }
        }
        if (stopped.isNotEmpty()) {
            HorizontalDivider(color = c.lineDivider)
            Lane(DivanIcon.URGENT, "متوقف", "نگه‌داشته، شکست یا رد", stopped.size, c.softNegative to c.negative) { for (x in stopped) ItemCard(x) { onOpen(x.ref) } }
        }
    }
}

@Composable
private fun Lane(icon: DivanIcon, title: String, who: String, n: Int, tint: Pair<androidx.compose.ui.graphics.Color, androidx.compose.ui.graphics.Color>?, content: @Composable () -> Unit) {
    val c = Divan.colors
    Column(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Box(Modifier.size(32.dp).clip(CircleShape).background(tint?.first ?: c.tile), contentAlignment = Alignment.Center) { DIcon(icon, size = 16.dp, tint = tint?.second ?: c.textMuted) }
            Column(Modifier.weight(1f)) {
                Text(if (n > 0) "$title $n" else title, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                Text(who, style = Divan.type.micro, color = c.textMuted)
            }
        }
        if (n > 0) Column(verticalArrangement = Arrangement.spacedBy(8.dp)) { content() }
    }
}

@Composable
private fun ItemCard(x: MediaItem, onOpen: () -> Unit) {
    val c = Divan.colors
    val st = ITEM_STATE[x.state]
    val k = KIND_FA[x.kind] ?: KIND_FA.getValue("post")
    val mine = x.state == "waiting_owner"
    val bad = x.state == "held" || x.state == "failed"
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(if (mine) c.softGold else if (bad) c.softNegative else c.tile)
            .then(if (mine) Modifier.border(1.dp, c.lineTahrir, RoundedCornerShape(14.dp)) else Modifier)
            .clickable(role = Role.Button, onClickLabel = x.titleFa, onClick = onOpen).padding(10.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        RenderPreview(x.render, aspectOfItem(x), x.titleFa, Modifier.width(if (x.kind == "design") 80.dp else 48.dp), compact = true)
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                CoMark(x.company, height = 10.dp)
                Text(x.titleFa, Modifier.weight(1f), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                DIcon(k.icon, size = 12.dp, tint = c.textMuted)
                Text(k.fa, style = Divan.type.micro, color = c.textMuted)
                Fig(x.ref, style = Divan.type.figureSmall, color = c.textMuted)
                if (x.series != null) Fig(x.series, style = Divan.type.figureSmall, color = c.textMuted) else Text("یک‌باره", style = Divan.type.micro, color = c.textMuted)
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                LabelPill(st, x.state)
                Text(ago(x.updatedAt), style = Divan.type.micro, color = c.textMuted)
            }
        }
    }
}

/** One item whole (the web's ItemSheet): where it is, why it waits, its render, voice and files, the brief, the script with its
 *  sources, the shots, the composition as code, the seven checks, the media director's review and where it goes. A waiting item is
 *  sealed here through its card (🔏 `decision.approve` on the card); a published one comes down with the passkey. */
@Composable
fun ItemView(ref: String) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val ctx = LocalContext.current
    val act = activity()
    val c = Divan.colors
    val scope = rememberCoroutineScope()
    val q = rememberQuery("media:item:$ref", "media") { mediaItem(ref) }
    val series = rememberQuery("media:series::", "media") { series() }
    val companies = rememberCompanies()
    val seal = rememberAction()
    val other = rememberAction()
    var confirm by remember { mutableStateOf(false) }
    var sharing by remember { mutableStateOf(false) }
    val x = q.data
    val live = x?.live == true
    LaunchedEffect(live) { while (live) { delay(15_000); q.refresh() } }
    if (x == null) return if (q.error != null) ErrorBlock(q.error, { q.refresh() }) else Skeleton(Modifier.fillMaxWidth().height(380.dp), radius = 12.dp)
    val co = companyOf(companies, x.company)
    val sr = series.data?.firstOrNull { it.ref == x.series }
    val manual = x.publish.any { it.placement == "telegram_story" && it.externalId == null }
    val design = x.kind == "design"
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Text(
            buildAnnotatedString {
                append("${co.nameFa}، ${KIND_FA[x.kind]?.fa ?: x.kind}")
                if (x.series != null) { append("، برنامه‌ی "); fig(x.series); sr?.let { append(" «${it.titleFa}»") } } else append("، یک‌باره")
            },
            style = Divan.type.caption, color = c.textMuted,
        )
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            StageTrack(x.state, design)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                LabelPill(ITEM_STATE[x.state], x.state)
                x.topicFa?.let { Text(buildAnnotatedString { append("موضوع: "); append(it) }, style = Divan.type.caption, color = c.textSecondary) }
                Pill("ساخته‌ی هوش مصنوعی", Tone.NEUTRAL, icon = DivanIcon.INFO)
                Text("به‌روز ${ago(x.updatedAt)}", style = Divan.type.micro, color = c.textMuted)
            }
            x.stateNoteFa?.let { note ->
                val bad = x.state == "held" || x.state == "failed"
                Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(if (bad) c.softNegative else c.softWarning).padding(12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    DIcon(DivanIcon.URGENT, Modifier.padding(top = 2.dp), size = 16.dp, tint = if (bad) c.negative else c.warning)
                    RichText(note, Modifier.weight(1f), style = Divan.type.small, color = c.textPrimary)
                }
            }
        }
        // The owner's part: a waiting item's card, sealed here; a published item comes down through the same API.
        val d = x.decisionRef
        when {
            x.state == "waiting_owner" && d != null -> Column(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(c.softGold).border(1.dp, c.lineTahrir, RoundedCornerShape(16.dp)).padding(14.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                    SealButton(x.company, co.nameFa, co.nameEn, co.holding, busy = seal.busy, size = 72.dp) {
                        seal.media(toasts) {
                            val token = env.auth.stepUp(act, "decision.approve", d)
                            env.api.approve(d, null, token)
                            env.cache.invalidate("media", "decisions", "inbox")
                            q.refresh()
                            toasts.ok(if (manual) "ثبت شد که استوری را خودت گذاشتی؛ بقیه از API رسمی رفت." else "مُهر خورد و از API رسمی منتشر شد.")
                        }
                    }
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(if (manual) "فایل را بردار، خودت در کانال بگذار، بعد مُهر کن" else "مُهر انتشار این آیتم", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text("کارت", style = Divan.type.caption, color = c.textSecondary)
                            RefChip(d)
                        }
                        Text("با اثر انگشت یا چهره." + if (manual) " استوری کانال تلگرام در Bot API نیست." else "", style = Divan.type.caption, color = c.textSecondary)
                    }
                }
                x.render?.let { f ->
                    HqButton("فایل", {
                        if (!sharing) { sharing = true; scope.launch { try { shareFile(ctx, env, f) } catch (_: Exception) { toasts.error("فایل باز نشد.") } finally { sharing = false } } }
                    }, icon = DivanIcon.DOWNLOAD, loading = sharing)
                }
            }
            x.state == "published" -> Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("پایین آوردن از همان API رسمی است، هر جا پلتفرم اجازه بدهد.", Modifier.weight(1f), style = Divan.type.caption, color = c.textMuted)
                HqButton("پایین بیاور", { confirm = true }, variant = BtnVariant.DANGER, size = BtnSize.SM, icon = DivanIcon.REJECT)
            }
            d != null -> Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("کارت این آیتم:", style = Divan.type.caption, color = c.textMuted)
                RefChip(d)
            }
        }
        Block(if (design) "ماکاپ رندرشده" else "پیش‌نمایش رندر") {
            Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                RenderPreview(x.render, aspectOfItem(x), "رندر ${x.ref}", if (design) Modifier.fillMaxWidth() else Modifier.widthIn(max = 240.dp).fillMaxWidth())
            }
            x.render?.let { f ->
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    FileChip(f, if (f.mime.startsWith("video/")) DivanIcon.VIDEO else DivanIcon.IMAGE)
                    f.durationS?.let { Fig(secs(it), style = Divan.type.figureSmall, color = c.textMuted) }
                }
            }
        }
        x.voice?.let { v -> Block("صدا (روی خود هاب)") { AudioPlayer(v.id, "صدای ${x.ref}", compact = true) } }
        x.captions?.let { f -> Block("زیرنویس") { FileChip(f, DivanIcon.REPORT) } }
        if (x.assets.isNotEmpty()) Block("فایل‌ها") {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) { for (a in x.assets) FileChip(a, DivanIcon.IMAGE) }
        }
        x.briefMd?.let { b -> Block("brief") { Text(prose(b), Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), style = Divan.type.small, color = c.textPrimary) } }
        x.script?.let { s ->
            Block("سناریو · ${actorFa(s.by)}") {
                Md(s.textFa, Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), style = Divan.type.body, color = c.textPrimary)
                if (s.sources.isEmpty()) Text("بی‌منبع: هر عدد سناریو منبع میخواهد.", style = Divan.type.caption, color = c.negative)
                else Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    for (src in s.sources) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(2.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                        DIcon(DivanIcon.KNOWLEDGE, size = 13.dp, tint = c.textSecondary)
                        Text(SOURCE_FA[src.kind] ?: src.kind, style = Divan.type.micro, color = c.textMuted)
                        src.ref?.let { RefChip(it, tone = RefTone.NEUTRAL) }
                        src.url?.let { Fig(it.removePrefix("https://").removePrefix("http://"), Modifier.widthIn(max = 220.dp), style = Divan.type.figureSmall, color = c.goldInk) }
                        Text(prose(src.note), style = Divan.type.caption, color = c.textSecondary)
                    }
                }
            }
        }
        x.direction?.let { dr ->
            Block("کارگردانی · ${actorFa(dr.by)}") {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    for (s in dr.shots) Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(10.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Box(Modifier.size(24.dp).clip(CircleShape).background(c.card), contentAlignment = Alignment.Center) { Text(s.n.toString(), style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary) }
                            if (s.durationS > 0) Fig(secs(s.durationS), style = Divan.type.figureSmall.copy(fontSize = 10.sp), color = c.textMuted)
                        }
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Text(prose(s.visualFa), style = Divan.type.caption, color = c.textPrimary)
                            s.textOnScreenFa?.let { Text(prose("روی تصویر: «$it»"), style = Divan.type.caption, color = c.textSecondary) }
                            s.voiceFa?.let { Text(prose("صدا: «$it»"), style = Divan.type.caption, color = c.textMuted) }
                        }
                    }
                }
            }
        }
        x.composition?.let { comp ->
            Block("ترکیب‌بندی به‌صورت کد") {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                    Fig(if (comp.format == "html") "HTML · CSS · SVG" else "Lottie JSON", Modifier.clip(RoundedCornerShape(6.dp)).background(c.tile).padding(horizontal = 8.dp, vertical = 2.dp), style = Divan.type.figureSmall, color = c.textPrimary)
                    Fig("sha256 ${comp.sha256.take(12)}…", style = Divan.type.figureSmall, color = c.textMuted)
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        ActorAvatar(comp.by, size = 18.dp)
                        Text(actorFa(comp.by), style = Divan.type.micro, color = c.textSecondary)
                    }
                }
                Text("بی‌شبکه، فقط کتابخانه‌های مجاز از داخل image، تنها قلم IRANYekanX و پالت شرکت؛ Chromium بی‌سر آن را قاب به قاب در سندباکس رندر میکند.".let(::prose), style = Divan.type.micro, color = c.textMuted)
            }
        }
        if (!design || x.checks.isNotEmpty()) Block("چک‌ها (با کد)") { CheckGrid(x.checks, design) }
        x.qc?.let { qc ->
            Block("بازبینی مدیر رسانه", action = { LabelPill(QC_VERDICT[qc.verdict], qc.verdict) }) { Md(qc.noteMd, style = Divan.type.small, color = c.textPrimary) }
        }
        if (!design) Block("برنامه‌ی انتشار") { PublishRows(x.publish) }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            Text(buildAnnotatedString { append("هزینه: "); fig("${tokens(x.cost.tokens)} tok · ${usd(x.cost.usd)}", c.textSecondary); append(" (از پاکت ماهانه‌ی شرکت)") }, style = Divan.type.micro, color = c.textMuted)
            Text(com.coinepro.hq.designsystem.timesFig("ساخته ${jDateTime(x.createdAt)}"), style = Divan.type.micro, color = c.textMuted)
            x.deliverableRef?.let { RefChip(it, note = "تحویل") }
        }
    }
    if (confirm) AlertDialog(
        onDismissRequest = { confirm = false },
        containerColor = c.overlay,
        title = { Text("پایین آوردن این آیتم", style = Divan.type.h3) },
        text = { Text("از همان API رسمی حذف میشود، هر جا پلتفرم اجازه بدهد؛ جایی که اجازه ندهد را خودت از اپ پایین میآوری. برنامه‌ی انتشار ادامه دارد.", style = Divan.type.small, color = c.textSecondary) },
        confirmButton = {
            HqButton("با اثر انگشت پایین بیاور", {
                other.media(toasts) {
                    q.set(env.api.unpublish(x.ref) { a, t -> env.auth.stepUp(act, a, t) })
                    env.cache.invalidate("media", "decisions")
                    confirm = false
                    toasts.info("پایین آمد؛ جایی که API اجازه نداد را از خود اپ پایین بیاور.")
                }
            }, variant = BtnVariant.DANGER, icon = DivanIcon.SEAL, loading = other.busy)
        },
        dismissButton = { HqButton("نه", { confirm = false }, variant = BtnVariant.GHOST) },
    )
}

/** A one-off item: which company, what (a design is a UI mockup for the CTO), and the brief. */
@Composable
fun NewItem(onMade: (String) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    val companies = rememberCompanies().filter { it.kind != "holding" }
    val key = remember { UUID.randomUUID().toString() }
    var company by rememberSaveable { mutableStateOf<String?>(null) }
    var kind by rememberSaveable { mutableStateOf("reel") }
    var brief by rememberSaveable { mutableStateOf("") }
    val ok = company != null && brief.trim().length >= 8
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("کدام شرکت", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            ChipRow {
                for (co in companies) Chip(company == co.code, { company = co.code }) { ink ->
                    CoMark(co.code, height = 11.dp, ink = ink)
                    Text(co.nameFa ?: co.code, style = Divan.type.small, color = ink, maxLines = 1)
                }
            }
        }
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("چه چیزی", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                for ((k, m) in KIND_FA) Chip(kind == k, { kind = k }) { ink ->
                    DIcon(m.icon, size = 14.dp, tint = ink)
                    Text(m.fa, style = Divan.type.small, color = ink, maxLines = 1)
                }
            }
        }
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("brief", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            HqTextField(
                brief, { brief = it },
                if (kind == "design") "مثلاً: صفحه‌ی اول تریدیار را برای کاربر تازه ساده‌تر کن" else "مثلاً: ریلز ۱۵ ثانیه‌ای معرفی VIP رایگان تریدیار",
                Modifier.fillMaxWidth(), singleLine = false, minLines = 4, maxLength = 2000,
            )
            Text("هیچ داده‌ی مشتری؛ هر عدد منبع میخواهد و محتوای ترید هشدار ریسک.", style = Divan.type.micro, color = c.textMuted)
        }
        HqButton("بساز", {
            val co = company ?: return@HqButton
            action.media(toasts) {
                val x = env.api.createMediaItem(co, kind, brief.trim(), key = key)
                env.cache.invalidate("media", "decisions")
                toasts.ok("آیتم ${x.ref} ساخته شد؛ تیم رسانه‌ی همان شرکت از سناریو شروع میکند.")
                onMade(x.ref)
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.SEND, enabled = ok, loading = action.busy)
    }
}
