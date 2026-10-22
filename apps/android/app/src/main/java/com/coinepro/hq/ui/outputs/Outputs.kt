package com.coinepro.hq.ui.outputs

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.agentKindOf
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.format.tokens
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.core.net.Deliverable
import com.coinepro.hq.designsystem.Avatar
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
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
import com.coinepro.hq.designsystem.RichText
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.RatingRow
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Loadable
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.refresher
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/** Outputs: every deliverable, unrated ones first. The owner's rating is 40% of the employee's score. */
@Composable
fun OutputsScreen() {
    val nav = LocalNav.current
    val companies = rememberCompanies()
    var unrated by rememberSaveable { mutableStateOf(false) }
    val q = rememberQuery("deliverables:${if (unrated) "unrated" else "all"}", "deliverables") { deliverables(unrated = if (unrated) true else null, limit = 100) }
    val r = refresher(q)
    val c = Divan.colors
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("خروجی‌ها", eyebrow = "کار تحویل‌شده‌ی ایجنت‌ها") }
        item {
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip("همه", !unrated, { unrated = false })
                FilterChip("بی‌امتیاز", unrated, { unrated = true })
            }
        }
        val list = q.data?.items
        when {
            list == null && q.error == null -> items(3) { Skeleton(Modifier.fillMaxWidth().height(110.dp), radius = 16.dp) }
            list == null -> item { ErrorBlock(q.error, { q.refresh() }) }
            list.isEmpty() -> item { Empty(if (unrated) "همه‌ی خروجی‌ها امتیاز گرفته‌اند" else "هنوز خروجی‌ای نیست", icon = DivanIcon.DELIVERABLE) }
            else -> items(list, key = { it.ref }) { d ->
                HqCard(Modifier.fillMaxWidth(), onClick = { nav.go("outputs/${d.ref}") }) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        CompanyMark(d.company, height = 13.dp, mono = true, ink = c.textSecondary)
                        Text(companyOf(companies, d.company).nameFa, style = Divan.type.micro, color = c.textMuted)
                        Fig(d.ref, style = Divan.type.figureSmall, color = c.textMuted)
                        Box(Modifier.weight(1f))
                        if (d.rating == null) Pill("بی‌امتیاز", Tone.GOLD, dot = true)
                        else Pill("${d.rating.score} از ۱۰", Tone.SILVER)
                    }
                    Text(d.title, style = Divan.type.bodyStrong, modifier = Modifier.padding(top = 8.dp))
                    RichText(d.summary, Modifier.padding(top = 4.dp), style = Divan.type.small, color = c.textSecondary, maxLines = 3)
                    Text("${d.producer.titleFa}، ${ago(d.createdAt)}", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.padding(top = 8.dp))
                }
            }
        }
    }
}

/** One deliverable: summary, body, evidence, what produced it, and the owner's rating. */
@Composable
fun OutputScreen(ref: String) {
    val q = rememberQuery("deliverable:$ref", "deliverables") { deliverable(ref) }
    val r = refresher(q)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { Loadable(q, skeleton = { Skeleton(Modifier.fillMaxWidth().height(300.dp), radius = 16.dp) }) { d -> OutputDetail(d) { q.set(it) } } }
    }
}

@Composable
private fun OutputDetail(d: Deliverable, onChanged: (Deliverable) -> Unit) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val companies = rememberCompanies()
    val action = rememberAction()
    var score by rememberSaveable(d.ref) { mutableIntStateOf(d.rating?.score ?: 0) }
    var comment by rememberSaveable(d.ref) { mutableStateOf(d.rating?.comment.orEmpty()) }
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                CompanyMark(d.company, height = 14.dp, mono = true, ink = c.textSecondary)
                Text(companyOf(companies, d.company).nameFa, style = Divan.type.caption, color = c.textMuted)
                Fig(d.ref, style = Divan.type.figureSmall, color = c.textMuted)
            }
            Text(d.title, style = Divan.type.h2)
        }
        HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(12.dp), radius = 14.dp, onClick = { nav.go("employees/${d.producer.code}") }) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Avatar(agentKindOf(d.producer.code, d.producer.kind), dept = d.producer.department, size = 40.dp)
                Column(Modifier.weight(1f)) {
                    Text(d.producer.titleFa, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                    Text(buildAnnotatedString { fig(d.producer.code); append("، " + jDateTime(d.createdAt)) }, style = Divan.type.micro, color = c.textMuted)
                }
                d.workId?.let { w -> HqButton(null, { nav.go("work/$w") }, variant = BtnVariant.GHOST, icon = DivanIcon.TASK, label = "کار مربوط") }
            }
        }
        HqCard(Modifier.fillMaxWidth(), color = c.softGold) {
            Text("خلاصه", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
            Md(d.summary, Modifier.padding(top = 4.dp), color = c.textPrimary)
        }
        if (!d.body.isNullOrBlank()) Md(d.body)
        val model = (d.producedWith["label_fa"] as? JsonPrimitive)?.contentOrNull ?: (d.producedWith["model"] as? JsonPrimitive)?.contentOrNull
        val used = (d.usage["tokens"] as? JsonPrimitive)?.contentOrNull?.toLongOrNull()
        val cost = (d.usage["usd"] as? JsonPrimitive)?.contentOrNull
        if (model != null || used != null) {
            Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                if (model != null) Column { Text("ساخته‌شده با", style = Divan.type.micro, color = c.textMuted); Fig(model, style = Divan.type.figure) }
                if (used != null) Column { Text("مصرف", style = Divan.type.micro, color = c.textMuted); Fig("${tokens(used)} tok · ${usd(cost)}", style = Divan.type.figure) }
            }
        }
        if (d.attachments.isNotEmpty()) {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("پیوست‌ها", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
                d.attachments.forEach { f -> Fig("${f.name} · ${f.size / 1024} KB", style = Divan.type.figureSmall, color = c.textSecondary) }
            }
        }
        HorizontalDivider(color = c.lineDivider)
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(if (d.rating == null) "امتیاز تو" else "امتیاز تو (قابل تغییر)", style = Divan.type.h3)
            Text("امتیاز تو ۴۰٪ نمره‌ی کارمند است و در یادگیری او اثر دارد.", style = Divan.type.caption, color = c.textMuted)
            RatingRow(score, { score = it })
            HqTextField(comment, { comment = it }, "نکته برای کارمند (اختیاری)", Modifier.fillMaxWidth(), singleLine = false, minLines = 2)
            HqButton("ثبت امتیاز", {
                action.run {
                    val out = env.api.rate(d.ref, score, comment.ifBlank { null })
                    onChanged(out)
                    env.cache.invalidate("deliverables", "inbox", "employees")
                    toasts.ok("امتیاز $score ثبت شد.")
                }
            }, variant = BtnVariant.PRIMARY, enabled = score > 0, loading = action.busy, icon = DivanIcon.RATE)
        }
    }
}
