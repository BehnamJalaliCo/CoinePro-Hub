package com.coinepro.hq

import android.os.Looper
import androidx.activity.ComponentActivity
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.hasSetTextAction
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.swipeDown
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
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.ParameterizedRobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * ⟨0.17.0⟩ The session as the owner holds it, at a phone's height (860dp), night and day, with the demo holding.
 * ⟨1.0.1⟩ Part C (C2.2): the one-line header (the short title, «کار n از m», the pace, the mood light) over the plan's line of
 * parts; the chat opened at its newest word with the steps as thin centred lines; the holder's question in ONE place, the «منتظر تو»
 * card over the composer with its ready answers; a long Persian draft across the whole width of the composer (six lines, then it
 * scrolls; «بفرست» in place of the mic); the chat scrolled up with the round «↓»; and a session ready for his OK with «تأیید و بستن»
 * in the decision bar (the page's one full gold). The «جزئیات» sheet is drawn whole in [SessionScreensTest].
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h860dp-xxhdpi")
class SessionChatScreensTest(private val name: String, private val night: Boolean) {
    private enum class Then { NOTHING, TYPE, SCROLL_UP }

    /** A screen, and what the owner does on it before it is drawn. */
    private class Scene(val then: Then, val content: @Composable () -> Unit)

    companion object {
        /** A long draft, as the owner writes one: it must read as prose across the composer, not two words a line. */
        private const val DRAFT = "ریلزها را اول منتشر کن، ولی پیش از انتشار متن هر سه را یک بار دیگر با جی‌پی‌تی بخوان و اگر جایی عدد پیوت هفته‌ی قبل " +
            "نیامده، اضافه‌اش کن. پست‌های کانال را فردا صبح بگذار، ساعت ده، و برای هر پست یک تصویر از چارت طلا با فونت تیتر کاور بساز. " +
            "اگر مدیر رسانه وقت ندارد، به من بگو تا یک نفر دیگر را بیاوریم؛ نمیخواهم هفته‌ی آموزش طلا عقب بیفتد. گزارش بازده تبلیغ را هم " +
            "آخر هفته با عدد بفرست، کوتاه و ساده، که بدانم کدام ریلز بهتر دیده شد."

        private val SCREENS: Map<String, Scene> = linkedMapOf(
            // The owner's turn: opened at the newest word (the CEO's question), the steps of the work as quiet lines in between.
            "session-chat-your-turn" to Scene(Then.NOTHING) { com.coinepro.hq.ui.session.OrderSessionScreen("F-0101") },
            // A long draft: the words across the whole composer, the actions in one row under them, «بفرست» instead of the mic.
            "session-chat-draft" to Scene(Then.TYPE) { com.coinepro.hq.ui.session.OrderSessionScreen("F-0101") },
            // Scrolled up to read: nothing moves under his finger, and «↓» takes him back to the end.
            "session-chat-scrolled-up" to Scene(Then.SCROLL_UP) { com.coinepro.hq.ui.session.OrderSessionScreen("F-0101") },
            // Ready for his OK: the result where it arrived, «تأیید و بستن» and the quiet «اصلاح» in the decision bar.
            "session-chat-ready" to Scene(Then.NOTHING) { com.coinepro.hq.ui.session.OrderSessionScreen("F-0102") },
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
        // ⟨1.0.1⟩ the files of a session and of an output are drawn as they are (their pictures and posters)
        picturesOn()
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

    @org.junit.After
    fun tearDown() = picturesOff()

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
        // The report, then the session's talk and the personas: each a demo answer of ~60–150 ms on OkHttp threads. Let them land.
        settle(20)
        when (scene.then) {
            Then.NOTHING -> Unit
            Then.TYPE -> compose.onNode(hasSetTextAction()).performTextInput(DRAFT)
            // from the middle of the thread (its top lies under the session's header)
            Then.SCROLL_UP -> compose.onNodeWithTag("session-chat").performTouchInput { swipeDown(startY = height * 0.35f, endY = height * 0.95f) }
        }
        settle(6)
        compose.onRoot().captureRoboImage(
            "src/test/screenshots/$name-${if (night) "night" else "day"}.png",
            roborazziOptions = RoborazziOptions(
                recordOptions = RoborazziOptions.RecordOptions(resizeScale = 0.5),
                compareOptions = RoborazziOptions.CompareOptions(changeThreshold = 0.002f),
            ),
        )
    }
}
