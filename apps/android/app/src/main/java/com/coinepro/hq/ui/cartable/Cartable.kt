package com.coinepro.hq.ui.cartable

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.waitForUpOrCancellation
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.onClick
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.DECISION_STATUS
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.actorFa
import com.coinepro.hq.core.format.agentKindOf
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.decisionKind
import com.coinepro.hq.core.format.deptOf
import com.coinepro.hq.core.format.hoursUntil
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.format.modelLabel
import com.coinepro.hq.core.format.risk
import com.coinepro.hq.core.format.tokens
import com.coinepro.hq.core.format.until
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.core.net.Company
import com.coinepro.hq.core.net.Decision
import com.coinepro.hq.core.net.LifecycleRule
import com.coinepro.hq.core.net.RuleLimits
import com.coinepro.hq.core.net.ShadowReport
import com.coinepro.hq.core.net.Template
import com.coinepro.hq.ui.v16.AUTO_SEND
import com.coinepro.hq.ui.v16.CHANNEL_FA
import com.coinepro.hq.ui.v16.PURPOSE_FA
import com.coinepro.hq.ui.v16.triggerFa
import com.coinepro.hq.designsystem.Avatar
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Seal
import com.coinepro.hq.designsystem.SealState
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.generated.DivanMotion
import com.coinepro.hq.designsystem.toneColors
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Loadable
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.refresher
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

// code_session: its seal creates a Code Workshop grant (contract §5.1 ⟨1.4.3⟩). The round-two kinds are sealed the same way, each card
// bound to what it proposes (§18.13 ⟨1.4.5⟩); a server plan is sealed only on its own route, against its digest (§18.8).
// ⟨1.5⟩ the revenue-and-support cards (§19.9) are sealed the same way, each bound to its template, rule or shadow report.
private val STEP_UP_KINDS = setOf(
    "hire", "dismissal", "budget_change", "code_session", "protocol", "tool_enable", "errand_action", "company_found", "lesson_adoption",
    "message_template", "lifecycle_rule", "support_go_live",
)
/** Kinds sealed on their own page, never by the cartable's approve: a server plan's seal is bound to its digest (§18.8).
 *  The card carries {plan, company}; the plan page sends a founding's plan on to its founding (§18.16). */
private val OWN_ROUTE: Map<String, Pair<(Decision) -> String, String>> = mapOf(
    "server_plan" to ({ d: Decision -> (d.payload["plan"] as? kotlinx.serialization.json.JsonPrimitive)?.takeIf { it.isString }?.content?.let { "founding/$it" } ?: "founding" } to "مُهر طرح سرور"),
)

/** A3 actions and hire, dismissal and budget changes are approved with a fresh passkey (contract §4). */
fun needsStepUp(d: Decision) = d.actionClass == "A3" || d.kind in STEP_UP_KINDS

/** One decision in a list: kind glyph, title, company, risk and time left. */
@Composable
fun DecisionRow(d: Decision, companies: List<Company>, onClick: () -> Unit) {
    val c = Divan.colors
    val k = decisionKind(d.kind)
    val r = risk(d.risk)
    val co = companyOf(companies, d.company)
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).clickable(role = Role.Button, onClick = onClick).padding(vertical = 10.dp, horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(Modifier.size(40.dp).clip(RoundedCornerShape(12.dp)).background(c.tile), contentAlignment = Alignment.Center) { DIcon(k.icon, size = 20.dp, tint = c.goldInk) }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(d.title, style = Divan.type.small.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold), maxLines = 2, overflow = TextOverflow.Ellipsis)
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                CompanyMark(d.company, height = 12.dp, mono = true, ink = c.textSecondary)
                Text(co.nameFa, style = Divan.type.micro, color = c.textMuted, maxLines = 1)
                Text("·", style = Divan.type.micro, color = c.textMuted)
                Text(k.fa, style = Divan.type.micro, color = c.textMuted, maxLines = 1)
            }
        }
        Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(4.dp)) {
            val (_, fg) = toneColors(r.tone)
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                Box(Modifier.size(6.dp).clip(androidx.compose.foundation.shape.CircleShape).background(fg))
                Text(r.fa, style = Divan.type.micro, color = fg)
            }
            if (d.status == "pending" && d.expiresAt != null) {
                val soon = (hoursUntil(d.expiresAt) ?: 99.0) < 12
                Text(until(d.expiresAt), style = Divan.type.micro, color = if (soon) c.warning else c.textMuted)
            } else Text(ago(d.createdAt), style = Divan.type.micro, color = c.textMuted)
        }
    }
}

/** The cartable: what needs the owner's seal, by risk; and what was decided. */
@Composable
fun CartableScreen() {
    val nav = LocalNav.current
    val companies = rememberCompanies()
    var tab by rememberSaveable { mutableStateOf("pending") }
    var riskF by rememberSaveable { mutableStateOf<String?>(null) }
    // Cartable age (M8): what expires first, what has waited longest, or the newest.
    var sort by rememberSaveable { mutableStateOf("expiry") }
    val q = rememberQuery("decisions:$tab", "decisions") { decisions(if (tab == "pending") "pending" else null, limit = 100) }
    val r = refresher(q)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("کارتابل", eyebrow = "تصمیم‌هایی که مُهر تو را لازم دارند") }
        item {
            Segmented(listOf(SegOption("pending", "منتظر مُهر"), SegOption("all", "همه")), tab, { tab = it }, Modifier.fillMaxWidth())
        }
        val all = q.data?.items.orEmpty().let { if (tab == "all") it else it.filter { d -> d.status == "pending" } }
        if (tab == "pending") item {
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip("همه", riskF == null, { riskF = null }, count = all.size)
                for ((key, label) in listOf("high" to "ریسک بالا", "medium" to "متوسط", "low" to "کم")) {
                    FilterChip(label, riskF == key, { riskF = if (riskF == key) null else key }, count = all.count { it.risk == key })
                }
            }
        }
        if (tab == "pending") item {
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                for ((key, label) in listOf("expiry" to "زودتر منقضی", "oldest" to "بیشترین انتظار", "newest" to "تازه‌ترین")) FilterChip(label, sort == key, { sort = key })
            }
        }
        val list = all.filter { riskF == null || it.risk == riskF }.let { xs ->
            when (sort) {
                "expiry" -> xs.sortedWith(compareBy({ it.expiresAt ?: "9999" }, { it.createdAt }))
                "oldest" -> xs.sortedBy { it.createdAt }
                else -> xs.sortedByDescending { it.createdAt }
            }
        }
        when {
            q.data == null && q.error == null -> items(4) { Skeleton(Modifier.fillMaxWidth().height(64.dp)) }
            q.data == null -> item { com.coinepro.hq.designsystem.ErrorBlock(q.error, { q.refresh() }) }
            list.isEmpty() -> item { Empty("کارتابل خالی است", icon = DivanIcon.SEAL, body = "هر تصمیمی که امضای تو را بخواهد این‌جا میاید.") }
            else -> item {
                HqCard(Modifier.fillMaxWidth(), padding = androidx.compose.foundation.layout.PaddingValues(horizontal = 12.dp, vertical = 6.dp)) {
                    list.forEach { d -> DecisionRow(d, companies) { nav.go("cartable/${d.ref}") } }
                }
            }
        }
    }
}

@Composable
private fun Section(title: String, content: @Composable () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(title, style = Divan.type.caption.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold), color = Divan.colors.goldInk)
        content()
    }
}

@Composable
private fun Fact(label: String, value: String, modifier: Modifier = Modifier, figure: Boolean = false) {
    Column(modifier.clip(RoundedCornerShape(12.dp)).background(Divan.colors.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(label, style = Divan.type.micro, color = Divan.colors.textMuted)
        if (figure) Fig(value, style = Divan.type.figure) else Text(value, style = Divan.type.small.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold))
    }
}

@Composable
private fun FactGrid(vararg facts: Triple<String, String, Boolean>) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        facts.toList().chunked(2).forEach { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                row.forEach { (l, v, f) -> Fact(l, v, Modifier.weight(1f), f) }
                if (row.size == 1) Spacer(Modifier.weight(1f))
            }
        }
    }
}

private fun JsonObject.s(k: String): String? = (this[k] as? JsonPrimitive)?.contentOrNull
private fun JsonObject.list(k: String): List<String> = (this[k] as? JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.contentOrNull }.orEmpty()
/** A §19.9 payload part as the app's model (⟨1.5.1⟩ shapes); null when it is missing or does not fit. */
private fun <T> JsonObject.model(k: String, s: kotlinx.serialization.KSerializer<T>): T? =
    (this[k] as? JsonObject)?.let { runCatching { com.coinepro.hq.core.net.Api.json.decodeFromJsonElement(s, it) }.getOrNull() }

@Composable
private fun Payload(d: Decision) {
    val p = d.payload
    val c = Divan.colors
    when (d.kind) {
        "hire" -> Section("قرارداد استخدام") {
            FactGrid(
                Triple("نقش", p.s("title_fa") ?: p.s("role") ?: "—", false),
                Triple("دپارتمان", p.s("department") ?: "—", true),
                Triple("مدل و فکر", "${modelLabel(p.s("model"))} · ${p.s("effort") ?: "—"}", true),
                Triple("برآورد ماهانه", "${tokens(p.s("quota_estimate_month")?.toLongOrNull() ?: d.quotaEstimate.tokens)} tok", true),
            )
            val duties = p.list("duties")
            if (duties.isNotEmpty()) Md(duties.joinToString("\n") { "- $it" })
            val perms = p.list("permissions")
            if (perms.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                perms.forEach { Fig(it, Modifier.clip(RoundedCornerShape(6.dp)).background(c.tile).padding(horizontal = 8.dp, vertical = 2.dp), style = Divan.type.figureSmall, color = c.textSecondary) }
            }
        }
        "deploy" -> Section("انتشار") {
            val ci = p["ci"] as? JsonObject
            val tests = p["tests"] as? JsonObject
            FactGrid(
                Triple("ریپو", p.s("repo") ?: "—", true),
                Triple("تغییر", p.s("diff_stat") ?: "—", true),
                Triple("CI", if (ci?.s("status") == "passed") "سبز" else ci?.s("status") ?: "—", false),
                Triple("تست‌ها", "${tests?.s("passed") ?: 0} ✓ · ${tests?.s("failed") ?: 0} ✗", true),
            )
            p.s("rollout")?.let { Text(buildAnnotatedString { append("روش انتشار: "); fig(it, c.textPrimary) }, style = Divan.type.small, color = c.textSecondary) }
        }
        "tool_enable" -> Section("ابزارهای این سرور عوض شده‌اند") {
            val diff = p["diff"] as? JsonObject
            Text(buildAnnotatedString { append("سرور "); fig(p.s("key") ?: "—", c.textPrimary); append(" خاموش است. با مُهر، دقیقاً با همین فهرست روشن میشود.") }, style = Divan.type.small, color = c.textSecondary)
            listOf(Triple("added", "تازه", c.warning), Triple("changed", "عوض‌شده", c.warning), Triple("removed", "حذف‌شده", c.textMuted)).forEach { (key, fa, tone) ->
                val names = diff?.list(key).orEmpty()
                if (names.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(fa, style = Divan.type.caption, color = tone)
                    names.forEach { Fig(it, Modifier.clip(RoundedCornerShape(6.dp)).background(c.tile).padding(horizontal = 8.dp, vertical = 2.dp), style = Divan.type.figureSmall, color = c.textSecondary) }
                }
            }
        }
        "a3_action" -> if (p.s("action") == "mcp_call") Section("فراخوانی ابزار بیرونی") {
            FactGrid(Triple("سرور", p.s("server") ?: "—", true), Triple("ابزار", p.s("tool") ?: "—", true))
            (p["args"] as? JsonObject)?.takeIf { it.isNotEmpty() }?.let { args ->
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    args.forEach { (k, v) -> Text(buildAnnotatedString { fig(k, c.textMuted); append("  "); fig((v as? JsonPrimitive)?.contentOrNull ?: v.toString(), c.textPrimary) }, style = Divan.type.small) }
                }
            }
            Text("با مُهر، همین فراخوانی با همین ورودی فقط یک بار اجرا میشود.", style = Divan.type.caption, color = c.textMuted)
        }
        // ⟨1.5⟩ §19.9: what each card seals, read from its payload.
        "support_go_live" -> Section("شروع پشتیبانی") {
            FactGrid(
                Triple("کانال", CHANNEL_FA[p.s("channel")] ?: p.s("channel") ?: "—", false),
                Triple("ارسال بی‌تو", AUTO_SEND[p.s("auto_send")]?.first ?: p.s("auto_send") ?: "—", false),
                Triple("آستانه‌ی عین دانشنامه", p.s("verbatim_threshold") ?: "—", true),
                Triple("آستانه‌ی پیش‌نویس مستند", p.s("grounded_threshold") ?: "—", true),
            )
            p.model("shadow_report", ShadowReport.serializer())?.let { r ->
                Text(buildAnnotatedString {
                    append("آزمون سایه‌ی "); fig(r.suite, c.textPrimary); append(": ")
                    fig(if (r.total > 0) "${Math.round(r.correct * 100.0 / r.total)}%" else "0%", c.textPrimary); append(" درست از "); fig(r.total.toString())
                    append("، خطای ایمنی "); fig(r.safetyFailures.toString(), if (r.safetyFailures > 0) c.negative else c.textPrimary)
                    append("، کد یا لینک اشتباه "); fig(r.wrongCodes.toString(), if (r.wrongCodes > 0) c.negative else c.textPrimary)
                    append(" · " + (if (r.pass) "قبول" else "رد") + ".")
                }, style = Divan.type.small, color = c.textSecondary)
            }
            Text("آستانه‌ها مسیر ویرایش ندارند؛ عوض کردنشان یعنی آزمون سایه‌ی تازه و کارت تازه. با مُهر، کانال روشن و آستانه‌ها همین اعداد میشوند.", style = Divan.type.caption, color = c.textMuted)
        }
        "message_template" -> {
            val t = p.model("template", Template.serializer())
            Section("قالب ${PURPOSE_FA[t?.purpose] ?: ""}".trim()) {
                if (t != null) {
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Fig("${t.ref}@${t.version}", style = Divan.type.figureSmall, color = c.textMuted)
                        t.variables.forEach { Fig("{{$it}}", Modifier.clip(RoundedCornerShape(6.dp)).background(c.tile).padding(horizontal = 8.dp, vertical = 2.dp), style = Divan.type.figureSmall, color = c.textSecondary) }
                    }
                    Text(com.coinepro.hq.ui.v16.prose(t.bodyFa), style = Divan.type.body, color = c.textPrimary, modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp))
                }
                val sha = p.s("sha256")?.takeIf { it.isNotBlank() } ?: t?.sha256.orEmpty()
                if (sha.isNotBlank()) Text(buildAnnotatedString { append("مُهر به همین متن بسته است: "); fig("sha256 ${sha.take(16)}…") }, style = Divan.type.micro, color = c.textMuted)
            }
        }
        "lifecycle_rule" -> Section("قاعده‌ی پیام") {
            val r = p.model("rule", LifecycleRule.serializer())
            val l = p.model("limits", RuleLimits.serializer()) ?: r?.limits
            FactGrid(
                Triple("قاعده", r?.let { "${it.ref}@${it.version}" } ?: "—", true),
                Triple("کی", r?.let { triggerFa(it.trigger) } ?: "—", false),
                Triple("قالب", p.s("template") ?: r?.template ?: "—", true),
                Triple("کانال", r?.let { CHANNEL_FA[it.channel] ?: it.channel } ?: "—", false),
            )
            l?.let {
                Text(buildAnnotatedString {
                    append("هر مشتری حداکثر یک بار در ${it.perCustomerDays} روز، سقف روزانه "); fig(it.dailyCap.toString())
                    append("، ساعت سکوت "); fig(it.quietHours.joinToString("–"))
                    if (it.maxFollowUps > 0) append("، حداکثر ${it.maxFollowUps} پیگیری")
                    append(".")
                }, style = Divan.type.small, color = c.textSecondary)
            }
            Text("مُهر این کارت تأیید پیشاپیش توست؛ قاعده فقط تا وقتی قالبِ همین نسخه مُهرشده است اجرا میشود.", style = Divan.type.caption, color = c.textMuted)
        }
        "budget_change" -> Section("تغییر بودجه") {
            FactGrid(
                Triple("دامنه", p["scope"]?.toString()?.replace(Regex("[\"{}]"), "") ?: "—", true),
                Triple("دوره", p.s("period") ?: "—", false),
                Triple("سقف توکن", p.s("token_limit")?.toLongOrNull()?.let(::tokens) ?: "—", true),
                Triple("سقف دلار", p.s("usd_limit")?.let { usd(it) } ?: "—", true),
            )
        }
    }
}

/** One decision: what, why, cost and risk, then the seal ritual or reject / return / ask / advisor. */
@Composable
fun DecisionScreen(ref: String) {
    val q = rememberQuery("decision:$ref", "decisions") { decision(ref) }
    val r = refresher(q)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { Loadable(q, skeleton = { Skeleton(Modifier.fillMaxWidth().height(320.dp), radius = 16.dp) }) { d -> DecisionDetail(d) { q.set(it) } } }
    }
}

@Composable
private fun DecisionDetail(d: Decision, onChanged: (Decision) -> Unit) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val companies = rememberCompanies()
    val co = companyOf(companies, d.company)
    val k = decisionKind(d.kind)
    val rk = risk(d.risk)
    val pending = d.status == "pending"
    val seal = rememberAction()
    val other = rememberAction()
    var reject by remember { mutableStateOf(false) }
    var ret by remember { mutableStateOf(false) }
    var note by rememberSaveable { mutableStateOf("") }
    var reason by rememberSaveable { mutableStateOf<String?>(null) }

    fun decided(x: Decision) {
        onChanged(x)
        env.cache.invalidate("decisions", "inbox", "away", "resolutions")
        // ⟨1.5⟩ a sealed §19.9 card changes what its screen shows: the template or rule, or the channel going live.
        when (d.kind) {
            "message_template", "lifecycle_rule" -> env.cache.invalidate("growth")
            "support_go_live" -> env.cache.invalidate("support")
        }
    }

    Column(verticalArrangement = Arrangement.spacedBy(18.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            Box(Modifier.size(48.dp).clip(RoundedCornerShape(14.dp)).background(c.tile), contentAlignment = Alignment.Center) { DIcon(k.icon, size = 24.dp, tint = c.goldInk) }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(buildAnnotatedString { append(k.fa + " "); fig(d.ref); append("، " + co.nameFa) }, style = Divan.type.caption, color = c.textMuted)
                Text(d.title, style = Divan.type.h2)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Pill(rk.fa, rk.tone, dot = true)
                    Pill(if (d.reversible) "برگشت‌پذیر" else "برگشت‌ناپذیر", if (d.reversible) Tone.SILVER else Tone.WARN, icon = if (d.reversible) DivanIcon.REFRESH else DivanIcon.URGENT)
                    Pill(d.actionClass, Tone.NEUTRAL, figure = true)
                    if (!pending) Pill(DECISION_STATUS[d.status] ?: d.status, if (d.status == "approved") Tone.GOLD else Tone.NEUTRAL)
                }
            }
        }
        HqCard(Modifier.fillMaxWidth(), padding = androidx.compose.foundation.layout.PaddingValues(12.dp), radius = 14.dp) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Avatar(agentKindOf(d.proposer.code, d.proposer.kind), dept = deptOf(d.proposer.code), size = 40.dp)
                Column(Modifier.weight(1f)) {
                    Text(actorFa(d.proposer), style = Divan.type.small.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold))
                    Text(buildAnnotatedString { fig(d.proposer.code); append("، " + ago(d.createdAt)) }, style = Divan.type.micro, color = c.textMuted)
                }
                if (pending && d.expiresAt != null) Text(until(d.expiresAt), style = Divan.type.caption, color = if ((hoursUntil(d.expiresAt) ?: 99.0) < 12) c.warning else c.textMuted)
            }
        }
        Section("چی") { Md(d.what) }
        Section("چرا") { Md(d.why) }
        Payload(d)
        Section("مصرف و ریسک") {
            FactGrid(Triple("برآورد توکن", tokens(d.quotaEstimate.tokens), true), Triple("هزینه‌ی معادل", usd(d.quotaEstimate.usd), true))
            d.riskNote?.let {
                Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.softWarning).padding(12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    DIcon(DivanIcon.URGENT, size = 18.dp, tint = c.warning)
                    Text(it, style = Divan.type.small)
                }
            }
        }
        if (pending) {
            HqCard(Modifier.fillMaxWidth(), radius = 18.dp) {
                Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    val own = OWN_ROUTE[d.kind]
                    if (own != null) {
                        HqButton(own.second, { nav.go(own.first(d)) }, icon = DivanIcon.SEAL)
                    } else SealButton(d.company, co.nameFa, co.nameEn, co.holding, busy = seal.busy) {
                        seal.run {
                            val token = if (needsStepUp(d)) env.auth.stepUp(act, "decision.approve", d.ref) else null
                            val out = env.api.approve(d.ref, null, token)
                            decided(out)
                            toasts.ok("مُهر خورد. ${out.resolution?.let { "$it " } ?: ""}به ${actorFa(d.proposer)} خبر داده شد.")
                        }
                    }
                    if (needsStepUp(d) || own != null) Text("این تصمیم با اثر انگشت یا چهره تأیید میشود.", style = Divan.type.caption, color = c.textMuted)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterHorizontally), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        HqButton("توی چت بپرس", { other.run { val o = env.api.ask(d.ref, null); nav.go("messages/${o.thread}") } }, icon = DivanIcon.MESSAGES, loading = other.busy)
                        HqButton("با مشاور بررسی کن", { other.run { env.api.reviewWithAdvisor(d.ref); nav.go("advisor") } }, variant = BtnVariant.SILVER, icon = DivanIcon.ADVISOR)
                        HqButton("برگشت با یادداشت", { ret = true }, icon = DivanIcon.BACK)
                        HqButton("رد", { reject = true }, variant = BtnVariant.DANGER, icon = DivanIcon.REJECT)
                    }
                }
            }
        } else if (d.seal != null) {
            val s = d.seal
            HqCard(Modifier.fillMaxWidth(), radius = 18.dp) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                    Seal(d.company, co.nameFa, co.nameEn, holding = co.holding, state = SealState.SEALED, size = 72.dp)
                    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text("مُهر خورد، ${jDateTime(s.sealedAt)}", style = Divan.type.small.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold))
                        d.resolution?.let { Text(buildAnnotatedString { append("مصوبه‌ی "); fig(it, c.goldInk) }, style = Divan.type.small, color = c.textSecondary) }
                        d.note?.let { Text(it, style = Divan.type.caption, color = c.textMuted) }
                    }
                }
            }
        } else if (d.decidedAt != null || d.note != null) {
            // Rejected, returned, expired or withdrawn: what happened, when, by whom, and why.
            HqCard(Modifier.fillMaxWidth(), radius = 18.dp) {
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    DIcon(
                        when (d.status) { "rejected" -> DivanIcon.REJECT; "returned" -> DivanIcon.BACK; "expired" -> DivanIcon.TIME; else -> DivanIcon.CLOSE },
                        size = 20.dp, tint = c.textSecondary,
                    )
                    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        val head = listOfNotNull(DECISION_STATUS[d.status] ?: d.status, d.decidedAt?.let { jDateTime(it) }, d.decidedBy?.let { actorFa(it) })
                        Text(head.joinToString("، "), style = Divan.type.small.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold))
                        d.note?.let { Text(it, style = Divan.type.caption, color = c.textMuted) }
                    }
                }
            }
        }
    }

    if (reject) AlertDialog(
        onDismissRequest = { reject = false },
        containerColor = c.overlay,
        title = { Text("رد این تصمیم", style = Divan.type.h3) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("دلیل کمک میکند سیستم دفعه‌ی بعد بهتر پیشنهاد بدهد.", style = Divan.type.small, color = c.textSecondary)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    for ((v, l) in listOf("cost" to "هزینه", "risk" to "ریسک", "timing" to "زمان", "quality" to "کیفیت", "other" to "دیگر")) {
                        FilterChip(l, reason == v, { reason = v })
                    }
                }
                HqTextField(note, { note = it }, "توضیح (اختیاری)", Modifier.fillMaxWidth(), singleLine = false, minLines = 3)
            }
        },
        confirmButton = {
            HqButton("رد کن", {
                other.run { decided(env.api.reject(d.ref, note.ifBlank { null }, reason)); reject = false; toasts.info("رد شد و دلیلش برای یادگیری ثبت شد.") }
            }, variant = BtnVariant.DANGER, loading = other.busy)
        },
        dismissButton = { HqButton("انصراف", { reject = false }, variant = BtnVariant.GHOST) },
    )
    if (ret) AlertDialog(
        onDismissRequest = { ret = false },
        containerColor = c.overlay,
        title = { Text("برگشت با یادداشت", style = Divan.type.h3) },
        text = { HqTextField(note, { note = it }, "چه چیزی باید عوض شود؟", Modifier.fillMaxWidth(), singleLine = false, minLines = 4) },
        confirmButton = {
            HqButton("بفرست", {
                other.run { decided(env.api.returnDecision(d.ref, note.trim())); ret = false; toasts.info("به پیشنهاددهنده برگشت.") }
            }, variant = BtnVariant.PRIMARY, enabled = note.isNotBlank(), loading = other.busy)
        },
        dismissButton = { HqButton("انصراف", { ret = false }, variant = BtnVariant.GHOST) },
    )
}

/** The seal ritual (D2): press and hold the seal; a gold ring fills; releasing early cancels. On completion
 *  [onSealed] runs (step-up, then approve). TalkBack users get a plain "seal" action instead of the hold. */
@Composable
fun SealButton(code: String, nameFa: String, nameEn: String, holding: Boolean, busy: Boolean, sealed: Boolean = false, onSealed: () -> Unit) {
    val scope = rememberCoroutineScope()
    val haptic = LocalHapticFeedback.current
    val progress = remember { Animatable(0f) }
    val p = if (busy) 1f else progress.value
    val state = when { sealed -> SealState.SEALED; p > 0f -> SealState.HOLDING; else -> SealState.READY }
    Column(
        Modifier
            .semantics {
                contentDescription = if (sealed) "مُهر خورد" else "مُهر بزن"
                onClick(label = "مُهر بزن") { if (!busy && !sealed) onSealed(); true }
            }
            .pointerInput(busy, sealed) {
                if (busy || sealed) return@pointerInput
                awaitEachGesture {
                    awaitFirstDown()
                    val job = scope.launch {
                        progress.snapTo(0f)
                        progress.animateTo(1f, tween(DivanMotion.SEAL_HOLD_MS, easing = LinearEasing))
                        haptic.performHapticFeedback(HapticFeedbackType.LongPress)
                        progress.snapTo(0f)
                        onSealed()
                    }
                    waitForUpOrCancellation()
                    if (job.isActive) {
                        job.cancel()
                        scope.launch { progress.animateTo(0f, tween(DivanMotion.STATE_MS)) }
                    }
                }
            },
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Seal(code, nameFa, nameEn, holding = holding, state = state, progress = p, size = 104.dp)
        Text(
            when { sealed -> "مُهر خورد"; busy -> "در حال تأیید با passkey…"; else -> "فشار بده و نگه دار" },
            style = Divan.type.caption, color = Divan.colors.textMuted,
        )
    }
}
