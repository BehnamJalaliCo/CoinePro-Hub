package com.coinepro.hq.ui.cartable

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.format.modelLabel
import com.coinepro.hq.core.format.tokens
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.Decision
import com.coinepro.hq.core.net.DecisionMemo
import com.coinepro.hq.core.net.DeployPayload
import com.coinepro.hq.core.net.DiffFile
import com.coinepro.hq.core.net.EvaluationPayload
import com.coinepro.hq.core.net.Opinion
import com.coinepro.hq.core.net.SecondReview
import com.coinepro.hq.core.net.mgmtError
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.RichText
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Loadable
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v16.Notice
import com.coinepro.hq.ui.v17.CONFLICT_RULE
import com.coinepro.hq.ui.v17.RefChip
import com.coinepro.hq.ui.v17.RefTone
import com.coinepro.hq.ui.v18.Confidence
import com.coinepro.hq.ui.v18.LEVEL3
import com.coinepro.hq.ui.v18.MEMO_STATE
import com.coinepro.hq.ui.v18.PlayerName
import com.coinepro.hq.ui.v18.REC
import com.coinepro.hq.ui.v18.RECOMMENDATION
import com.coinepro.hq.ui.v18.REMINDER
import com.coinepro.hq.ui.v18.Rec
import com.coinepro.hq.ui.v18.Section
import com.coinepro.hq.ui.v18.SubstituteNote
import com.coinepro.hq.ui.v18.ToneTag
import com.coinepro.hq.ui.v18.VERDICT3
import com.coinepro.hq.ui.v18.hoursFa
import com.coinepro.hq.ui.v18.mgmt
import kotlinx.coroutines.delay

// ⟨1.5⟩ Contract §21 in the cartable: the one definition of the deploy payload with its real diff and the substitute's second review
// (§21.6), the monthly HR round's `evaluation` payload v2 (§21.5), the advisor's memo with the second and third opinions (§21.1), how
// long a card has waited and its reminders (§21.8), and the digital CEO's sealed prediction once the owner has decided (§21.10).
// Mirrors apps/web/src/components/v18/decision.tsx.

private fun <T> decodeOr(e: kotlinx.serialization.json.JsonElement?, s: kotlinx.serialization.KSerializer<T>): T? =
    e?.let { runCatching { Api.json.decodeFromJsonElement(s, it) }.getOrNull() }

/** A labelled fact in a tile with any content (a pill, a link). */
@Composable
private fun FactBox(label: String, modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    val c = Divan.colors
    Column(modifier.clip(RoundedCornerShape(12.dp)).background(c.tile).padding(horizontal = 12.dp, vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(label, style = Divan.type.micro, color = c.textMuted, maxLines = 1)
        content()
    }
}

@Composable
private fun FactPairs(vararg facts: Pair<String, @Composable () -> Unit>) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        for (row in facts.toList().chunked(2)) Row(Modifier.height(IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            for ((l, v) in row) FactBox(l, Modifier.weight(1f).fillMaxHeight()) { v() }
            if (row.size == 1) Box(Modifier.weight(1f))
        }
    }
}

@Composable
private fun FigValue(v: String, color: Color = Divan.colors.textPrimary) = Fig(v, style = Divan.type.figure, color = color, maxLines = 2)

@Composable
private fun TextValue(v: String, color: Color = Divan.colors.textPrimary) = Text(v, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = color)

// ------------------------------------------------------------- the deploy card (§21.6) --
private data class FileStatus(val fa: String, val icon: DivanIcon)

private val FILE_STATUS = mapOf(
    "added" to FileStatus("تازه", DivanIcon.ADD), "modified" to FileStatus("عوض‌شده", DivanIcon.EDIT),
    "removed" to FileStatus("حذف‌شده", DivanIcon.REJECT), "renamed" to FileStatus("نام تازه", DivanIcon.SHARE),
)
private val UNAVAILABLE = mapOf(
    "no_access" to "هاب به این ریپو دسترسی ندارد؛ diff نیامد، ولی کارت همچنان به همان commit بسته است.",
    "too_large" to "diff از سقف (۳۰۰ فایل یا ۲۵۶ کیلوبایت) بزرگ‌تر است؛ فقط آمار آمده.",
    "fetch_failed" to "گرفتن diff شکست خورد؛ کارت همچنان به همان commit بسته است.",
)
private val SEVERITY = mapOf("low" to ("کم" to Tone.NEUTRAL), "medium" to ("متوسط" to Tone.WARN), "high" to ("زیاد" to Tone.NEG), "critical" to ("بحرانی" to Tone.NEG))

/** Code lines, left to right in Latin figures; additions and removals by sign and colour (masked lines stay masked). Scrolls both
 *  ways inside its own box, so a long patch never pushes the card away. */
@Composable
fun CodeDiff(text: String, modifier: Modifier = Modifier) {
    val c = Divan.colors
    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
        Box(modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.page).heightIn(max = 340.dp).verticalScroll(rememberScrollState())) {
            Column(Modifier.horizontalScroll(rememberScrollState()).padding(vertical = 6.dp)) {
                for (l in text.split('\n')) {
                    val head = l.startsWith("@@")
                    val add = !head && l.startsWith("+")
                    val del = !head && l.startsWith("-")
                    Row(Modifier.background(if (add) c.softPositive else if (del) c.softNegative else Color.Transparent).padding(horizontal = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Fig(if (head) "" else if (add) "+" else if (del) "−" else "", Modifier.width(10.dp), style = Divan.type.figureSmall, color = if (add) c.positive else if (del) c.negative else c.textMuted)
                        Fig(if (head) l else l.drop(1).ifEmpty { " " }, style = Divan.type.figureSmall, color = if (head) c.textMuted else c.textPrimary)
                    }
                }
            }
        }
    }
}

@Composable
private fun FileRow(ref: String, f: DiffFile, open0: Boolean) {
    val c = Divan.colors
    var open by rememberSaveable(f.path) { mutableStateOf(open0) }
    var full by rememberSaveable(f.path) { mutableStateOf(false) }
    val st = FILE_STATUS[f.status] ?: FILE_STATUS.getValue("modified")
    val tint = when (f.status) { "added" -> c.positive; "removed" -> c.negative; "renamed" -> c.lapis; else -> c.warning }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).clickable(role = Role.Button, onClickLabel = if (open) "بستن" else "باز کردن") { open = !open }.padding(horizontal = 6.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            DIcon(st.icon, size = 15.dp, tint = tint)
            Fig(f.path, Modifier.weight(1f), style = Divan.type.figureSmall, color = c.textPrimary)
            if (f.secretMasked) Pill("ماسک", Tone.WARN, icon = DivanIcon.LOCK)
            if (f.binary) Text("باینری", style = Divan.type.micro, color = c.textMuted)
            else Text(buildAnnotatedString { fig("+${f.additions}", c.positive); append(" "); fig("−${f.deletions}", c.negative) }, style = Divan.type.small)
            DIcon(DivanIcon.CHEVRON, size = 14.dp, tint = c.textMuted)
        }
        if (open) Column(Modifier.padding(start = 6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            val q = if (full) rememberQuery("diff:$ref:${f.path}", "decisions", maxAgeMs = 300_000) { diffFile(ref, f.path) } else null
            val patch = q?.data?.patch ?: f.patch
            if (f.binary || patch == null) Text("فایل باینری است؛ patch ندارد.", style = Divan.type.caption, color = c.textMuted)
            else CodeDiff(patch)
            if (f.secretMasked) Text("خطی که اسکن رمز در آن چیزی پیدا کرد ماسک شده؛ نه اینجا و نه در هیچ لاگی نمیاید.", style = Divan.type.micro, color = c.textMuted)
            if (f.truncated && !full) HqButton("patch کامل این فایل", { full = true }, size = BtnSize.SM, variant = BtnVariant.TEXT, icon = DivanIcon.DOWNLOAD)
            if (q != null && q.data == null && q.error == null) Skeleton(Modifier.fillMaxWidth().height(48.dp))
            q?.error?.let { Text(mgmtError(it), style = Divan.type.caption, color = c.negative) }
        }
    }
}

@Composable
private fun SecondReviewBlock(r: SecondReview) {
    val c = Divan.colors
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).border(1.dp, c.lineDivider, RoundedCornerShape(12.dp)).padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            Text("بازبینی دوم", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
            PlayerName(r.player, r.model, size = 13.dp)
            SubstituteNote()
        }
        for (f in r.findings) {
            val sev = SEVERITY[f.severity] ?: (f.severity to Tone.NEUTRAL)
            val (vFa, vTone) = when (f.verified) { true -> "تأیید مدیر فنی" to Tone.POS; false -> "رد مدیر فنی" to Tone.NEUTRAL; null -> "در حال سنجش" to Tone.LAPIS }
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Pill(sev.first, sev.second, dot = true)
                    Text(f.titleFa, Modifier.weight(1f), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Fig("${f.path}:${f.line}", Modifier.weight(1f), style = Divan.type.figureSmall, color = c.textMuted)
                    Pill(vFa, vTone)
                }
                Md(f.detailMd, style = Divan.type.caption)
            }
        }
        Text("هیچ یافته‌ای فقط با حرف بازیکن ذخیره وارد کارت نمیشود؛ مدیر فنی یا QC هر کدام را میسنجد و تأییدشده‌ها به یادداشت ریسک میروند. این بازبینی کارت را نه تأیید میکند نه مسدود.", style = Divan.type.micro, color = c.textMuted)
    }
}

/** The one definition of the deploy payload (§21.6): bound to `head_sha`, with the real diff when the hub can read the repository. */
@Composable
fun DeployPayloadBlock(d: Decision, open0: String? = null) {
    val c = Divan.colors
    val uri = LocalUriHandler.current
    val p = decodeOr(d.payload, DeployPayload.serializer()) ?: DeployPayload()
    Section("انتشار") {
        FactPairs(
            "ریپو" to { FigValue(p.repo.substringAfterLast('/').ifEmpty { "—" }) },
            "تغییر" to { FigValue(p.diffStat.ifEmpty { "—" }) },
            "CI" to { TextValue(if (p.ci.status == "passed") "سبز" else p.ci.status.ifEmpty { "—" }, if (p.ci.status == "passed") c.positive else c.negative) },
            "تست‌ها" to { FigValue("${p.tests.passed} ✓ · ${p.tests.failed} ✗") },
        )
        FlowRow(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            if (p.headSha.isNotBlank()) Text(buildAnnotatedString { append("commit "); fig(p.headSha.take(10), c.textPrimary) }, style = Divan.type.caption, color = c.textSecondary)
            if (p.rollout.isNotBlank()) Text(buildAnnotatedString { append("روش "); fig(p.rollout, c.textPrimary) }, style = Divan.type.caption, color = c.textSecondary)
            p.window?.let { Text("پنجره ${jDateTime(it.from)} تا ${jDateTime(it.to)}", style = Divan.type.caption, color = c.textSecondary) }
            if (p.prUrl.isNotBlank()) Row(Modifier.clip(CircleShape).clickable(role = Role.Button, onClickLabel = "باز کردن PR") { runCatching { uri.openUri(p.prUrl) } }.padding(horizontal = 4.dp, vertical = 2.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                DIcon(DivanIcon.SHARE, size = 13.dp, tint = c.goldInk)
                Fig("PR", style = Divan.type.figureSmall, color = c.goldInk)
            }
        }
        p.calendarConflicts.orEmpty().forEach { x ->
            Notice(DivanIcon.URGENT, c.softWarning, c.warning) { Text("${CONFLICT_RULE[x.rule] ?: x.rule}: ${x.noteFa}", style = Divan.type.caption, color = c.textPrimary) }
        }
        p.diffUnavailable?.let { Notice(DivanIcon.INFO, c.tile, c.textSecondary) { Text(UNAVAILABLE[it] ?: it, style = Divan.type.caption, color = c.textSecondary) } }
        p.diff?.let { diff ->
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).border(1.dp, c.lineDivider, RoundedCornerShape(12.dp)).padding(8.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Row(Modifier.padding(horizontal = 6.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("diff واقعی", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                    Text("${diff.totalFiles} فایل", style = Divan.type.caption, color = c.textSecondary)
                    Text(buildAnnotatedString { fig("+${diff.totalAdditions}", c.positive); append(" "); fig("−${diff.totalDeletions}", c.negative) }, style = Divan.type.small)
                    Box(Modifier.weight(1f))
                    Fig("${diff.baseSha.take(7)}…${diff.headSha.take(7)}", style = Divan.type.figureSmall, color = c.textMuted)
                }
                diff.files.forEach { f -> FileRow(d.ref, f, open0 == f.path) }
                Text(
                    "با دسترسی git خود هاب، ${ago(diff.fetchedAt)}. هر فایل تا ۴۰۰ خط اینجاست؛ فایل بلندتر «patch کامل» دارد. push تازه روی شاخه این کارت را کنار میگذارد." +
                        if (diff.truncated) " فهرست فایل‌ها هم بریده شده." else "",
                    Modifier.padding(horizontal = 6.dp, vertical = 4.dp), style = Divan.type.micro, color = c.textMuted,
                )
            }
        }
        p.secondReview?.let { SecondReviewBlock(it) }
    }
}

// ------------------------------------------------------------ evaluation v2 (§21.5) --
@Composable
fun EvaluationBlock(d: Decision) {
    val c = Divan.colors
    val nav = LocalNav.current
    val p = decodeOr(d.payload, EvaluationPayload.serializer()) ?: EvaluationPayload()
    val r = RECOMMENDATION[p.recommendation] ?: Rec(p.recommendation.ifEmpty { "—" }, Tone.NEUTRAL, DivanIcon.RATE)
    Section("ارزیابی ماهانه") {
        FactPairs(
            "کارمند" to { Fig(p.employee.ifEmpty { "—" }, Modifier.clickable(enabled = p.employee.isNotBlank(), role = Role.Button) { nav.go("employees/${p.employee}") }, style = Divan.type.figure, color = c.goldInk) },
            "پیشنهاد" to { Pill(r.fa, r.tone, icon = r.icon) },
            "دور ارزیابی" to { FigValue(p.round.ifEmpty { "—" }) },
        )
        p.change?.let { ch ->
            val facts = buildList<Pair<String, @Composable () -> Unit>> {
                ch.titleFa?.let { add("عنوان تازه" to { TextValue(it) }) }
                ch.model?.let { add("مدل" to { FigValue(modelLabel(it)) }) }
                ch.effort?.let { add("فکر" to { FigValue(it) }) }
                ch.quotaEstimateMonth?.let { add("برآورد ماهانه" to { FigValue("${tokens(it)} tok") }) }
            }
            if (facts.isNotEmpty()) FactPairs(*facts.toTypedArray())
        }
        p.transferTo?.let { Text(buildAnnotatedString { append("کارهای باز به "); fig(it, c.textPrimary); append(" میرسد.") }, style = Divan.type.small, color = c.textSecondary) }
        if (p.evidence.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            p.evidence.forEach { RefChip(it.ref, note = it.note.ifBlank { null }, tone = RefTone.NEUTRAL) }
        }
        if (p.unflagged) Notice(DivanIcon.URGENT, c.softWarning, c.warning) {
            Text("این کارمند پرچم قاعده‌محور ندارد؛ ارزیاب با این دلیل پیشنهاد داده: ${p.overrideReason ?: "—"}", style = Divan.type.small, color = c.textPrimary)
        }
        Text(
            when (p.recommendation) {
                "promote", "demote" -> "با مُهر، تغییر با همان بررسی‌های استخدام اعمال میشود: مدل باید در یک اتصال روشن باشد و تعهد ماهانه در پاکت شرکت جا شود، وگرنه هیچ چیز عوض نمیشود."
                "dismiss" -> "با مُهر، برکناری مثل §3.3 انجام میشود و کارهای باز منتقل میشوند."
                else -> "با مُهر، دوره‌ی آزمایشی پایان میگیرد."
            },
            style = Divan.type.caption, color = c.textMuted,
        )
    }
}

// --------------------------------------------------------- the premium advisor (§21.1) --
@Composable
private fun OpinionCard(o: Opinion, title: String) {
    val c = Divan.colors
    val rec = REC[o.recommendation] ?: REC.getValue("ask")
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).border(1.dp, c.lineDivider, RoundedCornerShape(12.dp)).padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            Text(title, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
            PlayerName(o.player, o.model, size = 13.dp)
            Pill(if (o.agrees) "هم‌نظر با مشاور" else "اختلاف با مشاور", if (o.agrees) Tone.POS else Tone.WARN, icon = if (o.agrees) DivanIcon.SEAL else DivanIcon.URGENT)
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) { Pill(rec.fa, rec.tone, dot = true); Confidence(o.confidence, silver = true) }
        RichText(o.summaryFa, style = Divan.type.small, color = c.textSecondary)
        if (o.differences.isNotEmpty()) Md(o.differences.joinToString("\n") { "- $it" }, style = Divan.type.caption)
        SubstituteNote()
    }
}

@Composable
private fun MemoView(m: DecisionMemo) {
    val c = Divan.colors
    val rec = REC[m.recommendation] ?: REC.getValue("ask")
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Fig(m.ref, style = Divan.type.figureSmall, color = c.textMuted)
            Text("${if (m.trigger == "auto") "خودکار" else "به درخواست تو"}، ${ago(m.createdAt)}", Modifier.weight(1f), style = Divan.type.micro, color = c.textMuted)
            Fig("${tokens(m.usage.tokens)} · ${usd(m.usage.usd)}", style = Divan.type.figureSmall, color = c.textMuted)
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) { Pill("توصیه: ${rec.fa}", rec.tone, dot = true); Confidence(m.confidence) }
        RichText(m.summaryFa, style = Divan.type.body, color = c.textPrimary)
        Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min).clip(RoundedCornerShape(12.dp)).background(c.softNegative)) {
            Box(Modifier.width(3.dp).fillMaxHeight().background(c.negative.copy(alpha = 0.6f)))
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(if (m.mode == "devil") "چرا نه" else "قوی‌ترین استدلال مخالف", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.negative)
                Md(m.againstMd, color = c.textPrimary)
            }
        }
        m.options.forEach { o ->
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                RichText(o.titleFa, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) { Text("+", style = Divan.type.caption, color = c.positive); RichText(o.prosMd, style = Divan.type.caption) }
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) { Text("−", style = Divan.type.caption, color = c.negative); RichText(o.consMd, style = Divan.type.caption) }
            }
        }
        m.risks.forEach { r ->
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(horizontal = 12.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                RichText(r.titleFa, style = Divan.type.small, color = c.textPrimary)
                Text("احتمال ${LEVEL3[r.likelihood] ?: r.likelihood} · اثر ${LEVEL3[r.impact] ?: r.impact}", style = Divan.type.micro, color = c.textMuted)
                RichText("کاهش: ${r.mitigationFa}", style = Divan.type.caption)
            }
        }
        if (m.questions.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("از پیشنهاددهنده بپرس", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            Md(m.questions.joinToString("\n") { "- $it" }, color = c.textPrimary)
        }
        if (m.citations.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            m.citations.forEach { RefChip(it.ref, tone = RefTone.NEUTRAL) }
        }
        if (m.secondOpinion != null || m.thirdOpinion != null) {
            m.secondOpinion?.let { OpinionCard(it, "نظر دوم") }
            m.thirdOpinion?.let { OpinionCard(it, "نظر سوم") }
        } else if (m.mode == "standard") Text("نظر دوم و سوم این یادداشت نیامد (بازیکن در دسترس نبود یا سقف روزش پر بود)؛ هیچ جابه‌جایی پنهانی نیست.", style = Divan.type.micro, color = c.textMuted)
    }
}

/** The decision memo (§21.1): standard or devil's advocate, bound to the card's version, with the substitutes' opinions beside it. */
@Composable
fun MemoBlock(d: Decision, mode0: String = "standard") {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val pending = d.status == "pending"
    if (!pending && d.memos.isEmpty()) return
    var mode by rememberSaveable(d.ref) { mutableStateOf(mode0) }
    val q = rememberQuery("memo:${d.ref}:$mode", "memos", "decisions") { memo(d.ref, mode) }
    val action = rememberAction()
    val m = q.data
    // Polls while the advisor writes.
    val writing = m?.state == "writing"
    LaunchedEffect(writing) { while (writing) { delay(2_500); q.refresh() } }
    fun ask() = action.mgmt(toasts) {
        q.set(env.api.requestMemo(d.ref, mode))
        env.cache.invalidate("memos", "decisions")
        toasts.info("مشاور شروع به نوشتن کرد.")
    }
    Section("یادداشت مشاور", action = {
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            FilterChip("استاندارد", mode == "standard", { mode = "standard" })
            FilterChip("مخالف‌خوان", mode == "devil", { mode = "devil" })
        }
    }) {
        HqCard(Modifier.fillMaxWidth(), padding = androidx.compose.foundation.layout.PaddingValues(12.dp), radius = 14.dp) {
            when {
                m == null && q.error == null && q.state.loading -> Skeleton(Modifier.fillMaxWidth().height(96.dp))
                m == null -> Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(
                        if (mode == "devil") "یادداشت مخالف‌خوان میگوید چرا نه؛ قوی‌ترین استدلال‌ها علیه همین کارت."
                        else "یادداشت رسمی: خلاصه، گزینه‌ها، قوی‌ترین استدلال مخالف، ریسک‌ها و پرسش‌ها، با نظر دوم و سوم بازیکن‌های ذخیره.",
                        style = Divan.type.small, color = c.textSecondary,
                    )
                    if (pending) HqButton("یادداشت بخواه", ::ask, variant = BtnVariant.SILVER, size = BtnSize.SM, icon = DivanIcon.ADVISOR, loading = action.busy)
                }
                else -> Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    if (m.state != "ready") Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        LabelPill(MEMO_STATE[m.state], m.state)
                        if (m.state == "stale" && pending) HqButton("یادداشت تازه", ::ask, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.REFRESH, loading = action.busy)
                    }
                    if (m.state == "writing") Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Skeleton(Modifier.fillMaxWidth(0.66f).height(14.dp))
                        Skeleton(Modifier.fillMaxWidth().height(56.dp))
                        Text("مشاور با بسته‌ی شاهد کارت مینویسد؛ هم‌زمان GPT و DeepSeek همان بسته را بی‌دیدن یادداشت میخوانند.", style = Divan.type.caption, color = c.textMuted)
                    } else MemoView(m)
                }
            }
        }
    }
}

// --------------------------------------------------------------- reminders (§21.8) --
@Composable
fun WaitingLine(d: Decision) {
    val c = Divan.colors
    val h = d.waitingH?.toInt() ?: return
    if (d.status != "pending" || h < 1) return
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            DIcon(DivanIcon.TIME, size = 14.dp, tint = c.textSecondary)
            Text("منتظر تو، ${hoursFa(h)}", style = Divan.type.caption, color = c.textSecondary)
        }
        d.reminders.forEach { r ->
            Text("یادآوری ${REMINDER[r.kind] ?: r.kind}", Modifier.clip(CircleShape).background(c.tile).padding(horizontal = 8.dp, vertical = 2.dp), style = Divan.type.micro, color = c.textMuted)
        }
    }
}

// ------------------------------------------------------------ the digital CEO (§21.10) --
@Composable
fun PredictionLine(d: Decision) {
    val c = Divan.colors
    val nav = LocalNav.current
    val p = d.digitalCeoPrediction ?: return
    val v = VERDICT3[p.verdict] ?: VERDICT3.getValue("approve")
    FlowRow(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.tile).clickable(role = Role.Button) { nav.go("digital-ceo") }.padding(12.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(32.dp).clip(CircleShape).background(c.card), contentAlignment = Alignment.Center) { DIcon(DivanIcon.HOLDING, size = 16.dp, tint = c.goldInk) }
        Text("مدیر کل دیجیتال", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
        Text("پیش از تصمیم تو پیش‌بینی کرده بود:", style = Divan.type.caption, color = c.textSecondary)
        LabelPill(v)
        Confidence(p.confidence, silver = true)
        Text(if (p.method == "model") "با مدل" else "روش پایه", style = Divan.type.micro, color = c.textMuted)
        p.correct?.let { ok -> Pill(if (ok) "درست" else "نادرست", if (ok) Tone.POS else Tone.NEG, icon = if (ok) DivanIcon.SEAL else DivanIcon.REJECT) }
    }
}

/** The §21 parts of one card on their own (the deploy or evaluation payload, the memo, the prediction): the screenshot tests show
 *  them here, below the fold of the decision page. [open0] opens one file of a deploy diff; [mode0] picks the memo. */
@Composable
fun DecisionManagementView(ref: String, open0: String? = null, mode0: String = "standard") {
    val q = rememberQuery("decision:$ref", "decisions") { decision(ref) }
    Loadable(q) { d ->
        Column(verticalArrangement = Arrangement.spacedBy(18.dp)) {
            WaitingLine(d)
            when (d.kind) {
                "deploy" -> DeployPayloadBlock(d, open0)
                "evaluation" -> EvaluationBlock(d)
            }
            MemoBlock(d, mode0)
            PredictionLine(d)
        }
    }
}
