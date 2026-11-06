package com.coinepro.hq.ui.companies

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.ACTIVITY
import com.coinepro.hq.core.format.DEPT_ICON
import com.coinepro.hq.core.format.EMPLOYEE_KIND
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.WORK_KIND
import com.coinepro.hq.core.format.WORK_STATUS
import com.coinepro.hq.core.format.actorFa
import com.coinepro.hq.core.format.agentKindOf
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.faDecimal
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.format.modelLabel
import com.coinepro.hq.core.format.tokens
import com.coinepro.hq.core.format.until
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.core.net.ChartNode
import com.coinepro.hq.core.net.Company
import com.coinepro.hq.core.net.Employee
import com.coinepro.hq.core.net.Work
import com.coinepro.hq.designsystem.Avatar
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.MeterBar
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Seal
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.Loadable
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.itemMotion
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/** Companies are data: the holding first, then every company, each with its live state at a glance (running, stopped, deploys
 *  closed), whether its agents are working right now, today's spend and its counts, and the switches to stop, resume, close or open
 *  deploys (contract §9). A long press opens every action on the company. */
@Composable
fun CompaniesScreen() {
    val nav = LocalNav.current
    val env = com.coinepro.hq.ui.LocalEnv.current
    val q = rememberQuery("companies", "companies", maxAgeMs = 30_000) { companies() }
    val d = rememberControlData()
    val ui = rememberControlUi()
    val r = refresher(q)
    Page(onRefresh = { r.refresh(); env.cache.invalidate("control", "runs", "treasury") }, refreshing = r.refreshing) {
        item(key = "header") {
            PageHeader("شرکت‌ها", eyebrow = "هلدینگ و شرکت‌هایش، زنده") {
                // One way to a new company: the founding wizard (an idea, a repository, or registered only).
                com.coinepro.hq.designsystem.HqButton("تأسیس شرکت", { nav.go("founding/new") }, size = com.coinepro.hq.designsystem.BtnSize.SM, icon = DivanIcon.FOUND)
            }
        }
        val list = q.data
        when {
            list == null && q.error == null -> items(3, key = { "skeleton-$it" }) { Skeleton(Modifier.fillMaxWidth().height(if (it == 0) 236.dp else 222.dp), radius = 16.dp) }
            list == null -> item(key = "error") { ErrorBlock(q.error, { q.refresh() }) }
            else -> {
                val holding = list.firstOrNull { it.kind == "holding" }
                if (holding != null) item(key = holding.code) {
                    HoldingControlCard(holding, list, d, ui, itemMotion()) { nav.go("companies/${holding.code}") }
                }
                items(list.filter { it.kind != "holding" && it.status != "archived" }, key = { it.code }) { co ->
                    CompanyControlCard(co, d, ui, holding?.nameFa, itemMotion()) { nav.go("companies/${co.code}") }
                }
                // An archived company (one with a history the owner no longer runs) stays reachable, apart, without its switches.
                val archived = list.filter { it.status == "archived" }
                if (archived.isNotEmpty()) item(key = "archived") {
                    HqCard(Modifier.fillMaxWidth()) {
                        SectionTitle("بایگانی‌شده", note = "سوابقشان میماند؛ در گزارش‌ها و ستاره‌ها نیستند")
                        Column(Modifier.padding(top = 6.dp)) {
                            for (co in archived) Row(
                                Modifier.fillMaxWidth().clickable(role = Role.Button) { nav.go("companies/${co.code}") }.padding(vertical = 8.dp),
                                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
                            ) {
                                com.coinepro.hq.designsystem.CompanyMark(co.code, height = 14.dp, mono = true, ink = Divan.colors.textMuted)
                                Text(co.nameFa ?: co.code, style = Divan.type.small, color = Divan.colors.textSecondary, modifier = Modifier.weight(1f))
                            }
                        }
                    }
                }
            }
        }
    }
    ControlSheets(ui)
}

/** One company: departments, people (org chart), its open work and ⟨1.4.6⟩ its brand and seal (not the holding's: fixed).
 *  ⟨1.6⟩ §22.1: a department opens with its mandate, identity and the roles its manager wrote ([dept0]); [role0] opens a draft. */
@Composable
fun CompanyScreen(code: String, tab0: String = "control", dept0: String? = null, role0: String? = null, kind0: String? = null) {
    val nav = LocalNav.current
    val c = Divan.colors
    val d = rememberControlData()
    val ui = rememberControlUi()
    val co = rememberQuery("company:$code", "companies") { company(code) }
    val depts = rememberQuery("departments:$code", "companies") { departments(code) }
    val chart = rememberQuery("chart:$code", "employees") { orgChart(code) }
    val work = rememberQuery("work:company:$code", "work") { work(company = code) }
    var tab by rememberSaveable { mutableStateOf(if (role0 != null) "people" else if (tab0 == "tech") "servers" else tab0) }
    var dept by rememberSaveable { mutableStateOf(dept0) }
    var role by rememberSaveable { mutableStateOf(role0) }
    val r = refresher(co, depts, chart, work)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            Loadable(co) { x ->
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                    Seal(x.code, x.nameFa ?: x.code, x.nameEn ?: x.code, holding = x.kind == "holding", size = 84.dp)
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text(x.nameFa ?: x.code, style = Divan.type.h1)
                        x.nameEn?.takeIf { it.isNotBlank() && it != x.code }?.let { Text(buildAnnotatedString { fig(it) }, style = Divan.type.caption, color = c.textMuted) }
                        val st = d.state(x.code, x.kind == "holding", x)
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            // Running or stopped, and the deploys on their own chip when they are closed.
                            StateChip(st.copy(freeze = null), d.busy(x.code))
                            st.freeze?.let { Pill("انتشار نسخه بسته، ${until(it.until)}", Tone.WARN, icon = DivanIcon.LOCK) }
                        }
                    }
                }
            }
        }
        item {
            val brand = co.data?.let { it.kind != "holding" } == true
            // ⟨control⟩ the control room first: the owner opens a company to see it and steer it.
            com.coinepro.hq.designsystem.ScrollRow {
                // ⟨1.11⟩ §29: the business first (its working groups and the connections that measure them); the technical (servers, the
                // catalogue, technical findings) lives under «فنی» only.
                (listOf("control" to "اتاق کنترل") + (if (brand) listOf("growth" to "کارگروه‌ها", "connections" to "اتصال‌ها") else emptyList()) +
                    // ⟨1.12⟩ §30 the company's production lines (hidden once the hub is known not to serve them).
                    (if (brand && com.coinepro.hq.ui.v29.served(com.coinepro.hq.core.net.HubFeature.LINES)) listOf("lines" to "خط تولید") else emptyList()) +
                    // ⟨1.13⟩ §31 the owned channel, search rank with competitors, and ad budgets.
                    (if (brand && com.coinepro.hq.ui.v29.served(com.coinepro.hq.core.net.HubFeature.GROWTH)) listOf("newsletter" to "خبرنامه", "seo" to "سئو و رقبا", "ads" to "تبلیغات") else emptyList()) +
                    // ⟨1.15⟩ §33 its money, sales, personas and journey.
                    (if (brand && com.coinepro.hq.ui.v29.served(com.coinepro.hq.core.net.HubFeature.MONEY)) listOf("money" to "پول", "sales" to "فروش") else emptyList()) +
                    (if (brand && com.coinepro.hq.ui.v29.served(com.coinepro.hq.core.net.HubFeature.JOURNEY)) listOf("personas" to "مخاطب‌ها", "journey" to "مسیر") else emptyList()) +
                    listOf("departments" to "دپارتمان‌ها", "people" to "کارمندها", "work" to "کارها") +
                    // ⟨1.17⟩ the holding's «فنی» holds every technical place the owner's tools no longer show.
                    (if (brand) listOf("servers" to "فنی", "brand" to "نشان و مُهر") else listOf("servers" to "فنی")))
                    .forEach { (k, l) -> com.coinepro.hq.designsystem.FilterChip(l, tab == k, { tab = k }) }
                // The company's conversations: the messages page, opened on this company's section.
                com.coinepro.hq.designsystem.FilterChip("پیام‌ها", false, { nav.go("messages-co/$code") })
            }
        }
        when (tab) {
            "control" -> if (co.data == null && co.error != null) item(key = "control-error") { ErrorBlock(co.error, { co.refresh() }) } else controlRoom(co.data, d, ui)
            "departments" -> {
                // ⟨1.5⟩ §21.5: the departments' rank and the latest monthly HR round.
                item { com.coinepro.hq.ui.people.DepartmentRanks(code) }
                item { com.coinepro.hq.ui.people.HrRoundLine(code) }
                val list = depts.data
                if (list == null) item { Loadable(depts) { } }
                else items(list.sortedBy { it.sort }, key = { it.code }) { d ->
                    HqCard(Modifier.fillMaxWidth(), onClick = { dept = d.code }) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            Box(Modifier.size(40.dp).clip(RoundedCornerShape(12.dp)).background(c.tile), contentAlignment = Alignment.Center) { DIcon(DEPT_ICON[d.code] ?: DivanIcon.DEPARTMENT, size = 20.dp, tint = c.silverInk) }
                            Column(Modifier.weight(1f)) {
                                Text(d.nameFa, style = Divan.type.bodyStrong)
                                val n = chart.data?.roots?.flatMap { listOf(it) + it.children }?.count { it.department == d.code } ?: 0
                                Text("${d.managerTitleFa}، $n نفر", style = Divan.type.caption, color = c.textMuted)
                                // ⟨1.6⟩ §22.1: where the department must arrive.
                                d.mandate?.let { m -> Text("مقصد: ${m.toFa}", style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis) }
                            }
                            DIcon(DivanIcon.NEXT, size = 16.dp, tint = c.textMuted)
                        }
                    }
                }
            }
            // ⟨1.8⟩ §26: the company's servers, under the holding's control; ⟨1.11⟩ §29.1 with everything technical of the company.
            "servers", "tech" -> item(key = "servers") { com.coinepro.hq.ui.v29.CompanyTech(code, holding = co.data?.kind == "holding") }
            // ⟨1.11⟩ §29.9, §29.11 its working groups and readiness; §29.12 its connections.
            "growth" -> item(key = "growth") { com.coinepro.hq.ui.v29.CompanyGroups(code) }
            "connections" -> item(key = "connections") { com.coinepro.hq.ui.v29.CompanyConnections(code, kind0) }
            // ⟨1.12⟩ §30.5 its lines, and «خط تازه» from a template.
            "lines" -> item(key = "lines") { com.coinepro.hq.ui.v30.CompanyLines(code) }
            "newsletter" -> item(key = "newsletter") { com.coinepro.hq.ui.v31.CompanyNewsletter(code) }
            "seo" -> item(key = "seo") { com.coinepro.hq.ui.v31.CompanySeo(code) }
            "ads" -> item(key = "ads") { com.coinepro.hq.ui.v31.CompanyAds(code) }
            "money" -> item(key = "money") { com.coinepro.hq.ui.v33.CompanyMoney(code) }
            "sales" -> item(key = "sales") { com.coinepro.hq.ui.v33.CompanySales(code) }
            "personas" -> item(key = "personas") { com.coinepro.hq.ui.v33.CompanyPersonas(code) }
            "journey" -> item(key = "journey") { com.coinepro.hq.ui.v33.CompanyJourney(code) }
            "brand" -> item {
                Loadable(co) { x -> HqCard(Modifier.fillMaxWidth()) { BrandBlock(x.code, x.nameFa ?: x.code, x.nameEn ?: x.code) } }
            }
            "people" -> {
              // ⟨1.6⟩ §22.5: roles a department's manager wrote beyond the template.
              item { com.coinepro.hq.ui.org.RolesOnDemand(code) { role = it } }
              item {
                Loadable(chart) { ch ->
                    if (ch.roots.isEmpty()) Empty("هنوز کسی استخدام نشده", icon = DivanIcon.HIRE, body = "پیشنهادهای استخدام در کارتابل منتظر مُهر تو هستند.")
                    else HqCard(Modifier.fillMaxWidth()) {
                        SectionTitle("چارت سازمانی")
                        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) { ch.roots.forEach { Node(it, 0) { code -> nav.go("employees/$code") } } }
                    }
                }
              }
            }
            else -> {
                val list = work.data?.items
                when {
                    list == null -> item { Loadable(work) { } }
                    list.isEmpty() -> item { Empty("کار بازی نیست", icon = DivanIcon.TASK) }
                    else -> item {
                        HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(horizontal = 12.dp, vertical = 6.dp)) {
                            list.forEachIndexed { i, w ->
                                if (i > 0) HorizontalDivider(color = c.lineDivider)
                                WorkRow(w) { nav.go("work/${w.id}") }
                            }
                        }
                    }
                }
            }
        }
    }
    dept?.let { dc ->
        val d = depts.data?.firstOrNull { it.code == dc }
        com.coinepro.hq.ui.v14.HqSheet({ dept = null }, d?.nameFa ?: dc, ref = dc) { com.coinepro.hq.ui.org.DepartmentView(code, dc) { role = it } }
    }
    role?.let { r -> com.coinepro.hq.ui.v14.HqSheet({ role = null }, "نقش تازه", ref = r) { com.coinepro.hq.ui.org.RoleDraftView(r) } }
    ControlSheets(ui)
}

@Composable
private fun Node(n: ChartNode, depth: Int, open: (String) -> Unit) {
    val c = Divan.colors
    Row(
        Modifier.fillMaxWidth().padding(start = (depth * 22).dp).clip(RoundedCornerShape(12.dp)).clickable(role = Role.Button) { open(n.code) }.padding(vertical = 8.dp, horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Avatar(agentKindOf(n.code, n.kind), dept = n.department, size = 40.dp, state = n.state?.let { com.coinepro.hq.core.data.avatarStateOf(it) } ?: n.activity)
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(n.displayName ?: n.titleFa, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
            n.displayName?.takeIf { it != n.titleFa }?.let { Text(n.titleFa, style = Divan.type.micro, color = c.textMuted) }
            // ⟨1.11⟩ §29.14 why it is stuck, in the owner's words.
            n.stuck?.takeIf { n.state == "stuck" }?.let { Text(com.coinepro.hq.designsystem.timesFig(it.reasonFa), style = Divan.type.micro, color = c.negative, maxLines = 2) }
        }
        // ⟨1.11⟩ §29.14 idle · thinking · working · waiting · stuck · done.
        com.coinepro.hq.ui.v29.EmployeeStatePill(n.state, n.activity)
    }
    n.children.forEach { Node(it, depth + 1, open) }
}

@Composable
fun WorkRow(w: Work, onClick: () -> Unit) {
    val c = Divan.colors
    Row(
        Modifier.fillMaxWidth().clickable(role = Role.Button, onClick = onClick).padding(vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Box(Modifier.size(8.dp).clip(CircleShape).background(when { w.overdue -> c.negative; w.status == "in_progress" -> c.goldFill; w.status in setOf("done", "delivered") -> c.positive; else -> c.silverInk }))
        Column(Modifier.weight(1f)) {
            Text(w.title, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text("${w.assignee?.titleFa ?: "بدون مسئول"}، ${ago(w.updatedAt)}", style = Divan.type.micro, color = c.textMuted, maxLines = 1)
        }
        com.coinepro.hq.ui.work.PriorityTag(w.priority, compact = true)
        Text(WORK_STATUS[w.status] ?: w.status, style = Divan.type.micro, color = c.textSecondary)
    }
}

/** One agent: medallion, role, model, score and recent ratings and work. */
@Composable
fun EmployeeScreen(code: String) {
    val nav = LocalNav.current
    val c = Divan.colors
    val q = rememberQuery("employee:$code", "employees") { employee(code) }
    val runs = rememberQuery("runs:employee:$code", "runs", maxAgeMs = 15_000) { runs(employee = code, limit = 20) }
    val r = refresher(q, runs)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            Loadable(q) { e: Employee ->
                Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                        Avatar(agentKindOf(e.code, e.kind), dept = e.department, size = 72.dp, state = e.state?.let { com.coinepro.hq.core.data.avatarStateOf(it) } ?: e.activity)
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(e.displayName ?: e.titleFa, style = Divan.type.h2)
                            Text(listOfNotNull(e.titleFa.takeIf { e.displayName != null && it != e.displayName }, EMPLOYEE_KIND[e.kind] ?: e.kind).joinToString(" · "), style = Divan.type.caption, color = c.textMuted)
                            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                // ⟨1.11⟩ §29.14 the employee's state (the older activity when the hub has none).
                                com.coinepro.hq.ui.v29.EmployeeStatePill(e.state, e.activity)
                                if (e.status != "active") Pill(com.coinepro.hq.ui.owner.EMPLOYEE_STATUS[e.status] ?: e.status, if (e.status == "dismissed") Tone.NEG else Tone.WARN)
                            }
                        }
                    }
                    e.stuck?.takeIf { e.state == "stuck" }?.let { com.coinepro.hq.ui.v29.StuckLine(it, e.company) }
                    com.coinepro.hq.ui.owner.EmployeeActions(e) { q.refresh() }
                    e.activityNote?.let { Text("الان: $it", style = Divan.type.small, color = c.textSecondary) }
                    // Two tiles of one height, their lines on the same baselines.
                    com.coinepro.hq.designsystem.StatRow {
                        com.coinepro.hq.designsystem.StatTile("نمره", e.score.value?.let { faDecimal(it) } ?: "—", Modifier.weight(1f), figure = false, sub = e.score.rankInDepartment?.let { "رتبه‌ی $it در دپارتمان" } ?: "—", count = true)
                        com.coinepro.hq.designsystem.StatTile("میانگین امتیاز تو", e.score.ownerAvg?.let { faDecimal(it) } ?: "—", Modifier.weight(1f), figure = false, sub = "از امتیازهای ۱ تا ۱۰ تو")
                    }
                    HqCard(Modifier.fillMaxWidth()) {
                        Text("مدل", style = Divan.type.caption, color = c.textMuted)
                        Fig("${modelLabel(e.model?.model)} · ${e.model?.effort ?: "—"}", style = Divan.type.figure)
                        Spacer(Modifier.height(8.dp))
                        Text("استخدام: ${jDate(e.hiredAt, withYear = true)}", style = Divan.type.caption, color = c.textMuted)
                        e.reportsTo?.let { Text("گزارش به: ${it.titleFa}", style = Divan.type.caption, color = c.textMuted) }
                    }
                    val duties = e.duties.mapNotNull { (it as? JsonPrimitive)?.contentOrNull }
                    if (duties.isNotEmpty()) HqCard(Modifier.fillMaxWidth()) {
                        SectionTitle("وظیفه‌ها")
                        Md(duties.joinToString("\n") { "- $it" }, Modifier.padding(top = 6.dp))
                    }
                    // ⟨1.5⟩ §21.5: this employee in the latest monthly HR round.
                    com.coinepro.hq.ui.people.HrCard(e.code, e.company)
                    com.coinepro.hq.ui.academy.TrainingCard(e.code)
                    HqCard(Modifier.fillMaxWidth()) {
                        SectionTitle("اجراهای اخیر", note = "قدم‌ها، ابزارها و مصرف هر اجرا")
                        Column(Modifier.padding(top = 10.dp)) {
                            Loadable(runs) { page -> com.coinepro.hq.ui.owner.RunList(page.items, "هنوز اجرایی ثبت نشده.", showEmployee = false) }
                        }
                    }
                    if (e.recentRatings.isNotEmpty()) HqCard(Modifier.fillMaxWidth()) {
                        SectionTitle("امتیازهای اخیر تو")
                        e.recentRatings.forEach { rt ->
                            Row(Modifier.fillMaxWidth().clickable { nav.go("outputs/${rt.deliverable}") }.padding(vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                Fig(rt.deliverable, style = Divan.type.figureSmall, color = c.goldInk)
                                Text("${rt.score} از ۱۰", style = Divan.type.small, modifier = Modifier.weight(1f))
                                Text(ago(rt.ratedAt), style = Divan.type.micro, color = c.textMuted)
                            }
                        }
                    }
                }
            }
        }
    }
}

/** One piece of work: the order's tracker (stage, estimate, who holds it, its outputs), brief, budget, the delegation chain, the live
 *  timeline of its events and runs, and the runs themselves. */
@Composable
fun WorkScreen(id: String) {
    val nav = LocalNav.current
    val c = Divan.colors
    val env = com.coinepro.hq.ui.LocalEnv.current
    val q = rememberQuery("work:$id", "work") { workOne(id) }
    // ⟨1.17⟩ §35.1 the root work of an owner's order is its session: the same page, its talk and its plan, not a second place.
    val orders = rememberQuery("voice-orders", "orders", maxAgeMs = 10_000) { orders().items }
    val w0 = q.data
    val sessionRef = w0?.takeIf { com.coinepro.hq.ui.v29.served(com.coinepro.hq.core.net.HubFeature.ORDER_REPORT) && com.coinepro.hq.core.data.isOwnerOrder(it) && it.depth == 0 }
        ?.let { x -> orders.data?.firstOrNull { o -> o.routes.any { it.workRef == x.ref } }?.ref }
    if (sessionRef != null) { com.coinepro.hq.ui.session.OrderSessionScreen(sessionRef); return }
    val wid = q.data?.id
    androidx.compose.runtime.LaunchedEffect(q.data) { q.data?.let(env.works::seed) }
    val track = if (wid != null) com.coinepro.hq.ui.work.rememberTrack(wid, full = true) else null
    val r = refresher(*listOfNotNull(q, track).toTypedArray())
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            Loadable(q) { w ->
                Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            CompanyMark(w.company, height = 13.dp, mono = true, ink = c.textSecondary)
                            Text(WORK_KIND[w.kind] ?: w.kind, style = Divan.type.micro, color = c.textMuted)
                        }
                        Text(w.title, style = Divan.type.h2)
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Pill(WORK_STATUS[w.status] ?: w.status, if (w.status == "in_progress") Tone.GOLD else Tone.SILVER, live = w.status == "in_progress")
                            com.coinepro.hq.ui.work.PriorityTag(w.priority)
                            // ⟨1.9⟩ §27: who plays it.
                            com.coinepro.hq.ui.work.PlayerTag(w.player, w.mode)
                            if (w.overdue) Pill("دیرکرد", Tone.NEG, icon = DivanIcon.URGENT)
                            w.dueAt?.let { Pill("موعد: ${jDateTime(it)}", Tone.NEUTRAL, icon = DivanIcon.TIME) }
                        }
                        com.coinepro.hq.ui.owner.WorkActions(w) { q.set(it) }
                    }
                    when (val t = track?.data) {
                        null -> Skeleton(Modifier.fillMaxWidth().height(196.dp), radius = 16.dp)
                        else -> com.coinepro.hq.ui.work.OrderTrackerCard(t)
                    }
                    // ⟨1.11⟩ §29.2 the order's report: receipt, plan, steps, what blocks it and the end summary.
                    com.coinepro.hq.ui.v29.OrderReportOnWork(w)
                    // ⟨1.9⟩ §27.2: the council of models, live.
                    if (w.mode == "council") com.coinepro.hq.ui.work.CouncilCard(w)
                    w.progressPct?.let { p ->
                        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Row { Text("گزارش پیشرفت مجری", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.weight(1f)); Text("$p٪", style = Divan.type.caption) }
                            MeterBar(p.toDouble(), tone = com.coinepro.hq.designsystem.BarTone.GOLD)
                            w.progressNote?.let { Text(it, style = Divan.type.caption, color = c.textSecondary) }
                        }
                    }
                    if (w.brief.isNotBlank()) HqCard(Modifier.fillMaxWidth()) { SectionTitle("شرح کار"); com.coinepro.hq.ui.Selectable { Md(w.brief, Modifier.padding(top = 6.dp)) } }
                    // ⟨1.17⟩ §34.4 the money it cost, in dollars (money is meant); no tokens, no depth, no runs.
                    HqCard(Modifier.fillMaxWidth()) {
                        SectionTitle("خرج این کار")
                        Fig(if (w.budget.usd == null) usd(w.budget.usdUsed) else "${usd(w.budget.usdUsed)} / ${usd(w.budget.usd)}", Modifier.padding(top = 8.dp))
                        val used = w.budget.usdUsed.toDoubleOrNull() ?: 0.0
                        w.budget.usd?.toDoubleOrNull()?.takeIf { it > 0 }?.let { lim -> MeterBar(used * 100.0 / lim, Modifier.padding(top = 10.dp), tone = com.coinepro.hq.designsystem.budgetTone(used * 100.0 / lim)) }
                    }
                    if (w.chain.isNotEmpty()) HqCard(Modifier.fillMaxWidth()) {
                        SectionTitle("چه کسانی رویش کار میکنند", note = "از فرمان تو تا کسی که انجامش میدهد")
                        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            w.chain.forEach { s ->
                                Row(Modifier.fillMaxWidth().padding(start = (s.depth * 18).dp).clickable(enabled = s.assignee != null) { s.assignee?.let { nav.go("employees/${it.code}") } }, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                    Avatar(s.assignee?.let { agentKindOf(it.code, it.kind) } ?: "employee", dept = s.assignee?.department, size = 32.dp)
                                    Column(Modifier.weight(1f)) {
                                        Text(s.assignee?.titleFa ?: "—", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                                        Text(WORK_STATUS[s.status] ?: s.status, style = Divan.type.micro, color = c.textMuted)
                                    }
                                }
                            }
                        }
                    }
                    track?.data?.let { com.coinepro.hq.ui.work.TimelineCard(it) }
                    Text("ساخته‌شده توسط ${actorFa(w.createdBy)}، ${ago(w.createdAt)}", style = Divan.type.micro, color = c.textMuted)
                }
            }
        }
    }
}

/** ⟨1.17⟩ «فنی» of the tools sheet: the holding's company page, opened on its «فنی» tab (servers, workshop, errors and the rest). */
@Composable
fun HoldingTechScreen() {
    val companies = com.coinepro.hq.ui.rememberCompanies()
    val holding = companies.firstOrNull { it.kind == "holding" }?.code
    if (holding == null) Box(Modifier.fillMaxWidth().padding(16.dp)) { Skeleton(Modifier.fillMaxWidth().height(120.dp), radius = 16.dp) }
    else CompanyScreen(holding, tab0 = "servers")
}
