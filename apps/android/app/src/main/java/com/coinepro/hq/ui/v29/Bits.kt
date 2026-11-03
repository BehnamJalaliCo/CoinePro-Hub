package com.coinepro.hq.ui.v29

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.coinepro.hq.core.data.FixWay
import com.coinepro.hq.core.data.employeeStateFa
import com.coinepro.hq.core.data.employeeStateOf
import com.coinepro.hq.core.data.employeeStateTone
import com.coinepro.hq.core.data.fixFa
import com.coinepro.hq.core.data.fixRoute
import com.coinepro.hq.core.data.fixWay
import com.coinepro.hq.core.data.orderStateFa
import com.coinepro.hq.core.data.orderStateTone
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.net.DayValue
import com.coinepro.hq.core.net.Fix
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.Stuck
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.ChartLine
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.LinesChart
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.timesFig
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies

// Contract §29 ⟨1.11⟩: the pieces the new screens share (the order's state, an employee's state, a one-tap fix, a KPI chart), built
// from the app's own components (Pill, HqButton, LinesChart, CompanyMark) and its bidi helpers.

/** The hub's words for the owner as they should read: every number a Latin figure ([com.coinepro.hq.ui.v14.figs]) and every Latin run
 *  isolated left to right ([timesFig]), inside the Persian sentence. */
fun plain(text: String): androidx.compose.ui.text.AnnotatedString = timesFig(com.coinepro.hq.ui.v14.figs(text))

/** A paragraph of the hub's prose: justified (its last line at the start; a long Latin run keeps it at the start), lines that breathe,
 *  numbers Latin and Latin runs isolated. */
@Composable
fun Para(text: String, modifier: Modifier = Modifier, style: androidx.compose.ui.text.TextStyle = Divan.type.small, color: Color = Divan.colors.textSecondary, maxLines: Int = Int.MAX_VALUE) {
    if (text.isBlank()) return
    val size = style.fontSize.takeIf { it.isSp }?.value ?: 13f
    Text(
        plain(text.trim()), modifier.fillMaxWidth(),
        style = style.copy(textAlign = com.coinepro.hq.designsystem.alignOf(text), lineHeight = (size * 1.7f).sp),
        color = color, maxLines = maxLines, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis,
    )
}

/** Whether this hub serves [f] (false once its route turned out missing in this app start; the screens then hide that part). */
@Composable
fun served(f: HubFeature): Boolean {
    val gaps by LocalEnv.current.api.gaps.missing.collectAsStateWithLifecycle()
    return f !in gaps
}

/** An order's state (§29.2) as a pill; a moving one breathes. */
@Composable
fun OrderStatePill(state: String?, modifier: Modifier = Modifier) {
    Pill(orderStateFa(state), orderStateTone(state), modifier, live = state == "in_progress", dot = state != "in_progress")
}

/** An employee's state (§29.14): idle, thinking, working, waiting, stuck or done; [state] null reads the older activity. */
@Composable
fun EmployeeStatePill(state: String?, activity: String?, modifier: Modifier = Modifier) {
    val s = employeeStateOf(state, activity)
    Pill(employeeStateFa(s), employeeStateTone(s), modifier, live = s == "working" || s == "thinking", dot = s != "working" && s != "thinking", icon = if (s == "stuck") DivanIcon.URGENT else null)
}

/** A stuck employee: why, in the owner's words, and its fix. */
@Composable
fun StuckLine(stuck: Stuck, company: String?, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Column(
        modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.softNegative).padding(horizontal = 12.dp, vertical = 10.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DIcon(DivanIcon.URGENT, size = 16.dp, tint = c.negative, modifier = Modifier.padding(top = 2.dp))
            Text(plain("گیر کرده: ${stuck.reasonFa.ifBlank { "علتش هنوز روشن نیست" }}"), style = Divan.type.small, color = c.textPrimary, modifier = Modifier.weight(1f))
        }
        stuck.fix?.let { FixButton(it, company, null) }
    }
}

/**
 * A one-tap fix (§29.2, §29.9, §29.14): an order's fix is posted to it ([orderRef]); a sealed one asks for the passkey; one that is done
 * elsewhere (a card, a guide, the release of a lock) opens that place. [onDone] refreshes what showed it.
 */
@Composable
fun FixButton(fix: Fix, company: String?, orderRef: String?, modifier: Modifier = Modifier, size: BtnSize = BtnSize.SM, budgetTokens: Long? = null, onDone: () -> Unit = {}) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val act = activity()
    val action = rememberAction()
    val way = fixWay(fix)
    val to = fixRoute(fix, company)
    HqButton(fixFa(fix), {
        when {
            way == FixWay.OPEN || orderRef == null -> if (to != null) nav.go(to) else toasts.info("این را مدیرعامل همان شرکت درست میکند؛ در گزارش هفته میبینی.")
            else -> action.run {
                val add = if (fix.action == "budget.add") budgetTokens ?: fix.target?.toLongOrNull() else null
                val sign: com.coinepro.hq.core.net.StepUp = { a, t -> env.auth.stepUp(act, a, t) }
                val out = env.api.gated(HubFeature.ORDER_REPORT) {
                    orderFix(orderRef, fix, add, if (way == FixWay.SIGNED) sign else null)
                }
                if (out == null && !env.api.gaps.has(HubFeature.ORDER_REPORT)) toasts.info("هاب هنوز این اصلاح را ندارد؛ بعد از به‌روزرسانی هاب.")
                else {
                    env.cache.invalidate("order-report", "orders", "home", "work")
                    toasts.ok("انجام شد؛ کار دوباره راه افتاد.")
                    onDone()
                }
            }
        }
    }, modifier, variant = BtnVariant.PRIMARY, size = size, icon = if (way == FixWay.OPEN) DivanIcon.NEXT else DivanIcon.SEAL, loading = action.busy)
}

/** A company's mark and name on one line (servers and companies are named by the company, never by a host). */
@Composable
fun CoName(code: String, modifier: Modifier = Modifier, height: Dp = 12.dp, color: Color = Divan.colors.textSecondary, bold: Boolean = false) {
    val name = companyOf(rememberCompanies(), code).nameFa
    Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        CompanyMark(code, height = height, mono = true, ink = color)
        Text(name, style = if (bold) Divan.type.small.copy(fontWeight = FontWeight.SemiBold) else Divan.type.caption, color = color, maxLines = 1)
    }
}

/** One series per company over the same days (a gap where a day has no figure, never a zero), in each company's palette slot. */
@Composable
fun CompanyKpiChart(series: List<Pair<String, List<DayValue>>>, label: String, fmt: (Double) -> String, modifier: Modifier = Modifier, height: Dp = 180.dp) {
    val c = Divan.colors
    val companies = rememberCompanies()
    val days = series.flatMap { (_, s) -> s.map { it.day } }.distinct().sorted()
    if (days.isEmpty()) {
        Text("هنوز عددی از اتصال‌ها نرسیده؛ با اولین خواندن روزانه این‌جا پر میشود.", style = Divan.type.caption, color = c.textMuted, modifier = modifier)
        return
    }
    val lines = series.map { (co, s) ->
        val byDay = s.associate { it.day to it.value }
        ChartLine(co, companyOf(companies, co).nameFa, com.coinepro.hq.ui.v16.companyColor(co), days.map { byDay[it] }, mark = { CompanyMark(co, height = 11.dp, mono = true, ink = c.textSecondary) })
    }
    LinesChart(days.map { jDate(it) }, lines, fmt = fmt, label = label, modifier = modifier, tick = { com.coinepro.hq.ui.v16.compact(it) }, height = height)
}

/** A small round icon tile, as the app's cards begin. */
@Composable
fun IconTile(icon: DivanIcon, tint: Color, bg: Color, size: Dp = 40.dp) {
    Box(Modifier.size(size).clip(CircleShape).background(bg), contentAlignment = Alignment.Center) { DIcon(icon, size = size * 0.5f, tint = tint) }
}
