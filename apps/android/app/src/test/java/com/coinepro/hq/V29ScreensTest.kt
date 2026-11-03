package com.coinepro.hq

import android.os.Looper
import androidx.activity.ComponentActivity
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.unit.dp
import androidx.test.core.app.ApplicationProvider
import com.coinepro.hq.core.AppGraph
import com.coinepro.hq.core.net.OrderRoute29
import com.coinepro.hq.core.net.OwnerRule
import com.coinepro.hq.core.net.Work
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.DivanTheme
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Nav
import com.coinepro.hq.ui.Toasts
import com.coinepro.hq.ui.media.VoiceResult
import com.coinepro.hq.ui.v29.Listening
import com.github.takahirom.roborazzi.RoborazziOptions
import com.github.takahirom.roborazzi.captureRoboImage
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.ParameterizedRobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * ⟨1.11⟩ Contract §29, night and day, with the demo holding, drawn tall (1600dp) so each page is seen whole: the home's lower part (the
 * content group's followers per company and the owner's orders with their states); an order's report blocked (its two blockers and
 * fixes), at work (plan and steps) and delivered (the end summary); the voice sheet with the secretary's line and its route editor; the
 * long voice listening on the phone (the text growing) and recording for the hub (chunks sent); a rule written and proposed, and the
 * rules list; the council v2 (the captain's plan, roles, the fact pack, answers behind «جزئیات»); the working groups and the content
 * group; a company's readiness, connections (one connection's guide and key) and «فنی» tab; the org chart with each employee's state.
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h1600dp-xxhdpi")
class V29ScreensTest(private val name: String, private val night: Boolean) {
    companion object {
        private const val SPOKEN = "برای تریدیار سه ریلز درباره‌ی سیگنال طلا بساز و در اینستاگرام منتشر کن."

        private val ROUTE = OrderRoute29(
            companies = listOf("TY"), department = "MEDIA", collaborators = listOf("FX"), outputKind = "reel", count = 3, budgetTokens = 400_000,
            previewFa = "→ تریدیار/رسانه و طراحی + کوینه‌پرو FX/انتشار؛ خروجی: 3 ریلز؛ بودجه: 400K واحد مصرف",
            whyFa = "تولید محتوا با مدیر رسانه‌ی همان شرکت است؛ انتشار در اینستاگرام از راه کوینه‌پرو FX.",
        )

        private val PROPOSED = OwnerRule(
            ref = "SO-031", textMd = "هیچ پستی بدون منبع برای عددهایش منتشر نشود.", source = "voice",
            appliesTo = JsonObject(mapOf("roles" to JsonArray(listOf(JsonPrimitive("media_director"), JsonPrimitive("scriptwriter"))))), status = "proposed",
        )

        private val COUNCIL = Work(
            id = "w-000222", ref = "W-000222", company = "TY", title = "برای فروش اشتراک طلایی تریدیار در سه ماه آینده چه کنیم؟", status = "delivered", mode = "council",
        )

        private val SCREENS: Map<String, @Composable (AppGraph) -> Unit> = linkedMapOf(
            "v29-home-lower" to { _ ->
                Cardlike {
                    com.coinepro.hq.ui.v29.rememberHome().data?.let { h ->
                        com.coinepro.hq.ui.v29.MorningCard(h.morning)
                        for (g in h.groups) com.coinepro.hq.ui.v29.GroupKpiCard(g)
                        com.coinepro.hq.ui.v29.HomeOrdersBlock(h.orders) {}
                    }
                }
            },
            "v29-order-blocked" to { _ -> com.coinepro.hq.ui.v29.OrderReportScreen("F-0042") },
            "v29-order-working" to { _ -> com.coinepro.hq.ui.v29.OrderReportScreen("F-0041") },
            "v29-order-delivered" to { _ -> com.coinepro.hq.ui.v29.OrderReportScreen("F-0043") },
            "v29-voice-preview" to { _ ->
                Sheetlike { com.coinepro.hq.ui.work.VoiceOrderBody({}, listen = false, text0 = SPOKEN, voice0 = VoiceResult(SPOKEN, null, 7.4, "phone"), preview0 = ROUTE) }
            },
            "v29-voice-route" to { _ -> Sheetlike { com.coinepro.hq.ui.v29.RouteEditorBody(ROUTE) {} } },
            "v29-voice-long-phone" to { _ ->
                Sheetlike { com.coinepro.hq.ui.work.VoiceOrderBody({}, listen = false, listening0 = Listening(LONG.take(170), 42.0, "phone")) }
            },
            "v29-voice-long-hub" to { _ ->
                Sheetlike {
                    com.coinepro.hq.ui.work.VoiceOrderBody(
                        {}, listen = false,
                        listening0 = Listening(LONG.take(120), 312.0, "hub", chunks = 4, sent = 3, fellBack = "بیش از یک دقیقه شد؛ از این‌جا صدا ضبط میشود و هاب آن را به متن میکند. ادامه بده."),
                    )
                }
            },
            "v29-rule-write" to { _ -> Sheetlike { com.coinepro.hq.ui.work.VoiceOrderBody({}, listen = false, rule0 = true, text0 = "هیچ پستی بدون منبع برای عددهایش منتشر نشود") } },
            "v29-rule-proposed" to { _ -> Sheetlike { com.coinepro.hq.ui.work.VoiceOrderBody({}, listen = false, rule0 = true, proposed0 = PROPOSED) } },
            "v29-rules" to { _ -> com.coinepro.hq.ui.v29.RulesScreen() },
            "v29-council" to { _ -> Cardlike { com.coinepro.hq.ui.work.CouncilCard(COUNCIL) } },
            "v29-groups" to { _ -> com.coinepro.hq.ui.v29.GroupsScreen() },
            "v29-group" to { _ -> com.coinepro.hq.ui.v29.GroupScreen("content") },
            "v29-company-growth" to { _ -> com.coinepro.hq.ui.companies.CompanyScreen("FX", tab0 = "growth") },
            "v29-company-connections" to { _ -> com.coinepro.hq.ui.companies.CompanyScreen("TY", tab0 = "connections") },
            "v29-connection" to { _ ->
                Sheetlike { com.coinepro.hq.ui.v29.ConnectionBody("FX", com.coinepro.hq.core.net.CompanyConnection(company = "FX", kind = "telegram")) }
            },
            "v29-company-tech" to { _ -> com.coinepro.hq.ui.companies.CompanyScreen("TY", tab0 = "servers") },
            "v29-company-people" to { _ -> com.coinepro.hq.ui.companies.CompanyScreen("TY", tab0 = "people") },
        )

        private const val LONG = V29Demo.LONG_TEXT

        @JvmStatic
        @ParameterizedRobolectricTestRunner.Parameters(name = "{0}-{1}")
        fun params(): List<Array<Any>> = SCREENS.keys.flatMap { listOf(arrayOf<Any>(it, true), arrayOf<Any>(it, false)) }

        @Composable
        private fun Cardlike(content: @Composable () -> Unit) {
            Column(
                Modifier.fillMaxSize().background(Divan.colors.page).verticalScroll(rememberScrollState()).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) { content() }
        }

        @Composable
        private fun Sheetlike(content: @Composable () -> Unit) {
            Column(
                Modifier.fillMaxSize().background(Divan.colors.overlay).verticalScroll(rememberScrollState()).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) { content() }
        }
    }

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private lateinit var graph: AppGraph

    @Before
    fun setUp() {
        com.coinepro.hq.core.format.HqClock.fixed = java.time.Instant.parse("2026-10-17T08:30:00Z")
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
        compose.mainClock.autoAdvance = false
        compose.setContent {
            DivanTheme(night) {
                CompositionLocalProvider(
                    LocalEnv provides graph.env.value, LocalToasts provides Toasts(), LocalNav provides nav,
                    com.coinepro.hq.designsystem.LocalReducedMotion provides true,
                ) {
                    Box(Modifier.fillMaxSize().background(Divan.colors.page)) { SCREENS.getValue(name)(graph) }
                }
            }
        }
        // Demo responses take ~150 ms each on OkHttp threads (a page, then what it opens: the group's members, runs, KPIs, each readiness);
        // the secretary's preview waits 650 ms of the test clock first. Let them all land.
        repeat(22) {
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
