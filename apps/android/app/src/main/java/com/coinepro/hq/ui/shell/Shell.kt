package com.coinepro.hq.ui.shell

import androidx.compose.animation.AnimatedContentTransitionScope
import androidx.compose.animation.EnterTransition
import androidx.compose.animation.ExitTransition
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import com.coinepro.hq.designsystem.Motion
import com.coinepro.hq.designsystem.motionShort
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.coinepro.hq.core.AppGraph
import com.coinepro.hq.core.data.StreamState
import com.coinepro.hq.core.net.StreamEvent
import com.coinepro.hq.designsystem.Badge
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.IconBtn
import com.coinepro.hq.designsystem.LiveDot
import com.coinepro.hq.designsystem.LocalBrands
import com.coinepro.hq.designsystem.Monogram
import com.coinepro.hq.designsystem.pressScale
import com.coinepro.hq.designsystem.Orb
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.Nav
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
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.settings.SettingsScreen
import com.coinepro.hq.ui.treasury.TreasuryScreen
import com.coinepro.hq.ui.work.NewOrderSheet
import com.coinepro.hq.ui.work.VoiceOrderSheet
import com.coinepro.hq.ui.workshop.GrantSheet
import com.coinepro.hq.ui.workshop.NewSessionSheet
import com.coinepro.hq.ui.workshop.SessionScreen
import com.coinepro.hq.ui.workshop.WorkshopScreen

/** What the live stream looks like to screens: connection state, the last event, a short feed. */
@Stable
class Live(val state: StreamState, val last: StreamEvent?, val feed: List<StreamEvent>)

val LocalLive = staticCompositionLocalOf { Live(StreamState.CONNECTING, null, emptyList()) }

private data class Tab(val route: String, val label: String, val icon: DivanIcon, val badge: String? = null)

/** The bottom bar; the gold button in the middle ("order") is not a tab: a tap speaks an order, a long press types one. */
private val TABS = listOf(
    Tab("home", "فرمان", DivanIcon.COMMAND),
    Tab("cartable", "کارتابل", DivanIcon.CARTABLE, "decisions"),
    Tab("order", "فرمان صوتی", DivanIcon.MIC),
    Tab("companies", "شرکت‌ها", DivanIcon.COMPANIES),
    Tab("messages", "پیام‌ها", DivanIcon.MESSAGES, "messages"),
)

private data class Tool(val route: String, val label: String, val icon: DivanIcon)

/** The organisation beside the advisor (contract §18): the overseer and the assistant first, then what they run. */
private val ORG = listOf(
    Tool("advisor", "مشاور کل", DivanIcon.ADVISOR),
    Tool("oversight", "ناظر کل", DivanIcon.OVERSEER),
    Tool("assistant", "دستیار", DivanIcon.ASSISTANT),
    Tool("stars", "ستاره‌ها", DivanIcon.STAR),
    Tool("founding", "تأسیس شرکت", DivanIcon.FOUND),
    Tool("skills", "مهارت‌ها", DivanIcon.SKILL),
    Tool("academy", "آکادمی", DivanIcon.ACADEMY),
    Tool("tools", "ابزارها و اینترنت", DivanIcon.GLOBE),
)

/** ⟨1.5⟩ governance (§20): the meeting room, the charter, knowledge, the cards, OKRs, outcomes, risks, the change calendar and authority. */
private val GOVERNANCE = listOf(
    Tool("meetings", "اتاق جلسه", DivanIcon.MEETING),
    Tool("charter", "اساسنامه", DivanIcon.REPORT),
    Tool("knowledge", "دانشنامه", DivanIcon.KNOWLEDGE),
    Tool("scorecard", "کارت‌ها و امتیاز", DivanIcon.CHART),
    Tool("okr", "OKR", DivanIcon.PLANNER),
    Tool("outcomes", "بازبینی نتیجه", DivanIcon.REFRESH),
    Tool("risks", "دفتر ریسک", DivanIcon.URGENT),
    Tool("calendar", "تقویم تغییرات", DivanIcon.TIME),
    Tool("authority", "ماتریس اختیار", DivanIcon.LOCK),
)

/** ⟨1.5⟩ management tools (§21): quick notes, the spoken briefings and CEO letters, the substitute players, the digital CEO. */
private val MANAGEMENT = listOf(
    Tool("notes", "یادداشت‌ها", DivanIcon.EDIT),
    Tool("letter", "گزارش صوتی و نامه‌ها", DivanIcon.MIC),
    Tool("substitutes", "بازیکن‌های ذخیره", DivanIcon.AGENT),
    Tool("digital-ceo", "مدیر کل دیجیتال", DivanIcon.HOLDING),
)

/** ⟨1.6⟩ the media studio and the legal counsel (§22): each company's pipeline, the sealed publishing series, the hub's own voice, the cases. */
private val MEDIA = listOf(
    Tool("studio", "استودیوی رسانه", DivanIcon.VIDEO),
    Tool("series", "برنامه‌های انتشار", DivanIcon.SEND),
    Tool("voice", "صدای هاب", DivanIcon.MIC),
    Tool("legal", "مشاور حقوقی", DivanIcon.DECISION),
)

/** ⟨1.7⟩ the archive of record (§23): search and intake, legal holds, reminders, the end of retention, and the open layer. */
private val ARCHIVE = listOf(
    Tool("archive", "بایگانی", DivanIcon.DELIVERABLE),
    Tool("archive-holds", "توقیف‌ها", DivanIcon.LOCK),
    Tool("archive-reminders", "یادآورها", DivanIcon.TIME),
    Tool("archive-retention", "پایان نگهداری", DivanIcon.MEMORY),
    Tool("archive-settings", "طرح بایگانی", DivanIcon.SETTINGS),
)

private val TOOLS = listOf(
    // ⟨1.5⟩ revenue and support (§19)
    Tool("revenue", "درآمد", DivanIcon.CHART),
    Tool("support", "پشتیبانی", DivanIcon.MESSAGES),
    Tool("growth", "رشد و پیام‌ها", DivanIcon.SEND),
    Tool("feedback", "بازخورد", DivanIcon.RATE),
    Tool("workshop", "کارگاه کد", DivanIcon.CODE),
    Tool("outputs", "خروجی‌ها", DivanIcon.DELIVERABLE),
    Tool("treasury", "خزانه‌ی توکن", DivanIcon.TREASURY),
    Tool("planner", "پلنر", DivanIcon.PLANNER),
    Tool("resolutions", "دفتر مصوبات", DivanIcon.SEAL),
    Tool("runs", "اجرای ایجنت‌ها", DivanIcon.AGENT),
    Tool("sites", "پایش سایت‌ها", DivanIcon.SERVER),
    Tool("notifications", "اعلان‌ها", DivanIcon.BELL),
    Tool("control", "کنترل", DivanIcon.LOCK),
    Tool("audit", "دفتر Audit", DivanIcon.REPORT),
    Tool("settings", "تنظیمات", DivanIcon.SETTINGS),
    Tool("errors", "خطاخوان", DivanIcon.URGENT),
)

private val TOP = TABS.map { it.route }.toSet() + ORG.map { it.route } + MANAGEMENT.map { it.route } + MEDIA.map { it.route } + ARCHIVE.map { it.route } +
    GOVERNANCE.map { it.route } + TOOLS.map { it.route }

private class NavImpl(private val nav: NavHostController) : Nav {
    override fun go(route: String) {
        if (route in TOP) {
            nav.navigate(route) {
                popUpTo("home") { saveState = true }
                launchSingleTop = true
                restoreState = true
            }
        } else {
            nav.navigate(route)
        }
    }

    override fun back() {
        nav.popBackStack()
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun Shell(graph: AppGraph, launch: String? = null, onLaunchConsumed: () -> Unit = {}) {
    val env = LocalEnv.current
    val ctx = androidx.compose.ui.platform.LocalContext.current
    val offlineSince by env.offlineSince.collectAsStateWithLifecycle()
    val nav = rememberNavController()
    val navApi = remember(nav) { NavImpl(nav) }
    val entry by nav.currentBackStackEntryAsState()
    val route = entry?.destination?.route ?: "home"
    val top = route in TOP
    val inbox = rememberQuery("inbox", "inbox", maxAgeMs = 30_000) { inbox() }
    val streamState by env.stream.state.collectAsStateWithLifecycle()
    val feed = remember(env) { mutableStateListOf<StreamEvent>() }
    var last by remember(env) { mutableStateOf<StreamEvent?>(null) }
    LaunchedEffect(env) {
        env.stream.events.collect { e ->
            last = e
            feed.add(0, e)
            while (feed.size > 20) feed.removeAt(feed.lastIndex)
        }
    }
    var tools by remember { mutableStateOf(false) }
    var order by remember { mutableStateOf(false) }
    var voice by remember { mutableStateOf(false) }
    // The gold button's long press, and «فرمان تازه»: the order typed.
    var newSession by remember { mutableStateOf(false) }
    var grantFor by remember { mutableStateOf<String?>(null) }
    var granting by remember { mutableStateOf(false) }
    // The quick-settings tile and the widget open the app on a place (voice order, cartable).
    LaunchedEffect(launch) {
        when (launch) { "voice" -> voice = true; "cartable" -> navApi.go("cartable") }
        if (launch != null) onLaunchConsumed()
    }
    // The home-screen widget shows the last counts the app saw (M12); the demo never writes to it.
    LaunchedEffect(inbox.data, env.demo) {
        val i = inbox.data ?: return@LaunchedEffect
        if (!env.demo) com.coinepro.hq.device.CartableWidget.update(ctx, i.decisionsPending, i.notifications["urgent"] ?: 0)
    }

    // ⟨1.4.6⟩ marks and seals draw from GET /brands first (§18.14).
    val brands = com.coinepro.hq.ui.companies.rememberBrands()
    // A ref in agent text opens its page; the error log records the screen each failure happened on.
    val refLinks = remember(navApi) {
        com.coinepro.hq.designsystem.RefLinks({ com.coinepro.hq.ui.v17.refRoute(it) != null }, { r -> com.coinepro.hq.ui.v17.refRoute(r)?.let(navApi::go) })
    }
    LaunchedEffect(route) { graph.errors.screen = route }

    CompositionLocalProvider(LocalNav provides navApi, LocalLive provides Live(streamState, last, feed.toList()), LocalBrands provides brands, com.coinepro.hq.designsystem.LocalRefLinks provides refLinks) {
        Column(Modifier.fillMaxSize()) {
            TopBar(
                back = !top,
                onBack = navApi::back,
                stream = streamState,
                demo = env.demo,
                urgent = (inbox.data?.notifications?.get("urgent") ?: 0) + (inbox.data?.notifications?.get("decision") ?: 0),
                onBell = { navApi.go("notifications") },
                onMore = { tools = true },
                onVoice = { voice = true },
            )
            offlineSince?.let { at ->
                Row(Modifier.fillMaxWidth().background(Divan.colors.softWarning).padding(horizontal = 16.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    com.coinepro.hq.designsystem.DIcon(DivanIcon.OFFLINE, size = 16.dp, tint = Divan.colors.warning)
                    Text("آفلاین؛ آخرین وضعیت از ${com.coinepro.hq.core.format.jDateTime(at)}. هیچ اقدامی آفلاین انجام نمیشود.", style = Divan.type.caption, color = Divan.colors.textPrimary)
                }
            }
            Box(Modifier.weight(1f)) {
                // Divan motion: a page pushed on top arrives from the reading side with the emphasised curve and leaves the same way on
                // back; switching between top-level places is a quiet cross-fade. Nothing moves when animations are removed.
                val reduced = com.coinepro.hq.designsystem.LocalReducedMotion.current
                NavHost(
                    nav, startDestination = "home",
                    enterTransition = {
                        when {
                            reduced -> EnterTransition.None
                            sideways() -> fadeIn(tween(Motion.MEDIUM, easing = Motion.Standard))
                            else -> fadeIn(tween(Motion.EMPHASISED, easing = Motion.Emphasised)) +
                                slideIntoContainer(AnimatedContentTransitionScope.SlideDirection.Start, tween(Motion.EMPHASISED, easing = Motion.Emphasised)) { it / 10 }
                        }
                    },
                    exitTransition = {
                        when {
                            reduced -> ExitTransition.None
                            sideways() -> fadeOut(tween(Motion.SHORT, easing = Motion.Exit))
                            else -> fadeOut(tween(Motion.MEDIUM, easing = Motion.Exit)) +
                                slideOutOfContainer(AnimatedContentTransitionScope.SlideDirection.Start, tween(Motion.EMPHASISED, easing = Motion.Emphasised)) { it / 24 }
                        }
                    },
                    popEnterTransition = {
                        when {
                            reduced -> EnterTransition.None
                            sideways() -> fadeIn(tween(Motion.MEDIUM, easing = Motion.Standard))
                            else -> fadeIn(tween(Motion.MEDIUM, easing = Motion.Standard)) +
                                slideIntoContainer(AnimatedContentTransitionScope.SlideDirection.End, tween(Motion.EMPHASISED, easing = Motion.Emphasised)) { it / 24 }
                        }
                    },
                    popExitTransition = {
                        when {
                            reduced -> ExitTransition.None
                            sideways() -> fadeOut(tween(Motion.SHORT, easing = Motion.Exit))
                            else -> fadeOut(tween(Motion.SHORT, easing = Motion.Exit)) +
                                slideOutOfContainer(AnimatedContentTransitionScope.SlideDirection.End, tween(Motion.MEDIUM, easing = Motion.Exit)) { it / 10 }
                        }
                    },
                ) {
                    composable("home") { HomeScreen(onNewOrder = { order = true }, onVoiceOrder = { voice = true }) }
                    composable("workshop") { WorkshopScreen(onNewSession = { newSession = true }, onGrant = { grantFor = it; granting = true }) }
                    composable("workshop/{ref}") { SessionScreen(it.arguments?.getString("ref").orEmpty()) }
                    composable("cartable") { CartableScreen() }
                    composable("cartable/{ref}") { DecisionScreen(it.arguments?.getString("ref").orEmpty()) }
                    composable("cartable-co/{company}") { CartableScreen(company0 = it.arguments?.getString("company")) }
                    composable("outputs") { OutputsScreen() }
                    composable("outputs/{ref}") { OutputScreen(it.arguments?.getString("ref").orEmpty()) }
                    composable("advisor") { com.coinepro.hq.ui.advisor.AdvisorScreen() }
                    composable("oversight") { OversightScreen() }
                    composable("oversight/chat") { ChatScreen("N", agent = "overseer") }
                    composable("assistant") { AssistantScreen() }
                    composable("stars") { StarsScreen() }
                    composable("founding") { FoundingsScreen() }
                    composable("founding/{ref}") { FoundingScreen(it.arguments?.getString("ref").orEmpty()) }
                    composable("skills") { SkillsScreen() }
                    composable("academy") { AcademyScreen() }
                    composable("tools") { ToolsScreen() }
                    composable("messages") { ThreadsScreen() }
                    composable("messages/{code}") { ChatScreen(it.arguments?.getString("code").orEmpty()) }
                    composable("companies") { CompaniesScreen() }
                    composable("companies/{code}") { CompanyScreen(it.arguments?.getString("code").orEmpty()) }
                    composable("employees/{code}") { EmployeeScreen(it.arguments?.getString("code").orEmpty()) }
                    composable("work/{id}") { WorkScreen(it.arguments?.getString("id").orEmpty()) }
                    composable("treasury") { TreasuryScreen() }
                    composable("planner") { PlannerScreen(onNewOrder = { order = true }) }
                    composable("notifications") { NotificationsScreen() }
                    composable("control") { ControlScreen() }
                    composable("audit") { AuditScreen() }
                    composable("resolutions") { com.coinepro.hq.ui.owner.ResolutionsScreen() }
                    composable("runs") { com.coinepro.hq.ui.owner.RunsScreen() }
                    composable("sites") { com.coinepro.hq.ui.owner.SitesScreen() }
                    composable("settings") { SettingsScreen(graph) }
                    composable("errors") { com.coinepro.hq.ui.settings.ErrorLogScreen(graph.errors) }
                    // ⟨1.5⟩ §19
                    composable("revenue") { com.coinepro.hq.ui.revenue.RevenueScreen() }
                    composable("support") { com.coinepro.hq.ui.support.SupportScreen() }
                    composable("support/{ref}") { com.coinepro.hq.ui.support.ConversationScreen(it.arguments?.getString("ref").orEmpty()) }
                    composable("growth") { com.coinepro.hq.ui.growth.GrowthScreen() }
                    composable("feedback") { com.coinepro.hq.ui.feedback.FeedbackScreen() }
                    // ⟨1.5⟩ §20
                    composable("meetings") { com.coinepro.hq.ui.meetings.MeetingsScreen() }
                    composable("meetings/{ref}") { com.coinepro.hq.ui.meetings.MeetingScreen(it.arguments?.getString("ref").orEmpty()) }
                    composable("charter") { com.coinepro.hq.ui.charter.CharterScreen() }
                    composable("knowledge") { com.coinepro.hq.ui.knowledge.KnowledgeScreen() }
                    composable("knowledge/{ref}") { com.coinepro.hq.ui.knowledge.KnowledgeScreen(open0 = it.arguments?.getString("ref")) }
                    composable("scorecard") { com.coinepro.hq.ui.scorecard.ScorecardScreen() }
                    composable("okr") { com.coinepro.hq.ui.okr.OkrScreen() }
                    composable("outcomes") { com.coinepro.hq.ui.outcomes.OutcomesScreen() }
                    composable("risks") { com.coinepro.hq.ui.risks.RisksScreen() }
                    composable("risks/{ref}") { com.coinepro.hq.ui.risks.RisksScreen(hi = it.arguments?.getString("ref")) }
                    composable("calendar") { com.coinepro.hq.ui.calendar.CalendarScreen() }
                    composable("authority") { com.coinepro.hq.ui.authority.AuthorityScreen() }
                    // ⟨1.5⟩ management tools (§21)
                    composable("notes") { com.coinepro.hq.ui.notes.NotesScreen() }
                    composable("notes/{ref}") { com.coinepro.hq.ui.notes.NotesScreen(highlight = it.arguments?.getString("ref")) }
                    composable("letter") { com.coinepro.hq.ui.letter.LetterScreen() }
                    composable("letter/{ref}") { com.coinepro.hq.ui.letter.LetterScreen(open0 = it.arguments?.getString("ref")) }
                    composable("substitutes") { com.coinepro.hq.ui.substitutes.SubstitutesScreen() }
                    composable("substitutes/{ref}") { com.coinepro.hq.ui.substitutes.SubstitutesScreen(creative0 = it.arguments?.getString("ref")) }
                    composable("digital-ceo") { com.coinepro.hq.ui.dceo.DigitalCeoScreen() }
                    // ⟨1.6⟩ the media studio and the legal counsel (§22)
                    composable("studio") { com.coinepro.hq.ui.studio.StudioScreen() }
                    composable("studio/{ref}") { com.coinepro.hq.ui.studio.StudioScreen(open0 = it.arguments?.getString("ref")) }
                    composable("series") { com.coinepro.hq.ui.studio.SeriesScreen() }
                    composable("series/{ref}") { com.coinepro.hq.ui.studio.SeriesScreen(focus0 = it.arguments?.getString("ref")) }
                    composable("voice") { com.coinepro.hq.ui.studio.VoiceScreen() }
                    composable("legal") { com.coinepro.hq.ui.legal.LegalScreen() }
                    composable("legal/{ref}") { com.coinepro.hq.ui.legal.CaseScreen(it.arguments?.getString("ref").orEmpty()) }
                    composable("roles/{ref}") { com.coinepro.hq.ui.org.RoleDraftScreen(it.arguments?.getString("ref").orEmpty()) }
                    // ⟨1.7⟩ the archive (§23)
                    composable("archive") { com.coinepro.hq.ui.archive.ArchiveScreen() }
                    composable("archive-in/{key}/{value}") { e ->
                        val k = e.arguments?.getString("key").orEmpty()
                        val v = e.arguments?.getString("value")
                        com.coinepro.hq.ui.archive.ArchiveScreen(party0 = v.takeIf { k == "party" }, folder0 = v.takeIf { k == "folder" })
                    }
                    composable("archive/{ref}") { com.coinepro.hq.ui.archive.RecordScreen(it.arguments?.getString("ref").orEmpty()) }
                    composable("archive-holds") { com.coinepro.hq.ui.archive.HoldsScreen() }
                    composable("archive-holds/{ref}") { com.coinepro.hq.ui.archive.HoldsScreen(focus0 = it.arguments?.getString("ref")) }
                    composable("archive-holds-new/{case}") { com.coinepro.hq.ui.archive.HoldsScreen(newFor = it.arguments?.getString("case")) }
                    composable("archive-reminders") { com.coinepro.hq.ui.archive.RemindersScreen() }
                    composable("archive-retention") { com.coinepro.hq.ui.archive.RetentionScreen() }
                    composable("archive-settings") { com.coinepro.hq.ui.archive.ArchiveSettingsScreen() }
                    composable("archive-settings/{tab}") { com.coinepro.hq.ui.archive.ArchiveSettingsScreen(tab0 = it.arguments?.getString("tab")) }
                    composable("archive-settings/{tab}/{ref}") { com.coinepro.hq.ui.archive.ArchiveSettingsScreen(tab0 = it.arguments?.getString("tab"), open0 = it.arguments?.getString("ref")) }
                }
            }
            BottomBar(route, inbox.data?.decisionsPending ?: 0, inbox.data?.messagesUnread ?: 0, listening = voice, onOrder = { voice = true }, onTypedOrder = { order = true }) { navApi.go(it) }
        }
        if (tools) {
            ModalBottomSheet(onDismissRequest = { tools = false }, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true), containerColor = Divan.colors.overlay) {
                ToolsSheet(outputs = inbox.data?.let { it.deliverablesUnseen ?: it.deliverablesUnrated } ?: 0, errors = graph.errors.entries.collectAsStateWithLifecycle().value.size) { r -> tools = false; navApi.go(r) }
            }
        }
        if (order) NewOrderSheet(onDismiss = { order = false })
        if (voice) VoiceOrderSheet(onDismiss = { voice = false })
        if (newSession) NewSessionSheet(onDismiss = { newSession = false })
        if (granting) GrantSheet(grantFor, onDismiss = { granting = false })
    }
}

/** Between two top-level places (tabs, the tools sheet's pages) the change is sideways: a cross-fade, not a push. */
private fun AnimatedContentTransitionScope<androidx.navigation.NavBackStackEntry>.sideways(): Boolean =
    initialState.destination.route in TOP && targetState.destination.route in TOP

@Composable
private fun TopBar(back: Boolean, onBack: () -> Unit, stream: StreamState, demo: Boolean, urgent: Int, onBell: () -> Unit, onMore: () -> Unit, onVoice: () -> Unit) {
    val c = Divan.colors
    Column(Modifier.fillMaxWidth().background(c.page).statusBarsPadding()) {
        Row(Modifier.fillMaxWidth().height(56.dp).padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            if (back) IconBtn(DivanIcon.BACK, "برگشت", onBack, tint = c.textPrimary)
            else {
                Spacer(Modifier.width(8.dp))
                Monogram(26.dp)
                Spacer(Modifier.width(8.dp))
                Text("ستاد", style = Divan.type.h3.copy(fontWeight = FontWeight.Bold))
            }
            if (demo) {
                Spacer(Modifier.width(8.dp))
                Box(Modifier.clip(CircleShape).background(c.softLearning).padding(horizontal = 8.dp, vertical = 2.dp)) {
                    Text("نمایشی", style = Divan.type.micro, color = c.learning)
                }
            }
            Spacer(Modifier.weight(1f))
            Box(
                Modifier.size(32.dp).semantics { contentDescription = if (stream == StreamState.LIVE) "استریم زنده وصل است" else "استریم قطع است" },
                contentAlignment = Alignment.Center,
            ) { LiveDot(if (stream == StreamState.LIVE) c.positive else c.warning, live = stream == StreamState.LIVE, size = 8.dp) }
            IconBtn(DivanIcon.MIC, "فرمان صوتی", onVoice, tint = c.goldInk)
            IconBtn(DivanIcon.BELL, "اعلان‌ها", onBell, badge = urgent)
            IconBtn(DivanIcon.MORE, "ابزارها", onMore)
        }
        HorizontalDivider(color = c.lineDivider, thickness = 1.dp)
    }
}

@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun BottomBar(route: String, decisions: Int, messages: Int, listening: Boolean, onOrder: () -> Unit, onTypedOrder: () -> Unit, go: (String) -> Unit) {
    val c = Divan.colors
    val current = route.substringBefore('/')
    Column(Modifier.fillMaxWidth().background(c.card)) {
        HorizontalDivider(color = c.lineDivider, thickness = 1.dp)
        Row(Modifier.fillMaxWidth().height(64.dp), verticalAlignment = Alignment.CenterVertically) {
            for (t in TABS) {
                val active = current == t.route || (t.route == "companies" && current in setOf("employees", "work"))
                if (t.route == "order") {
                    // The gold button: a tap opens the voice order and starts listening; a long press opens the order typed.
                    val haptic = androidx.compose.ui.platform.LocalHapticFeedback.current
                    val src = remember { androidx.compose.foundation.interaction.MutableInteractionSource() }
                    Box(Modifier.weight(1f), contentAlignment = Alignment.Center) {
                        Box(
                            Modifier
                                .offset(y = (-10).dp)
                                .size(60.dp)
                                .then(Modifier.pressScale(src, 0.94f))
                                // Not clipped: the listening glow reaches past the orb.
                                .background(c.card, CircleShape)
                                .combinedClickable(
                                    interactionSource = src,
                                    indication = androidx.compose.material3.ripple(bounded = false, radius = 30.dp),
                                    role = Role.Button,
                                    onClickLabel = "فرمان صوتی: بگو",
                                    onLongClickLabel = "فرمان نوشتنی",
                                    onLongClick = { haptic.performHapticFeedback(androidx.compose.ui.hapticfeedback.HapticFeedbackType.LongPress); onTypedOrder() },
                                    onClick = onOrder,
                                )
                                .semantics { contentDescription = "فرمان صوتی؛ نگه دار برای فرمان نوشتنی" },
                            contentAlignment = Alignment.Center,
                        ) {
                            // While the order is being spoken the orb breathes and a soft gold glow swells around it.
                            Orb(48.dp, state = if (listening) "listening" else "rest", label = "فرمان صوتی")
                            DIcon(DivanIcon.MIC, size = 22.dp, tint = c.onGold)
                        }
                    }
                    continue
                }
                val badge = when (t.badge) { "decisions" -> decisions; "messages" -> messages; else -> 0 }
                Column(
                    Modifier.weight(1f).clip(RoundedCornerShape(12.dp)).clickable(role = Role.Tab, onClickLabel = t.label) { go(t.route) }.padding(vertical = 6.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(2.dp),
                ) {
                    val tint by animateColorAsState(if (active) c.goldInk else c.textSecondary, motionShort(), label = "tab")
                    val ink by animateColorAsState(if (active) c.textPrimary else c.textSecondary, motionShort(), label = "tab-ink")
                    Box {
                        DIcon(t.icon, size = 24.dp, tint = tint, active = active)
                        if (badge > 0) Badge(badge, Modifier.align(Alignment.TopStart).offset(x = (-8).dp, y = (-6).dp))
                    }
                    Text(t.label, style = Divan.type.micro.copy(fontSize = 11.sp, lineHeight = 16.sp, fontWeight = if (active) FontWeight.SemiBold else FontWeight.Normal), color = ink)
                }
            }
        }
        Spacer(Modifier.navigationBarsPadding())
    }
}

@Composable
internal fun ToolsSheet(outputs: Int, errors: Int, go: (String) -> Unit) {
    Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp).padding(bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(20.dp)) {
        ToolGroup("سازمان", ORG, go)
        ToolGroup("ابزار مدیریت", MANAGEMENT, go)
        ToolGroup("رسانه و حقوقی", MEDIA, go)
        ToolGroup("بایگانی", ARCHIVE, go)
        ToolGroup("حاکمیت", GOVERNANCE, go)
        ToolGroup("ابزارها", TOOLS, go) { t -> when { t.route == "outputs" && outputs > 0 -> outputs; t.route == "errors" && errors > 0 -> errors; else -> null } }
    }
}

/** One group of the tools sheet: its header in the section style, then its rows on one card, separated by space, not lines. */
@Composable
private fun ToolGroup(title: String, tools: List<Tool>, go: (String) -> Unit, badge: (Tool) -> Int? = { null }) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(title, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted, modifier = Modifier.padding(horizontal = 4.dp).semantics { heading() })
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(c.card).padding(vertical = 4.dp)) {
            for (t in tools) ToolRow(t, badge(t), go)
        }
    }
}

@Composable
private fun ToolRow(t: Tool, badge: Int?, go: (String) -> Unit) {
    val c = Divan.colors
    Row(
        Modifier.fillMaxWidth().clickable(role = Role.Button) { go(t.route) }.padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(Modifier.size(36.dp).clip(RoundedCornerShape(10.dp)).background(c.tile), contentAlignment = Alignment.Center) { DIcon(t.icon, size = 20.dp, tint = c.textSecondary) }
        Text(t.label, style = Divan.type.body, modifier = Modifier.weight(1f))
        if (badge != null) Badge(badge)
        DIcon(DivanIcon.NEXT, size = 16.dp, tint = c.textMuted)
    }
}
