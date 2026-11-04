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
import com.coinepro.hq.core.net.Compiled
import com.coinepro.hq.core.net.InsightBest
import com.coinepro.hq.core.net.Insights
import com.coinepro.hq.core.net.Kit
import com.coinepro.hq.core.net.KitLine
import kotlinx.serialization.json.JsonObject
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
 * ⟨1.13⟩ Contract §31, night and day, with the demo holding, drawn tall (1600dp): a line's lessons, the kit gallery and a kit's preview
 * before the seal, a company's newsletter, SEO and ads tabs, the campaign calendar with its conflicts, and an automation from one sentence
 * (what it understood and what it refuses).
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h1600dp-xxhdpi")
class V31ScreensTest(private val name: String, private val night: Boolean) {
    companion object {
        private val INSIGHTS = Insights(
            line = "LN-0001", metric = "views", windowRuns = 12, best = InsightBest(18, "25 تا 35 ثانیه", "Kore", "پینترست"),
            topHooks = listOf("طلا دوباره به 2000 دلار رسید؛ خریدارها هنوز هستند؟", "سه اشتباه رایج وقتی قیمت به حمایت میرسد"),
            lessonsFa = listOf("ریلزهای ساعت 18 حدود 40% بیشتر از ساعت 10 دیده شدند.", "متن‌های 25 تا 35 ثانیه‌ای بیشتر تا آخر دیده میشوند."),
            updatedAt = "2026-10-17T05:40:00Z",
        )
        private val KIT = Kit(
            key = "media_channel", titleFa = "شرکت رسانه‌ی کانال‌محور", purposeFa = "یک شرکت تازه که هر روز برای کانال‌هایش محتوا میسازد و منتشر میکند.",
            teamTemplate = "media_company", groups = listOf("content"),
            lines = listOf(KitLine("instagram_reel", "instagram_reel", "ریلز آموزشی"), KitLine("telegram_post", "telegram_post", "پست روزانه‌ی کانال")),
            kpis = listOf("reach", "followers"), connections = listOf("instagram", "telegram"),
        )
        private val COMPILED = Compiled(
            rule = JsonObject(emptyMap()),
            previewFa = "هر شنبه ساعت 10:00 خط تولید را اجرا میکند و اگر بازده تبلیغ کم شد، به تو خبر میدهد. کاری جز این نمیکند و بدون مُهر تو اجرا نمیشود.",
            refusedFa = listOf("پرداخت پول در فهرست کارهای مجاز نیست؛ فقط ساخت کار، اجرا یا مکث خط، خبر دادن و توقف تبلیغ ممکن است."),
        )

        private val SCREENS: Map<String, @Composable (AppGraph) -> Unit> = linkedMapOf(
            "v31-insights" to { _ -> Cardlike { com.coinepro.hq.ui.v31.InsightsCard(INSIGHTS) } },
            "v31-kits" to { _ -> com.coinepro.hq.ui.v31.KitsScreen() },
            "v31-kit-preview" to { _ -> Sheetlike { com.coinepro.hq.ui.v31.KitFlowBody(KIT, onClose = {}, stage0 = "preview", nameFa0 = "نوین‌رسانه", nameEn0 = "NovinMedia", code0 = "NV", autoPreview = true) } },
            "v31-company-newsletter" to { _ -> com.coinepro.hq.ui.companies.CompanyScreen("TY", tab0 = "newsletter") },
            "v31-company-seo" to { _ -> com.coinepro.hq.ui.companies.CompanyScreen("TY", tab0 = "seo") },
            "v31-company-ads" to { _ -> com.coinepro.hq.ui.companies.CompanyScreen("TY", tab0 = "ads") },
            "v31-campaign-calendar" to { _ -> com.coinepro.hq.ui.v31.CampaignCalendarScreen() },
            "v31-automations" to { _ -> com.coinepro.hq.ui.v31.AutomationsScreen(sentence0 = "هر شنبه ساعت 10 یک ریلز بساز و اگر بازده تبلیغ کم شد خبرم کن و پول پرداخت کن", compiled0 = COMPILED) },
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
