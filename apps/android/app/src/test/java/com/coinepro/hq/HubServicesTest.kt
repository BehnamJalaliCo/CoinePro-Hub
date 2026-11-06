package com.coinepro.hq

import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.HubBlocking
import com.coinepro.hq.core.net.HubJob
import com.coinepro.hq.core.net.HubServices
import com.coinepro.hq.core.net.TokenSource
import com.coinepro.hq.core.net.hubPendingFa
import com.coinepro.hq.core.net.hubStateFa
import com.coinepro.hq.core.net.hubSwapFa
import com.coinepro.hq.core.net.hubToTurnOff
import com.coinepro.hq.core.net.mbFig
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
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

/**
 * ⟨1.20⟩ Contract §38.3, «سرویس‌ها»: the page's shapes (a hub whose dispatcher never reported has no `memory`), a switch as a job with
 * its own UUID key, the job read until it answers, and the refused swap: as few of the largest services as make room, in one sentence.
 */
@RunWith(RobolectricTestRunner::class)
class HubServicesTest {
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

    @Test
    fun thePageReadsWithAndWithoutTheDispatcher() {
        val d = Api.json.decodeFromString(
            HubServices.serializer(),
            """{"memory":{"total_mb":16384,"budget_mb":"12288","caps_mb":9344.0,"free_mb":2944},"services":[
              {"key":"media","title_fa":"ساخت ویدیو و کاور","what_fa":"ریلز","state":"on","optional":true,"mem_cap_mb":3072,"mem_used_mb":1840,"can_toggle":true,"note_fa":null},
              {"key":"api","title_fa":"هسته","state":"on","optional":false,"mem_cap_mb":1024,"can_toggle":false}],"at":"2026-11-06T08:29:20Z"}""",
        )
        assertEquals(2944.0, d.memory!!.freeMb, 0.0)
        assertEquals(12288.0, d.memory!!.budgetMb, 0.0)
        assertEquals(listOf(true, false), d.services.map { it.canToggle })
        assertNull(d.services[1].memUsedMb)
        assertNull(Api.json.decodeFromString(HubServices.serializer(), """{"memory":null,"services":[]}""").memory)
        assertEquals("1,536 MB", mbFig(1536.0))
        assertEquals("روشن", hubStateFa("on"))
        assertEquals("در حال روشن شدن…", hubPendingFa(true))
        assertEquals("در حال خاموش شدن…", hubPendingFa(false))
    }

    @Test
    fun aSwitchIsAJobWithItsOwnKeyFollowedToItsAnswer() = runTest {
        server.enqueue(json(202, """{"ref":"HJ-0001","state":"queued","result_fa":null,"blocking":[]}"""))
        server.enqueue(json(200, """{"ref":"HJ-0001","state":"done","result_fa":"روشن شد","blocking":[]}"""))
        val key = java.util.UUID.randomUUID().toString()
        val job = api.setHubService("stt", true, key, turnOff = listOf("media"))
        assertFalse(job.finished)
        val post = server.takeRequest()
        assertEquals("POST", post.method)
        assertEquals("/api/v1/hub/services/stt", post.url.encodedPath)
        assertEquals(key, post.headers["Idempotency-Key"])
        val body = Api.json.parseToJsonElement(post.body!!.utf8()).jsonObject
        assertTrue(body["on"]!!.jsonPrimitive.boolean)
        assertEquals(listOf("media"), body["turn_off"]!!.jsonArray.map { it.jsonPrimitive.content })
        val done = api.hubJob("HJ-0001")
        assertTrue(done.finished)
        assertEquals("روشن شد", done.resultFa)
        assertEquals("/api/v1/hub/jobs/HJ-0001", server.takeRequest().url.encodedPath)
        // A plain switch sends no `turn_off`.
        server.enqueue(json(202, """{"ref":"HJ-0002","state":"queued"}"""))
        api.setHubService("tts", false, java.util.UUID.randomUUID().toString())
        assertFalse(Api.json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject.containsKey("turn_off"))
    }

    @Test
    fun theRefusedSwapTurnsOffAsFewAsMakeRoom() {
        val blocking = listOf(HubBlocking("tts", "صدای ساده‌ی هاب", 512.0), HubBlocking("media", "ساخت ویدیو و کاور", 3072.0), HubBlocking("automations", "خودکارسازی", 768.0))
        // 3,584 MB needed, 2,944 free: the largest alone is enough.
        val one = hubToTurnOff(blocking, 3584.0, 2944.0)
        assertEquals(listOf("media"), one.map { it.key })
        assertEquals("ساخت ویدیو و کاور را خاموش کن و تبدیل گفتار به متن را روشن کن", hubSwapFa(one, "تبدیل گفتار به متن"))
        // 3,800 needed, nothing free: the largest two (3,840).
        assertEquals(listOf("media", "automations"), hubToTurnOff(blocking, 3800.0, 0.0).map { it.key })
        // Even all are not enough: all of them (the hub says so again).
        assertEquals(3, hubToTurnOff(blocking, 99999.0, 0.0).size)
        assertTrue(HubJob(state = "refused").finished)
        assertFalse(HubJob(state = "running").finished)
    }
}
