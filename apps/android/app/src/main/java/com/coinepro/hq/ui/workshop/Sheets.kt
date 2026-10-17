package com.coinepro.hq.ui.workshop

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.until
import com.coinepro.hq.core.media.clock
import com.coinepro.hq.core.net.GrantIn
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.IconBtn
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.media.AttachMenu
import com.coinepro.hq.ui.media.AttachmentTray
import com.coinepro.hq.ui.media.Waveform
import com.coinepro.hq.ui.media.rememberAttachments
import com.coinepro.hq.ui.media.rememberPickers
import com.coinepro.hq.ui.media.rememberVoiceInput
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import java.time.Instant
import java.time.temporal.ChronoUnit

/** A choice row: company mark, title, a second line; gold when chosen. */
@Composable
private fun ChoiceRow(company: String, title: String, sub: String, selected: Boolean, trailing: String? = null, onClick: () -> Unit) {
    val c = Divan.colors
    val shape = RoundedCornerShape(12.dp)
    Row(
        Modifier.fillMaxWidth().clip(shape).background(if (selected) c.softGold else c.tile)
            .then(if (selected) Modifier.border(1.dp, c.goldInk, shape) else Modifier)
            .clickable(role = Role.RadioButton, onClick = onClick).padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        CompanyMark(company, height = 15.dp, mono = true, ink = c.textSecondary)
        Column(Modifier.weight(1f)) {
            Text(title, style = Divan.type.small, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Fig(sub, style = Divan.type.figureSmall, color = c.textMuted)
        }
        trailing?.let { Fig(it, style = Divan.type.figureSmall, color = c.textMuted) }
    }
}

/** A multi-line field the owner can also speak into: the exact text is appended for them to read and fix. */
@Composable
fun SpokenField(label: String, value: String, onChange: (String) -> Unit, placeholder: String) {
    val c = Divan.colors
    val vh = rememberVoiceInput("note") { r -> onChange(if (value.isBlank()) r.text else "${value.trimEnd()} ${r.text}") }
    val v = vh.v
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(label, style = Divan.type.caption, color = c.textMuted, modifier = Modifier.weight(1f))
            when {
                v.recording -> {
                    Waveform(v.levels.takeLast(16), Modifier.height(20.dp))
                    Fig(clock(v.elapsed), Modifier.padding(horizontal = 6.dp), style = Divan.type.figureSmall, color = c.textSecondary)
                    IconBtn(DivanIcon.CLOSE, "لغو ضبط", v::cancel)
                    HqButton("تمام", v::finish, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.STOP)
                }
                v.transcribing -> Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    CircularProgressIndicator(Modifier.height(14.dp), color = c.goldInk, strokeWidth = 2.dp)
                    Text("در حال نوشتن…", style = Divan.type.caption, color = c.textSecondary)
                }
                else -> HqButton("بگو", vh.start, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.MIC)
            }
        }
        HqTextField(value, onChange, placeholder, Modifier.fillMaxWidth(), singleLine = false, minLines = 4, maxLength = 10_000)
    }
}

/** The owner's grant (contract §17.3): which repository, which actions, who drives, how much, until when. 🔏 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun GrantSheet(initial: String?, onDismiss: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val workspaces = rememberWorkspaces()
    val employees = rememberQuery("employees:all", "employees", maxAgeMs = 60_000) { employees().items }
    val action = rememberAction()
    var ws by rememberSaveable { mutableStateOf(initial) }
    var actions by remember { mutableStateOf(ACTION_FA.keys.toList()) }
    var driver by rememberSaveable { mutableStateOf<String?>(null) }
    var budget by rememberSaveable { mutableStateOf(10) }
    var days by rememberSaveable { mutableStateOf(3L) }
    val company = ws?.let { companyOf(workspaces.data, it) }
    // Managers and the chief advisor drive sessions (owner, 2026-10-17); the owner only grants.
    val drivers = employees.data.orEmpty().filter { it.status == "active" && ((it.company == company && it.kind in setOf("manager", "ceo")) || it.kind == "advisor") }

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true), containerColor = c.overlay) {
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).imePadding().padding(horizontal = 16.dp).padding(bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text("مجوز تازه برای کارگاه", style = Divan.type.h2)
            Text("تو فقط اجازه میدهی؛ مدیرها و مشاور کل کار را میبرند. ادغام و انتشار همیشه با مُهر خودت.", style = Divan.type.caption, color = c.textMuted)
            Text("کدام ریپو", style = Divan.type.caption, color = c.textMuted)
            for (w in workspaces.data.orEmpty().filter { it.status == "active" }) {
                ChoiceRow(w.company, w.titleFa, w.repo, ws == w.code) { ws = w.code; driver = null }
            }
            Text("چه کارهایی", style = Divan.type.caption, color = c.textMuted)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                for ((a, fa) in ACTION_FA) FilterChip(fa, a in actions, { if (a != "read") actions = if (a in actions) actions - a else actions + a })
            }
            Text("push فقط به شاخه‌های جدا؛ هر push و PR باز هم اجازه‌ی جدای تو را میخواهد.", style = Divan.type.micro, color = c.textMuted)
            if (ws != null) {
                Text("چه کسی کار را ببرد", style = Divan.type.caption, color = c.textMuted)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip("خودم، از همین‌جا", driver == null, { driver = null })
                    for (e in drivers) FilterChip(e.titleFa + if (e.company != company) " (${e.company})" else "", driver == e.code, { driver = e.code })
                }
            }
            Text("سقف هزینه", style = Divan.type.caption, color = c.textMuted)
            Segmented(listOf(5, 10, 25, 50).map { SegOption(it, "$$it") }, budget, { budget = it }, Modifier.fillMaxWidth())
            Text("تا کی", style = Divan.type.caption, color = c.textMuted)
            Segmented(listOf(SegOption(1L, "۱ روز"), SegOption(3L, "۳ روز"), SegOption(7L, "۱ هفته"), SegOption(30L, "۱ ماه")), days, { days = it }, Modifier.fillMaxWidth())
            HqButton(
                "با گذرکلید مجوز بده", {
                    action.run {
                        val body = GrantIn(ws!!, actions, driver, budget.toDouble(), Instant.now().plus(days, ChronoUnit.DAYS).toString())
                        val g = env.api.createGrant(body) { target -> env.auth.stepUp(act, "workshop.grant", target) }
                        env.cache.invalidate("workshop")
                        toasts.ok("مجوز ${g.ref} صادر شد.")
                        onDismiss()
                    }
                },
                Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEAL, enabled = ws != null, loading = action.busy,
            )
        }
    }
}

/** Open a session under an active grant. The brief can be spoken; photos and films help explain it. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NewSessionSheet(onDismiss: () -> Unit) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val c = Divan.colors
    val grants = rememberGrants()
    val workspaces = rememberWorkspaces()
    val action = rememberAction()
    val files = rememberAttachments()
    val pick = rememberPickers(files)
    var menu by remember { mutableStateOf(false) }
    var grant by rememberSaveable { mutableStateOf<String?>(null) }
    var title by rememberSaveable { mutableStateOf("") }
    var brief by rememberSaveable { mutableStateOf("") }
    val active = grants.data.orEmpty().filter { it.revokedAt == null }
    val chosen = active.firstOrNull { it.ref == grant } ?: active.singleOrNull()

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true), containerColor = c.overlay) {
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).imePadding().padding(horizontal = 16.dp).padding(bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text("جلسه‌ی تازه در کارگاه", style = Divan.type.h2)
            Text("زیر یکی از مجوزهای فعال؛ راننده‌ی همان مجوز کار را میبرد.", style = Divan.type.caption, color = c.textMuted)
            if (active.isEmpty()) Text("مجوز فعالی نیست؛ اول از «مجوز تازه» یکی بده.", style = Divan.type.small, color = c.textMuted)
            for (g in active) {
                val w = workspaces.data?.firstOrNull { it.code == g.workspace }
                ChoiceRow(companyOf(workspaces.data, g.workspace), w?.titleFa ?: g.workspace, "${g.driver?.displayFa ?: "خودت"} · $${g.budgetUsd.toInt()} · ${until(g.expiresAt)}", chosen?.ref == g.ref, g.ref) { grant = g.ref }
            }
            HqTextField(title, { title = it }, "عنوان؛ مثلاً: کندی صفحه‌ی ثبت‌نام", Modifier.fillMaxWidth(), maxLength = 200)
            SpokenField("چه باید بشود و کی تمام است", brief, { brief = it }, "هدف، محدودیت‌ها و معیار تمام شدن")
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("عکس، فیلم یا PDF برای روشن‌تر شدن (اختیاری)", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.weight(1f))
                androidx.compose.foundation.layout.Box {
                    HqButton("پیوست", { menu = true }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.ATTACH)
                    AttachMenu(menu, { menu = false }, pick)
                }
            }
            AttachmentTray(files)
            HqButton(
                "شروع کن", {
                    action.run {
                        val s = env.api.createSession(chosen!!.ref, title.trim(), brief.trim(), files.ids)
                        env.cache.invalidate("workshop")
                        onDismiss()
                        nav.go("workshop/${s.ref}")
                    }
                },
                Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.CODE,
                enabled = chosen != null && title.trim().length >= 3 && brief.trim().length >= 3 && !files.uploading, loading = action.busy,
            )
        }
    }
}
