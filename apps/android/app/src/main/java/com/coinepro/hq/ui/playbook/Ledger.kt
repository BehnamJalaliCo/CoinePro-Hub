package com.coinepro.hq.ui.playbook

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
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
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.ledgerCountsFa
import com.coinepro.hq.core.data.topicBody
import com.coinepro.hq.core.data.topicSourceFa
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.TopicEntry
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.timesFig
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.HqSheet
import kotlinx.coroutines.delay

// Contract §47.4: the ledger of what was said («دفتر موضوع‌ها»). The owner's order: «هیچ روزی تکراری نباشد: ۳۶۵ روز، ۳۶۵ مطلب و ویدیوی
// متفاوت». Each company's topics and outside samples in a working group, kept by the hub and compared by code; here he reads them, adds one
// himself («این را قبلاً گفته‌ایم») and frees a line so it may be said again. Under each member company, beside its standing word.

/** The ledger's two kinds, as its two filters. */
private val KINDS = listOf("topic" to "موضوع‌ها", "reference" to "نمونه‌ها")
private const val PAGE = 30

/**
 * One member's «دفتر موضوع‌ها» under its row: how many topics and samples it holds, and the way in. Nothing on a hub before §47 (the
 * route is learnt once, then not asked again).
 */
@Composable
internal fun LedgerRow(group: String, company: String, nameFa: String) {
    val c = Divan.colors
    val q = rememberQuery("ledger-counts:$group:$company", "ledger", maxAgeMs = 30_000) { gated(HubFeature.TOPIC_LEDGER) { topics(group, company, limit = 1) } }
    val counts = q.data ?: return
    var open by rememberSaveable(group, company) { mutableStateOf(false) }
    Row(
        Modifier.fillMaxWidth().testTag("ledger-row").clickable(role = Role.Button, onClickLabel = "دفتر موضوع‌ها") { open = true }.padding(start = 24.dp, bottom = 8.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(1.dp)) {
            Text("دفتر موضوع‌ها", style = Divan.type.caption, color = c.textSecondary)
            Text(ledgerCountsFa(counts.topics, counts.references), style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        HqButton("باز کن", { open = true }, variant = BtnVariant.TEXT, size = BtnSize.SM)
    }
    if (open) HqSheet({ open = false }, "دفتر موضوع‌ها", sub = "آنچه $nameFa در این کارگروه گفته است؛ هیچ موضوعی دو بار ساخته نمیشود.") {
        LedgerBody(group, company)
    }
}

/**
 * The ledger itself: search, the two filters with their counts, the line he adds, then the lines newest first («بیشتر» for the next
 * page of [pageSize]). [kind0], [draft0] and [refused0] are for the screenshots.
 */
@Composable
internal fun LedgerBody(group: String, company: String, kind0: String = "topic", draft0: String = "", refused0: String? = null, pageSize: Int = PAGE) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    var kind by rememberSaveable(group, company) { mutableStateOf(kind0) }
    var search by rememberSaveable(group, company) { mutableStateOf("") }
    var applied by rememberSaveable(group, company) { mutableStateOf("") }
    LaunchedEffect(search) { if (search != applied) { delay(350); applied = search } }
    val q = rememberQuery("ledger:$group:$company:$kind:$applied:$pageSize", "ledger", maxAgeMs = 15_000) {
        gated(HubFeature.TOPIC_LEDGER) { topics(group, company, kind, applied, limit = pageSize) }
    }
    // the pages after the first, and what he freed a moment ago (gone before the next answer)
    val more = remember(q.data) { mutableStateListOf<TopicEntry>() }
    var cursor by remember(q.data) { mutableStateOf(q.data?.nextCursor) }
    val gone = remember(group, company) { mutableStateListOf<String>() }
    val loading = rememberAction()

    // ---- the line he adds himself
    var draft by rememberSaveable(group, company) { mutableStateOf(draft0) }
    var link by rememberSaveable(group, company) { mutableStateOf("") }
    var refused by rememberSaveable(group, company) { mutableStateOf(refused0) }
    val add = rememberAction()
    val body = topicBody(kind, draft, link)

    HqTextField(search, { search = it }, "جستجو در دفتر", Modifier.fillMaxWidth(), maxLength = 100)
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        val page = q.data
        for ((k, fa) in KINDS) FilterChip(
            fa, kind == k, { if (kind != k) { kind = k; refused = null } },
            count = page?.let { if (k == "topic") it.topics else it.references },
        )
    }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            HqTextField(draft, { draft = it; refused = null }, "این را قبلاً گفته‌ایم…", Modifier.weight(1f).testTag("ledger-add"), maxLength = 300)
            HqButton("افزودن", {
                val b = body ?: return@HqButton
                add.run(onError = { e: ApiException ->
                    // said before: the hub names the earlier line and its day, under the field
                    if (e.status == 409) { e.logged?.let { env.api.failures?.forget(it) }; refused = e.messageFa } else toasts.error(e.messageFa)
                }) {
                    env.api.addTopic(group, company, b)
                    draft = ""; link = ""; refused = null
                    env.cache.invalidate("ledger")
                    toasts.ok("در دفتر ثبت شد؛ دیگر ساخته نمیشود.")
                }
            }, size = BtnSize.MD, icon = DivanIcon.ADD, enabled = body != null, loading = add.busy)
        }
        // a sample is its link (its words are optional); the example is Latin alone, so it reads left to right
        if (kind == "reference") {
            Text("لینک نمونه", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.padding(start = 4.dp, top = 2.dp))
            HqTextField(link, { link = it; refused = null }, "https://…", Modifier.fillMaxWidth().testTag("ledger-link"), maxLength = 2000, figure = true)
        }
        refused?.let { Text(timesFig(it), style = Divan.type.caption, color = c.negative, modifier = Modifier.padding(horizontal = 4.dp)) }
    }

    val page = q.data
    val rows = (page?.items.orEmpty() + more).filter { it.id !in gone }.distinctBy { it.id }
    when {
        page == null && q.error != null -> Text(q.error?.messageFa ?: "دفتر خوانده نشد.", style = Divan.type.caption, color = c.negative)
        page == null -> Skeleton(Modifier.fillMaxWidth().height(160.dp), radius = 12.dp)
        rows.isEmpty() -> Text(
            if (applied.isNotBlank()) "چیزی با این جستجو در دفتر نیست." else if (kind == "reference") "هنوز نمونه‌ای ثبت نشده." else "هنوز موضوعی ثبت نشده.",
            style = Divan.type.caption, color = c.textMuted, modifier = Modifier.padding(vertical = 8.dp),
        )
        else -> Column(Modifier.fillMaxWidth().testTag("ledger-list").clip(RoundedCornerShape(12.dp)).background(c.tile).padding(horizontal = 12.dp, vertical = 2.dp)) {
            rows.forEachIndexed { i, e ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                LedgerLine(group, company, e) { gone.add(e.id) }
            }
        }
    }
    if (cursor != null && page != null) HqButton("بیشتر", {
        loading.run {
            val next = env.api.topics(group, company, kind, applied, cursor = cursor, limit = pageSize)
            more.addAll(next.items)
            cursor = next.nextCursor
        }
    }, Modifier.fillMaxWidth(), variant = BtnVariant.SECONDARY, icon = DivanIcon.NEXT, loading = loading.busy)
    Text(
        "ایجنت‌ها پیش از ساختن هر محتوا موضوعش را همین‌جا ثبت میکنند؛ موضوعی که این‌جاست دوباره ساخته نمیشود مگر آزادش کنی.",
        style = Divan.type.micro, color = c.textMuted,
    )
}

/** One line: its words, its day and where it came from; a sample's link (opens outside); and «آزاد کن», asked in place. */
@Composable
private fun LedgerLine(group: String, company: String, e: TopicEntry, onFreed: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val uri = LocalUriHandler.current
    val free = rememberAction()
    var asking by rememberSaveable(e.id) { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                val title = e.titleFa.trim().ifBlank { if (e.kind == "reference") "نمونه‌ی بیرونی" else "بی‌عنوان" }
                Text(timesFig(title), style = Divan.type.small.copy(fontWeight = FontWeight.Medium), color = c.textPrimary)
                Text(listOfNotNull(jDate(e.at).takeIf { e.at.isNotBlank() }, topicSourceFa(e.source).ifBlank { null }).joinToString(" · "), style = Divan.type.micro, color = c.textMuted)
            }
            if (!asking) HqButton("آزاد کن", { asking = true }, variant = BtnVariant.GHOST, size = BtnSize.SM, label = "این خط را آزاد کن")
        }
        e.url?.takeIf { it.isNotBlank() }?.let { url ->
            Fig(
                url.removePrefix("https://").removePrefix("http://").removePrefix("www.").trimEnd('/'),
                Modifier.clip(CircleShape).clickable(role = Role.Button, onClickLabel = "باز کردن لینک") { runCatching { uri.openUri(url) } }.padding(vertical = 2.dp),
                style = Divan.type.figureSmall, color = c.lapis,
            )
        }
        if (asking) Row(Modifier.fillMaxWidth().padding(top = 2.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("دوباره قابل ساخت میشود", style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.weight(1f))
            HqButton("آزاد کن", {
                free.run {
                    env.api.freeTopic(group, company, e.id)
                    onFreed()
                    env.cache.invalidate("ledger")
                    toasts.ok("آزاد شد؛ دوباره میشود ساختش.")
                }
            }, variant = BtnVariant.SECONDARY, size = BtnSize.SM, loading = free.busy)
            HqButton("نه", { asking = false }, variant = BtnVariant.TEXT, size = BtnSize.SM, enabled = !free.busy)
        }
    }
}
