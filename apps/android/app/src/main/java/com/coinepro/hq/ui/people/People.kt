package com.coinepro.hq.ui.people

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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.DEPT_FA
import com.coinepro.hq.core.format.DEPT_ICON
import com.coinepro.hq.core.format.actorFa
import com.coinepro.hq.core.format.faDecimal
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.net.HrEmployee
import com.coinepro.hq.core.net.HrRound
import com.coinepro.hq.designsystem.BarTone
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.MeterBar
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v17.ActorAvatar
import com.coinepro.hq.ui.v17.RefChip
import com.coinepro.hq.ui.v17.RefTone
import com.coinepro.hq.ui.v17.Trend
import com.coinepro.hq.ui.v18.HR_FLAG
import com.coinepro.hq.ui.v18.HR_STATE
import com.coinepro.hq.ui.v18.jMonth
import com.coinepro.hq.ui.v18.pct01
import java.util.Locale

// Department ranks and the monthly HR round (contract §21.5), mirroring apps/web/src/components/v18/people.tsx. Scores, ranks and flags
// are rules: 35% people, 30% delivery, 20% efficiency, 15% the owner's ratings (spread over the rest when there are none).

private val PARTS = listOf("people" to "نیرو", "delivery" to "تحویل", "efficiency" to "کارایی", "owner" to "امتیاز تو")

/** Ranks of a company's departments, by rule; a department without active employees is not ranked. */
@Composable
fun DepartmentRanks(company: String) {
    val c = Divan.colors
    var period by rememberSaveable { mutableStateOf("month") }
    val q = rememberQuery("rankings:$period:$company", "rankings", "stars") { departmentRanks(period, company) }
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("رتبه‌ی دپارتمان‌ها", note = "با برآیند ستاره‌ها حساب میشود؛ دپارتمان بی‌کارمند فعال رتبه نمیگیرد")
        Segmented(listOf(SegOption("week", "هفته"), SegOption("month", "ماه")), period, { period = it }, Modifier.fillMaxWidth().padding(top = 10.dp))
        val rows = q.data?.sortedBy { it.rankCompany }
        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            when {
                rows == null -> Skeleton(Modifier.fillMaxWidth().height(160.dp))
                rows.isEmpty() -> Empty("هنوز دپارتمانی رتبه نگرفته", icon = DivanIcon.DEPARTMENT)
                else -> rows.forEach { r ->
                    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            Box(Modifier.size(28.dp).clip(CircleShape).background(c.card), contentAlignment = Alignment.Center) { Fig("${r.rankCompany}", style = Divan.type.figureSmall.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk) }
                            DIcon(DEPT_ICON[r.department] ?: DivanIcon.DEPARTMENT, size = 18.dp, tint = c.silverInk)
                            Column(Modifier.weight(1f)) {
                                Text(DEPT_FA[r.department] ?: r.department, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                                Text("${r.employees} نفر" + (r.rankHolding?.let { "، رتبه‌ی $it میان همین دپارتمان در هلدینگ" } ?: ""), style = Divan.type.micro, color = c.textMuted)
                            }
                            Trend(r.trend, null, width = 56.dp, height = 22.dp)
                            Fig(String.format(Locale.US, "%.1f", r.score), Modifier.width(44.dp), style = Divan.type.figureM, color = c.textPrimary)
                        }
                        MeterBar(r.score, tone = if (r.score >= 75) BarTone.GOLD else if (r.score >= 60) BarTone.SILVER else BarTone.WARN)
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            for ((k, fa) in PARTS) {
                                val v = when (k) { "people" -> r.parts.people; "delivery" -> r.parts.delivery; "efficiency" -> r.parts.efficiency; else -> r.parts.owner }
                                Column(Modifier.weight(1f).clip(RoundedCornerShape(8.dp)).background(c.card).padding(vertical = 4.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                                    Text(fa, style = Divan.type.micro, color = c.textMuted, maxLines = 1)
                                    Fig(v?.let { com.coinepro.hq.ui.v17.num(it) } ?: "—", style = Divan.type.figureSmall.copy(fontWeight = FontWeight.SemiBold), color = if (v == null) c.textMuted else c.textPrimary)
                                }
                            }
                        }
                    }
                }
            }
            Text("جایی که امتیاز تو نیست («—»)، وزن ۱۵٪ آن میان سه جزء دیگر پخش شده است.", style = Divan.type.micro, color = c.textMuted)
        }
    }
}

@Composable
private fun Cell(label: String, modifier: Modifier, value: @Composable () -> Unit) {
    Column(modifier.clip(RoundedCornerShape(8.dp)).background(Divan.colors.tile).padding(8.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(label, style = Divan.type.micro, color = Divan.colors.textMuted, maxLines = 1)
        value()
    }
}

@Composable
private fun Prose(v: String, color: Color = Divan.colors.textPrimary) = Text(v, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = color)

/** One employee in an HR round: the score against last month, the facts pack, and the rule flags. */
@Composable
fun EmployeeHr(e: HrEmployee) {
    val c = Divan.colors
    val drop = e.scorePrev?.let { e.score - it }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.Bottom) {
            Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(faDecimal(e.score), style = Divan.type.h1.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                Text("از ۱۰", Modifier.padding(bottom = 4.dp), style = Divan.type.micro, color = c.textMuted)
            }
            if (drop != null) Text(
                "${if (drop >= 0) "▲" else "▼"} ${faDecimal(kotlin.math.abs(drop))} از ماه قبل (${faDecimal(e.scorePrev)})", Modifier.padding(bottom = 4.dp),
                style = Divan.type.caption, color = if (drop <= -1.5) c.warning else if (drop >= 0) c.positive else c.textSecondary,
            ) else Text("ماه اول", Modifier.padding(bottom = 4.dp), style = Divan.type.caption, color = c.textMuted)
        }
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Cell("ستاره", Modifier.weight(1f)) { Prose(e.stars?.let { faDecimal(it) } ?: "—") }
                Cell("کارایی", Modifier.weight(1f)) { Prose(e.efficiency?.let { com.coinepro.hq.ui.v17.num(it) } ?: "—") }
                Cell("امتیاز تو", Modifier.weight(1f)) { Prose(e.ownerAvg?.let { faDecimal(it) } ?: "—") }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Cell("اجرای شکست‌خورده", Modifier.weight(1f)) { Fig(pct01(e.failedShare), style = Divan.type.figureSmall.copy(fontWeight = FontWeight.SemiBold), color = if (e.failedShare >= 0.25) c.warning else c.textPrimary) }
                Cell("یافته‌ی باز", Modifier.weight(1f)) { Prose("${e.findingsOpen}", if (e.findingsOpen > 0) c.warning else c.textPrimary) }
                Cell("ادعای رد شده", Modifier.weight(1f)) { Prose("${e.refutedClaims}", if (e.refutedClaims > 0) c.negative else c.textPrimary) }
            }
        }
        e.probationUntil?.let { Text("دوره‌ی آزمایشی تا ${jDate(it, withYear = true)}", style = Divan.type.caption, color = c.textSecondary) }
        if (e.flags.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) { e.flags.forEach { LabelPill(HR_FLAG[it], it) } }
        else Text("بی‌پرچم؛ کارتی برایش ساخته نمیشود مگر با شاهد و دلیل.", style = Divan.type.caption, color = c.textMuted)
    }
}

/** A whole HR round: its state, the evaluator, the deadline, the report, the cards and the teachings, then everyone in it. */
@Composable
fun HrRoundView(r: HrRound) {
    val nav = LocalNav.current
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            LabelPill(HR_STATE[r.state], r.state)
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                ActorAvatar(r.evaluator, size = 20.dp)
                Text(actorFa(r.evaluator), style = Divan.type.caption, color = c.textSecondary)
            }
            Text("مهلت ${jDate(r.dueAt)}", style = Divan.type.caption, color = c.textSecondary)
            r.deliverableRef?.let { RefChip(it, note = "گزارش HR") }
            r.decisions.forEach { RefChip(it, note = "کارت ارزیابی") }
            r.teachings.forEach { RefChip(it, note = "آموزش", tone = RefTone.NEUTRAL) }
        }
        r.employees.forEach { e ->
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.card).padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(Modifier.clickable(role = Role.Button) { nav.go("employees/${e.code}") }, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(e.titleFa, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                    Fig(e.code, style = Divan.type.figureSmall, color = c.textMuted)
                }
                EmployeeHr(e)
            }
        }
    }
}

@Composable
private fun RoundSheet(r: HrRound, onClose: () -> Unit) =
    HqSheet(onClose, "ارزیابی ماهانه‌ی ${jMonth(r.month)}", ref = r.ref, sub = "پرچم‌ها قاعده‌اند؛ ارزیاب فقط برای پرچم‌خورده‌ها کارت ارزیابی میسازد. «آموزش» کارت ندارد: پیش‌نویس آموزش آکادمی برای مدیر عملیات AI.") { HrRoundView(r) }

/** The employee's line of the latest monthly HR round (§21.5): the facts pack, the rule flags, and the card if one was proposed. */
@Composable
fun HrCard(code: String, company: String) {
    val c = Divan.colors
    val q = rememberQuery("hr:rounds:$company", "hr", "people") { hrRounds(company) }
    var open by remember { mutableStateOf(false) }
    val r = q.data?.sortedByDescending { it.month }?.firstOrNull { x -> x.employees.any { it.code == code } }
    val e = r?.employees?.firstOrNull { it.code == code }
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("ارزیابی ماهانه", note = r?.let { "${jMonth(it.month)}، ارزیاب ${actorFa(it.evaluator)}" } ?: "اول هر ماه شمسی") {
            if (r != null) HqButton("کل دور", { open = true }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.NEXT)
        }
        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            when {
                q.data == null -> Skeleton(Modifier.fillMaxWidth().height(110.dp))
                r == null || e == null -> Text("در دور ارزیابی این ماه نیست (تازه آمده، یا ارزیاب خود اوست).", style = Divan.type.caption, color = c.textMuted)
                else -> {
                    EmployeeHr(e)
                    if (r.decisions.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                        Text("کارت این دور:", style = Divan.type.caption, color = c.textSecondary)
                        r.decisions.forEach { RefChip(it) }
                    }
                }
            }
        }
    }
    if (open && r != null) RoundSheet(r) { open = false }
}

/** The company's latest HR round in one line, beside its department ranks. */
@Composable
fun HrRoundLine(company: String) {
    val c = Divan.colors
    val q = rememberQuery("hr:rounds:$company", "hr", "people") { hrRounds(company) }
    var open by remember { mutableStateOf(false) }
    val r = q.data?.maxByOrNull { it.month } ?: return
    val flagged = r.employees.count { it.flags.isNotEmpty() }
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.card).clickable(role = Role.Button) { open = true }.padding(12.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(Modifier.size(36.dp).clip(CircleShape).background(c.tile), contentAlignment = Alignment.Center) { DIcon(DivanIcon.RATE, size = 18.dp, tint = c.goldInk) }
        Column(Modifier.weight(1f)) {
            Text(buildAnnotatedString { append("ارزیابی ماهانه‌ی ${jMonth(r.month)} "); fig(r.ref, c.textMuted) }, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
            Text("${r.employees.size} نفر، $flagged پرچم‌خورده" + if (r.decisions.isNotEmpty()) "، ${r.decisions.size} کارت" else "", style = Divan.type.caption, color = c.textSecondary)
        }
        LabelPill(HR_STATE[r.state], r.state)
    }
    if (open) RoundSheet(r) { open = false }
}
