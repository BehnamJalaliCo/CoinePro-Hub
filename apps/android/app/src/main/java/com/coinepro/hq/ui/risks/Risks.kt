package com.coinepro.hq.ui.risks

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.wrapContentSize
import androidx.compose.foundation.shape.RoundedCornerShape
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
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.actorFa
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.net.Risk
import com.coinepro.hq.core.net.RiskIn
import com.coinepro.hq.core.net.reviewDays
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.toneColors
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v16.ChipRow
import com.coinepro.hq.ui.v16.Labelled
import com.coinepro.hq.ui.v16.Notice
import com.coinepro.hq.ui.v16.prose
import com.coinepro.hq.ui.v17.ActorAvatar
import com.coinepro.hq.ui.v17.CoMark
import com.coinepro.hq.ui.v17.FilterRow
import com.coinepro.hq.ui.v17.Heading
import com.coinepro.hq.ui.v17.RISK_CATEGORY
import com.coinepro.hq.ui.v17.RISK_STATUS
import com.coinepro.hq.ui.v17.RefChip
import com.coinepro.hq.ui.v17.RefTone
import com.coinepro.hq.ui.v17.ScopeChips
import com.coinepro.hq.ui.v17.daysFrom
import com.coinepro.hq.ui.v17.gov
import com.coinepro.hq.ui.v17.scoreTone
import java.time.LocalDate
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

private val LEVEL = listOf("خیلی کم", "کم", "متوسط", "زیاد", "خیلی زیاد")

/** دفتر ریسک (contract §20.8). [hi] rings one risk (a link from elsewhere). */
@Composable
fun RisksScreen(hi: String? = null) {
    val c = Divan.colors
    var company by rememberSaveable { mutableStateOf<String?>(null) }
    var status by rememberSaveable { mutableStateOf<String?>(null) }
    var category by rememberSaveable { mutableStateOf<String?>(null) }
    var cell by rememberSaveable { mutableStateOf<Pair<Int, Int>?>(null) }
    var edit by remember { mutableStateOf<Risk?>(null) }
    var create by remember { mutableStateOf(false) }
    val q = rememberQuery("risks:list:${company.orEmpty()}:${status.orEmpty()}:${category.orEmpty()}", "risks") { risks(company, status, category).items }
    val matrix = rememberQuery("risks:matrix:${company.orEmpty()}", "risks") { riskMatrix(company) }
    val r = refresher(q, matrix)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            PageHeader("دفتر ریسک", eyebrow = "نگه‌دار دفتر: بازرس کل (QC)") {
                HqButton("ریسک تازه", { create = true }, variant = BtnVariant.PRIMARY, icon = DivanIcon.ADD)
            }
        }
        item { Text("یافته‌ی بحرانی و هر کالبدشکافی خودشان پیش‌نویس ریسک میسازند. بازبینی دیرکرده اول کار پاسخ‌گو میشود و بعد یافته‌ی ناظر.", style = Divan.type.small, color = c.textSecondary) }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                ScopeChips(company, { company = it })
                FilterRow("همه‌ی وضعیت‌ها", status, RISK_STATUS.mapValues { it.value.fa }) { status = it }
                FilterRow("همه‌ی دسته‌ها", category, RISK_CATEGORY) { category = it }
            }
        }
        item(key = "matrix") { Matrix(matrix.data?.let { m -> { l: Int, i: Int -> m.at(l, i) } }, cell) { cell = it } }
        val all = q.data
        val list = all.orEmpty().filter { x -> cell == null || (x.likelihood == cell!!.first && x.impact == cell!!.second) }
        when {
            all == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            all == null -> item { Skeleton(Modifier.fillMaxWidth().height(240.dp), radius = 16.dp) }
            list.isEmpty() -> item { Empty("ریسکی پیدا نشد", icon = DivanIcon.URGENT) }
            else -> for (x in list) item(key = x.ref) { RiskCard(x, hi == x.ref) { edit = x } }
        }
    }
    if (create || edit != null) RiskSheet(edit) { create = false; edit = null }
}

/** The score tile: the score, and likelihood × impact under it. */
@Composable
private fun ScoreBadge(r: Risk) {
    val (bg, fg) = toneColors(scoreTone(r.score))
    Column(Modifier.size(48.dp).clip(RoundedCornerShape(12.dp)).background(bg).semantics { contentDescription = "امتیاز ${r.score}" }, horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
        Fig("${r.score}", style = Divan.type.figure.copy(fontSize = 18.sp, lineHeight = 22.sp, fontWeight = FontWeight.Bold), color = fg)
        Fig("${r.likelihood}×${r.impact}", style = Divan.type.figureSmall.copy(fontSize = 10.sp, lineHeight = 12.sp), color = fg.copy(alpha = 0.8f))
    }
}

/** The 5 × 5 counts: likelihood up the side, impact along the bottom (left to right, like every data chart). */
@Composable
private fun Matrix(count: ((Int, Int) -> Int)?, cell: Pair<Int, Int>?, onCell: (Pair<Int, Int>?) -> Unit) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("ماتریس ریسک", note = "ریسک‌های باز، در حال کاهش و پذیرفته") {
            if (cell != null) HqButton("همه", { onCell(null) }, variant = BtnVariant.GHOST, size = BtnSize.SM)
        }
        Spacer(Modifier.height(12.dp))
        if (count == null) Skeleton(Modifier.fillMaxWidth().height(260.dp))
        else BoxWithConstraints(Modifier.fillMaxWidth()) {
            val label = 18.dp
            val gap = 6.dp
            val side = (maxWidth - label - gap * 5) / 5
            Row(horizontalArrangement = Arrangement.spacedBy(gap)) {
                Box(Modifier.width(label).height(side * 5 + gap * 4), contentAlignment = Alignment.Center) {
                    Text("احتمال", Modifier.wrapContentSize(unbounded = true).rotate(-90f), style = Divan.type.micro, color = c.textMuted)
                }
                Column(verticalArrangement = Arrangement.spacedBy(gap)) {
                    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                        Column(verticalArrangement = Arrangement.spacedBy(gap)) {
                            for (l in 5 downTo 1) Row(horizontalArrangement = Arrangement.spacedBy(gap)) {
                                for (i in 1..5) {
                                    val n = count(l, i)
                                    val on = cell?.first == l && cell.second == i
                                    val (bg, fg) = toneColors(scoreTone(l * i))
                                    Box(
                                        Modifier.size(side).clip(RoundedCornerShape(8.dp))
                                            .background(if (n > 0) bg else Color.Transparent)
                                            .border(if (on) 2.dp else 1.dp, if (on) c.goldInk else if (n > 0) Color.Transparent else c.lineDivider, RoundedCornerShape(8.dp))
                                            .clickable(role = Role.Button) { onCell(if (on) null else l to i) }
                                            .semantics { contentDescription = "احتمال $l، اثر $i: $n ریسک"; selected = on },
                                        contentAlignment = Alignment.Center,
                                    ) { if (n > 0) Fig("$n", style = Divan.type.figure.copy(fontSize = 15.sp), color = if (l * i < 8) c.textSecondary else fg) }
                                }
                            }
                            Row(horizontalArrangement = Arrangement.spacedBy(gap)) {
                                for (i in 1..5) Box(Modifier.width(side), contentAlignment = Alignment.Center) { Fig("$i", style = Divan.type.figureSmall, color = c.textMuted) }
                            }
                        }
                    }
                    Text("اثر", Modifier.width(side * 5 + gap * 4), style = Divan.type.micro, color = c.textMuted, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
                }
            }
        }
        Spacer(Modifier.height(10.dp))
        Text("امتیاز = احتمال × اثر. از ۱۵ به بالا بازبینی هر ۱۴ روز و راه کاهش یا پذیرش تو لازم است؛ از ۸ به بالا هر ۳۰ روز؛ بقیه ۹۰ روز.", style = Divan.type.micro, color = c.textMuted)
    }
}

@Composable
private fun RiskCard(r: Risk, hi: Boolean, onEdit: () -> Unit) {
    val c = Divan.colors
    val review = daysFrom(r.reviewAt)
    val bare = r.score >= 15 && r.mitigationMd == null && r.accepted == null && r.status != "closed"
    var history by rememberSaveable(r.ref) { mutableStateOf(false) }
    Column(
        Modifier.fillMaxWidth().alpha(if (r.status == "closed") 0.7f else 1f).clip(RoundedCornerShape(16.dp)).background(c.card)
            .then(if (hi) Modifier.border(2.dp, c.goldInk, RoundedCornerShape(16.dp)) else Modifier).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            ScoreBadge(r)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    CoMark(r.company, ink = c.textMuted)
                    Text(RISK_CATEGORY[r.category] ?: r.category, style = Divan.type.micro, color = c.textMuted)
                    Fig(r.ref, style = Divan.type.figureSmall, color = c.textMuted)
                    Spacer(Modifier.weight(1f))
                    LabelPill(RISK_STATUS[r.status], r.status)
                }
                Text(prose(r.titleFa), style = Divan.type.bodyStrong, color = c.textPrimary)
                Md(r.bodyMd)
            }
        }
        if (bare) Notice(DivanIcon.URGENT, c.softNegative, c.negative) {
            Text("امتیاز بالای ۱۵ بی‌راه کاهش و بی‌پذیرش: یا راه کاهش، یا کارت «پذیرش ریسک» (با اثر انگشت، حداکثر ۹۰ روز).", style = Divan.type.caption, color = c.textPrimary)
        }
        r.mitigationMd?.let { m ->
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(10.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Heading("راه کاهش")
                Md(m)
            }
        }
        r.accepted?.let { a ->
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("پذیرفته تا ${jDate(a.until, withYear = true)}", style = Divan.type.caption, color = c.textSecondary)
                RefChip(a.decision)
            }
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                ActorAvatar(r.owner, 20.dp)
                Text(actorFa(r.owner), style = Divan.type.micro, color = c.textMuted)
            }
            if (r.status != "closed" && review != null) Text(
                if (review < 0) "بازبینی ${-review} روز گذشته" else "بازبینی ${jDate(r.reviewAt)}",
                style = Divan.type.micro.copy(fontWeight = if (review < 0) FontWeight.SemiBold else FontWeight.Normal), color = if (review < 0) c.negative else c.textMuted,
            )
            for (x in r.links.refs) RefChip(x, tone = RefTone.NEUTRAL)
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (r.history.size > 1) Text(
                "تاریخچه (${r.history.size})", style = Divan.type.caption, color = c.textSecondary,
                modifier = Modifier.clip(RoundedCornerShape(6.dp)).clickable(role = Role.Button) { history = !history }.padding(vertical = 2.dp),
            )
            Spacer(Modifier.weight(1f))
            if (r.status != "closed") HqButton("ویرایش", onEdit, variant = BtnVariant.GHOST, size = BtnSize.SM, icon = DivanIcon.EDIT)
        }
        if (history) Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            for (h in r.history) FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(jDate(h.at), style = Divan.type.micro, color = c.textMuted)
                Text(actorFa(h.by), style = Divan.type.micro, color = c.textSecondary)
                Text(prose(h.change), style = Divan.type.micro, color = c.textPrimary)
                if (h.note.isNotBlank()) Text(h.note, style = Divan.type.micro, color = c.textMuted)
            }
        }
    }
}

/** A new risk or an edit (If-Match): closing it is the inspector's, accepting it a card. */
@Composable
private fun RiskSheet(r: Risk?, onClose: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    var company by rememberSaveable { mutableStateOf(r?.company) }
    var title by rememberSaveable { mutableStateOf(r?.titleFa.orEmpty()) }
    var body by rememberSaveable { mutableStateOf(r?.bodyMd.orEmpty()) }
    var category by rememberSaveable { mutableStateOf(r?.category ?: "ops") }
    var l by rememberSaveable { mutableStateOf(r?.likelihood ?: 3) }
    var i by rememberSaveable { mutableStateOf(r?.impact ?: 3) }
    var status by rememberSaveable { mutableStateOf(r?.status ?: "open") }
    var mit by rememberSaveable { mutableStateOf(r?.mitigationMd.orEmpty()) }
    var review by rememberSaveable { mutableStateOf(r?.reviewAt?.take(10).orEmpty()) }
    val score = l * i
    val max = HqClock.today().plusDays(reviewDays(score).toLong())
    val reviewDate = runCatching { LocalDate.parse(review.trim()) }.getOrNull()
    val reviewBad = review.isNotBlank() && (reviewDate == null || reviewDate > max)
    val valid = company != null && title.trim().length > 3 && !reviewBad
    val (bg, fg) = toneColors(scoreTone(score))
    HqSheet(onClose, if (r != null) "ویرایش ${r.ref}" else "ریسک تازه", sub = "بستن ریسک فقط با تأیید بازرس کل است.") {
        if (r == null) Labelled("شرکت") { ScopeChips(company, { company = it }, all = false) }
        Labelled("عنوان") { HqTextField(title, { title = it }, "عنوان", Modifier.fillMaxWidth(), maxLength = 200) }
        Labelled("شرح") { HqTextField(body, { body = it }, "شرح", Modifier.fillMaxWidth(), singleLine = false, minLines = 3) }
        Labelled("دسته") { ChipRow { for ((k, fa) in RISK_CATEGORY) FilterChip(fa, category == k, { category = k }) } }
        Labelled("احتمال") { ChipRow { for (n in 1..5) FilterChip("$n · ${LEVEL[n - 1]}", l == n, { l = n }) } }
        Labelled("اثر") { ChipRow { for (n in 1..5) FilterChip("$n · ${LEVEL[n - 1]}", i == n, { i = n }) } }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("امتیاز", style = Divan.type.small, color = c.textSecondary)
            Fig("$score", Modifier.clip(RoundedCornerShape(8.dp)).background(bg).padding(horizontal = 8.dp, vertical = 2.dp), style = Divan.type.figure.copy(fontWeight = FontWeight.Bold), color = fg)
            Text("· بازبینی حداکثر هر ${reviewDays(score)} روز", style = Divan.type.small, color = c.textSecondary)
        }
        if (r != null) Labelled("وضعیت") {
            ChipRow { for (s in listOf("open", "mitigating")) FilterChip(RISK_STATUS.getValue(s).fa, status == s, { status = s }) }
            Text("پذیرش با کارت «پذیرش ریسک» در کارتابل است و بستن با بازرس کل.", style = Divan.type.micro, color = c.textMuted)
        }
        Labelled("راه کاهش") { HqTextField(mit, { mit = it }, "راه کاهش", Modifier.fillMaxWidth(), singleLine = false, minLines = 3) }
        Labelled("بازبینی بعدی") {
            CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                HqTextField(review, { review = it }, max.toString(), Modifier.fillMaxWidth(), maxLength = 10, figure = true)
            }
            if (reviewBad) Text(buildAnnotatedString { append("برای امتیاز $score حداکثر ${reviewDays(score)} روز بعد ("); fig(max.toString()); append(").") }, style = Divan.type.micro, color = c.negative)
        }
        HqButton("ذخیره", {
            val co = company ?: return@HqButton
            val reviewAt = reviewDate?.let { "${it}T08:30:00Z" }
            action.gov(toasts) {
                val out = if (r != null) env.api.patchRisk(r, buildJsonObject {
                    put("likelihood", l); put("impact", i); put("status", status)
                    put("mitigation_md", mit.trim().ifEmpty { null }?.let(::JsonPrimitive) ?: JsonNull)
                    if (reviewAt != null) put("review_at", reviewAt)
                    put("title_fa", title.trim()); put("body_md", body.trim()); put("category", category)
                }) else env.api.createRisk(RiskIn(co, title.trim(), body.trim(), category, l, i, mitigationMd = mit.trim().ifEmpty { null }, reviewAt = reviewAt))
                env.cache.invalidate("risks")
                toasts.ok("ریسک ${out.ref} " + if (r != null) "به‌روز شد." else "ثبت شد؛ نگه‌دارش بازرس کل است.")
                onClose()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, enabled = valid, loading = action.busy)
    }
}
