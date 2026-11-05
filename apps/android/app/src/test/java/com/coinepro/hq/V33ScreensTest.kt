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
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onRoot
import org.junit.Assert.assertTrue
import androidx.compose.ui.unit.dp
import androidx.test.core.app.ApplicationProvider
import com.coinepro.hq.core.AppGraph
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.LeadDraft
import com.coinepro.hq.core.net.Page
import com.coinepro.hq.core.net.PersonaTest
import com.coinepro.hq.core.net.UsageReport
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.DivanTheme
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Nav
import com.coinepro.hq.ui.Toasts
import com.github.takahirom.roborazzi.RoborazziOptions
import com.github.takahirom.roborazzi.captureRoboImage
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.ParameterizedRobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * ⟨1.15⟩ Contract §33, night and day, with the demo holding (`DemoV33`), drawn tall (1600dp): usage in the advisor's words with its
 * figures, a company's money (the board, the payments with the daily reconcile, the sources), the holding's revenue board with where the
 * money comes from, the affiliate gaps, sales (the pipeline, one lead with its drafted follow-up), personas with a message test, a
 * company's journey and every company's, the order report with parallel parts and a workspace on a company's server, and the cartable with
 * each card's money impact.
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h1600dp-xxhdpi")
class V33ScreensTest(private val name: String, private val night: Boolean) {
    companion object {
        private val DRAFT = LeadDraft(
            lead = "LD-000041", guardOk = true,
            draftFa = "سلام، دوره‌ی آزمایشی شما فردا تمام میشود. اگر تحلیل‌های روزانه به کارتان آمده، پلن سالانه 249 USDT است و دو ماهش رایگان حساب میشود.",
        )
        private const val TEXT = "این هفته با تحلیل روزانه‌ی طلا، حد ضرر هر معامله را از قبل میدانی. 7 روز رایگان امتحان کن."

        /** The demo's own answers, read when the screen is drawn (after the clock is fixed). */
        private fun usage(): UsageReport = Api.json.decodeFromJsonElement(Page.serializer(UsageReport.serializer()),
            V33Demo().handle("GET", "/usage/reports", mapOf("period" to "week"), null)!!.second).items.first()
        private fun test(): PersonaTest = Api.json.decodeFromJsonElement(PersonaTest.serializer(),
            V33Demo().handle("POST", "/companies/TY/personas/test", emptyMap(), JsonObject(mapOf("text" to JsonPrimitive(TEXT))))!!.second)

        private val SCREENS: Map<String, @Composable (AppGraph) -> Unit> = linkedMapOf(
            "v33-usage" to { _ -> com.coinepro.hq.ui.v33.UsageScreen() },
            "v33-usage-pack" to { _ -> Cardlike { com.coinepro.hq.ui.v33.UsageReportCard(usage(), head = true, open0 = true) } },
            "v33-company-money" to { _ -> com.coinepro.hq.ui.companies.CompanyScreen("TY", tab0 = "money") },
            "v33-money-payments" to { _ -> Cardlike { com.coinepro.hq.ui.v33.CompanyMoney("TY", seg0 = "payments") } },
            "v33-money-sources" to { _ -> Cardlike { com.coinepro.hq.ui.v33.CompanyMoney("TY", seg0 = "sources") } },
            "v33-revenue-board" to { _ -> com.coinepro.hq.ui.v33.RevenueBoardScreen() },
            "v33-affiliate-gaps" to { _ -> com.coinepro.hq.ui.v33.AffiliateGapsScreen() },
            "v33-company-sales" to { _ -> com.coinepro.hq.ui.companies.CompanyScreen("TY", tab0 = "sales") },
            "v33-lead" to { _ -> com.coinepro.hq.ui.v33.LeadScreen("LD-000041", draft0 = DRAFT) },
            "v33-company-personas" to { _ -> Cardlike { com.coinepro.hq.ui.v33.CompanyPersonas("TY", test0 = test(), text0 = TEXT) } },
            "v33-company-journey" to { _ -> com.coinepro.hq.ui.companies.CompanyScreen("TY", tab0 = "journey") },
            "v33-journeys" to { _ -> com.coinepro.hq.ui.v33.JourneysScreen() },
            "v33-order-parallel" to { _ -> com.coinepro.hq.ui.v29.OrderReportScreen("F-0045") },
            "v33-cartable-impact" to { _ -> com.coinepro.hq.ui.cartable.CartableScreen() },
            "v33-decision-impact" to { _ -> com.coinepro.hq.ui.cartable.DecisionScreen("D-000035") },
        )

        /** A line each screen shows only once its data arrived (not its skeleton, empty or error state). */
        private val SHOWS = mapOf(
            "v33-usage" to "یک صرفه‌جویی", "v33-usage-pack" to "به تفکیک شرکت", "v33-company-money" to "درآمد ماهانه",
            "v33-money-payments" to "تطبیق روزانه", "v33-money-sources" to "زنجیره‌ی عمومی", "v33-revenue-board" to "از کجا میاید",
            "v33-affiliate-gaps" to "باید میرسید", "v33-company-sales" to "سرنخ باز", "v33-lead" to "پیش‌نویس پیگیری", "v33-company-personas" to "میانگین",
            "v33-company-journey" to "قدم بعدی", "v33-journeys" to "خط زمان", "v33-order-parallel" to "بخش‌های موازی", "v33-cartable-impact" to "تخمین",
            "v33-decision-impact" to "اثر پولی",
        )

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
        // Demo responses take ~60–150 ms each on OkHttp threads (a page, then what it opens: a lead's pipeline, the companies). Let them all land.
        repeat(22) {
            Thread.sleep(200)
            shadowOf(Looper.getMainLooper()).idle()
            compose.mainClock.advanceTimeBy(250)
        }
        assertTrue("$name: «${SHOWS.getValue(name)}» not on screen", compose.onAllNodesWithText(SHOWS.getValue(name), substring = true, useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty())
        compose.onRoot().captureRoboImage(
            "src/test/screenshots/$name-${if (night) "night" else "day"}.png",
            roborazziOptions = RoborazziOptions(
                recordOptions = RoborazziOptions.RecordOptions(resizeScale = 0.5),
                compareOptions = RoborazziOptions.CompareOptions(changeThreshold = 0.002f),
            ),
        )
    }
}
