package com.coinepro.hq

import com.coinepro.hq.core.data.HoldingStream
import com.coinepro.hq.core.data.QueryCache
import com.coinepro.hq.core.data.StreamTopics
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.HubHealth
import com.coinepro.hq.core.net.TokenSource
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * `GET /api/v1/stream` takes `topics` as one value of at most 200 characters matching `^[a-z]+(,[a-z]+)*$` (apps/api routes/stream.py).
 * 0.4.0 sent all 42 topics in one value of 339 characters: `422` on every start, then only the core topics. The stream now opens one
 * connection per lane, each a value the hub accepts, together every topic.
 */
@RunWith(RobolectricTestRunner::class)
class StreamTopicsTest {
    /** The topics the hub serves (events.py TOPICS), as of contract ⟨1.7.4⟩. */
    private val served = setOf(
        "work", "decisions", "deliverables", "messages", "notifications", "activity", "llm", "control", "runs", "files", "workshop", "orders",
        "backups", "inquiries", "errands", "stars", "stories", "skills", "academy", "oversight", "founding", "revenue", "support", "growth",
        "feedback", "companies", "meetings", "governance", "knowledge", "advisor", "treasury", "creatives", "briefings", "people", "notes",
        "quality", "ask", "reviews", "dceo", "media", "legal", "archive",
    )

    @Test
    fun theOldSingleValueWasTooLongForTheHub() {
        val old = StreamTopics.ALL.joinToString(",")
        assertTrue(old.length > StreamTopics.MAX)
        assertTrue(!StreamTopics.accepted(old))
    }

    @Test
    fun everyLaneIsAcceptedAndTogetherTheyAskForEveryTopic() {
        val lanes = StreamTopics.lanes()
        assertTrue(lanes.size >= 2)
        for (l in lanes) assertTrue(l, StreamTopics.accepted(l))
        val asked = lanes.flatMap { it.split(',') }
        assertEquals(StreamTopics.ALL, asked)
        assertEquals(asked.size, asked.toSet().size)
        // Every topic the app names is one the hub serves, and the app names every one of them.
        assertEquals(served, asked.toSet())
        // The core topics stay together in the first connection.
        assertTrue(lanes.first().split(',').containsAll(StreamTopics.CORE))
    }

    @Test
    fun theAlertLaneComesFirstAndNoTopicIsAskedTwice() {
        val lanes = StreamTopics.split()
        // The lane the background link keeps open with the app closed: the alert topics alone, nothing chatty.
        assertEquals("work,decisions,deliverables,notifications,control", lanes.first())
        for (chatty in listOf("activity", "llm", "runs", "messages")) assertTrue(chatty !in lanes.first().split(','))
        for (l in lanes) assertTrue(l, StreamTopics.accepted(l))
        val asked = lanes.flatMap { it.split(',') }
        assertEquals(asked.size, asked.toSet().size)
        assertEquals(served, asked.toSet())
        // The events those topics carry (events.py TOPICS: control also carries presence and hiring).
        for (t in listOf("notification.created", "decision.decided", "deliverable.created", "work.delegated", "control.changed")) {
            assertTrue(t, StreamTopics.ALERT_PREFIXES.any { t.startsWith(it) })
        }
        assertTrue(StreamTopics.ALERT_PREFIXES.none { "llm.call".startsWith(it) || "run.step".startsWith(it) })
    }

    @Test
    fun lanesPackToTheLimit() {
        assertEquals(listOf("aaaa,bbbb", "cccc"), StreamTopics.lanes(listOf("aaaa", "bbbb", "cccc"), max = 9))
        assertEquals(listOf("a,b,c"), StreamTopics.lanes(listOf("a", "b", "c", "a"), max = 200))
    }

    @Test
    fun theUrlsTheStreamOpensAreWhatTheHubAccepts() {
        val api = Api("https://hq.coinepro.com/", object : TokenSource { override fun token() = "t"; override fun clear() = Unit })
        val scope = CoroutineScope(Dispatchers.Unconfined)
        val stream = HoldingStream(api, QueryCache(scope, HubHealth()), scope, demo = false)
        val urls = stream.urls()
        assertEquals(StreamTopics.split().size, urls.size)
        for (u in urls) {
            assertEquals("/api/v1/stream", u.encodedPath)
            assertEquals(setOf("topics"), u.queryParameterNames)
            val topics = u.queryParameter("topics")!!
            assertTrue("${topics.length} > 200", topics.length <= 200)
            assertTrue(Regex("^[a-z]+(,[a-z]+)*$").matches(topics))
        }
        assertEquals(served, urls.flatMap { it.queryParameter("topics")!!.split(',') }.toSet())
    }
}
