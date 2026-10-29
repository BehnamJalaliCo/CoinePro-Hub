package com.coinepro.hq.ui.owner

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.format.OWNER_TZ
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.format.modelLabel
import com.coinepro.hq.core.format.tokens
import com.coinepro.hq.core.format.until
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.core.net.BudgetRowIn
import com.coinepro.hq.core.net.CallRow
import com.coinepro.hq.core.net.Connection
import com.coinepro.hq.core.net.ConnectionPatch
import com.coinepro.hq.designsystem.BarTone
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.MeterBar
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.settings.parseMillions
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v14.figs
import java.time.LocalDate
import java.time.ZoneId
import kotlinx.coroutines.launch

private val QUOTA = mapOf("ok" to ("عادی" to Tone.POS), "warning" to ("نزدیک سقف" to Tone.WARN), "limited" to ("محدود" to Tone.NEG))

/** The subscription quota (§16.5): the Quota Controller pauses P4 at "warning" and lets only P0–P2 through at "limited". */
@Composable
fun QuotaCard() {
    val c = Divan.colors
    val q = rememberQuery("treasury:quota", "treasury", maxAgeMs = 60_000) { quota() }
    HqCard(Modifier.fillMaxWidth()) {
        val s = q.data?.subscription
        SectionTitle("سهمیه‌ی اشتراک", note = "کنترل‌کننده‌ی سهمیه کد است، نه مدل", action = s?.let { { val (l, t) = QUOTA[it.status] ?: (it.status to Tone.NEUTRAL); Pill(l, t, dot = true) } })
        when {
            s == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
            s == null -> Skeleton(Modifier.fillMaxWidth().height(48.dp).padding(top = 8.dp))
            else -> Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                val used = s.utilization?.toDoubleOrNull()?.let { it * 100 }
                if (used != null) {
                    Row { Text(figs("مصرف پنجره ${s.window ?: ""}"), style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.weight(1f)); Fig("${used.toInt()}%", style = Divan.type.figureSmall) }
                    MeterBar(used, tone = if (used >= 90) BarTone.NEG else if (used >= 70) BarTone.WARN else BarTone.SILVER)
                }
                FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    s.resetsAt?.let { Text("ریست ${until(it)}", style = Divan.type.micro, color = c.textMuted) }
                    s.connection?.let { Fig(it, style = Divan.type.figureSmall, color = c.textMuted) }
                }
                val paused = q.data!!.throttle.pausedPriorities
                if (paused.isNotEmpty()) Text(figs("کارهای ${paused.joinToString("، ")} تا ریست سهمیه نگه داشته شده‌اند."), style = Divan.type.caption,
                    modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.softWarning).padding(10.dp))
            }
        }
    }
}

private val MODELS = listOf("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5")

/** "What would this month have cost on model X" from our own price table (design list #22). */
@Composable
fun WhatIfCard() {
    val c = Divan.colors
    var model by rememberSaveable { mutableStateOf(MODELS[2]) }
    val today = com.coinepro.hq.core.format.HqClock.today()
    val q = rememberQuery("treasury:what-if:$model:$today", "treasury") { whatIf(model, today.withDayOfMonth(1).toString(), today.toString()) }
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("اگر با این مدل بود…", note = "همین فراخوانی‌های این ماه، با جدول قیمت خودمان")
        com.coinepro.hq.designsystem.ScrollRow(Modifier.padding(top = 10.dp)) { MODELS.forEach { m -> FilterChip(modelLabel(m), model == m, { model = m }) } }
        val d = q.data
        when {
            d == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
            d == null -> Skeleton(Modifier.fillMaxWidth().height(64.dp).padding(top = 8.dp))
            else -> {
                val diff = d.differenceUsd?.toDoubleOrNull()
                Row(Modifier.padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Box3("واقعی", usd(d.actualUsd), c.tile, Modifier.weight(1f))
                    Box3("با ${modelLabel(model)}", d.whatIfUsd?.let { usd(it) } ?: "—", c.tile, Modifier.weight(1f))
                    Box3(if (diff == null) "فرق" else if (diff < 0) "ارزان‌تر" else "گران‌تر", diff?.let { usd(kotlin.math.abs(it)) } ?: "—", if (diff == null) c.tile else if (diff < 0) c.softPositive else c.softWarning, Modifier.weight(1f))
                }
                Text(figs("${d.pricedCalls} از ${d.calls} فراخوانی قیمت داشت. فقط هزینه است، نه کیفیت؛ مقایسه‌ی کیفیت با ارزیابی آکادمی."), style = Divan.type.micro, color = c.textMuted, modifier = Modifier.padding(top = 8.dp))
            }
        }
    }
}

@Composable
private fun Box3(label: String, value: String, bg: androidx.compose.ui.graphics.Color, modifier: Modifier) {
    Column(modifier.clip(RoundedCornerShape(12.dp)).background(bg).padding(10.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Text(figs(label), style = Divan.type.micro, color = Divan.colors.textMuted, maxLines = 1)
        Fig(value, style = Divan.type.figure.copy(fontWeight = FontWeight.SemiBold))
    }
}

private fun m(v: Long?) = v?.let { (it / 1_000_000.0).let { x -> if (x == Math.floor(x)) x.toLong().toString() else x.toString() } }.orEmpty()

/** Budgets per scope and period (§9 PUT /budgets): the holding's month in tokens and dollars, each company's month and day. Sealed on the body. */
@Composable
fun BudgetSheet(onDismiss: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val action = rememberAction()
    val c = Divan.colors
    val companies = rememberCompanies()
    val q = rememberQuery("treasury:budgets", "treasury") { budgets() }
    val tok = remember { mutableStateMapOf<String, String>() }
    val usdV = remember { mutableStateMapOf<String, String>() }
    val holding = companies.firstOrNull { it.kind == "holding" }?.code ?: "HQ"
    val scopes = listOf(Triple("holding", holding, "month")) + companies.filter { it.kind != "holding" }.flatMap { listOf(Triple("company", it.code, "month"), Triple("company", it.code, "day")) }
    val key = { s: Triple<String, String, String> -> "${s.first}-${s.second}-${s.third}" }
    LaunchedEffect(q.data, companies) {
        val list = q.data ?: return@LaunchedEffect
        for (s in scopes) if (key(s) !in tok) {
            val b = list.firstOrNull { it.scopeType == s.first && it.company == s.second && it.period == s.third }
            tok[key(s)] = m(b?.tokenLimit); usdV[key(s)] = b?.usdLimit.orEmpty()
        }
    }
    val valid = scopes.all { s -> tok[key(s)].orEmpty().isBlank() || parseMillions(tok[key(s)].orEmpty()) != null } && scopes.all { s -> usdV[key(s)].orEmpty().isBlank() || (usdV[key(s)]!!.toDoubleOrNull() ?: -1.0) > 0 }
    HqSheet(onDismiss, "ویرایش بودجه‌ها", sub = "به میلیون توکن؛ خالی یعنی بی‌سقف. پاکت ماهانه‌ی هر شرکت همان سقف استخدام مدیرعامل است.") {
        if (q.data == null) Skeleton(Modifier.fillMaxWidth().height(160.dp))
        else scopes.filter { it.third == "month" }.forEach { s ->
            val day = scopes.firstOrNull { it.first == s.first && it.second == s.second && it.third == "day" }
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    if (s.first == "company") CompanyMark(s.second, height = 12.dp, mono = true, ink = c.textSecondary)
                    Text(if (s.first == "holding") "کل هلدینگ" else companyOf(companies, s.second).nameFa, style = Divan.type.small)
                }
                CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                        Field("month M", tok[key(s)].orEmpty(), { tok[key(s)] = it }, Modifier.weight(1f))
                        if (day != null) Field("day M", tok[key(day)].orEmpty(), { tok[key(day)] = it }, Modifier.weight(1f))
                        Field("month $", usdV[key(s)].orEmpty(), { usdV[key(s)] = it }, Modifier.weight(1f))
                    }
                }
            }
        }
        HqButton("ذخیره با گذرکلید", {
            action.run {
                val rows = scopes.filter { s -> tok[key(s)].orEmpty().isNotBlank() || usdV[key(s)].orEmpty().isNotBlank() }.map { s ->
                    BudgetRowIn(s.second, s.first, s.second, s.third, parseMillions(tok[key(s)].orEmpty()), usdV[key(s)].orEmpty().takeIf { it.isNotBlank() }?.toDouble()?.let { String.format(java.util.Locale.US, "%.2f", it) })
                }
                env.api.putBudgets(rows) { target -> env.auth.stepUp(act, "budgets.update", target) }
                env.cache.invalidate("treasury", "hiring")
                toasts.ok("بودجه‌ها ذخیره شد.")
                onDismiss()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEAL, enabled = q.data != null && valid, loading = action.busy)
    }
}

@Composable
private fun Field(label: String, value: String, onChange: (String) -> Unit, modifier: Modifier) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Fig(label, style = Divan.type.figureSmall, color = Divan.colors.textMuted)
        HqTextField(value, onChange, "—", Modifier.fillMaxWidth(), maxLength = 10, figure = true)
    }
}

/** One connection (§10): name and on/off with If-Match and a passkey; its key is write-only and never comes back. */
@Composable
fun ConnectionSheet(x: Connection, onDismiss: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val action = rememberAction()
    val c = Divan.colors
    var name by rememberSaveable { mutableStateOf(x.displayName) }
    var on by rememberSaveable { mutableStateOf(x.status != "disabled") }
    var secret by remember { mutableStateOf("") }
    val takesKey = x.kind != "claude_subscription"
    val changed = name.trim() != x.displayName || on != (x.status != "disabled")
    HqSheet(onDismiss, x.displayName, ref = "${x.key} · ${x.provider}") {
        HqTextField(name, { name = it }, "نام", Modifier.fillMaxWidth(), maxLength = 120)
        Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(if (on) "روشن؛ مسیریاب از آن استفاده میکند" else "خاموش؛ هیچ فراخوانی از آن رد نمیشود", style = Divan.type.small, modifier = Modifier.weight(1f))
            HqSwitch(on, { on = it }, "روشن")
        }
        if (takesKey) {
            CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                HqTextField(secret, { secret = it }, if (x.hasSecretRef) "کلید فعلی میماند مگر کلید تازه بدهی" else "کلید API", Modifier.fillMaxWidth(), maxLength = 500, figure = true)
            }
            Text("مستقیم به خزانه‌ی رمزها میرود؛ نه اینجا نمایش داده میشود و نه در Audit.", style = Divan.type.micro, color = c.textMuted)
        } else Text("اشتراک Claude کلید ندارد؛ اعتبارش روی خود سرور است.", style = Divan.type.caption, color = c.textMuted)
        HqButton("ذخیره با گذرکلید", {
            action.run {
                if (changed) env.api.patchConnection(x, ConnectionPatch(displayName = name.trim().takeIf { it != x.displayName }, status = if (on != (x.status != "disabled")) (if (on) "enabled" else "disabled") else null)) { a, t -> env.auth.stepUp(act, a, t) }
                if (secret.isNotBlank()) env.api.connectionSecret(x.id, secret.trim()) { a, t -> env.auth.stepUp(act, a, t) }
                secret = ""
                env.cache.invalidate("treasury")
                toasts.ok("اتصال به‌روز شد.")
                onDismiss()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEAL, enabled = changed || secret.isNotBlank(), loading = action.busy)
    }
}

private val CALL_STATUS = mapOf("ok" to "موفق", "error" to "خطا", "refused" to "رد")

/** Every model call, metadata only (§10 GET /treasury/calls): never the prompt or the response; paged, exportable. */
@Composable
fun CallsCard() {
    val c = Divan.colors
    val env = LocalEnv.current
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val toasts = LocalToasts.current
    var status by rememberSaveable { mutableStateOf<String?>(null) }
    val pages = remember(status) { mutableStateListOf<CallRow>() }
    var next by remember(status) { mutableStateOf<String?>(null) }
    var loading by remember(status) { mutableStateOf(true) }
    var error by remember(status) { mutableStateOf<ApiException?>(null) }
    fun load(cursor: String?) = scope.launch {
        loading = true
        try { val p = env.api.calls(status = status, cursor = cursor); pages.addAll(p.items); next = p.nextCursor; error = null }
        catch (e: ApiException) { error = e; if (cursor != null) toasts.error(e.messageFa) }
        finally { loading = false }
    }
    LaunchedEffect(status) { load(null) }
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("فراخوانی‌ها", note = "فقط متادیتا؛ متن پرامپت و پاسخ هرگز اینجا نیست", action = if (pages.isNotEmpty()) ({
            ExportButton {
                shareCsv(ctx, "calls.csv", listOf("started_at", "company", "actor", "work", "model", "status", "input", "output", "cache_read", "latency_ms", "equiv_usd"),
                    pages.map { x -> listOf(x.startedAt, x.company, x.actor, x.workRef, x.model, x.status, x.inputTokens, x.outputTokens, x.cacheReadTokens, x.latencyMs, x.equivCostUsd) })
            }
        }) else null)
        com.coinepro.hq.designsystem.ScrollRow(Modifier.padding(top = 10.dp)) {
            listOf(null to "همه", "ok" to "موفق", "error" to "خطا", "refused" to "رد").forEach { (k, l) -> FilterChip(l, status == k, { status = k }) }
        }
        when {
            pages.isEmpty() && error != null -> ErrorBlock(error, { load(null) })
            pages.isEmpty() && loading -> Skeleton(Modifier.fillMaxWidth().height(160.dp).padding(top = 8.dp))
            pages.isEmpty() -> Text("فراخوانی‌ای نیست.", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.padding(top = 8.dp))
            else -> Column(Modifier.padding(top = 8.dp)) {
                pages.forEachIndexed { i, x ->
                    if (i > 0) HorizontalDivider(color = c.lineDivider)
                    Column(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            CompanyMark(x.company, height = 10.dp, mono = true, ink = c.textSecondary)
                            Fig(x.actor, style = Divan.type.figureSmall.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, modifier = Modifier.weight(1f))
                            Text(CALL_STATUS[x.status] ?: x.status, style = Divan.type.micro, color = when (x.status) { "error" -> c.negative; "refused" -> c.warning; else -> c.textSecondary })
                            Fig(usd(x.equivCostUsd, 3), style = Divan.type.figureSmall.copy(fontWeight = FontWeight.SemiBold))
                        }
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            Text(jDateTime(x.startedAt), style = Divan.type.micro, color = c.textMuted)
                            x.model?.let { com.coinepro.hq.designsystem.ModelName(it, size = 11.dp, style = Divan.type.figureSmall, color = c.textMuted) } ?: Fig("—", style = Divan.type.figureSmall, color = c.textMuted)
                            Fig("in ${tokens(x.inputTokens)} · out ${tokens(x.outputTokens)} · cache ${tokens(x.cacheReadTokens)}", style = Divan.type.figureSmall, color = c.textMuted)
                            x.latencyMs?.let { Fig(String.format(java.util.Locale.US, "%.1fs", it / 1000.0), style = Divan.type.figureSmall, color = c.textMuted) }
                            x.workRef?.let { Fig(it, style = Divan.type.figureSmall, color = c.textMuted) }
                        }
                    }
                }
                if (next != null) HqButton("بیشتر", { load(next) }, Modifier.fillMaxWidth().padding(top = 8.dp), size = BtnSize.SM, loading = loading)
            }
        }
    }
}

