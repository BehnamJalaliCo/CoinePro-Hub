package com.coinepro.hq

import android.os.Looper
import androidx.activity.ComponentActivity
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.unit.dp
import androidx.test.core.app.ApplicationProvider
import com.coinepro.hq.core.AppGraph
import com.coinepro.hq.core.data.COMMAND_FA
import com.coinepro.hq.core.data.COMMAND_TEMPLATES
import com.coinepro.hq.core.data.ROUTINE_TEMPLATE_FA
import com.coinepro.hq.core.data.templateText
import com.coinepro.hq.core.net.Office
import com.coinepro.hq.core.net.SessionRoutine
import com.coinepro.hq.designsystem.Amount
import com.coinepro.hq.designsystem.CollapsingHeader
import com.coinepro.hq.designsystem.DecisionBar
import com.coinepro.hq.designsystem.DecisionPlace
import com.coinepro.hq.designsystem.DecisionState
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.DivanTheme
import com.coinepro.hq.designsystem.Facts
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.QuietAction
import com.coinepro.hq.designsystem.Ring
import com.coinepro.hq.designsystem.RingTone
import com.coinepro.hq.designsystem.Spark
import com.coinepro.hq.designsystem.SpringSheetPreview
import com.coinepro.hq.designsystem.StatRow
import com.coinepro.hq.designsystem.StatTile
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Nav
import com.coinepro.hq.ui.Toasts
import com.coinepro.hq.ui.look.CommandButton
import com.coinepro.hq.ui.look.CommandDecisionBar
import com.coinepro.hq.ui.look.CommandFields
import com.coinepro.hq.ui.look.CommandMode
import com.coinepro.hq.ui.look.CommandOpen
import com.coinepro.hq.ui.look.CommandState
import com.coinepro.hq.ui.look.LimitsBlock
import com.coinepro.hq.ui.look.TurnRow
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.github.takahirom.roborazzi.RoborazziOptions
import com.github.takahirom.roborazzi.captureRoboImage
import org.junit.After
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
 * ⟨1.0.1⟩ Part C, the look, night and day, with the demo holding. The shared pieces every screen is built from (the decision bar in
 * each of its states, the one sheet as tall as its content, the ring and the tiny line, the header that folds, the text rules:
 * a Latin token as one run, the hairline for «·», an amount that shrinks instead of being cut), the command (its round button over
 * the home, the sheet empty, ready, refused, the routine form and its confirmation), the limits of the treasury in every state the
 * hub can say (and a hub before them), a home with nothing waiting, and the notifications of one level. Each is checked to show its
 * words before it is drawn.
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h880dp-xxhdpi")
class LookScreensTest(private val name: String, private val night: Boolean) {
    /** A scene: what the demo is asked for first, what it must show, and the screen. */
    private class Scene(val shows: List<String>, val before: () -> Unit = {}, val content: @Composable () -> Unit)

    companion object {
        private const val WORDS = "برای تریدیار و پرو-چارت یک ریلز اینستاگرام بساز: سه اشتباه رایج در حد ضرر"

        private val SCREENS: Map<String, Scene> = linkedMapOf(
            // ------------------------------------------------------------------ C0 the shared pieces
            "look-decision-bar" to Scene(listOf("تأیید و انتشار", "اصلاح", "انجام شد")) { Bars() },
            "look-rings" to Scene(listOf("62%", "از ۶۰ دقیقه")) { Rings() },
            "look-collapse" to Scene(listOf("ریلز هفته‌ی آموزش طلا")) { Collapse() },
            "look-text" to Scene(listOf("P0", "فراخوانی")) { Texts() },
            // ------------------------------------------------------------------ C2.1 the command
            "look-command-button" to Scene(listOf("نوبت تو")) {
                Box(Modifier.fillMaxSize()) {
                    com.coinepro.hq.ui.office.OfficeScreen()
                    CommandButton({}, Modifier.align(Alignment.BottomEnd).padding(16.dp))
                }
            },
            "look-command" to Scene(listOf(COMMAND_FA, "برای کدام شرکت؟", "باز کن")) { Command(CommandState()) },
            "look-command-ready" to Scene(listOf("باز کن", "خودکار")) {
                Command(CommandState(CommandOpen(text = WORDS)).apply { picked = listOf("TY", "PC"); pace = "auto"; template = COMMAND_TEMPLATES.first() })
            },
            "look-command-refused" to Scene(listOf("ستاد الان جواب نمیدهد")) {
                Command(CommandState(CommandOpen(text = WORDS)).apply { picked = listOf("TY", "PC"); pace = "step"; error = "ستاد الان جواب نمیدهد؛ کمی بعد دوباره بزن." })
            },
            "look-command-routine" to Scene(listOf(ROUTINE_TEMPLATE_FA, "بساز", "برگرد")) {
                Command(CommandState(mode0 = CommandMode.ROUTINE).apply { sentence = "هر روز ساعت ۹ رتبه‌های سئوی سایت را ببین و خلاصه بده"; one = "PC" })
            },
            "look-command-made" to Scene(listOf("نوبت بعد", "باشه")) {
                Command(CommandState(mode0 = CommandMode.MADE).apply {
                    made = SessionRoutine(
                        "AT-0903", "PC", "هر روز ساعت ۹ رتبه‌های سئوی سایت را ببین و خلاصه بده", "هر روز ساعت 09:00",
                        "یک کار تازه برای «کارشناس سئوی پرو-چارت» با عنوان «رتبه‌های سئوی سایت را ببین و خلاصه بده» ساخته میشود", "on",
                        nextAt = "2026-10-18T05:30:00Z",
                    )
                })
            },
            // ------------------------------------------------------------------ C3.1 a home with nothing waiting, the pulse without a series
            "look-home-quiet" to Scene(listOf("چیزی منتظر تو نیست"), before = { LookDemo.series = false }) {
                Cardlike {
                    TurnRow(Office())
                    com.coinepro.hq.ui.live.OfficePulse(waiting = 0)
                    com.coinepro.hq.ui.look.CommandRow()
                }
            },
            // ------------------------------------------------------------------ C3.5 one level of the notifications
            "look-notifications-decision" to Scene(listOf("از تو کاری میخواهد")) { com.coinepro.hq.ui.notifications.NotificationsScreen(level0 = "decision") },
            // ------------------------------------------------------------------ C3.6 the limits, in every state
            "look-limits" to Scene(listOf("اکانت اصلی", "الان همین کار میکند", "کنتور امروز")) { Limits() },
            "look-limits-both-full" to Scene(listOf("هر دو اکانت پر است", "نزدیک سقف"), before = { LookDemo.limits = "both-full" }) { Limits() },
            "look-limits-warm" to Scene(listOf("پر است", "از ۷۰٪ گذشت"), before = { LookDemo.limits = "warm" }) { Limits() },
            "look-limits-near" to Scene(listOf("خاموش", "نزدیک سقف"), before = { LookDemo.limits = "near" }) { Limits() },
            "look-limits-full-day" to Scene(listOf("سقف پر شد"), before = { LookDemo.limits = "full-day" }) { Limits() },
            "look-limits-unknown" to Scene(listOf("هنوز خوانده نشده"), before = { LookDemo.limits = "unknown" }) { Limits() },
            // A hub before §55: no limits block, the older quota card stays.
            "look-treasury-old-hub" to Scene(listOf("سهمیه‌ی اشتراک"), before = { LookDemo.limits = "old" }) { com.coinepro.hq.ui.treasury.TreasuryScreen() },
        )

        @JvmStatic
        @ParameterizedRobolectricTestRunner.Parameters(name = "{0}-{1}")
        fun params(): List<Array<Any>> = SCREENS.keys.flatMap { listOf(arrayOf<Any>(it, true), arrayOf<Any>(it, false)) }

        @Composable
        private fun Cardlike(content: @Composable () -> Unit) {
            Column(
                Modifier.fillMaxSize().background(Divan.colors.page).verticalScroll(rememberScrollState()).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) { content() }
        }

        /** The command sheet over a dimmed page, as tall as what it holds. */
        @Composable
        private fun Command(state: CommandState) {
            val s = remember { state }
            val companies = rememberCompanies().filter { it.kind != "holding" }
            SpringSheetPreview(
                if (s.mode == CommandMode.ORDER) COMMAND_FA else ROUTINE_TEMPLATE_FA,
                sub = if (s.mode == CommandMode.ROUTINE) "یک جمله بنویس که چه کاری، هر چند وقت یک بار." else null,
                bar = { CommandDecisionBar(s, companies, {}, {}, {}) },
                fill = true,
            ) { CommandFields(s, companies, routineOn = true) }
        }

        @Composable
        private fun Limits() {
            val q = rememberQuery("treasury:limits", "treasury") { limits() }
            Cardlike { LimitsBlock(q.data, flying = true) }
        }

        /** The decision bar: in a sheet (idle with its line and a quiet action, working, done, refused) and on a page. */
        @Composable
        private fun Bars() {
            Column(Modifier.fillMaxSize().background(Divan.colors.page).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                DecisionBar("تأیید و انتشار", {}, context = "ریلز «سه اشتباه رایج در حد ضرر» در @tradeyar، امشب 21:00", quiet = listOf(QuietAction("اصلاح") {}, QuietAction("بعداً") {}))
                DecisionBar("انتشار", {}, context = "در حال فرستادن به اینستاگرام", state = DecisionState.WORKING, quiet = listOf(QuietAction("اصلاح") {}))
                DecisionBar("انتشار", {}, state = DecisionState.DONE)
                DecisionBar("باز کن", {}, error = "ستاد الان جواب نمیدهد؛ کمی بعد دوباره بزن.")
                DecisionBar("مُهر کارگروه", {}, context = "۳ جایگاه · ۲ روال · ۱ اتصال", enabled = false)
                DecisionBar("تأیید و انتشار", {}, context = "خروجی آماده است؛ با یک لمس منتشر میشود.", quiet = listOf(QuietAction("اصلاح") {}), place = DecisionPlace.PAGE)
            }
        }

        /** The ring: a share, an unknown one, a full one, one that is off, the build ring of a turn, a deadline; and the tiny line. */
        @Composable
        private fun Rings() {
            val c = Divan.colors
            Cardlike {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceAround) {
                    Ring(0.62f, live = true, label = "۶۲ درصد") { Fig("62%", style = Divan.type.figureM) }
                    Ring(null) { Fig("—", style = Divan.type.figureM, color = c.textMuted) }
                    Ring(1f, tone = RingTone.NEAR) { Fig("100%", style = Divan.type.figureM) }
                    Ring(null, tone = RingTone.MUTED, broken = true) { Fig("—", style = Divan.type.figureM, color = c.textMuted) }
                }
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceAround, verticalAlignment = Alignment.CenterVertically) {
                    Ring(23f / 60f, size = 92.dp, stroke = 6.dp, live = true) {
                        Text("۲۳", style = Divan.type.h2)
                        Text("از ۶۰ دقیقه", style = Divan.type.micro, color = c.textMuted)
                    }
                    Ring(0.93f, size = 92.dp, stroke = 6.dp, tone = RingTone.WARN) {
                        Text("۵۶", style = Divan.type.h2)
                        Text("از ۶۰ دقیقه", style = Divan.type.micro, color = c.textMuted)
                    }
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Ring(0.15f, size = 18.dp, stroke = 2.5.dp, tone = RingTone.NEG)
                        Text("۶ ساعت مانده", style = Divan.type.micro, color = c.textSecondary)
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(24.dp), verticalAlignment = Alignment.CenterVertically) {
                    Spark(listOf(2.0, 3.0, 3.0, 5.0, 4.0, 6.0, 7.0, 6.0, 8.0))
                    Spark(listOf(1.0, 1.0, 2.0, 4.0, 7.0, 9.0, 12.0), gold = true)
                    Spark(listOf(4.0, 4.0, 4.0))
                }
            }
        }

        /** The header that folds to one line: open, half way, folded. */
        @Composable
        private fun Collapse() {
            val c = Divan.colors
            Cardlike {
                for (f in listOf(0f, 0.5f, 1f)) Box(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.card).padding(14.dp)) {
                    CollapsingHeader(
                        { f },
                        line = { Facts("ریلز هفته‌ی آموزش طلا", "کار ۳ از ۴", "با من", style = Divan.type.small, color = c.textPrimary) },
                        full = {
                            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                Text("ریلز هفته‌ی آموزش طلا", style = Divan.type.h2)
                                Text("مدیرعامل تریدیار؛ کار ۳ از ۴؛ با من", style = Divan.type.caption, color = c.textSecondary)
                                Text("برای تریدیار هفته‌ی آموزش طلا را راه بینداز؛ مرحله به مرحله با من جلو برو.", style = Divan.type.small, color = c.textSecondary)
                            }
                        },
                    )
                }
            }
        }

        /** The text rules: one Latin token is one run, «·» is the hairline, an amount shrinks instead of being cut. */
        @Composable
        private fun Texts() {
            val c = Divan.colors
            Cardlike {
                HqCard(Modifier.fillMaxWidth()) {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("فقط کارهای اضطراری (P0) اجرا میشوند.", style = Divan.type.small)
                        Text(com.coinepro.hq.ui.v14.figs("فقط کارهای اضطراری (P0) اجرا میشوند."), style = Divan.type.small)
                        Text("اثر این کارت: +640 USDT/ماه، هزینه‌اش -18 USD/ماه", style = Divan.type.small)
                        Text("کمیسیون دیروز تریدیار 94.60 USDT بود، خروجی O-000152 را ببین.", style = Divan.type.small)
                        Text("مدیرعامل تریدیار · ۱ مدل · ۲ از ۴ کار · ۶۰ دقیقه پیش", style = Divan.type.caption, color = c.textMuted)
                        Facts("اینستاگرام", "@tradeyar", "امشب 21:30", "21% از سقف")
                        Text("ChatGPT Plus: 41 فراخوانی این ماه، معادل $12.40", style = Divan.type.caption, color = c.textSecondary)
                    }
                }
                // A tile narrower than its figure: the figure shrinks to fit, it is never cut with «…».
                StatRow {
                    StatTile("کسری کمیسیون", "−$1,284,650.75", Modifier.weight(1f), sub = "باید میرسید")
                    StatTile("خرج تبلیغ", "$98,412,300.00", Modifier.weight(1f), sub = "این ماه")
                    StatTile("رسید", "$7.20", Modifier.weight(1f), sub = "امروز")
                }
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.width(96.dp).clip(RoundedCornerShape(10.dp)).background(c.card).padding(8.dp)) { Amount("412K / 600K", style = Divan.type.figureL) }
                    Box(Modifier.width(72.dp).clip(RoundedCornerShape(10.dp)).background(c.card).padding(8.dp)) { Amount("$1,284,650,112,904.75", style = Divan.type.figureL) }
                    Box(Modifier.width(120.dp).clip(RoundedCornerShape(10.dp)).background(c.card).padding(8.dp)) { Fig("sha256:9f2c7a1be04d55aa01c3", style = Divan.type.figure) }
                }
            }
        }
    }

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private lateinit var graph: AppGraph

    @Before
    fun setUp() {
        com.coinepro.hq.core.format.HqClock.fixed = java.time.Instant.parse("2026-10-17T08:30:00Z")
        LookDemo.reset()
        SCREENS.getValue(name).before()
        graph = (ApplicationProvider.getApplicationContext<HqApp>()).graph
        graph.link.setForeground(false)
        graph.enterDemo()
        DemoLive.servers?.still = true
    }

    @After
    fun tearDown() = LookDemo.reset()

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
                    Box(Modifier.fillMaxSize().background(Divan.colors.page)) { scene.content() }
                }
            }
        }
        // Demo answers take ~60–150 ms each on OkHttp threads; let them land and the UI settle (a fitted figure takes a pass or two).
        repeat(16) {
            Thread.sleep(200)
            shadowOf(Looper.getMainLooper()).idle()
            compose.mainClock.advanceTimeBy(250)
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
