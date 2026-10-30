package com.coinepro.hq

import com.coinepro.hq.core.net.Actor
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.AttachIn
import com.coinepro.hq.core.net.AttachRules
import com.coinepro.hq.core.net.CallOutcome
import com.coinepro.hq.core.net.Decision
import com.coinepro.hq.core.net.ExecIn
import com.coinepro.hq.core.net.HubServer
import com.coinepro.hq.core.net.SEAL_CATEGORIES
import com.coinepro.hq.core.net.ServerCall
import com.coinepro.hq.core.net.ServerMaps
import com.coinepro.hq.core.net.ServerPolicy
import com.coinepro.hq.core.net.SseParser
import com.coinepro.hq.core.net.StreamEvent
import com.coinepro.hq.core.net.TermEvent
import com.coinepro.hq.core.net.TermHistory
import com.coinepro.hq.core.net.TermKind
import com.coinepro.hq.core.net.TerminalBuffer
import com.coinepro.hq.core.net.TokenSource
import com.coinepro.hq.core.net.callRow
import com.coinepro.hq.core.net.duration
import com.coinepro.hq.core.net.sealAction
import com.coinepro.hq.core.net.sealCardOf
import com.coinepro.hq.core.net.sealTarget
import com.coinepro.hq.core.net.termEventOf
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** ⟨1.8⟩ Contract §26: the companies' servers — the map read whatever shape it comes in, the activity rows, the seal card, the server
 *  rules, attaching a server, and the owner's terminal from the SSE bytes to the lines on screen. */
@RunWith(RobolectricTestRunner::class)
class ServersTest {
    private val server = MockWebServer()
    private lateinit var api: Api
    private val GIB = 1024L * 1024 * 1024

    @Before
    fun setUp() {
        server.start()
        api = Api(server.url("/").toString(), object : TokenSource { override fun token() = "t"; override fun clear() = Unit })
    }

    @After
    fun tearDown() = server.close()

    private fun json(code: Int, body: String) = MockResponse.Builder().code(code).addHeader("Content-Type", "application/json").body(body).build()
    private fun obj(s: String) = Api.json.parseToJsonElement(s)

    // ------------------------------------------------------------------ server.map --
    @Test
    fun aMapInTheCanonicalShapeIsReadWhole() {
        val m = ServerMaps.parse(obj("""{"taken_at":"2026-10-17T08:18:00Z","hostname":"coinepro-fx",
            "os":{"name":"Ubuntu","version":"24.04.1 LTS","kernel":"6.8.0-47-generic"},"cpus":8,"uptime_s":1900800,"load":[0.84,0.9,0.88],
            "disks":[{"mount":"/","total_bytes":${150 * GIB},"used_bytes":${62 * GIB}}],
            "memory":{"total_bytes":${16 * GIB},"used_bytes":${12 * GIB}},"swap":{"total_bytes":${8 * GIB},"used_bytes":0},
            "containers":[{"name":"api-1","image":"fx-api:a41","state":"running","status":"Up 3 minutes","compose_project":"coinepro-fx"},
                          {"name":"backtest-1","image":"fx-api:c9b","state":"exited","status":"Exited (0)"}],
            "compose":[{"project":"coinepro-fx","dir":"/home/forex/CoinePro-FX","services":10,"running":9}],
            "systemd":{"units":[{"name":"docker.service","state":"active"}],"timers":[{"unit":"fx-backup.timer","next":"2026-10-17T10:05:00Z","activates":"fx-backup.service"}]},
            "cron":[{"schedule":"*/5 * * * *","command":"scripts/healthcheck.sh","user":"forex"}],
            "ports":[{"port":443,"proto":"tcp","address":"0.0.0.0","process":"caddy"},{"port":22,"address":"10.10.1.2","process":"sshd"}],
            "repos":[{"path":"/home/forex/CoinePro-FX","remote":"git@github.com:o/CoineProFx.git","branch":"main","head":"a41c09e5f2b7d81c","dirty":true}],
            "n8n":{"workflows":[{"name":"گزارش روزانه","active":true,"trigger":"cron 08:00"},{"name":"بک‌تست","active":false}]},
            "automations":[{"kind":"celery-beat","name":"candles","active":true,"detail":"every 1m"}],
            "sites":[{"domain":"coineprofx.com","upstream":"website:80","tls":true,"server":"caddy"}]}"""))!!
        assertEquals("2026-10-17T08:18:00Z", m.at)
        assertEquals("Ubuntu 24.04.1 LTS", m.os)
        assertEquals("6.8.0-47-generic", m.kernel)
        assertEquals(8, m.cpus)
        assertEquals(0.84, m.load!!, 0.001)
        assertEquals(62 * GIB, m.disks.single().usedBytes)
        assertEquals(41.33, m.disks.single().pct, 0.01)
        assertEquals(75.0, m.memory!!.pct, 0.01)
        assertNull("an empty swap is no swap", m.swap?.takeIf { it.totalBytes == 0L })
        assertEquals(1, m.runningContainers)
        assertEquals("coinepro-fx", m.containers.first().project)
        assertEquals(9, m.compose.single().running)
        assertEquals("fx-backup.timer", m.timers.single().unit)
        assertEquals("docker.service", m.units.single().name)
        assertEquals("forex", m.cron.single().user)
        assertEquals(listOf(22, 443), m.ports.map { it.port })
        assertEquals("a41c09e5f2b7", m.repos.single().head)
        assertEquals(true, m.repos.single().dirty)
        assertEquals(listOf("celery-beat", "n8n", "n8n"), m.automations.map { it.kind })
        assertEquals(false, m.automations.last().active)
        assertEquals(true, m.sites.single().tls)
        assertFalse(m.empty)
    }

    @Test
    fun aMapWrittenLikeTheShellPrintsItIsReadToo() {
        // Sizes as `df -h` writes them, memory with what is available, `docker ps`'s names and labels, `docker compose ls`'s status,
        // crontab lines, `ss` addresses, a remote list, nginx's server_name.
        val m = ServerMaps.parse(obj("""{"map":{"os":"Ubuntu 24.04.1 LTS","disk":{"mount":"/","size":"150G","used":"97G"},
            "memory":{"total":"16Gi","available":"4Gi"},
            "containers":[{"names":["/ty-app-1"],"image":"app","status":"Up 5 days","labels":{"com.docker.compose.project":"tradeyar"}},"ty-redis-1"],
            "compose_projects":[{"name":"tradeyar","config_files":"/home/ty/docker-compose.yml","status":"running(4)","services":4}],
            "timers":["ty-sitemap.timer"],
            "crontab":["# a comment","0 3 * * * /home/ty/backup.sh --all","@daily /usr/bin/true"],
            "listening":["0.0.0.0:443","127.0.0.1:5432/tcp","[::]:22",8080,"nonsense"],
            "repositories":[{"path":"/home/ty/TradeYar","remotes":[{"name":"origin","url":"git@github.com:o/TradeYar.git"}],"commit":"5be0a7d91c3e00"}],
            "sites":[{"server_name":"tradeyar.com","proxy_pass":"http://127.0.0.1:3000","https":true,"via":"nginx"},"old.tradeyar.com"]},
            "taken_at":"2026-10-17T07:50:00Z"}"""))!!
        assertEquals("2026-10-17T07:50:00Z", m.at)
        assertEquals("Ubuntu 24.04.1 LTS", m.os)
        assertEquals(150 * GIB, m.disks.single().totalBytes)
        assertEquals(97 * GIB, m.disks.single().usedBytes)
        assertEquals(12 * GIB, m.memory!!.usedBytes)
        assertEquals(listOf("ty-app-1", "ty-redis-1"), m.containers.map { it.name })
        assertEquals("tradeyar", m.containers.first().project)
        assertEquals("running", m.containers.first().state)
        assertEquals(4, m.compose.single().running)
        assertEquals("/home/ty/docker-compose.yml", m.compose.single().dir)
        assertEquals("ty-sitemap.timer", m.timers.single().unit)
        assertEquals(listOf("0 3 * * *" to "/home/ty/backup.sh --all", "@daily" to "/usr/bin/true"), m.cron.map { it.schedule to it.command })
        assertEquals(listOf(22, 443, 5432, 8080), m.ports.map { it.port })
        assertEquals("127.0.0.1", m.ports.first { it.port == 5432 }.address)
        assertEquals("git@github.com:o/TradeYar.git", m.repos.single().remote)
        assertEquals("5be0a7d91c3e", m.repos.single().head)
        assertEquals(listOf("tradeyar.com", "old.tradeyar.com"), m.sites.map { it.domain })
        assertEquals("nginx", m.sites.first().server)
    }

    @Test
    fun aMapThatDoesNotFitLeavesOutWhatItCannotRead() {
        assertNull(ServerMaps.parse(null))
        assertNull(ServerMaps.parse(obj("[]")))
        val m = ServerMaps.parse(obj("""{"os":42,"disks":"full","memory":{"used":"lots"},"containers":[null,{"image":"x"},3],"ports":[{"proto":"udp"}],"cron":["* *"]}"""))!!
        assertTrue(m.empty)
        assertTrue(m.containers.isEmpty())
        assertTrue(m.ports.isEmpty())
        assertTrue(m.cron.isEmpty())
    }

    @Test
    fun sizesAreReadAndWrittenInBinaryUnits() {
        assertEquals(150 * GIB, ServerMaps.bytes(JsonPrimitive("150G")))
        assertEquals((15.5 * GIB).toLong(), ServerMaps.bytes(JsonPrimitive("15.5GiB")))
        assertEquals(512L * 1024 * 1024, ServerMaps.bytes(JsonPrimitive("512 MB")))
        assertEquals(1024L, ServerMaps.bytes(JsonPrimitive(1024)))
        assertNull(ServerMaps.bytes(JsonPrimitive("a lot")))
        assertEquals("62 GB", ServerMaps.size(62 * GIB))
        assertEquals("1.5 TB", ServerMaps.size(1536 * GIB))
        assertEquals("512 MB", ServerMaps.size(512L * 1024 * 1024))
        assertEquals("900 B", ServerMaps.size(900))
    }

    // ------------------------------------------------------------------ activity --
    @Test
    fun activityRowsSayHowEachCallEnded() {
        val ok = callRow(ServerCall(at = "t", actor = Actor("FX-TECH-MGR", "manager", "مدیر فنی FX"), tool = "server.exec", summaryFa = "migration", cmdMasked = "alembic upgrade head", exitCode = 0, durationMs = 6_420, sessionRef = "S-0004", transcriptUrl = "/api/v1/x"))
        assertEquals(CallOutcome.OK, ok.outcome)
        assertEquals("فرمان", ok.toolFa)
        assertEquals("6.4s", ok.duration)
        assertEquals("S-0004", ok.sessionRef)
        assertFalse(ok.byOwner)
        assertEquals(CallOutcome.FAILED, callRow(ServerCall(exitCode = 2, durationMs = 10)).outcome)
        assertEquals(CallOutcome.RUNNING, callRow(ServerCall(cmdMasked = "docker compose up -d --build api")).outcome)
        assertEquals(CallOutcome.AWAITING_SEAL, callRow(ServerCall(state = "awaiting_seal")).outcome)
        assertEquals(CallOutcome.OK, callRow(ServerCall(tool = "server.map", durationMs = 3_870)).outcome)
        assertNull("a blank command is no command", callRow(ServerCall(cmdMasked = " ")).cmd)
        assertEquals("Claude Code", callRow(ServerCall(tool = "server.claude")).toolFa)
        assertEquals("server.future", callRow(ServerCall(tool = "server.future")).toolFa)
    }

    @Test
    fun theStreamsCallIsARowAndNothingElseIs() {
        fun e(type: String, data: String) = StreamEvent("1", type, "2026-10-17T08:30:00Z", "FX", "srv-fx-1", obj(data).jsonObject)
        val a = callRow(e("server.call", """{"server":"srv-fx-1","actor":"owner","tool":"server.exec","summary_fa":"ok","exit_code":0,"duration_ms":120}"""))!!
        assertTrue(a.byOwner)
        assertEquals(CallOutcome.OK, a.outcome)
        assertEquals("120ms", a.duration)
        assertEquals("srv-fx-1", a.server)
        val b = callRow(e("server.call", """{"actor":{"kind":"agent","code":"TY-GROWTH-01","display_fa":"تحلیلگر"},"tool":"server.read","code":"company_locked"}"""))!!
        assertEquals("TY-GROWTH-01", b.actor.code)
        assertEquals(CallOutcome.REFUSED, b.outcome)
        assertEquals("srv-fx-1", b.server)
        assertNull(callRow(e("server.state", """{"state":"reachable"}""")))
        assertNull(callRow(e("run.started", "{}")))
    }

    @Test
    fun durationsAreFigures() {
        assertEquals("380ms", duration(380))
        assertEquals("2.4s", duration(2_400))
        assertEquals("41s", duration(41_000))
        assertEquals("3m 12s", duration(192_000))
        assertEquals("1h 05m", duration(3_900_000))
        assertNull(duration(null))
    }

    // ------------------------------------------------------------------ the seal card --
    private fun card(payload: String, kind: String = "server_destructive") = Decision(
        "d1", "D-000201", "FX", kind, "x", status = "pending", proposer = Actor("FX-TECH-MGR", "manager", "مدیر فنی FX"), createdAt = "2026-10-17T08:26:00Z",
        payload = obj(payload).jsonObject, actionClass = "A3",
    )

    @Test
    fun theSealCardShowsTheExactCommandAndIsSealedOnCompanyAndServer() {
        val d = card("""{"server":{"id":"srv-fx-1","name":"fx-main"},"company":"FX","category":"db_drop","tool":"server.exec",
            "cmd":"psql -c \"DROP TABLE signals_backtest_2025;\"","cwd":"/home/forex/CoinePro-FX","detected_by":"pattern","pattern":"DROP TABLE","session_ref":null}""")
        val c = sealCardOf(d)!!
        assertEquals("psql -c \"DROP TABLE signals_backtest_2025;\"", c.cmd)
        assertEquals("srv-fx-1", c.serverId)
        assertEquals("fx-main", c.serverName)
        assertEquals("db_drop", c.category!!.key)
        assertEquals("/home/forex/CoinePro-FX", c.cwd)
        assertNull(c.sessionRef)
        assertEquals("FX-TECH-MGR", c.actor.code)
        assertTrue(c.pending)
        assertEquals("FX:fx-main", c.target)
        assertEquals("FX:fx-main", sealTarget(d))
        assertEquals("server.destructive", sealAction(d))
        assertTrue(com.coinepro.hq.ui.cartable.needsStepUp(d))
    }

    @Test
    fun aSparseSealCardStillNamesItsServerAndOtherCardsAreNot() {
        val c = sealCardOf(card("""{"server":"srv-ty-1","server_name":"ty-web","cmd_masked":"docker volume rm ty_pg","category":"something_new","actor":{"kind":"owner","code":"owner"}}"""))!!
        assertEquals("srv-ty-1", c.serverId)
        assertEquals("ty-web", c.serverName)
        assertEquals("docker volume rm ty_pg", c.cmd)
        assertNull("an unknown category has no words, the key stays", c.category)
        assertEquals("something_new", c.categoryKey)
        assertEquals("owner", c.actor.kind)
        val other = card("{}", kind = "deploy")
        assertNull(sealCardOf(other))
        assertEquals("decision.approve", sealAction(other))
        assertEquals("D-000201", sealTarget(other))
    }

    // ------------------------------------------------------------------ the server rules --
    @Test
    fun policyTogglesKeepTheCanonicalOrderAndWhatANewerHubAdds() {
        val all = ServerPolicy()
        assertEquals(SEAL_CATEGORIES.map { it.key }, all.sealRequired)
        val off = all.with("db_drop", false)
        assertFalse(off.requires("db_drop"))
        assertEquals(5, off.sealRequired.size)
        assertEquals(all, off.with("db_drop", true))
        assertEquals(off, off.with("db_drop", false))
        val newer = ServerPolicy(listOf("server_delete", "kernel_upgrade", "db_drop"))
        assertEquals(listOf("db_drop", "server_delete", "kernel_upgrade"), newer.with("disk_wipe", false).sealRequired)
        assertEquals(listOf("db_drop", "disk_wipe", "server_delete", "kernel_upgrade"), newer.with("disk_wipe", true).sealRequired)
        assertEquals(listOf("db_drop", "server_delete"), newer.with("kernel_upgrade", false).sealRequired)
        assertEquals(listOf("db_drop" to false, "access_change" to false), all.changes(all.with("db_drop", false).with("access_change", false)))
        assertTrue(all.changes(all).isEmpty())
    }

    @Test
    fun policyIsSavedWholeWithItsSealOnTheExactBody() = runTest {
        server.enqueue(json(200, """{"seal_required":["volume_delete"]}"""))
        var signed: Pair<String, String>? = null
        val out = api.putServerPolicy(ServerPolicy()) { a, t -> signed = a to t; "step" }
        assertEquals(listOf("volume_delete"), out.sealRequired)
        val r = server.takeRequest()
        assertEquals("PUT", r.method)
        assertEquals("/api/v1/control/server-policy", r.url.encodedPath)
        val body = r.body!!.utf8()
        // A default list is still written: an omitted field would read as "no change" on the hub.
        assertEquals(SEAL_CATEGORIES.map { it.key }, obj(body).jsonObject["seal_required"]!!.jsonArray.map { it.jsonPrimitive.content })
        assertEquals("server.policy" to Api.sha256(body), signed)
        assertEquals("step", r.headers["X-Step-Up"])
    }

    // ------------------------------------------------------------------ attaching --
    private val key = "SHA256:q3XmF0b8Zk1v7R2pTnYw4cJdL6eUa9sHgVxQ5oNiB0M"
    private fun form(ip: String = "10.10.1.2", name: String = "fx-main", user: String = "forex", host: String = key, co: String = "FX") = AttachIn(co, name, ip, user, host)

    @Test
    fun onlyAPrivateIpv4OfAnotherServerIsAttached() {
        for (ip in listOf("10.10.1.2", "10.0.0.1", "172.16.0.5", "172.31.255.254", "192.168.1.20")) assertTrue(ip, AttachRules.isPrivate(ip))
        for (ip in listOf("8.8.8.8", "172.15.0.1", "172.32.0.1", "192.169.0.1", "11.0.0.1", "100.64.0.1")) assertFalse(ip, AttachRules.isPrivate(ip))
        for (ip in listOf("10.10.1", "10.10.1.256", "10.010.1.2", "10.10.1.2.3", "a.b.c.d", "", " 10.1.1.1x")) assertNull(ip, AttachRules.ipv4(ip))
        assertTrue(AttachRules.validate(form()).isEmpty())
        assertTrue(AttachRules.validate(form(ip = "8.8.8.8")).containsKey("private_ip"))
        assertTrue(AttachRules.validate(form(ip = "10.10.1.300")).containsKey("private_ip"))
        assertTrue("the hub itself", AttachRules.validate(form(ip = AttachRules.HUB_IP)).containsKey("private_ip"))
        val existing = listOf(HubServer("s1", "FX", "fx-main", privateIp = "10.10.1.2"))
        val dup = AttachRules.validate(form(), existing)
        assertEquals(setOf("name", "private_ip"), dup.keys)
        assertTrue(AttachRules.validate(form(name = "fx-main", ip = "10.10.1.9", co = "TY"), existing).isEmpty())
    }

    @Test
    fun nameUserAndHostKeyAreChecked() {
        assertTrue(AttachRules.validate(form(name = "FX Main")).containsKey("name"))
        assertTrue(AttachRules.validate(form(name = "f")).containsKey("name"))
        assertTrue(AttachRules.validate(form(name = "fx-")).containsKey("name"))
        assertTrue("never root", AttachRules.validate(form(user = "root")).containsKey("user"))
        assertTrue(AttachRules.validate(form(user = "Forex!")).containsKey("user"))
        assertTrue(AttachRules.validate(form(co = "")).containsKey("company"))
        assertTrue(AttachRules.validate(form(host = "")).containsKey("host_key_sha256"))
        assertTrue(AttachRules.validate(form(host = "SHA256:tooShort")).containsKey("host_key_sha256"))
        assertTrue(AttachRules.validate(form(host = "MD5:aa:bb:cc")).containsKey("host_key_sha256"))
        // What `ssh-keygen -lf` prints is accepted whole, padding or not; the body carries the fingerprint alone.
        val line = "256 $key= root@coinepro-fx (ED25519)"
        assertEquals(key, AttachRules.hostKey(line))
        assertTrue(AttachRules.validate(form(host = line)).isEmpty())
        assertEquals(form(), AttachRules.body(AttachIn(" FX ", " fx-main", "10.10.1.2 ", "forex", line)))
    }

    @Test
    fun theKeyLineCarriesTheSetupSheetsRestrictions() {
        val k = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHq9 hq-company-ops@FX:fx-main"
        assertEquals("from=\"10.10.1.4\",no-agent-forwarding,no-X11-forwarding,no-port-forwarding $k", AttachRules.authorizedLine(k))
        val already = "from=\"10.10.1.4\",no-pty $k"
        assertEquals(already, AttachRules.authorizedLine(already))
    }

    @Test
    fun attachIsSealedOnTheCompanyAndReadsEitherAnswer() = runTest {
        server.enqueue(json(201, """{"id":"srv-1","company":"FX","name":"fx-main","origin":"attached","private_ip":"10.10.1.2","user":"forex","host_key_sha256":"$key","state":"pending","last_seen_at":null,"map_at":null,"public_key":"ssh-ed25519 AAAA hq"}"""))
        server.enqueue(json(201, """{"server":{"id":"srv-2","company":"TY","name":"ty-web","state":"pending"},"public_key":"ssh-ed25519 BBBB hq"}"""))
        var signed: Pair<String, String>? = null
        val a = api.attachServer(form()) { x, t -> signed = x to t; "s" }
        assertEquals("server.attach" to "company:FX", signed)
        assertEquals("srv-1", a.server!!.id)
        assertEquals("pending", a.server!!.state)
        assertEquals("ssh-ed25519 AAAA hq", a.publicKey)
        val sent = obj(server.takeRequest().body!!.utf8()).jsonObject
        assertEquals("10.10.1.2", sent["private_ip"]!!.jsonPrimitive.content)
        assertEquals(key, sent["host_key_sha256"]!!.jsonPrimitive.content)
        val b = api.attachServer(form(co = "TY", name = "ty-web", ip = "10.10.1.3", user = "tradeyar")) { _, _ -> "s" }
        assertEquals("srv-2", b.server!!.id)
        assertEquals("ssh-ed25519 BBBB hq", b.publicKey)
    }

    @Test
    fun serversAreReadBareOrPagedAndRepinAndDetachAreSealedOnTheServer() = runTest {
        server.enqueue(json(200, """[{"id":"a","company":"FX","name":"fx-main","state":"reachable"},{"id":"b","company":"TY","name":"ty-web"}]"""))
        server.enqueue(json(200, """{"items":[{"id":"a","company":"FX","name":"fx-main","origin":"provisioned","private_ip":"10.10.1.2"}],"next_cursor":null}"""))
        assertEquals(listOf("a", "b"), api.servers().map { it.id })
        val fx = api.servers("FX").single()
        assertEquals("provisioned", fx.origin)
        server.takeRequest(); server.takeRequest()
        server.enqueue(json(200, """{"id":"a","company":"FX","name":"fx-main","state":"reachable","host_key_sha256":"$key"}"""))
        server.enqueue(MockResponse.Builder().code(204).build())
        val seen = mutableListOf<Pair<String, String>>()
        api.repinServer(fx, key) { a, t -> seen += a to t; "s" }
        api.detachServer(fx) { a, t -> seen += a to t; "s" }
        assertEquals(listOf("server.repin" to "FX:fx-main", "server.detach" to "FX:fx-main"), seen)
        assertEquals("/api/v1/infra/servers/a/repin", server.takeRequest().url.encodedPath)
        assertEquals("DELETE", server.takeRequest().method)
    }

    // ------------------------------------------------------------------ the owner's terminal --
    @Test
    fun sseLinesBecomeEvents() {
        val p = SseParser()
        val got = mutableListOf<com.coinepro.hq.core.net.SseMessage>()
        for (l in listOf(": heartbeat", "event: stdout", "id: 1", "data: {\"text\":\"a\"}", "", "data: one", "data: two\r", "", "event: exit", "data: {\"exit_code\":3}")) p.line(l)?.let { got += it }
        p.end()?.let { got += it }
        assertEquals(3, got.size)
        assertEquals("stdout", got[0].event)
        assertEquals("1", got[0].id)
        assertEquals("one\ntwo", got[1].data)
        assertNull(got[1].event)
        assertEquals(TermEvent.Exit(3, null), termEventOf(got[2]))
    }

    @Test
    fun everyKindOfExecEventIsRead() {
        fun m(e: String?, d: String) = com.coinepro.hq.core.net.SseMessage(e, d, null)
        assertEquals(TermEvent.Out("hi\n"), termEventOf(m("stdout", "{\"text\":\"hi\\n\"}")))
        assertEquals(TermEvent.Out("raw"), termEventOf(m("stdout", "raw")))
        assertEquals(TermEvent.Out("bad\n", err = true), termEventOf(m("stderr", "{\"text\":\"bad\\n\"}")))
        assertEquals(TermEvent.Exit(0, 1200), termEventOf(m("exit", "{\"exit_code\":0,\"duration_ms\":1200}")))
        assertEquals(TermEvent.Failed("company_locked", "قفل"), termEventOf(m("error", "{\"code\":\"company_locked\",\"message_fa\":\"قفل\"}")))
        assertEquals("D-000210", (termEventOf(m("awaiting_seal", "{\"decision_ref\":\"D-000210\"}")) as TermEvent.AwaitingSeal).decisionRef)
        assertEquals(TermEvent.Exit(1, null), termEventOf(m(null, "{\"exit_code\":1}")))
        assertEquals(TermEvent.Out("x", err = true), termEventOf(m(null, "{\"stderr\":\"x\"}")))
        assertNull(termEventOf(m("ping", "{}")))
    }

    @Test
    fun theBufferJoinsChunksIntoLinesAndEndsWithTheExit() {
        val b = TerminalBuffer()
        b.command("docker ps", "forex@10.10.1.2")
        assertTrue(b.running)
        b.apply(TermEvent.Out("CONTAINER ID   IMA"))
        assertEquals(listOf(TermKind.CMD, TermKind.OUT), b.lines.map { it.kind })
        assertEquals("CONTAINER ID   IMA", b.lines.last().text)
        b.apply(TermEvent.Out("GE\n3fa91c2b7d00   api\n"))
        assertEquals(listOf("forex@10.10.1.2\$ docker ps", "CONTAINER ID   IMAGE", "3fa91c2b7d00   api"), b.lines.map { it.text })
        // A progress bar rewrites its line; colours are dropped; Windows line ends are one.
        b.apply(TermEvent.Out("pull  10%\rpull  55%\rpull 100%\r\n\u001B[32mdone\u001B[0m\n"))
        assertEquals(listOf("pull 100%", "done"), b.lines.takeLast(2).map { it.text })
        b.apply(TermEvent.Out("warning: no tty", err = true))
        b.apply(TermEvent.Exit(0, 2_400))
        assertFalse(b.running)
        assertEquals(0, b.lastExit)
        assertEquals(TermKind.ERR to "warning: no tty", b.lines[b.lines.size - 2].let { it.kind to it.text })
        assertEquals(TermKind.OK to "exit 0 · 2.4s", b.lines.last().let { it.kind to it.text })
        b.command("false", "forex@10.10.1.2")
        b.apply(TermEvent.Exit(1, null))
        assertEquals(TermKind.FAIL to "exit 1", b.lines.last().let { it.kind to it.text })
    }

    @Test
    fun aStoppedOrRefusedCommandSaysSoAndOldLinesGo() {
        val b = TerminalBuffer(max = 4)
        b.command("sleep 100", "u@h")
        b.apply(TermEvent.Out("partial"))
        b.ended("stopped")
        assertEquals(listOf("u@h\$ sleep 100", "partial", "stopped"), b.lines.map { it.text })
        assertFalse(b.running)
        b.command("rm -rf /backups/old", "u@h")
        b.apply(TermEvent.AwaitingSeal("D-000210", "منتظر مُهر"))
        assertEquals(TermKind.INFO, b.lines.last().kind)
        assertEquals(4, b.lines.size)
        assertEquals("partial", b.lines.first().text)
        b.clear()
        assertTrue(b.lines.isEmpty())
    }

    @Test
    fun historyKeepsTheLastCommandsOnceNewestFirst() {
        val h = TermHistory(max = 3)
        listOf("df -h", "docker ps", "df -h", "  ", "free -h", "uptime").forEach(h::add)
        assertEquals(listOf("uptime", "free -h", "df -h"), h.items)
        assertEquals(listOf("uptime", "free -h", "df -h"), h.with(listOf("df -h", "git status")))
        assertEquals(listOf("a", "b"), TermHistory().apply { add("a") }.with(listOf("a", "b", "")))
    }

    @Test
    fun theOwnersCommandStreamsAndIsSealedOnItsExactBody() = runTest {
        val sse = "event: stdout\ndata: {\"text\":\"Filesystem Size\\n\"}\n\n: beat\n\nevent: stdout\ndata: {\"text\":\"/dev/sda1 150G\\n\"}\n\nevent: exit\ndata: {\"exit_code\":0,\"duration_ms\":90}\n\n"
        server.enqueue(MockResponse.Builder().code(200).addHeader("Content-Type", "text/event-stream").body(sse).build())
        val s = HubServer("srv-fx-1", "FX", "fx-main")
        var signed: Pair<String, String>? = null
        val events = api.exec(s, ExecIn("df -h")) { a, t -> signed = a to t; "tok" }.toList()
        assertEquals(listOf(TermEvent.Out("Filesystem Size\n"), TermEvent.Out("/dev/sda1 150G\n"), TermEvent.Exit(0, 90)), events)
        val r = server.takeRequest()
        assertEquals("/api/v1/infra/servers/srv-fx-1/exec", r.url.encodedPath)
        val body = r.body!!.utf8()
        assertEquals("df -h", obj(body).jsonObject["cmd"]!!.jsonPrimitive.content)
        assertEquals("server.exec" to Api.sha256(body), signed)
        assertEquals("tok", r.headers["X-Step-Up"])
        assertEquals("text/event-stream", r.headers["Accept"])
    }

    @Test
    fun aHeldOrRefusedCommandIsSaid() = runTest {
        server.enqueue(json(202, """{"status":"awaiting_seal","decision_ref":"D-000210","message_fa":"منتظر مُهر"}"""))
        server.enqueue(json(423, """{"type":"about:blank","title":"Locked","status":423,"code":"company_locked","message_fa":"قفل است."}"""))
        server.enqueue(json(200, """{"stdout":"ok","exit_code":0}"""))
        val s = HubServer("x", "FX", "fx-main")
        assertEquals(listOf(TermEvent.AwaitingSeal("D-000210", "منتظر مُهر")), api.exec(s, ExecIn("mkfs.ext4 /dev/sdb")) { _, _ -> "t" }.toList())
        try {
            api.exec(s, ExecIn("ls")) { _, _ -> "t" }.toList()
            fail("423 must throw")
        } catch (e: ApiException) {
            assertEquals("company_locked", e.code)
            assertEquals(423, e.status)
            assertTrue(com.coinepro.hq.core.net.serverError(e).contains("کلید توقف"))
        }
        assertEquals(listOf(TermEvent.Out("ok\n"), TermEvent.Exit(0, null)), api.exec(s, ExecIn("ls")) { _, _ -> "t" }.toList())
    }

    @Test
    fun aTaskOnTheServerIsAWorkshopSessionOnItsRuntime() = runTest {
        server.enqueue(json(201, """{"id":"s","ref":"S-0020","runtime":"company_server","server":"srv-ty-1","company":"TY","title":"cache","driver":{"kind":"manager","code":"TY-TECH-MGR"},"state":"starting","created_at":"t","updated_at":"t"}"""))
        val out = api.startServerSession(HubServer("srv-ty-1", "TY", "ty-web"), null, "cache", "brief", listOf("f1"))
        assertTrue(out.onServer)
        assertEquals("", out.workspace)
        assertEquals("srv-ty-1", out.server)
        val sent = obj(server.takeRequest().body!!.utf8()).jsonObject
        assertEquals("company_server", sent["runtime"]!!.jsonPrimitive.content)
        assertEquals("srv-ty-1", sent["server"]!!.jsonPrimitive.content)
        assertTrue("the owner drives: an explicit null", sent.containsKey("driver") && sent["driver"] is kotlinx.serialization.json.JsonNull)
        assertEquals(listOf("f1"), sent["attachments"]!!.jsonArray.map { it.jsonPrimitive.content })
    }

    @Test
    fun aMapNotTakenYetIsNoneAndActivityIsAPage() = runTest {
        server.enqueue(json(404, """{"type":"about:blank","title":"Not Found","status":404,"code":"not_found","message_fa":"پیدا نشد."}"""))
        server.enqueue(json(200, """{"items":[{"at":"2026-10-17T08:29:00Z","actor":{"kind":"agent","code":"FX-TECH-MGR"},"tool":"server.exec","summary_fa":"x","cmd_masked":"export TOKEN=***","exit_code":0,"duration_ms":5,"session_ref":null,"transcript_url":"/api/v1/t/1"}],"next_cursor":null}"""))
        assertNull(api.serverMap("x"))
        val p = api.serverActivity("x", actor = "owner")
        assertEquals("export TOKEN=***", p.items.single().cmdMasked)
        server.takeRequest()
        assertEquals("owner", server.takeRequest().url.queryParameter("actor"))
        assertNotNull(p.items.single().transcriptUrl)
    }

    @Test
    fun aStreamEventOnServersRefreshesTheRightScreens() {
        // The `servers` topic is asked for (§26.4) and a held seal refreshes the cartable too.
        assertTrue("servers" in com.coinepro.hq.core.data.StreamTopics.ALL)
        assertEquals("servers/srv-fx-1", com.coinepro.hq.core.data.Refs.forLink("server", "srv-fx-1"))
    }
}
