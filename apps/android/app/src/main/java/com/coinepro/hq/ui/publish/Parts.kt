package com.coinepro.hq.ui.publish

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.data.PUB_HELD_FA
import com.coinepro.hq.core.data.atHandle
import com.coinepro.hq.core.data.countdownFa
import com.coinepro.hq.core.data.faHour
import com.coinepro.hq.core.data.faNum
import com.coinepro.hq.core.data.pubKindFa
import com.coinepro.hq.core.data.pubStateFa
import com.coinepro.hq.core.data.pubStateTone
import com.coinepro.hq.core.data.setProgressFa
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.net.FileRef
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.PlannedItem
import com.coinepro.hq.core.net.PubFile
import com.coinepro.hq.core.net.PublicationCard
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.IconBtn
import com.coinepro.hq.designsystem.LiveDot
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.facts
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.silverLine
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.look.FileFace
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.served
import kotlinx.coroutines.delay

// ⟨1.39⟩ Contract §60, the publish centre (D6, the owner's approval of 2026-11-17): its queries, its tabs, a row's cover and state, a day's
// line, and the two cards of the home. Nothing of a publication is written in the app: every word, hour and count is the hub's row.

internal val PUB_TAGS = arrayOf("publish", "publications")

@Composable
internal fun rememberPubToday(account: String? = null) =
    rememberQuery("pub-today:${account.orEmpty()}", *PUB_TAGS, maxAgeMs = 30_000) { gated(HubFeature.PUBLICATIONS) { publicationsToday(account = account) } }

@Composable
internal fun rememberPubTree() = rememberQuery("pub-tree", *PUB_TAGS, maxAgeMs = 60_000) { gated(HubFeature.PUBLICATIONS) { publicationsTree() } }

@Composable
internal fun rememberPublication(ref: String) = rememberQuery("publication:$ref", *PUB_TAGS, maxAgeMs = 30_000) { gated(HubFeature.PUBLICATIONS) { publication(ref) } }

@Composable
internal fun rememberWaiting() = rememberQuery("pub-waiting", *PUB_TAGS, "decisions", maxAgeMs = 30_000) { gated(HubFeature.PUBLICATIONS) { publicationsWaiting() } }

/** The centre's routes, in its tabs' order. */
internal val CENTRE_TABS = listOf("publish" to "امروز", "publish-desk" to "میز", "publish/calendar" to "تقویم", "publish/archive" to "بایگانی")

/** «مرکز انتشار» with its search, and its four tabs; [here] the tab's route. Read again every minute while it is on screen. */
@Composable
fun CentreHead(here: String) {
    val nav = LocalNav.current
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        PageHeader("مرکز انتشار", eyebrow = "هر چه رفته یا میرود، از هر پیج", actions = {
            IconBtn(DivanIcon.SEARCH, "جستجو در همه‌ی انتشارها", { nav.go("publish/search") })
        })
        val shape = RoundedCornerShape(10.dp)
        Row(Modifier.fillMaxWidth().testTag("centre-tabs").clip(RoundedCornerShape(14.dp)).background(c.tile).padding(4.dp).selectableGroup()) {
            for ((route, label) in CENTRE_TABS) {
                val on = route == here
                Box(
                    Modifier.weight(1f).height(36.dp).clip(shape).then(if (on) Modifier.background(c.raised).border(1.dp, silverLine(), shape) else Modifier)
                        .selectable(on, role = Role.Tab) { if (!on) nav.go(route) },
                    contentAlignment = Alignment.Center,
                ) { Text(label, style = Divan.type.small.copy(fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal), color = if (on) c.textPrimary else c.textSecondary, maxLines = 1) }
            }
        }
    }
}

// --------------------------------------------------------------------------------------------------------- a cover --
private val TINTS = listOf(Color(0xFF173A33), Color(0xFF182544), Color(0xFF2A1F3D), Color(0xFF3B2C12), Color(0xFF3A1E24), Color(0xFF1E3340))

/** The page's own quiet tint under a cover that has not arrived (or has none): the same for a page everywhere. */
fun tintOf(account: String): Color = TINTS[Math.floorMod(account.removePrefix("@").hashCode(), TINTS.size)]

fun imageRef(id: String, name: String = "cover.jpg") = FileRef(id = id, name = name, mime = "image/jpeg", kind = "image")
fun PubFile.asFile() = FileRef(
    id = fileId, name = name ?: role, mime = mime ?: "application/octet-stream", size = size ?: 0,
    kind = when { (mime ?: "").startsWith("video/") -> "video"; (mime ?: "").startsWith("image/") -> "image"; else -> "document" },
)

/** A row's cover in a 9:16 frame: its picture when there is one, else the page's tint with the title on it (never an empty box). */
@Composable
fun PubCover(account: String, title: String, thumb: String?, modifier: Modifier, radius: Dp = 10.dp, label: String? = null, text: Boolean = true) {
    val shape = RoundedCornerShape(radius)
    Box(modifier.clip(shape).background(tintOf(account)), contentAlignment = Alignment.BottomStart) {
        if (thumb != null) FileFace(imageRef(thumb), mark = false)
        else if (text) Text(
            title, style = Divan.type.micro.copy(fontWeight = FontWeight.Bold, fontSize = 9.sp, lineHeight = 12.sp), color = Color(0xFFF7F2E6),
            maxLines = 3, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(5.dp),
        )
        if (label != null) Box(Modifier.align(Alignment.TopStart).padding(4.dp).clip(CircleShape).background(Color.Black.copy(alpha = 0.55f)).padding(horizontal = 6.dp, vertical = 1.dp)) {
            Text(label, style = Divan.type.micro.copy(fontSize = 9.sp, lineHeight = 13.sp, fontWeight = FontWeight.Bold), color = Color(0xFFF7F2E6), maxLines = 1)
        }
    }
}

/** Something still to be made: a dashed frame. */
@Composable
fun DashedFrame(modifier: Modifier, radius: Dp = 10.dp, content: @Composable () -> Unit = {}) {
    val c = Divan.colors
    Box(modifier.drawWithDash(c.lineStrong, radius), contentAlignment = Alignment.Center) { content() }
}

internal fun Modifier.drawWithDash(color: Color, radius: Dp): Modifier = this.drawBehind {
    drawRoundRect(
        color = color, cornerRadius = androidx.compose.ui.geometry.CornerRadius(radius.toPx()),
        style = androidx.compose.ui.graphics.drawscope.Stroke(width = 1.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(6.dp.toPx(), 4.dp.toPx()))),
    )
}

/** A row's state as a pill (a set: its progress). */
@Composable
fun PubState(card: PublicationCard, countdown: Boolean = true) {
    val set = card.set
    val now = HqClock.millis()
    when {
        set != null && set.n > 0 -> Pill(setProgressFa(set.done, set.n), if (set.done > 0) com.coinepro.hq.core.format.Tone.POS else com.coinepro.hq.core.format.Tone.NEUTRAL)
        card.state == "scheduled" && countdown && countdownFa(card.at, now)?.let { (com.coinepro.hq.core.format.instant(card.at)?.toEpochMilli() ?: 0) - now < 6 * 3_600_000 } == true ->
            Pill(countdownFa(card.at, now)!!, com.coinepro.hq.core.format.Tone.GOLD, icon = DivanIcon.TIME)
        else -> Pill(pubStateFa(card.state), pubStateTone(card.state), dot = card.state != "published", live = card.state == "publishing",
            icon = if (card.state == "published") DivanIcon.SEAL else if (card.state == "held") DivanIcon.PAUSE else null)
    }
}

/** A set's slides as a strip: green what went out, the rest quiet. */
@Composable
fun SetStrip(n: Int, done: Int, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Row(modifier.fillMaxWidth().height(4.dp), horizontalArrangement = Arrangement.spacedBy(2.dp)) {
        repeat(n.coerceIn(1, 15)) { i -> Box(Modifier.weight(1f).fillMaxSize().clip(RoundedCornerShape(2.dp)).background(if (i < done) c.positive else c.raised)) }
    }
}

/** One row of a list: the cover, the title, the page with its source, and its state. */
@Composable
fun PubRow(card: PublicationCard, modifier: Modifier = Modifier, sub: String? = null, onClick: (() -> Unit)? = null, trailing: (@Composable RowScope.() -> Unit)? = null) {
    val c = Divan.colors
    val nav = LocalNav.current
    val held = card.state == "held"
    val failed = card.state == "failed"
    val set = card.set
    val shape = RoundedCornerShape(16.dp)
    Row(
        modifier.fillMaxWidth().testTag("pub-row").clip(shape).background(c.card)
            .border(1.dp, if (held) c.warning.copy(alpha = 0.45f) else if (failed) c.negative.copy(alpha = 0.45f) else c.lineHairline, shape)
            .clickable(role = Role.Button, onClickLabel = "باز کردن") { onClick?.invoke() ?: nav.go(if (set != null) "publication/${card.ref}/set" else "publication/${card.ref}") }
            .padding(start = 8.dp, end = 10.dp, top = 8.dp, bottom = 8.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        PubCover(card.account, if (set != null) "${faNum(set.n)} تا" else pubKindFa(card.kind), card.thumbFileId, Modifier.size(width = 40.dp, height = 56.dp))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(plain(card.titleFa), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 2, overflow = TextOverflow.Ellipsis)
            if (set != null) SetStrip(set.n, set.done)
            val line = when {
                held -> card.stateNoteFa ?: PUB_HELD_FA
                failed -> card.stateNoteFa ?: "انجام نشد"
                sub != null -> sub
                set != null -> listOfNotNull(atHandle(card.account), set.nextAt?.let { "بعدی ${faHour(it)}" }, card.automationFa).joinToString(" · ")
                else -> listOfNotNull(atHandle(card.account), card.automationFa).joinToString(" · ")
            }
            Text(plain(line), style = Divan.type.micro, color = if (held) c.warning else if (failed) c.negative else c.textMuted, maxLines = 2, overflow = TextOverflow.Ellipsis)
        }
        if (trailing != null) trailing() else PubState(card)
    }
}

/** What an automation still makes today: dashed, with its build hour. */
@Composable
fun PlanRow(p: PlannedItem, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val nav = LocalNav.current
    val building = p.state == "building"
    Row(
        modifier.fillMaxWidth().testTag("plan-row").clip(RoundedCornerShape(16.dp)).drawWithDash(c.lineStrong, 16.dp)
            .clickable(role = Role.Button, onClickLabel = "اتوماسیونش") { if (p.automation.isNotBlank()) nav.go("automation/${p.automation}") }
            .padding(start = 8.dp, end = 10.dp, top = 8.dp, bottom = 8.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        DashedFrame(Modifier.size(width = 40.dp, height = 56.dp)) { Text("…", style = Divan.type.caption, color = c.textMuted) }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(plain(p.automationFa.ifBlank { p.titleFa }), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(plain(listOf(atHandle(p.account), if (building) "در کارگاه ساخته میشود" else "ساخته میشود · از ${faHour(p.buildAt)}").filter { it.isNotBlank() }.joinToString(" · ")), style = Divan.type.micro, color = c.textMuted, maxLines = 1)
        }
        Pill(if (building) "در ساخت" else "ساخت ${faHour(p.buildAt)}", com.coinepro.hq.core.format.Tone.LAPIS, dot = building, live = building)
    }
}

/** The «اکنون» line between what went and what comes. */
@Composable
fun NowLine(minute: Int) {
    val c = Divan.colors
    Row(Modifier.fillMaxWidth().testTag("now-line"), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("%02d:%02d".format(minute / 60, minute % 60), style = Divan.type.micro.copy(fontWeight = FontWeight.Bold), color = c.goldInk, modifier = Modifier.width(40.dp))
        LiveDot(c.goldFill)
        Box(Modifier.weight(1f).height(1.dp).background(c.goldFill.copy(alpha = 0.6f)))
        Text("اکنون", style = Divan.type.micro, color = c.goldInk)
    }
}

/** «منتظر شما · n»: only when something cannot move without him (§60.2); none, nothing at all. */
@Composable
fun WaitingBanner(modifier: Modifier = Modifier) {
    if (!served(HubFeature.PUBLICATIONS)) return
    val w = rememberWaiting().data ?: return
    if (w.items.isEmpty()) return
    val nav = LocalNav.current
    val c = Divan.colors
    val shape = RoundedCornerShape(16.dp)
    Row(
        modifier.fillMaxWidth().testTag("waiting-banner").clip(shape).background(c.softGold).border(1.dp, c.goldFill.copy(alpha = 0.35f), shape)
            .clickable(role = Role.Button, onClickLabel = "منتظر شما") { nav.go("publish/waiting") }.padding(horizontal = 14.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text("منتظر شما · ${faNum(w.items.size)}", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
        Text(plain(w.items.first().titleFa), style = Divan.type.micro, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
        DIcon(DivanIcon.NEXT, size = 14.dp, tint = c.textMuted)
    }
}

/** A query read again every [everyMs] while it is on screen (the centre's live hours, the countdowns). */
@Composable
fun Every(everyMs: Long, tick: () -> Unit) {
    LaunchedEffect(everyMs) { while (true) { delay(everyMs); tick() } }
}

/** A row of quiet facts under a title, the app's way. */
@Composable
fun FactLine(vararg parts: String?, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Text(remember(*parts) { facts(*parts) }, style = Divan.type.micro, color = c.textMuted, maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = modifier)
}

/** The live stream's publication events read the centre's queries again (besides the cache's own tags). */
@Composable
fun OnPublication(refresh: () -> Unit) {
    val env = LocalEnv.current
    LaunchedEffect(env) { env.stream.events.collect { e -> if (e.type.startsWith("publication.")) refresh() } }
}

internal fun Modifier.minRow() = this.heightIn(min = 44.dp)
