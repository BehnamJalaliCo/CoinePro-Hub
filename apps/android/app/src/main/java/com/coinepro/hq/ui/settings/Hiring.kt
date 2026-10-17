package com.coinepro.hq.ui.settings

import androidx.compose.foundation.background
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

/** Contract §18.11: hiring starts with the owner (owner, 2026-10-17). Closed until the owner opens it, by hiring directly or by asking the CEOs. */
@Composable
fun HiringCard() {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val nav = LocalNav.current
    val act = activity()
    val c = Divan.colors
    val hiring = rememberQuery("hiring", "hiring") { hiring() }
    val action = rememberAction()
    var sheet by rememberSaveable { mutableStateOf(false) }
    var confirm by rememberSaveable { mutableStateOf(false) }
    val h = hiring.data
    val open = h?.state == "open"

    HqCard(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            SectionTitle("استخدام", Modifier.weight(1f), note = "تا خودت شروع نکنی، هیچ ایجنتی استخدام پیشنهاد نمیدهد.")
            if (h != null) Pill(if (open) "باز برای پیشنهاد" else "بسته", if (open) Tone.POS else Tone.NEUTRAL)
        }
        if (h != null) {
            Text(stateLine(h), style = Divan.type.small, color = c.textSecondary, modifier = Modifier.padding(top = 10.dp))
            Column(Modifier.padding(top = 12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Choice(DivanIcon.HIRE, "خودم استخدام میکنم", "نقش، دپارتمان، مدل و effort را خودت انتخاب میکنی و با گذرکلید مُهر میکنی.") { sheet = true }
                if (open) {
                    Choice(DivanIcon.CLOSE, "بستن استخدام", "پیشنهادهای منتظر پس گرفته میشوند؛ چیزی حذف نمیشود.", enabled = !action.busy) {
                        action.run {
                            hiring.set(env.api.closeHiring())
                            env.cache.invalidate("hiring", "decisions", "inbox")
                            toasts.info("استخدام بسته شد؛ پیشنهادهای منتظر پس گرفته شدند.")
                        }
                    }
                } else {
                    Choice(DivanIcon.SEAL, "مدیرعامل‌ها پیشنهاد بدهند", "هر مدیرعامل یک کار «تیم ماه اول» میگیرد؛ پیشنهادها همان لحظه در کارتابل.") { confirm = true }
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
    if (confirm) AlertDialog(
        onDismissRequest = { confirm = false },
        containerColor = c.overlay,
        title = { Text("استخدام برای مدیرعامل‌ها باز شود؟", style = Divan.type.h3) },
        text = {
            Text(
                "هر مدیرعامل (و هر نقش هلدینگ با وظیفه‌ی استخدام) یک کار «تیم ماه اولت را پیشنهاد بده» میگیرد. هیچ استخدامی بدون مُهر تو انجام نمیشود و هر وقت بخواهی میبندی.",
                style = Divan.type.small, color = c.textSecondary,
            )
        },
        confirmButton = {
            HqButton("با گذرکلید باز کن", {
                action.run {
                    hiring.set(env.api.startHiring("proposals") { a, t -> env.auth.stepUp(act, a, t) })
                    env.cache.invalidate("hiring", "work", "planner")
                    confirm = false
                    toasts.ok("استخدام باز شد؛ هر مدیرعامل یک کار «تیم ماه اول» گرفت.")
                }
            }, variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, loading = action.busy)
        },
        dismissButton = { HqButton("نه حالا", { confirm = false }, variant = BtnVariant.GHOST) },
    )
}

private fun stateLine(h: Hiring): String {
    val text = when {
        h.state == "open" -> "مدیرعامل‌ها تیم ماه اول را پیشنهاد میدهند؛ هر پیشنهاد با برآورد توکن به کارتابل تو میرسد."
        h.mode == "self" -> "فقط خودت استخدام میکنی؛ ایجنت‌ها پیشنهاد نمیدهند و کمبود تیم را در خروجی کارشان مینویسند."
        else -> "وقتی هاب را برای کار واقعی بالا آوردی، یکی از دو راه را انتخاب کن. تا آن موقع ایجنت‌ها کمبود تیم را فقط در خروجی کارشان مینویسند."
    }
    val who = if (h.changedBy?.kind == "owner") "تو" else "سیستم"
    return if (h.changedAt != null) "$text ($who، ${ago(h.changedAt)})" else text
}

@Composable
private fun Choice(icon: DivanIcon, title: String, note: String, enabled: Boolean = true, onClick: () -> Unit) {
    val c = Divan.colors
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).clickable(enabled = enabled, role = Role.Button, onClick = onClick).padding(12.dp),
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
    val fitting = if (co != null && department != null) hireableRoles(roles.data.orEmpty(), co.kind, department) else emptyList()
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
                    "برای این دپارتمان هنوز منشور کارمندی نیست. منشور تازه را Claude سشن مشورت مینویسد؛ بگو چه نقشی میخواهی.",
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
            "با گذرکلید استخدام کن", {
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
        }
        Column(horizontalAlignment = Alignment.End) {
            Fig(tokens(r.limits.tokensPerRun), style = Divan.type.figureSmall, color = c.textMuted)
            Text("سقف هر اجرا", style = Divan.type.micro, color = c.textMuted)
        }
    }
}
