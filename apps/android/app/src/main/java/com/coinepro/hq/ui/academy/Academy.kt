package com.coinepro.hq.ui.academy

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDirection
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.Teaching
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.RichText
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.media.Composer
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v14.Spark
import com.coinepro.hq.ui.v14.TEACH_STATUS
import com.coinepro.hq.ui.v14.Tag
import com.coinepro.hq.ui.v14.spoken

private val ROLE_FA = mapOf(
    "all" to "همه", "overseer" to "ناظر کل", "advisor" to "مشاور کل", "ceo" to "مدیرعامل‌ها", "assistant" to "دستیار", "manager" to "مدیرها", "cto" to "مدیر فنی",
)

/** آکادمی هلدینگ (contract §18.6): the knowledge layer made measurable — our own fine-tuning, kept when the model
 *  changes. Golden evals gate every new charter, skill or model version; the owner teaches by voice or text. */
@Composable
fun AcademyScreen() {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val curricula = rememberQuery("academy:curricula", "academy", maxAgeMs = 300_000) { curricula() }
    val evals = rememberQuery("academy:evals", "academy", maxAgeMs = 60_000) { evals() }
    val teachings = rememberQuery("academy:teach", "academy", maxAgeMs = 5_000) { teachings() }
    val r = refresher(curricula, evals, teachings)
    val action = rememberAction()
    var role by rememberSaveable { mutableStateOf("overseer") }
    val roleFa = ROLE_FA[role] ?: role
    val cur = curricula.data?.firstOrNull { it.role == role }
    val suites = evals.data.orEmpty().filter { it.role == role || it.role == "all" }

    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("آکادمی", eyebrow = "فاین‌تیون ما: لایه‌ی دانشی که مال ماست و با عوض شدن مدل از دست نمیرود") }
        item { Text("هر نقش برنامه‌ی آموزشی و آزمون طلایی دارد. هیچ نسخه‌ی تازه‌ای از منشور، مهارت یا مدل بدون نمره‌ی برابر یا بهتر از خط پایه فعال نمیشود.", style = Divan.type.small, color = c.textSecondary) }
        item {
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                for (k in curricula.data.orEmpty().map { it.role }) FilterChip(ROLE_FA[k] ?: k, role == k, { role = k })
            }
        }
        item {
            HqCard(Modifier.fillMaxWidth()) {
                SectionTitle("آموزش مستقیم", note = "بگو یا بنویس؛ مدیر عملیات AI دقیقش میکند، ناظر بررسی میکند، آزمون اجرا میشود، تو تأیید میکنی")
                Composer("به $roleFa یاد بده…", onSend = { body, files ->
                    val v = spoken(body, files)
                    try {
                        env.api.teach("role", role, v.text, v.source, v.fileId)
                        env.cache.invalidate("academy")
                        toasts.ok("ثبت شد؛ پیشنهاد دقیق و نمره‌ی آزمون به‌زودی میاید.")
                    } catch (e: ApiException) {
                        toasts.error(e.messageFa)
                        throw e
                    }
                }, Modifier.padding(top = 10.dp), purpose = "note", allowFiles = false, draftKey = "teach:$role")
            }
        }
        val ts = teachings.data
        if (ts == null) item { Skeleton(Modifier.fillMaxWidth().height(120.dp), radius = 14.dp) }
        else items(ts.size, key = { ts[it].ref }) { i ->
            TeachingCard(ts[i], roleOf = { ROLE_FA[it] ?: it }, busy = action.busy, onApprove = {
                action.run {
                    env.api.approveTeaching(ts[i].ref) { a, t -> env.auth.stepUp(act, a, t) }
                    env.cache.invalidate("academy")
                    toasts.ok("تأیید شد؛ نسخه‌ی تازه فعال شد.")
                }
            }, onReject = {
                action.run { env.api.rejectTeaching(ts[i].ref); env.cache.invalidate("academy") }
            })
        }
        item {
            SectionTitle("برنامه‌ی $roleFa", note = cur?.let { "نسخه‌ی ${it.version}" })
        }
        item {
            if (cur == null) Skeleton(Modifier.fillMaxWidth().height(100.dp), radius = 14.dp)
            else HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(horizontal = 14.dp, vertical = 6.dp)) {
                cur.modules.forEachIndexed { i, m ->
                    if (i > 0) HorizontalDivider(color = c.lineDivider)
                    Column(Modifier.padding(vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text(m.titleFa, style = Divan.type.small, color = c.textPrimary)
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            for (ref in m.skills + m.evals) Tag(ref, figure = true)
                        }
                    }
                }
            }
        }
        item { SectionTitle("آزمون‌های طلایی", note = "نمره‌ی نسخه‌ها در برابر خط پایه") }
        item {
            if (evals.data == null) Skeleton(Modifier.fillMaxWidth().height(120.dp), radius = 14.dp)
            else HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(horizontal = 14.dp, vertical = 4.dp)) {
                suites.forEachIndexed { i, s ->
                    if (i > 0) HorizontalDivider(color = c.lineDivider)
                    val last = s.recent.lastOrNull()
                    Row(Modifier.padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Column(Modifier.weight(1f)) {
                            Text(s.titleFa, style = Divan.type.small)
                            Text(buildAnnotatedString {
                                fig(s.ref); append("، ${s.cases.size} مورد، خط پایه "); fig(s.baseline?.score?.toInt()?.toString() ?: "—")
                            }, style = Divan.type.micro, color = c.textMuted)
                        }
                        Spark(s.recent.map { it.score }, min = 60.0, max = 100.0)
                        last?.let { Fig(it.score.toInt().toString(), Modifier.width(28.dp), style = Divan.type.figure.copy(fontWeight = FontWeight.SemiBold), color = if (it.passed) c.positive else c.negative) }
                    }
                }
            }
        }
        item { ModelComparisonCard(role) }
    }
}

@Composable
private fun TeachingCard(t: Teaching, roleOf: (String) -> String, busy: Boolean, onApprove: () -> Unit, onReject: () -> Unit) {
    val c = Divan.colors
    val proposed = t.status == "proposed"
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(if (proposed) c.softGold else c.card).padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Fig(t.ref, style = Divan.type.figureSmall, color = c.textMuted)
            if (t.source == "voice") DIcon(DivanIcon.MIC, size = 12.dp, tint = c.textMuted)
            Text(roleOf(t.target.ref), style = Divan.type.micro, color = c.textMuted)
            Text(ago(t.createdAt), style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f))
            LabelPill(TEACH_STATUS[t.status], t.status)
        }
        RichText(t.textMd, style = Divan.type.body, color = c.textPrimary)
        t.proposal?.let {
            Text(it.diffMd, style = Divan.type.figureSmall.copy(textDirection = TextDirection.Ltr), color = c.textSecondary, modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.page).padding(12.dp))
        }
        t.evalRun?.let { e ->
            Text(buildAnnotatedString {
                append("آزمون: "); fig(e.score?.toInt()?.toString() ?: "—"); append(" در برابر خط پایه "); fig(e.baseline?.toInt()?.toString() ?: "—")
                append(when (e.passed) { true -> " · قبول"; false -> " · رد"; null -> " · در حال اجرا" })
            }, style = Divan.type.caption, color = when (e.passed) { true -> c.positive; false -> c.negative; null -> c.textSecondary })
        }
        if (proposed) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            HqButton("تأیید کن", onApprove, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.SEAL, loading = busy, enabled = t.evalRun?.passed != false)
            HqButton("رد کن", onReject, variant = BtnVariant.GHOST, size = BtnSize.SM)
        }
    }
}
