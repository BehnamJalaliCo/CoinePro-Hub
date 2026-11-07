package com.coinepro.hq.ui.office

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.officeFallback
import com.coinepro.hq.core.data.sortSessions
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.jWeekday
import com.coinepro.hq.core.net.Decision
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.Office
import com.coinepro.hq.core.net.OfficeMoney
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.IconBtn
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.timesFig
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.media.VoiceResult
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.session.SessionRow
import com.coinepro.hq.ui.v29.PreviewLine
import com.coinepro.hq.ui.v29.RouteEditor
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.rememberLongVoice
import com.coinepro.hq.ui.v29.rememberPreview
import com.coinepro.hq.ui.v29.served

// Contract §35.5 ⟨1.17⟩: the home is the owner's office, his place of work. Everything at hand: the command bar (every order opens its
// session at once), his open sessions (his turn first), the canvas of the companies linked to each other and to the hub, what waits for
// his seal (sealed in place), the money in one line, only what is critical, and suggestions on any subject («اجرا کن» opens a session).
// Nothing is fixed to one subject: no block of one working group's figures. A hub before ⟨1.17⟩ (no `/office`) is read through the
// older home and the cartable, in the same layout.

@Composable
fun rememberOffice() = rememberQuery("office", "office", "sessions", "decisions", "home", maxAgeMs = 20_000) { gated(HubFeature.SESSIONS) { office() } }

@Composable
fun OfficeScreen() {
    val c = Divan.colors
    val nav = LocalNav.current
    val q = rememberOffice()
    val sessionsOn = served(HubFeature.SESSIONS)
    val servicesOn = served(HubFeature.HUB_SERVICES)
    val playbooksOn = served(HubFeature.PLAYBOOKS)
    val companies = rememberCompanies()
    val presence = rememberQuery("presence", "presence") { presence() }
    // The older hub: the same office from `/home` and the pending cards.
    val home = if (!sessionsOn) com.coinepro.hq.ui.v29.rememberHome() else null
    val pending = if (!sessionsOn) rememberQuery("decisions:pending", "decisions") { decisions("pending") } else null
    val office: Office? = q.data ?: if (!sessionsOn && (home?.data != null || pending?.data != null)) officeFallback(home?.data, pending?.data?.items.orEmpty(), companies) else null
    val r = refresher(*listOfNotNull(q, presence, home, pending).toTypedArray())

    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item(key = "hello") {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(jWeekday(com.coinepro.hq.core.format.HqClock.now().toString()), style = Divan.type.caption, color = c.textMuted)
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("دفتر مدیر کل", style = Divan.type.h1, modifier = Modifier.weight(1f))
                    if (presence.data?.khalvat == true) Pill("خلوت؛ فقط فوری", Tone.LEARN, icon = DivanIcon.KHALVAT)
                    // ⟨1.20⟩ §38.3 the hub's services, one tap from the office.
                    // ⟨1.22⟩ §40 the working groups drawn from sessions, one tap from the office.
                    if (playbooksOn) com.coinepro.hq.designsystem.IconBtn(DivanIcon.DEPARTMENT, "کارگروه‌ها", { nav.go("playbooks") }, tint = c.textSecondary)
                    if (servicesOn) com.coinepro.hq.designsystem.IconBtn(DivanIcon.SERVER, "سرویس‌های هاب", { nav.go("services") }, tint = c.textSecondary)
                }
            }
        }
        when {
            office == null && (q.error ?: home?.error) != null -> item(key = "error") { ErrorBlock(q.error ?: home?.error, { r.refresh() }) }
            office == null -> item(key = "skeleton") { Column(verticalArrangement = Arrangement.spacedBy(16.dp)) { repeat(3) { Skeleton(Modifier.fillMaxWidth().height(if (it == 1) 300.dp else 140.dp), radius = 16.dp) } } }
            else -> {
                if (office.critical.isNotEmpty()) item(key = "critical") { com.coinepro.hq.ui.v29.CriticalCard(office.critical) }
                item(key = "command") { CommandBar() }
                item(key = "sessions") { SessionsCard(office, sessionsOn) }
                item(key = "canvas") { CanvasCard(office.canvas, editable = sessionsOn) }
                item(key = "approvals") { ApprovalsCard(office.approvals, office.approvalsTotal) }
                item(key = "money") { MoneyLine(office.money, sessionsOn) }
                if (office.suggestions.isNotEmpty()) {
                    item(key = "suggestions-title") { SectionTitle("پیشنهادها", note = "از کار واقعی، درباره‌ی هر چیزی؛ «اجرا کن» جلسه‌اش را باز میکند", icon = DivanIcon.STAR) }
                    for ((i, s) in office.suggestions.withIndex()) item(key = "sg-${s.id}") {
                        com.coinepro.hq.ui.v29.SuggestionCard(s, effective = i == 0 && s.kind == "effective", openSession = true)
                    }
                }
            }
        }
    }
}

// --------------------------------------------------------------- command --
/**
 * The command bar: the owner says or writes what he wants, the secretary's one line says where it goes, and «جلسه را باز کن» sends the
 * order and opens its session at once (§35.1: the holder speaks first there within seconds). [text0] opens it on words already there.
 */
@Composable
fun CommandBar(text0: String = "", preview0: com.coinepro.hq.core.net.OrderRoute29? = null) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val c = Divan.colors
    val action = rememberAction()
    var text by rememberSaveable { mutableStateOf(text0) }
    var voice by remember { mutableStateOf<VoiceResult?>(null) }
    var editing by remember { mutableStateOf(false) }
    val vh = rememberLongVoice("order") { r -> text = if (text.isBlank()) r.text else "${text.trimEnd()} ${r.text}"; voice = r }
    val v = vh.v
    val source = if (voice != null) "voice" else "text"
    val preview = rememberPreview(text, source, on = !v.active && text.isNotBlank(), preview0 = preview0)
    HqCard(Modifier.fillMaxWidth(), tahrir = true) {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                DIcon(DivanIcon.COMMAND, size = 18.dp, tint = c.goldInk)
                Text("فرمان تازه", style = Divan.type.bodyStrong, modifier = Modifier.weight(1f))
                Text("هر فرمان یک جلسه", style = Divan.type.micro, color = c.textMuted)
            }
            Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                HqTextField(text, { text = it }, "بگو یا بنویس چه میخواهی؛ درباره‌ی هر چیزی", Modifier.weight(1f), singleLine = false, minLines = 2, maxLength = 10000)
                Box(contentAlignment = Alignment.Center) {
                    if (v.transcribing) CircularProgressIndicator(Modifier.padding(10.dp), color = c.goldInk, strokeWidth = 2.dp)
                    else IconBtn(if (v.recording) DivanIcon.STOP else DivanIcon.MIC, if (v.recording) "تمام" else "بگو", { if (v.recording) v.finish() else vh.start() }, tint = c.goldInk, active = v.recording)
                }
            }
            if (v.recording || v.partial.isNotBlank()) Text(plain(v.partial.ifBlank { "میشنوم…" }), style = Divan.type.caption, color = c.textSecondary, maxLines = 2)
            v.unavailable?.let { Text(it, style = Divan.type.caption, color = c.warning) }
            PreviewLine(preview, onEdit = { editing = true })
            HqButton(
                "جلسه را باز کن", {
                    action.run {
                        val o = env.api.order(text.trim(), source, voice?.fileId, preview.route)
                        env.cache.invalidate("orders", "work", "sessions", "office", "home", "decisions", "inbox")
                        text = ""; voice = null; preview.route = null; preview.edited = false
                        nav.go("session/${o.ref}")
                    }
                },
                Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.SEND, enabled = text.trim().length >= 3 && !v.active, loading = action.busy,
            )
        }
    }
    if (editing) preview.route?.let { r -> RouteEditor(r, onDone = { preview.route = it; preview.edited = true; editing = false }, onCancel = { editing = false }) }
}

// -------------------------------------------------------------- sessions --
@Composable
private fun SessionsCard(office: Office, sessionsOn: Boolean) {
    val nav = LocalNav.current
    val c = Divan.colors
    val list = sortSessions(office.sessions)
    val mine = list.count { it.badge == "your_turn" }
    HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(start = 14.dp, end = 14.dp, top = 14.dp, bottom = 6.dp)) {
        SectionTitle("جلسه‌های باز", note = when {
            list.isEmpty() -> "جلسه‌ی بازی نیست"
            mine > 0 -> "$mine جلسه منتظر توست"
            else -> "${list.size} جلسه در جریان"
        }, icon = DivanIcon.MEETING) {
            if (sessionsOn) HqButton("همه", { nav.go("sessions") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.NEXT)
        }
        Column(Modifier.padding(top = 4.dp)) {
            if (list.isEmpty()) Text("فرمان تازه‌ای بده؛ همان لحظه جلسه‌اش این‌جا باز میشود.", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.padding(vertical = 10.dp))
            list.take(6).forEachIndexed { i, s ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                SessionRow(s) { nav.go("session/${s.ref}") }
            }
            if (list.size > 6) HqButton("${list.size - 6} جلسه‌ی دیگر", { nav.go("sessions") }, Modifier.fillMaxWidth(), variant = BtnVariant.TEXT, size = BtnSize.SM)
        }
    }
}

// ------------------------------------------------------------- approvals --
/** What waits for the owner's seal: the first few, sealed right here; the rest in the cartable. */
@Composable
private fun ApprovalsCard(items: List<Decision>, total: Int) {
    val nav = LocalNav.current
    val c = Divan.colors
    val companies = rememberCompanies()
    HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(start = 14.dp, end = 14.dp, top = 14.dp, bottom = 6.dp)) {
        SectionTitle("منتظر مُهر تو", note = if (total == 0) "چیزی منتظر نیست" else "$total مورد", icon = DivanIcon.SEAL) {
            HqButton("کارتابل", { nav.go("cartable") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.NEXT)
        }
        Column(Modifier.padding(top = 4.dp)) {
            if (items.isEmpty()) Text("هر کاری که مُهر تو را بخواهد این‌جا میاید.", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.padding(vertical = 10.dp))
            items.take(3).forEachIndexed { i, d ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                Column {
                    com.coinepro.hq.ui.cartable.DecisionRow(d, companies) { nav.go("cartable/${d.ref}") }
                    SealInPlace(d)
                }
            }
            if (total > 3) HqButton("${total - 3} مورد دیگر در کارتابل", { nav.go("cartable") }, Modifier.fillMaxWidth(), variant = BtnVariant.TEXT, size = BtnSize.SM)
        }
    }
}

/** One card's seal, without leaving the office (the passkey when the card asks for it, as in the cartable). */
@Composable
private fun SealInPlace(d: Decision) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val act = activity()
    val seal = rememberAction()
    var done by remember(d.ref) { mutableStateOf(false) }
    Row(Modifier.fillMaxWidth().padding(bottom = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
        if (done) Pill("مُهر خورد", Tone.POS, icon = DivanIcon.SEAL)
        else HqButton("مُهر بزن", {
            seal.run {
                val token = if (com.coinepro.hq.ui.cartable.needsStepUp(d)) env.auth.stepUp(act, com.coinepro.hq.core.net.sealAction(d), com.coinepro.hq.core.net.sealTarget(d)) else null
                env.api.approve(d.ref, null, token)
                done = true
                toasts.ok("مُهر خورد.")
                env.cache.invalidate("decisions", "inbox", "office")
            }
        }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.SEAL, loading = seal.busy)
        HqButton("ببین", { nav.go("cartable/${d.ref}") }, variant = BtnVariant.TEXT, size = BtnSize.SM)
    }
}

// ----------------------------------------------------------------- money --
/** The money in one line: this month's revenue, spend and its ceiling, in dollars (money is meant), and the advisor's plain line. */
@Composable
private fun MoneyLine(m: OfficeMoney, sessionsOn: Boolean) {
    val nav = LocalNav.current
    val c = Divan.colors
    if (!sessionsOn && m.lineFa.isBlank() && m.spendMonthUsd == 0.0 && m.revenueMonthUsd == null) return
    HqCard(Modifier.fillMaxWidth(), onClick = { nav.go("revenue-board") }, onClickLabel = "تابلوی پول") {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            MoneyFig("درآمد ماه", m.revenueMonthUsd?.let(::usdFig) ?: "—", Modifier.weight(1f), c.positive)
            MoneyFig("خرج ماه", usdFig(m.spendMonthUsd), Modifier.weight(1f), c.textPrimary)
            MoneyFig("سقف ماه", m.budgetMonthUsd?.let(::usdFig) ?: "بی‌سقف", Modifier.weight(1f), c.textSecondary, figure = m.budgetMonthUsd != null)
        }
        if (m.lineFa.isNotBlank()) Text(timesFig(m.lineFa), style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.padding(top = 10.dp))
    }
}

@Composable
private fun MoneyFig(label: String, value: String, modifier: Modifier, color: androidx.compose.ui.graphics.Color, figure: Boolean = true) {
    val c = Divan.colors
    Column(modifier, verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(label, style = Divan.type.micro, color = c.textMuted)
        if (figure && value != "—") Fig(value, style = Divan.type.figure.copy(fontWeight = FontWeight.SemiBold), color = color)
        else Text(value, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = color)
    }
}

/** «$1,240» — a whole dollar figure (cents under ten dollars). */
fun usdFig(v: Double): String = if (v < 10) String.format(java.util.Locale.US, "$%.2f", v) else "$" + String.format(java.util.Locale.US, "%,.0f", v)
