package com.coinepro.hq

import android.os.Looper
import androidx.activity.ComponentActivity
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.hasScrollToIndexAction
import androidx.compose.ui.test.hasSetTextAction
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToKey
import androidx.compose.ui.test.performTextInput
import androidx.test.core.app.ApplicationProvider
import com.coinepro.hq.core.AppGraph
import com.coinepro.hq.core.data.PLAYBOOK_KEPT_FA
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.DivanTheme
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Nav
import com.coinepro.hq.ui.Toasts
import com.coinepro.hq.ui.look.PublishDeskScreen
import com.coinepro.hq.ui.session.OrderSessionScreen
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
 * ⟨1.36⟩ §58 at a phone's height, night and day, with the demo holding:
 * - room to write (§58.1): TradeYar's reels session (F-0096) waits on a long question: three lines, «بیشتر» and the chip of its newest
 *   output; «بیشتر» opened in place (scrolling inside itself); and the owner writing a long answer: the card folded to its first line,
 *   the composer five lines tall over the thread;
 * - a closed session that left its working group in the library (§58.2), at the end of its thread;
 * - the publish desk's «منتشرشده» (§58.5's channel tab, §58.4's «بایگانی شد · … آزاد شد» on a swept card).
 * Each is checked to show its words (and not to show what it must not) before it is drawn.
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h880dp-xxhdpi")
class RoomScreensTest(private val name: String, private val night: Boolean) {
    private enum class Then { NOTHING, MORE, WRITE, DONE }

    private class Scene(val shows: List<String>, val hides: List<String> = emptyList(), val then: Then = Then.NOTHING, val content: @Composable () -> Unit)

    companion object {
        /** The owner's long answer, as he writes one. */
        private const val DRAFT = "با سؤال شروع کن، ولی عدد ۸۰٪ را در ثانیه‌ی دوم روی تصویر بیاور. زیرنویس کامل باشد چون خیلی‌ها بی‌صدا میبینند. " +
            "آخر ریلز دعوت به دنبال کردن صفحه باشد، کانال تلگرام را در کپشن بگذار. صدای گوینده خوب است ولی برش‌ها را کمی تندتر کن، " +
            "مخصوصاً وسط ریلز که مثال نمودار طلا می‌آید؛ آنجا کمی طولانی است. نسخه‌ی دوم را که ساختی همین‌جا بگذار تا ببینم."

        private val SCREENS: Map<String, Scene> = linkedMapOf(
            "room-question" to Scene(listOf("مدیر رسانه‌ی تریدیار میپرسد", "بیشتر", "خروجی آخر:", "حد ضرر را کجا بگذاریم", "خودت تصمیم بگیر"), hides = listOf("کمتر")) {
                OrderSessionScreen("F-0096")
            },
            "room-question-open" to Scene(listOf("کمتر", "اگر روی صدای گوینده", "خروجی آخر:"), hides = listOf("بیشتر"), then = Then.MORE) { OrderSessionScreen("F-0096") },
            "room-writing" to Scene(listOf("مدیر رسانه‌ی تریدیار میپرسد", "خروجی آخر:", "برش‌ها را کمی تندتر کن"), hides = listOf("بیشتر", "خودت تصمیم بگیر"), then = Then.WRITE) {
                OrderSessionScreen("F-0096")
            },
            "room-closed-kept" to Scene(listOf("این جلسه تأیید و بایگانی شد", PLAYBOOK_KEPT_FA)) { OrderSessionScreen("F-0093") },
            "room-desk-done" to Scene(listOf("اینستاگرام", "منتشرشده", "بایگانی شد", "آزاد شد"), then = Then.DONE) { PublishDeskScreen() },
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
        picturesOn()
        LookDemo.reset()
        graph = (ApplicationProvider.getApplicationContext<HqApp>()).graph
        graph.link.setForeground(false)
        graph.enterDemo()
        DemoLive.servers?.still = true
    }

    @After
    fun tearDown() {
        LookDemo.reset()
        picturesOff()
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
                    Box(Modifier.fillMaxSize().background(Divan.colors.page)) { scene.content() }
                }
            }
        }
        settle(22)
        when (scene.then) {
            Then.NOTHING -> Unit
            Then.MORE -> compose.onNodeWithText("بیشتر").performClick()
            Then.WRITE -> compose.onNode(hasSetTextAction()).performTextInput(DRAFT)
            Then.DONE -> compose.onNode(hasScrollToIndexAction()).performScrollToKey("h-done")
        }
        if (scene.then != Then.NOTHING) settle(8)
        if (scene.then == Then.WRITE) assertTrue("$name: the card folds while he writes", compose.onAllNodesWithTag("waiting-folded").fetchSemanticsNodes().isNotEmpty())
        for (t in scene.shows) assertTrue("$name shows «$t»", compose.onAllNodesWithText(t, substring = true).fetchSemanticsNodes().isNotEmpty())
        for (t in scene.hides) assertTrue("$name never shows «$t»", compose.onAllNodesWithText(t, substring = true).fetchSemanticsNodes().isEmpty())
        compose.onRoot().captureRoboImage(
            "src/test/screenshots/$name-${if (night) "night" else "day"}.png",
            roborazziOptions = RoborazziOptions(
                recordOptions = RoborazziOptions.RecordOptions(resizeScale = 0.5),
                compareOptions = RoborazziOptions.CompareOptions(changeThreshold = 0.002f),
            ),
        )
    }
}
