package com.coinepro.hq.core.data

import kotlin.math.PI
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.min

// design/LIVE_VIEWS.md §5 and rule 4, as pure geometry and counting the unit tests read: where each company sits on the map's ring (any
// number of them: full nodes up to the ring's capacity, then smaller down to a legible minimum, then a second ring, then «بقیه · n»), the
// order they sit in (by live activity, never alphabetical: the action is on top), and how many particles may fly at once (three per edge,
// twenty-four on a screen; the rest fold into «×n»).

// ------------------------------------------------------------------ rule 4: the burst limiter --
/**
 * Particles in flight per edge (at most [perEdge]) and on the screen (at most [total]); one that would pass either limit is folded into
 * its edge's «×n» chip instead of flying. [admit] says whether it may fly; [land] when it has arrived.
 */
class BurstLimiter(val perEdge: Int = 3, val total: Int = 24) {
    private val flying = HashMap<String, Int>()
    private val folded = HashMap<String, Int>()
    var inFlight: Int = 0
        private set

    /** Whether a particle on [edge] may fly now; when not, it is counted on the edge's chip. */
    @Synchronized
    fun admit(edge: String): Boolean {
        val n = flying[edge] ?: 0
        if (n >= perEdge || inFlight >= total) {
            folded[edge] = (folded[edge] ?: 0) + 1
            return false
        }
        flying[edge] = n + 1
        inFlight++
        return true
    }

    /** A particle on [edge] arrived. */
    @Synchronized
    fun land(edge: String) {
        val n = flying[edge] ?: return
        if (n <= 1) flying.remove(edge) else flying[edge] = n - 1
        inFlight = (inFlight - 1).coerceAtLeast(0)
    }

    @Synchronized
    fun flyingOn(edge: String): Int = flying[edge] ?: 0

    /** The «×n» of [edge]: every event crossing it now (those in flight and those folded), or null when none was folded. */
    @Synchronized
    fun chip(edge: String): Int? = folded[edge]?.let { it + (flying[edge] ?: 0) }

    /** The chip's count is read and gone (it faded): the next fold starts again. */
    @Synchronized
    fun clearChip(edge: String) { folded.remove(edge) }

    @Synchronized
    fun reset() { flying.clear(); folded.clear(); inFlight = 0 }
}

// ------------------------------------------------------------------ §5 scale: the ring --
/** One place on the map's company ring: a company ([code]) or the fold «بقیه · n» ([folded], [code] null). Angle in degrees, -90 = top. */
data class RingSlot(val code: String?, val ring: Int, val angle: Double, val size: Float, val folded: List<String> = emptyList()) {
    val fold: Boolean get() = code == null
}

/** The whole ring: its slots, how many rings it took, and the companies folded away (all of them are still in the table). */
data class RingPlan(val slots: List<RingSlot>, val rings: Int) {
    val folded: List<String> get() = slots.firstOrNull { it.fold }?.folded.orEmpty()
    val shown: List<String> get() = slots.mapNotNull { it.code }
}

object Ring {
    /** A company node at full size, the gap kept between two, and the legible minimum (dp). */
    const val NODE = 52f
    const val GAP = 16f
    const val MIN = 28f

    /** ⌊2πR / (node + gap)⌋, at least one. */
    fun capacity(radius: Float, node: Float, gap: Float = GAP): Int = max(1, floor(2 * PI * radius / (node + gap)).toInt())
}

private fun around(codes: List<String?>, ring: Int, size: Float, offset: Double, fold: List<String> = emptyList()): List<RingSlot> =
    codes.mapIndexed { i, c -> RingSlot(c, ring, -90.0 + 360.0 * (i + offset) / codes.size, size, if (c == null) fold else emptyList()) }

/**
 * Where [order] (already the busiest first) sits: up to the inner ring's capacity at [node] size; beyond, smaller (down to [minSize]);
 * beyond again a second ring at [r2] opens at the minimum size, and what still does not fit folds into one «بقیه · n» slot at the end
 * of the second ring (the least active). Zero companies: an empty plan (the hub alone).
 */
fun ringPlan(order: List<String>, r1: Float, r2: Float, node: Float = Ring.NODE, minSize: Float = Ring.MIN, gap: Float = Ring.GAP): RingPlan {
    val n = order.size
    if (n == 0) return RingPlan(emptyList(), 0)
    if (n <= Ring.capacity(r1, node, gap)) return RingPlan(around(order, 0, node, 0.0), 1)
    val capMin = Ring.capacity(r1, minSize, gap)
    if (n <= capMin) {
        val size = max(minSize, min(node, (2 * PI * r1 / n).toFloat() - gap))
        return RingPlan(around(order, 0, size, 0.0), 1)
    }
    val inner = order.take(capMin)
    val rest = order.drop(capMin)
    val cap2 = Ring.capacity(r2, minSize, gap)
    val outer: List<String?> = if (rest.size <= cap2) rest else rest.take(cap2 - 1) + listOf(null)
    val fold = if (rest.size <= cap2) emptyList() else rest.drop(cap2 - 1)
    return RingPlan(around(inner, 0, minSize, 0.0) + around(outer, 1, minSize, 0.5, fold), 2)
}

/** The companies busiest first: people at work, then flows in the last hour, then the latest event; the hub's own order breaks ties
 *  (never the alphabet). */
fun activityOrder(codes: List<String>, live: Map<String, CompanyLive>): List<String> {
    val index = codes.withIndex().associate { it.value to it.index }
    return codes.sortedWith(
        compareByDescending<String> { live[it]?.working ?: 0 }
            .thenByDescending { live[it]?.flowsHour ?: 0 }
            .thenByDescending { live[it]?.lastEventAt ?: 0L }
            .thenBy { index[it] ?: 0 },
    )
}

/** Each company's servers around its angle: at most [show] drawn (the rest «+n»), [spread] degrees apart, centred on the company. */
fun serverAngles(company: Double, count: Int, spread: Double, show: Int = 4): List<Double> {
    val k = min(count, show)
    if (k <= 0) return emptyList()
    return List(k) { j -> company + (j - (k - 1) / 2.0) * spread }
}

/** The particle's colour of a flow (§2 colour of motion): gold the owner's, silver the agents', lapis data and machines. */
enum class FlowInk { GOLD, SILVER, LAPIS }

fun flowInk(kind: String): FlowInk = when (kind) {
    "order", "playbook" -> FlowInk.GOLD
    "read", "job" -> FlowInk.LAPIS
    else -> FlowInk.SILVER
}

/** The legs a flow travels on the map: one edge (hub ↔ a company or a server), or two through the hub (A → hub → B). */
fun flowLegs(f: FlowLive): List<String> = when {
    f.from == "hub" || f.to == "hub" -> listOf(f.from, f.to)
    else -> listOf(f.from, "hub", f.to)
}

/** The edge a flow is counted on (rule 4): its two ends, in order. */
fun flowEdge(f: FlowLive): String = "${f.from}>${f.to}"

/** «پرو-چارت از تریدیار خواست»: what a flow was, in words (GL-4's sentence, the table, TalkBack). */
fun flowFa(f: FlowLive, name: (String) -> String): String {
    fun n(x: String) = when {
        x == "hub" -> "ستاد"
        x == "outside" -> "بیرون"
        x.startsWith("srv:") -> "سرور " + name(x.removePrefix("srv:"))
        else -> name(x)
    }
    val what = when (f.kind) {
        "order" -> "فرمان تو به ${n(f.to)} رسید"
        "request" -> "${n(f.from)} از ${n(f.to)} کار خواست"
        "accept" -> "${n(f.from)} کار ${n(f.to)} را پذیرفت"
        "deliver" -> "${n(f.from)} به ${n(f.to)} تحویل داد"
        "read" -> "${n(f.to)} داده‌ی ${n(f.from)} را خواند"
        "playbook" -> "کارگروه به ${n(f.to)} رفت"
        "publish" -> "${n(f.from)} منتشر کرد"
        "job" -> "کاری روی ${n(f.to)} شروع شد"
        "job_done" -> "کار ${n(f.from)} تمام شد"
        "job_failed" -> "کار ${n(f.from)} ناموفق شد"
        else -> "${n(f.from)} ← ${n(f.to)}"
    }
    return f.labelFa?.takeIf { it.isNotBlank() }?.let { "$what: $it" } ?: what
}
