package com.coinepro.hq.ui.ask

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.tokens
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.core.net.ASK_MAX
import com.coinepro.hq.core.net.Ask
import com.coinepro.hq.core.net.AskCitation
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v16.Chip
import com.coinepro.hq.ui.v17.CoMark
import com.coinepro.hq.ui.v17.RefChip
import com.coinepro.hq.ui.v18.CITATION
import com.coinepro.hq.ui.v18.mgmt
import com.coinepro.hq.ui.v17.Named
import java.util.UUID
import kotlinx.coroutines.delay

// «از هاب بپرس» (contract §21.2), mirroring apps/web/src/components/v18/ask.tsx: one question, a short answer with exact references
// to resolutions, decisions, deliverables, messages, docs or lines of code. Retrieval is code (full text, no embeddings); when nothing is
// found no model runs.

private val STATE_FA = mapOf(
    "queued" to "در صف…", "searching" to "جستجو در مصوبه‌ها، تصمیم‌ها، سندها و کد…", "answering" to "کتابدار هاب فقط از همین قطعه‌ها جواب مینویسد…",
    "failed" to "جواب معتبری ساخته نشد.",
)

@Composable
private fun Citation(c: AskCitation) {
    val col = Divan.colors
    val k = CITATION[c.kind] ?: Named(c.kind, DivanIcon.INFO)
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(col.tile).padding(10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                DIcon(k.icon, size = 14.dp, tint = col.textSecondary)
                Text(k.fa, style = Divan.type.micro, color = col.textSecondary)
            }
            c.ref?.let { RefChip(it) }
            c.path?.let { p ->
                val where = (c.repo?.substringAfterLast('/')?.let { "$it/" } ?: "") + p + (c.lines?.takeIf { it.size == 2 }?.let { "#L${it[0]}-${it[1]}" } ?: "") + (c.commit?.let { " @$it" } ?: "")
                Fig(where, style = Divan.type.figureSmall, color = col.textMuted, maxLines = 2)
            }
        }
        if (c.snippet.isNotBlank()) {
            if (c.kind == "code") CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                Fig(c.snippet, Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).background(col.page).padding(8.dp), style = Divan.type.figureSmall, color = col.textPrimary, maxLines = 12)
            } else Text("«${c.snippet}»", style = Divan.type.caption, color = col.textSecondary)
        }
    }
}

/** One question and its answer: its state while it runs, the cited answer, what was not indexed, the cost. */
@Composable
fun AskAnswer(a: Ask) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            Fig(a.ref, style = Divan.type.figureSmall, color = c.textMuted)
            Text(ago(a.createdAt), style = Divan.type.micro, color = c.textMuted)
            a.scope?.companies?.forEach { CoMark(it, height = 10.dp, ink = c.textMuted) }
            if (a.state == "done") Text(buildAnnotatedString {
                append(if (a.found > 0) "${a.found} قطعه، " else "چیزی پیدا نشد، ")
                fig("${tokens(a.usage.tokens)} · ${usd(a.usage.usd, 3)}")
            }, style = Divan.type.micro, color = c.textMuted)
        }
        if (a.live || a.state == "failed") Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (a.live) CircularProgressIndicator(Modifier.size(16.dp), color = c.goldInk, strokeWidth = 2.dp) else DIcon(DivanIcon.URGENT, size = 16.dp, tint = c.negative)
            Text(STATE_FA[a.state].orEmpty(), style = Divan.type.small, color = if (a.state == "failed") c.negative else c.textSecondary)
        }
        a.answerMd?.let { Md(it, style = Divan.type.body, color = c.textPrimary) }
        a.citations.forEach { Citation(it) }
        if (a.notIndexed.isNotEmpty()) Text(buildAnnotatedString {
            append("هاب این ریپوها را نمیخواند و در جستجو نبودند: "); fig(a.notIndexed.joinToString("، "))
        }, style = Divan.type.micro, color = c.textMuted)
    }
}

@Composable
private fun HistorySheet(onClose: () -> Unit) {
    val c = Divan.colors
    val q = rememberQuery("ask:list", "ask") { asks().items }
    var open by remember { mutableStateOf<String?>(null) }
    HqSheet(onClose, "پرسش‌های قبلی از هاب", sub = "جستجو کد است (متن کامل، بدون embedding)؛ چیزی پیدا نشود، هیچ مدلی اجرا نمیشود.") {
        val list = q.data
        when {
            list == null -> Skeleton(Modifier.fillMaxWidth().height(160.dp), radius = 12.dp)
            list.isEmpty() -> Empty("هنوز چیزی نپرسیده‌ای", icon = DivanIcon.SEARCH)
            else -> list.forEach { a ->
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(Modifier.fillMaxWidth().clickable(role = Role.Button) { open = if (open == a.ref) null else a.ref }, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(a.q, Modifier.weight(1f), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                        Text(if (a.found > 0) "${a.found} قطعه" else "بی‌نتیجه", style = Divan.type.micro, color = c.textMuted)
                        DIcon(DivanIcon.CHEVRON, size = 14.dp, tint = c.textMuted)
                    }
                    if (open == a.ref) Box(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.card).padding(10.dp)) { AskAnswer(a) }
                }
            }
        }
    }
}

/** «از هاب بپرس» on the command center, above the cartable. */
@Composable
fun AskBox() {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    val companies = rememberCompanies()
    var q by rememberSaveable { mutableStateOf("") }
    val scope = remember { mutableStateListOf<String>() }
    // One key per question, kept across a retry of the same press.
    var key by rememberSaveable { mutableStateOf(UUID.randomUUID().toString()) }
    var ref by rememberSaveable { mutableStateOf<String?>(null) }
    var history by remember { mutableStateOf(false) }
    val text = q.trim()
    fun submit() {
        if (text.isEmpty() || text.length > ASK_MAX) return
        action.mgmt(toasts) {
            val a = env.api.askHub(text, scope.toList(), key)
            ref = a.ref
            key = UUID.randomUUID().toString()
            env.cache.invalidate("ask")
        }
    }
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("از هاب بپرس", note = "جواب فقط از سوابق، سندها و کد، با ارجاع دقیق") {
            HqButton("قبلی‌ها", { history = true }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.TIME)
        }
        Row(
            Modifier.fillMaxWidth().padding(top = 10.dp).clip(RoundedCornerShape(14.dp)).background(c.tile).border(1.dp, c.lineStrong, RoundedCornerShape(14.dp)).padding(6.dp),
            verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            BasicTextField(
                q, { if (it.length <= ASK_MAX) q = it },
                Modifier.weight(1f).heightIn(min = 40.dp).padding(horizontal = 6.dp, vertical = 9.dp).semantics { contentDescription = "پرسش از هاب" },
                textStyle = Divan.type.body.copy(color = c.textPrimary), cursorBrush = SolidColor(c.goldInk), maxLines = 4,
                decorationBox = { inner -> Box { if (q.isEmpty()) Text("مثلاً: چرا گزارش روزانه‌ی مدیرعامل‌ها خاموش است؟", style = Divan.type.body, color = c.textMuted, maxLines = 2, overflow = TextOverflow.Ellipsis); inner() } },
            )
            Box(
                Modifier.size(40.dp).clip(CircleShape).background(if (text.isNotEmpty()) c.goldFill else c.disabledFill)
                    .clickable(enabled = text.isNotEmpty() && !action.busy, role = Role.Button, onClickLabel = "بپرس") { submit() }.semantics { contentDescription = "بپرس" },
                contentAlignment = Alignment.Center,
            ) {
                if (action.busy) CircularProgressIndicator(Modifier.size(16.dp), color = c.onGold, strokeWidth = 2.dp)
                else DIcon(DivanIcon.SEARCH, size = 18.dp, tint = if (text.isNotEmpty()) c.onGold else c.disabledText)
            }
        }
        Row(Modifier.fillMaxWidth().padding(top = 8.dp).horizontalScroll(rememberScrollState()), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("فقط در:", style = Divan.type.micro, color = c.textMuted)
            for (co in companies) Chip(co.code in scope, { if (co.code in scope) scope.remove(co.code) else scope.add(co.code) }) { ink ->
                CoMark(co.code, height = 11.dp, ink = ink)
                Text(co.nameFa ?: co.code, style = Divan.type.small, color = ink, maxLines = 1)
            }
        }
        if (q.length > ASK_MAX * 0.8) Fig("${q.length}/$ASK_MAX", Modifier.padding(top = 4.dp), style = Divan.type.figureSmall, color = c.textMuted)
        ref?.let { r -> Box(Modifier.padding(top = 12.dp)) { AskOne(r) } }
    }
    if (history) HistorySheet { history = false }
}

/** One ask, polled while it runs. */
@Composable
private fun AskOne(ref: String) {
    val q = rememberQuery("ask:$ref", "ask", maxAgeMs = 0) { asked(ref) }
    val a = q.data
    val live = a?.live == true
    LaunchedEffect(live) { while (live) { delay(1_500); q.refresh() } }
    if (a == null) Skeleton(Modifier.fillMaxWidth().height(64.dp), radius = 12.dp) else AskAnswer(a)
}
