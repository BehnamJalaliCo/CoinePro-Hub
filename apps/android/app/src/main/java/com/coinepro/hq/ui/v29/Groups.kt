package com.coinepro.hq.ui.v29

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.continuity
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.testTag
import com.coinepro.hq.designsystem.facts
import com.coinepro.hq.designsystem.stagger
import com.coinepro.hq.ui.look.Fold
import com.coinepro.hq.ui.look.GroupHeader
import com.coinepro.hq.ui.look.MemberHead
import com.coinepro.hq.ui.look.QuietLink
import com.coinepro.hq.ui.look.RunDots
import com.coinepro.hq.ui.look.StateWord
import com.coinepro.hq.core.data.connectionKindFa
import com.coinepro.hq.core.data.figureText
import com.coinepro.hq.core.data.fixRoute
import com.coinepro.hq.core.data.numberText
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.format.roleFa
import com.coinepro.hq.core.net.Experiment
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.Membership
import com.coinepro.hq.core.net.Readiness
import com.coinepro.hq.core.net.WorkGroup
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Chevron
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Expand
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Radius
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Loadable
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.itemMotion
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery

// Contract §29.9 and §29.11 ⟨1.11⟩: the working groups (growth groups) as data. A group has a purpose, seats, routines that run on their
// schedule, KPIs read from the connections, and a weekly experiment per company; every eligible company joins by itself and the owner
// may pause one. Each company's readiness for a group is a list of checks, each green or not, with its fix.
// ⟨1.0.1⟩ Part C (C3.4): the group's page opens with its member companies as tiles and each routine's last seven runs as dots; its
// run history and its definition are folded; nothing on it is gold (a state is a shape and a word, a warning carries its sign).

@Composable
fun rememberGroups() = rememberQuery("groups", "groups", maxAgeMs = 60_000) { gated(HubFeature.GROUPS) { groups() } }

/** «کارگروه‌ها»: every working group, what it is for, its seats and routines, and whether it is on. */
@Composable
fun GroupsScreen() {
    val nav = LocalNav.current
    val c = Divan.colors
    val q = rememberGroups()
    val r = refresher(q)
    val has = served(HubFeature.GROUPS)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("کارگروه‌ها", eyebrow = "رشد، محتوا و انتشار؛ هر شرکت با کارمندهای خودش") }
        val list = q.data
        when {
            !has -> item { Empty("کارگروه‌ها با به‌روزرسانی بعدی هاب میایند", icon = DivanIcon.DEPARTMENT) }
            list == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            list == null -> item { Skeleton(Modifier.fillMaxWidth().height(160.dp), radius = 16.dp) }
            list.isEmpty() -> item { Empty("هنوز کارگروهی تعریف نشده", icon = DivanIcon.DEPARTMENT) }
            else -> items(list, key = { it.key }) { g ->
                Box(itemMotion()) {
                    HqCard(Modifier.fillMaxWidth().continuity("groups/${g.key}"), onClick = { nav.go("groups/${g.key}") }) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            // ⟨1.0.1⟩ C0.1: a group's mark is silver; its state is a shape and a word.
                            IconTile(DivanIcon.DEPARTMENT, c.silverInk, c.tile)
                            Column(Modifier.weight(1f)) {
                                Text(plain(g.titleFa), style = Divan.type.bodyStrong)
                                Text(
                                    remember(g) { facts("${g.seats.sumOf { it.count }} صندلی", "${g.routines.size} روال", "${g.kpis.size} شاخص") },
                                    style = Divan.type.caption, color = c.textMuted,
                                )
                            }
                            StateWord(if (g.state == "on") "on" else "off", if (g.state == "on") "روشن" else "خاموش")
                        }
                        if (g.purposeFa.isNotBlank()) Para(g.purposeFa, Modifier.padding(top = 10.dp))
                    }
                }
            }
        }
    }
}

/**
 * A group's page (C3.4): its member companies as tiles (state, last run, next run, the work line; a member that stands still with
 * its reason and «راه بینداز»), each routine with its last seven runs as dots, the figures and the week's experiment, then what is
 * read only when wanted, folded: «سابقه‌ی اجرا» and «تعریف کارگروه» (its purpose, its connections, its seats and who fills them);
 * last, each member's readiness. The header folds to the title and the state (M18).
 */
@Composable
fun GroupScreen(key: String) {
    val q = rememberQuery("group:$key", "groups", maxAgeMs = 60_000) { gated(HubFeature.GROUPS) { group(key) } }
    val members = rememberQuery("group:$key:members", "groups", maxAgeMs = 30_000) { gated(HubFeature.GROUPS) { groupMembers(key) } }
    val runs = rememberQuery("group:$key:runs", "groups", maxAgeMs = 30_000) { gated(HubFeature.GROUPS) { groupRuns(key) } }
    val kpis = rememberQuery("group:$key:kpis", "groups", maxAgeMs = 60_000) { gated(HubFeature.GROUPS) { groupKpis(key) } }
    val exps = rememberQuery("group:$key:experiments", "groups", maxAgeMs = 60_000) { gated(HubFeature.GROUPS) { groupExperiments(key) } }
    val r = refresher(q, members, runs, kpis, exps)
    val listState = androidx.compose.foundation.lazy.rememberLazyListState()
    val collapse = com.coinepro.hq.designsystem.rememberCollapse(listState)
    val g = q.data
    Column(Modifier.fillMaxSize()) {
        // ⟨1.0.1⟩ M14: the card of the list grows into this header.
        if (g != null) GroupHeader(
            { collapse.value }, "کارگروه‌ها", g.titleFa, Modifier.continuity("groups/${g.key}"),
            state = { StateWord(if (g.state == "on") "on" else "off", if (g.state == "on") "روشن" else "خاموش") },
            facts = {
                Text(
                    remember(g) { facts("${g.seats.sumOf { it.count }} صندلی", "${g.routines.size} روال", "${g.kpis.size} شاخص") },
                    style = Divan.type.caption, color = Divan.colors.textMuted,
                )
            },
        )
        Box(Modifier.weight(1f)) {
            Page(onRefresh = r::refresh, refreshing = r.refreshing, state = listState) {
                when {
                    g == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
                    g == null -> item { Skeleton(Modifier.fillMaxWidth().height(220.dp), radius = 16.dp) }
                    else -> {
                        item(key = "members") { MemberTiles(g, members.data.orEmpty(), members.data == null, runs.data) { members.refresh() } }
                        item(key = "routines") { RoutinesCard(g, runs.data, live = members.data.orEmpty().any { it.state == "on" }) }
                        item(key = "kpis") { KpisCard(g, kpis.data, kpis.data == null && kpis.error == null) }
                        item(key = "experiments") { ExperimentsCard(exps.data) }
                        item(key = "runs") { Fold("سابقه‌ی اجرا", runs.data?.let { rs -> remember(rs) { facts("${rs.size} نوبت") } }, tag = "group-runs") { RunsList(g, runs.data) } }
                        item(key = "definition") {
                            Fold("تعریف کارگروه", remember(g) { facts(*com.coinepro.hq.core.data.sealSummary(g.seats.sumOf { it.count }, g.routines.size, g.connections.size).toTypedArray()) }, tag = "group-definition") {
                                Definition(g, members.data.orEmpty())
                            }
                        }
                        val list = members.data.orEmpty()
                        if (list.isNotEmpty()) item(key = "ready-title") { SectionTitle("آمادگی هر شرکت", note = "هر بررسی سبز یا نه، با دکمه‌ی اصلاحش") }
                        items(list, key = { "ready-${it.company}" }) { m -> ReadinessCard(m.company, g.key, collapsed = true, quietFix = true) }
                    }
                }
            }
        }
    }
}

/** The member companies as tiles: state, last run, next run, how many of its seats are filled; «مکث» while it works, and when it
 *  stands still its one-line reason with «راه بینداز». */
@Composable
private fun MemberTiles(g: WorkGroup, list: List<Membership>, loading: Boolean, runs: List<com.coinepro.hq.core.net.RoutineRun>?, onChanged: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val companies = rememberCompanies()
    val next = remember(g.routines) { com.coinepro.hq.core.data.soonestRun(g.routines.filter { it.state == "on" }.map { it.schedule }) }
    Column(Modifier.testTag("group-members"), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SectionTitle("شرکت‌های عضو", note = if (g.eligible == "has_channel") "هر شرکتی که کانال انتشار دارد خودش عضو میشود" else "همه‌ی شرکت‌ها عضو میشوند")
        when {
            loading -> Skeleton(Modifier.fillMaxWidth().height(96.dp), radius = 16.dp)
            list.isEmpty() -> Text("هنوز شرکتی عضو نشده.", style = Divan.type.caption, color = c.textMuted)
            else -> list.forEachIndexed { i, m ->
                val action = rememberAction()
                val on = m.state == "on"
                val name = companyOf(companies, m.company).nameFa
                fun set(state: String, said: String) = action.run {
                    env.api.setGroupMember(g.key, m.company, state)
                    env.cache.invalidate("groups", "home")
                    toasts.ok(said)
                    onChanged()
                }
                Column(
                    Modifier.fillMaxWidth().stagger(i).testTag("member-tile").clip(RoundedCornerShape(16.dp)).background(c.card).padding(14.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    MemberHead(
                        m.company, name, on, com.coinepro.hq.core.data.memberLook(m.company, on, runs), runsKnown = runs != null, next = next.takeIf { on },
                        onStart = { set("on", "کارگروه در $name دوباره راه افتاد.") }, starting = action.busy && !on,
                        action = if (on) ({ QuietLink("مکث", { set("paused", "این شرکت در کارگروه مکث کرد.") }) }) else null,
                    )
                    val filled = m.seats.count { it.employee != null }
                    if (m.seats.isNotEmpty()) Text("$filled از ${m.seats.size} صندلی پر است", style = Divan.type.micro, color = c.textMuted)
                }
            }
        }
    }
}

/** Each seat of the group and, per member company, who fills it (or that it is empty: filled by code when hiring is automatic). */
@Composable
private fun SeatsList(g: WorkGroup, members: List<Membership>) {
    val c = Divan.colors
    val nav = LocalNav.current
    val employees = rememberQuery("employees:all", "employees", maxAgeMs = 60_000) { employees().items }.data.orEmpty()
    Column {
        g.seats.forEachIndexed { i, s ->
            if (i > 0) HorizontalDivider(color = c.lineDivider)
            Column(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(plain(s.titleFa.ifBlank { roleFa(s.role) }), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), modifier = Modifier.weight(1f))
                    if (s.count > 1) Text("${s.count} نفر", style = Divan.type.micro, color = c.textMuted)
                }
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    for (m in members) {
                        val who = m.seats.firstOrNull { it.seat == s.seat }?.employee
                        val e = employees.firstOrNull { it.code == who }
                        Row(
                            Modifier.clip(RoundedCornerShape(Radius.small)).background(c.tile)
                                .then(if (who != null) Modifier.clickable(role = Role.Button) { nav.go("employees/$who") } else Modifier)
                                .padding(horizontal = 8.dp, vertical = 5.dp),
                            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
                        ) {
                            com.coinepro.hq.designsystem.CompanyMark(m.company, height = 11.dp, mono = true, ink = c.textSecondary)
                            Text(e?.let { it.displayName ?: it.titleFa } ?: if (who != null) "پر" else "خالی", style = Divan.type.micro, color = if (who != null) c.textPrimary else c.textMuted, maxLines = 1)
                            if (e != null) EmployeeStatePill(e.state, e.activity)
                        }
                    }
                }
                // Why an empty seat stays empty, and what fixes it (no silence, 2026-11-05): said with its sign, never a colour alone.
                for (m in members) {
                    val b = m.seats.firstOrNull { it.seat == s.seat && it.employee == null }?.blocked ?: continue
                    Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        DIcon(DivanIcon.URGENT, size = 13.dp, tint = c.warning, modifier = Modifier.padding(top = 2.dp))
                        com.coinepro.hq.designsystem.CompanyMark(m.company, height = 11.dp, mono = true, ink = c.textSecondary)
                        Text("${b.whyFa} ${b.fixFa}".trim(), style = Divan.type.micro, color = c.textSecondary, modifier = Modifier.weight(1f))
                    }
                }
            }
        }
    }
}

/** What the group is, read whole: its purpose, the connections it reads from, its seats and who fills them. */
@Composable
private fun Definition(g: WorkGroup, members: List<Membership>) {
    val c = Divan.colors
    if (g.purposeFa.isNotBlank()) Para(g.purposeFa)
    if (g.connections.isNotEmpty()) Text(
        plain("از این اتصال‌ها میخواند: " + g.connections.joinToString("، ") { connectionKindFa(it) }),
        style = Divan.type.caption, color = c.textMuted,
    )
    if (g.seats.isNotEmpty()) Column {
        Text("صندلی‌ها", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
        Text("هر صندلی یک نقش؛ خالی‌ها با استخدام خودکار پر میشوند", style = Divan.type.micro, color = c.textMuted)
        SeatsList(g, members)
    }
}

/** Each KPI of the group, one line per member company. */
@Composable
private fun KpisCard(g: WorkGroup, series: List<com.coinepro.hq.core.net.KpiSeries>?, loading: Boolean) {
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("شاخص‌ها", note = "از اتصال‌ها، هر روز؛ روز بی‌عدد خالی میماند")
        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            when {
                loading -> Skeleton(Modifier.fillMaxWidth().height(180.dp), radius = 12.dp)
                g.kpis.isEmpty() -> Text("این کارگروه هنوز شاخصی ندارد.", style = Divan.type.caption, color = Divan.colors.textMuted)
                else -> for (k in g.kpis) {
                    val mine = series.orEmpty().filter { it.key == k.key }
                    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text(plain(k.titleFa), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                        CompanyKpiChart(mine.map { it.company to it.series }, label = k.titleFa, fmt = { numberText(it, k.unit) }, unit = k.unit)
                    }
                }
            }
        }
    }
}

/** Each routine with its last seven runs as dots, when it runs, whose it is and its next turn; «مکث» or «ادامه», quiet. */
@Composable
private fun RoutinesCard(g: WorkGroup, runs: List<com.coinepro.hq.core.net.RoutineRun>?, live: Boolean) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    Column(Modifier.testTag("routine-runs"), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SectionTitle("روال‌ها", note = if (runs != null) "هفت نوبت آخر هر روال" else "هر کدام سر وقتش برای کارمند همان صندلی یک کار کوچک میسازد")
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(c.card).padding(horizontal = 16.dp)) {
            if (g.routines.isEmpty()) Text("روالی تعریف نشده.", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.padding(vertical = 12.dp))
            g.routines.forEachIndexed { i, rt ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                val action = rememberAction()
                val on = rt.state == "on"
                Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            Text(plain(rt.titleFa), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, modifier = Modifier.weight(1f))
                            if (runs != null) RunDots(runs.filter { it.routine == rt.key }, rt.titleFa)
                        }
                        val seat = g.seats.firstOrNull { it.seat == rt.seat }
                        val next = if (live && on) com.coinepro.hq.core.data.nextRun(rt.schedule) else null
                        Text(
                            remember(rt, seat, next) {
                                com.coinepro.hq.ui.look.factsWhen(
                                    listOf(com.coinepro.hq.core.data.routineTimeFa(rt.schedule).takeIf { rt.schedule.isNotBlank() }, seat?.let { it.titleFa.ifBlank { roleFa(it.role) } }, "مکث".takeIf { !on }),
                                    "نوبت بعد", next,
                                )
                            },
                            style = Divan.type.caption, color = c.textSecondary,
                        )
                    }
                    HqButton(if (on) "مکث" else "ادامه", {
                        action.run {
                            env.api.setRoutine(g.key, rt.key, if (on) "paused" else "on")
                            env.cache.invalidate("groups")
                            toasts.ok(if (on) "این روال مکث کرد." else "این روال دوباره روشن شد.")
                        }
                    }, variant = BtnVariant.TEXT, size = BtnSize.SM, loading = action.busy)
                }
            }
        }
    }
}

/** The routines' runs, newest first: which company, which routine, what it said, when, and how it ended. */
@Composable
private fun RunsList(g: WorkGroup, runs: List<com.coinepro.hq.core.net.RoutineRun>?) {
    val nav = LocalNav.current
    val c = Divan.colors
    Column {
        when {
            runs == null -> Skeleton(Modifier.fillMaxWidth().height(80.dp))
            runs.isEmpty() -> Text("هنوز اجرایی نبوده.", style = Divan.type.caption, color = c.textMuted)
            else -> runs.sortedByDescending { it.at }.take(12).forEachIndexed { i, x ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                Row(
                    Modifier.fillMaxWidth().then(x.workRef?.let { ref -> Modifier.clickable(role = Role.Button) { nav.go("work/$ref") } } ?: Modifier).padding(vertical = 9.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    com.coinepro.hq.designsystem.CompanyMark(x.company, height = 11.dp, mono = true, ink = c.textSecondary)
                    Column(Modifier.weight(1f)) {
                        Text(plain(g.routines.firstOrNull { it.key == x.routine }?.titleFa ?: x.routine), style = Divan.type.small, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        if (x.noteFa.isNotBlank()) Text(plain(x.noteFa), style = Divan.type.micro, color = if (x.state == "failed") c.negative else c.textMuted, maxLines = 2)
                    }
                    Text(remember(x) { facts(com.coinepro.hq.core.data.RUN_FA[x.state] ?: x.state, ago(x.at)) }, style = Divan.type.micro, color = c.textMuted)
                }
            }
        }
    }
}

/** The week's experiment of each company: the hypothesis, the figure it is judged by, the target, the result and whether it stays. */
@Composable
private fun ExperimentsCard(list: List<Experiment>?) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("آزمایش هفته", note = "هر هفته برای هر شرکت یکی؛ تحلیلگر مینویسد و با عدد بسته میشود")
        Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            when {
                list == null -> Skeleton(Modifier.fillMaxWidth().height(80.dp))
                list.isEmpty() -> Text("آزمایشی ثبت نشده.", style = Divan.type.caption, color = c.textMuted)
                else -> for (x in list.sortedByDescending { it.week }.take(6)) {
                    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(Radius.tile)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            CoName(x.company, Modifier.weight(1f))
                            Text(plain("هفته‌ی ${jDate(x.week)}"), style = Divan.type.micro, color = c.textMuted)
                            when (x.kept) {
                                true -> Pill("ماند", Tone.POS, dot = true)
                                false -> Pill("کنار رفت", Tone.SILVER, dot = true)
                                null -> Pill("در جریان", Tone.SILVER, dot = true)
                            }
                        }
                        Text(plain(x.hypothesisFa), style = Divan.type.small.copy(textAlign = TextAlign.Justify), color = c.textPrimary)
                        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            Text(plain("هدف: ${figureText(x.target)}"), style = Divan.type.caption, color = c.textSecondary)
                            Text(plain("نتیجه: ${figureText(x.result)}"), style = Divan.type.caption, color = c.textSecondary)
                        }
                    }
                }
            }
        }
    }
}

/** A company's readiness for a group: ready or not, each check green or not, a failed one with its fix. [collapsed] shows the head
 *  and opens on a tap (the group page lists every member); [quietFix] draws the fixes outlined, where a page lists several cards
 *  and none of them is the page's one gold (C0.1). */
@Composable
fun ReadinessCard(company: String, group: String, collapsed: Boolean = false, title: String? = null, quietFix: Boolean = false) {
    val nav = LocalNav.current
    val c = Divan.colors
    val q = rememberQuery("readiness:$company:$group", "readiness", "groups", "connections", maxAgeMs = 60_000) { gated(HubFeature.READINESS) { readiness(company, group) } }
    if (!served(HubFeature.READINESS)) return
    var open by rememberSaveable("$company:$group") { mutableStateOf(!collapsed) }
    val name = companyOf(rememberCompanies(), company).nameFa
    HqCard(Modifier.fillMaxWidth()) {
        Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).clickable(role = Role.Button) { open = !open },
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            com.coinepro.hq.designsystem.CompanyMark(company, height = 14.dp, mono = true, ink = c.textSecondary)
            Column(Modifier.weight(1f)) {
                Text(plain(title ?: "آمادگی $name"), style = Divan.type.bodyStrong)
                q.data?.let { r -> Text("${r.checks.count { it.ok }} از ${r.checks.size} بررسی سبز", style = Divan.type.micro, color = c.textMuted) }
            }
            // ⟨1.0.1⟩ C0.1: a warning carries its own sign, never a colour alone
            q.data?.let { r -> if (r.ready) Pill("آماده", Tone.POS, dot = true) else Pill("هنوز نه", Tone.WARN, icon = DivanIcon.URGENT) }
            Chevron(open, tint = c.textMuted)
        }
        Expand(open) {
            Box(Modifier.padding(top = 10.dp)) {
                Loadable(q, skeleton = { Skeleton(Modifier.fillMaxWidth().height(120.dp)) }) { r -> if (r != null) Checks(r, company, quietFix) }
            }
        }
    }
}

@Composable
private fun Checks(r: Readiness, company: String, quietFix: Boolean) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        for (k in r.checks) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                DIcon(if (k.ok) DivanIcon.SEAL else DivanIcon.URGENT, size = 16.dp, tint = if (k.ok) c.positive else c.warning, modifier = Modifier.padding(top = 2.dp))
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(plain(k.titleFa), style = Divan.type.small, color = c.textPrimary)
                    if (k.detailFa.isNotBlank()) Text(plain(k.detailFa), style = Divan.type.micro, color = c.textMuted)
                }
                if (!k.ok) k.fix?.let { f ->
                    if (fixRoute(f, company) != null) FixButton(f, company, null, variant = if (quietFix) BtnVariant.SECONDARY else BtnVariant.PRIMARY)
                }
            }
        }
    }
}

/** The company's «رشد» tab: each working group with its readiness and the way to the group. */
@Composable
fun CompanyGroups(code: String) {
    val nav = LocalNav.current
    val q = rememberGroups()
    if (!served(HubFeature.GROUPS)) {
        Empty("کارگروه‌ها با به‌روزرسانی بعدی هاب میایند", icon = DivanIcon.DEPARTMENT)
        return
    }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Loadable(q) { list ->
            if (list.isNullOrEmpty()) Empty("هنوز کارگروهی تعریف نشده", icon = DivanIcon.DEPARTMENT)
            else {
                for (g in list) Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    SectionTitle(g.titleFa, note = g.purposeFa.lineSequence().firstOrNull()?.take(90)) {
                        HqButton("کارگروه", { nav.go("groups/${g.key}") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.NEXT)
                    }
                    ReadinessCard(code, g.key, title = "آمادگی برای ${g.titleFa}")
                }
            }
        }
    }
}
