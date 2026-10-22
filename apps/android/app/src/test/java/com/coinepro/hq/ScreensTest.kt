package com.coinepro.hq

import androidx.activity.ComponentActivity
import androidx.compose.foundation.background
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.ui.unit.dp
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.hasScrollToIndexAction
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performScrollToIndex
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
            "advisor" to { _ -> com.coinepro.hq.ui.advisor.AdvisorScreen() },
            "stars" to { _ -> StarsScreen() },
            "skills" to { _ -> SkillsScreen() },
            "academy" to { _ -> AcademyScreen() },
            "foundings" to { _ -> FoundingsScreen() },
            "founding-proposed" to { _ -> FoundingScreen("C-0002") },
            "founding-ready" to { _ -> FoundingScreen("C-0001") },
            "founding-plan" to { _ -> FoundingScreen("PV-0003") },
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
            // ⟨1.4.6⟩ a company's brand and seal: the active version in every size, both themes, the seal ready and sealed
            "company-brand" to { _ -> CompanyScreen("FX", tab0 = "brand") },
            // ⟨1.5⟩ revenue and support (§19): the radar and its lower sections, the desk's five tabs, a conversation whose draft the
            // guard refused, growth's three tabs, the feedback inbox, the three cards and the intake on the tools screen
            "revenue" to { _ -> com.coinepro.hq.ui.revenue.RevenueScreen() },
            "revenue-funnel" to { _ -> com.coinepro.hq.ui.revenue.RevenueScreen() },
            "revenue-accounts" to { _ -> com.coinepro.hq.ui.revenue.RevenueScreen() },
            "revenue-rescue" to { _ -> com.coinepro.hq.ui.revenue.RevenueScreen() },
            "support" to { _ -> com.coinepro.hq.ui.support.SupportScreen() },
            "support-conversations" to { _ -> com.coinepro.hq.ui.support.SupportScreen("conversations") },
            "support-channels" to { _ -> com.coinepro.hq.ui.support.SupportScreen("channels") },
            "support-knowledge" to { _ -> com.coinepro.hq.ui.support.SupportScreen("kb") },
            "support-shadow" to { _ -> com.coinepro.hq.ui.support.SupportScreen("shadow") },
            "conversation-blocked" to { _ -> com.coinepro.hq.ui.support.ConversationScreen("SC-000411") },
            "growth" to { _ -> com.coinepro.hq.ui.growth.GrowthScreen() },
            "growth-rules" to { _ -> com.coinepro.hq.ui.growth.GrowthScreen("rules") },
            "growth-nps" to { _ -> com.coinepro.hq.ui.growth.GrowthScreen("nps") },
            "feedback" to { _ -> com.coinepro.hq.ui.feedback.FeedbackScreen() },
            "decision-golive" to { _ -> DecisionScreen("D-000032") },
            "decision-template" to { _ -> DecisionScreen("D-000031") },
            "decision-rule" to { _ -> DecisionScreen("D-000033") },
            "tools-intake" to { _ -> ToolsScreen() },
            // ⟨1.5⟩ governance (§20): the meeting room (the list, its settings, a live board meeting and its transcript, a meeting
            // before it starts, the minutes, the war room), the charter (the holding's, a proposed addendum with its seal, a version
            // against the one before), knowledge and one entry under review, the three cards (holding, a company, the scorecard) and a
            // KPI, OKR, outcomes, risks (the matrix and the register), the change calendar, the authority matrix, the batch seal and
            // the cards of the new kinds in the cartable.
            "meetings" to { _ -> com.coinepro.hq.ui.meetings.MeetingsScreen() },
            "meetings-settings" to { _ -> com.coinepro.hq.ui.meetings.MeetingsScreen("settings") },
            "meeting-live" to { _ -> com.coinepro.hq.ui.meetings.MeetingScreen("MT-0012") },
            "meeting-live-transcript" to { _ -> com.coinepro.hq.ui.meetings.MeetingScreen("MT-0012") },
            "meeting-prep" to { _ -> com.coinepro.hq.ui.meetings.MeetingScreen("MT-0013") },
            "meeting-minutes" to { _ -> com.coinepro.hq.ui.meetings.MeetingScreen("MT-0011") },
            "meeting-war" to { _ -> com.coinepro.hq.ui.meetings.MeetingScreen("MT-0010") },
            "charter" to { _ -> com.coinepro.hq.ui.charter.CharterScreen() },
            "charter-proposed" to { _ -> com.coinepro.hq.ui.charter.CharterScreen("FX") },
            "charter-diff" to { _ -> com.coinepro.hq.ui.charter.CharterScreen("TY", diff0 = true) },
            "knowledge" to { _ -> com.coinepro.hq.ui.knowledge.KnowledgeScreen() },
            "knowledge-entry" to { _ -> Sheetlike { com.coinepro.hq.ui.knowledge.EntryView("K-0009") } },
            "scorecard" to { _ -> com.coinepro.hq.ui.scorecard.ScorecardScreen() },
            "scorecard-company" to { _ -> com.coinepro.hq.ui.scorecard.ScorecardScreen("TY") },
            "scorecard-table" to { _ -> com.coinepro.hq.ui.scorecard.ScorecardScreen() },
            "kpi" to { _ -> Sheetlike { com.coinepro.hq.ui.scorecard.KpiView("TY", "min_balance_rate") } },
            "okr" to { _ -> com.coinepro.hq.ui.okr.OkrScreen() },
            "outcomes" to { _ -> com.coinepro.hq.ui.outcomes.OutcomesScreen() },
            "risks" to { _ -> com.coinepro.hq.ui.risks.RisksScreen() },
            "risks-list" to { _ -> com.coinepro.hq.ui.risks.RisksScreen() },
            "calendar" to { _ -> com.coinepro.hq.ui.calendar.CalendarScreen() },
            "authority" to { _ -> com.coinepro.hq.ui.authority.AuthorityScreen() },
            "authority-locked" to { _ -> com.coinepro.hq.ui.authority.AuthorityScreen() },
            "batch-seal" to { _ -> Sheetlike { com.coinepro.hq.ui.cartable.BatchSealContent() } },
            "decision-resolution" to { _ -> DecisionScreen("D-000034") },
            "decision-expected" to { _ -> DecisionScreen("D-000035") },
            "decision-charter" to { _ -> DecisionScreen("D-000007") },
            "decision-outcomes" to { _ -> DecisionScreen("D-000004") },
            "decision-risk" to { _ -> DecisionScreen("D-000009") },
            "decision-okr" to { _ -> DecisionScreen("D-000006") },
            // ⟨1.5⟩ management tools (§21): the advisor with the devil switch and its review, memos and proactive notes; the evaluation
            // card, the deploy card's diff with one file opened and its memo in both modes; notes; the letters and one spoken briefing;
            // the substitutes, their creatives, one creative and a new one, a player's seats; the digital CEO and its principles; the
            // HR round; waste and ROI; the connections and the wizard; claims and run health; the management settings.
            "advisor-review" to { _ -> Sheetlike { com.coinepro.hq.ui.advisor.ReviewContent() } },
            "advisor-memos" to { _ -> Sheetlike { com.coinepro.hq.ui.advisor.MemosContent() } },
            "advisor-triggers" to { _ -> Sheetlike { com.coinepro.hq.ui.advisor.TriggersContent() } },
            "decision-evaluation" to { _ -> DecisionScreen("D-000040") },
            "deploy-diff" to { _ -> Sheetlike { com.coinepro.hq.ui.cartable.DecisionManagementView("D-000017", open0 = "src/chart/cache.ts") } },
            "deploy-memo" to { _ -> Sheetlike { com.coinepro.hq.ui.cartable.DecisionManagementView("D-000017") } },
            "deploy-memo-devil" to { _ -> Sheetlike { com.coinepro.hq.ui.cartable.DecisionManagementView("D-000017", mode0 = "devil") } },
            "evaluation-memo" to { _ -> Sheetlike { com.coinepro.hq.ui.cartable.DecisionManagementView("D-000040") } },
            "notes" to { _ -> com.coinepro.hq.ui.notes.NotesScreen() },
            "letter" to { _ -> com.coinepro.hq.ui.letter.LetterScreen() },
            "letter-briefing" to { _ -> Sheetlike { com.coinepro.hq.ui.letter.BriefingView("BR-0026") } },
            "substitutes" to { _ -> com.coinepro.hq.ui.substitutes.SubstitutesScreen() },
            "substitutes-creatives" to { _ -> com.coinepro.hq.ui.substitutes.SubstitutesScreen() },
            "creative" to { _ -> Sheetlike { com.coinepro.hq.ui.substitutes.CreativeView("CR-0006") } },
            "creative-new" to { _ -> Sheetlike { com.coinepro.hq.ui.substitutes.NewCreative {} } },
            "seats" to { _ -> Sheetlike { WithSub("gemini") { com.coinepro.hq.ui.substitutes.SeatsEditor(it) } } },
            "digital-ceo" to { _ -> com.coinepro.hq.ui.dceo.DigitalCeoScreen() },
            "digital-ceo-principles" to { _ -> com.coinepro.hq.ui.dceo.DigitalCeoScreen() },
            "company-people" to { _ -> CompanyScreen("TY") },
            "hr-round" to { _ -> Sheetlike { WithRound("TY") { com.coinepro.hq.ui.people.HrRoundView(it) } } },
            "treasury-waste" to { _ -> Cardlike { com.coinepro.hq.ui.treasury.WasteCard() } },
            "treasury-roi" to { _ -> Cardlike { com.coinepro.hq.ui.treasury.RoiCard() } },
            "tools-connections" to { _ -> ToolsScreen() },
            "connection-wizard" to { _ -> Sheetlike { com.coinepro.hq.ui.tools.ConnectionWizard(onClose = {}) } },
            "runs-health" to { _ -> Cardlike { com.coinepro.hq.ui.owner.ClaimsCard(); com.coinepro.hq.ui.owner.HealthBoard() } },
            "settings-management" to { g -> SettingsScreen(g) },
        )

        /** Cards of a page on their own, on the page's surface (a card far down a long page). */
        @Composable
        private fun Cardlike(content: @Composable () -> Unit) {
            androidx.compose.foundation.layout.Column(
                Modifier.fillMaxSize().background(Divan.colors.page).verticalScroll(rememberScrollState()).padding(16.dp),
                verticalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(12.dp),
            ) { content() }
        }

        /** A substitute player as the demo serves it. */
        @Composable
        private fun WithSub(player: String, content: @Composable (com.coinepro.hq.core.net.Substitute) -> Unit) {
            val q = com.coinepro.hq.ui.rememberQuery("substitutes", "substitutes") { substitutes() }
            q.data?.firstOrNull { it.player == player }?.let { content(it) }
        }

        /** A company's HR round as the demo serves it. */
        @Composable
        private fun WithRound(company: String, content: @Composable (com.coinepro.hq.core.net.HrRound) -> Unit) {
            val q = com.coinepro.hq.ui.rememberQuery("hr:rounds:$company", "hr") { hrRounds(company) }
            q.data?.firstOrNull()?.let { content(it) }
        }

        /** A sheet's content as the sheet shows it: the overlay surface, 16dp gutters, scrolling. */
        @Composable
        private fun Sheetlike(content: @Composable () -> Unit) {
            androidx.compose.foundation.layout.Column(
                Modifier.fillMaxSize().background(Divan.colors.overlay).verticalScroll(rememberScrollState()).padding(16.dp),
            ) { content() }
        }

        /** Screens shown from further down their page: the item (of the page's list) to bring to the top. */
        private val SCROLL: Map<String, Int> = mapOf(
            "revenue-funnel" to 6, "revenue-accounts" to 7, "revenue-rescue" to 9,
            "support-conversations" to 3, "support-channels" to 3, "support-knowledge" to 3, "support-shadow" to 3,
            "growth-rules" to 3, "growth-nps" to 3,
            // The tools page: header, intro, totals, the egress log and its title, ⟨1.5⟩ the connections, the MCP title, one item per
            // server, the accounts and their title, then the intake card.
            "tools-intake" to 9 + mcpServers(),
            // ⟨1.5⟩ §21: the connections card (after the header, intro, totals and the egress log); the creatives (after the header,
            // the intro and one card per player); the principles (after the header, intro, window, tiles, calibration and kinds);
            // the management settings (after the header, devices and hiring).
            "tools-connections" to 5, "substitutes-creatives" to 2 + players(), "digital-ceo-principles" to 6, "settings-management" to 3,
            // ⟨1.5⟩ the room's agenda, whisper and transcript (after the header, table, three cards and rules); the scorecard after the
            // three cards; the register under the matrix; the locked invariants.
            "meeting-live-transcript" to 6, "scorecard-table" to 6, "risks-list" to 4, "authority-locked" to 3,
        )

        private fun players(): Int =
            com.coinepro.hq.core.net.Api.json.parseToJsonElement(java.io.File("src/debug/assets/demo-fixtures.json").readText())
                .let { (it as kotlinx.serialization.json.JsonObject)["/substitutes"]!!.let { e -> (e as kotlinx.serialization.json.JsonObject)["body"] as kotlinx.serialization.json.JsonArray }.size }

        private fun mcpServers(): Int =
            com.coinepro.hq.core.net.Api.json.parseToJsonElement(java.io.File("src/debug/assets/demo-fixtures.json").readText())
                .let { (it as kotlinx.serialization.json.JsonObject)["/tools/mcp"]!!.let { e -> (e as kotlinx.serialization.json.JsonObject)["body"] as kotlinx.serialization.json.JsonArray }.size }
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
        // Sections further down load when they are first composed, so the page is scrolled again once they have.
        SCROLL[name]?.let { index ->
            repeat(2) {
                compose.onAllNodes(hasScrollToIndexAction())[0].performScrollToIndex(index)
                repeat(6) {
                    Thread.sleep(200)
                    shadowOf(Looper.getMainLooper()).idle()
                    compose.mainClock.advanceTimeBy(250)
                }
            }
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
