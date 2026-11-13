package com.coinepro.hq.ui.automation

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.WEEK_DAYS
import com.coinepro.hq.core.data.budgetFa
import com.coinepro.hq.core.data.clockOf
import com.coinepro.hq.core.data.dollarsOf
import com.coinepro.hq.core.data.dollarsText
import com.coinepro.hq.core.data.faNum
import com.coinepro.hq.core.data.flowLineFa
import com.coinepro.hq.core.data.flowModeFa
import com.coinepro.hq.core.data.autoStateFa
import com.coinepro.hq.core.data.lineRunStateFa
import com.coinepro.hq.core.data.lineRunStateTone
import com.coinepro.hq.core.data.resultsLineFa
import com.coinepro.hq.core.data.scheduleFa
import com.coinepro.hq.core.data.spentFa
import com.coinepro.hq.core.data.versionFa
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.format.jWeekday
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.core.net.FlowAutomation
import com.coinepro.hq.core.net.FlowRunRef
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.UseBudget
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BarTone
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.DecisionBar
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.MeterBar
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.ScrollRow
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.SpringSheet
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.facts
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.look.Fold
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.Para
import com.coinepro.hq.ui.v29.plain
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.util.UUID

// Contract §59.7–§59.9 ⟨1.37⟩: one flow automation's page. Its switch is the owner's, one tap. Then what he may want to do with it today
// («همین حالا اجرا کن», «مکث», «نوبت بعد را رد کن»), what it is set to (the hour, the account, the story, «خودکار کامل» or «قبل از
// انتشار بپرس», the budget of a run and of a day), its replies and its company's links, its runs with their results (each opens its
// timeline), the next fourteen days with their topics, the steps it runs and the version, and the log of every change made to it.

@Composable
internal fun rememberFlow(ref: String) =
    rememberQuery("flow:$ref", "automations", maxAgeMs = 10_000) { gated(HubFeature.AUTOMATIONS) { flowAutomation(ref) } }

@Composable
internal fun rememberSiteLinks(company: String?) =
    rememberQuery("site-links:${company.orEmpty()}", "site-links", maxAgeMs = 60_000) { company?.let { co -> gated(HubFeature.SITE_LINKS) { siteLinks(co) } } }

private enum class FlowSheet { NONE, TIME, BUDGET, ACCOUNT, LINKS, PAUSE }

@Composable
fun FlowScreen(ref: String) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val q = rememberFlow(ref)
    val runs = rememberQuery("flow-runs:$ref", "automations", maxAgeMs = 15_000) { gated(HubFeature.AUTOMATIONS) { flowRuns(ref) } }
    val r = refresher(q, runs)
    var sheet by rememberSaveable { mutableStateOf(FlowSheet.NONE) }
    LaunchedEffect(env, ref) {
        env.stream.events.collect { e -> if (e.type.startsWith("automation.") && (e.ref == ref || e.ref == null)) { q.refresh(); runs.refresh() } }
    }
    val f = q.data
    val toggle = rememberAction()
    val now = rememberAction()
    val skip = rememberAction()
    val patch = rememberAction()
    val on = com.coinepro.hq.ui.v29.served(HubFeature.AUTOMATIONS)
    fun changed(out: FlowAutomation, said: String) { q.set(out); env.cache.invalidate("automations"); toasts.ok(said) }

    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item(key = "head") {
            PageHeader(f?.titleFa?.ifBlank { null } ?: "اتوماسیون", eyebrow = f?.let { facts("کارگروه خودکار", it.companyFa.ifBlank { null }).text } ?: "کارگروه خودکار")
        }
        when {
            f == null && q.error != null -> item(key = "err") { ErrorBlock(q.error, { q.refresh() }) }
            f == null && !on -> item(key = "none") {
                Empty("این بخش با به‌روزرسانی بعدی هاب می‌آید", icon = DivanIcon.SETTINGS)
            }
            f == null -> item(key = "sk") { Skeleton(Modifier.fillMaxWidth().height(380.dp), radius = 16.dp) }
            else -> {
                item(key = "switch") {
                    HqCard(Modifier.fillMaxWidth().testTag("flow-switch")) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                                val (fa, tone) = autoStateFa(f.state)
                                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Pill(fa, tone, dot = true)
                                    if (f.state == "paused" && f.pausedUntil != null) Text("تا ${jDateTime(f.pausedUntil)}", style = Divan.type.micro, color = c.textMuted)
                                }
                                Text(
                                    remember(f) { facts(scheduleFa(f.schedule), f.account?.let { "@$it" }, if (f.story) "استوری هم" else null, flowModeFa(f.mode)) },
                                    style = Divan.type.caption, color = c.textSecondary, maxLines = 2, overflow = TextOverflow.Ellipsis,
                                )
                            }
                            HqSwitch(f.on, { on ->
                                toggle.run {
                                    env.api.switchAutomation(ref, on)
                                    q.refresh(); env.cache.invalidate("automations")
                                    toasts.ok(if (on) "روشن شد؛ از نوبت بعد کار میکند." else "خاموش شد؛ تا روشنش نکنی اجرا نمیشود.")
                                }
                            }, "روشن")
                        }
                        f.next?.let { n ->
                            HorizontalDivider(Modifier.padding(vertical = 10.dp), color = c.lineDivider)
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                DIcon(DivanIcon.TIME, size = 16.dp, tint = c.silverInk)
                                Column(Modifier.weight(1f)) {
                                    Text(plain(if (n.skip) "نوبت ${jWeekday(n.at)} رد میشود" else "اجرای بعد: ${jWeekday(n.at)}، ${jTime(n.at)}"), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                                    Text(plain(n.topicFa?.let { "موضوع: $it" } ?: "موضوع روز اجرا از دفتر موضوع‌ها انتخاب میشود"), style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                }
                            }
                        }
                        Row(Modifier.padding(top = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            HqButton("همین حالا اجرا کن", {
                                now.run {
                                    val run = env.api.runFlowNow(ref, UUID.randomUUID().toString())
                                    runs.refresh(); env.cache.invalidate("automations")
                                    toasts.ok("اجرا شروع شد.", "ببین") { nav.go("flow-run/${run.ref}") }
                                }
                            }, Modifier.weight(1f), variant = BtnVariant.SECONDARY, size = BtnSize.MD, icon = DivanIcon.RESUME, loading = now.busy, enabled = f.state != "off")
                            if (f.state == "paused") HqButton("ادامه", { toggle.run { env.api.switchAutomation(ref, true); q.refresh(); toasts.ok("از مکث درآمد.") } }, variant = BtnVariant.TEXT, size = BtnSize.MD)
                            else HqButton("مکث", { sheet = FlowSheet.PAUSE }, variant = BtnVariant.TEXT, size = BtnSize.MD, enabled = f.state == "on")
                        }
                        f.next?.let { n ->
                            HqButton(if (n.skip) "نوبت بعد را برگردان" else "نوبت بعد را رد کن", {
                                skip.run { changed(env.api.skipFlow(ref, n.at, !n.skip, UUID.randomUUID().toString()), if (n.skip) "نوبت بعد برگشت." else "نوبت بعد رد میشود؛ بعدی‌اش سر جایش است.") }
                            }, Modifier.fillMaxWidth().padding(top = 4.dp), variant = BtnVariant.TEXT, size = BtnSize.SM, loading = skip.busy)
                        }
                    }
                }
                item(key = "today") { TodayBudget(f) }
                item(key = "settings") {
                    HqCard(Modifier.fillMaxWidth().testTag("flow-settings"), padding = PaddingValues(vertical = 4.dp)) {
                        SettingRow(DivanIcon.TIME, "ساعت انتشار", scheduleFa(f.schedule)) { sheet = FlowSheet.TIME }
                        SettingRow(DivanIcon.OWNER, "حساب", f.account?.let { "@$it" } ?: "حساب ثبت‌شده‌ی شرکت") { sheet = FlowSheet.ACCOUNT }
                        Row(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            DIcon(DivanIcon.IMAGE, size = 18.dp, tint = c.silverInk)
                            Text("استوری هم", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, modifier = Modifier.weight(1f))
                            HqSwitch(f.story, { on -> patch.run { changed(env.api.patchFlow(ref, buildJsonObject { put("story", on) }), if (on) "استوری هم میرود." else "فقط ریلز میرود.") } }, "استوری هم")
                        }
                        Column(Modifier.padding(horizontal = 14.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text("حالت", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                            ScrollRow {
                                for (m in listOf("auto", "ask")) FilterChip(flowModeFa(m), f.mode == m, {
                                    if (f.mode != m) patch.run { changed(env.api.patchFlow(ref, buildJsonObject { put("mode", m) }), if (m == "auto") "از این به بعد خودش منتشر میکند؛ دکمه‌ای لازم نیست." else "پیش از هر انتشار، ویدیو در «نوبت تو» منتظر میماند.") }
                                })
                            }
                        }
                        SettingRow(DivanIcon.BUDGET, "بودجه", budgetFa(f.budget)) { sheet = FlowSheet.BUDGET }
                        SettingRow(DivanIcon.MESSAGES, "جواب‌ها", "کامنت، استوری، دایرکت و جواب‌های عمومی") { nav.go("automation/$ref/replies") }
                        SettingRow(DivanIcon.GLOBE, "لینک‌های شرکت", "سایت، بخش‌ها و UTM هر مسیر") { sheet = FlowSheet.LINKS }
                    }
                }
                item(key = "runs") { RunsCard(runs.data?.items ?: listOfNotNull(f.lastRun), runs.loading) { nav.go("flow-run/$it") } }
                if (f.upcoming.isNotEmpty()) item(key = "upcoming") { UpcomingFold(f) { at, skipIt -> skip.run { changed(env.api.skipFlow(ref, at, skipIt, UUID.randomUUID().toString()), if (skipIt) "این نوبت رد میشود." else "این نوبت برگشت.") } } }
                item(key = "flow") {
                    Fold("روند", remember(f) { facts(f.playbookFa?.let { "کارگروه «$it»" }, f.version?.let { versionFa(it) }, "${faNum(f.steps.size)} قدم") }, tag = "flow-steps") {
                        Para(flowLineFa(f.steps), style = Divan.type.caption, color = c.textSecondary)
                        f.playbook?.let { pb -> HqButton("صفحه‌ی کارگروه", { nav.go("playbook/$pb") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.DEPARTMENT) }
                        Text(plain("n8n هر دقیقه سر میزند${f.n8n.lastTickAt?.let { "؛ آخرین بار ${jTime(it)}" }.orEmpty()}."), style = Divan.type.micro, color = c.textMuted)
                    }
                }
                item(key = "audit") { AuditFold(ref) }
            }
        }
    }
    val f0 = f ?: return
    when (sheet) {
        FlowSheet.NONE -> Unit
        FlowSheet.TIME -> TimeSheet(f0, { sheet = FlowSheet.NONE }) { body, said -> patch.run { changed(env.api.patchFlow(ref, body), said); sheet = FlowSheet.NONE } }
        FlowSheet.BUDGET -> BudgetSheet(f0.budget, { sheet = FlowSheet.NONE }) { b -> patch.run {
            changed(env.api.patchFlow(ref, buildJsonObject { put("budget", buildJsonObject { put("per_run_usd", b.perRunUsd); put("per_day_usd", b.perDayUsd) }) }), "بودجه عوض شد: ${budgetFa(b)}")
            sheet = FlowSheet.NONE
        } }
        FlowSheet.ACCOUNT -> AccountSheet(f0.account, { sheet = FlowSheet.NONE }) { a -> patch.run {
            changed(env.api.patchFlow(ref, buildJsonObject { if (a == null) put("account", kotlinx.serialization.json.JsonNull) else put("account", a) }), "از اجرای بعد به ${a?.let { "@$it" } ?: "حساب ثبت‌شده‌ی شرکت"} میرود.")
            sheet = FlowSheet.NONE
        } }
        FlowSheet.LINKS -> SpringSheet({ sheet = FlowSheet.NONE }, "لینک‌های شرکت", sub = "n8n از این میداند هر جواب چه لینکی بفرستد.") {
            SiteLinksEditor(f0.company, campaign = f0.ref.lowercase()) { sheet = FlowSheet.NONE }
        }
        FlowSheet.PAUSE -> PauseSheet({ sheet = FlowSheet.NONE }) { until -> patch.run {
            changed(env.api.pauseFlow(ref, until, UUID.randomUUID().toString()), if (until == null) "مکث شد؛ با «ادامه» برمیگردد." else "تا ${jDate(until)} مکث شد.")
            sheet = FlowSheet.NONE
        } }
    }
}

@Composable
private fun SettingRow(icon: DivanIcon, title: String, value: String, onClick: () -> Unit) {
    val c = Divan.colors
    Row(
        Modifier.fillMaxWidth().clickable(role = Role.Button, onClick = onClick).padding(horizontal = 14.dp, vertical = 11.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        DIcon(icon, size = 18.dp, tint = c.silverInk)
        Column(Modifier.weight(1f)) {
            Text(title, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
            Text(plain(value), style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        DIcon(DivanIcon.NEXT, size = 14.dp, tint = c.textMuted)
    }
}

/** Today's runs and spend against the day's cap, as a meter (silver, warn past 70%, negative past 90%). */
@Composable
private fun TodayBudget(f: FlowAutomation) {
    val c = Divan.colors
    val spent = f.budget.spentTodayUsd ?: f.today.costUsd
    val pct = if (f.budget.perDayUsd > 0) spent / f.budget.perDayUsd * 100 else 0.0
    HqCard(Modifier.fillMaxWidth().testTag("flow-today")) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("امروز", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, modifier = Modifier.weight(1f))
            Text(facts(if (f.today.runs > 0) "${faNum(f.today.runs)} اجرا" else "هنوز اجرایی نه", spentFa(f.budget.copy(spentTodayUsd = spent))), style = Divan.type.caption, color = c.textSecondary)
        }
        MeterBar(pct, Modifier.fillMaxWidth().padding(top = 8.dp), tone = when { pct >= 90 -> BarTone.NEG; pct >= 70 -> BarTone.WARN; else -> BarTone.SILVER })
        Text("به سقف که برسد میایستد و همین‌جا میگوید.", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.padding(top = 6.dp))
    }
}

/** The runs, newest first: the day, the state, the topic, the figures, the cost; each opens its timeline. */
@Composable
private fun RunsCard(items: List<FlowRunRef>, loading: Boolean, onOpen: (String) -> Unit) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth().testTag("flow-runs"), padding = PaddingValues(vertical = 4.dp)) {
        Box(Modifier.padding(horizontal = 14.dp, vertical = 8.dp)) { SectionTitle("اجراها و نتیجه‌ها") }
        if (items.isEmpty()) Text(if (loading) "…" else "هنوز اجرایی نیست.", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp))
        items.forEachIndexed { i, run ->
            if (i > 0) HorizontalDivider(color = c.lineDivider)
            Row(
                Modifier.fillMaxWidth().clickable(role = Role.Button, onClickLabel = "خط زمان") { onOpen(run.ref) }.padding(horizontal = 14.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(run.at?.let { jWeekday(it) } ?: "—", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                        Pill(lineRunStateFa(run.state), lineRunStateTone(run.state), live = run.state == "running", dot = run.state != "running")
                    }
                    run.topicFa?.let { Text(plain(it), style = Divan.type.caption, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis) }
                    Text(
                        remember(run) { facts(resultsLineFa(run.results), run.costUsd?.let { usd(it) }, run.noteFa.ifBlank { null }?.takeIf { resultsLineFa(run.results) == null }) },
                        style = Divan.type.micro, color = c.textMuted, maxLines = 2, overflow = TextOverflow.Ellipsis,
                    )
                }
                DIcon(DivanIcon.NEXT, size = 14.dp, tint = c.textMuted)
            }
        }
    }
}

/** The next fourteen days: each its day and hour, its topic once planned, and «رد کن» / «برگردان». */
@Composable
private fun UpcomingFold(f: FlowAutomation, onSkip: (String, Boolean) -> Unit) {
    val c = Divan.colors
    Fold("تقویم اجراهای پیش رو", remember(f.upcoming) { facts("${faNum(f.upcoming.size)} نوبت", f.upcoming.count { it.skip }.takeIf { it > 0 }?.let { "${faNum(it)} رد" }) }, tag = "flow-upcoming") {
        f.upcoming.forEachIndexed { i, o ->
            if (i > 0) HorizontalDivider(color = c.lineDivider)
            Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Column(Modifier.weight(1f)) {
                    Text(plain("${jWeekday(o.at)}، ${jTime(o.at)}"), style = Divan.type.small, color = if (o.skip) c.textMuted else c.textPrimary)
                    Text(plain(o.topicFa ?: "موضوع روز اجرا انتخاب میشود"), style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                HqButton(if (o.skip) "برگردان" else "رد کن", { onSkip(o.at, !o.skip) }, variant = BtnVariant.TEXT, size = BtnSize.SM)
            }
        }
    }
}

/** Every change of this automation, newest first (its switch, hour, account, mode, budget, replies), from the audit log. */
@Composable
private fun AuditFold(ref: String) {
    val c = Divan.colors
    val q = rememberQuery("flow-audit:$ref", "automations", maxAgeMs = 30_000) { gated(HubFeature.AUTOMATIONS) { automationAudit(ref) } }
    val list = q.data.orEmpty()
    Fold("دفتر تغییرها", remember(list.size) { facts(if (list.isEmpty()) "هنوز تغییری نیست" else "${faNum(list.size)} تغییر") }, tag = "flow-audit") {
        for (a in list) Column(Modifier.padding(vertical = 4.dp)) {
            Text(plain(a.summaryFa.ifBlank { a.action }), style = Divan.type.caption, color = c.textPrimary)
            Text(facts(a.whoFa.ifBlank { null }, jDateTime(a.at)), style = Divan.type.micro, color = c.textMuted)
        }
    }
}

// ------------------------------------------------------------------ the sheets --
/** The hour: the account's best hour (§49) or a fixed one, the days of the week (all of them: every day). */
@Composable
internal fun TimeSheet(f: FlowAutomation, onDismiss: () -> Unit, onSave: (kotlinx.serialization.json.JsonObject, String) -> Unit) {
    val c = Divan.colors
    var mode by rememberSaveable { mutableStateOf(f.schedule.mode) }
    var at by rememberSaveable { mutableStateOf(f.schedule.at.orEmpty()) }
    var days by rememberSaveable { mutableStateOf(f.schedule.days ?: WEEK_DAYS.map { it.first }) }
    val ok = mode == "best" || clockOf(at) != null
    SpringSheet(onDismiss, "ساعت انتشار", sub = "اجرا آن‌قدر زودتر شروع میشود که ویدیو سر ساعت آماده باشد.", bar = {
        DecisionBar("ذخیره", {
            val body = buildJsonObject {
                put("schedule", buildJsonObject {
                    put("mode", mode)
                    if (mode == "fixed") put("at", clockOf(at))
                    put("days", JsonArray(days.map(::JsonPrimitive)))
                })
            }
            onSave(body, if (mode == "best") "از این به بعد در بهترین ساعت حساب منتشر میشود." else "از این به بعد ساعت ${clockOf(at)} منتشر میشود.")
        }, enabled = ok && days.isNotEmpty(), icon = DivanIcon.TIME)
    }) {
        ScrollRow { FilterChip("بهترین ساعت", mode == "best", { mode = "best" }); FilterChip("ساعت ثابت", mode == "fixed", { mode = "fixed" }) }
        if (mode == "fixed") HqTextField(at, { at = it }, "مثل 18:30", Modifier.fillMaxWidth(), maxLength = 5, figure = true)
        else Text("هاب از روی لایک و کامنت پست‌های همین حساب ساعت خوب را پیدا میکند؛ داده که کم باشد، همان لحظه‌ی آماده شدن.", style = Divan.type.micro, color = c.textMuted)
        Text("کدام روزها", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            for ((k, fa) in WEEK_DAYS) FilterChip(fa, k in days, { days = if (k in days) days - k else WEEK_DAYS.map { it.first }.filter { it in days || it == k } })
        }
    }
}

/** The budget of one run and of one day, typed in dollars. */
@Composable
internal fun BudgetSheet(b: UseBudget, onDismiss: () -> Unit, onSave: (UseBudget) -> Unit) {
    val c = Divan.colors
    var run by rememberSaveable { mutableStateOf(dollarsText(b.perRunUsd)) }
    var day by rememberSaveable { mutableStateOf(dollarsText(b.perDayUsd)) }
    val r = dollarsOf(run)
    val d = dollarsOf(day)
    val ok = r != null && d != null && r > 0 && d >= r
    SpringSheet(onDismiss, "بودجه", sub = "به سقف که برسد، اجرا میایستد و همین‌جا میگوید؛ چیزی بی‌صدا خرج نمیشود.", bar = {
        DecisionBar("ذخیره", { if (r != null && d != null) onSave(UseBudget(r, d)) }, enabled = ok, icon = DivanIcon.BUDGET)
    }) {
        Text("هر اجرا (دلار)", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
        HqTextField(run, { run = it }, "مثل 5", Modifier.fillMaxWidth(), maxLength = 8, figure = true)
        Text("هر روز (دلار)", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
        HqTextField(day, { day = it }, "مثل 8", Modifier.fillMaxWidth(), maxLength = 8, figure = true)
        if (!ok) Text("هر دو عدد بیشتر از صفر، و سقف روز دست‌کم به اندازه‌ی یک اجرا.", style = Divan.type.micro, color = c.negative)
        Text("بالا بردن سقف تا جایی که در پاکت ماه شرکت بماند یک ضربه است؛ بیشتر از آن اثر انگشت میخواهد.", style = Divan.type.micro, color = c.textMuted)
    }
}

/** The account the flow publishes to: one he names, or the company's registered one. */
@Composable
private fun AccountSheet(account: String?, onDismiss: () -> Unit, onSave: (String?) -> Unit) {
    val c = Divan.colors
    var text by rememberSaveable { mutableStateOf(account.orEmpty()) }
    SpringSheet(onDismiss, "حساب انتشار", sub = "خالی بگذاری، حساب ثبت‌شده‌ی شرکت.", bar = {
        DecisionBar("ذخیره", { onSave(text.trim().removePrefix("@").ifBlank { null }) }, icon = DivanIcon.OWNER)
    }) {
        HqTextField(text, { text = it }, "@حساب", Modifier.fillMaxWidth(), maxLength = 40, figure = true)
        Text("اگر شرکت چند حساب دارد و نامی ندهی، هاب میپرسد کدام.", style = Divan.type.micro, color = c.textMuted)
    }
}

/** «مکث»: until he says (no date) or for a day, three days or a week. */
@Composable
private fun PauseSheet(onDismiss: () -> Unit, onPause: (String?) -> Unit) {
    val c = Divan.colors
    SpringSheet(onDismiss, "مکث", sub = "چیزی پاک نمیشود؛ موضوع‌ها و تنظیم‌ها سر جایشان میمانند.") {
        for ((fa, days) in listOf("تا خودم بگویم" to 0, "یک روز" to 1, "سه روز" to 3, "یک هفته" to 7)) Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).clickable(role = Role.Button) {
                onPause(if (days == 0) null else com.coinepro.hq.core.format.HqClock.now().plus(days.toLong(), java.time.temporal.ChronoUnit.DAYS).toString())
            }.padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) { Text(fa, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, modifier = Modifier.weight(1f)); DIcon(DivanIcon.PAUSE, size = 16.dp, tint = c.textMuted) }
    }
}
