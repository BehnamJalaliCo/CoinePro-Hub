package com.coinepro.hq.ui.live

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.absoluteOffset
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.requiredSize
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import com.coinepro.hq.designsystem.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.State
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.AbsoluteAlignment
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipPath
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.Beat
import com.coinepro.hq.core.data.CompanyLive
import com.coinepro.hq.core.data.FlowInk
import com.coinepro.hq.core.data.FlowLive
import com.coinepro.hq.core.data.LINK_KIND_FA
import com.coinepro.hq.core.data.LiveRules
import com.coinepro.hq.core.data.LiveState
import com.coinepro.hq.core.data.RingPlan
import com.coinepro.hq.core.data.ServerLive
import com.coinepro.hq.core.data.activityOrder
import com.coinepro.hq.core.data.ageFa
import com.coinepro.hq.core.data.companyStateOf
import com.coinepro.hq.core.data.faNum
import com.coinepro.hq.core.data.flowEdge
import com.coinepro.hq.core.data.flowFa
import com.coinepro.hq.core.data.flowInk
import com.coinepro.hq.core.data.flowLegs
import com.coinepro.hq.core.data.frozen
import com.coinepro.hq.core.data.isoMs
import com.coinepro.hq.core.data.linkKindFa
import com.coinepro.hq.core.data.ringPlan
import com.coinepro.hq.core.data.serverAngles
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.net.CompanyLink
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.NetNode
import com.coinepro.hq.core.net.NetworkMap
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.Grammar
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.LocalReducedMotion
import com.coinepro.hq.designsystem.Monogram
import com.coinepro.hq.designsystem.ParticleField
import com.coinepro.hq.designsystem.ParticleChips
import com.coinepro.hq.designsystem.ParticleLayer
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.animateBreak
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanFixed
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.rememberAppVisible
import com.coinepro.hq.designsystem.rememberCeremony
import com.coinepro.hq.designsystem.rippleOnce
import com.coinepro.hq.designsystem.timesFig
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v16.companyColor
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlinx.coroutines.delay

// Contract §42 ⟨1.24⟩ ⟨0.20.0⟩, design/LIVE_VIEWS.md §5: the holding's network map, live (HM-1, HM-2, HM-3, HM-8). The holding seal in
// the centre (the hub; it never moves, and its gem brightens only on the owner's acts), every company from data on the inner ring (any
// number: smaller, then a second ring, then «بقیه · n»), each company's servers on the outer ring. Three kinds of edge: the work spoke
// hub ↔ company (a gold hairline), the runner link hub ↔ server (lapis; dashed over the public road; red and broken when silent), and the
// owner's company links as chords (gold ink when on, dotted when off). Every particle is one event; a request between two companies
// travels A → hub → B, because that is the truth (servers never talk to each other). A frozen stream stops the particles and the map
// says «قدیمی»: a frozen map must never look like a calm holding. Every company and server is also a row of the table (HM-8).

/** The links of the owner's canvas (§35.6): the companies (kind `company`) and their chords. */
@Composable
fun rememberHoldingLinks() = rememberQuery("links", "links", "office", maxAgeMs = 60_000) { gated(HubFeature.SESSIONS) { links() } }

/** «runner روی سرور ایستاده» — why a server is offline, in plain words (§42.2 `server.state.reason`). */
fun reasonFa(reason: String?): String = when (reason) {
    "runner_stopped" -> "runner روی سرور ایستاده؛ خود سرور روشن است"
    "server_unreachable" -> "هیچ سروری به آن نمیرسد؛ خاموش است یا شبکه ندارد"
    "revoked" -> "runner این سرور باطل شده"
    "fallback_public" -> "از راه عمومی وصل است؛ راه خصوصی جواب نداد"
    "slow" -> "کند به هاب میرسد"
    else -> "runner تماس نمیگیرد"
}

/** What fixes it (HM-3's sheet). */
fun fixFa(reason: String?): String = when (reason) {
    "runner_stopped" -> "Claude همان سرور سرویس hq-runner را دوباره راه بیندازد و با hq-runner status ببیند که کار میگیرد."
    "server_unreachable" -> "از کنسول هتزنر ببین سرور روشن است و به شبکه‌ی هلدینگ وصل است؛ بعد runner خودش تماس میگیرد."
    "revoked" -> "برای کار دوباره، runner را روی سرور از نو جفت کن («وصل کردن سرور»)."
    "fallback_public" -> "از کنسول هتزنر، Networks، سرور را به شبکه‌ی هلدینگ برگردان؛ تا آن موقع از راه عمومی با TLS کار میکند."
    "slow" -> "کار میکند ولی هر فرمان دیرتر جواب میدهد؛ اگر ماند، بار سرور را ببین."
    else -> "Claude همان سرور با hq-runner status علتش را ببیند؛ وقتی runner دوباره تماس گرفت، خط بسته میشود."
}

/** A server by its company's name (owner rule), «· its name» when the company has several; a server of a company the app does not know
 *  yet (a server paired before its company was founded in the hub) goes by its own name. Never a hostname. */
internal fun serverLabel(s: MapServer, many: Boolean, names: (String) -> String): String {
    val co = names(s.company)
    return when {
        co == s.company && s.name.isNotBlank() -> s.name
        many -> "$co · ${s.name}"
        else -> co
    }
}

/** A server on the map: the network's node with the hub's live word over it (a state, why and since when). */
data class MapServer(val id: String, val company: String, val name: String, val state: String, val via: String?, val rttMs: Double?, val live: ServerLive?) {
    val offline: Boolean get() = state == "offline"
}

/** The map's servers: `GET /infra/network`'s nodes, each with what the stream said of it since (the hub's word only; never silence). */
fun mapServers(net: NetworkMap?, live: LiveState): List<MapServer> {
    val nodes = net?.servers.orEmpty()
    val out = nodes.map { n ->
        val l = live.serverStates[n.id]
        MapServer(n.id, n.company, n.name, l?.state?.ifBlank { null } ?: n.state, l?.via ?: n.via, l?.hubRttMs ?: n.hubRttMs, l)
    }.toMutableList()
    // A server the stream told of that the map has not read yet joins it (it is the hub's word).
    for (l in live.serverStates.values) if (out.none { it.id == l.id } && l.state.isNotBlank() && l.company != null) {
        out += MapServer(l.id, l.company, l.id, l.state, l.via, l.hubRttMs, l)
    }
    return out.filter { it.state != "revoked" }
}

// ------------------------------------------------------------------ the card --
/**
 * The live map's card: «نقشه | جدول» (the table is every company and server, any number), the heartbeat in its corner, «قدیمی» when the
 * stream is frozen, the last event in words (announced). [onRoads] opens a server's roads port by port (the network page's detail).
 */
@Composable
fun HoldingMapCard(modifier: Modifier = Modifier, net: NetworkMap?, onRoads: ((String) -> Unit)? = null, view0: String = "map") {
    val c = Divan.colors
    val live = rememberLive()
    val beat = rememberBeat()
    var view by rememberSaveable { mutableStateOf(view0) }
    com.coinepro.hq.designsystem.HqCard(modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Column(Modifier.weight(1f)) {
                Text("نقشه‌ی زنده‌ی هلدینگ", style = Divan.type.h3)
                Text("هاب در مرکز؛ شرکت‌ها و سرورها از داده. هر ذره یک رویداد است.", style = Divan.type.micro, color = c.textMuted)
            }
            LiveBeat(compact = true)
        }
        Row(Modifier.padding(top = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Segmented(listOf(SegOption("map", "نقشه"), SegOption("table", "جدول")), view, { view = it }, Modifier.weight(1f))
            MissedChip()
        }
        if (view == "map") {
            Box(Modifier.fillMaxWidth().padding(top = 8.dp)) {
                // A frozen map must never look like a calm holding: it fades back and says «قدیمی»; nothing on it flies.
                HoldingMap(net, live, beat.beat.frozen, onRoads, Modifier.graphicsLayer { alpha = if (beat.beat.frozen) 0.55f else 1f })
                if (beat.beat.frozen) Row(
                    Modifier.align(Alignment.TopEnd).clip(CircleShape).background(c.softWarning).border(1.dp, c.warning, CircleShape).padding(horizontal = 10.dp, vertical = 2.dp)
                        .semantics(mergeDescendants = true) { liveRegion = LiveRegionMode.Polite; contentDescription = "نقشه قدیمی است" },
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    DIcon(DivanIcon.TIME, size = 12.dp, tint = c.warning)
                    Text("قدیمی؛ چیزی حرکت نمیکند", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.warning)
                }
            }
            MapLegend(Modifier.padding(top = 10.dp))
        } else HoldingTable(net, live, Modifier.padding(top = 10.dp))
        LastEventLine(live, Modifier.padding(top = 8.dp))
    }
}

/** The newest event in words, a polite live region (P0 events are announced: rule 9). */
@Composable
private fun LastEventLine(live: LiveState, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val names = rememberNames()
    val f = live.flows.lastOrNull() ?: return
    Row(modifier.semantics(mergeDescendants = true) { liveRegion = LiveRegionMode.Polite }, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Box(Modifier.size(6.dp).clip(CircleShape).background(inkOf(flowInk(f.kind))))
        Text(timesFig(flowFa(f, names)), style = Divan.type.caption, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
        Fig(jTime(java.time.Instant.ofEpochMilli(f.at).toString()), style = Divan.type.figureSmall, color = c.textMuted)
    }
}

/** A company or a server by its company's name (owner rule: never a hostname). */
@Composable
internal fun rememberNames(): (String) -> String {
    val list = rememberCompanies()
    return remember(list) { { code -> list.firstOrNull { it.code == code }?.nameFa ?: code } }
}

@Composable
internal fun inkOf(k: FlowInk): Color = when (k) {
    FlowInk.GOLD -> Divan.colors.goldInk
    FlowInk.SILVER -> Divan.colors.silverInk
    FlowInk.LAPIS -> Divan.colors.lapis
}

@Composable
private fun MapLegend(modifier: Modifier = Modifier) {
    val c = Divan.colors
    FlowRow(modifier, horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
        for ((ink, t) in listOf(c.goldInk to "فرمان تو", c.silverInk to "کار ایجنت‌ها", c.lapis to "داده · کار روی سرور")) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            Box(Modifier.size(7.dp).clip(CircleShape).background(ink))
            Text(t, style = Divan.type.micro, color = c.textSecondary)
        }
        LegendLine(c.lapis.copy(alpha = 0.6f), null, "runner · شبکه‌ی خصوصی")
        LegendLine(c.warning, floatArrayOf(5f, 4f), "راه عمومی")
        LegendLine(c.negative, null, "قطع")
        LegendLine(c.goldInk.copy(alpha = 0.6f), null, "پیوند دو شرکت")
    }
}

@Composable
private fun LegendLine(ink: Color, dash: FloatArray?, text: String) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        Canvas(Modifier.size(width = 18.dp, height = 4.dp)) {
            drawLine(ink, Offset(0f, size.height / 2), Offset(size.width, size.height / 2), 1.5.dp.toPx(), pathEffect = dash?.let { d -> PathEffect.dashPathEffect(d.map { it * density }.toFloatArray()) })
        }
        Text(text, style = Divan.type.micro, color = Divan.colors.textSecondary)
    }
}

// ------------------------------------------------------------------ the map --
/** What a tap on the map opened. */
private sealed interface MapSheet {
    data object Hub : MapSheet
    data class Company(val code: String) : MapSheet
    data class Server(val id: String) : MapSheet
    data class Chord(val link: CompanyLink) : MapSheet
    data class Fold(val codes: List<String>) : MapSheet
}

/** The map's geometry, in dp: the centre, the company ring(s) and the servers' ring. */
private data class Geo(val cx: Dp, val cy: Dp, val r1: Dp, val r2: Dp, val rs: Dp, val plan: RingPlan)

private fun polar(cx: Dp, cy: Dp, r: Dp, deg: Double): Pair<Dp, Dp> {
    val a = Math.toRadians(deg)
    return Pair(cx + r * cos(a).toFloat(), cy + r * sin(a).toFloat())
}

private val HUB = 60.dp
private val SERVER = 16.dp
/** A company node at full size on a phone. */
private val NODE = 48.dp

/**
 * HM-1, HM-2, HM-3: the map itself. [net] the servers (`GET /infra/network`), [live] the store, [frozen] the stream not live (no particle
 * flies, the state is applied at once).
 */
@Composable
fun HoldingMap(net: NetworkMap?, live: LiveState, frozen: Boolean, onRoads: ((String) -> Unit)? = null, modifier: Modifier = Modifier, codes0: List<String>? = null) {
    val c = Divan.colors
    val nav = LocalNav.current
    val reduced = LocalReducedMotion.current
    val visible = rememberAppVisible()
    val links = rememberHoldingLinks().data
    val companies = rememberCompanies()
    val names = rememberNames()
    // Companies are data: the canvas's companies, else the list's; the busiest on top, never alphabetical.
    val codes = (codes0 ?: links?.nodes?.filter { it.kind == "company" }?.map { it.code }
        ?: companies.filter { it.kind != "holding" && it.status != "archived" }.map { it.code }).distinct()
    val order = activityOrder(codes, live.companies)
    val servers = mapServers(net, live)
    val chords = links?.links.orEmpty().filter { it.from in codes && it.to in codes && it.from != it.to }
    val field = remember { ParticleField() }
    var sheet by remember { mutableStateOf<MapSheet?>(null) }
    var ceremony by remember { mutableLongStateOf(0L) }
    // Time-bound states (a link positive for 2 s after it came back, a red tick for 4 s after a failed job) end by a recomposition.
    var tick by remember { mutableIntStateOf(0) }
    val nowMs = remember(tick, live.applied) { com.coinepro.hq.core.format.HqClock.millis() }
    LaunchedEffect(live.serverStates) {
        val soon = live.serverStates.values.flatMap { listOfNotNull(it.backAt?.plus(LiveRules.RECONNECTED_MS), it.failedAt?.plus(LiveRules.FAILED_TICK_MS)) }
            .filter { it > nowMs }.minOrNull() ?: return@LaunchedEffect
        delay(soon - nowMs + 50)
        tick++
    }

    BoxWithConstraints(modifier.fillMaxWidth(), contentAlignment = AbsoluteAlignment.TopLeft) {
        val w = maxWidth
        // The servers' ring near the edge; one company ring inside it with room for each company's name between the two; if they do not
        // all fit, two company rings (smaller nodes) and «بقیه · n».
        val rs = (w / 2 - 12.dp).coerceIn(120.dp, 230.dp)
        val r1one = (rs - 62.dp).coerceAtLeast(64.dp)
        val one = ringPlan(order, r1one.value, r1one.value + 46f, node = NODE.value)
        val geo = if (one.rings <= 1) Geo(w / 2, rs + 28.dp, r1one, r1one, rs, one)
        else {
            val r2 = rs - 46.dp
            val r1 = (r2 - 46.dp).coerceAtLeast(56.dp)
            Geo(w / 2, rs + 28.dp, r1, r2, rs, ringPlan(order, r1.value, r2.value, node = NODE.value))
        }
        val h = geo.cy * 2
        val density = LocalDensity.current
        fun px(d: Dp) = with(density) { d.toPx() }

        // Where everything sits.
        val slotOf = geo.plan.slots.filter { it.code != null }.associateBy { it.code!! }
        val compPos: Map<String, Pair<Dp, Dp>> = slotOf.mapValues { (_, s) -> polar(geo.cx, geo.cy, if (s.ring == 0) geo.r1 else geo.r2, s.angle) }
        val serversBy = servers.groupBy { it.company }
        val srvPos = HashMap<String, Pair<Dp, Dp>>()
        val srvMore = HashMap<String, Int>()
        for ((code, list) in serversBy) {
            val s = slotOf[code] ?: continue
            val step = 360.0 / max(1, geo.plan.slots.count { it.ring == s.ring })
            val spread = min(14.0, max(8.0, step * 0.5 / max(1, list.size)))
            // A lone server sits a little beside its company's angle, so its runner link is not read as the company's own spoke; turned
            // away from the vertical, so the link passes beside the company's name (above the node in the upper half, below it in the lower).
            val rad = Math.toRadians(s.angle)
            val away = if (cos(rad) >= -1e-9) (if (sin(rad) > 1e-9) -1.0 else 1.0) else (if (sin(rad) > 1e-9) 1.0 else -1.0)
            val angles = serverAngles(s.angle + if (list.size == 1) away * min(24.0, step * 0.25) else 0.0, list.size, spread)
            list.take(angles.size).forEachIndexed { i, sv -> srvPos[sv.id] = polar(geo.cx, geo.cy, geo.rs, angles[i]) }
            if (list.size > angles.size) srvMore[code] = list.size - angles.size
        }
        fun pos(end: String): Offset? = when {
            end == "hub" -> Offset(px(geo.cx), px(geo.cy))
            end.startsWith("srv:") -> (srvPos[end.removePrefix("srv:")] ?: servers.firstOrNull { it.id == end.removePrefix("srv:") }?.company?.let { compPos[it] })?.let { Offset(px(it.first), px(it.second)) }
            end == "outside" -> Offset(px(geo.cx), 0f)
            else -> compPos[end]?.let { Offset(px(it.first), px(it.second)) }
        }

        // HM-2: each new flow flies once (the hub's ceremony first when the owner acted); replays and a frozen map only tint nothing.
        var seen by remember { mutableLongStateOf(live.flowN) }
        val goldInk = c.goldInk
        val silver = c.silverInk
        val lapis = c.lapis
        LaunchedEffect(live.flowN) {
            val fresh = live.flows.filter { it.n > seen }
            seen = live.flowN
            if (frozen || !visible) return@LaunchedEffect
            for (f in fresh) {
                if (f.quiet) continue
                val ink = when (flowInk(f.kind)) { FlowInk.GOLD -> goldInk; FlowInk.SILVER -> silver; FlowInk.LAPIS -> lapis }
                // An end the map does not draw (a company folded into «بقیه», a server past four) flies nothing: the table has it.
                val ends = flowLegs(f).map { pos(it) }
                if (ends.any { it == null }) continue
                val path = ends.filterNotNull()
                if (f.owner) ceremony = f.n
                // A request between two companies with a link that is on: the chord glows while it travels through the hub.
                if (f.from != "hub" && f.to != "hub") chords.firstOrNull { it.state == "on" && setOf(it.from, it.to) == setOf(f.from, f.to) }?.let { field.tint(chordKey(it), silver) }
                if (reduced) for (leg in flowLegs(f).zipWithNext()) field.tint(edgeKey(leg.first, leg.second), ink)
                field.fly(flowEdge(f), path, ink, reduced, delayMs = if (f.owner && !reduced) Grammar.CEREMONY else 0)
            }
        }

        // M9 per runner link: the gap opens when it drops and closes when it is back.
        val gaps = HashMap<String, State<Float>>()
        for (s in servers) key(s.id) { gaps[s.id] = animateBreak(s.offline) }

        // The edges.
        val spokeInk = c.goldInk.copy(alpha = if (Divan.night) 0.30f else 0.36f)
        val runnerInk = c.lapis.copy(alpha = 0.45f)
        val chordInk = c.goldInk.copy(alpha = if (Divan.night) 0.42f else 0.5f)
        val holdingLocked = live.control.holding
        Canvas(
            Modifier.fillMaxWidth().height(h).pointerInput(chords, geo) {
                detectTapGestures { p ->
                    val hit = chords.firstOrNull { l ->
                        val a = compPos[l.from] ?: return@firstOrNull false
                        val b = compPos[l.to] ?: return@firstOrNull false
                        chordNear(Offset(px(a.first), px(a.second)), Offset(px(b.first), px(b.second)), Offset(px(geo.cx), px(geo.cy)), p, px(14.dp))
                    }
                    if (hit != null) sheet = MapSheet.Chord(hit)
                }
            },
        ) {
            val hub = Offset(px(geo.cx), px(geo.cy))
            // Chords: the owner's links between companies, curving through the inner ring.
            for (l in chords) {
                val a = compPos[l.from] ?: continue
                val b = compPos[l.to] ?: continue
                val pa = Offset(px(a.first), px(a.second))
                val pb = Offset(px(b.first), px(b.second))
                val glow = field.tints[chordKey(l)]
                val on = l.state == "on"
                drawPath(
                    chordPath(pa, pb, hub), glow?.color ?: if (on) chordInk else c.textMuted.copy(alpha = 0.7f),
                    style = Stroke(
                        (if (glow != null) 2.4.dp else 1.2.dp).toPx(),
                        pathEffect = if (on || glow != null) null else PathEffect.dashPathEffect(floatArrayOf(1.dp.toPx(), 5.dp.toPx())), cap = StrokeCap.Round,
                    ),
                )
            }
            // Work spokes hub ↔ company.
            for ((code, p) in compPos) {
                val node = slotOf[code]?.size?.dp ?: 52.dp
                val (from, to) = trim(hub, Offset(px(p.first), px(p.second)), px(HUB / 2), px(node / 2 + 7.dp))
                val locked = holdingLocked || code in live.control.locked
                val tint = field.tints[edgeKey("hub", code)] ?: field.tints[edgeKey(code, "hub")]
                drawLine(
                    when { locked -> c.negative.copy(alpha = 0.6f); tint != null -> tint.color; else -> spokeInk }, from, to,
                    strokeWidth = (if (tint != null) 2.2.dp else 1.3.dp).toPx(), cap = StrokeCap.Round,
                    pathEffect = if (locked) PathEffect.dashPathEffect(floatArrayOf(2.dp.toPx(), 4.dp.toPx())) else null,
                )
            }
            // Runner links hub ↔ server: solid private, dashed public, red and broken when offline, positive 2 s once back.
            for (s in servers) {
                val p = srvPos[s.id] ?: continue
                val (from, to) = trim(hub, Offset(px(p.first), px(p.second)), px(HUB / 2 - 2.dp), px(SERVER / 2 + 3.dp))
                val back = s.live?.backAt?.let { nowMs - it < LiveRules.RECONNECTED_MS } == true
                val tint = field.tints[edgeKey("hub", "srv:${s.id}")] ?: field.tints[edgeKey("srv:${s.id}", "hub")]
                val ink = when { s.offline -> c.negative; back -> c.positive; tint != null -> tint.color; else -> runnerInk }
                val width = (if (s.offline || back || tint != null) 1.7.dp else 1.1.dp).toPx()
                val dash = if (s.via == "public" && !s.offline) PathEffect.dashPathEffect(floatArrayOf(5.dp.toPx(), 4.dp.toPx())) else null
                broken(from, to, (gaps[s.id]?.value ?: 0f) * 7.dp.toPx(), ink, width, dash)
            }
            // A measured road between two servers appears only while it fails (§5): a thin red dashed line.
            for (l in live.links.values) {
                if (l.to == "hub") continue
                val a = srvPos[l.from] ?: continue
                val b = srvPos[l.to] ?: continue
                drawLine(c.negative.copy(alpha = 0.75f), Offset(px(a.first), px(a.second)), Offset(px(b.first), px(b.second)), 1.4.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(4.dp.toPx(), 4.dp.toPx())))
            }
        }
        // The one particle layer of this screen.
        Box(Modifier.fillMaxWidth().height(h), contentAlignment = AbsoluteAlignment.TopLeft) { ParticleLayer(field, frozen) }

        // The hub: the holding seal.
        Box(Modifier.absoluteOffset(x = geo.cx - HUB / 2, y = geo.cy - HUB / 2).size(HUB).clickable(role = Role.Button, onClickLabel = "هاب") { sheet = MapSheet.Hub }, contentAlignment = Alignment.Center) {
            HubSeal(HUB, ceremony) { field.hubPassing }
        }
        Box(Modifier.absoluteOffset(x = geo.cx - 40.dp, y = geo.cy + HUB / 2 + 2.dp).width(80.dp), contentAlignment = Alignment.Center) {
            Halo("ستاد · هاب", Divan.type.micro, c.textMuted)
        }

        // The companies.
        val narrow = geo.plan.slots.size > 8
        for (slot in geo.plan.slots) {
            val (x, y) = polar(geo.cx, geo.cy, if (slot.ring == 0) geo.r1 else geo.r2, slot.angle)
            val size = slot.size.dp
            if (slot.fold) {
                key("fold") {
                    Box(
                        Modifier.absoluteOffset(x = x - size / 2 - 8.dp, y = y - size / 2).size(width = size + 16.dp, height = size).clip(CircleShape).background(c.tile)
                            .border(1.dp, c.lineStrong, CircleShape).clickable(role = Role.Button, onClickLabel = "بقیه‌ی شرکت‌ها") { sheet = MapSheet.Fold(slot.folded) },
                        contentAlignment = Alignment.Center,
                    ) { Text("بقیه · ${faNum(slot.folded.size)}", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary, maxLines = 1) }
                }
                continue
            }
            val code = slot.code!!
            val co = live.companies[code] ?: CompanyLive(code)
            val named = co.copy(nameFa = co.nameFa.ifBlank { names(code) })
            val state = companyStateOf(co, live.control)
            key(code) {
                CompanyDisc(named, state, size, Modifier.absoluteOffset(x = x - (size + 12.dp) / 2, y = y - (size + 12.dp) / 2)) { sheet = MapSheet.Company(code) }
                // The name on the outward side (above a node in the upper half), so it never sits on the spokes.
                if (!narrow || slot.ring == 0 && size >= 40.dp) {
                    val above = y < geo.cy - 4.dp
                    val labelH = if (!narrow) 38.dp else 20.dp
                    CompanyLabel(
                        named, state == "locked", showSub = !narrow,
                        Modifier.absoluteOffset(x = x - 50.dp, y = if (above) y - size / 2 - 6.dp - labelH else y + size / 2 + 6.dp).width(100.dp),
                    )
                }
            }
        }

        // The servers, and a dropped one's chip «قطع · 14:02».
        for (s in servers) {
            val (x, y) = srvPos[s.id] ?: continue
            key(s.id) {
                val failed = s.live?.failedAt?.let { nowMs - it < LiveRules.FAILED_TICK_MS } == true
                ServerNode(
                    s, showName = !narrow && (serversBy[s.company]?.size ?: 1) > 1, failed = failed,
                    modifier = Modifier.absoluteOffset(x = x - 30.dp, y = y - SERVER / 2 - 7.dp).width(60.dp),
                ) { sheet = MapSheet.Server(s.id) }
                if (s.offline) {
                    // On the side of the server away from its company's name (below it when the name is above the node, else above),
                    // and leaning outward, so neither the node, its name nor a spoke runs under the chip.
                    val nameAbove = (compPos[s.company]?.second ?: geo.cy) < geo.cy - 4.dp
                    val oy = if (nameAbove) y + SERVER / 2 + 6.dp else y - SERVER / 2 - 26.dp
                    val ox = if (x >= geo.cx) x - 20.dp else x - 60.dp
                    BreakChip(s, Modifier.absoluteOffset(x = ox.coerceIn(0.dp, w - 80.dp), y = oy.coerceIn(0.dp, h - 20.dp)).width(80.dp)) { sheet = MapSheet.Server(s.id) }
                }
            }
        }
        for ((code, more) in srvMore) {
            val s = slotOf[code] ?: continue
            val (x, y) = polar(geo.cx, geo.cy, geo.rs + 18.dp, s.angle)
            Text("+" + faNum(more), Modifier.absoluteOffset(x = x - 12.dp, y = y - 8.dp).width(24.dp), style = Divan.type.micro, color = c.textMuted, textAlign = TextAlign.Center)
        }
        // The «×n» chips over everything (rule 4).
        Box(Modifier.fillMaxWidth().height(h), contentAlignment = AbsoluteAlignment.TopLeft) { ParticleChips(field) }
    }

    when (val s = sheet) {
        null -> Unit
        MapSheet.Hub -> HubSheet(live) { sheet = null }
        is MapSheet.Company -> CompanySheet(s.code, live, servers.filter { it.company == s.code }, names, { sheet = null }) { nav.go("companies/${s.code}") }
        is MapSheet.Server -> servers.firstOrNull { it.id == s.id }?.let { sv -> ServerSheet(sv, live, names, { sheet = null }, onRoads?.let { r -> { sheet = null; r(sv.id) } }) { sheet = null; nav.go("servers/${sv.id}") } }
        is MapSheet.Chord -> ChordSheet(s.link, live, names) { sheet = null }
        is MapSheet.Fold -> FoldSheet(s.codes, live, names, { sheet = null }) { code -> sheet = null; nav.go("companies/$code") }
    }
}

private fun edgeKey(a: String, b: String): String = "$a>$b"
private fun chordKey(l: CompanyLink): String = "chord:" + listOf(l.from, l.to).sorted().joinToString("~")

/** A segment between [a] and [b] cut back by the two circles it joins. */
private fun trim(a: Offset, b: Offset, ra: Float, rb: Float): Pair<Offset, Offset> {
    val d = b - a
    val len = hypot(d.x, d.y)
    if (len <= ra + rb) return a to a
    val u = Offset(d.x / len, d.y / len)
    return (a + u * ra) to (b - u * rb)
}

/** A line with a gap of [gap] px open in its middle (M9). */
private fun DrawScope.broken(a: Offset, b: Offset, gap: Float, ink: Color, width: Float, dash: PathEffect?) {
    if (gap <= 0.5f) { drawLine(ink, a, b, width, StrokeCap.Round, pathEffect = dash); return }
    val d = b - a
    val len = hypot(d.x, d.y).takeIf { it > 0f } ?: return
    val u = Offset(d.x / len, d.y / len)
    val m = a + d * 0.5f
    drawLine(ink, a, m - u * gap, width, StrokeCap.Round, pathEffect = dash)
    drawLine(ink, m + u * gap, b, width, StrokeCap.Round, pathEffect = dash)
}

/** A chord from [a] to [b] curving toward the hub [h] (a quadratic through 55 % of the way to the centre). */
private fun chordPath(a: Offset, b: Offset, h: Offset): Path {
    val m = (a + b) * 0.5f
    val ctl = m + (h - m) * 0.55f
    return Path().apply { moveTo(a.x, a.y); quadraticTo(ctl.x, ctl.y, b.x, b.y) }
}

private fun chordNear(a: Offset, b: Offset, h: Offset, p: Offset, tol: Float): Boolean {
    val m = (a + b) * 0.5f
    val ctl = m + (h - m) * 0.55f
    for (i in 2..18) {
        val t = i / 20f
        val q = a * ((1 - t) * (1 - t)) + ctl * (2 * (1 - t) * t) + b * (t * t)
        if (hypot(q.x - p.x, q.y - p.y) <= tol) return true
    }
    return false
}

// ------------------------------------------------------------------ the nodes --
/**
 * The holding seal (§5): the shamseh rim of 24 rays, the lapis gem, the two-metal monogram. It never moves; its gem brightens and one gold
 * ring expands only when the owner acts (M10, [ceremony]); the rim flickers once as a request crosses it ([passing]).
 */
@Composable
fun HubSeal(size: Dp, ceremony: Any?, passing: () -> Boolean = { false }) {
    val c = Divan.colors
    val p by rememberCeremony(ceremony)
    val gemHi = if (Divan.night) Color(0xFF2C4290) else Color(0xFF3552A8)
    Box(Modifier.size(size).semantics { contentDescription = "هاب · ستاد" }, contentAlignment = Alignment.Center) {
        Canvas(Modifier.requiredSize(size * 2f)) {
            val s = size.toPx()
            val cx = center.x
            val cy = center.y
            // The ceremony's ring, growing out of the seal and fading.
            if (p < 1f) drawCircle(c.goldInk.copy(alpha = 0.75f * (1f - p)), s / 2 * (0.82f + 0.7f * p), Offset(cx, cy), style = Stroke(2.dp.toPx()))
            val rim = Path().apply {
                for (k in 0 until 48) {
                    val r = if (k % 2 == 0) s / 2 else s / 2 * 0.84f
                    val a = (-PI / 2 + k * PI / 24).toFloat()
                    val x = cx + r * cos(a)
                    val y = cy + r * sin(a)
                    if (k == 0) moveTo(x, y) else lineTo(x, y)
                }
                close()
            }
            drawPath(rim, c.goldFill.copy(alpha = if (passing()) 1f else 0.85f))
            val lit = sin(PI * p).toFloat().coerceIn(0f, 1f)
            drawCircle(lerp(DivanFixed.lapisDisc, gemHi, lit), s / 2 * 0.75f, Offset(cx, cy))
            drawCircle(c.goldFill.copy(alpha = 0.55f), s / 2 * 0.66f, Offset(cx, cy), style = Stroke(1.dp.toPx()))
        }
        Monogram(size * 0.38f, metals = Color(0xFFDBDBDB) to Color(0xFFD8A848))
    }
}

/** A company on the ring: its mark in an octagon and its activity arc in its chart colour (M12); hatched when locked; one ripple when
 *  its state changes (M3). Its name is [CompanyLabel], on the outward side. */
@Composable
private fun CompanyDisc(co: CompanyLive, state: String, size: Dp, modifier: Modifier, onClick: () -> Unit) {
    val c = Divan.colors
    val ink = companyColor(co.code)
    val share = if ((co.total ?: 0) > 0) ((co.working ?: 0).toFloat() / co.total!!).coerceIn(0f, 1f) else 0f
    val f by com.coinepro.hq.designsystem.animateFill(share)
    val locked = state == "locked"
    Box(
        modifier.size(size + 12.dp).rippleOnce(state, ink).clip(CircleShape).clickable(role = Role.Button, onClickLabel = co.nameFa, onClick = onClick)
            .semantics(mergeDescendants = true) {
                contentDescription = co.nameFa + "، " + (co.working?.let { "${faNum(it)} در کار" } ?: "") + if (locked) "، قفل" else ""
            },
        contentAlignment = Alignment.Center,
    ) {
        Canvas(Modifier.size(size + 12.dp)) {
            val st = 3.dp.toPx()
            val r = this.size.minDimension / 2 - st / 2
            drawCircle(c.lineDivider, r, style = Stroke(st))
            if (f > 0f) drawArc(ink, -90f, 360f * f, false, topLeft = Offset(center.x - r, center.y - r), size = androidx.compose.ui.geometry.Size(2 * r, 2 * r), style = Stroke(st, cap = StrokeCap.Round))
            val oct = octagon(center, size.toPx() / 2)
            drawPath(oct, c.tile)
            if (locked) clipPath(oct) { hatch(c.softNegative) }
            drawPath(oct, if (locked) c.negative else c.lineStrong, style = Stroke(1.dp.toPx()))
        }
        CompanyMark(co.code, height = size * 0.48f, ink = c.textPrimary)
    }
}

/** A company's name and «۳ در کار از ۷» (or «قفل»), each on a halo of the card so no line runs through it. */
@Composable
private fun CompanyLabel(co: CompanyLive, locked: Boolean, showSub: Boolean, modifier: Modifier) {
    val c = Divan.colors
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(0.dp)) {
        Halo(co.nameFa, Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), c.textPrimary)
        if (showSub) Halo(
            if (locked) "قفل" else co.working?.let { w -> "${faNum(w)} در کار" + (co.total?.let { " از ${faNum(it)}" } ?: "") } ?: "—",
            Divan.type.micro, if (locked) c.negative else c.textSecondary,
        )
    }
}

/** A label on the map on a halo of the card's colour (the prototype's paint-order stroke). */
@Composable
private fun Halo(text: String, style: androidx.compose.ui.text.TextStyle, color: Color) {
    Text(
        text, Modifier.clip(RoundedCornerShape(5.dp)).background(Divan.colors.card.copy(alpha = 0.88f)).padding(horizontal = 4.dp),
        style = style, color = color, maxLines = 1, overflow = TextOverflow.Ellipsis, textAlign = TextAlign.Center,
    )
}

private fun octagon(center: Offset, r: Float): Path = Path().apply {
    for (k in 0 until 8) {
        val a = (PI / 8 + k * PI / 4).toFloat()
        val x = center.x + r * cos(a)
        val y = center.y + r * sin(a)
        if (k == 0) moveTo(x, y) else lineTo(x, y)
    }
    close()
}

/** A server on the outer ring: its state by shape (online, offline with ×, pending dashed, revoked muted), M7 while a job runs on it, a
 *  small globe when it came over the public road, a red tick for 4 s after a job failed, one ripple when its state changes. */
@Composable
private fun ServerNode(s: MapServer, showName: Boolean, failed: Boolean, modifier: Modifier, onClick: () -> Unit) {
    val c = Divan.colors
    val busy = (s.live?.busy ?: 0) > 0
    Column(modifier.clickable(role = Role.Button, onClickLabel = "سرور") { onClick() }, horizontalAlignment = Alignment.CenterHorizontally) {
        Box(Modifier.size(SERVER + 14.dp), contentAlignment = Alignment.Center) {
            Box(Modifier.size(SERVER).rippleOnce(s.state, if (s.offline) c.negative else c.positive), contentAlignment = Alignment.Center) {
                ServerGlyph(s.state, size = SERVER)
            }
            if (busy) Box(Modifier.size(SERVER + 12.dp), contentAlignment = Alignment.Center) { com.coinepro.hq.designsystem.Arc(true, c.lapis, size = SERVER + 12.dp, word = null) }
            if (s.via == "public" && !s.offline) Box(Modifier.align(Alignment.TopStart)) { DIcon(DivanIcon.GLOBE, size = 10.dp, tint = c.warning) }
            if (failed) Box(Modifier.align(Alignment.BottomStart)) { com.coinepro.hq.designsystem.DrawnMark(false, c.negative, size = 9.dp) }
        }
        if (showName) Text(s.name, style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

/** «قطع · 14:02» beside a dropped server; a tap opens why and what fixes it. */
@Composable
private fun BreakChip(s: MapServer, modifier: Modifier, onClick: () -> Unit) {
    val c = Divan.colors
    val since = s.live?.since
    Box(modifier, contentAlignment = Alignment.Center) {
        Row(
            Modifier.clip(CircleShape).background(c.softNegative).border(1.dp, c.negative, CircleShape).clickable(role = Role.Button, onClickLabel = "چرا قطع شد", onClick = onClick)
                .padding(horizontal = 7.dp, vertical = 1.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(buildAnnotatedString { append("قطع"); if (since != null) { append(" · "); fig(jTime(since)) } }, style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.negative, maxLines = 1)
        }
    }
}

// ------------------------------------------------------------------ the sheets --
@Composable
private fun SheetRow(label: String, value: androidx.compose.ui.text.AnnotatedString) {
    val c = Divan.colors
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.Top) {
        Text(label, style = Divan.type.caption, color = c.textMuted, modifier = Modifier.width(92.dp))
        Text(value, style = Divan.type.small, color = c.textPrimary, modifier = Modifier.weight(1f))
    }
}

private fun plainA(s: String) = timesFig(s)

/** The hub: today's orders, flows in the last hour, servers online, the stream's state. */
@Composable
private fun HubSheet(live: LiveState, onDismiss: () -> Unit) {
    val beat = rememberBeat()
    val now = com.coinepro.hq.core.format.HqClock.millis()
    val today = java.time.LocalDate.ofInstant(java.time.Instant.ofEpochMilli(now), java.time.ZoneOffset.UTC)
    val orders = live.flows.count { it.kind == "order" && java.time.LocalDate.ofInstant(java.time.Instant.ofEpochMilli(it.at), java.time.ZoneOffset.UTC) == today }
    val hour = live.flows.count { now - it.at < 3_600_000L }
    com.coinepro.hq.ui.v14.HqSheet(onDismiss, "ستاد · هاب", sub = "هر کار میان شرکت‌ها از هاب میگذرد؛ سرورها با هم مستقیم حرف نمیزنند.") {
        SheetRow("فرمان‌های امروز", plainA(faNum(orders)))
        SheetRow("جریان در ساعت", plainA(faNum(hour)))
        SheetRow("سرورهای وصل", plainA(live.servers.online?.let { o -> "${faNum(o)} از ${live.servers.total?.let(::faNum) ?: "—"}" } ?: "—"))
        SheetRow("پخش زنده", plainA(beat.fa))
    }
}

/** HM-4 (lite): a company's people at work, its sessions, its servers and their round trips, its last flows. */
@Composable
private fun CompanySheet(code: String, live: LiveState, servers: List<MapServer>, names: (String) -> String, onDismiss: () -> Unit, onOpen: () -> Unit) {
    val c = Divan.colors
    val co = live.companies[code] ?: CompanyLive(code)
    val flows = live.flows.filter { it.from == code || it.to == code }.takeLast(10).asReversed()
    com.coinepro.hq.ui.v14.HqSheet(onDismiss, names(code), sub = if (companyStateOf(co, live.control) == "locked") "قفل است؛ کاری اجرا نمیشود." else null) {
        SheetRow("در کار", plainA(co.working?.let { w -> "${faNum(w)} نفر" + (co.total?.let { " از ${faNum(it)}" } ?: "") } ?: "—"))
        SheetRow("جلسه‌ی باز", plainA(co.sessionsOpen?.let(::faNum) ?: "—"))
        SheetRow("خرج امروز", buildAnnotatedString { fig(co.spendTodayUsd?.let(::usdCents) ?: "—"); co.budgetUsd?.let { append(" از "); fig(usdCents(it)) } })
        if (servers.isNotEmpty()) {
            Text("سرورها", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.silverInk)
            for (s in servers) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                ServerGlyph(s.state, size = 11.dp)
                Text(if (servers.size > 1) "${names(code)} · ${s.name}" else names(code), style = Divan.type.small, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(serverStateFa(s.state), style = Divan.type.caption, color = if (s.offline) c.negative else c.textSecondary)
                com.coinepro.hq.core.net.Network.ms(s.rttMs)?.takeIf { !s.offline }?.let { Fig(it, style = Divan.type.figureSmall, color = c.textMuted) }
            }
        }
        if (flows.isNotEmpty()) {
            Text("آخرین جریان‌ها", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.silverInk)
            for (f in flows) FlowRowLine(f, names)
        }
        HqButton("باز کردن شرکت", onOpen, Modifier.fillMaxWidth(), icon = DivanIcon.NEXT)
    }
}

@Composable
private fun FlowRowLine(f: FlowLive, names: (String) -> String) {
    val c = Divan.colors
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Box(Modifier.size(6.dp).clip(CircleShape).background(inkOf(flowInk(f.kind))))
        Text(timesFig(flowFa(f, names)), style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.weight(1f), maxLines = 2, overflow = TextOverflow.Ellipsis)
        Fig(jTime(java.time.Instant.ofEpochMilli(f.at).toString()), style = Divan.type.figureSmall, color = c.textMuted)
    }
}

/**
 * HM-3: a server — its state, since when (and for how long, live), the last good contact, why in plain words, what waits on it, and what
 * fixes it. Its hostname and address are only on its own page.
 */
@Composable
private fun ServerSheet(s: MapServer, live: LiveState, names: (String) -> String, onDismiss: () -> Unit, onRoads: (() -> Unit)?, onOpen: () -> Unit) {
    val c = Divan.colors
    val now = rememberTicker(15_000, on = s.offline)
    val l = s.live
    // The last good contact: the hub's own measure of the road, else when the runner last polled.
    val seen = com.coinepro.hq.ui.servers.rememberServers().data?.firstOrNull { it.id == s.id }?.lastSeenAt
    val lastOk = live.links.values.firstOrNull { it.from == s.id && it.to == "hub" }?.lastOkAt ?: seen
    val title = serverLabel(s, mapServersOf(live, s.company) > 1, names)
    com.coinepro.hq.ui.v14.HqSheet(onDismiss, title, sub = "سرور ${names(s.company)}") {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Pill(serverStateFa(s.state), if (s.offline) com.coinepro.hq.core.format.Tone.NEG else if (s.state == "online") com.coinepro.hq.core.format.Tone.POS else com.coinepro.hq.core.format.Tone.WARN, dot = true)
            if (s.via == "public") Pill("راه عمومی", com.coinepro.hq.core.format.Tone.WARN, icon = DivanIcon.GLOBE)
        }
        if (s.offline) {
            val since = l?.since
            SheetRow("از کی", buildAnnotatedString {
                if (since != null) { fig(jTime(since)); isoMs(since)?.let { append(" · " + ageFa(now - it)) } } else append("—")
            })
            SheetRow("آخرین تماس سالم", buildAnnotatedString { lastOk?.let { fig(jTime(it)); isoMs(it)?.let { t -> append(" · " + ageFa(now - t) + " پیش") } } ?: append("—") })
            SheetRow("چرا", plainA(l?.reasonFa?.ifBlank { null } ?: reasonFa(l?.reason)))
            SheetRow("منتظر این سرور", plainA(l?.openJobs?.let { if (it == 0) "کاری در صف نیست" else "${faNum(it)} کار در صف" } ?: "—"))
            SheetRow("راه حل", plainA(fixFa(l?.reason)))
        } else {
            SheetRow("راه به هاب", plainA(if (s.via == "public") "عمومی" else if (s.via == "private") "شبکه‌ی خصوصی" else "—"))
            SheetRow("رفت و برگشت", buildAnnotatedString { fig(com.coinepro.hq.core.net.Network.ms(s.rttMs) ?: "—") })
            if ((l?.busy ?: 0) > 0) SheetRow("الان", plainA("${faNum(l!!.busy)} کار روی این سرور در جریان است"))
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (onRoads != null) HqButton("راه‌ها پورت به پورت", onRoads, Modifier.weight(1f), variant = BtnVariant.SECONDARY, size = BtnSize.SM)
            HqButton("باز کردن سرور", onOpen, Modifier.weight(1f), size = BtnSize.SM, icon = DivanIcon.NEXT)
        }
    }
}

private fun mapServersOf(live: LiveState, company: String): Int = live.serverStates.values.count { it.company == company }

/** A company link: its kind, purpose, open works, on or off, and the flows that went between the two. */
@Composable
private fun ChordSheet(l: CompanyLink, live: LiveState, names: (String) -> String, onDismiss: () -> Unit) {
    val c = Divan.colors
    val flows = live.flows.filter { setOf(it.from, it.to) == setOf(l.from, l.to) }.takeLast(6).asReversed()
    com.coinepro.hq.ui.v14.HqSheet(onDismiss, "${names(l.from)} ← ${names(l.to)}", sub = l.purposeFa.ifBlank { null }) {
        SheetRow("نوع", plainA(linkKindFa(l.kind)))
        SheetRow("وضع", plainA(if (l.state == "on") "روشن" else "خاموش"))
        SheetRow("کار باز", plainA(faNum(l.openWorks)))
        Text("کار میان این دو همیشه از هاب میگذرد؛ پیوند خودش ذره‌ای نمیبرد و وقتی درخواستی میانشان در راه است روشن میشود.", style = Divan.type.micro, color = c.textMuted)
        for (f in flows) FlowRowLine(f, names)
    }
}

/** «بقیه · n»: the companies the ring had no room for, the busiest first (every one is in the table too). */
@Composable
private fun FoldSheet(codes: List<String>, live: LiveState, names: (String) -> String, onDismiss: () -> Unit, onOpen: (String) -> Unit) {
    val c = Divan.colors
    com.coinepro.hq.ui.v14.HqSheet(onDismiss, "بقیه‌ی شرکت‌ها", sub = "${faNum(codes.size)} شرکت که روی حلقه جا نشدند؛ همه در «جدول» هم هستند.") {
        for (code in codes) {
            val co = live.companies[code] ?: CompanyLive(code)
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).clickable(role = Role.Button) { onOpen(code) }.padding(vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                CompanyMark(code, height = 14.dp, mono = true, ink = c.textSecondary)
                Text(names(code), style = Divan.type.small, modifier = Modifier.weight(1f))
                Text(co.working?.let { "${faNum(it)} در کار" } ?: "—", style = Divan.type.caption, color = c.textMuted)
            }
        }
    }
}

// ------------------------------------------------------------------ HM-8 the table --
/**
 * HM-8: the same live data as a table — every company (any number) with its servers online, people at work, open sessions, flows in the
 * last hour and its last event; sortable; a row whose figures changed tints once. Then every server with its state and why. The reduced-
 * motion default.
 */
@Composable
fun HoldingTable(net: NetworkMap?, live: LiveState, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val nav = LocalNav.current
    val names = rememberNames()
    val now = rememberTicker(15_000)
    val all = rememberLiveCompanies(live)
    var sort by rememberSaveable { mutableStateOf("activity") }
    val rows = when (sort) {
        "servers" -> all.sortedByDescending { (it.serversTotal ?: 0) - (it.serversOnline ?: 0) }
        "people" -> all.sortedByDescending { it.working ?: -1 }
        "last" -> all.sortedByDescending { it.lastEventAt ?: 0L }
        else -> all
    }
    val servers = mapServers(net, live)
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        com.coinepro.hq.ui.v16.ChipRow {
            for ((k, t) in listOf("activity" to "فعالیت", "people" to "در کار", "servers" to "سرور قطع", "last" to "آخرین رویداد")) {
                com.coinepro.hq.designsystem.FilterChip(t, sort == k, { sort = k })
            }
        }
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile)) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 10.dp, vertical = 7.dp), verticalAlignment = Alignment.CenterVertically) {
                for ((t, wgt) in listOf("شرکت" to 1.6f, "سرور" to 1f, "در کار" to 1f, "جلسه" to 0.8f, "جریان/ساعت" to 1f, "آخرین" to 1.2f)) {
                    Text(t, Modifier.weight(wgt), style = Divan.type.micro, color = c.textMuted, maxLines = 2)
                }
            }
            for (co in rows) key(co.code) {
                HorizontalDivider(color = c.lineDivider)
                TableRow(co, live, now) { nav.go("companies/${co.code}") }
            }
        }
        if (servers.isNotEmpty()) {
            Text("سرورها", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.silverInk, modifier = Modifier.padding(top = 4.dp))
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile)) {
                servers.sortedWith(compareBy({ if (it.offline) 0 else 1 }, { it.company })).forEachIndexed { i, s ->
                    if (i > 0) HorizontalDivider(color = c.lineDivider)
                    val many = servers.count { it.company == s.company } > 1
                    Row(
                        Modifier.fillMaxWidth().clickable(role = Role.Button) { nav.go("servers/${s.id}") }.padding(horizontal = 10.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        ServerGlyph(s.state, size = 11.dp)
                        Text(serverLabel(s, many, names), style = Divan.type.small, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Text(
                            if (s.offline) timesFig("قطع · " + (s.live?.reasonFa?.ifBlank { null } ?: reasonFa(s.live?.reason))) else buildAnnotatedString { append(serverStateFa(s.state)) },
                            style = Divan.type.caption, color = if (s.offline) c.negative else c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1.4f),
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun TableRow(co: CompanyLive, live: LiveState, now: Long, onClick: () -> Unit) {
    val c = Divan.colors
    val locked = companyStateOf(co, live.control) == "locked"
    // A row whose figures changed tints once (M2).
    val sig = listOf(co.working, co.serversOnline, co.sessionsOpen, co.flowsHour)
    val tint = remember { androidx.compose.animation.core.Animatable(0f) }
    var first by remember { mutableStateOf(true) }
    val reduced = LocalReducedMotion.current
    LaunchedEffect(sig) {
        if (first || reduced) { first = false; return@LaunchedEffect }
        tint.snapTo(1f)
        tint.animateTo(0f, androidx.compose.animation.core.tween(Grammar.RIPPLE, easing = com.coinepro.hq.designsystem.Motion.Standard))
    }
    Row(
        Modifier.fillMaxWidth().background(c.softGold.copy(alpha = c.softGold.alpha * tint.value)).clickable(role = Role.Button, onClickLabel = co.nameFa, onClick = onClick)
            .padding(horizontal = 10.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Row(Modifier.weight(1.6f), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
            CompanyMark(co.code, height = 12.dp, mono = true, ink = c.textSecondary)
            Text(co.nameFa, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = if (locked) c.negative else c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        Text(co.serversOnline?.let { o -> "${faNum(o)} از ${co.serversTotal?.let(::faNum) ?: "—"}" } ?: "—", Modifier.weight(1f), style = Divan.type.caption, color = if ((co.serversOnline ?: 0) < (co.serversTotal ?: 0)) c.negative else c.textSecondary)
        Text(co.working?.let(::faNum) ?: "—", Modifier.weight(1f), style = Divan.type.caption, color = c.textSecondary)
        Text(co.sessionsOpen?.let(::faNum) ?: "—", Modifier.weight(0.8f), style = Divan.type.caption, color = c.textSecondary)
        Text(faNum(co.flowsHour), Modifier.weight(1f), style = Divan.type.caption, color = c.textSecondary)
        Text(if (locked) "قفل" else lastFa(co.lastEventAt, now), Modifier.weight(1.2f), style = Divan.type.micro, color = if (locked) c.negative else c.textMuted, maxLines = 1)
    }
}
