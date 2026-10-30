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
import com.coinepro.hq.core.data.PlayerOption
import com.coinepro.hq.core.format.OWNER_TZ
import com.coinepro.hq.core.net.ScheduleIn
import com.coinepro.hq.core.net.WorkCreate
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqTextField
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
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true), containerColor = Divan.colors.overlay) {
        Column(
            Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).imePadding().padding(horizontal = 16.dp).padding(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) { NewOrderContent(onDismiss, company0) }
    }
}

/** The order's form: the company, the title and brief, ⟨1.9⟩ who plays it, how urgent it is (in words, with its meaning), and whether it
 *  repeats. */
@Composable
fun NewOrderContent(
    onDismiss: () -> Unit, company0: String? = null, title0: String = "", priority0: String = com.coinepro.hq.core.format.DEFAULT_PRIORITY,
    player0: String = "auto",
) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val companies = rememberCompanies()
    val action = rememberAction()
    var company by rememberSaveable { mutableStateOf(company0) }
    var title by rememberSaveable { mutableStateOf(title0) }
    var brief by rememberSaveable { mutableStateOf("") }
    var priority by rememberSaveable { mutableStateOf(priority0) }
    var repeat by rememberSaveable { mutableStateOf("none") }
    // ⟨1.9⟩ §27.1: who plays it (the router by default), or the council of models (§27.2).
    var player by rememberSaveable { mutableStateOf(player0) }
    val option = PlayerOption.entries.firstOrNull { it.key == player } ?: PlayerOption.AUTO
    // A council can make images or a video instead of words: each player its own version, the owner picks one.
    var media by rememberSaveable { mutableStateOf<String?>(null) }
    Text("فرمان تازه", style = Divan.type.h2)
    Text("به کدام شرکت؟ مدیرعاملش کار را به دپارتمان درست میسپارد.", style = Divan.type.caption, color = c.textMuted)
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        companies.sortedBy { if (it.kind == "holding") 0 else 1 }.forEach { co ->
            FilterChip(if (co.kind == "holding") "هلدینگ" else co.nameFa ?: co.code, company == co.code, { company = co.code })
        }
    }
    HqTextField(title, { title = it }, "عنوان کار", Modifier.fillMaxWidth(), maxLength = 200)
    HqTextField(brief, { brief = it }, "شرح: چه میخواهی، تا کی، با چه معیاری تمام است", Modifier.fillMaxWidth(), singleLine = false, minLines = 4)
    PlayerPicker(option, { player = it.key }, Modifier.fillMaxWidth())
    if (option == PlayerOption.COUNCIL) Text("شورا چه بسازد؟ عکس و ویدیو: هر بازیکن نسخه‌ی خودش را میسازد و تو یکی را انتخاب میکنی.", style = Divan.type.caption, color = c.textMuted)
    if (option == PlayerOption.COUNCIL) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        FilterChip("نوشته", media == null, { media = null })
        FilterChip("عکس", media == "image", { media = "image" })
        FilterChip("ویدیو", media == "video", { media = "video" })
    }
    Text("چقدر عجله دارد؟", style = Divan.type.caption, color = c.textMuted)
    PriorityPicker(priority, { priority = it }, Modifier.fillMaxWidth())
    Text("تکرار", style = Divan.type.caption, color = c.textMuted)
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        FilterChip("یک‌باره", repeat == "none", { repeat = "none" })
        FilterChip("هر روز ۸ صبح", repeat == "daily", { repeat = "daily" })
        FilterChip("هر شنبه", repeat == "weekly", { repeat = "weekly" })
    }
    HqButton(
        "بفرست", {
            action.run {
                val rrule = when (repeat) { "daily" -> "FREQ=DAILY;BYHOUR=8;BYMINUTE=0"; "weekly" -> "FREQ=WEEKLY;BYDAY=SA;BYHOUR=8;BYMINUTE=0"; else -> null }
                val w = env.api.createWork(
                    WorkCreate(
                        company = company!!, title = title.trim(), brief = brief.trim(), priority = priority,
                        kind = if (rrule != null) "recurring" else "one_off", schedule = rrule?.let { ScheduleIn(it, OWNER_TZ) },
                        player = option.player, mode = option.mode, media = media.takeIf { option == PlayerOption.COUNCIL },
                    ),
                )
                // Followed at once: its stage changes are told even before the list is read again.
                env.orders.track(w)
                env.cache.invalidate("work", "planner", "companies")
                toasts.ok("فرمان ${w.ref} رفت؛ در «فرمان‌های من» مرحله‌به‌مرحله دنبالش کن.", "فرمان‌های من") { nav.go("orders") }
                onDismiss()
                nav.go("work/${w.id}")
            }
        },
        Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEND,
        enabled = company != null && title.isNotBlank(), loading = action.busy,
    )
}
