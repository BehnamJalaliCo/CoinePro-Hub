package com.coinepro.hq.ui.academy

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
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.format.modelLabel
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.core.net.EvalRun
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.Spark
import com.coinepro.hq.ui.v14.Tag

private val MODEL_ORDER = listOf("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5")
private fun modelRank(m: String) = MODEL_ORDER.indexOf(m).let { if (it < 0) 99 else it }

/** Item 16 (contract §18.6): what an employee has been taught and how it scores — charter and curriculum versions, the
 *  skills in its prompt, its latest evals against each suite's baseline, the lessons it carries, the score trend. */
@Composable
fun TrainingCard(code: String, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val nav = LocalNav.current
    val q = rememberQuery("academy:record:$code", "academy", maxAgeMs = 120_000) { trainingRecord(code) }
    val evals = rememberQuery("academy:evals", "academy", maxAgeMs = 60_000) { evals() }
    HqCard(modifier.fillMaxWidth()) {
        SectionTitle("آموزش", note = "منشور، برنامه‌ی آکادمی، مهارت‌ها و آزمون‌ها")
        val r = q.data
        when {
            r == null && q.error == null -> Skeleton(Modifier.fillMaxWidth().padding(top = 10.dp).height(96.dp), radius = 12.dp)
            r == null -> Text("هنوز سابقه‌ی آموزشی ندارد.", style = Divan.type.small, color = c.textMuted, modifier = Modifier.padding(top = 8.dp))
            else -> Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(buildAnnotatedString {
                        append("منشور نسخه‌ی "); fig(r.charterVersion.toString())
                        r.curriculumVersion?.let { append("، برنامه‌ی آکادمی نسخه‌ی "); fig(it.toString()) }
                    }, style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.weight(1f))
                    Spark(r.trend, width = 88.dp, min = 60.0, max = 100.0)
                }
                if (r.skills.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    r.skills.forEach { s -> Tag(s, Modifier.clickable { nav.go("skills") }, figure = true) }
                }
                if (r.evals.isEmpty()) Text("هنوز آزمونی نداده.", style = Divan.type.small, color = c.textMuted)
                r.evals.forEachIndexed { i, e ->
                    val suite = evals.data?.firstOrNull { it.ref == e.suite }
                    val pass = suite?.baseline?.let { e.score >= it.score - 1 }
                    if (i > 0) HorizontalDivider(color = c.lineDivider)
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Column(Modifier.weight(1f)) {
                            Text(suite?.titleFa ?: e.suite, style = Divan.type.small, maxLines = 1)
                            Text(buildAnnotatedString {
                                fig(e.suite); append(" · ${jDate(e.at)}")
                                suite?.baseline?.let { append(" · خط پایه "); fig(it.score.toInt().toString()) }
                            }, style = Divan.type.micro, color = c.textMuted)
                        }
                        Fig(
                            e.score.toInt().toString(), style = Divan.type.figure.copy(fontWeight = FontWeight.SemiBold),
                            color = when (pass) { false -> c.negative; true -> c.positive; null -> c.textPrimary },
                        )
                    }
                }
                if (r.lessons.isNotEmpty()) Text(buildAnnotatedString {
                    append("درس‌هایی که با خودش دارد: ")
                    r.lessons.forEachIndexed { i, l -> if (i > 0) append("، "); fig(l, c.goldInk) }
                }, style = Divan.type.micro, color = c.textMuted, modifier = Modifier.clickable { nav.go("stars") })
            }
        }
    }
}

/** Item 30 (contract §18.6 ⟨1.4.5⟩): the newest run of each golden suite on each model, with what it cost. The cheapest
 *  model that passes a suite is marked, so the CEOs' model choice inside their envelope has evidence behind it. */
@Composable
fun ModelComparisonCard(role: String, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val q = rememberQuery("academy:models:$role", "academy", maxAgeMs = 120_000) { modelComparison(role) }
    val evals = rememberQuery("academy:evals", "academy", maxAgeMs = 60_000) { evals() }
    HqCard(modifier.fillMaxWidth()) {
        SectionTitle("مقایسه‌ی مدل‌ها", note = "آخرین اجرای هر آزمون طلایی روی هر مدل، با هزینه‌ی همان اجرا")
        val runs = q.data?.items
        val suitesAll = evals.data
        if (runs == null || suitesAll == null) {
            Skeleton(Modifier.fillMaxWidth().padding(top = 10.dp).height(120.dp), radius = 12.dp)
            return@HqCard
        }
        if (runs.isEmpty()) {
            Text("برای این نقش هنوز آزمونی روی مدل‌ها اجرا نشده.", style = Divan.type.small, color = c.textMuted, modifier = Modifier.padding(top = 8.dp))
            return@HqCard
        }
        val models = runs.map { it.subject.ref }.distinct().sortedWith(compareBy({ modelRank(it) }, { it }))
        val suites = suitesAll.filter { s -> runs.any { it.suite == s.ref } }
        fun cell(suite: String, model: String): EvalRun? = runs.firstOrNull { it.suite == suite && it.subject.ref == model }
        val everywhere = models.filter { m -> suites.isNotEmpty() && suites.all { cell(it.ref, m)?.passed == true } }
            .minByOrNull { m -> suites.sumOf { cell(it.ref, m)?.costUsd ?: 0.0 } }
        Column(Modifier.padding(top = 10.dp)) {
            Row(Modifier.padding(bottom = 6.dp)) {
                Text("آزمون", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1.4f))
                models.forEach { Fig(modelLabel(it), Modifier.weight(1f), style = Divan.type.figureSmall, color = c.textMuted) }
            }
            suites.forEach { s ->
                val best = runs.filter { it.suite == s.ref && it.passed }.minByOrNull { it.costUsd ?: Double.MAX_VALUE }
                HorizontalDivider(color = c.lineDivider)
                Row(Modifier.padding(vertical = 8.dp), verticalAlignment = Alignment.Top) {
                    Column(Modifier.weight(1.4f)) {
                        Text(s.titleFa, style = Divan.type.small, maxLines = 2)
                        Text(buildAnnotatedString { append("خط پایه "); fig(s.baseline?.score?.toInt()?.toString() ?: "—") }, style = Divan.type.micro, color = c.textMuted)
                    }
                    models.forEach { m ->
                        val r = cell(s.ref, m)
                        Column(Modifier.weight(1f)) {
                            if (r == null) Text("—", style = Divan.type.small, color = c.textMuted)
                            else {
                                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                                    Fig(r.score.toInt().toString(), style = Divan.type.figure.copy(fontWeight = FontWeight.SemiBold), color = if (r.passed) c.positive else c.negative)
                                    if (best?.id == r.id) Box(Modifier.size(6.dp).clip(CircleShape).background(c.goldFill))
                                }
                                Fig(r.costUsd?.let { usd(it) } ?: "—", style = Divan.type.figureSmall, color = c.textMuted)
                            }
                        }
                    }
                }
            }
            Row(Modifier.padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Box(Modifier.size(6.dp).clip(CircleShape).background(c.goldFill))
                Text(buildAnnotatedString {
                    append("ارزان‌ترین مدلی که آن آزمون را قبول شده.")
                    if (everywhere != null) { append(" ارزان‌ترین مدلی که همه را قبول شده: "); fig(modelLabel(everywhere), c.textPrimary); append(".") }
                    else append(" هیچ مدلی همه را قبول نشده.")
                }, style = Divan.type.micro, color = c.textMuted, modifier = Modifier.width(0.dp).weight(1f))
            }
        }
    }
}
