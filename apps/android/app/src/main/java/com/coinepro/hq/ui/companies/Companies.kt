package com.coinepro.hq.ui.companies

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
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
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/** Companies are data: the holding first, then every company with its own mark and live counts. */
@Composable
fun CompaniesScreen() {
    val nav = LocalNav.current
    val c = Divan.colors
    val q = rememberQuery("companies", "companies", maxAgeMs = 30_000) { companies() }
    val r = refresher(q)
    var adding by rememberSaveable { mutableStateOf(false) }
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            PageHeader("شرکت‌ها", eyebrow = "هلدینگ و شرکت‌هایش") {
                com.coinepro.hq.designsystem.HqButton("شرکت تازه", { adding = true }, size = com.coinepro.hq.designsystem.BtnSize.SM, icon = DivanIcon.ADD)
                com.coinepro.hq.designsystem.HqButton("تأسیس از ریپو یا ایده", { nav.go("founding") }, size = com.coinepro.hq.designsystem.BtnSize.SM, variant = com.coinepro.hq.designsystem.BtnVariant.TEXT, icon = DivanIcon.FOUND)
            }
        }
        val list = q.data?.sortedBy { if (it.kind == "holding") 0 else 1 }
        when {
            list == null && q.error == null -> items(3) { Skeleton(Modifier.fillMaxWidth().height(120.dp), radius = 16.dp) }
            list == null -> item { ErrorBlock(q.error, { q.refresh() }) }
            else -> items(list, key = { it.code }) { co -> CompanyCard(co) { nav.go("companies/${co.code}") } }
        }
    }
    if (adding) com.coinepro.hq.ui.owner.NewCompanySheet { adding = false }
}

@Composable
private fun CompanyCard(co: Company, onClick: () -> Unit) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth(), onClick = onClick, tahrir = co.kind == "holding") {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            Box(Modifier.size(52.dp).clip(CircleShape).background(c.tile).border(1.dp, if (co.killSwitch == "engaged") c.negative else c.lineStrong, CircleShape), contentAlignment = Alignment.Center) {
                if (co.kind == "holding") com.coinepro.hq.designsystem.Monogram(26.dp) else CompanyMark(co.code, height = 22.dp, ink = c.textPrimary)
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(co.nameFa ?: co.code, style = Divan.type.bodyStrong)
                Text(buildAnnotatedString { fig(co.nameEn ?: co.code); append(" · "); fig(co.code) }, style = Divan.type.micro, color = c.textMuted)
            }
            when {
                co.killSwitch == "engaged" -> Pill("متوقف", Tone.NEG, icon = DivanIcon.PAUSE)
                co.deployFreezeUntil != null -> Pill("توقف deploy", Tone.WARN, icon = DivanIcon.PAUSE)
                else -> Pill("فعال", Tone.POS, dot = true)
            }
        }
        Row(Modifier.padding(top = 14.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Count("کارمند فعال", co.counts.employeesActive, Modifier.weight(1f))
            Count("کار باز", co.counts.workOpen, Modifier.weight(1f))
            Count("منتظر مُهر", co.counts.decisionsPending, Modifier.weight(1f), gold = co.counts.decisionsPending > 0)
        }
    }
}

@Composable
private fun Count(label: String, n: Int, modifier: Modifier, gold: Boolean = false) {
    val c = Divan.colors
    Column(modifier.clip(RoundedCornerShape(12.dp)).background(c.tile).padding(10.dp)) {
        Text(n.toString(), style = Divan.type.h3, color = if (gold) c.goldInk else c.textPrimary)
        Text(label, style = Divan.type.micro, color = c.textMuted)
    }
}

/** One company: departments, people (org chart) and its open work. */
@Composable
fun CompanyScreen(code: String) {
    val nav = LocalNav.current
    val c = Divan.colors
    val co = rememberQuery("company:$code", "companies") { company(code) }
    val depts = rememberQuery("departments:$code", "companies") { departments(code) }
    val chart = rememberQuery("chart:$code", "employees") { orgChart(code) }
    val work = rememberQuery("work:company:$code", "work") { work(company = code) }
    var tab by rememberSaveable { mutableStateOf("departments") }
    val r = refresher(co, depts, chart, work)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            Loadable(co) { x ->
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                    Seal(x.code, x.nameFa ?: x.code, x.nameEn ?: x.code, holding = x.kind == "holding", size = 84.dp)
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text(x.nameFa ?: x.code, style = Divan.type.h1)
                        Text(buildAnnotatedString { fig(x.nameEn ?: ""); append(" · "); fig(x.code) }, style = Divan.type.caption, color = c.textMuted)
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            if (x.killSwitch == "engaged") Pill("متوقف", Tone.NEG, icon = DivanIcon.PAUSE) else Pill("فعال", Tone.POS, dot = true)
                            x.deployFreezeUntil?.let { Pill("توقف deploy · ${until(it)}", Tone.WARN, icon = DivanIcon.PAUSE) }
                        }
                    }
                }
            }
        }
        item {
            Segmented(listOf(SegOption("departments", "دپارتمان‌ها"), SegOption("people", "کارمندها"), SegOption("work", "کارها")), tab, { tab = it }, Modifier.fillMaxWidth())
        }
        when (tab) {
            "departments" -> {
                val list = depts.data
                if (list == null) item { Loadable(depts) { } }
                else items(list.sortedBy { it.sort }, key = { it.code }) { d ->
                    HqCard(Modifier.fillMaxWidth()) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            Box(Modifier.size(40.dp).clip(RoundedCornerShape(12.dp)).background(c.tile), contentAlignment = Alignment.Center) { DIcon(DEPT_ICON[d.code] ?: DivanIcon.DEPARTMENT, size = 20.dp, tint = c.silverInk) }
                            Column(Modifier.weight(1f)) {
                                Text(d.nameFa, style = Divan.type.bodyStrong)
                                val n = chart.data?.roots?.flatMap { listOf(it) + it.children }?.count { it.department == d.code } ?: 0
                                Text("${d.managerTitleFa}، $n نفر", style = Divan.type.caption, color = c.textMuted)
                            }
                        }
                    }
                }
            }
            "people" -> item {
                Loadable(chart) { ch ->
                    if (ch.roots.isEmpty()) Empty("هنوز کسی استخدام نشده", icon = DivanIcon.HIRE, body = "پیشنهادهای استخدام در کارتابل منتظر مُهر تو هستند.")
                    else HqCard(Modifier.fillMaxWidth()) {
                        SectionTitle("چارت سازمانی")
                        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) { ch.roots.forEach { Node(it, 0) { code -> nav.go("employees/$code") } } }
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
}

@Composable
private fun Node(n: ChartNode, depth: Int, open: (String) -> Unit) {
    val c = Divan.colors
    Row(
        Modifier.fillMaxWidth().padding(start = (depth * 22).dp).clip(RoundedCornerShape(12.dp)).clickable(role = Role.Button) { open(n.code) }.padding(vertical = 8.dp, horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Avatar(agentKindOf(n.code, n.kind), dept = n.department, size = 40.dp, state = n.activity)
        Column(Modifier.weight(1f)) {
            Text(n.displayName ?: n.titleFa, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
            Text(buildAnnotatedString { fig(n.code); append("، " + (ACTIVITY[n.activity] ?: n.activity)) }, style = Divan.type.micro, color = c.textMuted)
        }
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
            Text(buildAnnotatedString { fig(w.ref); append("، ${w.assignee?.titleFa ?: "بدون مسئول"}، ${ago(w.updatedAt)}") }, style = Divan.type.micro, color = c.textMuted, maxLines = 1)
        }
        Fig(w.priority, style = Divan.type.figureSmall, color = if (w.priority <= "P1") c.negative else c.textMuted)
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
                        Avatar(agentKindOf(e.code, e.kind), dept = e.department, size = 72.dp, state = e.activity)
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(e.displayName ?: e.titleFa, style = Divan.type.h2)
                            Text(buildAnnotatedString { fig(e.code); append(" · " + (EMPLOYEE_KIND[e.kind] ?: e.kind)) }, style = Divan.type.caption, color = c.textMuted)
                            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                Pill(ACTIVITY[e.activity] ?: e.activity, if (e.activity == "working") Tone.GOLD else if (e.activity == "error") Tone.NEG else Tone.SILVER, live = e.activity == "working")
                                if (e.status != "active") Pill(com.coinepro.hq.ui.owner.EMPLOYEE_STATUS[e.status] ?: e.status, if (e.status == "dismissed") Tone.NEG else Tone.WARN)
                            }
                        }
                    }
                    com.coinepro.hq.ui.owner.EmployeeActions(e) { q.refresh() }
                    e.activityNote?.let { Text("الان: $it", style = Divan.type.small, color = c.textSecondary) }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Box(Modifier.weight(1f)) { com.coinepro.hq.designsystem.StatTile("نمره", e.score.value?.let { faDecimal(it) } ?: "—", figure = false, sub = e.score.rankInDepartment?.let { "رتبه‌ی $it در دپارتمان" }) }
                        Box(Modifier.weight(1f)) { com.coinepro.hq.designsystem.StatTile("میانگین امتیاز تو", e.score.ownerAvg?.let { faDecimal(it) } ?: "—", figure = false) }
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

/** One piece of work: brief, progress, budget, the delegation chain and its events. */
@Composable
fun WorkScreen(id: String) {
    val nav = LocalNav.current
    val c = Divan.colors
    val q = rememberQuery("work:$id", "work") { workOne(id) }
    val wid = q.data?.id
    val ev = if (wid != null) rememberQuery("work:events:$wid", "work") { workEvents(wid) } else null
    val runs = if (wid != null) rememberQuery("runs:work:$wid", "runs", "work", maxAgeMs = 15_000) { workRuns(wid) } else null
    val r = refresher(*listOfNotNull(q, ev, runs).toTypedArray())
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            Loadable(q) { w ->
                Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            CompanyMark(w.company, height = 13.dp, mono = true, ink = c.textSecondary)
                            Fig(w.ref, style = Divan.type.figureSmall, color = c.textMuted)
                            Text(WORK_KIND[w.kind] ?: w.kind, style = Divan.type.micro, color = c.textMuted)
                        }
                        Text(w.title, style = Divan.type.h2)
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Pill(WORK_STATUS[w.status] ?: w.status, if (w.status == "in_progress") Tone.GOLD else Tone.SILVER, live = w.status == "in_progress")
                            Pill(w.priority, if (w.priority <= "P1") Tone.NEG else Tone.NEUTRAL, figure = true)
                            if (w.overdue) Pill("دیرکرد", Tone.NEG, icon = DivanIcon.URGENT)
                            w.dueAt?.let { Pill("موعد: ${jDateTime(it)}", Tone.NEUTRAL, icon = DivanIcon.TIME) }
                        }
                        com.coinepro.hq.ui.owner.WorkActions(w) { q.set(it) }
                    }
                    w.progressPct?.let { p ->
                        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Row { Text("پیشرفت", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.weight(1f)); Text("$p٪", style = Divan.type.caption) }
                            MeterBar(p.toDouble(), tone = com.coinepro.hq.designsystem.BarTone.GOLD)
                            w.progressNote?.let { Text(it, style = Divan.type.caption, color = c.textSecondary) }
                        }
                    }
                    if (w.brief.isNotBlank()) HqCard(Modifier.fillMaxWidth()) { SectionTitle("شرح کار"); Md(w.brief, Modifier.padding(top = 6.dp)) }
                    HqCard(Modifier.fillMaxWidth()) {
                        SectionTitle("بودجه")
                        Row(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                            Column { Text("توکن", style = Divan.type.micro, color = c.textMuted); Fig("${tokens(w.budget.tokensUsed)} / ${tokens(w.budget.tokens)}") }
                            Column { Text("دلار معادل", style = Divan.type.micro, color = c.textMuted); Fig("${usd(w.budget.usdUsed)} / ${usd(w.budget.usd)}") }
                        }
                        w.budget.tokens?.let { lim -> MeterBar(w.budget.tokensUsed * 100.0 / lim.coerceAtLeast(1), Modifier.padding(top = 10.dp), tone = com.coinepro.hq.designsystem.budgetTone(w.budget.tokensUsed * 100.0 / lim.coerceAtLeast(1))) }
                    }
                    if (w.chain.isNotEmpty()) HqCard(Modifier.fillMaxWidth()) {
                        SectionTitle("مسیر ارجاع", note = "از فرمان تو تا مجری؛ عمق حداکثر ۲")
                        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            w.chain.forEach { s ->
                                Row(Modifier.fillMaxWidth().padding(start = (s.depth * 18).dp).clickable(enabled = s.assignee != null) { s.assignee?.let { nav.go("employees/${it.code}") } }, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                    Avatar(s.assignee?.let { agentKindOf(it.code, it.kind) } ?: "employee", dept = s.assignee?.department, size = 32.dp)
                                    Column(Modifier.weight(1f)) {
                                        Text(s.assignee?.titleFa ?: "—", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                                        Text(WORK_STATUS[s.status] ?: s.status, style = Divan.type.micro, color = c.textMuted)
                                    }
                                    Fig("${tokens(s.tokensUsed)} · ${usd(s.usdUsed)}", style = Divan.type.figureSmall, color = c.textMuted)
                                }
                            }
                        }
                    }
                    runs?.let { rq ->
                        HqCard(Modifier.fillMaxWidth()) {
                            SectionTitle("اجرای ایجنت‌ها روی این کار", note = "هر اجرا با قدم‌ها و ابزارهایش")
                            Column(Modifier.padding(top = 10.dp)) { Loadable(rq) { list -> com.coinepro.hq.ui.owner.RunList(list, "هنوز ایجنتی روی این کار اجرا نشده.", withSteps = true) } }
                        }
                    }
                    val events = ev?.data?.items.orEmpty()
                    if (events.isNotEmpty()) HqCard(Modifier.fillMaxWidth()) {
                        SectionTitle("رویدادها")
                        events.forEach { e ->
                            Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                Text(jDateTime(e.at), style = Divan.type.micro, color = c.textMuted, modifier = Modifier.width(96.dp))
                                Fig(e.kind, style = Divan.type.figureSmall, modifier = Modifier.weight(1f))
                                Fig(e.actorCode, style = Divan.type.figureSmall, color = c.textMuted)
                            }
                        }
                    }
                    Text("ساخته‌شده توسط ${actorFa(w.createdBy)}، ${ago(w.createdAt)}", style = Divan.type.micro, color = c.textMuted)
                }
            }
        }
    }
}
