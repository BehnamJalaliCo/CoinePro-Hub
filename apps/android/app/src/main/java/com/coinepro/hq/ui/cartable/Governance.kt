package com.coinepro.hq.ui.cartable

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.format.decisionKind
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.format.tokens
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.BATCH_REASON_FA
import com.coinepro.hq.core.net.BatchItem
import com.coinepro.hq.core.net.Claim
import com.coinepro.hq.core.net.Decision
import com.coinepro.hq.core.net.RedLine
import com.coinepro.hq.core.net.Votes
import com.coinepro.hq.core.net.govError
import com.coinepro.hq.core.net.limitNumber
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v16.Fact
import com.coinepro.hq.ui.v16.FactRows
import com.coinepro.hq.ui.v16.Notice
import com.coinepro.hq.ui.v16.prose
import com.coinepro.hq.ui.v17.Block
import com.coinepro.hq.ui.v17.DiffView
import com.coinepro.hq.ui.v17.KNOWLEDGE_KIND
import com.coinepro.hq.ui.v17.LAYER_FA
import com.coinepro.hq.ui.v17.RefChip
import com.coinepro.hq.ui.v17.RefTone
import com.coinepro.hq.ui.v17.VERDICT
import com.coinepro.hq.ui.v17.VOTE_FA
import com.coinepro.hq.ui.v17.dayEnd
import com.coinepro.hq.ui.v17.kpiFig
import com.coinepro.hq.ui.v17.num as figNum
import java.util.UUID
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

// ⟨1.5⟩ Contract §20 in the cartable: the batch seal (§20.10), the payloads of the governance kinds (§20.11, ⟨1.5.1⟩ shapes), the
// measurable promise of a proposal and its 30/60/90-day reviews (§20.6). Mirrors apps/web/src/components/v17/cartable.tsx.

// ----------------------------------------------------------------- batch seal --
/** «مُهر گروهی»: shown when there are pending low-risk A1 cards the hub allows to seal together. */
@Composable
fun BatchSealButton() {
    val q = rememberQuery("decisions:batchable", "decisions") { batchable() }
    var open by remember { mutableStateOf(false) }
    val n = q.data?.size ?: 0
    if (n == 0) return
    HqButton("مُهر گروهی ($n)", { open = true }, variant = BtnVariant.SILVER, size = BtnSize.SM, icon = DivanIcon.SEAL, label = "مُهر گروهی $n کارت")
    if (open) HqSheet({ open = false }, "مُهر گروهی", sub = "کارت‌های کم‌ریسک و برگشت‌پذیر A1؛ یک اثر انگشت برای دقیقاً همین مجموعه.") { BatchSealContent { open = false } }
}

/** A check box drawn in the Divan style (gold when on). */
@Composable
private fun Check(on: Boolean) {
    val c = Divan.colors
    Box(
        Modifier.size(20.dp).clip(RoundedCornerShape(5.dp)).background(if (on) c.goldInk else Color.Transparent).border(1.5.dp, if (on) c.goldInk else c.lineStrong, RoundedCornerShape(5.dp)),
        contentAlignment = Alignment.Center,
    ) {
        if (on) Canvas(Modifier.size(12.dp)) {
            val p = Path().apply { moveTo(size.width * 0.12f, size.height * 0.55f); lineTo(size.width * 0.42f, size.height * 0.82f); lineTo(size.width * 0.9f, size.height * 0.2f) }
            drawPath(p, c.onGold, style = Stroke(2.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
        }
    }
}

/** The batch: every eligible card, chosen by default; one passkey bound to the exact set; all or nothing. */
@Composable
fun BatchSealContent(onDone: () -> Unit = {}) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val action = rememberAction()
    val q = rememberQuery("decisions:batchable", "decisions") { batchable() }
    val auth = rememberQuery("authority", "authority") { authority() }
    val off = remember { mutableStateListOf<String>() }
    var reasons by remember { mutableStateOf<List<Pair<String, String>>>(emptyList()) }
    // One key per set: pressing again for the same cards is a retry; a different set is a new action.
    var keyFor by remember { mutableStateOf<Pair<String, String>?>(null) }
    val list = q.data.orEmpty()
    val chosen = list.filter { it.ref !in off }
    val maxItems = limitNumber(auth.data?.firstOrNull { it.key == "batch.max_items" }?.limit)?.second?.toInt() ?: 20
    val maxUsd = limitNumber(auth.data?.firstOrNull { it.key == "batch.max_usd" }?.limit)?.second ?: 2.0
    val total = chosen.sumOf { it.quotaEstimate.usd?.toDoubleOrNull() ?: 0.0 }
    val holding = rememberCompanies().firstOrNull { it.kind == "holding" }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(buildAnnotatedString {
            append("فقط پیشنهاد، مصوبه‌ی جلسه و ورودی دانشنامه؛ هر کدام حداکثر "); fig(usd(maxUsd)); append(" و حداکثر "); fig("$maxItems")
            append(" کارت در یک مُهر (ماتریس اختیار). هر کارت مصوبه، ردیف Audit و ثبت تعامل خودش را دارد.")
        }, Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), style = Divan.type.caption.copy(lineHeight = 22.sp), color = c.textSecondary)
        when {
            q.data == null -> Skeleton(Modifier.fillMaxWidth().height(160.dp))
            list.isEmpty() -> Empty("کارت شایسته‌ای نیست", icon = DivanIcon.SEAL)
            else -> for (x in list) {
                val bad = reasons.firstOrNull { it.first == x.ref }
                val on = x.ref !in off
                val k = decisionKind(x.kind)
                Row(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp))
                        .background(if (bad != null) c.softNegative else if (on) c.softGold else Color.Transparent)
                        .border(1.dp, if (bad != null) c.negative.copy(alpha = 0.45f) else if (on) c.goldInk else c.lineDivider, RoundedCornerShape(12.dp))
                        .toggleable(on, role = Role.Checkbox) { v -> if (v) off.remove(x.ref) else off.add(x.ref) }.padding(12.dp),
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    Box(Modifier.padding(top = 2.dp)) { Check(on) }
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(prose(x.title), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            CompanyMark(x.company, height = 12.dp, mono = true, ink = c.textMuted)
                            Text("${k.fa}، ${x.proposer.displayFa ?: x.proposer.code}", style = Divan.type.micro, color = c.textMuted)
                            Fig(x.ref, style = Divan.type.figureSmall, color = c.textMuted)
                        }
                        if (bad != null) Text(BATCH_REASON_FA[bad.second] ?: bad.second, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.negative)
                    }
                    Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Fig(usd(x.quotaEstimate.usd), style = Divan.type.figure, color = c.textPrimary)
                        Fig("${tokens(x.quotaEstimate.tokens)} tok", style = Divan.type.figureSmall, color = c.textMuted)
                    }
                }
            }
        }
        Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (chosen.isNotEmpty() && chosen.size <= maxItems) SealButton(holding?.code ?: "HQ", holding?.nameFa ?: "هلدینگ", holding?.nameEn ?: "Holding", holding = true, busy = action.busy) {
                val set = chosen.map { "${it.ref}@${it.version}" }.sorted().joinToString(",")
                val key = keyFor?.takeIf { it.first == set }?.second ?: UUID.randomUUID().toString()
                keyFor = set to key
                reasons = emptyList()
                action.run(onError = { e -> reasons = e.batchReasons; toasts.error(govError(e)) }) {
                    val out = env.api.batchApprove(chosen.map { BatchItem(it.ref, it.version) }, key) { a, t -> env.auth.stepUp(act, a, t) }
                    env.cache.invalidate("decisions", "inbox", "away", "resolutions", "meetings", "knowledge", "outcomes")
                    toasts.ok("${out.items.size} کارت با یک مُهر تأیید شد (${out.batch})؛ هر کدام مصوبه‌ی خودش را دارد.")
                    onDone()
                }
            }
            Text(
                if (chosen.isEmpty()) buildAnnotatedString { append("کارتی انتخاب نشده.") }
                else buildAnnotatedString { append("مُهر "); fig("${chosen.size}"); append(" کارت، روی هم "); fig(usd(total)); append(". اگر یکی عوض شده باشد هیچ‌کدام مُهر نمیشود.") },
                style = Divan.type.caption, color = c.textMuted, textAlign = TextAlign.Center,
            )
        }
    }
}

// ------------------------------------------------------- payloads of the §20 kinds --
private fun JsonObject.s(k: String): String? = (this[k] as? JsonPrimitive)?.contentOrNull
private fun obj(e: JsonElement?): JsonObject = e as? JsonObject ?: JsonObject(emptyMap())
private fun arr(e: JsonElement?): List<JsonElement> = (e as? JsonArray).orEmpty()
private fun <T> decodeOr(e: JsonElement?, s: kotlinx.serialization.KSerializer<T>): T? = e?.let { runCatching { Api.json.decodeFromJsonElement(s, it) }.getOrNull() }

/** A compact form of a limit or a value for a one-line change: `count_day:5`, `days:TH,FR`. */
private fun compact(e: JsonElement?): String = when (e) {
    null, is JsonNull -> "—"
    is JsonPrimitive -> e.content
    is JsonObject -> e.entries.joinToString(", ") { (k, v) -> "$k:${if (v is JsonArray) v.joinToString(",") { (it as? JsonPrimitive)?.content.orEmpty() } else compact(v)}" }
    is JsonArray -> e.joinToString(",") { compact(it) }
}

@Composable
private fun VotesRow(v: Votes) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        for ((k, n) in listOf("support" to v.support, "oppose" to v.oppose, "abstain" to v.abstain)) {
            val l = VOTE_FA.getValue(k)
            Pill("${l.fa} $n", l.tone, dot = true)
        }
    }
}

/** The payload of a governance card (§20.11), read tolerantly: every field the card carries, nothing assumed beyond it. */
@Composable
fun GovernancePayload(d: Decision) {
    val c = Divan.colors
    val p = d.payload
    when (d.kind) {
        "meeting_resolution" -> Block("مصوبه‌ی جلسه") {
            p.s("meeting")?.let { RefChip(it, "جلسه") }
            p.s("text_md")?.let { Md(it, Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), style = Divan.type.body, color = c.textPrimary) }
            decodeOr(p["votes"], Votes.serializer())?.let { VotesRow(it) }
            val claims = decodeOr(p["claims"], ListSerializer(Claim.serializer())).orEmpty()
            for (x in claims) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                DIcon(DivanIcon.SEAL, size = 14.dp, tint = c.textSecondary)
                Text(prose(x.textFa), style = Divan.type.small, color = c.textSecondary, modifier = Modifier.weight(1f, fill = false))
                x.source?.let { RefChip(it.ref) }
            }
            Text("فقط ادعاهای منبع‌دار همراه این کارت‌اند. رأی مدیرها جای مُهر تو را نمیگیرد؛ با مُهر، مصوبه و کار پیگیری ساخته میشود.", style = Divan.type.caption, color = c.textMuted)
        }
        "charter_amendment" -> Block("اصلاحیه‌ی اساسنامه") {
            FactRows(listOf(
                { m -> Fact("دامنه", p.s("scope") ?: "—", m, figure = true) },
                { m -> Fact("بر پایه‌ی نسخه", p.s("base_version") ?: "—", m, figure = true) },
            ))
            val diff = p.s("diff_md")
            if (!diff.isNullOrBlank()) DiffView(diff, Modifier.heightIn(max = 320.dp).verticalScroll(rememberScrollState()))
            else p.s("body_md")?.let { Md(it, Modifier.fillMaxWidth().heightIn(max = 320.dp).clip(RoundedCornerShape(12.dp)).background(c.tile).verticalScroll(rememberScrollState()).padding(12.dp)) }
            for (r in decodeOr(p["red_lines"], ListSerializer(RedLine.serializer())).orEmpty()) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                DIcon(DivanIcon.LOCK, Modifier.padding(top = 3.dp), size = 14.dp, tint = c.negative)
                Text(r.textFa, style = Divan.type.small, color = c.textPrimary, modifier = Modifier.weight(1f))
                Fig(r.check, style = Divan.type.figureSmall, color = c.textMuted)
            }
            val sha = p.s("body_sha256").orEmpty()
            Text(buildAnnotatedString {
                if (sha.isNotBlank()) { append("مُهر به همین متن و همین خطوط قرمز بسته است ("); fig("sha256 ${sha.take(12)}…"); append("). ") }
                append("اگر نسخه‌ی پایه دیگر جاری نباشد، این کارت کنار میرود و کارت تازه میاید.")
            }, style = Divan.type.caption, color = c.textMuted)
        }
        "okr" -> Block("OKR") {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                p.s("objective")?.takeIf { p["objective"] is JsonPrimitive }?.let { RefChip(it) }
                p.s("quarter")?.let { Fig(it, style = Divan.type.figureSmall, color = c.textSecondary) }
            }
            ObjectiveKrs(p["objective"])
            Text("فقط مُهر تو OKR را فعال میکند؛ بی‌مُهر، فصل بی‌OKR میماند.", style = Divan.type.caption, color = c.textMuted)
        }
        "knowledge_entry" -> Block("ورودی دانشنامه‌ی هلدینگ") {
            val e = obj(p["entry"] ?: p)
            FactRows(listOf(
                { m -> Fact("لایه", LAYER_FA[e.s("layer")]?.fa ?: e.s("layer") ?: "—", m) },
                { m -> Fact("نوع", KNOWLEDGE_KIND[e.s("kind")] ?: e.s("kind") ?: "—", m) },
                { m -> Fact("معتبر تا", e.s("valid_until")?.let { jDate(dayEnd(it), withYear = true) } ?: "—", m) },
            ))
            e.s("body_md")?.let { Md(it, Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp)) }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                for (s in arr(e["sources"]).map(::obj)) RefChip(s.s("ref").orEmpty(), s.s("note")?.ifBlank { null }, RefTone.NEUTRAL)
            }
        }
        "risk_acceptance" -> Block("پذیرش ریسک") {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Column(Modifier.weight(1f).clip(RoundedCornerShape(12.dp)).background(c.tile).padding(horizontal = 12.dp, vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("ریسک", style = Divan.type.micro, color = c.textMuted)
                    p.s("risk")?.let { RefChip(it) } ?: Text("—", style = Divan.type.small)
                }
                Fact("تا", p.s("until")?.let { jDate(it, withYear = true) } ?: "—", Modifier.weight(1f))
                p.s("score")?.let { Fact("امتیاز", it, Modifier.weight(1f), figure = true) }
            }
            Text("پذیرش حداکثر ۹۰ روز است؛ بعد از آن ریسک دوباره راه کاهش یا مُهر تازه میخواهد.", style = Divan.type.caption, color = c.textMuted)
        }
        "authority_change" -> Block("تغییر ماتریس اختیار") {
            for (r in arr(p["changes"] ?: p["rules"]).map(::obj)) FlowRow(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(horizontal = 12.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(2.dp),
            ) {
                Fig(r.s("key").orEmpty(), style = Divan.type.figureSmall, color = c.textPrimary)
                if (r.containsKey("from")) Fig(compact(r["from"]), style = Divan.type.figureSmall.copy(textDecoration = TextDecoration.LineThrough), color = c.textMuted)
                Fig(compact(r["to"] ?: r["limit"]), style = Divan.type.figureSmall, color = c.textPrimary)
            }
            Text("ثابت‌های قفل با هیچ کارتی عوض نمیشوند.", style = Divan.type.caption, color = c.textMuted)
        }
    }
}

@Composable
private fun ObjectiveKrs(value: JsonElement?) {
    val c = Divan.colors
    val ref = (value as? JsonPrimitive)?.contentOrNull
    val q = ref?.let { r -> rememberQuery("okr:one:$r", "okr") { objective(r) } }
    val krs: List<JsonObject> = if (ref != null) q?.data?.keyResults.orEmpty().map { k ->
        JsonObject(mapOf("ref" to JsonPrimitive(k.ref), "title_fa" to JsonPrimitive(k.titleFa), "start" to JsonPrimitive(k.start), "target" to JsonPrimitive(k.target), "weight" to JsonPrimitive(k.weight)))
    } else arr(obj(value)["key_results"]).map(::obj)
    if (ref != null && q?.data == null) { Skeleton(Modifier.fillMaxWidth().height(80.dp)); return }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        for (k in krs) Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Fig(k.s("ref").orEmpty(), style = Divan.type.figureSmall, color = c.textMuted)
            Text(prose(k.s("title_fa").orEmpty()), style = Divan.type.small, color = c.textPrimary, modifier = Modifier.weight(1f))
            Fig("${num(k.s("start"))} → ${num(k.s("target"))}", style = Divan.type.figureSmall, color = c.textSecondary)
            Fig("w ${num(k.s("weight"))}", style = Divan.type.figureSmall, color = c.textMuted)
        }
    }
}

private fun num(s: String?): String = s?.toDoubleOrNull()?.let { figNum(it) } ?: s ?: "—"

// ------------------------------------------------------------ expected outcome (§20.6) --
private fun unitOf(metric: String) = if (Regex("٪|%").containsMatchIn(metric)) "%" else ""

/** What a proposal promises (measured at 30/60/90 days); a card without it says so. */
@Composable
fun ExpectedBlock(d: Decision) {
    val c = Divan.colors
    val e = d.expected
    val missing = "expected_missing" in d.warnings
    if (e == null && !missing) return
    Block("قول قابل سنجش") {
        if (missing) Notice(DivanIcon.URGENT, c.softWarning, c.warning) {
            Text("این پیشنهاد نتیجه‌ی مورد انتظار ندارد؛ بی‌آن در ۳۰، ۶۰ و ۹۰ روز سنجیده نمیشود. از پیشنهاددهنده بخواه آن را اضافه کند.", style = Divan.type.small, color = c.textPrimary)
        }
        if (e != null) {
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("سنجه", style = Divan.type.micro, color = c.textMuted)
                Text(prose(e.metricFa), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                if (e.kpi != null) Fig("KPI ${e.kpi}", style = Divan.type.figureSmall, color = c.textSecondary)
                else Text("بی‌KPI: پیشنهاددهنده یادداشت میدهد و ناظر حکم میکند", style = Divan.type.micro, color = c.textSecondary)
            }
            val u = unitOf(e.metricFa)
            FactRows(listOf(
                { m -> Fact("از → به", "${kpiFig(e.baseline, u)} → ${kpiFig(e.target, u)}", m, figure = true) },
                { m -> Fact("تا", "${e.byDays} روز", m) },
            ))
        }
    }
}

/** The 30/60/90-day reviews of a sealed decision. */
@Composable
fun DecisionOutcomes(d: Decision) {
    if (d.status != "approved" || d.expected == null) return
    val c = Divan.colors
    val q = rememberQuery("outcomes:decision:${d.ref}", "outcomes") { outcomes(decision = d.ref).items }
    Block("بازبینی نتیجه") {
        val rows = q.data?.sortedBy { it.day }
        when {
            rows == null -> Skeleton(Modifier.fillMaxWidth().height(64.dp))
            rows.isEmpty() -> Text("بازبینی‌ها با مُهر ساخته میشوند؛ هنوز ردیفی نیامده.", style = Divan.type.small, color = c.textMuted)
            else -> Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                for (r in rows) Column(Modifier.weight(1f).clip(RoundedCornerShape(12.dp)).background(c.tile).padding(10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text("روز ${r.day}", style = Divan.type.micro, color = c.textMuted)
                        Fig(r.ref, style = Divan.type.figureSmall, color = c.textMuted)
                    }
                    LabelPill(VERDICT[r.verdict], r.verdict)
                    Text(
                        r.measured?.let { m -> buildAnnotatedString { append("اندازه "); fig(kpiFig(m.value, unitOf(r.expected.metricFa)), c.textPrimary) } } ?: buildAnnotatedString { append("موعد ${jDate(r.dueAt)}") },
                        style = Divan.type.caption, color = c.textSecondary,
                    )
                }
            }
        }
    }
}
