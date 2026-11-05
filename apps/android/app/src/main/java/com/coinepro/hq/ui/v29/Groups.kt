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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.RUN_STATE_FA
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
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.Md
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

@Composable
fun rememberGroups() = rememberQuery("groups", "groups", maxAgeMs = 60_000) { gated(HubFeature.GROUPS) { groups() } }

/** «کارگروه‌ها»: every working group, what it is for, its seats and routines, and how many companies are in it. */
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
                    HqCard(Modifier.fillMaxWidth(), onClick = { nav.go("groups/${g.key}") }) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            IconTile(DivanIcon.DEPARTMENT, c.goldInk, c.softGold)
                            Column(Modifier.weight(1f)) {
                                Text(plain(g.titleFa), style = Divan.type.bodyStrong)
                                Text("${g.seats.sumOf { it.count }} صندلی، ${g.routines.size} کار روتین، ${g.kpis.size} شاخص", style = Divan.type.caption, color = c.textMuted)
                            }
                            Pill(if (g.state == "on") "روشن" else "خاموش", if (g.state == "on") Tone.POS else Tone.SILVER, dot = true)
                        }
                        if (g.purposeFa.isNotBlank()) Para(g.purposeFa, Modifier.padding(top = 10.dp))
                    }
                }
            }
        }
    }
}

/** A group's page: purpose, member companies (pause or resume), seats and who fills them, routines and their runs, KPI charts, the
 *  weekly experiment, and each member's readiness. */
@Composable
fun GroupScreen(key: String) {
    val q = rememberQuery("group:$key", "groups", maxAgeMs = 60_000) { gated(HubFeature.GROUPS) { group(key) } }
    val members = rememberQuery("group:$key:members", "groups", maxAgeMs = 30_000) { gated(HubFeature.GROUPS) { groupMembers(key) } }
    val runs = rememberQuery("group:$key:runs", "groups", maxAgeMs = 30_000) { gated(HubFeature.GROUPS) { groupRuns(key) } }
    val kpis = rememberQuery("group:$key:kpis", "groups", maxAgeMs = 60_000) { gated(HubFeature.GROUPS) { groupKpis(key) } }
    val exps = rememberQuery("group:$key:experiments", "groups", maxAgeMs = 60_000) { gated(HubFeature.GROUPS) { groupExperiments(key) } }
    val r = refresher(q, members, runs, kpis, exps)
    val c = Divan.colors
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        val g = q.data
        when {
            g == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            g == null -> item { Skeleton(Modifier.fillMaxWidth().height(220.dp), radius = 16.dp) }
            else -> {
                item(key = "head") {
                    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text("کارگروه", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.weight(1f))
                            Pill(if (g.state == "on") "روشن" else "خاموش", if (g.state == "on") Tone.POS else Tone.SILVER, dot = true)
                        }
                        Text(plain(g.titleFa), style = Divan.type.h1)
                        if (g.purposeFa.isNotBlank()) Para(g.purposeFa)
                        if (g.connections.isNotEmpty()) Text(
                            plain("از این اتصال‌ها میخواند: " + g.connections.joinToString("، ") { connectionKindFa(it) }),
                            style = Divan.type.caption, color = c.textMuted,
                        )
                    }
                }
                item(key = "members") { MembersCard(g, members.data.orEmpty(), members.data == null) { members.refresh() } }
                item(key = "seats") { SeatsCard(g, members.data.orEmpty()) }
                item(key = "kpis") { KpisCard(g, kpis.data, kpis.data == null && kpis.error == null) }
                item(key = "routines") { RoutinesCard(g) }
                item(key = "runs") { RunsCard(g, runs.data) }
                item(key = "experiments") { ExperimentsCard(exps.data) }
                val list = members.data.orEmpty()
                if (list.isNotEmpty()) item(key = "ready-title") { SectionTitle("آمادگی هر شرکت", note = "هر بررسی سبز یا نه، با دکمه‌ی اصلاحش") }
                items(list, key = { "ready-${it.company}" }) { m -> ReadinessCard(m.company, g.key, collapsed = true) }
            }
        }
    }
}

@Composable
private fun MembersCard(g: WorkGroup, list: List<Membership>, loading: Boolean, onChanged: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("شرکت‌های عضو", note = if (g.eligible == "has_channel") "هر شرکتی که کانال انتشار دارد خودش عضو میشود" else "همه‌ی شرکت‌ها عضو میشوند")
        when {
            loading -> Skeleton(Modifier.fillMaxWidth().height(80.dp).padding(top = 8.dp))
            list.isEmpty() -> Text("هنوز شرکتی عضو نشده.", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.padding(top = 8.dp))
            else -> Column(Modifier.padding(top = 6.dp)) {
                list.forEachIndexed { i, m ->
                    if (i > 0) HorizontalDivider(color = c.lineDivider)
                    val action = rememberAction()
                    Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        CoName(m.company, Modifier.weight(1f), height = 13.dp, color = c.textPrimary, bold = true)
                        val filled = m.seats.count { it.employee != null }
                        Text("$filled از ${m.seats.size} صندلی", style = Divan.type.micro, color = c.textMuted)
                        Pill(if (m.state == "on") "فعال" else "مکث", if (m.state == "on") Tone.POS else Tone.WARN, dot = true)
                        HqButton(if (m.state == "on") "مکث" else "ادامه", {
                            action.run {
                                env.api.setGroupMember(g.key, m.company, if (m.state == "on") "paused" else "on")
                                env.cache.invalidate("groups", "home")
                                toasts.ok(if (m.state == "on") "این شرکت در کارگروه مکث کرد." else "این شرکت دوباره در کارگروه کار میکند.")
                                onChanged()
                            }
                        }, variant = BtnVariant.GHOST, size = BtnSize.SM, icon = if (m.state == "on") DivanIcon.PAUSE else DivanIcon.RESUME, loading = action.busy)
                    }
                }
            }
        }
    }
}


/** Each seat of the group and, per member company, who fills it (or that it is empty: filled by code when hiring is automatic). */
@Composable
private fun SeatsCard(g: WorkGroup, members: List<Membership>) {
    val c = Divan.colors
    val nav = LocalNav.current
    val employees = rememberQuery("employees:all", "employees", maxAgeMs = 60_000) { employees().items }.data.orEmpty()
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("صندلی‌ها", note = "هر صندلی یک نقش؛ خالی‌ها با استخدام خودکار پر میشوند")
        Column(Modifier.padding(top = 6.dp)) {
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
                                Modifier.clip(RoundedCornerShape(Radius.small)).background(if (who != null) c.tile else c.softWarning)
                                    .then(if (who != null) Modifier.clickable(role = Role.Button) { nav.go("employees/$who") } else Modifier)
                                    .padding(horizontal = 8.dp, vertical = 5.dp),
                                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
                            ) {
                                com.coinepro.hq.designsystem.CompanyMark(m.company, height = 11.dp, mono = true, ink = c.textSecondary)
                                Text(e?.let { it.displayName ?: it.titleFa } ?: if (who != null) "پر" else "خالی", style = Divan.type.micro, color = if (who != null) c.textPrimary else c.warning, maxLines = 1)
                                if (e != null) EmployeeStatePill(e.state, e.activity)
                            }
                        }
                    }
                    // Why an empty seat stays empty, and what fixes it (no silence, 2026-11-05).
                    for (m in members) {
                        val b = m.seats.firstOrNull { it.seat == s.seat && it.employee == null }?.blocked ?: continue
                        Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            com.coinepro.hq.designsystem.CompanyMark(m.company, height = 11.dp, mono = true, ink = c.warning)
                            Text("${b.whyFa} ${b.fixFa}".trim(), style = Divan.type.micro, color = c.warning)
                        }
                    }
                }
            }
        }
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

@Composable
private fun RoutinesCard(g: WorkGroup) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("کارهای روتین", note = "هر کدام سر وقتش برای کارمند همان صندلی یک کار کوچک میسازد")
        Column(Modifier.padding(top = 6.dp)) {
            if (g.routines.isEmpty()) Text("کار روتینی تعریف نشده.", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.padding(vertical = 8.dp))
            g.routines.forEachIndexed { i, rt ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                val action = rememberAction()
                Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(plain(rt.titleFa), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                        val seat = g.seats.firstOrNull { it.seat == rt.seat }
                        Text(
                            plain(listOfNotNull(com.coinepro.hq.ui.v14.rruleFa(rt.schedule).takeIf { rt.schedule.isNotBlank() }, seat?.let { it.titleFa.ifBlank { roleFa(it.role) } }).joinToString(" · ")),
                            style = Divan.type.micro, color = c.textMuted,
                        )
                    }
                    Pill(if (rt.state == "on") "روشن" else "مکث", if (rt.state == "on") Tone.POS else Tone.WARN, dot = true)
                    HqButton(null, {
                        action.run {
                            env.api.setRoutine(g.key, rt.key, if (rt.state == "on") "paused" else "on")
                            env.cache.invalidate("groups")
                            toasts.ok(if (rt.state == "on") "این کار روتین مکث کرد." else "این کار روتین دوباره روشن شد.")
                        }
                    }, variant = BtnVariant.GHOST, size = BtnSize.SM, icon = if (rt.state == "on") DivanIcon.PAUSE else DivanIcon.RESUME, loading = action.busy, label = if (rt.state == "on") "مکث" else "ادامه")
                }
            }
        }
    }
}

/** The routines' runs, newest first. */
@Composable
private fun RunsCard(g: WorkGroup, runs: List<com.coinepro.hq.core.net.RoutineRun>?) {
    val nav = LocalNav.current
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("اجراهای اخیر", note = "هر اجرای کار روتین، با نتیجه‌اش")
        Column(Modifier.padding(top = 6.dp)) {
            when {
                runs == null -> Skeleton(Modifier.fillMaxWidth().height(80.dp))
                runs.isEmpty() -> Text("هنوز اجرایی نبوده.", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.padding(vertical = 8.dp))
                else -> runs.sortedByDescending { it.at }.take(12).forEachIndexed { i, x ->
                    if (i > 0) HorizontalDivider(color = c.lineDivider)
                    val (fa, tone) = RUN_STATE_FA[x.state] ?: (x.state to Tone.NEUTRAL)
                    Row(
                        Modifier.fillMaxWidth().then(x.workRef?.let { ref -> Modifier.clickable(role = Role.Button) { nav.go("work/$ref") } } ?: Modifier).padding(vertical = 9.dp),
                        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        com.coinepro.hq.designsystem.CompanyMark(x.company, height = 11.dp, mono = true, ink = c.textSecondary)
                        Column(Modifier.weight(1f)) {
                            Text(plain(g.routines.firstOrNull { it.key == x.routine }?.titleFa ?: x.routine), style = Divan.type.small, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            if (x.noteFa.isNotBlank()) Text(plain(x.noteFa), style = Divan.type.micro, color = c.textMuted, maxLines = 2)
                        }
                        Text(ago(x.at), style = Divan.type.micro, color = c.textMuted)
                        Pill(fa, tone, dot = true)
                    }
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
                                null -> Pill("در جریان", Tone.GOLD, dot = true)
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
 *  and opens on a tap (the group page lists every member). */
@Composable
fun ReadinessCard(company: String, group: String, collapsed: Boolean = false, title: String? = null) {
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
            q.data?.let { r -> Pill(if (r.ready) "آماده" else "هنوز نه", if (r.ready) Tone.POS else Tone.WARN, dot = true) }
            Chevron(open, tint = c.textMuted)
        }
        Expand(open) {
            Box(Modifier.padding(top = 10.dp)) {
                Loadable(q, skeleton = { Skeleton(Modifier.fillMaxWidth().height(120.dp)) }) { r -> if (r != null) Checks(r, company) }
            }
        }
    }
}

@Composable
private fun Checks(r: Readiness, company: String) {
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
                    if (fixRoute(f, company) != null) FixButton(f, company, null)
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
