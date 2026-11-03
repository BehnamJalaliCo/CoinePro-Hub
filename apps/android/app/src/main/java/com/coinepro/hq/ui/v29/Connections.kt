package com.coinepro.hq.ui.v29

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.CONNECTION_STATE_FA
import com.coinepro.hq.core.data.connectionKindFa
import com.coinepro.hq.core.data.metricFa
import com.coinepro.hq.core.data.numberText
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.net.CompanyConnection
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Radius
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Loadable
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

// Contract §29.12 ⟨1.11⟩: what can be measured and managed per company. Each kind (Search Console, Analytics, Instagram through IG-Hub,
// Telegram, YouTube, X, site speed, Trends, Bing, Play Console) with its state, when it was last read and its daily figures; «وصل کن»
// opens the one-page guide, the settings and the write-only key (🔏, never shown back: only «گذاشته شده» or «نیست»).

@Composable
fun rememberConnections(code: String) =
    rememberQuery("connections29:$code", "connections", maxAgeMs = 60_000) { gated(HubFeature.CONNECTIONS) { companyConnections(code) } }

/** The company's «اتصال‌ها» tab; [open0] opens one kind's guide at once (a blocker's or a readiness check's «وصل کن»). */
@Composable
fun CompanyConnections(code: String, open0: String? = null) {
    val q = rememberConnections(code)
    var open by rememberSaveable(code) { mutableStateOf(open0) }
    if (!served(HubFeature.CONNECTIONS)) {
        Empty("اتصال‌ها با به‌روزرسانی بعدی هاب میایند", icon = DivanIcon.GLOBE)
        return
    }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(
            "هر عددی که کارگروه‌ها میبینند از همین اتصال‌ها میاید، هر روز و بدون حدس. کلیدها فقط در گاوصندوق هاب میمانند و هیچ‌وقت نشان داده نمیشوند.",
            style = Divan.type.caption.copy(textAlign = androidx.compose.ui.text.style.TextAlign.Justify), color = Divan.colors.textMuted,
        )
        Loadable(q, skeleton = { Skeleton(Modifier.fillMaxWidth().height(200.dp), radius = 16.dp) }) { list ->
            if (list.isNullOrEmpty()) Empty("اتصالی تعریف نشده", icon = DivanIcon.GLOBE)
            else { for (x in list) ConnectionCard(x) { open = x.kind } }
        }
    }
    open?.let { kind ->
        val x = q.data?.firstOrNull { it.kind == kind } ?: CompanyConnection(company = code, kind = kind)
        ConnectionSheet(code, x) { open = null }
    }
}

@Composable
private fun ConnectionCard(x: CompanyConnection, onOpen: () -> Unit) {
    val c = Divan.colors
    val (fa, tone) = CONNECTION_STATE_FA[x.state] ?: (x.state to Tone.NEUTRAL)
    HqCard(Modifier.fillMaxWidth(), tahrir = x.state == "error") {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            IconTile(DivanIcon.GLOBE, if (x.state == "connected") c.positive else c.textSecondary, if (x.state == "connected") c.softPositive else c.tile, 36.dp)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(connectionKindFa(x.kind, x.labelFa), style = Divan.type.bodyStrong)
                Text(
                    plain(x.lastReadAt?.let { "آخرین خواندن ${ago(it)}" } ?: "هنوز خوانده نشده"),
                    style = Divan.type.micro, color = c.textMuted,
                )
            }
            Pill(fa, tone, dot = true)
        }
        x.lastErrorFa?.takeIf { it.isNotBlank() && x.state == "error" }?.let {
            Text(plain(it), style = Divan.type.caption, color = c.negative, modifier = Modifier.padding(top = 8.dp))
        }
        // The last day's figures, each key in words.
        val last = x.daily.maxOfOrNull { it.day }
        val today = x.daily.filter { it.day == last }
        if (today.isNotEmpty()) Column(Modifier.padding(top = 10.dp).fillMaxWidth().clip(RoundedCornerShape(Radius.tile)).background(c.tile).padding(10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(plain("عددهای ${jDate(last)}"), style = Divan.type.micro, color = c.textMuted)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                for (d in today) Column {
                    Text(metricFa(d.key), style = Divan.type.micro, color = c.textSecondary)
                    Fig(d.value?.let { numberText(it) } ?: "—", style = Divan.type.figure, color = c.textPrimary)
                }
            }
        }
        Row(Modifier.padding(top = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(if (x.secret == "set") "کلید گذاشته شده" else "کلید نیست", style = Divan.type.micro, color = if (x.secret == "set") c.positive else c.textMuted, modifier = Modifier.weight(1f))
            HqButton(if (x.state == "connected") "تنظیم" else "وصل کن", onOpen, variant = if (x.state == "connected") BtnVariant.SECONDARY else BtnVariant.PRIMARY, size = BtnSize.SM, icon = if (x.state == "connected") DivanIcon.SETTINGS else DivanIcon.ADD)
        }
    }
}

/** One connection in its sheet. */
@Composable
private fun ConnectionSheet(code: String, x: CompanyConnection, onDone: () -> Unit) {
    com.coinepro.hq.ui.v14.HqSheet(onDone, connectionKindFa(x.kind, x.labelFa), sub = "راهنمای یک‌صفحه‌ای، تنظیم و کلید") { ConnectionBody(code, x) }
}

/** One connection: its guide, its settings (non-secret), the write-only key and a test. */
@Composable
fun ConnectionBody(code: String, x: CompanyConnection) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val act = activity()
    val guide = rememberQuery("connection-guide:${x.kind}", "connections", maxAgeMs = 300_000) { gated(HubFeature.CONNECTIONS) { connectionGuide(x.kind) } }
    val values = remember(x.kind) { mutableStateMapOf<String, String>().apply { for ((k, v) in x.config) put(k, (v as? JsonPrimitive)?.contentOrNull ?: v.toString()) } }
    var secret by remember(x.kind) { mutableStateOf("") }
    val save = rememberAction()
    val key = rememberAction()
    val test = rememberAction()
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Loadable(guide, skeleton = { Skeleton(Modifier.fillMaxWidth().height(140.dp)) }) { g ->
            if (g != null) Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                if (g.titleFa.isNotBlank()) Text(plain(g.titleFa), style = Divan.type.bodyStrong)
                Md(g.bodyMd)
                val fields = g.fields.ifEmpty { values.keys.map { com.coinepro.hq.core.net.GuideField(it, it) } }
                if (fields.isNotEmpty()) {
                    HorizontalDivider(color = c.lineDivider)
                    SectionTitle("تنظیم", note = "چیزهایی که راز نیستند؛ با مُهر تو ذخیره میشوند")
                    for (f in fields) Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(plain(f.labelFa.ifBlank { f.key }), style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                        HqTextField(values[f.key].orEmpty(), { values[f.key] = it }, f.hintFa.ifBlank { f.key }, Modifier.fillMaxWidth(), figure = true)
                    }
                    HqButton("ذخیره‌ی تنظیم", {
                        save.run {
                            val cfg = JsonObject(values.filterValues { it.isNotBlank() }.mapValues { JsonPrimitive(it.value.trim()) })
                            env.api.putConnectionConfig(code, x.kind, cfg) { a, t -> env.auth.stepUp(act, a, t) }
                            env.cache.invalidate("connections", "readiness")
                            toasts.ok("تنظیم ذخیره شد.")
                        }
                    }, Modifier.fillMaxWidth(), icon = DivanIcon.SEAL, loading = save.busy)
                }
                HorizontalDivider(color = c.lineDivider)
                SectionTitle("کلید", note = if (x.secret == "set") "کلید گذاشته شده؛ برای عوض کردن، تازه‌اش را بگذار" else "فقط یک بار میگذاری؛ هیچ‌وقت نشان داده نمیشود")
                com.coinepro.hq.ui.v18.SecretField(secret, { secret = it }, "••••••••", label = "کلید ${connectionKindFa(x.kind, x.labelFa)}")
                HqButton(g.secretLabelFa?.let { "ثبت $it" } ?: "ثبت کلید", {
                    key.run {
                        env.api.putConnectionSecret(code, x.kind, secret.trim()) { a, t -> env.auth.stepUp(act, a, t) }
                        secret = ""
                        env.cache.invalidate("connections", "readiness")
                        toasts.ok("کلید در گاوصندوق هاب گذاشته شد.")
                    }
                }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.LOCK, enabled = secret.isNotBlank(), loading = key.busy)
                HqButton("آزمایش اتصال", {
                    test.run {
                        val t = env.api.testConnection(code, x.kind)
                        env.cache.invalidate("connections", "readiness")
                        if (t.ok) toasts.ok(t.messageFa.ifBlank { "وصل است؛ از فردا هر روز خوانده میشود." }) else toasts.error(t.messageFa.ifBlank { "هنوز وصل نشد؛ راهنما را دوباره نگاه کن." })
                    }
                }, Modifier.fillMaxWidth(), variant = BtnVariant.GHOST, icon = DivanIcon.REFRESH, loading = test.busy)
            }
        }
    }
}
