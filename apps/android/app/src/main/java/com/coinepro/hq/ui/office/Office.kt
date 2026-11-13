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
import com.coinepro.hq.designsystem.Text
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
import com.coinepro.hq.core.net.orderWithPace
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
    // ⟨1.24⟩ §42 the holding live: the pulse, the companies' live cards and the token meter (a hub without `/live/summary` leaves them out).
    val liveOn = served(HubFeature.LIVE)
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
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("دفتر مدیر کل", style = Divan.type.h1, modifier = Modifier.weight(1f))
                    // ⟨1.20⟩ §38.3 the hub's services, ⟨1.22⟩ §40 the working groups, ⟨1.24⟩ the holding's live network map: one tap from the
                    // office. ⟨1.0.1⟩ each sign carries its name.
                    com.coinepro.hq.ui.look.NamedIcon(DivanIcon.GLOBE, "شبکه", { nav.go("network") })
                    if (playbooksOn) com.coinepro.hq.ui.look.NamedIcon(DivanIcon.DEPARTMENT, "کارگروه‌ها", { nav.go("playbooks") })
                    if (servicesOn) com.coinepro.hq.ui.look.NamedIcon(DivanIcon.SERVER, "سرویس‌ها", { nav.go("services") })
                }
                if (presence.data?.khalvat == true) Pill("خلوت؛ فقط فوری", Tone.LEARN, icon = DivanIcon.KHALVAT)
                // ⟨1.36⟩ §58.5 the publish desk is its own page: the office keeps ONE line to it, at its head (nothing on a hub without it)
                com.coinepro.hq.ui.look.DeskLine()
            }
        }
        when {
            office == null && (q.error ?: home?.error) != null -> item(key = "error") { ErrorBlock(q.error ?: home?.error, { r.refresh() }) }
            office == null -> item(key = "skeleton") { Column(verticalArrangement = Arrangement.spacedBy(16.dp)) { repeat(3) { Skeleton(Modifier.fillMaxWidth().height(if (it == 1) 300.dp else 140.dp), radius = 16.dp) } } }
            else -> {
                // ⟨1.0.1⟩ C3.1: what waits for the owner first, answered in place; then the pulse in one row, the one-row command entry,
                // the sessions as cards; the rest as it was.
                item(key = "turn") { com.coinepro.hq.ui.look.TurnRow(office) }
                if (office.critical.isNotEmpty()) item(key = "critical") { com.coinepro.hq.ui.v29.CriticalCard(office.critical) }
                // ⟨1.24⟩ OF-1: is my holding working, and is anything waiting for me.
                if (liveOn) item(key = "pulse") { com.coinepro.hq.ui.live.OfficePulse(waiting = com.coinepro.hq.core.data.turnCount(office)) }
                item(key = "command") { com.coinepro.hq.ui.look.CommandRow() }
                item(key = "sessions") { SessionsBlock(office, sessionsOn) }
                // ⟨1.24⟩ CO-1: every company alive, working, healthy and what it costs today, the busiest first.
                if (liveOn) item(key = "live-companies") { com.coinepro.hq.ui.live.LiveCompaniesCard() }
                item(key = "canvas") { CanvasCard(office.canvas, editable = sessionsOn) }
                // ⟨1.24⟩ MO-1: the holding's real cost, moving as it is spent.
                if (liveOn) item(key = "tokens") { com.coinepro.hq.ui.live.TokenMeter() }
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

// -------------------------------------------------------------- sessions --
/** ⟨1.0.1⟩ The open sessions as cards with three states only («منتظر تو», «در کار», «تمام»), each opening out of itself (M14). */
@Composable
private fun SessionsBlock(office: Office, sessionsOn: Boolean) {
    val nav = LocalNav.current
    val list = sortSessions(office.sessions)
    val waiting = list.count { com.coinepro.hq.core.data.state3(it.badge) == "waiting" }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SectionTitle("جلسه‌ها", note = when {
            waiting > 0 -> "${com.coinepro.hq.core.data.faNum(waiting)} جلسه منتظر توست"
            else -> "هر فرمان یک جلسه است"
        }) {
            if (sessionsOn) HqButton("همه و بایگانی", { nav.go("sessions") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.NEXT)
        }
        com.coinepro.hq.ui.look.SessionCards(office.sessions, onMore = { nav.go("sessions") }) { s -> nav.go("session/${s.ref}") }
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
