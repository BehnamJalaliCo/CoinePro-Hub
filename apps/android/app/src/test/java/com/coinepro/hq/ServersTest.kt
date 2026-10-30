package com.coinepro.hq

import com.coinepro.hq.core.net.Actor
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.CallOutcome
import com.coinepro.hq.core.net.Decision
import com.coinepro.hq.core.net.ExecIn
import com.coinepro.hq.core.net.HubServer
import com.coinepro.hq.core.net.PairCode
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

/** ⟨1.8⟩ Contract §26: the companies' servers through their runners — the map read in §26.5's shape and whatever else it comes in, the
 *  jobs on the activity page, the seal card, the server rules, pairing a runner and detaching it, a task in a repository, and the owner's
 *  terminal from the SSE bytes to the lines on screen. */
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
    fun aMapInTheContractsBindingShapeIsReadWhole() {
        // §26.5 exactly: `{at, map}`, sizes in MB and GB, one systemd list with timers flagged, cron's masked command, ports' `public`.
        val m = ServerMaps.parse(obj("""{"at":"2026-10-30T08:18:00Z","map":{"os":"Ubuntu 24.04.1 LTS","kernel":"6.8.0-47-generic","uptime_s":1900800,
            "cpu":{"cores":8,"load1":0.84},"memory":{"total_mb":16384,"used_mb":12288,"swap_total_mb":8192,"swap_used_mb":1024},
            "disks":[{"mount":"/","total_gb":150,"used_gb":62}],
            "containers":[{"name":"api-1","image":"fx-api:a41","state":"running","health":"healthy","project":"coinepro-fx"},{"name":"bt-1","image":"x","state":"exited","health":null,"project":null}],
            "compose":[{"project":"coinepro-fx","path":"/home/forex/CoinePro-FX","services":["api","bt"]}],
            "systemd":[{"unit":"docker.service","state":"active","timer":false,"next_at":null},{"unit":"fx-backup.timer","state":"active","timer":true,"next_at":"2026-10-30T10:05:00Z"}],
            "cron":[{"user":"forex","schedule":"*/5 * * * *","cmd_masked":"TOKEN=*** scripts/healthcheck.sh"}],
            "ports":[{"port":443,"proto":"tcp","bind":"0.0.0.0","process":"caddy","public":true},{"port":5432,"proto":"tcp","bind":"127.0.0.1","process":"docker-proxy","public":false}],
            "repos":[{"path":"/home/forex/CoinePro-FX","remote":"git@github.com:o/CoineProFx.git","branch":"main","dirty":false,"last_commit_at":"2026-10-30T08:00:00Z"}],
            "automations":[{"kind":"n8n","name":"daily","active":true,"detail":"cron 08:00"}],"sites":[{"host":"coineprofx.com","upstream":"website:80"}]}}"""))!!
        assertEquals("2026-10-30T08:18:00Z", m.at)
        assertEquals("Ubuntu 24.04.1 LTS", m.os)
        assertEquals("6.8.0-47-generic", m.kernel)
        assertEquals(8, m.cpus)
        assertEquals(0.84, m.load!!, 0.001)
        assertEquals(75.0, m.memory!!.pct, 0.01)
        assertEquals(1024L * 1024 * 1024, m.swap!!.usedBytes)
        assertEquals(62 * GIB, m.disks.single().usedBytes)
        assertEquals("healthy", m.containers.first().health)
        assertEquals(1, m.runningContainers)
        assertEquals(2, m.compose.single().services)
        assertEquals("/home/forex/CoinePro-FX", m.compose.single().dir)
        assertEquals(listOf("docker.service"), m.units.map { it.name })
        assertEquals(listOf("fx-backup.timer" to "2026-10-30T10:05:00Z"), m.timers.map { it.unit to it.next })
        assertEquals("TOKEN=*** scripts/healthcheck.sh", m.cron.single().command)
        assertEquals(listOf(true, false), m.ports.map { it.public })
        assertEquals("2026-10-30T08:00:00Z", m.repos.single().lastCommitAt)
        assertEquals("n8n", m.automations.single().kind)
        assertEquals("coineprofx.com", m.sites.single().domain)
    }

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
    fun aJobsStateIsItsRowsState() {
        // §26.2: queued · running · awaiting_seal · done · failed · cancelled.
        fun st(state: String, exit: Int? = null) = callRow(ServerCall(kind = "exec", state = state, exitCode = exit)).outcome
        assertEquals(CallOutcome.QUEUED, st("queued"))
        assertEquals(CallOutcome.RUNNING, st("running"))
        assertEquals(CallOutcome.AWAITING_SEAL, st("awaiting_seal"))
        assertEquals(CallOutcome.OK, st("done", 0))
        assertEquals(CallOutcome.OK, st("done"))
        assertEquals("a done job that exited non-zero failed", CallOutcome.FAILED, st("done", 2))
        assertEquals(CallOutcome.FAILED, st("failed"))
        assertEquals(CallOutcome.CANCELLED, st("cancelled"))
        assertTrue(callRow(ServerCall(state = "queued")).open)
        assertFalse(callRow(ServerCall(state = "cancelled")).open)
    }

    @Test
    fun aJobReadsItsKindArgsAndTimes() {
        val job = Api.json.decodeFromString(ServerCall.serializer(), """{"id":"j1","server":"srv-ty-1","kind":"claude","actor":{"kind":"manager","code":"TY-TECH-MGR"},
            "args":{"cwd":"/home/tradeyar/TradeYar","brief":"cache /market"},"state":"done","created_at":"2026-10-30T08:00:00Z","started_at":"2026-10-30T08:00:05Z",
            "finished_at":"2026-10-30T08:03:17Z","exit_code":0,"summary_fa":"کش فعال شد","transcript_url":"/api/v1/t/j1"}""")
        val r = callRow(job)
        assertEquals("server.claude", r.tool)
        assertEquals("Claude Code", r.toolFa)
        assertEquals("2026-10-30T08:00:05Z", r.at)
        assertEquals("/home/tradeyar/TradeYar", r.cwd)
        assertNull("a claude job has no command of its own", r.cmd)
        assertEquals("3m 12s", r.duration)
        assertEquals(CallOutcome.OK, r.outcome)
        val exec = callRow(Api.json.decodeFromString(ServerCall.serializer(), """{"kind":"exec","args":{"cmd":"df -h","cwd":"/srv"},"state":"queued","created_at":"2026-10-30T08:00:00Z"}"""))
        assertEquals("df -h", exec.cmd)
        assertEquals("/srv", exec.cwd)
        assertEquals("2026-10-30T08:00:00Z", exec.at)
        assertNull(exec.duration)
        assertEquals(CallOutcome.QUEUED, exec.outcome)
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
        assertNull(callRow(e("server.state", """{"state":"online"}""")))
        assertNull(callRow(e("run.started", "{}")))
        // §26.5: `state` arrives once at the start and once at the end; a failure may come without an exit code.
        assertEquals(CallOutcome.RUNNING, callRow(e("server.call", """{"tool":"server.exec","state":"running","exit_code":null}"""))!!.outcome)
        assertEquals(CallOutcome.FAILED, callRow(e("server.call", """{"tool":"server.exec","state":"failed","exit_code":null,"duration_ms":40}"""))!!.outcome)
        assertEquals(CallOutcome.OK, callRow(e("server.call", """{"tool":"server.map","state":"done","exit_code":0,"duration_ms":40}"""))!!.outcome)
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

    // ------------------------------------------------------------------ pairing a runner --
    @Test
    fun theCodeIsFormattedAsTyped() {
        assertEquals("ABCD-1234", PairCode.format("abcd1234"))
        assertEquals("ABCD-12", PairCode.format("ab cd-12"))
        assertEquals("ABCD", PairCode.format("abcd"))
        assertEquals("ABCD-1234", PairCode.format("ABCD-1234-XYZ"))
        assertEquals("Persian and Arabic digits are Latin", "K7QD-2490", PairCode.format("k7qd-۲۴٩٠"))
        assertEquals("letters outside Latin are dropped", "AB", PairCode.format("aبb"))
        assertEquals("", PairCode.format("— "))
        assertTrue(PairCode.valid("ABCD-1234"))
        assertFalse(PairCode.valid("ABCD-123"))
        assertFalse(PairCode.valid("abcd-1234"))
        assertFalse(PairCode.valid("ABCD1234"))
        assertEquals("hq-runner pair --company TY --name <name>", PairCode.pairCommand("TY"))
        assertEquals("hq-runner pair --company <CODE> --name <name>", PairCode.pairCommand(null))
    }

    @Test
    fun anExpiredOrUnknownCodeIsSaidAsSuch() {
        assertTrue(PairCode.refusal(ApiException(410, "expired_token", "x"))!!.contains("منقضی"))
        assertTrue(PairCode.refusal(ApiException(400, "code_expired", "x"))!!.contains("منقضی"))
        assertTrue(PairCode.refusal(ApiException(404, "invalid_user_code", "x"))!!.contains("پیدا نشد"))
        assertTrue(PairCode.refusal(ApiException(404, "not_found", "x"))!!.contains("پیدا نشد"))
        assertTrue(PairCode.refusal(ApiException(409, "company_mismatch", "x"))!!.contains("شرکت"))
        assertNull(PairCode.refusal(ApiException(423, "company_locked", "x")))
    }

    @Test
    fun approvingACodeIsSealedOnTheCompanyAndSendsTheCodeAlone() = runTest {
        server.enqueue(json(200, """{"server":{"id":"srv-9","company":"TY","name":"ty-media","origin":"attached","private_ip":"10.10.1.9","user":"tradeyar","hostname":"ty-media","runner_version":"0.1.0","state":"pending","last_seen_at":null,"map_at":null}}"""))
        server.enqueue(json(200, """{"id":"srv-10","company":"FX","name":"fx-worker","state":"pending"}"""))
        server.enqueue(json(410, """{"type":"about:blank","title":"Gone","status":410,"code":"expired_token","message_fa":"منقضی."}"""))
        var signed: Pair<String, String>? = null
        val s = api.approveRunner("TY", "TY7K-M4QD") { a, t -> signed = a to t; "s" }
        assertEquals("server.attach" to "company:TY", signed)
        assertEquals("srv-9", s.id)
        assertEquals("pending", s.state)
        assertEquals("0.1.0", s.runnerVersion)
        assertEquals("tradeyar@ty-media", s.login)
        val r = server.takeRequest()
        assertEquals("/api/v1/runners/approve", r.url.encodedPath)
        assertEquals("s", r.headers["X-Step-Up"])
        val sent = obj(r.body!!.utf8()).jsonObject
        assertEquals(setOf("user_code"), sent.keys)
        assertEquals("TY7K-M4QD", sent["user_code"]!!.jsonPrimitive.content)
        assertEquals("srv-10", api.approveRunner("FX", "FX3R-82NB") { _, _ -> "s" }.id)
        try {
            api.approveRunner("FX", "Q2WX-0000") { _, _ -> "s" }
            fail("410 must throw")
        } catch (e: ApiException) {
            assertTrue(PairCode.refusal(e)!!.contains("منقضی"))
        }
    }

    @Test
    fun serversAreReadBareOrPagedWithTheirRunnersAndDetachRevokesIt() = runTest {
        server.enqueue(json(200, """[{"id":"a","company":"FX","name":"fx-main","state":"online","user":"forex","hostname":"coinepro-fx","runner_version":"0.1.0","last_seen_at":"2026-10-30T08:29:55Z"},{"id":"b","company":"TY","name":"ty-web"}]"""))
        server.enqueue(json(200, """{"items":[{"id":"a","company":"FX","name":"fx-main","origin":"provisioned","private_ip":"10.10.1.2","user":"forex","state":"offline"}],"next_cursor":null}"""))
        val all = api.servers()
        assertEquals(listOf("a", "b"), all.map { it.id })
        assertTrue(all[0].online)
        assertEquals("forex@coinepro-fx", all[0].login)
        assertEquals("pending", all[1].state)
        val fx = api.servers("FX").single()
        assertEquals("provisioned", fx.origin)
        assertFalse(fx.online)
        assertEquals("without a hostname, the private address", "forex@10.10.1.2", fx.login)
        assertTrue(HubServer("r", state = "revoked").revoked)
        server.takeRequest(); server.takeRequest()
        server.enqueue(MockResponse.Builder().code(204).build())
        val seen = mutableListOf<Pair<String, String>>()
        api.detachServer(fx) { a, t -> seen += a to t; "s" }
        assertEquals(listOf("server.detach" to "FX:fx-main"), seen)
        val r = server.takeRequest()
        assertEquals("DELETE", r.method)
        assertEquals("/api/v1/infra/servers/a", r.url.encodedPath)
    }

    @Test
    fun serverListsPutOnlineFirstAndRevokedLast() {
        val list = listOf(HubServer("1", state = "revoked"), HubServer("2", state = "offline"), HubServer("3", state = "online"), HubServer("4", state = "pending"), HubServer("5", state = "online"))
        assertEquals(listOf("3", "5", "4", "2", "1"), com.coinepro.hq.ui.servers.byState(list).map { it.id })
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
    fun aTaskOnTheServerIsAWorkshopSessionOnItsRuntimeInTheChosenRepository() = runTest {
        server.enqueue(json(201, """{"id":"s","ref":"S-0020","runtime":"company_server","server":"srv-ty-1","company":"TY","title":"cache","driver":{"kind":"manager","code":"TY-TECH-MGR"},"state":"starting","created_at":"t","updated_at":"t"}"""))
        server.enqueue(json(201, """{"id":"s2","ref":"S-0021","runtime":"company_server","server":"srv-ty-1","company":"TY","title":"x","driver":{"kind":"manager","code":"TY-TECH-MGR"},"state":"starting","created_at":"t","updated_at":"t"}"""))
        val out = api.startServerSession(HubServer("srv-ty-1", "TY", "ty-web"), null, "cache", "brief", listOf("f1"), cwd = "/home/tradeyar/TradeYar")
        assertTrue(out.onServer)
        assertEquals("", out.workspace)
        assertEquals("srv-ty-1", out.server)
        val sent = obj(server.takeRequest().body!!.utf8()).jsonObject
        assertEquals("company_server", sent["runtime"]!!.jsonPrimitive.content)
        assertEquals("srv-ty-1", sent["server"]!!.jsonPrimitive.content)
        assertTrue("the owner drives: an explicit null", sent.containsKey("driver") && sent["driver"] is kotlinx.serialization.json.JsonNull)
        assertEquals(listOf("f1"), sent["attachments"]!!.jsonArray.map { it.jsonPrimitive.content })
        assertEquals("/home/tradeyar/TradeYar", sent["cwd"]!!.jsonPrimitive.content)
        api.startServerSession(HubServer("srv-ty-1", "TY", "ty-web"), "TY-TECH-MGR", "x", "y", emptyList())
        assertFalse("no repository chosen: `cwd` is left out", obj(server.takeRequest().body!!.utf8()).jsonObject.containsKey("cwd"))
    }

    @Test
    fun theRepositoryIsThePickedOneOrTheOnlyOne() {
        val two = listOf("/home/ty/TradeYar", "/home/ty/blog")
        assertEquals("/home/ty/blog", com.coinepro.hq.ui.servers.defaultRepo(two, "/home/ty/blog"))
        assertNull("two and none picked: the hub picks", com.coinepro.hq.ui.servers.defaultRepo(two, null))
        assertNull("a pick the map no longer has", com.coinepro.hq.ui.servers.defaultRepo(two, "/gone"))
        assertEquals("/home/ty/TradeYar", com.coinepro.hq.ui.servers.defaultRepo(listOf("/home/ty/TradeYar"), null))
        assertNull(com.coinepro.hq.ui.servers.defaultRepo(emptyList(), null))
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
