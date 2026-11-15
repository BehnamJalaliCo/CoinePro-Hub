package com.coinepro.hq.core.data

import com.coinepro.hq.core.format.OWNER_TZ
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.instant
import com.coinepro.hq.core.format.jWeekday
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.net.FlowGraph
import com.coinepro.hq.core.net.FlowGraphEdge
import com.coinepro.hq.core.net.FlowGraphNode
import com.coinepro.hq.core.net.LineRun
import java.time.ZoneId
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

// Contract §59.7.1 ⟨1.38⟩: an automation's map, as n8n draws one. Everything here is plain arithmetic on the hub's `graph` (no map is written
// in the app): each lane a band, top to bottom in the hub's order; each node at its column (time) and row (a fan-out); right to left, so
// column 0 is on the right as Persian reads. Units are dp of the unscaled canvas; the screen scales and moves it.

object MapDims {
    const val NODE_W = 184f
    const val NODE_H = 78f
    /** Between two columns: an edge's curve, then its level run into the target with its label above it. */
    const val GAP_X = 140f
    /** The level run of an edge into its target, under its label: the labels of a fan-out each sit beside their own node. */
    const val LAND = 76f
    const val ROW_GAP = 14f
    const val LANE_PAD = 18f
    const val LANE_GAP = 8f
    /** Room at the start of the bands, so the lanes' names (on the view's edge) do not hide the first column at first. */
    const val LABEL_W = 92f
    const val MARGIN = 20f
    const val MIN_SCALE = 0.1f
    const val MAX_SCALE = 1.6f
    /** The first look: a node's title still reads and its neighbours show, centred on where the day is now. */
    const val START_SCALE = 0.6f
}

data class Pt(val x: Float, val y: Float)

data class LaneBand(val key: String, val top: Float, val height: Float, val rows: Int) {
    val bottom: Float get() = top + height
    val cy: Float get() = top + height / 2f
}

data class NodeBox(val node: FlowGraphNode, val x: Float, val y: Float, val col: Int, val row: Int) {
    val w: Float get() = MapDims.NODE_W
    val h: Float get() = MapDims.NODE_H
    val right: Float get() = x + w
    val bottom: Float get() = y + h
    val cx: Float get() = x + w / 2f
    val cy: Float get() = y + h / 2f
}

/**
 * One edge: a cubic curve out of its source's side to [land], level there, then a level run into its target's side (its arrow is level,
 * and its label sits just above that run, beside its own target, however many edges fan out of one source).
 */
data class EdgeRoute(val edge: FlowGraphEdge, val from: Pt, val c1: Pt, val c2: Pt, val land: Pt, val to: Pt) {
    /** The point at [t] along the whole edge (the curve to 3/4, then the level run), for the dots that flow along it. */
    fun at(t: Float): Pt {
        if (t >= CURVE) {
            val k = (t - CURVE) / (1f - CURVE)
            return Pt(land.x + (to.x - land.x) * k, land.y + (to.y - land.y) * k)
        }
        val s = t / CURVE
        val u = 1f - s
        val a = u * u * u
        val b = 3f * u * u * s
        val c = 3f * u * s * s
        val d = s * s * s
        return Pt(a * from.x + b * c1.x + c * c2.x + d * land.x, a * from.y + b * c1.y + c * c2.y + d * land.y)
    }

    /** The middle of the level run: the label's bottom centre sits just above it. */
    val label: Pt get() = Pt((land.x + to.x) / 2f, to.y)

    /** +1 when the arrow points right, -1 when it points left. */
    val arrowDir: Float get() = if (to.x >= land.x) 1f else -1f

    private companion object { const val CURVE = 0.75f }
}

data class FlowMapLayout(
    val width: Float,
    val height: Float,
    val lanes: List<LaneBand>,
    val nodes: List<NodeBox>,
    val edges: List<EdgeRoute>,
    val cols: Int,
    val rtl: Boolean,
) {
    private val byKey = nodes.associateBy { it.node.key }
    fun box(key: String): NodeBox? = byKey[key]

    /** The left edge of the lanes' names (at the start of each band). */
    val labelX: Float get() = if (rtl) width - MapDims.MARGIN - MapDims.LABEL_W else MapDims.MARGIN

    /** The nodes in time: by column, then row. */
    val inTime: List<NodeBox> get() = nodes.sortedWith(compareBy({ it.col }, { it.row }))
}

/** The lanes in their order on the canvas: the hub's `lanes` that hold a node, then any lane a node names that `lanes` does not (a newer hub). */
fun laneOrder(g: FlowGraph): List<String> {
    val used = g.nodes.map { it.lane }.distinct()
    return g.lanes.distinct().filter { it in used } + used.filter { it !in g.lanes }
}

/**
 * The canvas of [g]. Nodes that would sit on one another (the same lane, column and row) go down a row, so a careless map still reads; a
 * node whose key repeats is drawn once. An edge to or from a node that is not there, or to itself, is left out.
 */
fun flowMapLayout(g: FlowGraph, rtl: Boolean = true): FlowMapLayout {
    val nodes = g.nodes.distinctBy { it.key }.filter { it.key.isNotBlank() }
    val lanes = laneOrder(g.copy(nodes = nodes))
    // rows, with a node that lands on a taken place moved down
    val taken = HashSet<Triple<String, Int, Int>>()
    val placed = nodes.map { n ->
        val col = n.col.coerceAtLeast(0)
        var row = n.row.coerceAtLeast(0)
        while (!taken.add(Triple(n.lane, col, row))) row++
        Triple(n, col, row)
    }
    val cols = (placed.maxOfOrNull { it.second } ?: -1) + 1
    val bands = ArrayList<LaneBand>()
    var y = MapDims.MARGIN
    for (lane in lanes) {
        val rows = (placed.filter { it.first.lane == lane }.maxOfOrNull { it.third } ?: 0) + 1
        val h = MapDims.LANE_PAD * 2 + rows * MapDims.NODE_H + (rows - 1) * MapDims.ROW_GAP
        bands += LaneBand(lane, y, h, rows)
        y += h + MapDims.LANE_GAP
    }
    val height = if (bands.isEmpty()) MapDims.MARGIN * 2 else bands.last().bottom + MapDims.MARGIN
    val width = MapDims.MARGIN * 2 + MapDims.LABEL_W + cols * MapDims.NODE_W + max(0, cols - 1) * MapDims.GAP_X
    val step = MapDims.NODE_W + MapDims.GAP_X
    val band = bands.associateBy { it.key }
    val boxes = placed.map { (n, col, row) ->
        val x = if (rtl) width - MapDims.MARGIN - MapDims.LABEL_W - col * step - MapDims.NODE_W else MapDims.MARGIN + MapDims.LABEL_W + col * step
        val b = band.getValue(n.lane)
        NodeBox(n, x, b.top + MapDims.LANE_PAD + row * (MapDims.NODE_H + MapDims.ROW_GAP), col, row)
    }
    val byKey = boxes.associateBy { it.node.key }
    val dir = if (rtl) -1f else 1f
    val routes = g.edges.mapNotNull { e ->
        val s = byKey[e.source] ?: return@mapNotNull null
        val t = byKey[e.target] ?: return@mapNotNull null
        if (s === t) return@mapNotNull null
        val from = Pt(if (rtl) s.x else s.right, s.cy)
        val to = Pt(if (rtl) t.right else t.x, t.cy)
        val land = Pt(to.x - dir * MapDims.LAND, to.y)
        val pull = max(28f, abs(land.x - from.x) / 2f)
        EdgeRoute(e, from, Pt(from.x + dir * pull, from.y), Pt(land.x - dir * pull, land.y), land, to)
    }
    return FlowMapLayout(width, height, bands, boxes, routes, cols, rtl)
}

// ----------------------------------------------------------------------------------------------- the view --
/** The scale that shows the whole canvas in a view of [viewW]×[viewH] (never bigger than life). */
fun fitScale(l: FlowMapLayout, viewW: Float, viewH: Float): Float =
    if (l.width <= 0f || l.height <= 0f || viewW <= 0f || viewH <= 0f) 1f
    else min(viewW / l.width, viewH / l.height).coerceIn(MapDims.MIN_SCALE, 1f)

/** Keeps the canvas in the view: centred along a side it does not fill, else no further than [slack] past its edge. */
fun clampPan(t: Pt, scale: Float, l: FlowMapLayout, viewW: Float, viewH: Float, slack: Float = 48f): Pt {
    val w = l.width * scale
    val h = l.height * scale
    val x = if (w <= viewW) (viewW - w) / 2f else t.x.coerceIn(viewW - w - slack, slack)
    val y = if (h <= viewH) (viewH - h) / 2f else t.y.coerceIn(viewH - h - slack, slack)
    return Pt(x, y)
}

/** The pan that keeps the canvas point under [c] (a view point) where it is while the scale goes from [scale] to [next]. */
fun zoomAbout(t: Pt, scale: Float, next: Float, c: Pt): Pt = Pt(c.x - (c.x - t.x) * next / scale, c.y - (c.y - t.y) * next / scale)

/** The pan that puts [key]'s node in the middle of the view at [scale]. */
fun centreOn(l: FlowMapLayout, key: String?, scale: Float, viewW: Float, viewH: Float): Pt {
    val b = key?.let(l::box) ?: l.inTime.firstOrNull() ?: return Pt(0f, 0f)
    return clampPan(Pt(viewW / 2f - b.cx * scale, viewH / 2f - b.cy * scale), scale, l, viewW, viewH)
}

/** Where the day is now, to look at first: a node that failed, else one at work, else one waiting, else the last one done, else the first. */
fun focusKey(l: FlowMapLayout, states: Map<String, String>): String? {
    val t = l.inTime
    return t.firstOrNull { states[it.node.key] == "failed" }?.node?.key
        ?: t.firstOrNull { states[it.node.key] == "running" }?.node?.key
        ?: t.firstOrNull { states[it.node.key] == "waiting" }?.node?.key
        ?: t.lastOrNull { states[it.node.key] == "done" }?.node?.key
        ?: t.firstOrNull()?.node?.key
}

// --------------------------------------------------------------------------------------------- the words --
/** Each node's state that day, by its key; a node the day has no step for is `pending`. Null run: no day chosen, no colours. */
fun dayStates(run: LineRun?): Map<String, String> = run?.steps?.associate { it.key to it.state }.orEmpty()

const val NODE_PENDING = "pending"
val MAP_STATES: List<String> = listOf("done", "running", "waiting", "failed", "skipped", NODE_PENDING)

/** A node's state in the owner's words. `waiting` is held in IG-Hub until its hour; `skipped` is a story whose hour had gone. */
fun nodeStateFa(state: String?): String = when (state) {
    "done" -> "تمام شد"
    "running" -> "در کار"
    "waiting" -> "منتظر ساعتش"
    "failed" -> "نشد"
    "skipped" -> "جا ماند"
    else -> "هنوز نه"
}

fun nodeStateTone(state: String?): Tone = when (state) {
    "done" -> Tone.POS
    "running" -> Tone.LAPIS
    "waiting" -> Tone.WARN
    "failed" -> Tone.NEG
    else -> Tone.SILVER
}

/** The states a day's map holds, in the legend's order. */
fun legendOf(nodes: List<FlowGraphNode>, states: Map<String, String>): List<String> {
    if (states.isEmpty()) return emptyList()
    val here = nodes.map { states[it.key] ?: NODE_PENDING }.toSet()
    return MAP_STATES.filter { it in here }
}

/** A day of an n8n flow (§59.7.1) in the owner's words: `waiting` is a day whose posts wait for their hours, never his seal. */
fun flowDayStateFa(state: String?): String = when (state) {
    "waiting" -> "منتظر ساعت انتشار"
    "queued" -> "در صف کارگاه"
    else -> lineRunStateFa(state)
}

fun flowDayStateTone(state: String?): Tone = when (state) {
    "running" -> Tone.LAPIS
    "waiting" -> Tone.WARN
    else -> lineRunStateTone(state)
}

/** Has the day still something to do (read it again every 15 s)? */
fun dayLive(state: String?): Boolean = state in setOf("queued", "running", "waiting")

/** A lane by name: who does the steps on it. */
fun laneFa(lane: String): String = when (lane) {
    "n8n" -> "n8n"
    "hub" -> "ستاد"
    "workshop" -> "کارگاه Claude"
    "chatgpt" -> "ChatGPT"
    "gemini" -> "Gemini"
    "voice" -> "گوینده"
    "ighub" -> "اینستاگرام"
    else -> lane
}

/** A day's chip: «امروز», «دیروز», «فردا», else its weekday and date. */
fun mapDayFa(iso: String?, now: Long = HqClock.millis()): String {
    val t = instant(iso) ?: return "—"
    val zone = ZoneId.of(OWNER_TZ)
    val day = t.atZone(zone).toLocalDate()
    val today = java.time.Instant.ofEpochMilli(now).atZone(zone).toLocalDate()
    return when (day) {
        today -> "امروز"
        today.minusDays(1) -> "دیروز"
        today.plusDays(1) -> "فردا"
        else -> jWeekday(iso).replace(Regex("\\s+\\S+$"), "")
    }
}
