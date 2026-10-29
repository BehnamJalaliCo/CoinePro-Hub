package com.coinepro.hq.ui.work

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.OWNER_TZ
import com.coinepro.hq.core.net.ScheduleIn
import com.coinepro.hq.core.net.WorkCreate
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies

/** A new order (فرمان): the owner gives work to a company; its CEO routes it (contract §4). Recurring work
 *  carries an RRULE in the owner's zone. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NewOrderSheet(onDismiss: () -> Unit, company0: String? = null) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val companies = rememberCompanies()
    val action = rememberAction()
    var company by rememberSaveable { mutableStateOf(company0) }
    var title by rememberSaveable { mutableStateOf("") }
    var brief by rememberSaveable { mutableStateOf("") }
    var priority by rememberSaveable { mutableStateOf("P3") }
    var repeat by rememberSaveable { mutableStateOf("none") }

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true), containerColor = c.overlay) {
        Column(
            Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).imePadding().padding(horizontal = 16.dp).padding(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Text("فرمان تازه", style = Divan.type.h2)
            Text("به کدام شرکت؟ مدیرعاملش کار را به دپارتمان درست میسپارد.", style = Divan.type.caption, color = c.textMuted)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                companies.sortedBy { if (it.kind == "holding") 0 else 1 }.forEach { co ->
                    FilterChip(if (co.kind == "holding") "هلدینگ" else co.nameFa ?: co.code, company == co.code, { company = co.code })
                }
            }
            HqTextField(title, { title = it }, "عنوان کار", Modifier.fillMaxWidth(), maxLength = 200)
            HqTextField(brief, { brief = it }, "شرح: چه میخواهی، تا کی، با چه معیاری تمام است", Modifier.fillMaxWidth(), singleLine = false, minLines = 4)
            Text("اولویت", style = Divan.type.caption, color = c.textMuted)
            Segmented(listOf("P0", "P1", "P2", "P3", "P4").map { SegOption(it, it) }, priority, { priority = it }, Modifier.fillMaxWidth())
            Text("تکرار", style = Divan.type.caption, color = c.textMuted)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip("یک‌باره", repeat == "none", { repeat = "none" })
                FilterChip("هر روز ۸ صبح", repeat == "daily", { repeat = "daily" })
                FilterChip("هر شنبه", repeat == "weekly", { repeat = "weekly" })
            }
            if (priority == "P0") Text("P0 یعنی اضطراری: حتی با کلید توقف هم اجرا میشود. فقط برای اتفاق واقعی.", style = Divan.type.caption, color = c.warning)
            HqButton(
                "بفرست", {
                    action.run {
                        val rrule = when (repeat) { "daily" -> "FREQ=DAILY;BYHOUR=8;BYMINUTE=0"; "weekly" -> "FREQ=WEEKLY;BYDAY=SA;BYHOUR=8;BYMINUTE=0"; else -> null }
                        val w = env.api.createWork(
                            WorkCreate(
                                company = company!!, title = title.trim(), brief = brief.trim(), priority = priority,
                                kind = if (rrule != null) "recurring" else "one_off", schedule = rrule?.let { ScheduleIn(it, OWNER_TZ) },
                            ),
                        )
                        env.cache.invalidate("work", "planner", "companies")
                        toasts.ok("فرمان ${w.ref} رفت.")
                        onDismiss()
                        nav.go("work/${w.id}")
                    }
                },
                Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEND,
                enabled = company != null && title.isNotBlank(), loading = action.busy,
            )
        }
    }
}
