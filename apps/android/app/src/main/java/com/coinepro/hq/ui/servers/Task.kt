package com.coinepro.hq.ui.servers

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
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
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.net.HubServer
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.media.AttachMenu
import com.coinepro.hq.ui.media.AttachmentTray
import com.coinepro.hq.ui.media.rememberAttachments
import com.coinepro.hq.ui.media.rememberPickers
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.workshop.SpokenField

/** The roles that may drive Claude Code on a company's server by default (§26.2: the CEO, CTO / Lead Developer, DevOps and SRE). */
internal fun canDrive(kind: String, company: String, employeeCompany: String): Boolean = employeeCompany == company && kind in setOf("ceo", "manager")

/** «یک کار روی این سرور بسپار»: Claude Code on the server itself, driven by an agent of the company or by the owner. */
@Composable
fun ServerTaskSheet(servers: List<HubServer>, initial: HubServer?, onDismiss: () -> Unit) {
    com.coinepro.hq.ui.v14.HqSheet(onDismiss, "یک کار روی این سرور بسپار", sub = "Claude Code خود سرور، در ریپوی همان‌جا؛ زنده تماشا کن، راهنمایی کن یا متوقفش کن.") {
        ServerTaskContent(servers, initial, onDone = onDismiss)
    }
}

@Composable
fun ServerTaskContent(servers: List<HubServer>, initial: HubServer?, onDone: () -> Unit, title0: String = "", brief0: String = "", driver0: String? = null, cwd0: String? = null) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val employees = rememberQuery("employees:all", "employees", maxAgeMs = 60_000) { employees().items }
    val action = rememberAction()
    val files = rememberAttachments()
    val pick = rememberPickers(files)
    var menu by remember { mutableStateOf(false) }
    var chosen by rememberSaveable { mutableStateOf(initial?.id) }
    var driver by rememberSaveable { mutableStateOf(driver0) }
    var title by rememberSaveable { mutableStateOf(title0) }
    var brief by rememberSaveable { mutableStateOf(brief0) }
    val server = defaultServer(servers, chosen) ?: initial
    // §26.5: the repository folder the session runs in, from the server's own map; the only one is taken unless the owner says otherwise.
    val repos = server?.let { rememberServerMap(it.id).data?.repos }.orEmpty()
    var cwdPicked by rememberSaveable(server?.id) { mutableStateOf(cwd0) }
    val cwd = defaultRepo(repos.map { it.path }, cwdPicked)
    val drivers = employees.data.orEmpty().filter { it.status == "active" && server != null && canDrive(it.kind, server.company, it.company) }

    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        if (initial == null && servers.size > 1) {
            Text("کدام سرور", style = Divan.type.caption, color = c.textMuted)
            for (s in servers) {
                val on = server?.id == s.id
                val shape = RoundedCornerShape(12.dp)
                Row(
                    Modifier.fillMaxWidth().clip(shape).background(if (on) c.softGold else c.tile).then(if (on) Modifier.border(1.dp, c.goldInk, shape) else Modifier)
                        .clickable(role = Role.RadioButton) { chosen = s.id; driver = null; cwdPicked = null }.padding(horizontal = 12.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    CompanyMark(s.company, height = 14.dp, mono = true, ink = c.textSecondary)
                    Fig(s.name, Modifier.weight(1f), style = Divan.type.figure, color = c.textPrimary)
                    Fig(s.login, style = Divan.type.figureSmall, color = c.textMuted)
                }
            }
        } else if (server != null) {
            Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(horizontal = 12.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                CompanyMark(server.company, height = 14.dp, mono = true, ink = c.textSecondary)
                Fig(server.name, Modifier.weight(1f), style = Divan.type.figure, color = c.textPrimary)
                Fig(server.login, style = Divan.type.figureSmall, color = c.textMuted)
            }
        }
        if (server != null) {
            Text("چه کسی کار را ببرد", style = Divan.type.caption, color = c.textMuted)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip("خودم", driver == null, { driver = null })
                for (e in drivers) FilterChip(e.displayName ?: e.titleFa, driver == e.code, { driver = e.code })
            }
            Text(
                if (driver == null) "Claude را خودت راهنمایی میکنی؛ پیام‌هایت با همان نشست به Claude سرور میرسد."
                else "${drivers.firstOrNull { it.code == driver }?.let { it.displayName ?: it.titleFa } ?: ""} کار را میبرد و از پاکت همین شرکت خرج میکند؛ تو زنده میبینی و هر لحظه میتوانی بایستانی.",
                style = Divan.type.micro, color = c.textMuted,
            )
        }
        if (server != null && repos.isNotEmpty()) {
            Text("در کدام ریپو", style = Divan.type.caption, color = c.textMuted)
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                for (r in repos) {
                    val on = cwd == r.path
                    val shape = RoundedCornerShape(12.dp)
                    Row(
                        Modifier.fillMaxWidth().clip(shape).background(if (on) c.softGold else c.tile).then(if (on) Modifier.border(1.dp, c.goldInk, shape) else Modifier)
                            .clickable(role = Role.RadioButton, onClickLabel = r.path) { cwdPicked = r.path }.padding(horizontal = 12.dp, vertical = 9.dp),
                        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        DIcon(DivanIcon.CODE, size = 16.dp, tint = if (on) c.goldInk else c.textSecondary)
                        Column(Modifier.weight(1f)) {
                            Fig(r.path, style = Divan.type.figureSmall.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                            r.branch?.let { Fig(it, style = Divan.type.figureSmall, color = c.textMuted) }
                        }
                        if (r.dirty == true) Pill("تغییر ثبت‌نشده", Tone.WARN)
                    }
                }
            }
            Text("Claude در همین پوشه و زیر CLAUDE.md همان ریپو کار میکند.", style = Divan.type.micro, color = c.textMuted)
        }
        HqTextField(title, { title = it }, "عنوان؛ مثلاً: انتشار نسخه‌ی تازه‌ی API", Modifier.fillMaxWidth(), maxLength = 200)
        SpokenField("چه باید بشود و کی تمام است", brief, { brief = it }, "هدف، محدودیت‌ها، معیار تمام شدن؛ مثلاً «تست‌ها سبز، deploy، سلامت سایت را بسنج»")
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("عکس، فیلم یا PDF (اختیاری)", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.weight(1f))
            Box {
                HqButton("پیوست", { menu = true }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.ATTACH)
                AttachMenu(menu, { menu = false }, pick)
            }
        }
        AttachmentTray(files)
        Text("کد، commit، push، deploy و ریستارت آزاد است؛ اگر به یکی از شش کار ویرانگر برسد، همان‌جا میایستد و کارتش به کارتابل تو میاید.", style = Divan.type.micro, color = c.textMuted)
        HqButton(
            "شروع کن", {
                action.run(onError = { toasts.error(com.coinepro.hq.core.net.serverError(it)) }) {
                    val s = env.api.startServerSession(server!!, driver, title.trim(), brief.trim(), files.ids, cwd)
                    env.cache.invalidate("workshop", "servers")
                    onDone()
                    nav.go("workshop/${s.ref}")
                }
            },
            Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.CODE,
            enabled = server != null && title.trim().length >= 3 && brief.trim().length >= 3 && !files.uploading, loading = action.busy,
        )
    }
}

/** The repository a task runs in: the one picked if the map still has it, else the only one, else none (the hub picks). */
internal fun defaultRepo(paths: List<String>, picked: String?): String? = paths.firstOrNull { it == picked } ?: paths.singleOrNull()
