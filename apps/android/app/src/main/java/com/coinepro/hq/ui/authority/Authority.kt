package com.coinepro.hq.ui.authority

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.tokens
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.core.net.AuthorityChange
import com.coinepro.hq.core.net.AuthorityRule
import com.coinepro.hq.core.net.limitDays
import com.coinepro.hq.core.net.limitNumber
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v16.ChipRow
import com.coinepro.hq.ui.v16.prose
import com.coinepro.hq.ui.v17.ACTOR_ROLE_FA
import com.coinepro.hq.ui.v17.WEEKDAY_FA
import com.coinepro.hq.ui.v17.gov
import com.coinepro.hq.ui.v17.num
import java.util.Locale
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

private val UNIT = mapOf("tokens_month" to "توکن در ماه", "usd" to "دلار", "count_day" to "در روز", "count_hour" to "در ساعت", "items" to "کارت")
private val CLASS_TONE = mapOf("A0" to Tone.NEUTRAL, "A1" to Tone.LAPIS, "A2" to Tone.GOLD, "A3" to Tone.WARN, "A4" to Tone.NEG)

/** A limit in words: $2.00, 2M توکن در ماه, 5 در روز, پنجشنبه، جمعه. */
fun limitFa(l: JsonObject?): String {
    limitNumber(l)?.let { (k, v) -> return if (k == "usd") usd(v) else if (k == "tokens_month") "${tokens(v.toLong())} ${UNIT[k]}" else "${num(v)} ${UNIT[k]}" }
    limitDays(l)?.let { ds -> return ds.joinToString("، ") { WEEKDAY_FA[it] ?: it } }
    return "—"
}

/** ماتریس اختیار (contract §20.7): rows OPA reads as data; the locked invariants hold whatever the data says. */
@Composable
fun AuthorityScreen() {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val q = rememberQuery("authority", "authority") { authority() }
    val drafts = remember { mutableStateMapOf<String, AuthorityChange>() }
    var confirm by remember { mutableStateOf(false) }
    val action = rememberAction()
    val rules = q.data.orEmpty()
    val changes = drafts.values.toList()
    val bad = changes.any { ch -> val r = rules.firstOrNull { it.key == ch.key }; val n = limitNumber(ch.limit); r?.bounds != null && n != null && (n.second < r.bounds.min || n.second > r.bounds.max) }
    val r = refresher(q)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            PageHeader("ماتریس اختیار", eyebrow = "قاعده‌ها داده‌اند و OPA میخواندشان؛ ثابت‌های قفل مستقل از داده‌اند") {
                HqButton(if (changes.isEmpty()) "ذخیره" else "ذخیره (${changes.size})", { confirm = true }, variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, enabled = changes.isNotEmpty() && !bad)
            }
        }
        item {
            Text(
                "فقط ردیف‌های باز و فقط داخل محدوده‌ی هر ردیف عوض میشوند؛ ذخیره با اثر انگشت روی همین تغییرهای دقیق است. ایجنت‌ها ماتریس را نمیتوانند عوض کنند و فقط با کارت «تغییر ماتریس اختیار» پیشنهاد میدهند.",
                style = Divan.type.small, color = c.textSecondary,
            )
        }
        when {
            q.data == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            q.data == null -> item { Skeleton(Modifier.fillMaxWidth().height(360.dp), radius = 16.dp) }
            else -> {
                item(key = "open") {
                    HqCard(Modifier.fillMaxWidth()) {
                        SectionTitle("ردیف‌های باز", note = "سقف‌ها، سهمیه‌ها و این‌که چه کسی تأیید میکند")
                        for (rule in rules.filter { !it.locked }) {
                            Spacer(Modifier.height(12.dp))
                            Box(Modifier.fillMaxWidth().height(1.dp).background(c.lineDivider))
                            Spacer(Modifier.height(12.dp))
                            RuleRow(rule, drafts[rule.key]) { ch -> if (ch == null) drafts.remove(rule.key) else drafts[rule.key] = ch }
                        }
                    }
                }
                item(key = "locked") {
                    HqCard(Modifier.fillMaxWidth()) {
                        SectionTitle("ثابت‌های قفل", note = "در کد، مستقل از داده؛ هیچ ذخیره‌ای عوضشان نمیکند")
                        Spacer(Modifier.height(10.dp))
                        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            for (rule in rules.filter { it.locked }) androidx.compose.foundation.layout.Row(
                                Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), horizontalArrangement = Arrangement.spacedBy(10.dp),
                            ) {
                                DIcon(DivanIcon.LOCK, Modifier.padding(top = 2.dp), size = 16.dp, tint = c.negative)
                                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                    Text(prose(rule.titleFa), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                                    if (rule.noteFa.isNotBlank()) Text(prose(rule.noteFa), style = Divan.type.caption, color = c.textSecondary)
                                    Fig(rule.key, style = Divan.type.figureSmall, color = c.textMuted)
                                }
                                Pill(rule.actionClass, CLASS_TONE[rule.actionClass] ?: Tone.NEUTRAL, figure = true)
                            }
                        }
                    }
                }
            }
        }
    }
    if (confirm) AlertDialog(
        onDismissRequest = { confirm = false },
        containerColor = c.overlay,
        title = { Text("ذخیره‌ی ماتریس اختیار", style = Divan.type.h3) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("این ردیف‌ها عوض میشوند:", style = Divan.type.small, color = c.textSecondary)
                for (ch in changes) {
                    val rule = rules.firstOrNull { it.key == ch.key }
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(prose(rule?.titleFa.orEmpty()), style = Divan.type.small, color = c.textPrimary)
                        Text(prose(limitFa(rule?.limit)), style = Divan.type.small.copy(textDecoration = TextDecoration.LineThrough), color = c.textMuted)
                        Text(prose(limitFa(ch.limit)), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                        if (ch.actor != null) Text("فقط با تو", style = Divan.type.small, color = c.goldInk)
                    }
                }
            }
        },
        confirmButton = {
            HqButton("مُهر با passkey", {
                action.gov(toasts) {
                    env.api.putAuthority(changes) { a, x -> env.auth.stepUp(act, a, x) }
                    env.cache.invalidate("authority", "decisions")
                    drafts.clear(); confirm = false
                    toasts.ok("ماتریس اختیار مُهر و ذخیره شد؛ OPA از همین لحظه عدد تازه را اجرا میکند.")
                }
            }, variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, loading = action.busy)
        },
        dismissButton = { HqButton("انصراف", { confirm = false }, variant = BtnVariant.GHOST) },
    )
}

private fun numberOf(v: Double): JsonPrimitive = if (v % 1.0 == 0.0) JsonPrimitive(v.toLong()) else JsonPrimitive(v)

@Composable
private fun RuleRow(r: AuthorityRule, draft: AuthorityChange?, onChange: (AuthorityChange?) -> Unit) {
    val c = Divan.colors
    val limit = if (draft != null) draft.limit else r.limit
    val actor = draft?.actor ?: r.actor
    val n = limitNumber(limit)
    val days = limitDays(limit)
    val out = n != null && r.bounds != null && (n.second < r.bounds.min || n.second > r.bounds.max)
    var text by remember(r.key, r.version) { mutableStateOf(n?.second?.let(::num).orEmpty()) }
    fun set(nextLimit: JsonObject?, nextActor: String) {
        val same = nextLimit == r.limit && nextActor == r.actor
        onChange(if (same) null else AuthorityChange(r.key, if (nextActor != r.actor) nextActor else null, nextLimit, r.version))
    }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        androidx.compose.foundation.layout.Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(prose(r.titleFa), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                Fig("${r.key} · ${r.action}", style = Divan.type.figureSmall, color = c.textMuted)
            }
            Pill(r.actionClass, CLASS_TONE[r.actionClass] ?: Tone.NEUTRAL, figure = true)
            if (r.stepUp) DIcon(DivanIcon.SEAL, size = 16.dp, tint = c.goldInk, label = "با اثر انگشت")
        }
        if (r.noteFa.isNotBlank()) Text(prose(r.noteFa), style = Divan.type.caption, color = c.textSecondary)
        androidx.compose.foundation.layout.Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("${ACTOR_ROLE_FA[actor] ?: actor} · ${if (r.scope == "holding") "هلدینگ" else "شرکت خودش"}", style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.weight(1f))
            if (r.actor != "owner") {
                Text("فقط با تو", style = Divan.type.micro, color = c.textMuted)
                HqSwitch(actor == "owner", { v -> set(limit, if (v) "owner" else r.actor) }, "فقط با تو: ${r.titleFa}")
            }
        }
        when {
            n != null -> androidx.compose.foundation.layout.Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                    HqTextField(text, { v ->
                        val clean = v.filter { it.isDigit() || it == '.' }
                        text = clean
                        val num = clean.toDoubleOrNull() ?: 0.0
                        set(JsonObject((limit ?: JsonObject(emptyMap())) + (n.first to numberOf(num))), actor)
                    }, "0", Modifier.width(120.dp), maxLength = 12, figure = true)
                }
                Text(UNIT[n.first].orEmpty(), style = Divan.type.caption, color = c.textMuted)
                r.bounds?.let { b ->
                    Text(buildAnnotatedString { append("بین "); fig(String.format(Locale.US, "%,.0f", b.min)); append(" و "); fig(String.format(Locale.US, "%,.0f", b.max)) }, style = Divan.type.micro, color = if (out) c.negative else c.textMuted)
                }
            }
            days != null -> ChipRow {
                for ((d, fa) in WEEKDAY_FA) {
                    val on = d in days
                    FilterChip(fa, on, { set(JsonObject((limit ?: JsonObject(emptyMap())) + ("days" to JsonArray((if (on) days - d else days + d).map { x -> JsonPrimitive(x) }))), actor) })
                }
            }
            else -> Text("بی‌سقف عددی", style = Divan.type.caption, color = c.textMuted)
        }
    }
}
