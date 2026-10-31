package com.coinepro.hq.ui.tools

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
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.CONNECTION_STATUS
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.CONNECTION_KEY
import com.coinepro.hq.core.net.ConnLimits
import com.coinepro.hq.core.net.Connection
import com.coinepro.hq.core.net.ConnectionIn
import com.coinepro.hq.core.net.Price
import com.coinepro.hq.core.net.ROUTER_PROVIDERS
import com.coinepro.hq.core.net.publicHttps
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.ModelMark
import com.coinepro.hq.designsystem.ModelName
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v14.Label
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v16.Chip
import com.coinepro.hq.ui.v16.Notice
import com.coinepro.hq.ui.v16.TerminalCommand
import com.coinepro.hq.ui.v18.CONN
import com.coinepro.hq.ui.v18.SecretField
import com.coinepro.hq.ui.v18.mgmt
import java.util.Locale
import java.util.UUID
import kotlinx.coroutines.delay
import kotlinx.serialization.json.Json

// «اتصال تازه‌ی مدل» (contract §21.7), mirroring apps/web/src/components/v18/connection.tsx: provider, models and prices, sealed with the
// passkey on the exact body; then the secret, through the existing write-only route or the owner's own terminal; the router then
// checks it with a call that costs nothing. Its use is only ever through an assignment the owner seals.

private val PROVIDER_FA = mapOf("anthropic" to "Anthropic", "openai" to "OpenAI", "google" to "Google", "deepseek" to "DeepSeek", "mistral" to "Mistral", "openai_compatible" to "سازگار با OpenAI")
private val STEPS = listOf("ارائه‌دهنده", "مدل‌ها و قیمت", "مرور و مُهر", "کلید")
private fun dec(s: String) = s.trim().isNotEmpty() && s.trim().toDoubleOrNull()?.let { it >= 0 } == true

/** What the owner fills in; [body] is exactly what is sent and sealed. */
class ConnectionDraft {
    var provider by mutableStateOf("openai")
    var kind by mutableStateOf("api_key")
    var key by mutableStateOf("")
    var displayName by mutableStateOf("")
    var baseUrl by mutableStateOf("")
    var models by mutableStateOf("")
    var defaultModel by mutableStateOf("")
    val priceIn = mutableStateMapOf<String, String>()
    val priceOut = mutableStateMapOf<String, String>()
    var rpm by mutableStateOf("")
    var tpm by mutableStateOf("")
    var dailyUsd by mutableStateOf("")
    var fallback by mutableStateOf("")

    fun modelList(): List<String> = models.split(Regex("[\\s,،]+")).map { it.trim() }.filter { it.isNotEmpty() }.distinct()

    fun body(): ConnectionIn {
        val ms = modelList()
        return ConnectionIn(
            key = key.trim(), provider = provider, kind = kind, displayName = displayName.trim(),
            baseUrl = baseUrl.trim().takeIf { provider == "openai_compatible" && it.isNotEmpty() },
            models = ms, defaultModel = defaultModel.takeIf { it in ms },
            pricing = ms.filter { dec(priceIn[it].orEmpty()) && dec(priceOut[it].orEmpty()) }.associateWith {
                Price(String.format(Locale.US, "%.2f", priceIn[it]!!.trim().toDouble()), String.format(Locale.US, "%.2f", priceOut[it]!!.trim().toDouble()))
            },
            limits = ConnLimits(rpm.trim().toIntOrNull(), tpm.trim().toIntOrNull(), dailyUsd.trim().toDoubleOrNull()?.let { String.format(Locale.US, "%.2f", it) }),
            fallbackPriority = fallback.trim().toIntOrNull(),
        )
    }

    val ok0: Boolean get() = CONNECTION_KEY.matches(key.trim()) && displayName.trim().length >= 2 && (provider != "openai_compatible" || (baseUrl.isNotBlank() && publicHttps(baseUrl)))
    val ok1: Boolean get() = modelList().isNotEmpty() && modelList().all { m -> priceIn[m].orEmpty().let { it.isBlank() || dec(it) } && priceOut[m].orEmpty().let { it.isBlank() || dec(it) } }
}

private val PRETTY = Json(Api.json) { prettyPrint = true }

/** The model connections on the tools page, with the wizard and the secret step for one waiting for its key. */
@Composable
fun ConnectionsCard() {
    val c = Divan.colors
    val q = rememberQuery("connections", "treasury") { connections() }
    var wizard by remember { mutableStateOf<Connection?>(null) }
    var making by remember { mutableStateOf(false) }
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("اتصال‌های مدل", note = "کلیدها هرگز نمایش داده نمیشوند؛ تخصیص هر نقش در خزانه") {
            HqButton("اتصال تازه", { making = true }, size = BtnSize.SM, variant = BtnVariant.PRIMARY, icon = DivanIcon.ADD)
        }
        val list = q.data
        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            if (list == null) Skeleton(Modifier.fillMaxWidth().height(120.dp))
            else list.forEach { x ->
                val waiting = x.status in setOf("pending_secret", "verifying", "error")
                Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(if (waiting) c.softGold else c.tile).padding(10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    ModelMark(x.defaultModel ?: x.models.firstOrNull(), provider = x.provider, size = 20.dp)
                    Column(Modifier.weight(1f)) {
                        Text(x.displayName, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 1)
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            Fig(x.key, style = Divan.type.figureSmall, color = c.textMuted)
                            Text(when (x.kind) { "subscription" -> "اشتراک"; "claude_subscription" -> "اشتراک Claude"; else -> "کلید API" }, style = Divan.type.micro, color = c.textMuted)
                        }
                    }
                    if (waiting) HqButton("کلید", { wizard = x }, size = BtnSize.SM, variant = BtnVariant.TEXT, icon = DivanIcon.LOCK)
                    LabelPill(connLabel(x.status), x.status)
                }
            }
        }
    }
    if (making) HqSheet({ making = false }, "اتصال تازه‌ی مدل", sub = "فقط ارائه‌دهنده‌ای که مسیریاب میشناسد؛ نشانی پایه فقط برای سازگار با OpenAI و از محافظ خروجی. استفاده‌اش بعداً فقط با تخصیص و مُهر تو.") {
        ConnectionWizard(onClose = { making = false })
    }
    wizard?.let { w -> HqSheet({ wizard = null }, "کلید اتصال", ref = w.key) { SecretStep(w) { wizard = null } } }
}

private fun connLabel(status: String): Label? = CONN[status] ?: CONNECTION_STATUS[status]?.let { Label(it.first, it.second) }

/** The four steps: the provider, the models and their prices, the exact body to seal, then the key. */
@Composable
fun ConnectionWizard(onClose: () -> Unit, draft: ConnectionDraft = remember { ConnectionDraft() }, step0: Int = 0) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val action = rememberAction()
    var step by rememberSaveable { mutableStateOf(step0) }
    var made by remember { mutableStateOf<Connection?>(null) }
    // One Idempotency-Key per wizard, kept across a retry of the same body.
    val idem = remember { UUID.randomUUID().toString() }
    val d = draft
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            STEPS.forEachIndexed { i, s ->
                Row(Modifier.clip(CircleShape).background(if (i == step) c.softGold else c.tile).padding(horizontal = 10.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("${i + 1}", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = if (i == step) c.goldInk else c.textMuted)
                    Text(s, style = Divan.type.micro.copy(fontWeight = if (i == step) FontWeight.SemiBold else FontWeight.Normal), color = if (i == step) c.goldInk else if (i < step) c.textSecondary else c.textMuted)
                }
            }
        }
        when (step) {
            0 -> Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    for (p in ROUTER_PROVIDERS) Chip(d.provider == p, { d.provider = p }) { ink ->
                        if (p != "openai_compatible") ModelMark(null, provider = p, size = 14.dp) else DIcon(DivanIcon.MODEL, size = 14.dp, tint = ink)
                        Text(PROVIDER_FA[p] ?: p, style = Divan.type.small, color = ink, maxLines = 1)
                    }
                }
                Segmented(listOf(SegOption("api_key", "کلید API (پولی)"), SegOption("subscription", "اشتراک")), d.kind, { d.kind = it }, Modifier.fillMaxWidth())
                Field("کلید اتصال", "حروف کوچک لاتین، عدد و خط تیره؛ یکتا", bad = d.key.isNotEmpty() && !CONNECTION_KEY.matches(d.key.trim())) {
                    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) { HqTextField(d.key, { d.key = it.lowercase() }, "mistral-api", Modifier.fillMaxWidth(), maxLength = 40, figure = true) }
                }
                Field("نام") { HqTextField(d.displayName, { d.displayName = it }, "API میسترال (پشتیبان)", Modifier.fillMaxWidth(), maxLength = 120) }
                if (d.provider == "openai_compatible") Field("نشانی پایه", "فقط https و هرگز نشانی خصوصی (شبکه‌ی هتزنر، localhost)؛ از محافظ خروجی رد میشود.", bad = d.baseUrl.isNotEmpty() && !publicHttps(d.baseUrl)) {
                    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) { HqTextField(d.baseUrl, { d.baseUrl = it }, "https://api.example.com/v1", Modifier.fillMaxWidth(), maxLength = 300, figure = true) }
                }
            }
            1 -> Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Field("مدل‌ها", "با ویرگول یا فاصله؛ شناسه‌ی هر مدل همان‌طور که ارائه‌دهنده میگوید") {
                    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) { HqTextField(d.models, { d.models = it }, "mistral-large-3, mistral-small-3", Modifier.fillMaxWidth(), singleLine = false, minLines = 2, maxLength = 1000, figure = true) }
                }
                val ms = d.modelList()
                if (ms.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("پیش‌فرض و قیمت (دلار برای هر میلیون توکن)", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                    for (m in ms) Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(8.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Box(Modifier.size(20.dp).clip(CircleShape).background(if (d.defaultModel == m) c.goldFill else c.card).clickable(role = Role.RadioButton, onClickLabel = "پیش‌فرض: $m") { d.defaultModel = m })
                        Box(Modifier.weight(1f)) { ModelName(m, provider = d.provider, size = 13.dp, style = Divan.type.figureSmall) }
                        HqTextField(d.priceIn[m].orEmpty(), { d.priceIn[m] = it }, "ورودی", Modifier.width(72.dp), maxLength = 10, figure = true)
                        HqTextField(d.priceOut[m].orEmpty(), { d.priceOut[m] = it }, "خروجی", Modifier.width(72.dp), maxLength = 10, figure = true)
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Field("در دقیقه", modifier = Modifier.weight(1f)) { HqTextField(d.rpm, { d.rpm = it.filter(Char::isDigit) }, "rpm", Modifier.fillMaxWidth(), maxLength = 7, figure = true) }
                    Field("توکن در دقیقه", modifier = Modifier.weight(1f)) { HqTextField(d.tpm, { d.tpm = it.filter(Char::isDigit) }, "tpm", Modifier.fillMaxWidth(), maxLength = 10, figure = true) }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Field("سقف روزانه ($)", modifier = Modifier.weight(1f)) { HqTextField(d.dailyUsd, { d.dailyUsd = it }, "10.00", Modifier.fillMaxWidth(), maxLength = 10, figure = true) }
                    Field("اولویت پشتیبان", modifier = Modifier.weight(1f)) { HqTextField(d.fallback, { d.fallback = it.filter(Char::isDigit) }, "6", Modifier.fillMaxWidth(), maxLength = 3, figure = true) }
                }
            }
            2 -> Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    ModelMark(null, provider = d.provider, size = 20.dp)
                    Text(d.displayName, style = Divan.type.bodyStrong)
                    Fig(d.key, style = Divan.type.figureSmall, color = c.textMuted)
                    Pill(if (d.kind == "api_key") "کلید API" else "اشتراک", Tone.NEUTRAL)
                }
                Text("اثر انگشت به SHA-256 همین بدنه بسته است؛ اگر چیزی عوض شود، مُهر دیگر نمیخورد. نتیجه اتصالی «منتظر کلید» است که هنوز هیچ کاری از آن نمیگذرد.", style = Divan.type.small, color = c.textSecondary)
                CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                    Fig(PRETTY.encodeToString(ConnectionIn.serializer(), d.body()), Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.page).padding(12.dp), style = Divan.type.figureSmall, color = c.textPrimary, maxLines = 60)
                }
            }
            else -> made?.let { SecretStep(it, onClose) } ?: Skeleton(Modifier.fillMaxWidth().height(120.dp))
        }
        if (step < 3) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (step > 0) HqButton("قبلی", { step-- }, variant = BtnVariant.GHOST, icon = DivanIcon.BACK)
            Box(Modifier.weight(1f))
            if (step < 2) HqButton("بعدی", { step++ }, variant = BtnVariant.PRIMARY, icon = DivanIcon.NEXT, enabled = if (step == 0) d.ok0 else d.ok1)
            else HqButton("ساختن با اثر انگشت", {
                action.mgmt(toasts) {
                    val out = env.api.createConnection(d.body(), idem) { a, t -> env.auth.stepUp(act, a, t) }
                    made = out
                    step = 3
                    env.cache.invalidate("treasury")
                    toasts.ok("اتصال ${out.key} ساخته شد؛ منتظر کلید است.")
                }
            }, variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, loading = action.busy)
        }
    }
}

@Composable
private fun Field(label: String, note: String? = null, modifier: Modifier = Modifier, bad: Boolean = false, content: @Composable () -> Unit) {
    val c = Divan.colors
    Column(modifier, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(label, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        content()
        if (note != null) Text(note, style = Divan.type.micro, color = if (bad) c.negative else c.textMuted)
    }
}

/** The secret step: the existing write-only route with a passkey, or the owner's own terminal; then a no-cost check by the router. */
@Composable
fun SecretStep(x0: Connection, onDone: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val nav = LocalNav.current
    val c = Divan.colors
    val action = rememberAction()
    val q = rememberQuery("connections", "treasury") { connections() }
    var secret by remember { mutableStateOf("") }
    val x = q.data?.firstOrNull { it.id == x0.id } ?: x0
    val checking = x.status == "verifying" || x.status == "pending_secret"
    val onScreen = com.coinepro.hq.ui.rememberOnScreen()
    LaunchedEffect(checking, onScreen) { while (checking && onScreen) { delay(2_000); q.refresh() } }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (x.kind == "subscription") {
            Text("اشتراک کلید API ندارد؛ با ورود خود CLI وصل میشود (کد دستگاه از اپ، یا ترمینال خودت).", style = Divan.type.small, color = c.textSecondary)
            HqButton("بازیکن‌های ذخیره و ورودشان", { onDone(); nav.go("substitutes") }, variant = BtnVariant.TEXT, icon = DivanIcon.AGENT)
            HqButton("بستن", onDone)
            return@Column
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            ModelMark(x.defaultModel ?: x.models.firstOrNull(), provider = x.provider, size = 20.dp)
            Text(x.displayName, Modifier.weight(1f), style = Divan.type.bodyStrong)
            LabelPill(connLabel(x.status), x.status)
        }
        when (x.status) {
            "ready", "enabled" -> Notice(DivanIcon.SEAL, c.softPositive, c.positive) { Text("مسیریاب کلید را با یک فراخوانی بی‌هزینه سنجید. استفاده از این اتصال فقط با تخصیص (PUT /assignments) و مُهر توست.", style = Divan.type.small, color = c.textPrimary) }
            "error" -> Notice(DivanIcon.URGENT, c.softNegative, c.negative) { Text("سنجش نشد: ${x.statusReason ?: "—"}. کلید تازه بده.", style = Divan.type.small, color = c.textPrimary) }
            "verifying" -> Notice(DivanIcon.TIME, c.softLapis, c.lapis) { Text("کلید رسید؛ مسیریاب با فهرست مدل‌ها (بی‌هزینه، از درگاه خروجی) آن را میسنجد…", style = Divan.type.small, color = c.textPrimary) }
        }
        if (x.status == "pending_secret" || x.status == "error") {
            Text("کلید، همین‌جا", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            SecretField(secret, { secret = it }, "sk-…", "کلید")
            Text("فقط‌نوشتنی: مستقیم به خزانه‌ی رمزها میرود و نه این‌جا، نه در پاسخ، نه در لاگ و نه در Audit برنمیگردد.", style = Divan.type.micro, color = c.textMuted)
            HqButton("ذخیره با اثر انگشت", {
                action.mgmt(toasts) {
                    env.api.connectionSecret(x.id, secret.trim()) { a, t -> env.auth.stepUp(act, a, t) }
                    secret = ""
                    toasts.ok("کلید رفت؛ در حال سنجش.")
                    q.refresh()
                }
            }, variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, enabled = secret.isNotBlank(), loading = action.busy)
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("یا در ترمینال خودت (ورودی پنهان، مستقیم به OpenBao)", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                TerminalCommand("make connection-secret KEY=${x.key}")
            }
        }
        HqButton(if (x.status == "ready" || x.status == "enabled") "تمام" else "بعداً", onDone)
    }
}
