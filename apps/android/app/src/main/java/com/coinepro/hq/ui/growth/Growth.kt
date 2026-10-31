package com.coinepro.hq.ui.growth

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.instant
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.format.until
import com.coinepro.hq.core.net.LifecycleRule
import com.coinepro.hq.core.net.LifecycleRuleIn
import com.coinepro.hq.core.net.NpsWave
import com.coinepro.hq.core.net.RuleLimits
import com.coinepro.hq.core.net.RuleTrigger
import com.coinepro.hq.core.net.Template
import com.coinepro.hq.core.net.TemplateIn
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Seg
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.StackedBar
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v16.CHANNEL_FA
import com.coinepro.hq.ui.v16.Chip
import com.coinepro.hq.ui.v16.ChipRow
import com.coinepro.hq.ui.v16.CompanyChips
import com.coinepro.hq.ui.v16.Fact
import com.coinepro.hq.ui.v16.FactRows
import com.coinepro.hq.ui.v16.Labelled
import com.coinepro.hq.ui.v16.Notice
import com.coinepro.hq.ui.v16.PURPOSE_FA
import com.coinepro.hq.ui.v16.RULE_STATUS
import com.coinepro.hq.ui.v16.TEMPLATE_STATUS
import com.coinepro.hq.ui.v16.go
import com.coinepro.hq.ui.v16.prose
import com.coinepro.hq.ui.v16.rate
import com.coinepro.hq.ui.v16.triggerFa

private val TABS = listOf(SegOption("templates", "قالب‌ها"), SegOption("rules", "قاعده‌ها"), SegOption("nps", "NPS"))

/** رشد و پیام‌ها (contract §19.5): rule-sent messages use a sealed template under a sealed rule with limits; sealing the rule is
 *  the owner's A3 approval in advance. Free text from an agent to a customer does not exist. */
@Composable
fun GrowthScreen(tab0: String = "templates") {
    val c = Divan.colors
    var tab by rememberSaveable { mutableStateOf(tab0) }
    var company by rememberSaveable { mutableStateOf<String?>(null) }
    val templates = rememberQuery("growth:templates:${company.orEmpty()}", "growth") { templates(company) }
    val rules = rememberQuery("growth:rules:${company.orEmpty()}", "growth") { rules(company) }
    val nps = rememberQuery("growth:nps:${company.orEmpty()}", "growth") { nps(company) }
    val r = refresher(templates, rules, nps)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("رشد و پیام‌ها", eyebrow = "فقط قالب مُهرشده زیر قاعده‌ی مُهرشده؛ هیچ متن آزادی از ایجنت به مشتری نمیرسد") }
        item {
            Text(
                "خوش‌آمد، بازگشت، نجات رفرال، NPS و رضایت. هر پیام از نگهبان خروجی، ساعت سکوت تهران، سقف‌ها و قواعد تلگرام میگذرد؛ پیامی که تلگرام اجازه نمیدهد ثبت میشود، نه زور.",
                style = Divan.type.small, color = c.textSecondary,
            )
        }
        item { CompanyChips(company, { company = it }) }
        item { Segmented(TABS, tab, { tab = it }, Modifier.fillMaxWidth()) }
        item {
            when (tab) {
                "rules" -> RulesTab(company, rules.data, rules.error, { rules.refresh() }, templates.data.orEmpty())
                "nps" -> NpsTab(nps.data, nps.error) { nps.refresh() }
                else -> TemplatesTab(company, templates.data, templates.error) { templates.refresh() }
            }
        }
    }
}

/** A template body with its variables marked, so the owner sees exactly what will be sent and what is filled in. */
@Composable
private fun body(text: String): AnnotatedString {
    val c = Divan.colors
    return remember(text, c) {
        buildAnnotatedString {
            var last = 0
            for (m in Regex("\\{\\{\\s*\\w+\\s*\\}\\}").findAll(text)) {
                append(text.substring(last, m.range.first))
                withStyle(SpanStyle(background = c.softGold)) { fig(m.value, c.goldInk) }
                last = m.range.last + 1
            }
            append(text.substring(last))
        }
    }
}

@Composable
private fun Body(text: String, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Text(body(text), modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), style = Divan.type.small.copy(lineHeight = 24.sp), color = c.textPrimary)
}

// --------------------------------------------------------------- templates --
@Composable
private fun TemplatesTab(company: String?, data: List<Template>?, error: com.coinepro.hq.core.net.ApiException?, retry: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val action = rememberAction()
    var seal by remember { mutableStateOf<Template?>(null) }
    var edit by remember { mutableStateOf<Template?>(null) }
    var neu by remember { mutableStateOf(false) }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row { Spacer(Modifier.weight(1f)); HqButton("قالب تازه", { neu = true }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.ADD) }
        val list = data?.sortedWith(compareByDescending<Template> { it.status == "proposed" }.thenBy { it.company }.thenBy { it.ref })
        when {
            list == null && error != null -> ErrorBlock(error, retry)
            list == null -> Skeleton(Modifier.fillMaxWidth().height(220.dp), radius = 16.dp)
            list.isEmpty() -> Empty("قالبی نیست", icon = DivanIcon.SEND)
            else -> for (t in list) Column(
                Modifier.fillMaxWidth().alpha(if (t.status == "retired") 0.6f else 1f).clip(RoundedCornerShape(16.dp)).background(if (t.status == "proposed") c.softGold else c.card).padding(14.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    CompanyMark(t.company, height = 13.dp, mono = true, ink = c.textSecondary)
                    Text(prose(PURPOSE_FA[t.purpose] ?: t.purpose), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Fig("${t.ref}@${t.version}", style = Divan.type.figureSmall, color = c.textMuted)
                    LabelPill(TEMPLATE_STATUS[t.status], t.status)
                }
                Body(t.bodyFa)
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    if (t.sha256.isNotBlank()) Fig("sha256 ${t.sha256.take(10)}…", style = Divan.type.figureSmall, color = c.textMuted)
                    t.sealedAt?.let { Text("مُهر ${jDate(it)}", style = Divan.type.micro, color = c.textMuted) }
                    Spacer(Modifier.weight(1f))
                    if (t.status == "proposed") HqButton("مُهر", { seal = t }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.SEAL)
                    if (t.status == "sealed") HqButton("نسخه‌ی تازه", { edit = t }, variant = BtnVariant.GHOST, size = BtnSize.SM, icon = DivanIcon.EDIT)
                }
            }
        }
    }
    seal?.let { t ->
        AlertDialog(
            onDismissRequest = { seal = null },
            containerColor = c.overlay,
            title = { Text(buildAnnotatedString { append("مُهر قالب "); fig("${t.ref}@${t.version}") }, style = Divan.type.h3) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("دقیقاً همین متن فرستاده میشود:", style = Divan.type.small, color = c.textSecondary)
                    Body(t.bodyFa, Modifier.heightIn(max = 240.dp).verticalScroll(rememberScrollState()))
                    Text(buildAnnotatedString {
                        append("مُهر به همین متن بسته است ("); fig("${t.ref}@${t.version}:${t.sha256.take(12)}…"); append(") و برای متن هم‌شکل شرکت دیگر به کار نمیرود.")
                    }, style = Divan.type.micro, color = c.textMuted)
                }
            },
            confirmButton = {
                HqButton("مُهر با اثر انگشت", {
                    action.go(toasts) {
                        env.api.sealTemplate(t) { a, x -> env.auth.stepUp(act, a, x) }
                        env.cache.invalidate("growth", "decisions")
                        toasts.ok("مُهر شد؛ قاعده‌هایی که با همین نسخه‌اند میتوانند بفرستند.")
                        seal = null
                    }
                }, variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, loading = action.busy)
            },
            dismissButton = { HqButton("انصراف", { seal = null }, variant = BtnVariant.GHOST) },
        )
    }
    if (neu || edit != null) TemplateSheet(company, edit) { neu = false; edit = null }
}

@Composable
private fun TemplateSheet(company0: String?, from: Template?, onClose: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    var company by rememberSaveable { mutableStateOf(from?.company ?: company0) }
    var purpose by rememberSaveable { mutableStateOf(from?.purpose ?: "holding_reply") }
    var text by rememberSaveable { mutableStateOf(from?.bodyFa ?: "") }
    val variables = Regex("\\{\\{\\s*(\\w+)\\s*\\}\\}").findAll(text).map { it.groupValues[1] }.distinct().toList()
    val valid = company != null && text.trim().length >= 10
    HqSheet(onClose, if (from != null) "نسخه‌ی تازه‌ی ${from.ref}" else "قالب تازه", sub = "فقط همین متن با همین متغیرها فرستاده میشود؛ نسخه‌ی تازه قاعده‌اش را تا مُهر نگه میدارد.") {
        if (from == null) {
            Labelled("شرکت") { CompanyChips(company, { company = it }, all = false) }
            Labelled("کاربرد") { ChipRow { for ((k, fa) in PURPOSE_FA) FilterChip(fa, purpose == k, { purpose = k }) } }
        }
        Labelled("متن") { HqTextField(text, { text = it }, "متغیرها با {{name}}؛ برای لغو «لغو» بفرستید", Modifier.fillMaxWidth(), singleLine = false, minLines = 6, maxLength = 1500) }
        if (variables.isNotEmpty()) Text(buildAnnotatedString { append("متغیرها: "); variables.forEachIndexed { i, v -> if (i > 0) append("، "); fig("{{$v}}") } }, style = Divan.type.caption, color = c.textSecondary)
        Text(
            "جمله‌ی ایمنی خودکار به هر پیام چرخه‌ی عمر اضافه میشود. لینک و کد فقط از دانشنامه‌ی تأییدشده؛ نگهبان خروجی بقیه را رد میکند.",
            style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp),
        )
        HqButton("ثبت برای مُهر", {
            val co = company ?: return@HqButton
            action.go(toasts) {
                val t = env.api.proposeTemplate(TemplateIn(co, purpose, text.trim(), variables, from?.ref))
                env.cache.invalidate("growth")
                toasts.ok("قالب ${t.ref}@${t.version} ثبت شد؛ تا مُهر تو هیچ قاعده‌ای با آن نمیفرستد.")
                onClose()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEND, enabled = valid, loading = action.busy)
    }
}

// ------------------------------------------------------------------- rules --
private val KINDS = listOf("welcome", "reactivation", "rescue", "nps", "csat")
private val EVENT_OF = mapOf("welcome" to "signup", "rescue" to "referral_failed", "csat" to "conversation_closed")
private const val QUARTERLY = "FREQ=MONTHLY;INTERVAL=3;BYMONTHDAY=1;BYHOUR=11"

@Composable
private fun RulesTab(company: String?, data: List<LifecycleRule>?, error: com.coinepro.hq.core.net.ApiException?, retry: () -> Unit, templates: List<Template>) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val action = rememberAction()
    var busy by remember { mutableStateOf<String?>(null) }
    var neu by remember { mutableStateOf(false) }
    val intake = rememberQuery("intake:sources", "intake", maxAgeMs = 120_000) { intakeSources() }
    fun tmpl(ref: String) = ref.split('@').let { (r, v) -> templates.firstOrNull { it.ref == r && it.version.toString() == v } }
    // welcome and reactivation wait for product events (CR-009/010): without a configured product intake they have no candidates.
    fun noProduct(r: LifecycleRule) = (r.kind == "welcome" || r.kind == "reactivation") && intake.data != null &&
        intake.data!!.none { it.company == r.company && it.kind == "product" && it.configured }
    fun doRule(r: LifecycleRule, ok: String, block: suspend () -> Unit) {
        busy = r.ref
        action.go(toasts, onError = { busy = null; false }) {
            block()
            busy = null
            env.cache.invalidate("growth", "decisions")
            toasts.ok(ok)
        }
    }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row { Spacer(Modifier.weight(1f)); HqButton("قاعده‌ی تازه", { neu = true }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.ADD) }
        val list = data?.sortedWith(compareByDescending<LifecycleRule> { it.status == "proposed" }.thenBy { it.company }.thenBy { it.ref })
        when {
            list == null && error != null -> ErrorBlock(error, retry)
            list == null -> Skeleton(Modifier.fillMaxWidth().height(220.dp), radius = 16.dp)
            list.isEmpty() -> Empty("قاعده‌ای نیست", icon = DivanIcon.TIME)
            else -> for (r in list) {
                val t = tmpl(r.template)
                Column(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(if (r.status == "proposed") c.softGold else c.card).padding(14.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        CompanyMark(r.company, height = 13.dp, mono = true, ink = c.textSecondary)
                        Text(prose(PURPOSE_FA[r.kind] ?: r.kind), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), modifier = Modifier.weight(1f), maxLines = 1)
                        Fig("${r.ref}@${r.version}", style = Divan.type.figureSmall, color = c.textMuted)
                        LabelPill(RULE_STATUS[r.status], r.status)
                    }
                    FactRows(listOf(
                        { m -> Fact("کی", triggerFa(r.trigger), m) },
                        { m -> Fact("کانال", CHANNEL_FA[r.channel] ?: r.channel, m) },
                        { m ->
                            Column(m.clip(RoundedCornerShape(12.dp)).background(c.tile).padding(horizontal = 12.dp, vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                Text("قالب", style = Divan.type.micro, color = c.textMuted)
                                Fig(r.template, style = Divan.type.figure, color = c.textPrimary)
                                t?.let { Text(TEMPLATE_STATUS[it.status]?.fa ?: it.status, style = Divan.type.micro, color = if (it.status == "sealed") c.positive else c.warning) }
                            }
                        },
                        { m -> Fact("۳۰ روز گذشته", "${r.sent30d} فرستاده، ${r.optOuts30d} لغو", m) },
                    ))
                    Text(buildAnnotatedString {
                        append("هر مشتری یک بار در ${r.limits.perCustomerDays} روز · سقف روزانه "); fig(r.limits.dailyCap.toString())
                        append(" · سکوت "); fig(r.limits.quietHours.joinToString("–"))
                        if (r.limits.maxFollowUps > 0) append(" · حداکثر ${r.limits.maxFollowUps} پیگیری")
                    }, style = Divan.type.caption, color = c.textSecondary)
                    if (noProduct(r)) Notice(DivanIcon.INFO, c.tile, c.textMuted) {
                        Text(prose("تا رویداد ثبت‌نام و فعالیت از محصول نرسد (CR-009/010)، این قاعده هیچ کاندیدی ندارد."), style = Divan.type.caption, color = c.textSecondary)
                    }
                    if (r.status != "active" && t != null && t.status != "sealed") Text("قالب این نسخه هنوز مُهر نشده؛ اول قالب، بعد قاعده.", style = Divan.type.caption, color = c.warning)
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        r.decisionRef?.let { d ->
                            Fig(d, Modifier.clip(RoundedCornerShape(6.dp)).clickable(role = Role.Button) { nav.go("cartable/$d") }.padding(horizontal = 4.dp, vertical = 2.dp), style = Divan.type.figureSmall, color = c.goldInk)
                        }
                        Spacer(Modifier.weight(1f))
                        val mine = busy == r.ref && action.busy
                        when (r.status) {
                            "proposed" -> HqButton("مُهر و فعال", { doRule(r, "مُهر شد و فعال است.") { env.api.sealRule(r) { a, x -> env.auth.stepUp(act, a, x) } } }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.SEAL, loading = mine)
                            "active" -> HqButton("توقف", { doRule(r, "متوقف شد.") { env.api.pauseRule(r.ref) } }, variant = BtnVariant.DANGER, size = BtnSize.SM, icon = DivanIcon.PAUSE, loading = mine)
                            "paused" -> HqButton("ادامه با اثر انگشت", { doRule(r, "دوباره فعال شد.") { env.api.resumeRule(r) { a, x -> env.auth.stepUp(act, a, x) } } }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.RESUME, loading = mine)
                        }
                    }
                }
            }
        }
    }
    if (neu) RuleSheet(company) { neu = false }
}

/** Latin or Persian digits, as typed; null when not a whole number. */
private fun whole(s: String): Int? = s.trim().map { ch -> if (ch in '۰'..'۹') '0' + (ch - '۰') else ch }.joinToString("").toIntOrNull()

@Composable
private fun RuleSheet(company0: String?, onClose: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    var company by rememberSaveable { mutableStateOf(company0) }
    var kind by rememberSaveable { mutableStateOf("csat") }
    var template by rememberSaveable { mutableStateOf<String?>(null) }
    var channel by rememberSaveable { mutableStateOf<String?>(null) }
    var hours by rememberSaveable { mutableStateOf("1") }
    var inactive by rememberSaveable { mutableStateOf("30") }
    var per by rememberSaveable { mutableStateOf("30") }
    var cap by rememberSaveable { mutableStateOf("100") }
    var quietFrom by rememberSaveable { mutableStateOf("22:00") }
    var quietTo by rememberSaveable { mutableStateOf("09:00") }
    var follow by rememberSaveable { mutableStateOf("2") }
    val co = company
    val tq = co?.let { rememberQuery("growth:templates:$it", "growth") { templates(it) } }
    val cq = co?.let { rememberQuery("support:channels:$it", "support") { supportChannels(it) } }
    val templates = tq?.data.orEmpty().filter { it.purpose == kind && it.status != "retired" }
    val channels = cq?.data.orEmpty().filter { it.kind != "mystery" }
    val hhmm = Regex("^([01]\\d|2[0-3]):[0-5]\\d$")
    val body = if (co != null && template != null && channel != null) LifecycleRuleIn(
        co, kind,
        when (kind) { "nps" -> RuleTrigger(rrule = QUARTERLY); "reactivation" -> RuleTrigger(inactiveDays = whole(inactive) ?: 0); else -> RuleTrigger(event = EVENT_OF.getValue(kind), afterHours = whole(hours) ?: 0) },
        template!!, channel!!,
        RuleLimits(whole(per) ?: 0, whole(cap) ?: 0, listOf(quietFrom, quietTo), if (kind == "rescue") whole(follow) ?: 0 else 0),
    ) else null
    val valid = body != null && body.limits.dailyCap > 0 && body.limits.perCustomerDays > 0 && hhmm.matches(quietFrom) && hhmm.matches(quietTo)
    HqSheet(onClose, "قاعده‌ی تازه", sub = "پیشنهادی ساخته میشود؛ با مُهر تو (اثر انگشت) و فقط وقتی قالبِ همان نسخه مُهرشده است فعال میشود.") {
        Labelled("شرکت") { CompanyChips(company, { company = it; template = null; channel = null }, all = false) }
        Labelled("نوع") { ChipRow { for (k in KINDS) FilterChip(PURPOSE_FA[k] ?: k, kind == k, { kind = k; template = null }) } }
        when (kind) {
            "nps" -> Text("فصلی، روز اول؛ نمونه‌ی تصادفی از مشتری‌هایی که در ۹۰ روز گذشته گفت‌وگو داشته‌اند.", style = Divan.type.caption, color = c.textSecondary,
                modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp))
            "reactivation" -> Labelled("بعد از چند روز بی‌فعالیتی") { HqTextField(inactive, { inactive = it }, "30", Modifier.fillMaxWidth(), maxLength = 4, figure = true) }
            else -> Labelled("چند ساعت بعد از «${com.coinepro.hq.ui.v16.EVENT_FA[EVENT_OF[kind]] ?: ""}»") { HqTextField(hours, { hours = it }, "1", Modifier.fillMaxWidth(), maxLength = 4, figure = true) }
        }
        Labelled("قالب") {
            when {
                co == null -> Text("اول شرکت", style = Divan.type.caption, color = c.textMuted)
                templates.isEmpty() -> Text("قالبی با این کاربرد نیست", style = Divan.type.caption, color = c.textMuted)
                else -> ChipRow {
                    for (t in templates) {
                        val ref = "${t.ref}@${t.version}"
                        Chip(template == ref, { template = ref }) { ink ->
                            Fig(ref, style = Divan.type.figureSmall, color = ink)
                            Text(TEMPLATE_STATUS[t.status]?.fa ?: t.status, style = Divan.type.micro, color = ink)
                        }
                    }
                }
            }
        }
        Labelled("کانال") {
            if (channels.isEmpty()) Text(if (co == null) "اول شرکت" else "کانالی نیست", style = Divan.type.caption, color = c.textMuted)
            else ChipRow { for (ch in channels) FilterChip(CHANNEL_FA[ch.kind] ?: ch.kind, channel == ch.kind, { channel = ch.kind }) }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Labelled("هر مشتری یک بار در (روز)", Modifier.weight(1f)) { HqTextField(per, { per = it }, "30", Modifier.fillMaxWidth(), maxLength = 4, figure = true) }
            Labelled("سقف روزانه", Modifier.weight(1f)) { HqTextField(cap, { cap = it }, "100", Modifier.fillMaxWidth(), maxLength = 6, figure = true) }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Labelled("سکوت از", Modifier.weight(1f)) { HqTextField(quietFrom, { quietFrom = it.trim() }, "22:00", Modifier.fillMaxWidth(), maxLength = 5, figure = true) }
            Labelled("تا", Modifier.weight(1f)) { HqTextField(quietTo, { quietTo = it.trim() }, "09:00", Modifier.fillMaxWidth(), maxLength = 5, figure = true) }
        }
        if (kind == "rescue") Labelled("حداکثر پیگیری") { HqTextField(follow, { follow = it }, "2", Modifier.fillMaxWidth(), maxLength = 2, figure = true) }
        Text("ساعت سکوت به وقت تهران. «لغو»، «stop» یا «نمیخواهم» همه‌ی قاعده‌های این شرکت را برای آن مشتری برای همیشه قطع میکند.", style = Divan.type.caption, color = c.textMuted)
        HqButton("ثبت قاعده", {
            val b = body ?: return@HqButton
            action.go(toasts) {
                val r = env.api.createRule(b)
                env.cache.invalidate("growth")
                toasts.ok("قاعده‌ی ${r.ref} ثبت شد؛ برای فعال شدن مُهرش کن.")
                onClose()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.ADD, enabled = valid, loading = action.busy)
    }
}

// --------------------------------------------------------------------- NPS --
@Composable
private fun NpsTab(data: List<NpsWave>?, error: com.coinepro.hq.core.net.ApiException?, retry: () -> Unit) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        when {
            data == null && error != null -> ErrorBlock(error, retry)
            data == null -> Skeleton(Modifier.fillMaxWidth().height(220.dp), radius = 16.dp)
            data.isEmpty() -> Empty("موجی نیست", icon = DivanIcon.RATE, body = "NPS یک قاعده‌ی فصلی است؛ با مُهر قاعده‌ی NPS هر شرکت شروع میشود.")
            else -> {
                Text("جواب ۰ تا ۱۰؛ امتیاز = درصد مروج منهای درصد منتقد. توضیح‌ها به صندوق بازخورد میروند.", style = Divan.type.small, color = c.textSecondary)
                for (w in data.sortedWith(compareByDescending<NpsWave> { it.quarter }.thenBy { it.company })) Wave(w)
            }
        }
    }
}

@Composable
private fun Wave(w: NpsWave) {
    val nav = LocalNav.current
    val c = Divan.colors
    val now = HqClock.millis()
    val opens = instant(w.opensAt)?.toEpochMilli() ?: 0L
    val closes = instant(w.closesAt)?.toEpochMilli() ?: 0L
    val open = opens <= now && closes > now
    val ahead = opens > now
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(c.card).padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            CompanyMark(w.company, height = 13.dp, mono = true, ink = c.textSecondary)
            Fig(w.quarter, Modifier.weight(1f), style = Divan.type.figure.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
            Fig(w.ref, style = Divan.type.figureSmall, color = c.textMuted)
            Pill(if (open) "باز" else if (ahead) "هنوز باز نشده" else "بسته", if (open) Tone.LAPIS else Tone.NEUTRAL, live = open, dot = !open)
        }
        val score = w.score
        if (score != null) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Fig((if (score > 0) "+" else if (score < 0) "−" else "") + kotlin.math.abs(score), style = Divan.type.figureL.copy(fontSize = 28.sp), color = if (score >= 0) c.textPrimary else c.negative)
                Text(buildAnnotatedString { append("امتیاز NPS، از "); fig("−100"); append(" تا "); fig("+100") }, style = Divan.type.caption, color = c.textSecondary)
            }
            NpsTrack(score)
            StackedBar(listOf(
                Seg("p", "مروج (۹–۱۰)", w.promoters.toDouble(), c.positive, w.promoters.toString()),
                Seg("n", "خنثی (۷–۸)", w.passives.toDouble(), c.silverInk, w.passives.toString()),
                Seg("d", "منتقد (۰–۶)", w.detractors.toDouble(), c.negative, w.detractors.toString()),
            ), label = "مروج، خنثی، منتقد", height = 10.dp)
        } else Text(
            if (ahead) "موج ${jDate(w.opensAt)} باز میشود؛ نمونه از پیش انتخاب شده است." else "هنوز جوابی نرسیده؛ امتیاز بی‌جواب ساخته نمیشود.",
            style = Divan.type.small, color = c.textSecondary,
        )
        FactRows(listOf(
            { m -> Fact("نمونه", w.sample.toString(), m, figure = true) },
            { m -> Fact("فرستاده", w.sent.toString(), m, figure = true) },
            { m -> Fact("جواب", w.responses.toString() + if (w.sent > 0) " · ${rate(w.responses.toDouble() / w.sent)}" else "", m, figure = true) },
        ), perRow = 3)
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("${jDate(w.opensAt)} تا ${jDate(w.closesAt)}" + if (open) " (${until(w.closesAt)})" else "", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f))
            if (w.commentsToFeedback > 0) Text(
                "${w.commentsToFeedback} توضیح در صندوق بازخورد", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk,
                modifier = Modifier.clip(RoundedCornerShape(6.dp)).clickable(role = Role.Button) { nav.go("feedback") }.padding(horizontal = 4.dp, vertical = 2.dp),
            )
        }
    }
}

/** −100..100 on one track, as a number line (left to right): the bar grows from zero towards the score. */
@Composable
private fun NpsTrack(score: Int) {
    val c = Divan.colors
    val s = score.coerceIn(-100, 100)
    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
        Box(Modifier.fillMaxWidth().height(16.dp).semantics { contentDescription = "امتیاز $s" }) {
            Canvas(Modifier.fillMaxWidth().height(16.dp)) {
                val h = 8.dp.toPx(); val y = (size.height - h) / 2; val r = CornerRadius(h / 2, h / 2)
                drawRoundRect(c.tile, Offset(0f, y), Size(size.width, h), r)
                val mid = size.width / 2
                val len = size.width / 2 * kotlin.math.abs(s) / 100f
                if (len > 0) drawRoundRect(if (s >= 0) c.positive else c.negative, Offset(if (s >= 0) mid else mid - len, y), Size(len, h), r)
                drawRoundRect(c.lineStrong, Offset(mid - 1.dp.toPx(), 0f), Size(2.dp.toPx(), size.height), CornerRadius(1.dp.toPx()))
            }
        }
    }
}
