package com.coinepro.hq

import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.HubServer
import com.coinepro.hq.core.net.LinkHealth
import com.coinepro.hq.core.net.NetLink
import com.coinepro.hq.core.net.NetNode
import com.coinepro.hq.core.net.Network
import com.coinepro.hq.core.net.NetworkMap
import com.coinepro.hq.core.net.TokenSource
import com.coinepro.hq.ui.servers.headline
import com.coinepro.hq.ui.servers.outsideHint
import com.coinepro.hq.ui.servers.ringAngles
import com.coinepro.hq.ui.servers.serverNameOf
import com.coinepro.hq.core.format.Tone
import kotlinx.coroutines.test.runTest
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** ⟨1.8⟩ Contract §26.6: the holding's network map — read from the wire, each road's health, the map in words (what is broken, who is
 *  outside the private network and where it should go), following a check, and the owner's rule that a server is named by its company. */
@RunWith(RobolectricTestRunner::class)
class NetworkTest {
    private val server = MockWebServer()
    private lateinit var api: Api

    @Before
    fun setUp() {
        server.start()
        api = Api(server.url("/").toString(), object : TokenSource { override fun token() = "t"; override fun clear() = Unit })
    }

    @After
    fun tearDown() = server.close()

    private fun json(code: Int, body: String) = MockResponse.Builder().code(code).addHeader("Content-Type", "application/json").body(body).build()

    private val hub = NetNode("hub", "HQ", "hub", "10.10.1.4", state = "online")
    private fun node(id: String, co: String, ip: String?, via: String = "private", rtt: Double? = 3.0, state: String = "online") =
        NetNode(id, co, id, ip, via, state, rtt)
    private fun ok(from: String, to: String, port: Int, ms: Double = 0.6, at: String = "2026-10-30T06:00:00Z") = NetLink(from, to, port, true, ms, null, at)
    private fun bad(from: String, to: String, port: Int, error: String = "timeout", at: String = "2026-10-30T06:00:00Z") = NetLink(from, to, port, false, null, error, at)

    /** Every runner reaches the hub on 443 and every other private address on 22, 80 and 443. */
    private fun mesh(nodes: List<NetNode>, at: String = "2026-10-30T06:00:00Z", broken: (NetNode, NetNode, Int) -> String? = { _, _, _ -> null }): List<NetLink> =
        nodes.flatMap { f ->
            listOf(ok(f.id, "hub", 443, at = at)) + nodes.filter { it.id != f.id && !it.privateIp.isNullOrBlank() }.flatMap { t ->
                NetworkMap.PORTS.map { p ->
                    val e = if (f.privateIp.isNullOrBlank()) "timeout" else broken(f, t, p)
                    if (e != null) bad(f.id, t.id, p, e, at) else ok(f.id, t.id, p, at = at)
                }
            }
        }

    private val fx = node("srv-fx-1", "FX", "10.10.1.2", rtt = 3.0)
    private val ty = node("srv-ty-1", "TY", "10.10.1.3", rtt = 2.0)
    private val pc = node("srv-pc-1", "PC", "10.10.1.1", rtt = 2.4)
    private val ig = node("srv-ig-1", "IG", null, via = "public", rtt = 41.0)

    /** The demo's network: PC cannot open FX's SSH port, IG-Hub is not on the private network. */
    private val demo = NetworkMap(
        "2026-10-30T08:00:00Z", listOf(hub, fx, ty, pc, ig),
        mesh(listOf(fx, ty, pc, ig)) { f, t, p -> if (f.id == "srv-pc-1" && t.id == "srv-fx-1" && p == 22) "connection refused" else null },
    )

    // ------------------------------------------------------------------ health --
    @Test
    fun aRoadIsGreenAmberRedOrGrey() {
        assertEquals(LinkHealth.OK, Network.health(true, 3.0))
        assertEquals(LinkHealth.OK, Network.health(true, 150.0))
        assertEquals("slower than 150 ms is amber", LinkHealth.SLOW, Network.health(true, 150.1))
        assertEquals(LinkHealth.OK, Network.health(true, null))
        assertEquals(LinkHealth.FAIL, Network.health(false, null))
        assertEquals(LinkHealth.FAIL, Network.health(false, 12.0))
        assertEquals(LinkHealth.UNKNOWN, Network.health(null, null))
    }

    @Test
    fun theHubLineFollowsTheRunnersStateItsCheckAndItsRoundTrip() {
        assertEquals(LinkHealth.OK, Network.hubLine(demo, fx).health)
        assertEquals(3.0, Network.hubLine(demo, fx).rttMs!!, 0.0)
        assertEquals("private", Network.hubLine(demo, fx).via)
        assertEquals("public", Network.hubLine(demo, ig).via)
        val slow = node("s", "FX", "10.10.1.9", rtt = 220.0)
        assertEquals(LinkHealth.SLOW, Network.hubLine(NetworkMap(nodes = listOf(hub, slow)), slow).health)
        val off = node("o", "FX", "10.10.1.9", state = "offline")
        assertEquals(LinkHealth.FAIL, Network.hubLine(NetworkMap(nodes = listOf(hub, off)), off).health)
        assertEquals("offline", Network.hubLine(NetworkMap(nodes = listOf(hub, off)), off).error)
        val pending = node("p", "FX", "10.10.1.9", rtt = null, state = "pending")
        assertEquals(LinkHealth.UNKNOWN, Network.hubLine(NetworkMap(nodes = listOf(hub, pending)), pending).health)
        val broken = node("b", "FX", "10.10.1.9", rtt = null)
        val m = NetworkMap(nodes = listOf(hub, broken), links = listOf(bad("b", "hub", 443, "connection refused")))
        assertEquals(LinkHealth.FAIL, Network.hubLine(m, broken).health)
        assertNull("a broken road has no round trip", Network.hubLine(m, broken).rttMs)
    }

    @Test
    fun roundTripsAreLatinFigures() {
        assertEquals("3 ms", Network.ms(3.0))
        assertEquals("0.4 ms", Network.ms(0.4))
        assertEquals("41 ms", Network.ms(41.2))
        assertEquals("1.2 s", Network.ms(1_234.0))
        assertNull(Network.ms(null))
    }

    // ------------------------------------------------------------------ the wire --
    @Test
    fun theMapIsReadFromTheContractsShape() = runTest {
        server.enqueue(json(200, """{"at":"2026-10-30T08:00:00Z",
            "nodes":[{"id":"hub","company":"HQ","name":"hub","private_ip":"10.10.1.4","via":null,"state":"online","hub_rtt_ms":null},
                     {"id":"srv-fx-1","company":"FX","name":"fx-main","private_ip":"10.10.1.2","via":"private","state":"online","hub_rtt_ms":3},
                     {"id":"srv-ig-1","company":"IG","name":"IG-Hub","private_ip":null,"via":"public","state":"online","hub_rtt_ms":41.5,"new_field":1}],
            "links":[{"from":"srv-fx-1","to":"hub","port":443,"ok":true,"ms":3.6,"error":null,"at":"2026-10-30T07:59:00Z"},
                     {"from":"srv-ig-1","to":"srv-fx-1","port":22,"ok":false,"ms":null,"error":"timeout","at":"2026-10-30T07:59:30Z"}]}"""))
        val m = api.network()
        assertEquals("/api/v1/infra/network", server.takeRequest().url.encodedPath)
        assertEquals(listOf("hub", "srv-fx-1", "srv-ig-1"), m.all.map { it.id })
        assertEquals(3.0, m.node("srv-fx-1")!!.hubRttMs!!, 0.0)
        assertTrue(m.node("srv-ig-1")!!.outside)
        assertFalse(m.node("srv-fx-1")!!.outside)
        assertEquals("timeout", m.link("srv-ig-1", "srv-fx-1", 22)!!.error)
        assertEquals("2026-10-30T07:59:30Z", m.lastAt)
    }

    @Test
    fun aMapWithoutTheHubStillHasItInTheCentre() {
        val m = NetworkMap(nodes = listOf(fx, node("srv-ty-2", "TY", "10.10.1.13", state = "revoked")))
        assertEquals("hub", m.all.first().id)
        assertEquals(NetworkMap.HUB_IP, m.all.first().privateIp)
        assertEquals("a revoked server is off the map", listOf("srv-fx-1"), m.servers.map { it.id })
    }

    @Test
    fun theCheckIsQueuedWithAPost() = runTest {
        server.enqueue(json(202, """{"queued":4}"""))
        api.checkNetwork()
        val r = server.takeRequest()
        assertEquals("POST", r.method)
        assertEquals("/api/v1/infra/network/check", r.url.encodedPath)
    }

    @Test
    fun aServerRowCarriesItsRoad() {
        val s = Api.json.decodeFromString(HubServer.serializer(), """{"id":"srv-fx-1","company":"FX","name":"fx-main","via":"public","hub_rtt_ms":38.5}""")
        assertEquals("public", s.via)
        assertEquals(38.5, s.hubRttMs!!, 0.0)
    }

    // ------------------------------------------------------------------ in words --
    @Test
    fun theDemoNetworkSaysOneRoadIsBrokenAndIgHubIsOutside() {
        val s = Network.summary(demo)
        assertEquals(4, s.servers)
        // IG-Hub's nine timeouts towards private addresses are one issue (join the network), not nine broken roads.
        assertEquals(listOf("srv-pc-1" to "srv-fx-1"), s.failed.map { it.from.id to it.to.id })
        assertEquals(listOf(22), s.failed.single().ports)
        assertEquals("connection refused", s.failed.single().error)
        assertFalse(s.failed.single().toHub)
        assertTrue(s.hubOk)
        assertEquals(listOf("srv-ig-1"), s.outside.map { it.id })
        assertEquals("10.10.1.5", s.nextFreeIp)
        assertFalse(s.allOk)
        assertEquals("1 مسیر قطع است" to Tone.NEG, headline(s))
        assertEquals("پورت بسته است", Network.errorFa("connection refused"))
        assertTrue(outsideHint(s.nextFreeIp).contains("کنسول هتزنر"))
        assertTrue(outsideHint(s.nextFreeIp).contains("10.10.1.5"))
    }

    @Test
    fun aHealthyNetworkSaysEveryServerReachesTheHub() {
        val igIn = ig.copy(privateIp = "10.10.1.5", via = "private", hubRttMs = 2.8)
        val m = NetworkMap(nodes = listOf(hub, fx, ty, pc, igIn), links = mesh(listOf(fx, ty, pc, igIn)))
        val s = Network.summary(m)
        assertTrue(s.allOk)
        assertTrue(s.failed.isEmpty())
        assertEquals("همه‌ی سرورها به هاب وصل‌اند" to Tone.POS, headline(s))
        assertEquals("10.10.1.6", s.nextFreeIp)
    }

    @Test
    fun aPortThatAnsweredSinceIsNotBroken() {
        val m = NetworkMap(nodes = listOf(hub, fx, pc), links = mesh(listOf(fx, pc)) { f, _, p -> if (f.id == "srv-pc-1" && p == 22) "timeout" else null } +
            ok("srv-pc-1", "srv-fx-1", 22, at = "2026-10-30T07:00:00Z"))
        assertTrue(Network.summary(m).failed.isEmpty())
    }

    @Test
    fun anOfflineRunnerIsABrokenRoadToTheHubAndASlowOneIsNamed() {
        val off = node("srv-fx-2", "FX", "10.10.1.12", state = "offline", rtt = null)
        val slow = node("srv-ty-1", "TY", "10.10.1.3", rtt = 230.0)
        val fell = node("srv-pc-1", "PC", "10.10.1.1", via = "public", rtt = 40.0)
        val m = NetworkMap(nodes = listOf(hub, off, slow, fell), links = mesh(listOf(slow, fell)))
        val s = Network.summary(m)
        assertEquals(listOf("srv-fx-2"), s.failed.filter { it.toHub }.map { it.from.id })
        assertEquals("offline", s.failed.single().error)
        assertFalse(s.hubOk)
        assertEquals(listOf("srv-ty-1"), s.slow.map { it.node.id })
        assertEquals("on the network, but came over the public road", listOf("srv-pc-1"), s.fellBack.map { it.id })
        assertEquals("1 مسیر قطع است", headline(s).first)
        val noFail = Network.summary(NetworkMap(nodes = listOf(hub, slow), links = mesh(listOf(slow))))
        assertEquals("همه‌ی سرورها به هاب وصل‌اند؛ 1 راه کند است" to Tone.WARN, headline(noFail))
    }

    // ------------------------------------------------------------------ following a check --
    @Test
    fun aCheckIsDoneWhenEveryOnlineRunnerHasReportedSinceItWasQueued() {
        val before = demo
        val nodes = listOf(fx, ty, pc, ig)
        val p0 = Network.progress(before, before)
        assertEquals(setOf("srv-fx-1", "srv-ty-1", "srv-pc-1", "srv-ig-1"), p0.expected)
        assertTrue(p0.reported.isEmpty())
        assertFalse(p0.done)
        // FX and TY answered; their links are newer than anything the map had.
        val later = "2026-10-30T08:31:00Z"
        val half = before.copy(links = before.links.filter { it.from !in setOf("srv-fx-1", "srv-ty-1") } + mesh(nodes).filter { it.from in setOf("srv-fx-1", "srv-ty-1") }.map { it.copy(at = later) })
        val p1 = Network.progress(before, half)
        assertEquals(setOf("srv-fx-1", "srv-ty-1"), p1.reported)
        assertEquals(0.5f, p1.fraction, 0.001f)
        assertFalse(p1.done)
        val all = before.copy(links = before.links.map { it.copy(at = later) })
        assertTrue(Network.progress(before, all).done)
        // An offline runner is not waited for.
        val withOff = all.copy(nodes = all.nodes + node("srv-fx-2", "FX", "10.10.1.12", state = "offline"))
        assertTrue(Network.progress(before, withOff).done)
    }

    // ------------------------------------------------------------------ names --
    @Test
    fun aServerIsNamedByItsCompanyAndItsOwnNameOnlyWhenTheCompanyHasSeveral() {
        assertEquals("تریدیار", serverNameOf("TY", "تریدیار", "ty-web", 1).text)
        assertNull(serverNameOf("TY", "تریدیار", "ty-web", 1).server)
        assertEquals("تریدیار · ty-web", serverNameOf("TY", "تریدیار", "ty-web", 2).text)
        assertEquals("a company the list does not know keeps its code", "IG", serverNameOf("IG", null, "IG-Hub", 1).text)
    }

    @Test
    fun theServersOfOneCompanySitTogetherAroundTheHub() {
        val a = ringAngles(listOf(fx, fx.copy(id = "srv-fx-2"), ty, pc))
        // Three companies: a gap after each group, so 7 slots; FX's two servers are neighbours, then a gap.
        assertEquals(-90.0, a[0], 0.001)
        assertEquals(-90.0 + 360.0 / 7, a[1], 0.001)
        assertEquals(-90.0 + 3 * 360.0 / 7, a[2], 0.001)
        assertEquals(-90.0 + 5 * 360.0 / 7, a[3], 0.001)
        assertEquals(listOf(-90.0), ringAngles(listOf(fx)))
    }
}
