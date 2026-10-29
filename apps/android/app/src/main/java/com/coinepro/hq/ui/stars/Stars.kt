package com.coinepro.hq.ui.stars

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
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
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.agentKindOf
import com.coinepro.hq.core.format.deptOf
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.net.CompanyStanding
import com.coinepro.hq.core.net.StarRollup
import com.coinepro.hq.designsystem.Avatar
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.ScoreBar
import com.coinepro.hq.ui.v14.Spark
import com.coinepro.hq.ui.v14.StarsRow

// Contract §18.4 ⟨1.4.3⟩: efficiency (the envelope kept, little waste, a fair cost per accepted output) is 15% of a company's score.
private val PARTS: List<Triple<(CompanyStanding) -> Double?, String, Int>> = listOf(
    Triple({ it.parts.kpi }, "KPI", 35), Triple({ it.parts.challenges }, "چالش‌ها", 20),
    Triple({ it.parts.compliance }, "انطباق", 15), Triple({ it.parts.people }, "ستاره‌ی کارمندها", 15),
    Triple({ it.parts.efficiency }, "کارایی", 15),
)

/** The roll-up of a period, or none yet (the hub's 404 before its first one). */
private class Rolled(val rollup: StarRollup?)

/** No roll-up for the period yet: what makes one and when, instead of an error. */
@Composable
private fun NoRollup(period: String) {
    HqCard(Modifier.fillMaxWidth()) {
        Empty(
            if (period == "week") "هنوز برآیند هفتگی ساخته نشده" else "هنوز برآیند ماهانه ساخته نشده",
            icon = DivanIcon.STAR,
            body = if (period == "week") "برآیند هر هفته شنبه صبح از ستاره‌هایی که مدیرعامل‌ها با شاهد داده‌اند ساخته میشود؛ هفته‌ای که ستاره‌ای نگرفته برآیند ندارد."
            else "برآیند هر ماه روز اول ماه ساخته میشود؛ تا آن وقت رتبه‌ی شرکت‌ها و کارمندها این‌جا خالی است.",
        )
    }
}

/** ستاره‌ها (contract §18.4): CEOs give their people 0–5 stars weekly under their own rubric; companies are ranked
 *  from KPIs, the overseer's challenges, compliance and their people. The owner gives no stars; the owner's 1–10
 *  rating stays separate. */
@Composable
fun StarsScreen() {
    val nav = LocalNav.current
    val c = Divan.colors
    val companies = rememberCompanies()
    var period by rememberSaveable { mutableStateOf("week") }
    var co by rememberSaveable { mutableStateOf<String?>(null) }
    // A period without a roll-up yet is not an error: the hub answers 404 until its first Saturday (or first of the month).
    val q = rememberQuery("stars:rollup:$period", "stars", maxAgeMs = 60_000) { Rolled(rollup(period)) }
    val rubrics = rememberQuery("stars:rubrics", "stars", maxAgeMs = 300_000) { rubrics() }
    val lessons = rememberQuery("stars:lessons", "stars", maxAgeMs = 120_000) { lessons() }
    val r = refresher(q, rubrics, lessons)

    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            PageHeader("ستاره‌ها", eyebrow = "برآیند هفتگی شنبه صبح، ماهانه اول هر ماه") {
                Segmented(listOf(SegOption("week", "این هفته"), SegOption("month", "این ماه")), period, { period = it }, Modifier.fillMaxWidth())
            }
        }
        item { Text("مدیرعامل هر شرکت طبق آیین‌نامه‌ی خودش به کارمندها ستاره میدهد؛ ناظر کل انصاف و شاهدش را میپاید. امتیاز ۱ تا ۱۰ تو جداست.", style = Divan.type.small, color = c.textSecondary) }
        val roll = q.data?.rollup
        when {
            q.data == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            q.data == null -> item { Skeleton(Modifier.fillMaxWidth().height(200.dp), radius = 16.dp) }
            roll == null || (roll.companies.isEmpty() && roll.employees.isEmpty()) -> item { NoRollup(period) }
            else -> {
                roll.companies.firstOrNull { it.company == roll.bestCompany }?.let { best ->
                    item {
                        HqCard(Modifier.fillMaxWidth(), tahrir = true) {
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                                Box(Modifier.size(52.dp).clip(CircleShape).background(c.softGold), contentAlignment = Alignment.Center) { DIcon(DivanIcon.STAR, size = 26.dp, tint = c.goldInk, active = true) }
                                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                    Text("شرکت برتر ${if (period == "week") "هفته · هفته‌ی ${jDate(roll.key)}" else "ماه"}", style = Divan.type.caption, color = c.textMuted)
                                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                        CompanyMark(best.company, height = 20.dp)
                                        Text(companyOf(companies, best.company).nameFa, style = Divan.type.h2)
                                    }
                                    best.stars?.let { StarsRow(it, size = 18.dp) }
                                }
                                Fig(best.score?.toInt()?.toString() ?: "—", style = Divan.type.figureL, color = c.textPrimary)
                            }
                        }
                    }
                }
                item {
                    HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(horizontal = 14.dp, vertical = 12.dp)) {
                        SectionTitle("رتبه‌ی شرکت‌ها", note = "امتیاز = ۳۵٪ KPI + ۲۰٪ چالش‌ها + ۱۵٪ انطباق + ۱۵٪ ستاره‌ی کارمندها + ۱۵٪ کارایی (مصرف درست بودجه)")
                        roll.companies.forEachIndexed { i, k ->
                            if (i > 0) HorizontalDivider(color = c.lineDivider)
                            Column(Modifier.padding(vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Fig(k.rank?.toString() ?: "—", Modifier.width(18.dp), style = Divan.type.figure.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
                                    CompanyMark(k.company, height = 15.dp, mono = true, ink = c.textSecondary)
                                    Text(companyOf(companies, k.company).nameFa, style = Divan.type.bodyStrong, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                                    Spark(k.trend, min = 40.0, max = 100.0, width = 48.dp)
                                }
                                k.stars?.let { StarsRow(it, Modifier.padding(start = 26.dp)) } ?: Text("هنوز ستاره‌ای نگرفته", Modifier.padding(start = 26.dp), style = Divan.type.micro, color = c.textMuted)
                                Column(Modifier.padding(start = 26.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                    for (pair in PARTS.chunked(2)) Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                                        for ((get, fa, w) in pair) Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                            Text("$fa $w٪", style = Divan.type.micro, color = c.textMuted)
                                            ScoreBar(get(k))
                                        }
                                        // An odd last row keeps its half width.
                                        if (pair.size == 1) Spacer(Modifier.weight(1f))
                                    }
                                }
                            }
                        }
                    }
                }
                item { SectionTitle("کارمندهای برتر", note = "ستاره‌ی مدیرعامل، با شاهد") }
                item {
                    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        FilterChip("همه", co == null, { co = null })
                        for (k in roll.companies) FilterChip(companyOf(companies, k.company).nameFa, co == k.company, { co = k.company })
                    }
                }
                item {
                    val people = roll.employees.filter { co == null || it.company == co }
                    HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(horizontal = 12.dp, vertical = 4.dp)) {
                        people.forEachIndexed { i, e ->
                            if (i > 0) HorizontalDivider(color = c.lineDivider)
                            Row(Modifier.fillMaxWidth().clickable(role = Role.Button) { nav.go("employees/${e.code}") }.padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                Fig((if (co != null) e.rankCompany else e.rankHolding).toString(), Modifier.width(16.dp), style = Divan.type.figureSmall, color = c.textMuted)
                                Avatar(agentKindOf(e.code), dept = deptOf(e.code), size = 30.dp)
                                Column(Modifier.weight(1f)) {
                                    Text(e.titleFa, style = Divan.type.small, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                    Fig(e.code, style = Divan.type.figureSmall, color = c.textMuted)
                                }
                                e.efficiency?.let { eff ->
                                    Column(horizontalAlignment = Alignment.End) {
                                        Fig(eff.toInt().toString(), style = Divan.type.figureSmall, color = c.textSecondary)
                                        Text("کارایی", style = Divan.type.micro, color = c.textMuted)
                                    }
                                }
                                StarsRow(e.stars, size = 12.dp)
                            }
                        }
                    }
                }
            }
        }
        item { SectionTitle("درس‌ها از شرکت برتر", note = "هر هفته ناظر مینویسد؛ بقیه پیشنهاد به‌کارگیری میدهند") }
        val ls = lessons.data
        if (ls == null && lessons.error != null) item { ErrorBlock(lessons.error, { lessons.refresh() }) }
        else if (ls == null) item { Skeleton(Modifier.fillMaxWidth().height(120.dp), radius = 14.dp) }
        else if (ls.isEmpty()) item {
            Text("هنوز درسی نوشته نشده؛ ناظر بعد از هر برآیند از شرکت برتر مینویسد.", Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), style = Divan.type.caption, color = c.textMuted)
        }
        else items(ls.size, key = { ls[it].ref }) { i ->
            val l = ls[i]
            HqCard(Modifier.fillMaxWidth()) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    CompanyMark(l.sourceCompany, height = 13.dp, mono = true, ink = c.textSecondary)
                    Text(l.titleFa, style = Divan.type.bodyStrong, modifier = Modifier.weight(1f))
                    Fig(l.ref, style = Divan.type.figureSmall, color = c.textMuted)
                }
                Md(l.bodyMd, Modifier.padding(top = 6.dp))
                FlowRow(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    for (a in l.adoption) {
                        val (fa, tone) = when (a.status) { "adopted" -> "به‌کار گرفت" to Tone.POS; "rejected" -> "رد کرد" to Tone.NEG; else -> "پیشنهاد داد" to Tone.NEUTRAL }
                        Pill("${companyOf(companies, a.company).nameFa}: $fa", tone, dot = true)
                    }
                }
            }
        }
        val rubric = rubrics.data?.let { all -> all.firstOrNull { it.company == (co ?: roll?.bestCompany) } ?: all.firstOrNull() }
        item { SectionTitle("آیین‌نامه‌ی ستاره" + (rubric?.let { " · " + companyOf(companies, it.company).nameFa } ?: ""), note = "نوشته‌ی مدیرعامل همان شرکت؛ تو میبینی") }
        item {
            if (rubrics.data == null && rubrics.error == null) Skeleton(Modifier.fillMaxWidth().height(140.dp), radius = 14.dp)
            else if (rubric == null) Text("هنوز هیچ مدیرعاملی آیین‌نامه‌ی ستاره ننوشته.", Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), style = Divan.type.caption, color = c.textMuted)
            else HqCard(Modifier.fillMaxWidth()) {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    for (k in rubric.criteria) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Column(Modifier.weight(1f)) {
                            Text(k.nameFa, style = Divan.type.small)
                            Text(k.descriptionMd, style = Divan.type.micro, color = c.textMuted)
                        }
                        Fig("${k.weight.toInt()}%", style = Divan.type.figureSmall, color = c.textSecondary)
                    }
                    HorizontalDivider(color = c.lineDivider)
                    Text(rubric.rulesMd, style = Divan.type.caption, color = c.textSecondary)
                    Text("نسخه‌ی ${rubric.version}، ${jDate(rubric.updatedAt)}", style = Divan.type.micro, color = c.textMuted)
                }
            }
        }
    }
}
