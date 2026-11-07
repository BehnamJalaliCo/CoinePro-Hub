package com.coinepro.hq

import android.os.Looper
import androidx.activity.ComponentActivity
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.unit.dp
import androidx.test.core.app.ApplicationProvider
import com.coinepro.hq.core.AppGraph
import com.coinepro.hq.core.net.TalkCard
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.DivanTheme
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Nav
import com.coinepro.hq.ui.Toasts
import com.github.takahirom.roborazzi.RoborazziOptions
import com.github.takahirom.roborazzi.captureRoboImage
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.ParameterizedRobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * ⟨1.22⟩ Contract §40, night and day, with the demo holding, drawn tall (2000dp): a session becomes a working group.
 * - the «جزئیات» of Pro-Chart's SEO session: «تا اینجا» (folded, its ref hidden), «کارگروه از این جلسه بساز» and the draft it made;
 * - the `playbook` cards: the draft's (live, «باز کن» and «مُهر کن»), the holder's rewrite in words (the new draft, «اجرا کن»), a sealed
 *   one's, and a card of a kind this app does not know (drawn as any card), in two screens;
 * - the playbook's page as a draft (the hint, what was dropped, the platform picker, seats with their helpers' logos, routines in plain
 *   Persian, rules, each to take out or edit, «مُهر کن») and sealed (members, «به شرکت دیگر بده», ⋮);
 * - «به شرکت دیگر بده»: a company and a platform and a note, and «بدون تغییر»;
 * - the library «کارگروه‌ها», sealed first;
 * - a session opened from a playbook for Pro-Chart: «از کارگروه …» in its head.
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h2000dp-xxhdpi")
class PlaybookScreensTest(private val name: String, private val night: Boolean) {
    /** What is done on the demo hub before the screen is drawn (its answer goes to the screen), and the screen. */
    private class Scene(val setup: (suspend (AppGraph) -> String?)? = null, val content: @Composable (String?) -> Unit)

    companion object {
        private val SCENES: Map<String, Scene> = linkedMapOf(
            "playbook-session-details" to Scene { Details("F-0104") },
            "playbook-cards" to Scene { Cards(sealed = false) },
            "playbook-cards-sealed" to Scene { Cards(sealed = true) },
            "playbook-draft" to Scene { com.coinepro.hq.ui.playbook.PlaybookScreen("PB-0002") },
            "playbook-sealed" to Scene { com.coinepro.hq.ui.playbook.PlaybookScreen("PB-0001") },
            "playbook-apply" to Scene { Apply() },
            "playbook-library" to Scene { com.coinepro.hq.ui.playbook.PlaybooksScreen() },
            "playbook-session-from" to Scene({ g ->
                g.env.value.api.applyPlaybook("PB-0001", "PC", "youtube", "برای یوتیوب، ویدیوهای بلندتر.", false, java.util.UUID.randomUUID().toString()).order
            }) { ref -> com.coinepro.hq.ui.session.OrderSessionScreen(ref.orEmpty()) },
        )

        @Composable
        private fun Sheet(title: String, content: @Composable () -> Unit) {
            Column(
                Modifier.fillMaxSize().background(Divan.colors.overlay).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                Text(title, style = Divan.type.h2)
                content()
            }
        }

        @Composable
        private fun Details(ref: String) {
            val o = com.coinepro.hq.ui.v29.rememberOrderReport(ref).data ?: return
            Sheet("جزئیات جلسه") {
                com.coinepro.hq.ui.session.SessionDetailsBody(
                    o, closed = false, sessionsOn = true, participants = com.coinepro.hq.core.data.orderParticipants(o.participants), addressee = null,
                    onPick = {}, onAddPerson = {}, onAddModel = {}, onPace = {}, onTasksChanged = {}, onClose = {}, onReopen = {}, onHide = {}, onErase = {},
                )
            }
        }

        private fun card(id: String, kind: String, payload: String, state: String = "offered", title: String = "", body: String = "") = TalkCard(
            id = JsonPrimitive(id), kind = kind, titleFa = title, bodyFa = body, state = state,
            payload = com.coinepro.hq.core.net.Api.json.parseToJsonElement(payload).jsonObject,
        )

        @Composable
        private fun Cards(sealed: Boolean) {
            val c = Divan.colors
            Column(Modifier.fillMaxSize().background(c.page).padding(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                if (sealed) {
                    // A sealed one: «باز کن» only.
                    com.coinepro.hq.ui.v32.TalkCardView(card("TC-403", "playbook", """{"playbook":"PB-0001"}"""), { _, _ -> }, { })
                    HorizontalDivider(color = c.lineDivider)
                    // A kind this app does not know yet: still a card, with its words and its choices.
                    com.coinepro.hq.ui.v32.TalkCardView(card("TC-404", "survey", "{}", title = "نظرسنجی از مشتری‌ها", body = "پنج پرسش کوتاه برای مشتری‌های این ماه."), { _, _ -> }, { })
                    return@Column
                }
                // The card the draft posted: the playbook itself, live.
                com.coinepro.hq.ui.v32.TalkCardView(card("TC-401", "playbook", """{"playbook":"PB-0002"}"""), { _, _ -> }, { })
                // The holder's rewrite in the owner's words: the whole new draft, stored by «اجرا کن».
                com.coinepro.hq.ui.v32.TalkCardView(
                    card("TC-402", "playbook", """{"playbook":"PB-0002","draft":{"title_fa":"سئوی هفتگی سایت","purpose_fa":"هر هفته رقبا بررسی شوند و دو مقاله منتشر شود.","platform":"site",
                        "seats":[{"seat":"writer","role":"content_writer","title_fa":"نویسنده‌ی مقاله","duties_fa":"هفته‌ای دو مقاله؛ موضوع با ChatGPT، متن با DeepSeek سنجیده میشود.","helpers":["gpt","deepseek"]}],
                        "routines":[{"key":"article","title_fa":"مقاله‌ی آموزشی","seat":"writer","schedule":"FREQ=WEEKLY;BYDAY=MO,TH;BYHOUR=10;BYMINUTE=30","brief_md":""}],
                        "kpis":[],"connections":[],"rules_fa":["هیچ مقاله‌ای بدون منبع منتشر نشود."]}}"""),
                    { _, _ -> }, { },
                )
            }
        }

        @Composable
        private fun Apply() {
            val pb = com.coinepro.hq.ui.playbook.rememberPlaybook("PB-0001").data ?: return
            val companies = com.coinepro.hq.ui.rememberCompanies()
            if (companies.isEmpty()) return
            Sheet("به شرکت دیگر بده") {
                com.coinepro.hq.ui.playbook.ApplyBody(pb, companies, company0 = "PC") { _, _ -> }
                HorizontalDivider(color = Divan.colors.lineDivider)
                com.coinepro.hq.ui.playbook.ApplyBody(pb, companies, company0 = "PC", asIs0 = true) { _, _ -> }
            }
        }

        @JvmStatic
        @ParameterizedRobolectricTestRunner.Parameters(name = "{0}-{1}")
        fun params(): List<Array<Any>> = SCENES.keys.flatMap { listOf(arrayOf<Any>(it, true), arrayOf<Any>(it, false)) }
    }

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private lateinit var graph: AppGraph

    @Before
    fun setUp() {
        com.coinepro.hq.core.format.HqClock.fixed = java.time.Instant.parse("2026-11-07T08:30:00Z")
        graph = (ApplicationProvider.getApplicationContext<HqApp>()).graph
        graph.link.setForeground(false)
        graph.enterDemo()
        DemoLive.servers?.still = true
    }

    @Test
    fun screen() {
        val nav = object : Nav {
            override fun go(route: String) = Unit
            override fun back() = Unit
        }
        val scene = SCENES.getValue(name)
        val made = scene.setup?.let { s -> kotlinx.coroutines.runBlocking { s(graph) } }
        compose.mainClock.autoAdvance = false
        compose.setContent {
            DivanTheme(night) {
                CompositionLocalProvider(
                    LocalEnv provides graph.env.value, LocalToasts provides Toasts(), LocalNav provides nav,
                    com.coinepro.hq.designsystem.LocalReducedMotion provides true,
                ) {
                    Box(Modifier.fillMaxSize().background(Divan.colors.page)) { scene.content(made) }
                }
            }
        }
        // The playbook, the companies, the report and the talk: each a demo answer of ~60–150 ms on OkHttp threads. Let them land.
        repeat(20) {
            Thread.sleep(200)
            shadowOf(Looper.getMainLooper()).idle()
            compose.mainClock.advanceTimeBy(250)
        }
        compose.onRoot().captureRoboImage(
            "src/test/screenshots/$name-${if (night) "night" else "day"}.png",
            roborazziOptions = RoborazziOptions(
                recordOptions = RoborazziOptions.RecordOptions(resizeScale = 0.5),
                compareOptions = RoborazziOptions.CompareOptions(changeThreshold = 0.002f),
            ),
        )
    }
}
