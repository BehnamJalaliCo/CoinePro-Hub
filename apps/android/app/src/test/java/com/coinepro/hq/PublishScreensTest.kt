package com.coinepro.hq

import android.os.Looper
import androidx.activity.ComponentActivity
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.SemanticsNodeInteractionsProvider
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.unit.dp
import androidx.test.core.app.ApplicationProvider
import com.coinepro.hq.core.AppGraph
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.DivanTheme
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Nav
import com.coinepro.hq.ui.Toasts
import com.github.takahirom.roborazzi.RoborazziOptions
import com.github.takahirom.roborazzi.captureRoboImage
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
 * ⟨1.3.0⟩ Contracts §60 and §61 with the D6 mockup's day (the demo of [V60Demo], 2026-11-17 11:40 Tehran), night and day:
 * - the home's two cards; the centre's today (sets as one row, a held story, «اکنون», what is still to be made), the desk under the
 *   centre's tabs, the Jalali month, «منتظر شما», the archive by company and page, @zaribsad's grid by day, P-000214 whole, DotCoin's
 *   twelve slides full screen, the search folding «بلاکچین»;
 * - the board by company, AF-0001's overview, its editor with a day switched off and its save bar, «چه عوض میشود», its runs, versions
 *   and health; the wizard at its kits and at its preview; the week.
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h1800dp-xxhdpi")
class PublishScreensTest(private val name: String, private val night: Boolean) {
    private class Scene(
        val shows: List<String>,
        val hides: List<String> = emptyList(),
        val act: ((SemanticsNodeInteractionsProvider, () -> Unit) -> Unit)? = null,
        val content: @Composable () -> Unit,
    )

    companion object {
        private val SCENES: Map<String, Scene> = linkedMapOf(
            "d6-home" to Scene(listOf("انتشار امروز", "نگه‌داشته", "تازه‌ترین‌ها", "اتوماسیون‌ها", "ساخت بعدی", "هزینه‌ی امروز")) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    com.coinepro.hq.ui.publish.PublishTodayCard()
                    com.coinepro.hq.ui.automation.AutomationsCard()
                }
            },
            "d6-today" to Scene(listOf("مرکز انتشار", "منتظر شما", "اکنون", "۷ استوری امروز", "اندیکاتور", "صفحه بسته است", "ساخت ۱۴:۰۰")) { com.coinepro.hq.ui.publish.PublishTodayScreen() },
            "d6-desk" to Scene(listOf("مرکز انتشار", "میز")) { com.coinepro.hq.ui.look.PublishDeskScreen() },
            "d6-calendar" to Scene(listOf("آبان ۱۴۰۵", "۶ از ۳۰", "ساخته میشود")) { com.coinepro.hq.ui.publish.PublishCalendarScreen() },
            "d6-waiting" to Scene(listOf("منتظر شما", "فدرال رزرو و بازار امروز", "این بار نه"), hides = listOf("سقف را")) { com.coinepro.hq.ui.publish.PublishWaitingScreen() },
            "d6-archive" to Scene(listOf("تریدیار", "@zaribsad", "استوری ۵۱", "IG-Hub", "@dotcoin.me")) { com.coinepro.hq.ui.publish.PublishArchiveScreen() },
            "d6-page" to Scene(listOf("@zaribsad", "امروز", "دیروز", "زی‌کش", "ناموفق")) { com.coinepro.hq.ui.publish.PublishPageScreen("zaribsad") },
            "d6-item" to Scene(listOf("زی‌کش؛ حریم خصوصی در بلاک‌چین", "کپشن", "کلمه‌ی کامنت", "پیام دایرکت", "جواب‌های عمومی", "ساخته‌شده با", "reel.mp4", "بینش")) {
                com.coinepro.hq.ui.publish.PublicationScreen("P-000214")
            },
            "d6-set" to Scene(listOf("اسلاید ۳ از ۱۲", "«سرد»")) { com.coinepro.hq.ui.publish.StorySetScreen("P-000301") },
            "d6-search" to Scene(listOf("زی‌کش؛ حریم خصوصی", "کیف پول سرد"), act = { c, _ -> c.onAllNodesWithTag("pub-search")[0].performTextInput("بلاکچین") }) {
                com.coinepro.hq.ui.publish.PublishSearchScreen()
            },
            "d6-board" to Scene(listOf("اتوماسیون‌ها", "تریدیار", "ریلز چرخشی ضریب صد", "دور ۴ هفته", "هزینه‌ی امروز")) { com.coinepro.hq.ui.automation.FlowsBoardScreen() },
            "d6-overview" to Scene(listOf("ریلز روزانه‌ی پروچارت", "نمای کلی", "انتشار بعدی", "همین حالا بساز")) { com.coinepro.hq.ui.automation.FlowDefScreen("AF-0001") },
            "d6-settings" to Scene(listOf("ساعت انتشار", "هفته‌ی ۴", "روزهای هفته", "شروع ساخت", "هشدار هزینه‌ی روز", "۱ تغییر"), act = { c, _ -> c.onAllNodesWithText("ج")[0].performClick() }) {
                com.coinepro.hq.ui.automation.FlowDefScreen("AF-0001", tab0 = "settings")
            },
            // the sheet opens in its own window: its body here, over the page, as the owner sees it
            "d6-diff" to Scene(listOf("چه عوض میشود", "ساعت انتشار", "روزهای هفته", "نسخه‌ی ۳ میماند")) {
                val f = com.coinepro.hq.ui.rememberQuery("test-flowdef", "flows") { flowDef("AF-0001") }.data
                if (f != null) {
                    val before = com.coinepro.hq.core.data.flowDraftOf(f)
                    val after = before.copy(hours = listOf("10:00") + before.hours.drop(1), days = before.days - 6)
                    com.coinepro.hq.designsystem.SpringSheetPreview("چه عوض میشود", sub = "نسخه‌ی ۴", fill = true) {
                        com.coinepro.hq.ui.automation.DiffBody(f, com.coinepro.hq.core.data.draftChanges(before, after) { "Opus 5.5" }, "") {}
                    }
                }
            },
            "d6-runs" to Scene(listOf("هزینه‌ی هر روز", "اندیکاتور", "رد شد")) { com.coinepro.hq.ui.automation.FlowDefScreen("AF-0001", tab0 = "runs") },
            "d6-versions" to Scene(listOf("برگشت به این نسخه", "سرور هاب", "در کار")) { com.coinepro.hq.ui.automation.FlowDefScreen("AF-0001", tab0 = "versions") },
            "d6-health" to Scene(listOf("سلامت", "هشدارها", "بسته شد")) { com.coinepro.hq.ui.automation.FlowDefScreen("AF-0001", tab0 = "health") },
            "d6-wizard" to Scene(listOf("اتوماسیون تازه", "قالب", "ریلز خبری", "کیت تازه میخواهی؟")) { com.coinepro.hq.ui.automation.NewFlowScreen("dotcoin.me", step0 = 1) },
            "d6-wizard-preview" to Scene(listOf("ساعت‌ها", "مدل و هزینه", "پیش‌نمایش", "بساز و روشن کن")) {
                com.coinepro.hq.ui.automation.NewFlowScreen("dotcoin.me", step0 = 4, kit0 = "dotcoin-news")
            },
            "d6-week" to Scene(listOf("خلاصه‌ی هفته", "انتشار هر روز", "@zaribsad", "بهترین")) { com.coinepro.hq.ui.automation.FlowWeekScreen() },
        )

        @JvmStatic
        @ParameterizedRobolectricTestRunner.Parameters(name = "{0}-{1}")
        fun params(): List<Array<Any>> = SCENES.keys.flatMap { listOf(arrayOf<Any>(it, true), arrayOf<Any>(it, false)) }
    }

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private lateinit var graph: AppGraph

    @Before
    fun setUp() {
        com.coinepro.hq.core.format.HqClock.fixed = java.time.Instant.parse("2026-11-17T08:10:00Z")
        graph = (ApplicationProvider.getApplicationContext<HqApp>()).graph
        graph.link.setForeground(false)
        graph.enterDemo()
        DemoLive.servers?.still = true
    }

    private fun settle(rounds: Int) = repeat(rounds) {
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
        val scene = SCENES.getValue(name)
        compose.mainClock.autoAdvance = false
        compose.setContent {
            DivanTheme(night) {
                CompositionLocalProvider(
                    LocalEnv provides graph.env.value, LocalToasts provides Toasts(), LocalNav provides nav,
                    com.coinepro.hq.designsystem.LocalReducedMotion provides true,
                ) {
                    Box(Modifier.fillMaxSize().background(Divan.colors.page)) { scene.content() }
                }
            }
        }
        settle(20)
        scene.act?.let { it(compose) { settle(8) }; settle(10) }
        for (t in scene.shows) assertTrue("$name shows «$t»", compose.onAllNodesWithText(t, substring = true, useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty())
        for (t in scene.hides) assertTrue("$name does not show «$t»", compose.onAllNodesWithText(t, substring = true, useUnmergedTree = true).fetchSemanticsNodes().isEmpty())
        compose.onRoot().captureRoboImage(
            "src/test/screenshots/$name-${if (night) "night" else "day"}.png",
            roborazziOptions = RoborazziOptions(
                recordOptions = RoborazziOptions.RecordOptions(resizeScale = 0.5),
                compareOptions = RoborazziOptions.CompareOptions(changeThreshold = 0.002f),
            ),
        )
    }
}
