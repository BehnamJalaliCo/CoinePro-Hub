package com.coinepro.hq

import androidx.activity.ComponentActivity
import androidx.compose.animation.AnimatedContent
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.assertHeightIsEqualTo
import androidx.compose.ui.test.assertWidthIsEqualTo
import androidx.compose.ui.test.getUnclippedBoundsInRoot
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.unit.dp
import com.coinepro.hq.designsystem.CollapsingHeader
import com.coinepro.hq.designsystem.ContinuityHost
import com.coinepro.hq.designsystem.ContinuityPage
import com.coinepro.hq.designsystem.DecisionBar
import com.coinepro.hq.designsystem.DecisionPage
import com.coinepro.hq.designsystem.DecisionPlace
import com.coinepro.hq.designsystem.DecisionState
import com.coinepro.hq.designsystem.DivanTheme
import com.coinepro.hq.designsystem.FitText
import com.coinepro.hq.designsystem.LocalPageDock
import com.coinepro.hq.designsystem.LocalReducedMotion
import com.coinepro.hq.designsystem.PageDock
import com.coinepro.hq.designsystem.QuietAction
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.continuity
import com.coinepro.hq.designsystem.rememberHaptics
import com.coinepro.hq.designsystem.stagger
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * ⟨1.0.1⟩ Part C, the motion of the shared pieces (C0.2, C0.3), run for real on the test clock: a plain `clickable` answers the touch
 * through the theme's indication and still clicks (M16); a card and the head it opens into are one thing while the page changes, and
 * nothing travels when animations are removed (M14); a header folds with its fraction (M18); rows settle in steps (M17); the decision
 * bar works, is done and leaves; a figure wider than its box shrinks instead of being cut (C0.4).
 */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h880dp-xxhdpi")
class LookMotionTest {
    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    @Test
    fun aPlainClickableSinksUnderTheFingerAndStillClicks() {
        var clicks = 0
        compose.setContent { DivanTheme(true, reducedMotion = false) { Box(Modifier.size(120.dp).testTag("row").clickable { clicks++ }) { Text("ردیف") } } }
        // Held down: the indication's own node draws the row (its ripple and its 2 % sink) without a crash; released: one click.
        compose.onNodeWithTag("row").performTouchInput { down(center) }
        compose.mainClock.advanceTimeBy(200)
        compose.onNodeWithText("ردیف").assertExists()
        compose.onNodeWithTag("row").performTouchInput { up() }
        compose.waitForIdle()
        assertEquals(1, clicks)
        compose.onNodeWithTag("row").performClick()
        assertEquals(2, clicks)
    }

    @Test
    fun aCardGrowsIntoThePageItOpens() {
        var page by mutableIntStateOf(0)
        compose.mainClock.autoAdvance = false
        compose.setContent {
            DivanTheme(true, reducedMotion = false) {
                ContinuityHost {
                    AnimatedContent(page, label = "pages") { p ->
                        ContinuityPage(this) {
                            if (p == 0) Box(Modifier.width(120.dp).height(60.dp).continuity("session/F-1").testTag("card")) { Text("کارت") }
                            else Box(Modifier.fillMaxWidth().height(200.dp).continuity("session/F-1").testTag("head")) { Text("سربرگ") }
                        }
                    }
                }
            }
        }
        compose.mainClock.advanceTimeBy(500)
        compose.onNodeWithTag("card").assertWidthIsEqualTo(120.dp)
        compose.runOnUiThread { page = 1 }
        // The page changes inside the shared scope without a fault, and settles: the head at its own size, the card gone.
        repeat(30) { compose.waitForIdle(); compose.mainClock.advanceTimeBy(100) }
        compose.waitForIdle()
        compose.onNodeWithTag("head").assertWidthIsEqualTo(400.dp).assertHeightIsEqualTo(200.dp)
        compose.onNodeWithTag("card").assertDoesNotExist()
    }

    @Test
    fun nothingTravelsWhenAnimationsAreRemoved() {
        var page by mutableIntStateOf(0)
        compose.setContent {
            DivanTheme(true, reducedMotion = true) {
                ContinuityHost {
                    // No shared scope at all: the modifier is a no-op, the page simply opens.
                    if (page == 0) Box(Modifier.width(120.dp).height(60.dp).continuity("session/F-1").stagger(3).testTag("card"))
                    else Box(Modifier.fillMaxWidth().height(200.dp).continuity("session/F-1").testTag("head"))
                }
            }
        }
        compose.onNodeWithTag("card").assertWidthIsEqualTo(120.dp)
        page = 1
        compose.onNodeWithTag("head").assertWidthIsEqualTo(400.dp)
    }

    @Test
    fun aHeaderFoldsToOneLineWithItsFraction() {
        var f by mutableFloatStateOf(0f)
        compose.setContent {
            DivanTheme(true) {
                CollapsingHeader({ f }, Modifier.testTag("header"), line = { Box(Modifier.fillMaxWidth().height(40.dp)) }, full = { Box(Modifier.fillMaxWidth().height(160.dp)) })
            }
        }
        compose.onNodeWithTag("header").assertHeightIsEqualTo(160.dp)
        f = 0.5f
        compose.onNodeWithTag("header").assertHeightIsEqualTo(100.dp)
        f = 1f
        compose.onNodeWithTag("header").assertHeightIsEqualTo(40.dp)
    }

    @Test
    fun rowsSettleInSteps() {
        compose.mainClock.autoAdvance = false
        compose.setContent {
            DivanTheme(true, reducedMotion = false) { Column { repeat(10) { i -> Box(Modifier.fillMaxWidth().height(20.dp).stagger(i).testTag("r$i")) } } }
        }
        // Every row has its place from the first frame (the motion lives in the layer); after the steps all have settled.
        compose.mainClock.advanceTimeBy(16)
        compose.onNodeWithTag("r0").assertHeightIsEqualTo(20.dp)
        compose.onNodeWithTag("r9").assertHeightIsEqualTo(20.dp)
        compose.mainClock.advanceTimeBy(1_000)
        assertEquals(180.dp, compose.onNodeWithTag("r9").getUnclippedBoundsInRoot().top)
    }

    @Test
    fun theDecisionBarWorksIsDoneAndLeaves() {
        var state by mutableStateOf(DecisionState.IDLE)
        var taps = 0
        var quiet = 0
        var left = false
        val dock = PageDock()
        compose.mainClock.autoAdvance = false
        compose.setContent {
            DivanTheme(true) {
                CompositionLocalProvider(LocalReducedMotion provides true, LocalPageDock provides dock) {
                    DecisionPage(bar = {
                        DecisionBar(
                            "تأیید و انتشار", { taps++ }, context = "ریلز آماده است", quiet = listOf(QuietAction("اصلاح") { quiet++ }),
                            state = state, onLeft = { left = true }, place = DecisionPlace.PAGE,
                        )
                    }) { Box(Modifier.fillMaxWidth().testTag("page")) { val h = rememberHaptics(); Text("صفحه", Modifier.clickable { h.tick(); h.seal(); h.error() }) } }
                }
            }
        }
        compose.mainClock.advanceTimeBy(100)
        compose.onNodeWithText("تأیید و انتشار").performClick()
        compose.onNodeWithText("اصلاح").performClick()
        compose.onNodeWithText("صفحه").performClick()
        compose.mainClock.advanceTimeBy(100)
        assertEquals(1, taps)
        assertEquals(1, quiet)
        // The page gives the bar its own room and says how tall it is (the shell lifts the command button above it).
        assertTrue(dock.barHeight > 0)
        // Working: the primary takes no tap. Done: the tick, then the bar leaves.
        state = DecisionState.WORKING
        compose.mainClock.advanceTimeBy(100)
        compose.onNodeWithText("تأیید و انتشار").performClick()
        compose.mainClock.advanceTimeBy(100)
        assertEquals(1, taps)
        state = DecisionState.DONE
        compose.mainClock.advanceTimeBy(100)
        compose.onNodeWithText("انجام شد").assertExists()
        assertFalse(left)
        compose.mainClock.advanceTimeBy(1_200)
        assertTrue(left)
    }

    @Test
    fun aFigureWiderThanItsBoxShrinksInsteadOfBeingCut() {
        compose.mainClock.autoAdvance = false
        compose.setContent { DivanTheme(true) { Box(Modifier.width(96.dp)) { FitText("412K / 600K / 900K", Modifier.testTag("fig"), style = com.coinepro.hq.designsystem.Divan.type.figureL) } } }
        repeat(6) { compose.mainClock.advanceTimeBy(100) }
        val out = mutableListOf<androidx.compose.ui.text.TextLayoutResult>()
        compose.onNodeWithTag("fig").fetchSemanticsNode().config[androidx.compose.ui.semantics.SemanticsActions.GetTextLayoutResult].action?.invoke(out)
        val r = out.single()
        // It fits its 96 dp: nothing overflows, and nothing was replaced by «…».
        assertFalse(r.hasVisualOverflow)
        assertTrue(r.size.width <= 96 * 3)
        assertFalse(r.isLineEllipsized(r.lineCount - 1))
    }
}
