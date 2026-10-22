package com.coinepro.hq.ui.treasury

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.DEPT_FA
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.format.tokens
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.core.net.RoiRow
import com.coinepro.hq.core.net.WasteDay
import com.coinepro.hq.designsystem.BarTone
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.MeterBar
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v17.CoMark
import com.coinepro.hq.ui.v17.Trend
import com.coinepro.hq.ui.v18.WASTE
import com.coinepro.hq.ui.v18.pct01
import com.coinepro.hq.ui.v18.tehDay

// Waste and ROI in the treasury (contract §21.7), mirroring apps/web/src/components/v18/treasury.tsx. Waste is computed by code at 07:45 for
// the day before, from the ledger and the runs (never a prompt or a response); efficiency stars read the same figure. Revenue, net and
// ROI are a company's only: commission cannot be traced to one agent, and no figure is invented.

private fun dayFa(d: String) = jDate("${d}T08:00:00Z")

/** The daily waste report: yesterday by category, with the fourteen days before (the dashed line is the 15% notice). */
@Composable
fun WasteCard(company: String? = null) {
    val nav = LocalNav.current
    val c = Divan.colors
    val from = remember { tehDay(14) }
    val to = remember { tehDay(1) }
    val q = rememberQuery("treasury:waste:$from:$to:${company ?: ""}", "treasury") { wasteRange(from, to, company) }
    var pick by rememberSaveable { mutableStateOf<String?>(null) }
    var open by rememberSaveable { mutableStateOf<String?>(null) }
    val days = q.data.orEmpty().sortedBy { it.day }
    val d: WasteDay? = days.firstOrNull { it.day == pick } ?: days.lastOrNull()
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("هدررفت روزانه", note = "با کد، از دفتر خزانه و اجراها؛ همان عددی که کارایی ستاره‌ها میخواند")
        when {
            d == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
            d == null -> Skeleton(Modifier.fillMaxWidth().height(200.dp).padding(top = 8.dp))
            else -> Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Pill(if (d.share > 0.15) "بالای ۱۵٪؛ اعلان گزارش رفت" else "زیر آستانه", if (d.share > 0.15) Tone.WARN else Tone.NEUTRAL, dot = true)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(20.dp), verticalArrangement = Arrangement.spacedBy(8.dp), itemVerticalAlignment = Alignment.Bottom) {
                    Column {
                        Text(dayFa(d.day), style = Divan.type.micro, color = c.textMuted)
                        Fig(usd(d.wasteUsd), style = Divan.type.figureL, color = c.textPrimary)
                    }
                    Column {
                        Text("سهم از مصرف روز", style = Divan.type.micro, color = c.textMuted)
                        Fig(pct01(d.share, 1), style = Divan.type.figureM, color = if (d.share > 0.15) c.warning else c.textPrimary)
                    }
                    Column {
                        Text("در برابر میانگین ۷ روز", style = Divan.type.micro, color = c.textMuted)
                        Fig((if (d.vs7d >= 0) "+" else "−") + pct01(kotlin.math.abs(d.vs7d)), style = Divan.type.figureM, color = if (d.vs7d > 0.1) c.warning else if (d.vs7d < -0.1) c.positive else c.textPrimary)
                    }
                    Column {
                        Text("کل روز", style = Divan.type.micro, color = c.textMuted)
                        Fig("${tokens(d.wasteTokens)} / ${tokens(d.totalTokens)} · ${usd(d.totalUsd)}", style = Divan.type.figureSmall, color = c.textSecondary)
                    }
                }
                WasteBars(days, d.day) { pick = it }
                val items = d.items.sortedByDescending { it.usd.toDoubleOrNull() ?: 0.0 }
                val top = items.firstOrNull()?.usd?.toDoubleOrNull()?.takeIf { it > 0 } ?: 1.0
                Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    for (it in items) {
                        val w = WASTE[it.category] ?: (it.category to "")
                        val on = open == it.category
                        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).clickable(role = Role.Button) { open = if (on) null else it.category }.padding(horizontal = 4.dp, vertical = 6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Text(w.first, Modifier.weight(1f), style = Divan.type.small, color = c.textPrimary)
                                Text("${it.count} مورد", style = Divan.type.micro, color = c.textMuted)
                                Fig(tokens(it.tokens), Modifier.width(48.dp), style = Divan.type.figureSmall, color = c.textMuted)
                                Fig(usd(it.usd), Modifier.width(52.dp), style = Divan.type.figureSmall.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                            }
                            MeterBar((it.usd.toDoubleOrNull() ?: 0.0) / top * 100, tone = BarTone.SILVER, height = 5.dp)
                        }
                        if (on) Column(Modifier.padding(start = 14.dp, bottom = 6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(w.second, style = Divan.type.micro, color = c.textMuted)
                            for (t in it.top) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                t.employee?.let { e -> Fig(e, Modifier.clickable(role = Role.Button) { nav.go("employees/$e") }, style = Divan.type.figureSmall, color = c.textPrimary) }
                                t.workRef?.let { r -> Fig(r, Modifier.clickable(role = Role.Button) { nav.go("work/$r") }, style = Divan.type.figureSmall, color = c.goldInk) }
                                t.runId?.let { r -> Fig(r, style = Divan.type.figureSmall, color = c.textMuted) }
                                Box(Modifier.weight(1f))
                                Fig(tokens(t.tokens), style = Divan.type.figureSmall, color = c.textSecondary)
                            }
                        }
                    }
                }
            }
        }
    }
}

/** Fourteen days of the waste share, oldest at the left (data charts read left to right); a tap picks the day. */
@Composable
private fun WasteBars(days: List<WasteDay>, picked: String, onPick: (String) -> Unit) {
    val c = Divan.colors
    val max = maxOf(0.2, days.maxOfOrNull { it.share } ?: 0.0)
    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
        Box(Modifier.fillMaxWidth().height(64.dp).semantics { contentDescription = "سهم هدررفت ${days.size} روز" }) {
            Row(Modifier.fillMaxSize(), horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.Bottom) {
                for (x in days) {
                    val color = when {
                        x.day == picked -> c.goldFill
                        x.share > 0.15 -> c.warning.copy(alpha = 0.7f)
                        else -> c.silverInk.copy(alpha = 0.4f)
                    }
                    Box(Modifier.weight(1f).fillMaxHeight(maxOf(0.06f, (x.share / max).toFloat())).clip(RoundedCornerShape(topStart = 4.dp, topEnd = 4.dp)).background(color)
                        .clickable(role = Role.Button, onClickLabel = "${dayFa(x.day)}: ${pct01(x.share, 1)}") { onPick(x.day) })
                }
            }
            val line = c.warning.copy(alpha = 0.6f)
            Canvas(Modifier.fillMaxSize()) {
                val y = size.height * (1 - (0.15 / max).toFloat())
                drawLine(line, Offset(0f, y), Offset(size.width, y), 1.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(6f, 6f)))
            }
        }
    }
}

// ---------------------------------------------------------------------------- ROI --
private val BY = listOf(SegOption("company", "شرکت"), SegOption("department", "دپارتمان"), SegOption("employee", "کارمند"))

@Composable
private fun RoiLabel(by: String, r: RoiRow) {
    val nav = LocalNav.current
    val c = Divan.colors
    when (by) {
        "company" -> Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) { CoMark(r.company, height = 12.dp); Fig(r.company, style = Divan.type.figure, color = c.textPrimary) }
        "department" -> Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            CoMark(r.company, height = 11.dp)
            val dept = r.key.substringAfter('-')
            Text(DEPT_FA[dept] ?: dept, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
        }
        else -> Fig(r.key, Modifier.clickable(role = Role.Button) { nav.go("employees/${r.key}") }, style = Divan.type.figure, color = c.textPrimary)
    }
}

@Composable
private fun Num(label: String, value: String, color: androidx.compose.ui.graphics.Color = Divan.colors.textSecondary) {
    Column {
        Text(label, style = Divan.type.micro, color = Divan.colors.textMuted, maxLines = 1)
        Fig(value, style = Divan.type.figureSmall, color = color)
    }
}

/** Cost, accepted deliverables and the owner's rating per company, department or employee; revenue and ROI for companies only. */
@Composable
fun RoiCard(company: String? = null) {
    val c = Divan.colors
    var by by rememberSaveable { mutableStateOf("company") }
    var period by rememberSaveable { mutableStateOf("month") }
    val q = rememberQuery("treasury:roi:$by:$period:${company ?: ""}", "treasury") { roi(by, period, company) }
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("ROI", note = "هزینه، خروجی پذیرفته‌شده و امتیاز تو؛ درآمد فقط برای شرکت، چون کمیسیون به یک ایجنت نسبت داده نمیشود")
        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Segmented(BY, by, { by = it }, Modifier.fillMaxWidth())
            Segmented(listOf(SegOption("week", "هفته"), SegOption("month", "ماه")), period, { period = it }, Modifier.fillMaxWidth())
            val rows = q.data?.sortedWith(compareByDescending<RoiRow> { it.roi ?: -1.0 }.thenByDescending { it.costUsd.toDoubleOrNull() ?: 0.0 })
            when {
                rows == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
                rows == null -> Skeleton(Modifier.fillMaxWidth().height(160.dp))
                else -> rows.forEach { r ->
                    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Box(Modifier.weight(1f)) { RoiLabel(by, r) }
                            Trend(r.trend, null, width = 56.dp, height = 20.dp)
                            if (r.roi != null) Fig("${com.coinepro.hq.ui.v17.num(r.roi)}×", style = Divan.type.figureM, color = c.textPrimary)
                            else Fig(usd(r.costPerAcceptedUsd), style = Divan.type.figureM, color = c.textPrimary)
                        }
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Num("هزینه", usd(r.costUsd))
                            Num("پذیرفته", "${r.accepted}")
                            Num("میانگین امتیاز", r.avgRating?.let { com.coinepro.hq.ui.v17.num(it) } ?: "—")
                            Num("ارزش", com.coinepro.hq.ui.v17.num(r.valuePoints))
                            Num("هر خروجی", usd(r.costPerAcceptedUsd))
                            if (r.revenueUsd != null) {
                                Num("درآمد", usd(r.revenueUsd))
                                Num("خالص", usd(r.netUsd), if ((r.netUsd?.toDoubleOrNull() ?: 0.0) < 0) c.negative else c.textSecondary)
                            }
                        }
                        val attributed = listOfNotNull(r.attributed.rescued?.let { "$it نجات" }, r.attributed.resolvedConversations?.let { "$it گفت‌وگو" })
                        if (attributed.isNotEmpty()) Text("نسبت‌داده: " + attributed.joinToString("، "), style = Divan.type.micro, color = c.textMuted)
                    }
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                DIcon(DivanIcon.INFO, size = 13.dp, tint = c.textMuted, modifier = Modifier.padding(top = 2.dp))
                Text(buildAnnotatedString {
                    append("روند: برای شرکت "); fig("ROI"); append("، برای دپارتمان و کارمند هزینه‌ی هر خروجی پذیرفته‌شده در دوره‌های قبل. برای کارمند و دپارتمان عدد درآمد ساخته نمیشود.")
                }, style = Divan.type.micro, color = c.textMuted)
            }
        }
    }
}
