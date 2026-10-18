package com.coinepro.hq

import androidx.activity.ComponentActivity
import androidx.compose.foundation.background
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onRoot
import androidx.test.core.app.ApplicationProvider
import com.coinepro.hq.core.AppGraph
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.DivanTheme
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Nav
import com.coinepro.hq.ui.Toasts
import com.coinepro.hq.ui.academy.AcademyScreen
import com.coinepro.hq.ui.advisor.InquiriesAction
import com.coinepro.hq.ui.assistant.AssistantScreen
import com.coinepro.hq.ui.audit.AuditScreen
import com.coinepro.hq.ui.founding.FoundingScreen
import com.coinepro.hq.ui.founding.FoundingsScreen
import com.coinepro.hq.ui.oversight.OversightScreen
import com.coinepro.hq.ui.skills.SkillsScreen
import com.coinepro.hq.ui.stars.StarsScreen
import com.coinepro.hq.ui.tools.ToolsScreen
import com.coinepro.hq.ui.cartable.CartableScreen
import com.coinepro.hq.ui.cartable.DecisionScreen
import com.coinepro.hq.ui.companies.CompaniesScreen
import com.coinepro.hq.ui.companies.CompanyScreen
import com.coinepro.hq.ui.companies.EmployeeScreen
import com.coinepro.hq.ui.companies.WorkScreen
import com.coinepro.hq.ui.control.ControlScreen
import com.coinepro.hq.ui.home.HomeScreen
import com.coinepro.hq.ui.messages.ChatScreen
import com.coinepro.hq.ui.messages.ThreadsScreen
import com.coinepro.hq.ui.notifications.NotificationsScreen
import com.coinepro.hq.ui.outputs.OutputScreen
import com.coinepro.hq.ui.outputs.OutputsScreen
import com.coinepro.hq.ui.planner.PlannerScreen
import com.coinepro.hq.ui.settings.HireForm
import com.coinepro.hq.ui.stories.StoryPreview
import com.coinepro.hq.ui.settings.SettingsScreen
import com.coinepro.hq.ui.treasury.TreasuryScreen
import com.coinepro.hq.ui.workshop.SessionScreen
import com.coinepro.hq.ui.workshop.WorkshopScreen
import com.github.takahirom.roborazzi.RoborazziOptions
import com.github.takahirom.roborazzi.captureRoboImage
import android.os.Looper
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import org.robolectric.ParameterizedRobolectricTestRunner
import org.robolectric.Shadows.shadowOf

/** Renders every screen with the demo holding (the same fixtures as the web) in both themes. The images
 *  (src/test/screenshots) are how a change to the design is reviewed; `recordRoborazziDebug` refreshes them. */
@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h880dp-xxhdpi")
class ScreensTest(private val name: String, private val night: Boolean) {

    companion object {
        @JvmStatic
        @ParameterizedRobolectricTestRunner.Parameters(name = "{0}-{1}")
        fun params(): List<Array<Any>> = SCREENS.keys.flatMap { listOf(arrayOf<Any>(it, true), arrayOf<Any>(it, false)) }

        private val SCREENS: Map<String, @Composable (AppGraph) -> Unit> = linkedMapOf(
            "home" to { _ -> HomeScreen(onNewOrder = {}) },
            "cartable" to { _ -> CartableScreen() },
            "decision-hire" to { _ -> DecisionScreen("D-000014") },
            "decision-deploy" to { _ -> DecisionScreen("D-000017") },
            "decision-sealed" to { _ -> DecisionScreen("D-000011") },
            "outputs" to { _ -> OutputsScreen() },
            "output" to { _ -> OutputScreen("O-000029") },
            "chat-media" to { _ -> ChatScreen("FX-CEO") },
            "threads" to { _ -> ThreadsScreen() },
            "companies" to { _ -> CompaniesScreen() },
            "company" to { _ -> CompanyScreen("FX") },
            "employee" to { _ -> EmployeeScreen("TY-GROWTH-01") },
            "work" to { _ -> WorkScreen("w0") },
            "treasury" to { _ -> TreasuryScreen() },
            "planner" to { _ -> PlannerScreen(onNewOrder = {}) },
            "control" to { _ -> ControlScreen() },
            "notifications" to { _ -> NotificationsScreen() },
            "audit" to { _ -> AuditScreen() },
            "settings" to { g -> SettingsScreen(g) },
            "workshop" to { _ -> WorkshopScreen(onNewSession = {}, onGrant = {}) },
            "session-approval" to { _ -> SessionScreen("S-0004") },
            "session-done" to { _ -> SessionScreen("S-0002") },
            // ⟨1.4⟩
            "oversight" to { _ -> OversightScreen() },
            "overseer-chat" to { _ -> ChatScreen("N", agent = "overseer") },
            "assistant" to { _ -> AssistantScreen() },
            "advisor" to { _ -> ChatScreen("A", advisor = true, headerAction = { InquiriesAction() }) },
            "stars" to { _ -> StarsScreen() },
            "skills" to { _ -> SkillsScreen() },
            "academy" to { _ -> AcademyScreen() },
            "foundings" to { _ -> FoundingsScreen() },
            "founding-proposed" to { _ -> FoundingScreen("C-0002") },
            "founding-ready" to { _ -> FoundingScreen("C-0001") },
            "tools" to { _ -> ToolsScreen() },
            // ⟨1.4.2⟩ the owner's own hire, filled in (the sheet's content)
            // ⟨1.4.3⟩ a hire story (welcome / dismiss) and a CEO's milestone
            "story-hire" to { _ -> StoryPreview("FX") },
            "story-stars" to { _ -> StoryPreview("TY") },
            "hire" to { _ -> HireForm(onDone = {}, modifier = Modifier.verticalScroll(rememberScrollState()), company0 = "TY", department0 = "TECH", role0 = "sre") },
            // ⟨1.4.4⟩ the owner's tools on existing APIs
            "resolutions" to { _ -> com.coinepro.hq.ui.owner.ResolutionsScreen() },
            "runs" to { _ -> com.coinepro.hq.ui.owner.RunsScreen() },
            "sites" to { _ -> com.coinepro.hq.ui.owner.SitesScreen() },
            "employee-manager" to { _ -> EmployeeScreen("FX-TECH-MGR") },
        )
    }

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private lateinit var graph: AppGraph

    @Before
    fun setUp() {
        // One fixed instant: the demo's relative times, Jalali dates and the planner's week are the same on any day,
        // so CI can compare the images with the recorded ones (the visual gate).
        com.coinepro.hq.core.format.HqClock.fixed = java.time.Instant.parse("2026-10-17T08:30:00Z")
        graph = (ApplicationProvider.getApplicationContext<HqApp>()).graph
        graph.enterDemo()
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
                CompositionLocalProvider(LocalEnv provides graph.env.value, LocalToasts provides Toasts(), LocalNav provides nav) {
                    Box(Modifier.fillMaxSize().background(Divan.colors.page)) { SCREENS.getValue(name)(graph) }
                }
            }
        }
        // Demo responses take ~150 ms each on OkHttp threads; let them land and the UI settle.
        repeat(14) {
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
