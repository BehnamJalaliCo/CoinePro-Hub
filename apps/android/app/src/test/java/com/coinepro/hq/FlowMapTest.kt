package com.coinepro.hq

import com.coinepro.hq.core.data.MapDims
import com.coinepro.hq.core.data.Pt
import com.coinepro.hq.core.data.centreOn
import com.coinepro.hq.core.data.clampPan
import com.coinepro.hq.core.data.dayLive
import com.coinepro.hq.core.data.dayStates
import com.coinepro.hq.core.data.fitScale
import com.coinepro.hq.core.data.flowDayStateFa
import com.coinepro.hq.core.data.flowMapLayout
import com.coinepro.hq.core.data.focusKey
import com.coinepro.hq.core.data.laneFa
import com.coinepro.hq.core.data.laneOrder
import com.coinepro.hq.core.data.legendOf
import com.coinepro.hq.core.data.mapDayFa
import com.coinepro.hq.core.data.modelFa
import com.coinepro.hq.core.data.nodeStateFa
import com.coinepro.hq.core.data.zoomAbout
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.FlowAutomation
import com.coinepro.hq.core.net.FlowGraph
import com.coinepro.hq.core.net.FlowGraphEdge
import com.coinepro.hq.core.net.FlowGraphNode
import com.coinepro.hq.core.net.LineRun
import com.coinepro.hq.core.net.StepRun
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import kotlin.math.abs

/** Contract §59.7.1 ⟨1.38⟩: the map's layout from the hub's `graph`, right to left, its lanes, the seven stories' fan-out, the view's arithmetic. */
@RunWith(RobolectricTestRunner::class)
class FlowMapTest {

    /** `N8:zaribsad_stories` as the hub draws it (domain/flow_view.py graph_of, 2026-11-15). */
    private fun stories(): FlowGraph {
        val chain = listOf("n8n" to "n8n", "order" to "hub", "data" to "workshop", "word" to "workshop", "pictures" to "chatgpt", "compose" to "workshop",
            "dm" to "workshop", "package" to "hub", "schedule" to "ighub")
        val nodes = chain.mapIndexed { i, (k, lane) -> FlowGraphNode(k, k, "workshop", null, lane, i, 0, "", if (k == "word") "claude-fable-5-2" else null) }.toMutableList()
        val edges = chain.zipWithNext { a, b -> FlowGraphEdge(a.first, b.first) }.toMutableList()
        val hours = listOf("۰۸:۳۰", "۱۰:۳۰", "۱۳:۳۰", "۱۵:۳۰", "۱۷:۳۰", "۲۰:۳۰", "۲۲:۳۰")
        for ((i, h) in hours.withIndex()) {
            nodes += FlowGraphNode("s${i + 1}", "استوری ${i + 1}", "publish", "ighub", "ighub", 9, i, "ساعت $h")
            edges += FlowGraphEdge("schedule", "s${i + 1}", "ساعت $h")
        }
        nodes += FlowGraphNode("rule", "جواب دایرکت استوری‌ها", "publish", "ighub", "ighub", 10)
        nodes += FlowGraphNode("report", "خبر به مدیر کل", "report", "code", "hub", 11)
        edges += FlowGraphEdge("s1", "rule", "وقتی اولین استوری رفت")
        edges += FlowGraphEdge("rule", "report")
        return FlowGraph(listOf("n8n", "hub", "workshop", "chatgpt", "ighub"), nodes, edges)
    }

    private val step = MapDims.NODE_W + MapDims.GAP_X

    @Test
    fun columnZeroIsOnTheRightAndTimeRunsLeft() {
        val l = flowMapLayout(stories())
        assertEquals(12, l.cols)
        assertEquals(MapDims.MARGIN * 2 + MapDims.LABEL_W + 12 * MapDims.NODE_W + 11 * MapDims.GAP_X, l.width, 0.01f)
        val n8n = l.box("n8n")!!
        assertEquals(l.width - MapDims.MARGIN - MapDims.LABEL_W - MapDims.NODE_W, n8n.x, 0.01f)
        // each column one step to the left of the one before it
        val xs = l.inTime.filter { it.row == 0 }.map { it.x }
        xs.zipWithNext { a, b -> assertEquals(step, a - b, 0.01f) }
        assertEquals(l.box("report")!!.x, MapDims.MARGIN, 0.01f)
        // the lanes' names at the start of the bands: on the right
        assertEquals(l.width - MapDims.MARGIN - MapDims.LABEL_W, l.labelX, 0.01f)
    }

    @Test
    fun leftToRightIsTheMirror() {
        val g = stories()
        val rtl = flowMapLayout(g)
        val ltr = flowMapLayout(g, rtl = false)
        for (b in rtl.nodes) {
            val m = ltr.box(b.node.key)!!
            assertEquals(rtl.width - b.x - b.w, m.x, 0.01f)
            assertEquals(b.y, m.y, 0.01f)
        }
        assertEquals(MapDims.MARGIN, ltr.labelX, 0.01f)
    }

    @Test
    fun theSevenStoriesFanOutDownTheirLane() {
        val l = flowMapLayout(stories())
        val ig = l.lanes.single { it.key == "ighub" }
        assertEquals(7, ig.rows)
        assertEquals(MapDims.LANE_PAD * 2 + 7 * MapDims.NODE_H + 6 * MapDims.ROW_GAP, ig.height, 0.01f)
        val s = (1..7).map { l.box("s$it")!! }
        assertEquals(1, s.map { it.x }.distinct().size)
        s.zipWithNext { a, b -> assertEquals(MapDims.NODE_H + MapDims.ROW_GAP, b.y - a.y, 0.01f) }
        assertEquals(ig.top + MapDims.LANE_PAD, s[0].y, 0.01f)
        // one edge to each, all out of «schedule»'s one port; each label beside its own story (level with it), inside the gap
        val fan = l.edges.filter { it.edge.source == "schedule" }
        assertEquals(7, fan.size)
        assertEquals(1, fan.map { it.from }.distinct().size)
        val schedule = l.box("schedule")!!
        for ((i, e) in fan.withIndex()) {
            assertEquals(s[i].cy, e.label.y, 0.01f)
            assertEquals(s[i].cy, e.land.y, 0.01f)
            assertTrue("label inside the gap: ${e.label.x}", e.label.x - (MapDims.LAND - 4f) / 2f > s[i].right && e.label.x + (MapDims.LAND - 4f) / 2f < schedule.x)
        }
    }

    @Test
    fun lanesKeepTheHubsOrderAndANewLaneGoesLast() {
        val g = stories()
        assertEquals(listOf("n8n", "hub", "workshop", "chatgpt", "ighub"), laneOrder(g))
        // a lane named but empty is not a band; a lane a newer hub adds goes after them
        val newer = g.copy(lanes = listOf("voice") + g.lanes, nodes = g.nodes + FlowGraphNode("x", "x", "k", null, "tiktok", 12))
        assertEquals(listOf("n8n", "hub", "workshop", "chatgpt", "ighub", "tiktok"), laneOrder(newer))
        val l = flowMapLayout(newer)
        l.lanes.zipWithNext { a, b -> assertEquals(MapDims.LANE_GAP, b.top - a.bottom, 0.01f) }
        assertEquals(l.lanes.last().bottom + MapDims.MARGIN, l.height, 0.01f)
        assertEquals("tiktok", laneFa("tiktok"))
        assertEquals("اینستاگرام", laneFa("ighub"))
    }

    @Test
    fun nodesNeverSitOnOneAnother() {
        val g = FlowGraph(listOf("hub"), listOf(FlowGraphNode("a", lane = "hub"), FlowGraphNode("b", lane = "hub"), FlowGraphNode("a", lane = "hub", col = 3)), emptyList())
        val l = flowMapLayout(g)
        assertEquals(2, l.nodes.size)
        assertEquals(0, l.box("a")!!.row)
        assertEquals(1, l.box("b")!!.row)
        assertEquals(2, l.lanes.single().rows)
    }

    @Test
    fun edgesGoFromTheSourcesSideToTheTargetsSide() {
        val l = flowMapLayout(stories().let { it.copy(edges = it.edges + FlowGraphEdge("dm", "nowhere") + FlowGraphEdge("dm", "dm")) })
        assertNull(l.edges.firstOrNull { it.edge.target == "nowhere" || it.edge.source == it.edge.target })
        val e = l.edges.first { it.edge.source == "n8n" }
        val a = l.box("n8n")!!
        val b = l.box("order")!!
        assertEquals(Pt(a.x, a.cy), e.from)
        assertEquals(Pt(b.right, b.cy), e.to)
        assertEquals(-1f, e.arrowDir)
        assertEquals(e.from, e.at(0f))
        assertEquals(e.land, e.at(0.75f))
        assertEquals(e.to.x, e.at(1f).x, 0.01f)
        // the level run into the target: the arrow's own length and more, on the target's side
        assertEquals(b.right + MapDims.LAND, e.land.x, 0.01f)
        assertEquals(1f, flowMapLayout(stories(), rtl = false).edges.first().arrowDir)
    }

    @Test
    fun theViewFitsZoomsAboutTheFingersAndStaysOnTheCanvas() {
        val l = flowMapLayout(stories())
        val fit = fitScale(l, 400f, 480f)
        assertEquals(minOf(400f / l.width, 480f / l.height), fit, 0.0001f)
        assertTrue(l.width * fit <= 400.01f && l.height * fit <= 480.01f)
        // never bigger than life
        assertEquals(1f, fitScale(flowMapLayout(FlowGraph(listOf("hub"), listOf(FlowGraphNode("a", lane = "hub")))), 2000f, 2000f), 0f)
        // the canvas point under the fingers stays under them
        val t = Pt(-300f, -120f)
        val c = Pt(180f, 240f)
        val t2 = zoomAbout(t, 0.7f, 1.1f, c)
        assertEquals((c.x - t.x) / 0.7f, (c.x - t2.x) / 1.1f, 0.01f)
        assertEquals((c.y - t.y) / 0.7f, (c.y - t2.y) / 1.1f, 0.01f)
        // a canvas wider than the view does not fly away; a narrower one sits in the middle
        val far = clampPan(Pt(5000f, -99999f), 0.72f, l, 400f, 480f)
        assertEquals(48f, far.x, 0.01f)
        assertEquals(480f - l.height * 0.72f - 48f, far.y, 0.01f)
        val small = clampPan(Pt(0f, 0f), 0.1f, l, 400f, 480f)
        assertEquals((400f - l.width * 0.1f) / 2f, small.x, 0.01f)
        // centred on a node
        val p = centreOn(l, "s5", 0.72f, 400f, 480f)
        val b = l.box("s5")!!
        assertTrue(abs(p.x + b.cx * 0.72f - 200f) < 1f)
    }

    @Test
    fun theFirstLookIsWhereTheDayIsNow() {
        val l = flowMapLayout(stories())
        // the live sample of 2026-11-15 (F-0029): three stories past their hour, one out, three waiting for theirs
        val f0029 = listOf("n8n", "order", "data", "word", "pictures", "compose", "dm", "package", "schedule").associateWith { "done" } +
            mapOf("s1" to "skipped", "s2" to "skipped", "s3" to "skipped", "s4" to "done", "s5" to "waiting", "s6" to "waiting", "s7" to "waiting", "rule" to "done", "report" to "done")
        assertEquals("s5", focusKey(l, f0029))
        assertEquals("compose", focusKey(l, f0029 + ("compose" to "running")))
        assertEquals("pictures", focusKey(l, f0029 + ("compose" to "running") + ("pictures" to "failed")))
        assertEquals("report", focusKey(l, f0029.mapValues { "done" }))
        assertEquals("n8n", focusKey(l, emptyMap()))
        assertEquals(listOf("done", "waiting", "skipped"), legendOf(stories().nodes, f0029))
        assertEquals(emptyList<String>(), legendOf(stories().nodes, emptyMap()))
    }

    @Test
    fun aDaysStepsColourItsNodes() {
        val run = LineRun("F-0029", state = "waiting", steps = listOf(StepRun("s4", state = "done"), StepRun("s5", state = "waiting")))
        assertEquals(mapOf("s4" to "done", "s5" to "waiting"), dayStates(run))
        assertEquals(emptyMap<String, String>(), dayStates(null))
        assertTrue(dayLive("waiting") && dayLive("running") && dayLive("queued"))
        assertFalse(dayLive("done") || dayLive("failed") || dayLive("cancelled"))
        assertEquals("منتظر ساعتش", nodeStateFa("waiting"))
        assertEquals("جا ماند", nodeStateFa("skipped"))
        assertEquals("هنوز نه", nodeStateFa(null))
        // an n8n day that waits for its posts' hours never says it waits for his seal
        assertNotEquals("منتظر مُهر تو", flowDayStateFa("waiting"))
        assertEquals("انجام شد", flowDayStateFa("done"))
    }

    @Test
    fun theHubsGraphReadsAndItsModelsAreNamed() {
        val body = """{"ref":"N8:zaribsad_stories","kind":"flow","company":"TY","playbook":null,"version":null,"line":null,"title_fa":"استوری‌ها",
            "state":"on","schedule":{"mode":"fixed","at":"06:00","when_fa":"هر روز ۰۶:۰۰ ساخت"},"budget":{"per_run_usd":5,"per_day_usd":5,"spent_today_usd":1.2},
            "graph":{"lanes":["n8n","hub"],"nodes":[{"key":"n8n","title_fa":"n8n روند را روشن میکند","kind":"n8n","helper":"code","lane":"n8n","col":0,"row":0,
            "note_fa":"درخواست امضاشده","model":null},{"key":"order","title_fa":"سفارش روز","kind":"order","lane":"hub","col":1}],
            "edges":[{"source":"n8n","target":"order","label_fa":""}]},"created_at":"2026-11-14T10:00:00Z"}"""
        val f = Api.json.decodeFromString(FlowAutomation.serializer(), body)
        assertTrue(f.hubOwn)
        assertEquals(2, f.graph!!.nodes.size)
        assertEquals(0, f.graph!!.nodes[1].row)
        assertEquals("order", f.graph!!.edges.single().target)
        assertNull(Api.json.decodeFromString(FlowAutomation.serializer(), """{"ref":"AT-0700"}""").graph)
        assertFalse(Api.json.decodeFromString(FlowAutomation.serializer(), """{"ref":"AT-0700"}""").hubOwn)
        assertEquals("Opus 5.5", modelFa("claude-opus-5-5"))
        assertEquals("Fable 5.2", modelFa("claude-fable-5-2"))
    }

    @Test
    fun aDaysChipSaysTodayYesterdayOrTomorrow() {
        val now = java.time.ZonedDateTime.of(2026, 11, 15, 12, 0, 0, 0, java.time.ZoneId.of("Asia/Tehran")).toInstant().toEpochMilli()
        assertEquals("امروز", mapDayFa("2026-11-15T05:00:00Z", now))
        assertEquals("دیروز", mapDayFa("2026-11-14T05:00:00Z", now))
        assertEquals("فردا", mapDayFa("2026-11-16T15:00:00Z", now))
        assertTrue(mapDayFa("2026-11-12T05:00:00Z", now).isNotBlank())
    }
}
