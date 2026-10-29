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
import kotlinx.serialization.json.put
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import org.robolectric.ParameterizedRobolectricTestRunner
import org.robolectric.Shadows.shadowOf

/** Renders every screen with the demo holding (the same fixtures as the web) in both themes. The images
 *  (src/test/screenshots) are how a change to the design is reviewed; `recordRoborazziDebug` refreshes them.
 *  The screens run in [SHARDS] classes (the end of this file), each in a fresh test JVM: one JVM for every screen ran out of heap. */
abstract class ScreensTest(private val name: String, private val night: Boolean) {

    companion object {
        const val SHARDS = 5

        /** The screens of shard [i], night and day, in the order they are listed. */
        fun shard(i: Int): List<Array<Any>> =
            SCREENS.keys.toList().let { keys -> keys.chunked((keys.size + SHARDS - 1) / SHARDS).getOrElse(i) { emptyList() } }
                .flatMap { listOf(arrayOf<Any>(it, true), arrayOf<Any>(it, false)) }

        private val SCREENS: Map<String, @Composable (AppGraph) -> Unit> = linkedMapOf(
            "home" to { _ -> HomeScreen(onNewOrder = {}) },
            "cartable" to { _ -> CartableScreen() },
            "decision-hire" to { _ -> DecisionScreen("D-000014") },
            "decision-deploy" to { _ -> DecisionScreen("D-000017") },
            "decision-sealed" to { _ -> DecisionScreen("D-000011") },
            "outputs" to { _ -> OutputsScreen() },
            "output" to { _ -> OutputScreen("O-000029") },
            // ⟨1.7.3⟩ outputs: the new ones (the swipe and «همه را خوانده‌شده کن»), the seen ones by day (one filed in the archive), the
            // filters, and the hub's rule-based morning report with its table of companies (the table on its own further down).
            "outputs-seen" to { _ -> OutputsScreen("seen") },
            "outputs-all" to { _ -> OutputsScreen("all") },
            "outputs-filters" to { _ ->
                Sheetlike {
                    com.coinepro.hq.ui.outputs.OutputFilters(
                        "report", {}, "TY", {}, null, {},
                        listOf(com.coinepro.hq.core.net.EmployeeRef("HQ-SYS", "HQ", "system", "سیستم"), com.coinepro.hq.core.net.EmployeeRef("FX-QUANT-02", "FX", "employee", "پایشگر سیگنال")),
                        "7d", {}, {}, {},
                    )
                }
            },
            "output-report" to { _ -> OutputScreen("O-000032") },
            "output-report-table" to { _ ->
                Cardlike {
                    val q = com.coinepro.hq.ui.rememberQuery("deliverable:O-000032", "deliverables") { deliverable("O-000032") }
                    q.data?.body?.let { com.coinepro.hq.designsystem.Md(it.substringAfter("## شرکت‌ها").let { b -> "## شرکت‌ها$b" }) }
                }
            },
            "chat-media" to { _ -> ChatScreen("FX-CEO") },
            "threads" to { _ -> ThreadsScreen() },
            // Company control: the companies in mixed states (Pro-Chart stopped by its CEO, CoinePro FX's deploys closed, the holding and FX
            // at work, TradeYar's run just started on the live stream), the same list further down, a company's control room (FX: running
            // with its deploys closed; the history, the month's budget gauge; further down its live activity, hiring and sites) and a stopped
            // one (PC, who stopped it and why), the stop confirmation sheet, a company's actions (the long press), the holding's card with
            // its switch engaged and running.
            "companies" to { g -> Live(g) { CompaniesScreen() } },
            "companies-list" to { g -> Live(g) { CompaniesScreen() } },
            "company-control" to { g -> Live(g) { CompanyScreen("FX") } },
            "company-control-live" to { g -> Live(g) { CompanyScreen("FX") } },
            "company-control-stopped" to { _ -> CompanyScreen("PC") },
            "company-control-holding" to { g -> Live(g) { CompanyScreen("HQ") } },
            "stop-sheet" to { _ ->
                Sheetlike {
                    SheetTitle("توقف کوینه‌پرو FX")
                    com.coinepro.hq.ui.companies.StopContent(com.coinepro.hq.ui.companies.CoTarget("FX", "کوینه‌پرو FX", false), busy = false, onStop = {}, onCancel = {})
                }
            },
            "resume-sheet" to { _ ->
                Sheetlike {
                    val control = com.coinepro.hq.ui.rememberQuery("control", "control") { control() }
                    SheetTitle("ادامه‌ی کار پرو-چارت")
                    control.data?.let { com.coinepro.hq.ui.companies.ResumeContent(com.coinepro.hq.ui.companies.CoTarget("PC", "پرو-چارت", false), com.coinepro.hq.core.data.coState("PC", false, it), busy = false, onResume = {}, onCancel = {}) }
                }
            },
            "company-actions" to { _ ->
                Sheetlike {
                    val control = com.coinepro.hq.ui.rememberQuery("control", "control") { control() }
                    val ui = com.coinepro.hq.ui.companies.rememberControlUi()
                    SheetTitle("کوینه‌پرو FX")
                    control.data?.let { com.coinepro.hq.ui.companies.ActionsContent(com.coinepro.hq.ui.companies.CoTarget("FX", "کوینه‌پرو FX", false), com.coinepro.hq.core.data.coState("FX", false, it), ui) {} }
                }
            },
            "holding-card" to { _ -> Cardlike { HoldingCards() } },
            // The tools sheet: its groups on cards, each row with its icon tile (and the outputs' and the error log's counts).
            "tools-sheet" to { _ -> Box(Modifier.fillMaxSize().background(Divan.colors.overlay).padding(top = 16.dp)) { com.coinepro.hq.ui.shell.ToolsSheet(outputs = 6, errors = 2) {} } },
            "company" to { _ -> CompanyScreen("FX", tab0 = "departments") },
            "employee" to { _ -> EmployeeScreen("TY-GROWTH-01") },
            "work" to { _ -> WorkScreen("w0") },
            "treasury" to { _ -> TreasuryScreen() },
            "planner" to { _ -> PlannerScreen(onNewOrder = {}) },
            "control" to { _ -> ControlScreen() },
            "notifications" to { _ -> NotificationsScreen() },
            "audit" to { _ -> AuditScreen() },
            "settings" to { g -> SettingsScreen(g) },
            // «خطاخوان»: a contract mismatch with its field path (opened), an HTTP error counted twice, a network failure, a crash.
            "errors" to { g -> androidx.compose.runtime.remember { sampleErrors(g) }; com.coinepro.hq.ui.settings.ErrorLogScreen(g.errors) },
            "errors-open" to { g ->
                val e = androidx.compose.runtime.remember { sampleErrors(g); g.errors.entries.value }
                Cardlike { for ((i, x) in e.withIndex()) com.coinepro.hq.ui.settings.EntryCard(x, open0 = i == 0 || x.kind == "crash") }
            },
            "workshop" to { _ -> WorkshopScreen(onNewSession = {}, onGrant = {}) },
            "session-approval" to { _ -> SessionScreen("S-0004") },
            "session-done" to { _ -> SessionScreen("S-0002") },
            // ⟨1.4⟩
            "oversight" to { _ -> OversightScreen() },
            "overseer-chat" to { _ -> ChatScreen("N", agent = "overseer") },
            "assistant" to { _ -> AssistantScreen() },
            "advisor" to { _ -> com.coinepro.hq.ui.advisor.AdvisorScreen() },
            "stars" to { _ -> StarsScreen() },
            // A hub with no roll-up yet (404 until its first Saturday): the empty state, not an error.
            "stars-empty" to { _ -> androidx.compose.runtime.remember { Demo.absent = setOf("/stars/rollup") }; StarsScreen() },
            "skills" to { _ -> SkillsScreen() },
            "academy" to { _ -> AcademyScreen() },
            "foundings" to { _ -> FoundingsScreen() },
            "founding-proposed" to { _ -> FoundingScreen("C-0002") },
            "founding-ready" to { _ -> FoundingScreen("C-0001") },
            "founding-plan" to { _ -> FoundingScreen("PV-0003") },
            "tools" to { _ -> ToolsScreen() },
            // ⟨1.4.2⟩ the owner's own hire, filled in (the sheet's content)
            // ⟨1.4.3⟩ a hire story (welcome / dismiss) and a CEO's milestone
            "story-hire" to { _ -> StoryPreview("FX", "hire") },
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
            "company-people" to { _ -> CompanyScreen("TY", tab0 = "departments") },
            "hr-round" to { _ -> Sheetlike { WithRound("TY") { com.coinepro.hq.ui.people.HrRoundView(it) } } },
            "treasury-waste" to { _ -> Cardlike { com.coinepro.hq.ui.treasury.WasteCard() } },
            "treasury-roi" to { _ -> Cardlike { com.coinepro.hq.ui.treasury.RoiCard() } },
            "tools-connections" to { _ -> ToolsScreen() },
            // Every provider's logo as the app draws it (paths without arcs, gradients kept), large and at list size.
            "provider-logos" to { _ -> Cardlike { ProviderLogos() } },
            "connection-wizard" to { _ -> Sheetlike { com.coinepro.hq.ui.tools.ConnectionWizard(onClose = {}) } },
            "runs-health" to { _ -> Cardlike { com.coinepro.hq.ui.owner.ClaimsCard(); com.coinepro.hq.ui.owner.HealthBoard() } },
            "settings-management" to { g -> SettingsScreen(g) },
            // ⟨1.6⟩ media and legal (§22): the studio (its pipeline board further down), an item published, one waiting for the
            // owner's seal, one held by the overseer and a design, a one-off item; the publishing series (the channels' week and
            // limits further down) and one series in the editor; the hub's voice (the registry further down); legal counsel, a case
            // with an email to seal, a closed case and a new case; the four cards in the cartable; a department's mandate and its
            // editor, roles its manager wrote (active and rejected), the people tab with roles on demand, a role's story; thread L.
            "studio" to { _ -> com.coinepro.hq.ui.studio.StudioScreen() },
            "studio-board" to { _ -> com.coinepro.hq.ui.studio.StudioScreen() },
            "studio-item" to { _ -> Sheetlike { com.coinepro.hq.ui.studio.ItemView("MI-0014") } },
            "studio-item-waiting" to { _ -> Sheetlike { com.coinepro.hq.ui.studio.ItemView("MI-0013") } },
            "studio-item-held" to { _ -> Sheetlike { com.coinepro.hq.ui.studio.ItemView("MI-0012") } },
            "studio-item-design" to { _ -> Sheetlike { com.coinepro.hq.ui.studio.ItemView("MI-0024") } },
            "studio-new" to { _ -> Sheetlike { com.coinepro.hq.ui.studio.NewItem {} } },
            "series" to { _ -> com.coinepro.hq.ui.studio.SeriesScreen() },
            "series-week" to { _ -> com.coinepro.hq.ui.studio.SeriesScreen() },
            "series-editor" to { _ -> Sheetlike { WithSeries("SR-0001") { com.coinepro.hq.ui.studio.SeriesEditor(it) {} } } },
            "voice" to { _ -> com.coinepro.hq.ui.studio.VoiceScreen() },
            "voice-registry" to { _ -> com.coinepro.hq.ui.studio.VoiceScreen() },
            "legal" to { _ -> com.coinepro.hq.ui.legal.LegalScreen() },
            "legal-case" to { _ -> com.coinepro.hq.ui.legal.CaseScreen("LC-0001") },
            "legal-case-resolved" to { _ -> com.coinepro.hq.ui.legal.CaseScreen("LC-0003") },
            "legal-new" to { _ -> Sheetlike { com.coinepro.hq.ui.legal.NewCase {} } },
            "decision-media-publish" to { _ -> DecisionScreen("D-000087") },
            "decision-email" to { _ -> DecisionScreen("D-000085") },
            "decision-series" to { _ -> DecisionScreen("D-000081") },
            "decision-role" to { _ -> DecisionScreen("D-000084") },
            "department" to { _ -> Sheetlike { com.coinepro.hq.ui.org.DepartmentView("FX", "MEDIA") {} } },
            "mandate-editor" to { _ -> Sheetlike { WithDepartment("FX", "MEDIA") { com.coinepro.hq.ui.org.MandateEditor("FX", it) {} } } },
            "role-draft" to { _ -> Sheetlike { com.coinepro.hq.ui.org.RoleDraftView("RD-0001") } },
            "role-draft-rejected" to { _ -> Sheetlike { com.coinepro.hq.ui.org.RoleDraftView("RD-0003") } },
            "company-roles" to { _ -> CompanyScreen("FX", tab0 = "people") },
            "story-role" to { _ -> StoryPreview("FX", "role") },
            "chat-legal" to { _ -> ChatScreen("L") },
            // ⟨1.7⟩ the archive (§23): its home, the list under the search, a search with snippets from the files' text and a party's
            // records; a new document (two files: one refused by name for a secret pattern, the other read, with the rules' suggestion);
            // a record filed with two versions (its files, links and seal, retention and the access log further down), a held one, a
            // sealed «سری» one (its seal and declassification further down), a draft with its suggestion and a tombstone; a file shown
            // and one behind the passkey; the holds and a new hold for a case; reminders; the end of retention; the open layer's tabs,
            // a class, an automation and a retention rule (with its dry run's impact) in the editor, a new level the hub refused (the
            // errors beside their fields) and a party; the two cards; a case's holds on the legal page.
            "archive" to { _ -> com.coinepro.hq.ui.archive.ArchiveScreen() },
            "archive-list" to { _ -> com.coinepro.hq.ui.archive.ArchiveScreen() },
            "archive-search" to { _ -> com.coinepro.hq.ui.archive.ArchiveScreen(q0 = "هتزنر") },
            "archive-party" to { _ -> com.coinepro.hq.ui.archive.ArchiveScreen(party0 = "PT-0002") },
            "archive-intake" to { _ -> Sheetlike { com.coinepro.hq.ui.archive.IntakeContent("HQ", {}, pickedFiles()) } },
            "archive-record" to { _ -> com.coinepro.hq.ui.archive.RecordScreen("AR-000110") },
            "archive-record-files" to { _ -> com.coinepro.hq.ui.archive.RecordScreen("AR-000110") },
            "archive-record-links" to { _ -> com.coinepro.hq.ui.archive.RecordScreen("AR-000110") },
            "archive-record-access" to { _ -> com.coinepro.hq.ui.archive.RecordScreen("AR-000110") },
            "archive-record-held" to { _ -> com.coinepro.hq.ui.archive.RecordScreen("AR-000151") },
            "archive-record-sealed" to { _ -> com.coinepro.hq.ui.archive.RecordScreen("AR-000180") },
            "archive-record-seal" to { _ -> com.coinepro.hq.ui.archive.RecordScreen("AR-000180") },
            "archive-record-draft" to { _ -> com.coinepro.hq.ui.archive.RecordScreen("AR-000170") },
            "archive-record-disposed" to { _ ->
                Cardlike {
                    WithRecord("AR-000090") { r, m ->
                        val hashes = r.versions.flatMap { it.files }.map { com.coinepro.hq.core.net.HashRow(it.name, it.sha256) }
                        com.coinepro.hq.ui.archive.TombstoneView(r.copy(state = "disposed", tombstone = com.coinepro.hq.core.net.Tombstone("D-000093", "2026-10-17T08:00:00Z", hashes)), m)
                    }
                }
            },
            "archive-file" to { _ -> Sheetlike { WithRecord("AR-000170") { r, m -> com.coinepro.hq.ui.archive.FileViewer(r, r.current!!.files.first(), m) } } },
            "archive-file-locked" to { _ -> Sheetlike { WithRecord("AR-000180") { r, m -> com.coinepro.hq.ui.archive.FileViewer(r, r.current!!.files.first(), m) } } },
            "archive-holds" to { _ -> com.coinepro.hq.ui.archive.HoldsScreen() },
            "archive-hold-new" to { _ -> Sheetlike { com.coinepro.hq.ui.archive.NewHoldContent("LC-0001", {}, {}) } },
            "archive-reminders" to { _ -> com.coinepro.hq.ui.archive.RemindersScreen() },
            "archive-retention" to { _ -> com.coinepro.hq.ui.archive.RetentionScreen() },
            "archive-settings" to { _ -> com.coinepro.hq.ui.archive.ArchiveSettingsScreen() },
            "archive-settings-folders" to { _ -> com.coinepro.hq.ui.archive.ArchiveSettingsScreen("folders") },
            "archive-settings-levels" to { _ -> com.coinepro.hq.ui.archive.ArchiveSettingsScreen("levels") },
            "archive-settings-clearance" to { _ -> com.coinepro.hq.ui.archive.ArchiveSettingsScreen("clearance") },
            "archive-settings-retention" to { _ -> com.coinepro.hq.ui.archive.ArchiveSettingsScreen("retention") },
            "archive-settings-automations" to { _ -> com.coinepro.hq.ui.archive.ArchiveSettingsScreen("automations") },
            "archive-settings-parties" to { _ -> com.coinepro.hq.ui.archive.ArchiveSettingsScreen("parties") },
            "archive-settings-sources" to { _ -> com.coinepro.hq.ui.archive.ArchiveSettingsScreen("sources") },
            "archive-class-editor" to { _ -> Sheetlike { WithRow("classes", "invoice") { ui, row -> com.coinepro.hq.ui.archive.RowEditorContent("classes", ui, row, {}) } } },
            "archive-automation-editor" to { _ -> Sheetlike { WithRow("automations", "AU-0002") { ui, row -> com.coinepro.hq.ui.archive.RowEditorContent("automations", ui, row, {}) } } },
            "archive-retention-editor" to { _ -> Sheetlike { WithRow("retention", "RR-0002") { ui, row -> com.coinepro.hq.ui.archive.RowEditorContent("retention", ui, row, {}, preview0 = true) } } },
            "archive-level-invalid" to { _ ->
                Sheetlike {
                    WithRow("levels", null) { ui, _ ->
                        val blank = kotlinx.serialization.json.buildJsonObject {
                            put("key", "top_secret"); put("title_fa", "فوق سری"); put("rank", 30); put("color_index", 5)
                            put("watermark", true); put("encrypt", true); put("step_up_to_view", true); put("agents_max", true)
                        }
                        com.coinepro.hq.ui.archive.RowEditorContent("levels", ui, null, {}, preview0 = true, blank0 = blank)
                    }
                }
            },
            "archive-party-editor" to { _ -> Sheetlike { WithParty("PT-0006") { p, m -> com.coinepro.hq.ui.archive.PartyContent(p, m) {} } } },
            "decision-archive-schema" to { _ -> DecisionScreen("D-000092") },
            "decision-archive-disposal" to { _ -> DecisionScreen("D-000093") },
            "legal-case-holds" to { _ -> Cardlike { com.coinepro.hq.ui.archive.CaseHolds("LC-0001") } },
        )

        /** The demo's live stream running under [content]: its first beat (a run starting) lands at once. */
        @Composable
        private fun Live(g: AppGraph, content: @Composable () -> Unit) {
            androidx.compose.runtime.remember { g.env.value.stream.start() }
            content()
        }

        /** A sheet's title as [com.coinepro.hq.ui.v14.HqSheet] sets it. */
        @Composable
        private fun SheetTitle(text: String) {
            androidx.compose.material3.Text(text, style = Divan.type.h2, modifier = Modifier.padding(bottom = 14.dp))
        }

        /** The holding's card with its switch engaged (everything stopped), then as it is (running). */
        @Composable
        private fun HoldingCards() {
            val q = com.coinepro.hq.ui.rememberQuery("companies", "companies") { companies() }
            val base = com.coinepro.hq.ui.companies.rememberControlData()
            val ui = com.coinepro.hq.ui.companies.rememberControlUi()
            val list = q.data ?: return
            val ctl = base.control ?: return
            val holding = list.first { it.kind == "holding" }
            val engaged = ctl.copy(holding = ctl.holding.copy(state = "engaged", reason = "رفتار غیرعادی در چند شرکت؛ تا بررسی همه بایستند.", changedAt = "2026-10-17T08:12:00Z", changedBy = "owner"))
            com.coinepro.hq.ui.companies.HoldingControlCard(holding, list, com.coinepro.hq.ui.companies.ControlData(engaged, base.running, base.spend, base.pulses), ui) {}
            com.coinepro.hq.ui.companies.HoldingControlCard(holding, list, base, ui) {}
        }

        /** The error log as a real session fills it: what the owner reported, with the fields the report names. */
        private fun sampleErrors(g: AppGraph) {
            val l = g.errors
            l.clear()
            l.screen = "voice"
            l.record(com.coinepro.hq.core.net.ApiFailure("network", "POST", "/api/v1/transcribe", null, "network_error", "SocketTimeoutException"))
            l.screen = "stars"
            val http = com.coinepro.hq.core.net.ApiFailure("http", "GET", "/api/v1/media/voices/reference", 503, "channel_not_configured", "Service Unavailable", "01JBX4Q7A9")
            l.record(http); l.record(http)
            l.screen = "outputs/{ref}"
            l.record(com.coinepro.hq.core.net.ApiFailure("decode", "GET", "/api/v1/media/voices", 200, "contract_mismatch", null, "01JBX4Q2ZK", "$[0].mem_mb", "Expected Int, got 412.6"))
            l.crash(Thread.currentThread(), IllegalStateException("demo crash for the screenshot"))
        }

        /** Every provider logo at 48dp and at the list's 20dp, with its key. */
        @Composable
        private fun ProviderLogos() {
            val c = Divan.colors
            for (k in com.coinepro.hq.designsystem.generated.PROVIDER_LOGOS.keys) {
                androidx.compose.foundation.layout.Row(
                    Modifier.padding(vertical = 4.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
                    horizontalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(16.dp),
                ) {
                    com.coinepro.hq.designsystem.ModelMark(null, provider = k, size = 48.dp)
                    com.coinepro.hq.designsystem.ModelMark(null, provider = k, size = 20.dp)
                    com.coinepro.hq.designsystem.Fig(k, color = c.textSecondary)
                }
            }
        }

        /** A record of the archive and the schema's maps, as the demo serves them. */
        @Composable
        private fun WithRecord(ref: String, content: @Composable (com.coinepro.hq.core.net.ArchiveRecord, com.coinepro.hq.ui.archive.ArchiveMaps) -> Unit) {
            val q = com.coinepro.hq.ui.rememberQuery("archive:record:$ref", "archive") { record(ref) }
            val a = com.coinepro.hq.ui.archive.rememberArchive()
            val r = q.data
            if (r != null && a.q.data != null) content(r, a.m)
        }

        /** One row of a part of the archive's schema (none: a new one) with the part's editor description. */
        @Composable
        private fun WithRow(part: String, key: String?, content: @Composable (com.coinepro.hq.ui.archive.PartUI, kotlinx.serialization.json.JsonObject?) -> Unit) {
            val a = com.coinepro.hq.ui.archive.rememberArchive()
            val rows = a.q.data?.rows(part) ?: return
            val ui = com.coinepro.hq.ui.archive.partUI(part, rows)
            content(ui, key?.let { k -> rows.first { com.coinepro.hq.ui.archive.rowKey(ui, it) == k } })
        }

        /** A party of the archive's registry. */
        @Composable
        private fun WithParty(ref: String, content: @Composable (com.coinepro.hq.core.net.Party, com.coinepro.hq.ui.archive.ArchiveMaps) -> Unit) {
            val q = com.coinepro.hq.ui.rememberQuery("archive:parties", "archive") { parties() }
            val a = com.coinepro.hq.ui.archive.rememberArchive()
            val p = q.data?.firstOrNull { it.ref == ref }
            if (p != null && a.q.data != null) content(p, a.m)
        }

        /** Two files as the system picker hands them over: an invoice from the demo's archive and a text file named like a wallet seed. */
        @Composable
        private fun pickedFiles(): List<android.net.Uri> {
            val ctx = androidx.compose.ui.platform.LocalContext.current
            return androidx.compose.runtime.remember {
                val dir = java.io.File(ctx.cacheDir, "picked").apply { mkdirs() }
                val pdf = java.io.File(dir, "hetzner-R2026-10.pdf").apply { writeBytes(ctx.assets.open("demo/archive/hetzner-R2026-10.pdf").use { it.readBytes() }) }
                val seed = java.io.File(dir, "wallet-seed.txt").apply { writeText("demo: twelve words of an old wallet") }
                listOf(android.net.Uri.fromFile(pdf), android.net.Uri.fromFile(seed))
            }
        }

        /** A publishing series as the demo serves it. */
        @Composable
        private fun WithSeries(ref: String, content: @Composable (com.coinepro.hq.core.net.Series) -> Unit) {
            val q = com.coinepro.hq.ui.rememberQuery("media:series::", "media") { series() }
            q.data?.firstOrNull { it.ref == ref }?.let { content(it) }
        }

        /** A company's department as the demo serves it. */
        @Composable
        private fun WithDepartment(company: String, code: String, content: @Composable (com.coinepro.hq.core.net.Department) -> Unit) {
            val q = com.coinepro.hq.ui.rememberQuery("departments:$company", "companies") { departments(company) }
            q.data?.firstOrNull { it.code == code }?.let { content(it) }
        }

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
            // ⟨1.6⟩ §22: the studio's board (after the header, intro, overview, scopes, kinds, counts and what needs the owner); the
            // channels' week (after the header, scopes, statuses and one card per series); the voice registry (after the header,
            // intro, the active voice and the blind test).
            "studio-board" to 7, "series-week" to 3 + fixtureSize("/media/series"), "voice-registry" to 4,
            // ⟨1.7⟩ §23: the archive's list under the search card (after the header, fixity and links, what expires and the drafts), a
            // party's card above its records; a record's files, its links and seal, retention and the access log (after the header and
            // the metadata), the held record's holds and the sealed one's seal.
            "archive-list" to 4, "archive-search" to 4, "archive-party" to 5,
            // Company control: the list from CoinePro FX on (header, holding, TradeYar, FX); the control room's live activity (header, tabs,
            // state, history, budget, live).
            "companies-list" to 3, "company-control-live" to 5,
            "archive-record-files" to 2, "archive-record-links" to 3, "archive-record-access" to 5, "archive-record-held" to 5, "archive-record-seal" to 4,
        )

        /** The number of rows the demo serves at [path], bare or paged. */
        private fun fixtureSize(path: String): Int =
            com.coinepro.hq.core.net.Api.json.parseToJsonElement(java.io.File("src/debug/assets/demo-fixtures.json").readText())
                .let { (it as kotlinx.serialization.json.JsonObject)[path]!!.let { e -> (e as kotlinx.serialization.json.JsonObject)["body"]!! } }
                .let { b -> (if (b is kotlinx.serialization.json.JsonObject) b["items"] else b) as kotlinx.serialization.json.JsonArray }.size

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

@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h880dp-xxhdpi")
class ScreensShard1Test(name: String, night: Boolean) : ScreensTest(name, night) {
    companion object {
        @JvmStatic
        @ParameterizedRobolectricTestRunner.Parameters(name = "{0}-{1}")
        fun params(): List<Array<Any>> = ScreensTest.shard(0)
    }
}

@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h880dp-xxhdpi")
class ScreensShard2Test(name: String, night: Boolean) : ScreensTest(name, night) {
    companion object {
        @JvmStatic
        @ParameterizedRobolectricTestRunner.Parameters(name = "{0}-{1}")
        fun params(): List<Array<Any>> = ScreensTest.shard(1)
    }
}

@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h880dp-xxhdpi")
class ScreensShard3Test(name: String, night: Boolean) : ScreensTest(name, night) {
    companion object {
        @JvmStatic
        @ParameterizedRobolectricTestRunner.Parameters(name = "{0}-{1}")
        fun params(): List<Array<Any>> = ScreensTest.shard(2)
    }
}

@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h880dp-xxhdpi")
class ScreensShard4Test(name: String, night: Boolean) : ScreensTest(name, night) {
    companion object {
        @JvmStatic
        @ParameterizedRobolectricTestRunner.Parameters(name = "{0}-{1}")
        fun params(): List<Array<Any>> = ScreensTest.shard(3)
    }
}

@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h880dp-xxhdpi")
class ScreensShard5Test(name: String, night: Boolean) : ScreensTest(name, night) {
    companion object {
        @JvmStatic
        @ParameterizedRobolectricTestRunner.Parameters(name = "{0}-{1}")
        fun params(): List<Array<Any>> = ScreensTest.shard(4)
    }
}
