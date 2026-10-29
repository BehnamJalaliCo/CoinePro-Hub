package com.coinepro.hq.ui.owner

import android.content.Context
import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.runtime.CompositionLocalProvider
import androidx.core.content.FileProvider
import com.coinepro.hq.core.net.Employee
import com.coinepro.hq.core.net.EvidenceIn
import com.coinepro.hq.core.net.Work
import com.coinepro.hq.core.net.WorkPatch
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.HqSheet
import java.io.File
import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val CLOSED = setOf("done", "cancelled", "failed")
private val EVIDENCE = listOf("deliverable" to "خروجی", "link" to "لینک", "metric" to "متریک", "log" to "لاگ")
private val LOCAL = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")
val EMPLOYEE_STATUS = mapOf("active" to "فعال", "paused" to "در مکث", "dismissed" to "اخراج شده")

/** The owner's hands on one work item (§4): edit (If-Match), close with evidence (a tick needs evidence, §1.9), or cancel with everything under it. */
@Composable
fun WorkActions(w: Work, onChanged: (Work) -> Unit) {
    if (w.status in CLOSED) return
    var mode by rememberSaveable { mutableStateOf<String?>(null) }
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        HqButton("ویرایش", { mode = "edit" }, size = BtnSize.SM, icon = DivanIcon.EDIT)
        HqButton("تکمیل با شاهد", { mode = "complete" }, size = BtnSize.SM, icon = DivanIcon.SEAL)
        HqButton("لغو", { mode = "cancel" }, size = BtnSize.SM, variant = BtnVariant.GHOST, icon = DivanIcon.CLOSE)
    }
    when (mode) {
        "edit" -> EditWorkSheet(w, { mode = null }, onChanged)
        "complete" -> CompleteWorkSheet(w, { mode = null }, onChanged)
        "cancel" -> CancelWorkSheet(w, { mode = null }, onChanged)
    }
}

@Composable
private fun EditWorkSheet(w: Work, onDismiss: () -> Unit, onChanged: (Work) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val action = rememberAction()
    val zone = ZoneId.systemDefault()
    val due0 = w.dueAt?.let { runCatching { LocalDateTime.ofInstant(Instant.parse(it), zone).format(LOCAL) }.getOrNull() }.orEmpty()
    var title by rememberSaveable { mutableStateOf(w.title) }
    var brief by rememberSaveable { mutableStateOf(w.brief) }
    var priority by rememberSaveable { mutableStateOf(w.priority) }
    var due by rememberSaveable { mutableStateOf(due0) }
    val dueOk = due.isBlank() || runCatching { LocalDateTime.parse(due.trim(), LOCAL) }.isSuccess
    HqSheet(onDismiss, "ویرایش کار", ref = w.ref) {
        Text("عنوان", style = Divan.type.caption, color = Divan.colors.textSecondary)
        HqTextField(title, { title = it }, "عنوان", Modifier.fillMaxWidth(), maxLength = 300)
        Text("شرح", style = Divan.type.caption, color = Divan.colors.textSecondary)
        HqTextField(brief, { brief = it }, "شرح", Modifier.fillMaxWidth(), singleLine = false, minLines = 4, maxLength = 20000)
        Text("اولویت", style = Divan.type.caption, color = Divan.colors.textSecondary)
        com.coinepro.hq.ui.work.PriorityPicker(priority, { priority = it }, Modifier.fillMaxWidth())
        Text("موعد", style = Divan.type.caption, color = Divan.colors.textSecondary)
        CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
            HqTextField(due, { due = it }, "2026-10-20 14:00", Modifier.fillMaxWidth(), maxLength = 16, figure = true)
        }
        HqButton("ذخیره", {
            action.run {
                val dueIso = due.trim().takeIf { it.isNotEmpty() }?.let { LocalDateTime.parse(it, LOCAL).atZone(zone).toInstant().toString() }
                val patch = WorkPatch(
                    title = title.trim().takeIf { it != w.title },
                    brief = brief.trim().takeIf { it != w.brief },
                    priority = priority.takeIf { it != w.priority },
                    dueAt = if (due.trim() != due0) dueIso else null,
                )
                if (patch != WorkPatch()) onChanged(env.api.patchWork(w, patch))
                env.cache.invalidate("work", "planner")
                toasts.ok("کار به‌روز شد.")
                onDismiss()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, enabled = title.isNotBlank() && dueOk, loading = action.busy)
    }
}

@Composable
private fun CompleteWorkSheet(w: Work, onDismiss: () -> Unit, onChanged: (Work) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val action = rememberAction()
    val rows = remember { mutableStateListOf(EvidenceIn("deliverable", "", "")) }
    val valid = rows.filter { it.ref.isNotBlank() }
    HqSheet(onDismiss, "تکمیل با شاهد", sub = "کار فقط با شاهد بسته میشود؛ شاهد در کار میماند و ناظر میتواند بررسی‌اش کند.", ref = w.ref) {
        rows.forEachIndexed { i, e ->
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(Divan.colors.tile).padding(10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) { EVIDENCE.forEach { (k, l) -> FilterChip(l, e.kind == k, { rows[i] = e.copy(kind = k) }) } }
                CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                    HqTextField(e.ref, { rows[i] = e.copy(ref = it) }, if (e.kind == "link") "https://…" else "O-000031", Modifier.fillMaxWidth(), maxLength = 500, figure = true)
                }
                HqTextField(e.note.orEmpty(), { rows[i] = e.copy(note = it) }, "توضیح کوتاه (اختیاری)", Modifier.fillMaxWidth(), maxLength = 1000)
            }
        }
        if (rows.size < 10) HqButton("شاهد دیگر", { rows.add(EvidenceIn("link", "", "")) }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.ADD)
        HqButton("ببند", {
            action.run {
                onChanged(env.api.completeWork(w.id, valid.map { it.copy(ref = it.ref.trim(), note = it.note?.trim()?.ifBlank { null }) }))
                env.cache.invalidate("work", "planner", "companies")
                toasts.ok("کار ${w.ref} با شاهد بسته شد.")
                onDismiss()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEAL, enabled = valid.isNotEmpty(), loading = action.busy)
    }
}

@Composable
private fun CancelWorkSheet(w: Work, onDismiss: () -> Unit, onChanged: (Work) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val action = rememberAction()
    var reason by rememberSaveable { mutableStateOf("") }
    HqSheet(onDismiss, "لغو کار", sub = "این کار و همه‌ی کارهای زیرش لغو میشوند و کارهای تکرارشونده‌اش هم تمام میشود. تاریخچه میماند.", ref = w.ref) {
        HqTextField(reason, { reason = it }, "دلیل (لازم)", Modifier.fillMaxWidth(), maxLength = 2000)
        HqButton("لغو کن", {
            action.run {
                onChanged(env.api.cancelWork(w.id, reason.trim()))
                env.cache.invalidate("work", "planner", "companies")
                toasts.info("کار ${w.ref} و کارهای زیرش لغو شد.")
                onDismiss()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.DANGER, size = BtnSize.LG, enabled = reason.isNotBlank(), loading = action.busy)
    }
}

/** Pause, resume and dismiss (§4): pause stops new work being routed and keeps open work; dismissal is sealed and hands knowledge over. */
@Composable
fun EmployeeActions(e: Employee, onChanged: () -> Unit) {
    if (e.status == "dismissed" || e.kind !in setOf("employee", "manager", "ceo")) return
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val action = rememberAction()
    var dismiss by rememberSaveable { mutableStateOf(false) }
    val name = e.displayName ?: e.titleFa
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        HqButton(if (e.status == "paused") "ادامه" else "مکث", {
            action.run {
                if (e.status == "paused") { env.api.resumeEmployee(e.code); toasts.ok("$name دوباره کار میگیرد.") }
                else { env.api.pauseEmployee(e.code); toasts.info("$name در مکث است؛ کار تازه به او نمیرسد و کارهای باز میمانند.") }
                env.cache.invalidate("employees", "companies")
                onChanged()
            }
        }, size = BtnSize.SM, icon = if (e.status == "paused") DivanIcon.RESUME else DivanIcon.PAUSE, loading = action.busy)
        if (e.kind != "ceo") HqButton("اخراج", { dismiss = true }, size = BtnSize.SM, variant = BtnVariant.GHOST, icon = DivanIcon.DISMISS)
    }
    if (dismiss) DismissSheet(e, { dismiss = false }, onChanged)
}

@Composable
private fun DismissSheet(e: Employee, onDismiss: () -> Unit, onChanged: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val action = rememberAction()
    val c = Divan.colors
    var reason by rememberSaveable { mutableStateOf("") }
    var to by rememberSaveable { mutableStateOf<String?>(null) }
    val peers = rememberQuery("employees:${e.company}", "employees") { employees(company = e.company) }.data?.items.orEmpty()
        .filter { it.code != e.code && it.status == "active" && (it.department == e.department || it.kind != "employee") }
    val name = e.displayName ?: e.titleFa
    HqSheet(onDismiss, "اخراج $name", sub = "کد ${e.code} دیگر به کسی داده نمیشود.") {
        listOf(
            "کارهای بازش به مدیرش برمیگردد، یا به کسی که اینجا انتخاب کنی.",
            "یک کار «انتقال دانش» ساخته میشود: خروجی‌ها، یادداشت‌ها، و نکات مثبت و منفی کارش.",
            "تاریخچه، خروجی‌ها و امتیازهایش میماند؛ هیچ چیز پاک نمیشود.",
        ).forEach { Text("• $it", style = Divan.type.small, color = c.textSecondary) }
        HqTextField(reason, { reason = it }, "دلیل (لازم)", Modifier.fillMaxWidth(), singleLine = false, minLines = 2, maxLength = 2000)
        Text("کارهای باز به", style = Divan.type.caption, color = c.textSecondary)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            FilterChip("مدیرش", to == null, { to = null })
            peers.forEach { p -> FilterChip(p.displayName ?: p.titleFa, to == p.code, { to = p.code }) }
        }
        HqButton("اخراج با گذرکلید", {
            action.run {
                val out = env.api.dismiss(e.code, reason.trim(), to) { a, t -> env.auth.stepUp(act, a, t) }
                env.cache.invalidate("employees", "companies", "stories", "work")
                toasts.info(buildString {
                    append("$name اخراج شد.")
                    if (out.workReturned > 0) append(" ${out.workReturned} کار باز برگشت.")
                    out.transferWork?.let { append(" کار انتقال دانش: $it") }
                })
                onChanged()
                onDismiss()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.DANGER, size = BtnSize.LG, icon = DivanIcon.SEAL, enabled = reason.isNotBlank(), loading = action.busy)
    }
}

/** The owner records a resolution from a message (§5.3 POST /resolutions): numbered, append-only, linked to the message. */
@Composable
fun RecordResolutionSheet(messageRef: String, body: String, onDismiss: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val action = rememberAction()
    val first = body.replace(Regex("[*_`#>]"), "").lines().firstOrNull { it.isNotBlank() }?.trim().orEmpty()
    var title by rememberSaveable { mutableStateOf(if (first.length > 80) first.take(77) + "…" else first) }
    var text by rememberSaveable { mutableStateOf(body) }
    HqSheet(onDismiss, "ثبت به‌عنوان مصوبه", sub = "از پیام $messageRef؛ بعد از ثبت عوض نمیشود.") {
        HqTextField(title, { title = it }, "عنوان", Modifier.fillMaxWidth(), maxLength = 200)
        HqTextField(text, { text = it }, "متن", Modifier.fillMaxWidth(), singleLine = false, minLines = 5, maxLength = 20000)
        HqButton("ثبت مصوبه", {
            action.run {
                val r = env.api.recordResolution(title.trim(), text.trim(), messageRef)
                env.cache.invalidate("resolutions")
                toasts.ok("مصوبه‌ی ${r.ref} ثبت شد.")
                onDismiss()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEAL, enabled = title.isNotBlank() && text.isNotBlank(), loading = action.busy)
    }
}

/** Writes a CSV (with a BOM so Excel opens Persian text) under cache/shared and offers it to any app (M14). */
fun shareCsv(context: Context, name: String, header: List<String>, rows: List<List<Any?>>) {
    fun cell(v: Any?) = "\"" + (v?.toString() ?: "").replace("\"", "\"\"") + "\""
    val dir = File(context.cacheDir, "shared").apply { mkdirs() }
    val file = File(dir, name)
    file.writeText("﻿" + (listOf(header) + rows).joinToString("\r\n") { r -> r.joinToString(",") { cell(it) } })
    val uri = FileProvider.getUriForFile(context, "${context.packageName}.files", file)
    val send = Intent(Intent.ACTION_SEND).setType("text/csv").putExtra(Intent.EXTRA_STREAM, uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    context.startActivity(Intent.createChooser(send, name))
}

@Composable
fun ExportButton(onClick: () -> Unit) = HqButton("Excel", onClick, size = BtnSize.SM, variant = BtnVariant.TEXT, icon = DivanIcon.DOWNLOAD)

internal fun nowIso(offsetMs: Long = 0): String = Instant.now().plusMillis(offsetMs).toString()

/** A new company straight away (§3.1), sealed on its code; founding from a repo or an idea stays in its own flow. */
@Composable
fun NewCompanySheet(onDismiss: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val action = rememberAction()
    var code by rememberSaveable { mutableStateOf("") }
    var nameFa by rememberSaveable { mutableStateOf("") }
    var nameEn by rememberSaveable { mutableStateOf("") }
    val codeOk = Regex("^[A-Z][A-Z0-9]{1,5}$").matches(code)
    HqSheet(onDismiss, "شرکت تازه", sub = "کد شرکت یک بار داده میشود و عوض نمیشود. نشانش بعداً اضافه میشود؛ تا آن موقع کد جای نشان را میگیرد.") {
        Text("کد (۲ تا ۶ حرف لاتین بزرگ)", style = Divan.type.caption, color = Divan.colors.textSecondary)
        CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
            HqTextField(code, { code = it.uppercase().filter { ch -> ch.isLetterOrDigit() } }, "NW", Modifier.fillMaxWidth(), maxLength = 6, figure = true)
        }
        HqTextField(nameFa, { nameFa = it }, "نام فارسی", Modifier.fillMaxWidth(), maxLength = 80)
        CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
            HqTextField(nameEn, { nameEn = it }, "English name", Modifier.fillMaxWidth(), maxLength = 80)
        }
        HqButton("بساز با گذرکلید", {
            action.run {
                val co = env.api.createCompany(com.coinepro.hq.core.net.CompanyIn(code, nameFa.trim(), nameEn.trim())) { a, t -> env.auth.stepUp(act, a, t) }
                env.cache.invalidate("companies")
                toasts.ok("${co.nameFa ?: co.code} ساخته شد.")
                onDismiss()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEAL, enabled = codeOk && nameFa.isNotBlank() && nameEn.isNotBlank(), loading = action.busy)
    }
}
