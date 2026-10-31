package com.coinepro.hq.ui.settings

import androidx.compose.foundation.background
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.core.net.Company
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.runtime.remember
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.modelLabel
import com.coinepro.hq.core.format.tokens
import com.coinepro.hq.core.net.HireIn
import com.coinepro.hq.core.net.Hiring
import com.coinepro.hq.core.net.RoleInfo
import com.coinepro.hq.core.net.hireableRoles
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.figs

private val EFFORTS = listOf("low", "medium", "high", "xhigh")
private val MODELS = listOf("claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5")

/** Contract §18.11 (owner, 2026-10-17): closed until the owner brings the hub up; then each company's CEO hires with full authority inside
 *  the company's monthly envelope and picks the model each job needs, or every hire is the owner's card. The owner can always hire directly. */
@Composable
fun HiringCard() {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val nav = LocalNav.current
    val act = activity()
    val c = Divan.colors
    val hiring = rememberQuery("hiring", "hiring") { hiring() }
    val companies = rememberQuery("companies", "companies", maxAgeMs = 60_000) { companies() }
    val action = rememberAction()
    var sheet by rememberSaveable { mutableStateOf(false) }
    var envelopes by rememberSaveable { mutableStateOf<String?>(null) }
    var confirm by rememberSaveable { mutableStateOf(false) }
    val h = hiring.data
    val open = h?.state == "open"
    val delegated = open && h?.mode == "delegated"

    HqCard(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            SectionTitle("استخدام", Modifier.weight(1f), note = if (delegated) "مدیرعامل‌ها با اختیار کامل، داخل پاکت ماهانه‌ی هر شرکت" else "تا خودت باز نکنی، هیچ ایجنتی استخدام پیشنهاد نمیدهد.")
            if (h != null) Pill(if (delegated) "با مدیرعامل‌ها" else if (open) "با مُهر من" else "بسته", if (open) Tone.POS else Tone.NEUTRAL)
        }
        if (h != null) {
            Text(stateLine(h), style = Divan.type.small, color = c.textSecondary, modifier = Modifier.padding(top = 10.dp))
            if (h.envelopes.isNotEmpty()) EnvelopeRows(h, companies.data.orEmpty()) { envelopes = "edit" }
            Column(Modifier.padding(top = 12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (!delegated) Choice(DivanIcon.SEAL, "اختیار استخدام با مدیرعامل‌ها", "پاکت ماهانه‌ی هر شرکت را تعیین کن؛ از آن به بعد استخدام با خود مدیرعامل‌هاست.", primary = true) { envelopes = "open" }
                Choice(DivanIcon.HIRE, "خودم استخدام میکنم", "نقش، دپارتمان، مدل و effort را خودت انتخاب میکنی و با اثر انگشت مُهر میکنی.") { sheet = true }
                if (!open) Choice(DivanIcon.DECISION, "هر استخدام با مُهر من", "مدیرها پیشنهاد میدهند و هر استخدام یک کارت در کارتابل توست.") { confirm = true }
                if (open) {
                    Choice(DivanIcon.CLOSE, "بستن استخدام", "پیشنهادهای منتظر پس گرفته میشوند؛ چیزی حذف نمیشود.", enabled = !action.busy) {
                        action.run {
                            hiring.set(env.api.closeHiring())
                            env.cache.invalidate("hiring", "decisions", "inbox")
                            toasts.info("استخدام بسته شد؛ پیشنهادهای منتظر پس گرفته شدند.")
                        }
                    }
                }
            }
            if (h.withdrawn.isNotEmpty()) {
                Text("پیشنهادهای پس‌گرفته (در تاریخچه میمانند)", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.padding(top = 12.dp, bottom = 6.dp))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    for (ref in h.withdrawn) {
                        Fig(
                            ref,
                            Modifier.clip(RoundedCornerShape(50)).background(c.tile).clickable { nav.go("cartable/$ref") }.padding(horizontal = 10.dp, vertical = 4.dp),
                            style = Divan.type.figureSmall, color = c.textSecondary,
                        )
                    }
                }
            }
        }
    }

    if (sheet) HireSheet { sheet = false }
    val mode = envelopes
    if (mode != null && h != null) EnvelopeSheet(h, companies.data.orEmpty(), opening = mode == "open", onDone = { hiring.set(it) }) { envelopes = null }
    if (confirm) AlertDialog(
        onDismissRequest = { confirm = false },
        containerColor = c.overlay,
        title = { Text("هر استخدام با مُهر تو؟", style = Divan.type.h3) },
        text = {
            Text(
                "هر مدیرعامل یک کار «تیم ماه اولت را پیشنهاد بده» میگیرد و هر استخدام یک کارت در کارتابل توست. هر وقت بخواهی اختیار را به مدیرعامل‌ها میدهی یا میبندی.",
                style = Divan.type.small, color = c.textSecondary,
            )
        },
        confirmButton = {
            HqButton("با اثر انگشت باز کن", {
                action.run {
                    hiring.set(env.api.startHiring("proposals") { a, t -> env.auth.stepUp(act, a, t) })
                    env.cache.invalidate("hiring", "work", "planner")
                    confirm = false
                    toasts.ok("استخدام باز شد؛ هر استخدام یک کارت برای مُهر توست.")
                }
            }, variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, loading = action.busy)
        },
        dismissButton = { HqButton("نه حالا", { confirm = false }, variant = BtnVariant.GHOST) },
    )
}

private fun stateLine(h: Hiring): String {
    val text = when {
        h.state == "open" && h.mode == "delegated" -> "هر دپارتمان به اندازه‌ی نیازش نیرو میخواهد و مدیرعامل تصمیم میگیرد و مدل هر کار را خودش انتخاب میکند. هر استخدام یک استوری میسازد؛ از همان‌جا خوش‌آمد میگویی یا برمیگردانی. مصرف درست بودجه ستاره میگیرد."
        h.state == "open" -> "هر استخدام یک کارت در کارتابل توست، با برآورد توکن."
        else -> "وقتی هاب را برای کار واقعی بالا آوردی، اختیار را به مدیرعامل‌ها بده. تا آن موقع ایجنت‌ها کمبود تیم را فقط در خروجی کارشان مینویسند."
    }
    val who = if (h.changedBy?.kind == "owner") "تو" else "سیستم"
    return if (h.changedAt != null) "$text ($who، ${ago(h.changedAt)})" else text
}

/** Each operating company's month: used and committed against its envelope. */
@Composable
private fun EnvelopeRows(h: Hiring, companies: List<Company>, onEdit: () -> Unit) {
    val c = Divan.colors
    Column(
        Modifier.fillMaxWidth().padding(top = 12.dp).clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("پاکت ماهانه‌ی هر شرکت (توکن)", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f))
            HqButton("پاکت‌ها", onEdit, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.BUDGET)
        }
        for (e in h.envelopes) {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    CompanyMark(e.company, height = 13.dp, mono = true, ink = c.textSecondary)
                    Text(companyOf(companies, e.company).nameFa, style = Divan.type.small, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                    val cap = e.tokensMonth
                    if (cap != null) Fig("${tokens(e.usedMonth)} / ${tokens(cap)}", style = Divan.type.figureSmall, color = c.textSecondary)
                    else Text("پاکت تعیین نشده", style = Divan.type.caption, color = c.warning)
                }
                e.tokensMonth?.let { cap ->
                    val used = (e.usedMonth.toFloat() / cap).coerceIn(0f, 1f)
                    val committed = (e.committedMonth.toFloat() / cap).coerceIn(0f, 1f)
                    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                        Box(Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(50)).background(c.page)) {
                            Box(Modifier.fillMaxWidth(committed).height(6.dp).clip(RoundedCornerShape(50)).background(c.softGold))
                            Box(Modifier.fillMaxWidth(used).height(6.dp).clip(RoundedCornerShape(50)).background(if (used >= 0.9f) c.negative else if (used >= 0.7f) c.warning else c.positive))
                        }
                    }
                    // The commitment is a figure; the count of hires is prose.
                    Text(figs("تعهد کارمندها ${tokens(e.committedMonth)}") + AnnotatedString("، استخدام این ماه ${e.hiresMonth}"), style = Divan.type.micro, color = c.textMuted)
                }
            }
        }
    }
}

/** The envelopes: each operating company's monthly token budget (contract §9 /budgets, §18.11). With `opening`, delegated hiring opens after. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun EnvelopeSheet(h: Hiring, companies: List<Company>, opening: Boolean, onDone: (Hiring) -> Unit, onDismiss: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val action = rememberAction()
    val vals = remember { mutableStateMapOf<String, String>().apply { for (e in h.envelopes) put(e.company, e.tokensMonth?.let { millions(it) }.orEmpty()) } }
    val parsed = h.envelopes.associate { it.company to parseMillions(vals[it.company].orEmpty()) }
    val valid = parsed.values.all { it != null && it > 0 }
    val changed = parsed.filter { (co, t) -> t != null && t > 0 && t != h.envelopes.first { it.company == co }.tokensMonth }.mapValues { it.value!! }
    val total = parsed.values.sumOf { it ?: 0L }

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true), containerColor = c.overlay) {
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).imePadding().padding(horizontal = 16.dp).padding(bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text(if (opening) "اختیار استخدام با مدیرعامل‌ها" else "پاکت ماهانه‌ی شرکت‌ها", style = Divan.type.h2)
            Text("هر شرکت تا سقف پاکت ماهانه‌اش استخدام میکند؛ استخدامی که در پاکت جا نشود پذیرفته نمیشود. پاکت همان بودجه‌ی ماهانه‌ی شرکت در خزانه است.", style = Divan.type.caption, color = c.textMuted)
            for (e in h.envelopes) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    CompanyMark(e.company, height = 13.dp, mono = true, ink = c.textSecondary)
                    Text(companyOf(companies, e.company).nameFa, style = Divan.type.small, modifier = Modifier.weight(1f))
                    Text(figs("تعهد ${tokens(e.committedMonth)}، مصرف ${tokens(e.usedMonth)}"), style = Divan.type.micro, color = c.textMuted)
                }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                        HqTextField(vals[e.company].orEmpty(), { vals[e.company] = it }, "—", Modifier.weight(1f), maxLength = 8, figure = true)
                    }
                    Fig("M", style = Divan.type.figure, color = c.textMuted)
                }
            }
            Text(figs("جمع پاکت‌ها ${tokens(total)} در ماه. استخدام‌های خود هلدینگ همیشه با مُهر توست."), style = Divan.type.small, color = c.textSecondary,
                modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp))
            HqButton(
                if (opening) "با اثر انگشت ثبت کن و باز کن" else "با اثر انگشت ثبت کن", {
                    action.run {
                        if (changed.isNotEmpty()) env.api.setEnvelopes(changed) { target -> env.auth.stepUp(act, "budgets.update", target) }
                        if (opening) {
                            onDone(env.api.startHiring("delegated") { a, t -> env.auth.stepUp(act, a, t) })
                            toasts.ok("اختیار استخدام با مدیرعامل‌هاست؛ هر استخدام یک استوری میسازد.")
                        } else {
                            onDone(env.api.hiring())
                            toasts.ok("پاکت‌ها ثبت شد.")
                        }
                        env.cache.invalidate("hiring", "treasury", "work", "planner")
                        onDismiss()
                    }
                },
                Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEAL,
                enabled = valid && (opening || changed.isNotEmpty()), loading = action.busy,
            )
        }
    }
}

/** "5" or "2.5" (Latin or Persian digits, either decimal mark) millions → tokens. */
internal fun parseMillions(text: String): Long? {
    val t = text.trim().map { ch -> if (ch in '۰'..'۹') '0' + (ch - '۰') else if (ch == '٫' || ch == ',') '.' else ch }.joinToString("")
    val m = t.toDoubleOrNull() ?: return null
    return if (m > 0) Math.round(m * 1_000_000) else null
}

private fun millions(tokens: Long): String = (tokens / 1_000_000.0).let { if (it == Math.floor(it)) it.toLong().toString() else it.toString() }

@Composable
private fun Choice(icon: DivanIcon, title: String, note: String, enabled: Boolean = true, primary: Boolean = false, onClick: () -> Unit) {
    val c = Divan.colors
    val shape = RoundedCornerShape(12.dp)
    Row(
        Modifier.fillMaxWidth().clip(shape).background(if (primary) c.softGold else c.tile).then(if (primary) Modifier.border(1.dp, c.goldInk, shape) else Modifier)
            .clickable(enabled = enabled, role = Role.Button, onClick = onClick).padding(12.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        DIcon(icon, size = 20.dp, tint = c.goldInk)
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(title, style = Divan.type.body, fontWeight = FontWeight.SemiBold)
            Text(note, style = Divan.type.caption, color = c.textMuted)
        }
    }
}

/** The owner's own hire (POST /org/hires) in a bottom sheet. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HireSheet(onDismiss: () -> Unit) {
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true), containerColor = Divan.colors.overlay) {
        HireForm(onDone = onDismiss, modifier = Modifier.verticalScroll(rememberScrollState()).imePadding())
    }
}

/** A charter that fits the company and the department, sealed with a passkey bound to the exact body. The initial values let a
 *  screenshot show a filled form. */
@Composable
fun HireForm(onDone: () -> Unit, modifier: Modifier = Modifier, company0: String? = null, department0: String? = null, role0: String? = null) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val companies = rememberQuery("companies", "companies", maxAgeMs = 60_000) { companies() }
    val roles = rememberQuery("roles", "roles", maxAgeMs = 300_000) { roles() }
    val connections = rememberQuery("connections", "treasury", maxAgeMs = 300_000) { connections() }
    val action = rememberAction()
    var company by rememberSaveable { mutableStateOf(company0) }
    var department by rememberSaveable { mutableStateOf(department0) }
    var roleKey by rememberSaveable { mutableStateOf(role0) }
    var titleFa by rememberSaveable { mutableStateOf("") }
    var model by rememberSaveable { mutableStateOf("") }
    var effort by rememberSaveable { mutableStateOf("high") }
    var reason by rememberSaveable { mutableStateOf("") }
    val departments = rememberQuery("departments:${company.orEmpty()}", "companies") { company?.let { departments(it) }.orEmpty() }
    val co = companies.data.orEmpty().firstOrNull { it.code == company }
    val fitting = if (co != null && department != null) hireableRoles(roles.data.orEmpty(), co.kind, department, co.code) else emptyList()
    val role = fitting.firstOrNull { it.role == roleKey }
    val offered = connections.data.orEmpty().filter { it.status == "enabled" }.flatMap { it.models }.toSet()
    val models = MODELS.filter { offered.isEmpty() || it in offered }
    // A role preset by a screenshot (or kept across a rotation) fills the defaults once it is known.
    if (role != null && model.isEmpty()) { titleFa = role.titleFa; model = role.model; effort = role.effort }
    val ready = role != null && titleFa.isNotBlank()

    fun pick(r: RoleInfo) { roleKey = r.role; titleFa = r.titleFa; model = r.model; effort = r.effort }

    Column(modifier.fillMaxWidth().padding(horizontal = 16.dp).padding(bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text("استخدام مستقیم", style = Divan.type.h2)
        Text("با مُهر خودت؛ کارمند همان لحظه کارش را شروع میکند و کارت تصمیمش در تاریخچه میماند.", style = Divan.type.caption, color = c.textMuted)
        Text("کدام شرکت", style = Divan.type.caption, color = c.textMuted)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            for (x in companies.data.orEmpty().filter { it.status == "active" }) {
                val on = company == x.code
                val shape = RoundedCornerShape(10.dp)
                Row(
                    Modifier.clip(shape).background(if (on) c.softGold else c.tile).then(if (on) Modifier.border(1.dp, c.goldInk, shape) else Modifier)
                        .clickable(role = Role.RadioButton) { company = x.code; department = null; roleKey = null; model = "" }.padding(horizontal = 12.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    CompanyMark(x.code, height = 14.dp, mono = true, ink = c.textSecondary)
                    Text(x.nameFa ?: x.code, style = Divan.type.small)
                }
            }
        }
        if (company != null) {
            Text("کدام دپارتمان", style = Divan.type.caption, color = c.textMuted)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                for (d in departments.data.orEmpty().filter { it.status == "active" }) FilterChip(d.nameFa, department == d.code, { department = d.code; roleKey = null; model = "" })
            }
        }
        if (department != null && roles.data != null) {
            Text("کدام نقش", style = Divan.type.caption, color = c.textMuted)
            if (fitting.isEmpty()) {
                Text(
                    // ⟨1.6⟩ §22.5: the department's manager writes any role the work needs.
                    "برای این دپارتمان هنوز منشور کارمندی نیست. مدیر همین دپارتمان هر نقشی که کار لازم دارد مینویسد؛ از صفحه‌ی شرکت، روی دپارتمان بزن و «نقش تازه بخواه».",
                    style = Divan.type.small, color = c.textMuted,
                    modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp),
                )
            }
            for (r in fitting) RoleRow(r, r.role == roleKey) { pick(r) }
        }
        if (role != null) {
            Text("عنوان فارسی", style = Divan.type.caption, color = c.textMuted)
            HqTextField(titleFa, { titleFa = it }, role.titleFa, Modifier.fillMaxWidth(), maxLength = 200)
            Text("مدل", style = Divan.type.caption, color = c.textMuted)
            Segmented(models.map { SegOption(it, modelLabel(it).substringBefore(' ')) }, model, { model = it }, Modifier.fillMaxWidth())
            Text("effort", style = Divan.type.caption, color = c.textMuted)
            Segmented(EFFORTS.map { SegOption(it, it) }, effort, { effort = it }, Modifier.fillMaxWidth())
            Text(figs("پیش‌فرض‌ها از منشور نقش‌اند (${modelLabel(role.model)}، ${role.effort}). ارزان‌ترین مدلی که کار را خوب انجام میدهد بهترین است."), style = Divan.type.micro, color = c.textMuted)
            Text("چرا (اختیاری)", style = Divan.type.caption, color = c.textMuted)
            HqTextField(reason, { reason = it }, "مثلاً: پایش سایت و پنل کاربری", Modifier.fillMaxWidth(), singleLine = false, minLines = 3, maxLength = 5_000)
        }
        HqButton(
            "با اثر انگشت استخدام کن", {
                val r = role ?: return@HqButton
                action.run {
                    val body = HireIn(company!!, department!!, r.role, titleFa.trim(), model = model, effort = effort, reason = reason.trim().ifBlank { null })
                    val out = env.api.hireDirect(body) { target -> env.auth.stepUp(act, "hire.direct", target) }
                    env.cache.invalidate("hiring", "employees", "companies", "decisions", "inbox")
                    toasts.ok("${out.employee.code} استخدام شد (${out.decision.ref}).")
                    onDone()
                }
            },
            Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEAL, enabled = ready, loading = action.busy,
        )
    }
}

@Composable
private fun RoleRow(r: RoleInfo, selected: Boolean, onClick: () -> Unit) {
    val c = Divan.colors
    val shape = RoundedCornerShape(12.dp)
    Row(
        Modifier.fillMaxWidth().clip(shape).background(if (selected) c.softGold else c.tile)
            .then(if (selected) Modifier.border(1.dp, c.goldInk, shape) else Modifier)
            .clickable(role = Role.RadioButton, onClick = onClick).padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        DIcon(DivanIcon.HIRE, size = 20.dp, tint = c.textSecondary)
        Column(Modifier.weight(1f)) {
            Text(r.titleFa, style = Divan.type.small, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Fig("${r.titleEn}, ${modelLabel(r.model)}, ${r.effort}", style = Divan.type.figureSmall, color = c.textMuted, maxLines = 1)
            // ⟨1.6⟩ §22.5: a role written on demand, scoped to its company and department.
            if (r.source == "draft") Row(
                Modifier.padding(top = 4.dp).clip(RoundedCornerShape(50)).background(c.softLapis).padding(horizontal = 8.dp, vertical = 1.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                Text("نوشته‌ی مدیر دپارتمان", style = Divan.type.micro.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold), color = c.lapis)
                r.draft?.let { Fig(it, style = Divan.type.figureSmall, color = c.lapis) }
            }
        }
        Column(horizontalAlignment = Alignment.End) {
            Fig(tokens(r.limits.tokensPerRun), style = Divan.type.figureSmall, color = c.textMuted)
            Text("سقف هر اجرا", style = Divan.type.micro, color = c.textMuted)
        }
    }
}
