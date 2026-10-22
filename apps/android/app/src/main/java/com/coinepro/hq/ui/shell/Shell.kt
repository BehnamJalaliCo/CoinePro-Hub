package com.coinepro.hq.ui.shell

import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import com.coinepro.hq.designsystem.Monogram
import com.coinepro.hq.designsystem.Orb
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.Nav
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

private val TABS = listOf(
    Tab("home", "فرمان", DivanIcon.COMMAND),
    Tab("cartable", "کارتابل", DivanIcon.CARTABLE, "decisions"),
    Tab("advisor", "مشاور", DivanIcon.ADVISOR),
    Tab("companies", "شرکت‌ها", DivanIcon.COMPANIES),
    Tab("messages", "پیام‌ها", DivanIcon.MESSAGES, "messages"),
)

private data class Tool(val route: String, val label: String, val icon: DivanIcon)

/** The organisation beside the advisor (contract §18): the overseer and the assistant first, then what they run. */
private val ORG = listOf(
    Tool("oversight", "ناظر کل", DivanIcon.OVERSEER),
    Tool("assistant", "دستیار", DivanIcon.ASSISTANT),
    Tool("stars", "ستاره‌ها", DivanIcon.STAR),
    Tool("founding", "تأسیس شرکت", DivanIcon.FOUND),
    Tool("skills", "مهارت‌ها", DivanIcon.SKILL),
    Tool("academy", "آکادمی", DivanIcon.ACADEMY),
    Tool("tools", "ابزارها و اینترنت", DivanIcon.GLOBE),
)

private val TOOLS = listOf(
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
)

private val TOP = TABS.map { it.route }.toSet() + ORG.map { it.route } + TOOLS.map { it.route }

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

    CompositionLocalProvider(LocalNav provides navApi, LocalLive provides Live(streamState, last, feed.toList())) {
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
                NavHost(nav, startDestination = "home", enterTransition = { fadeIn(tween(200)) }, exitTransition = { fadeOut(tween(120)) }) {
                    composable("home") { HomeScreen(onNewOrder = { order = true }, onVoiceOrder = { voice = true }) }
                    composable("workshop") { WorkshopScreen(onNewSession = { newSession = true }, onGrant = { grantFor = it; granting = true }) }
                    composable("workshop/{ref}") { SessionScreen(it.arguments?.getString("ref").orEmpty()) }
                    composable("cartable") { CartableScreen() }
                    composable("cartable/{ref}") { DecisionScreen(it.arguments?.getString("ref").orEmpty()) }
                    composable("outputs") { OutputsScreen() }
                    composable("outputs/{ref}") { OutputScreen(it.arguments?.getString("ref").orEmpty()) }
                    composable("advisor") { ChatScreen("A", advisor = true, headerAction = { InquiriesAction() }) }
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
                }
            }
            BottomBar(route, inbox.data?.decisionsPending ?: 0, inbox.data?.messagesUnread ?: 0) { navApi.go(it) }
        }
        if (tools) {
            ModalBottomSheet(onDismissRequest = { tools = false }, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true), containerColor = Divan.colors.overlay) {
                ToolsSheet(unrated = inbox.data?.deliverablesUnrated ?: 0) { r -> tools = false; navApi.go(r) }
            }
        }
        if (order) NewOrderSheet(onDismiss = { order = false })
        if (voice) VoiceOrderSheet(onDismiss = { voice = false })
        if (newSession) NewSessionSheet(onDismiss = { newSession = false })
        if (granting) GrantSheet(grantFor, onDismiss = { granting = false })
    }
}

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

@Composable
private fun BottomBar(route: String, decisions: Int, messages: Int, go: (String) -> Unit) {
    val c = Divan.colors
    val current = route.substringBefore('/')
    Column(Modifier.fillMaxWidth().background(c.card)) {
        HorizontalDivider(color = c.lineDivider, thickness = 1.dp)
        Row(Modifier.fillMaxWidth().height(64.dp), verticalAlignment = Alignment.CenterVertically) {
            for (t in TABS) {
                val active = current == t.route || (t.route == "companies" && current in setOf("employees", "work"))
                if (t.route == "advisor") {
                    Box(Modifier.weight(1f), contentAlignment = Alignment.Center) {
                        Box(
                            Modifier
                                .offset(y = (-10).dp)
                                .size(60.dp)
                                .clip(CircleShape)
                                .background(c.card)
                                .clickable(role = Role.Tab, onClickLabel = t.label) { go(t.route) }
                                .semantics { contentDescription = "مشاور کل" },
                            contentAlignment = Alignment.Center,
                        ) { Orb(48.dp, state = if (active) "listening" else "rest") }
                    }
                    continue
                }
                val badge = when (t.badge) { "decisions" -> decisions; "messages" -> messages; else -> 0 }
                Column(
                    Modifier.weight(1f).clip(RoundedCornerShape(12.dp)).clickable(role = Role.Tab, onClickLabel = t.label) { go(t.route) }.padding(vertical = 6.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(2.dp),
                ) {
                    Box {
                        DIcon(t.icon, size = 24.dp, tint = if (active) c.goldInk else c.textSecondary, active = active)
                        if (badge > 0) Badge(badge, Modifier.align(Alignment.TopStart).offset(x = (-8).dp, y = (-6).dp))
                    }
                    Text(t.label, style = Divan.type.micro.copy(fontSize = 11.sp, fontWeight = if (active) FontWeight.SemiBold else FontWeight.Normal), color = if (active) c.textPrimary else c.textSecondary)
                }
            }
        }
        Spacer(Modifier.navigationBarsPadding())
    }
}

@Composable
private fun ToolsSheet(unrated: Int, go: (String) -> Unit) {
    Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp).padding(bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text("سازمان", style = Divan.type.h3, modifier = Modifier.padding(bottom = 8.dp))
        for (t in ORG) ToolRow(t, null, go)
        Text("ابزارها", style = Divan.type.h3, modifier = Modifier.padding(top = 12.dp, bottom = 8.dp))
        for (t in TOOLS) ToolRow(t, if (t.route == "outputs" && unrated > 0) unrated else null, go)
    }
}

@Composable
private fun ToolRow(t: Tool, badge: Int?, go: (String) -> Unit) {
    val c = Divan.colors
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).clickable(role = Role.Button) { go(t.route) }.padding(horizontal = 12.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        DIcon(t.icon, tint = c.textSecondary)
        Text(t.label, style = Divan.type.body, modifier = Modifier.weight(1f))
        if (badge != null) Badge(badge)
        DIcon(DivanIcon.NEXT, size = 18.dp, tint = c.textMuted)
    }
}
