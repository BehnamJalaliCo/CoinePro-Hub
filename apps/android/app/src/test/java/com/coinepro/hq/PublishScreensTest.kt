package com.coinepro.hq

import android.os.Looper
import androidx.activity.ComponentActivity
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.unit.dp
import androidx.test.core.app.ApplicationProvider
import com.coinepro.hq.core.AppGraph
import com.coinepro.hq.core.net.Decision
import com.coinepro.hq.core.net.FileRef
import com.coinepro.hq.core.net.PublishPanel
import com.coinepro.hq.core.net.SessionPublish
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.DivanTheme
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Nav
import com.coinepro.hq.ui.Toasts
import com.coinepro.hq.ui.cartable.needsStepUp
import com.coinepro.hq.ui.outputs.PublishForm
import com.coinepro.hq.ui.outputs.PublishSection
import com.coinepro.hq.ui.outputs.kindsOf
import com.coinepro.hq.ui.outputs.publishOf
import com.coinepro.hq.ui.outputs.publishable
import com.coinepro.hq.ui.rememberQuery
import com.github.takahirom.roborazzi.RoborazziOptions
import com.github.takahirom.roborazzi.captureRoboImage
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.ParameterizedRobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * ⟨0.19.8⟩ §44.5 «تأیید و انتشار» on a session's output, night and day, each on its own as the page shows it (the section sits
 * under the output's files, far down a long page): the reel and its cover each with the one gold action; the sheet's content the tap
 * opens (which account, as what, the caption); and where each publish stands once he tapped (one published with its link, one on
 * its way, one Instagram refused, said plainly, with «دوباره»). Each is checked to show its words before it is drawn.
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h900dp-xxhdpi")
class PublishScreensTest(private val name: String, private val night: Boolean) {
    /** [tap]: a node tapped once the scene has settled (its words), before it is checked and drawn. */
    private class Scene(val ref: String, val sheet: Boolean, val shows: List<String>, val tap: String? = null)

    companion object {
        private val SCREENS: Map<String, Scene> = linkedMapOf(
            "output-publish" to Scene("O-000950", false, listOf("انتشار در اینستاگرام", "تأیید و انتشار", "gold-levels-reel.mp4", "کارت و اثر انگشت ندارد")),
            "output-publish-sheet" to Scene("O-000950", true, listOf("به شکل", "ریلز", "استوری", "@coineprofx.academy", "کاور", "gold-levels-cover.webp", "بدون کاور", "اول حساب را انتخاب کنید")),
            "output-publish-states" to Scene("O-000951", false, listOf("منتشر شد", "با کاور", "باز کن", "در حال انتشار", "سقف انتشار", "دوباره")),
            // ⟨0.19.9⟩ §45 a working group's daily output (no session): it went out on the owner's standing word, and the sheet of a
            // file of it opens with the package's own caption and cover
            "output-publish-auto" to Scene("O-000952", false, listOf("خودکار", "منتشر شد", "استوری: در حال انتشار", "خروجی هر روز را خودکار منتشر میکند")),
            "output-publish-auto-sheet" to Scene(
                "O-000952", true,
                // ⟨0.20.0⟩ §46 the time and the comment rule of this post, the package's own word and link already in place
                listOf("@tradeyar", "ریلز", "gold-levels-cover.webp", "حد ضرر را در ۳۰ ثانیه یاد بگیر", "زمان", "ساعت مشخص", "کامنت و لینک", "۳۰", "tradeyar.com/learn"),
            ),
            // ⟨0.20.0⟩ §46 a reel set for this evening with its comment word, and a carousel of two files on its way
            "output-publish-scheduled" to Scene("O-000953", false, listOf("زمان‌بندی شد", "ساعت 18:30", "کامنت «۷»", "اسلاید", "در حال انتشار")),
            // ⟨1.0.1⟩ §51 a scheduled post taken back: a reel he can still cancel («لغو»), a post taken back («لغو شد», his to publish
            // again), a story whose cancel is on its way, and a post IG-Hub would not cancel (he may try again)
            "output-publish-cancel" to Scene("O-000954", false, listOf("زمان‌بندی شد", "لغو", "پست، \u200Fلغو شد", "در حال لغو", "لغو انجام نشد")),
            // …asked once, in the row's own place
            "output-publish-cancel-ask" to Scene("O-000954", false, listOf("این انتشار لغو شود؟", "لغو کن", "نه"), tap = "لغو"),
            // ⟨1.0.1⟩ §49 «بهترین ساعت» among the sheet's times (chosen: what it rests on, «تأیید و زمان‌بندی»), and §52 the quiet line
            // under a cover that is no JPEG
            "output-publish-best-sheet" to Scene(
                "O-000952", true,
                listOf("بهترین ساعت (۲۱:۰۰)", "از روی لایک و کامنت", "تأیید و زمان‌بندی", "این تصویر هنگام انتشار خودکار به"),
                tap = "بهترین ساعت (۲۱:۰۰)",
            ),
        )

        @JvmStatic
        @ParameterizedRobolectricTestRunner.Parameters(name = "{0}-{1}")
        fun params(): List<Array<Any>> = SCREENS.keys.flatMap { listOf(arrayOf<Any>(it, true), arrayOf<Any>(it, false)) }
    }

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private lateinit var graph: AppGraph

    @Before
    fun setUp() {
        com.coinepro.hq.core.format.HqClock.fixed = java.time.Instant.parse("2026-11-06T08:30:00Z")
        graph = (ApplicationProvider.getApplicationContext<HqApp>()).graph
        graph.link.setForeground(false)
        graph.enterDemo()
        DemoLive.servers?.still = true
    }

    private fun settle(times: Int) = repeat(times) {
        Thread.sleep(200)
        shadowOf(Looper.getMainLooper()).idle()
        compose.mainClock.advanceTimeBy(250)
    }

    @Test
    fun screen() {
        val nav = object : Nav {
            override fun go(route: String) = Unit
            override fun back() = Unit
        }
        val scene = SCREENS.getValue(name)
        compose.mainClock.autoAdvance = false
        compose.setContent {
            DivanTheme(night) {
                CompositionLocalProvider(
                    LocalEnv provides graph.env.value, LocalToasts provides Toasts(), LocalNav provides nav,
                    com.coinepro.hq.designsystem.LocalReducedMotion provides true,
                ) {
                    val q = rememberQuery("deliverable:${scene.ref}", "deliverables") { deliverable(scene.ref) }
                    val panel = rememberQuery("publish-panel:${scene.ref}", "publish") { publishPanel(scene.ref) }
                    Column(
                        Modifier.fillMaxSize().background(if (scene.sheet) Divan.colors.overlay else Divan.colors.page).padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(14.dp),
                    ) {
                        val d = q.data
                        val p = panel.data
                        if (d != null && scene.sheet && p != null) PublishForm(d, publishable(d).first(), p) {}
                        else if (d != null) PublishSection(d)
                    }
                }
            }
        }
        settle(16)
        scene.tap?.let { t ->
            compose.onAllNodesWithText(t)[0].performClick()
            settle(6)
        }
        for (t in scene.shows) assertTrue("$name shows «$t»", compose.onAllNodesWithText(t, substring = true).fetchSemanticsNodes().isNotEmpty())
        compose.onRoot().captureRoboImage(
            "src/test/screenshots/$name-${if (night) "night" else "day"}.png",
            roborazziOptions = RoborazziOptions(
                recordOptions = RoborazziOptions.RecordOptions(resizeScale = 0.5),
                compareOptions = RoborazziOptions.CompareOptions(changeThreshold = 0.002f),
            ),
        )
    }
}

/** ⟨0.19.8⟩ §44.4, §44.5 the rules behind the section (no screen). */
class PublishRulesTest {
    private fun card(kind: String, cls: String) =
        com.coinepro.hq.core.net.Api.json.decodeFromString(
            Decision.serializer(),
            """{"id":"d1","ref":"D-000001","company":"FX","kind":"$kind","title":"t","action_class":"$cls","status":"pending","proposer":{"kind":"agent","code":"FX-MEDIA-01"},"created_at":"2026-11-10T00:00:00Z"}""",
        )

    @Test
    fun whatGoesOutAndCanBeTakenBackIsATap() {
        assertFalse(needsStepUp(card("media_publish", "A3")))
        // the passkey stays for money, deleting for good, keys and access, a destructive command
        for ((kind, cls) in listOf("hire" to "A2", "budget_change" to "A2", "server_destructive" to "A3", "line_publish" to "A3", "a3_action" to "A3")) {
            assertTrue(kind, needsStepUp(card(kind, cls)))
        }
    }

    @Test
    fun aVideoIsAReelOrAStoryAndTheNewestPublishOfAFileIsItsState() {
        assertEquals(listOf("reel", "story"), kindsOf(FileRef(id = "v", kind = "video")))
        assertEquals(listOf("post", "story"), kindsOf(FileRef(id = "i", kind = "image")))
        val panel = PublishPanel(
            order = "F-0100",
            publishes = listOf(SessionPublish(job = "2", fileId = "v", state = "published"), SessionPublish(job = "1", fileId = "v", state = "failed")),
        )
        assertEquals("published", publishOf(panel, "v")?.state)
        assertEquals(null, publishOf(panel, "i"))
        // ⟨0.19.9⟩ the same video as a reel and (newer) as a story: the reel is the row, the story a line under it
        val both = PublishPanel(publishes = listOf(
            SessionPublish(job = "4", fileId = "v", kind = "story", state = "publishing", auto = true),
            SessionPublish(job = "3", fileId = "v", kind = "reel", state = "published", auto = true),
            SessionPublish(job = "5", fileId = "s", kind = "story", state = "failed"),
        ))
        assertEquals("reel", publishOf(both, "v")?.kind)
        assertEquals("publishing", com.coinepro.hq.ui.outputs.storyOf(both, "v")?.state)
        assertEquals("story", publishOf(both, "s")?.kind)
        assertEquals(null, com.coinepro.hq.ui.outputs.storyOf(both, "s"))
        // ⟨0.20.0⟩ §46 with other files in the output, a carousel too; the time he set, in the owner's zone; a comment rule needs both
        assertEquals(listOf("reel", "story", "carousel"), kindsOf(FileRef(id = "v", kind = "video"), 2))
        com.coinepro.hq.core.format.HqClock.fixed = java.time.Instant.parse("2026-11-06T08:30:00Z")
        assertEquals("2026-11-06T18:30:00+03:30", com.coinepro.hq.ui.outputs.scheduledIso(0, "۱۸:۳۰"))
        assertEquals("2026-11-07T09:05:00+03:30", com.coinepro.hq.ui.outputs.scheduledIso(1, "9:05"))
        assertEquals(null, com.coinepro.hq.ui.outputs.scheduledIso(0, "25:00"))
        com.coinepro.hq.core.format.HqClock.fixed = null
        assertEquals(listOf("۷", "هفت"), com.coinepro.hq.ui.outputs.commentOf("۷، هفت", " لینک ", "http://x")!!.keywords)
        assertEquals(null, com.coinepro.hq.ui.outputs.commentOf("۷", " لینک ", "http://x")!!.link)
        assertTrue(com.coinepro.hq.ui.outputs.commentHalf("۷", "", ""))
        assertTrue(com.coinepro.hq.ui.outputs.commentHalf("", "", "https://x.test"))
        assertFalse(com.coinepro.hq.ui.outputs.commentHalf("", "", ""))
        assertFalse(com.coinepro.hq.ui.outputs.commentHalf("۷", "سلام", ""))
        assertEquals("18:30", com.coinepro.hq.core.data.clockOf(" ۱۸:۳۰ "))
        assertEquals("09:05", com.coinepro.hq.core.data.clockOf("9:05"))
        assertEquals(null, com.coinepro.hq.core.data.clockOf("18"))
        assertEquals("cover.png", com.coinepro.hq.ui.outputs.coverOf(listOf(FileRef(id = "a", name = "chart.png", kind = "image"), FileRef(id = "b", name = "cover.png", kind = "image")))?.name)
    }
}
