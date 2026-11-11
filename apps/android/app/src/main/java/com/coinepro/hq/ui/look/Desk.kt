package com.coinepro.hq.ui.look

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.DESK_EMPTY_FA
import com.coinepro.hq.core.data.DESK_FA
import com.coinepro.hq.core.data.ROUTE_WAITS_FA
import com.coinepro.hq.core.data.bestHourOf
import com.coinepro.hq.core.data.cancellable
import com.coinepro.hq.core.data.cancelling
import com.coinepro.hq.core.data.deskAt
import com.coinepro.hq.core.data.deskDayFa
import com.coinepro.hq.core.data.deskEmpty
import com.coinepro.hq.core.data.deskLead
import com.coinepro.hq.core.data.deskLineFa
import com.coinepro.hq.core.data.deskQueueWordFa
import com.coinepro.hq.core.data.deskRatio
import com.coinepro.hq.core.data.deskSorted
import com.coinepro.hq.core.data.quietLine
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.net.DeskCard
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.bidi
import com.coinepro.hq.designsystem.facts
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.sep
import com.coinepro.hq.designsystem.silverLine
import com.coinepro.hq.designsystem.stagger
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.outputs.CancelAsk
import com.coinepro.hq.ui.outputs.KIND_FA
import com.coinepro.hq.ui.outputs.OpenLink
import com.coinepro.hq.ui.outputs.PublishFor
import com.coinepro.hq.ui.outputs.PublishSeed
import com.coinepro.hq.ui.outputs.PublishStateWord
import com.coinepro.hq.ui.outputs.publishNote
import com.coinepro.hq.ui.outputs.rememberPublishCancel
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.served
import kotlinx.coroutines.delay

// ⟨1.0.1⟩ Part C, «میز انتشار» (C2.3, feature 43; contract §55.2): one place for everything that can go out, is set to go out, or
// went out, of every company. Three sections, each hidden while it is empty: «آماده‌ی انتشار» (the media itself, large, in its
// network's shape, with the company, the account, the caption, the account's best hour, and «تأیید و انتشار»: only the FIRST card's is
// the full gold, the others are outlined), «در صف» (set for an hour or on its way, soonest first, each taken back in place) and
// «منتشرشده» (its link, a failure with its reason and a quiet «دوباره», a cancelled one as «لغو شد»). A company whose publishing path
// is not set yet has no action and says the technical team sets it: never the owner's step. On a hub before §55 the page says so, and
// its tab and the home's line are hidden.

/** The desk as the hub serves it; null data on a hub before §55.2 (learnt once: the feature is then hidden everywhere). */
@Composable
internal fun rememberPublishDesk(company: String? = null) =
    rememberQuery("publish-desk:${company.orEmpty()}", "publish", "deliverables", maxAgeMs = 15_000) { gated(HubFeature.PUBLISH_DESK) { publishDesk(company) } }

/** «خروجی‌ها | میز انتشار»: the two halves of where outputs live ([here]: the route of the page it is on). Nothing on a hub that
 *  does not serve the desk. */
@Composable
fun OutputsTabs(here: String, modifier: Modifier = Modifier) {
    if (!served(HubFeature.PUBLISH_DESK)) return
    val desk = rememberPublishDesk().data ?: return
    val nav = LocalNav.current
    val c = Divan.colors
    val shape = RoundedCornerShape(8.dp)
    Row(modifier.fillMaxWidth().testTag("outputs-tabs").clip(RoundedCornerShape(10.dp)).background(c.tile).padding(4.dp).selectableGroup()) {
        for ((route, label, count) in listOf(Triple("outputs", "خروجی‌ها", 0), Triple("publish-desk", DESK_FA, desk.ready.size))) {
            val on = route == here
            Row(
                Modifier.weight(1f).height(36.dp).clip(shape).then(if (on) Modifier.background(c.raised).border(1.dp, silverLine(), shape) else Modifier)
                    .selectable(on, role = Role.Tab) { if (!on) nav.go(route) },
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp, Alignment.CenterHorizontally),
            ) {
                Text(label, style = Divan.type.small.copy(fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal), color = if (on) c.textPrimary else c.textSecondary, maxLines = 1)
                if (count > 0) Text("$count", style = Divan.type.micro, color = c.textMuted, maxLines = 1)
            }
        }
    }
}

/** One line for the home: how many outputs are ready to go out, and the way to the desk. Nothing on a hub without the desk. */
@Composable
fun DeskLine(modifier: Modifier = Modifier) {
    if (!served(HubFeature.PUBLISH_DESK)) return
    val desk = rememberPublishDesk().data ?: return
    val nav = LocalNav.current
    val c = Divan.colors
    Row(
        modifier.fillMaxWidth().heightIn(min = 48.dp).testTag("desk-line").clip(RoundedCornerShape(12.dp)).background(c.card)
            .clickable(role = Role.Button, onClickLabel = DESK_FA) { nav.go("publish-desk") }.padding(horizontal = 14.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text(DESK_FA, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 1)
        Text(remember(desk) { facts(*deskLineFa(desk).toTypedArray()) }, style = Divan.type.caption, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
        DIcon(DivanIcon.NEXT, size = 16.dp, tint = c.textMuted)
    }
}

// ---------------------------------------------------------------------------------------------- the cards --
private fun seedOf(k: DeskCard) = PublishSeed(caption = k.caption, account = k.account, cover = k.cover?.id, best = k.best)

/** Whose it is and where it goes: the company's mark and name, the network, the account (or how many there are to choose from). */
@Composable
private fun Who(k: DeskCard) {
    val c = Divan.colors
    Row(Modifier.testTag("desk-who"), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        CompanyMark(k.company, height = 14.dp, mono = true, ink = c.textSecondary)
        Text(
            remember(k) {
                buildAnnotatedString {
                    pushStyle(androidx.compose.ui.text.SpanStyle(fontWeight = FontWeight.SemiBold, color = c.textPrimary))
                    bidi(k.companyFa.ifBlank { "شرکت" })
                    pop()
                    sep()
                    append("اینستاگرام")
                    val account = k.account
                    if (account != null) { sep(); fig("@$account") } else if (k.accounts.size > 1) { sep(); append("${k.accounts.size} حساب") }
                }
            },
            style = Divan.type.caption, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis,
        )
    }
}

/** A small poster: the cover when there is one, else the file itself. */
@Composable
private fun Thumb(k: DeskCard) {
    FaceFrame(Modifier.size(width = 48.dp, height = 64.dp), radius = 10.dp) { FileFace((k.cover ?: k.file).asFile(), sign = 22.dp) }
}

@Composable
private fun ReadyCard(k: DeskCard, lead: Boolean, index: Int, onAsk: () -> Unit) {
    val c = Divan.colors
    val nav = LocalNav.current
    var all by rememberSaveable(k.output) { mutableStateOf(false) }
    val best = bestHourOf(k.best)
    Column(
        Modifier.fillMaxWidth().stagger(index).testTag("desk-ready").clip(RoundedCornerShape(16.dp)).background(c.card).padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Who(k)
        HeroMedia(k.file.asFile(), deskRatio(k.kind), cover = k.cover?.asFile())
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Column(Modifier.clip(RoundedCornerShape(8.dp)).clickable(role = Role.Button, onClickLabel = "خروجی‌اش") { nav.go("outputs/${k.output}") }) {
                Text(plain(quietLine(k.titleFa)), style = Divan.type.bodyStrong, color = c.textPrimary)
                Text(remember(k.kind, k.files) { facts(KIND_FA[k.kind], if (k.files > 1) "${k.files} فایل" else null) }, style = Divan.type.micro, color = c.textMuted)
            }
            // The first two lines of the caption; a tap opens all of it.
            k.caption?.trim()?.ifBlank { null }?.let { caption ->
                Text(
                    plain(caption), style = Divan.type.small, color = c.textSecondary, maxLines = if (all) Int.MAX_VALUE else 2, overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.fillMaxWidth().testTag("desk-caption").clip(RoundedCornerShape(8.dp)).clickable(role = Role.Button, onClickLabel = if (all) "کوتاه کن" else "همه‌ی کپشن") { all = !all },
                )
            }
            if (best != null) Text(buildAnnotatedString { append("بهترین ساعت این حساب: "); fig(best) }, style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.testTag("desk-best"))
            k.groupFa?.trim()?.ifBlank { null }?.let { Text("کارگروه «${quietLine(it)}»", style = Divan.type.micro, color = c.textMuted) }
        }
        // A company whose publishing path is not set yet: no action, and one calm line (never the owner's step).
        if (!k.routeReady) Text(ROUTE_WAITS_FA, style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.testTag("route-not-ready"))
        else HqButton("تأیید و انتشار", onAsk, Modifier.fillMaxWidth(), variant = if (lead) BtnVariant.PRIMARY else BtnVariant.SECONDARY, size = BtnSize.LG)
    }
}

@Composable
private fun QueueCard(k: DeskCard, index: Int, onChanged: () -> Unit) {
    val c = Divan.colors
    val p = k.publish
    val job = p?.job
    val cancel = rememberPublishCancel { onChanged() }
    val canCancel = served(HubFeature.PUBLISH_CANCEL)
    val asking = job != null && cancel.asking == job
    val word = deskQueueWordFa(k.state)
    val at = deskAt(k)
    Column(
        Modifier.fillMaxWidth().stagger(index).testTag("desk-queue").clip(RoundedCornerShape(14.dp)).background(c.card).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Thumb(k)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(
                    if (word != null) buildAnnotatedString { append(word) } else buildAnnotatedString { append(deskDayFa(at)); append(" "); fig(jTime(at)) },
                    style = Divan.type.bodyStrong, color = c.textPrimary, maxLines = 1, modifier = Modifier.testTag("desk-time"),
                )
                Text(plain(quietLine(k.titleFa)), style = Divan.type.small, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(
                    remember(k) { facts(k.companyFa, k.account?.let { "@$it" }, KIND_FA[k.kind], "خودکار".takeIf { p?.auto == true }) },
                    style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis,
                )
            }
            if (p != null && job != null && canCancel && !asking && cancellable(p)) HqButton("لغو", { cancel.ask(job) }, variant = BtnVariant.TEXT, size = BtnSize.SM, label = "لغو این انتشار")
        }
        if (k.state == "waiting_setup") Text(ROUTE_WAITS_FA, style = Divan.type.caption, color = c.textSecondary)
        // what the hub says of it meanwhile («در حال لغو», «لغو انجام نشد (…)»), and what it refused of his cancel
        (publishNote(p) ?: p?.takeIf { k.state != "waiting_setup" && !cancelling(it) }?.noteFa?.trim()?.ifBlank { null })?.let { Text(plain(it), style = Divan.type.micro, color = c.textMuted) }
        job?.let { j -> cancel.refused[j] }?.let { Text(plain(it), style = Divan.type.micro, color = c.negative) }
        if (asking && job != null) CancelAsk(job, cancel)
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun DoneCard(k: DeskCard, index: Int, onAgain: () -> Unit) {
    val c = Divan.colors
    val p = k.publish
    Column(
        Modifier.fillMaxWidth().stagger(index).testTag("desk-done").clip(RoundedCornerShape(14.dp)).background(c.card).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Thumb(k)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(plain(quietLine(k.titleFa)), style = Divan.type.bodyStrong, color = c.textPrimary, maxLines = 2, overflow = TextOverflow.Ellipsis)
                Text(remember(k) { facts(k.companyFa, k.account?.let { "@$it" }, KIND_FA[k.kind]) }, style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
                // Where it stands and when, and the one thing to do about it, on a line of their own (a title is never cut for them).
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                    if (p != null) PublishStateWord(p)
                    Text(ago(p?.publishedAt ?: k.at), style = Divan.type.micro, color = c.textMuted, maxLines = 1)
                    val url = p?.url
                    if (k.state == "published" && url != null) OpenLink(url)
                    if (k.state == "failed" && k.routeReady) HqButton("دوباره", onAgain, variant = BtnVariant.SECONDARY, size = BtnSize.SM)
                }
            }
        }
        if (k.state == "failed") p?.noteFa?.trim()?.ifBlank { null }?.let { Text(plain(it), style = Divan.type.caption, color = c.negative, modifier = Modifier.testTag("desk-note")) }
    }
}

@Composable
private fun SectionHead(title: String, count: Int) {
    val c = Divan.colors
    Row(Modifier.fillMaxWidth().padding(top = 4.dp), verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(title, style = Divan.type.h3, color = c.textPrimary, modifier = Modifier.semantics { heading() })
        Text("$count", style = Divan.type.caption, color = c.textMuted)
    }
}

/** The desk itself. [company0]: only this company's (the hub filters). */
@Composable
fun PublishDeskScreen(company0: String? = null) {
    val c = Divan.colors
    val q = rememberPublishDesk(company0)
    val served = served(HubFeature.PUBLISH_DESK)
    val desk = remember(q.data) { q.data?.let(::deskSorted) }
    var asking by remember { mutableStateOf<DeskCard?>(null) }
    // While something is on its way the desk is read again often; while something waits for its hour, once a minute.
    val moving = desk?.queue.orEmpty().any { k -> k.state == "publishing" || k.publish?.let(::cancelling) == true }
    val waiting = desk?.queue.orEmpty().isNotEmpty()
    LaunchedEffect(moving, waiting) {
        while (moving || waiting) { delay(if (moving) 5_000 else 60_000); q.refresh() }
    }
    Page(onRefresh = { q.refresh() }, refreshing = q.state.refreshing) {
        item(key = "head") {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                PageHeader(DESK_FA, eyebrow = "هر خروجی آماده، یک جا")
                OutputsTabs("publish-desk")
            }
        }
        when {
            // A hub before §55: the page (reached by a link) says so; its entries are hidden.
            !served -> item(key = "old") {
                Empty("میز انتشار بعد از به‌روزرسانی ستاد می‌آید", icon = DivanIcon.SEND, body = "تا آن وقت، هر خروجی را از صفحه‌ی خودش منتشر کن.")
            }
            desk == null && q.error != null -> item(key = "error") { ErrorBlock(q.error, { q.refresh() }) }
            desk == null -> {
                item(key = "sk1") { Skeleton(Modifier.fillMaxWidth().height(288.dp), radius = 16.dp) }
                item(key = "sk2") { Skeleton(Modifier.fillMaxWidth().height(80.dp), radius = 14.dp) }
            }
            deskEmpty(desk) -> item(key = "empty") {
                Box(Modifier.fillMaxWidth().testTag("desk-empty").clip(RoundedCornerShape(16.dp)).background(c.card).padding(horizontal = 20.dp, vertical = 40.dp), contentAlignment = Alignment.Center) {
                    Text(DESK_EMPTY_FA, style = Divan.type.small, color = c.textSecondary, textAlign = TextAlign.Center)
                }
            }
            else -> {
                // Only the first card that can be published carries the full gold.
                val lead = deskLead(desk.ready)
                if (desk.ready.isNotEmpty()) {
                    item(key = "h-ready") { SectionHead("آماده‌ی انتشار", desk.ready.size) }
                    itemsIndexed(desk.ready, key = { _, k -> "r-${k.output}" }) { i, k -> ReadyCard(k, lead = k.output == lead, index = i) { asking = k } }
                }
                if (desk.queue.isNotEmpty()) {
                    item(key = "h-queue") { SectionHead("در صف", desk.queue.size) }
                    itemsIndexed(desk.queue, key = { _, k -> "q-${k.output}-${k.publish?.job ?: k.file.id}" }) { i, k -> QueueCard(k, i) { q.refresh() } }
                }
                if (desk.done.isNotEmpty()) {
                    item(key = "h-done") { SectionHead("منتشرشده", desk.done.size) }
                    itemsIndexed(desk.done, key = { _, k -> "d-${k.output}-${k.publish?.job ?: k.file.id}" }) { i, k -> DoneCard(k, i) { asking = k } }
                }
                item(key = "foot") { Spacer(Modifier.height(4.dp)) }
            }
        }
    }
    asking?.let { k -> PublishFor(k.output, k.file.id, seedOf(k), onDismiss = { asking = null }) { q.refresh() } }
}
