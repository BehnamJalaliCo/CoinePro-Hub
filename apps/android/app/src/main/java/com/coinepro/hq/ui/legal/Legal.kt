package com.coinepro.hq.ui.legal

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.actorFa
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.instant
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.format.until
import com.coinepro.hq.core.net.CaseEmail
import com.coinepro.hq.core.net.LegalCase
import com.coinepro.hq.core.net.draft
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.RichText
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.cartable.SealButton
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v16.Chip
import com.coinepro.hq.ui.v16.ChipRow
import com.coinepro.hq.ui.v16.prose
import com.coinepro.hq.ui.v17.ActorAvatar
import com.coinepro.hq.ui.v17.CoMark
import com.coinepro.hq.ui.v17.RefChip
import com.coinepro.hq.ui.v17.RefTone
import com.coinepro.hq.ui.v17.ScopeChips
import com.coinepro.hq.ui.v19.Block
import com.coinepro.hq.ui.v19.CASE_KIND
import com.coinepro.hq.ui.v19.CASE_STATUS
import com.coinepro.hq.ui.v19.ExactEmail
import com.coinepro.hq.ui.v19.TIMELINE
import com.coinepro.hq.ui.v19.media
import java.util.UUID

// The legal counsel (contract §22.4), mirroring apps/web/src/app/(app)/legal/page.tsx and components/v19/legal.tsx: the holding's cases
// LC-…, their timeline and deadlines, and every outgoing email sealed on the exact message (its digest). Nothing is ever sent by itself.

private val STATUSES = listOf<String?>(null, "waiting_owner", "open", "waiting_reply", "resolved", "closed")

/** مشاور حقوقی: the mailbox, the cases by company and status; a case opens on its own page. */
@Composable
fun LegalScreen() {
    val nav = LocalNav.current
    val c = Divan.colors
    var company by rememberSaveable { mutableStateOf<String?>(null) }
    var status by rememberSaveable { mutableStateOf<String?>(null) }
    var making by remember { mutableStateOf(false) }
    val q = rememberQuery("legal:cases:${company ?: ""}:${status ?: ""}", "legal") { cases(company, status).items }
    val r = refresher(q)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            PageHeader("مشاور حقوقی", eyebrow = "یک مشاور برای همه‌ی شرکت‌ها؛ فقط کانال رسمی، و هر ایمیل با مُهر تو روی همان پیام") {
                HqButton("پرونده‌ی تازه", { making = true }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.ADD)
                HqButton("رشته‌ی L", { nav.go("messages/L") }, size = BtnSize.SM, icon = DivanIcon.MESSAGES)
            }
        }
        item { Mailbox() }
        item { ScopeChips(company, { company = it }, allLabel = "همه") }
        item { ChipRow { for (s in STATUSES) FilterChip(s?.let { CASE_STATUS[it]?.fa } ?: "همه", status == s, { status = s }) } }
        val xs = q.data
        when {
            xs == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            xs == null -> item { Skeleton(Modifier.fillMaxWidth().height(240.dp), radius = 16.dp) }
            xs.isEmpty() -> item { HqCard(Modifier.fillMaxWidth()) { Empty("پرونده‌ای نیست", icon = DivanIcon.DECISION, body = "هر گیر حقوقی یا محدودیت پلتفرم را اینجا یا در رشته‌ی L بگو.") } }
            else -> item {
                HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(horizontal = 8.dp, vertical = 6.dp)) {
                    xs.forEachIndexed { i, x ->
                        if (i > 0) HorizontalDivider(color = c.lineDivider)
                        CaseRow(x) { nav.go("legal/${x.ref}") }
                    }
                }
            }
        }
    }
    if (making) HqSheet(
        { making = false }, "پرونده‌ی تازه",
        sub = "مشاور اول واقعیت‌ها و قاعده‌ی منتشرشده‌ی خود طرف مقابل را پیدا میکند؛ هر ایمیل یا فرم کارت مُهر توست. اگر کار وکیل انسانی باشد، همین را میگوید.",
    ) { NewCase { ref -> making = false; nav.go("legal/$ref") } }
}

/** The counsel's mailbox: whether the owner entered it (in the terminal, by hand); until then drafts are only cards. */
@Composable
private fun Mailbox() {
    val c = Divan.colors
    val q = rememberQuery("tools:accounts", "tools", maxAgeMs = 120_000) { serviceAccounts() }
    val all = q.data ?: return
    val mail = all.firstOrNull { it.key == "mail" }
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
        DIcon(DivanIcon.SEND, size = 14.dp, tint = c.textSecondary)
        Text("صندوق ایمیل مشاور:", style = Divan.type.caption, color = c.textSecondary)
        if (mail?.hasSecret == true) Pill("وصل", Tone.POS, dot = true) else Pill("وصل نیست؛ تا وصل نشود پیش‌نویس‌ها فقط کارت‌اند", Tone.WARN, dot = true)
        Text(buildAnnotatedString { append("ورود فقط با "); fig("make account-secret"); append(" روی سرور، به دست خودت.") }, style = Divan.type.micro, color = c.textMuted)
    }
}

@Composable
private fun CaseRow(x: LegalCase, onOpen: () -> Unit) {
    val c = Divan.colors
    val next = x.deadlines.minByOrNull { it.at }
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(if (x.status == "waiting_owner") c.softGold else androidx.compose.ui.graphics.Color.Transparent)
            .clickable(role = Role.Button, onClick = onOpen).padding(10.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            CoMark(x.company, height = 11.dp)
            Text(x.titleFa, Modifier.weight(1f), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 2, overflow = TextOverflow.Ellipsis)
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            LabelPill(CASE_STATUS[x.status], x.status)
            Fig(x.ref, style = Divan.type.figureSmall, color = c.textMuted)
            Text(CASE_KIND[x.kind] ?: x.kind, style = Divan.type.micro, color = c.textMuted)
            Text(ago(x.updatedAt), style = Divan.type.micro, color = c.textMuted)
        }
        next?.let {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                DIcon(DivanIcon.TIME, size = 12.dp, tint = c.warning)
                Text("${it.whatFa}، ${until(it.at)}", style = Divan.type.micro, color = c.warning, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}

/** One case, whole: the email waiting for the owner's seal first, then deadlines, the timeline and the email thread. */
@Composable
fun CaseScreen(ref: String) {
    val q = rememberQuery("legal:case:$ref", "legal") { legalCase(ref) }
    val r = refresher(q)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            val x = q.data
            when {
                x == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
                x == null -> Skeleton(Modifier.fillMaxWidth().height(420.dp), radius = 16.dp)
                else -> CaseDetail(x) { q.refresh() }
            }
        }
    }
}

@Composable
private fun CaseDetail(x: LegalCase, refresh: () -> Unit) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val companies = rememberCompanies()
    val action = rememberAction()
    var closing by remember { mutableStateOf(false) }
    val pending = x.emails.filter { it.state == "waiting_seal" }
    val thread = x.emails.filter { it.state != "waiting_seal" }
    Column(verticalArrangement = Arrangement.spacedBy(18.dp)) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(2.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                CoMark(x.company, height = 11.dp)
                Text(companyOf(companies, x.company).nameFa, style = Divan.type.micro, color = c.textMuted)
                Fig(x.ref, style = Divan.type.figureSmall, color = c.textMuted)
                Text(CASE_KIND[x.kind] ?: x.kind, style = Divan.type.micro, color = c.textMuted)
            }
            Text(x.titleFa, style = Divan.type.h2, color = c.textPrimary)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                LabelPill(CASE_STATUS[x.status], x.status)
                Text(buildAnnotatedString { append("طرف مقابل: "); append(prose(x.counterpart.name)) }, style = Divan.type.caption, color = c.textSecondary)
                x.counterpart.address?.let { Fig(it, style = Divan.type.figureSmall, color = c.textMuted) }
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                ActorAvatar(x.openedBy, size = 18.dp)
                Text("باز شده‌ی ${actorFa(x.openedBy)}، ${ago(x.createdAt)}", style = Divan.type.caption, color = c.textSecondary)
            }
            x.briefMd?.let { Text(prose(it), Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), style = Divan.type.small, color = c.textPrimary) }
        }
        for (e in pending) EmailToSeal(e, x, refresh)
        if (x.deadlines.isNotEmpty()) Block("مهلت‌ها") {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                for (d in x.deadlines.sortedBy { it.at }) {
                    val soon = instant(d.at)?.let { it.toEpochMilli() - HqClock.millis() < 48 * 3_600_000L } == true
                    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(horizontal = 12.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            DIcon(DivanIcon.TIME, size = 14.dp, tint = c.textSecondary)
                            Text(prose(d.whatFa), Modifier.weight(1f), style = Divan.type.caption, color = c.textPrimary)
                        }
                        Text("${jDateTime(d.at)}، ${until(d.at)}", style = Divan.type.micro, color = if (soon) c.warning else c.textMuted)
                    }
                }
            }
        }
        Block("روند پرونده") {
            Column {
                x.timeline.forEachIndexed { i, t ->
                    val k = TIMELINE[t.kind] ?: TIMELINE.getValue("note")
                    val rail = c.lineDivider
                    val joined = i < x.timeline.lastIndex
                    // The rail: a marker per entry, joined to the next (drawn at the reading start, whichever side that is).
                    Row(
                        Modifier.drawBehind {
                            if (joined) {
                                val cx = if (layoutDirection == LayoutDirection.Rtl) size.width - 10.dp.toPx() else 10.dp.toPx()
                                drawLine(rail, Offset(cx, 22.dp.toPx()), Offset(cx, size.height), 1.dp.toPx())
                            }
                        },
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        Box(Modifier.size(20.dp).clip(CircleShape).background(c.card).border(1.5.dp, c.lineStrong, CircleShape), contentAlignment = Alignment.Center) {
                            DIcon(k.icon, size = 11.dp, tint = c.goldInk)
                        }
                        Column(Modifier.weight(1f).padding(bottom = 12.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(2.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                                Text(k.fa, style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                                Text(jDateTime(t.at), style = Divan.type.micro, color = c.textMuted)
                                t.ref?.let { RefChip(it, tone = RefTone.NEUTRAL) }
                            }
                            RichText(t.summaryFa, style = Divan.type.small, color = c.textPrimary)
                        }
                    }
                }
            }
        }
        if (thread.isNotEmpty()) Block("رشته‌ی ایمیل") { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) { for (e in thread) EmailItem(e) } }
        // ⟨1.7⟩ §23.5: the case's legal holds in the archive; a new one is placed tied to this case.
        com.coinepro.hq.ui.archive.CaseHolds(x.ref)
        HorizontalDivider(color = c.lineDivider)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            HqButton("در رشته‌ی L بپرس", { nav.go("messages/L") }, icon = DivanIcon.MESSAGES)
            if (x.status != "closed") HqButton("بستن پرونده", { closing = true }, variant = BtnVariant.GHOST, icon = DivanIcon.CLOSE)
        }
    }
    if (closing) AlertDialog(
        onDismissRequest = { closing = false },
        containerColor = c.overlay,
        title = { Text("بستن پرونده", style = Divan.type.h3) },
        text = { Text("مشاور دیگر روی آن کار نمیکند؛ جواب تازه‌ای که برسد در روند پرونده ثبت میشود ولی او را بیدار نمیکند. تاریخچه میماند.", style = Divan.type.small, color = c.textSecondary) },
        confirmButton = {
            HqButton("ببند", {
                action.media(toasts) {
                    env.api.closeCase(x.ref)
                    env.cache.invalidate("legal", "threads")
                    closing = false
                    refresh()
                    toasts.info("پرونده بسته شد؛ تاریخچه‌اش میماند.")
                }
            }, variant = BtnVariant.PRIMARY, loading = action.busy)
        },
        dismissButton = { HqButton("نه", { closing = false }, variant = BtnVariant.GHOST) },
    )
}

/** The exact message the seal is bound to (§22.4): approving its `email_send` card sends exactly this once; returning or refusing it
 *  reopens the case. */
@Composable
private fun EmailToSeal(e: CaseEmail, x: LegalCase, refresh: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val companies = rememberCompanies()
    val co = companyOf(companies, x.company)
    val seal = rememberAction()
    val other = rememberAction()
    var mode by remember { mutableStateOf<String?>(null) }
    var note by rememberSaveable { mutableStateOf("") }
    fun done() { env.cache.invalidate("legal", "threads", "messages", "decisions", "inbox"); refresh() }
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(c.softGold).border(1.dp, c.lineTahrir, RoundedCornerShape(16.dp)).padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DIcon(DivanIcon.SEAL, size = 18.dp, tint = c.goldInk)
            Text("ایمیل منتظر مُهر تو", Modifier.weight(1f), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
            e.decisionRef?.let { RefChip(it) }
        }
        ExactEmail(e.draft())
        val ref = e.decisionRef
        if (ref != null) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            SealButton(x.company, co.nameFa, co.nameEn, co.holding, busy = seal.busy, size = 64.dp) {
                seal.media(toasts) {
                    // Bound to the message digest, not to the card's ref (§22.6).
                    val token = env.auth.stepUp(act, "decision.approve", e.digest.ifBlank { ref })
                    env.api.approve(ref, null, token)
                    done()
                    toasts.ok("مُهر خورد؛ دقیقاً همین پیام یک بار فرستاده شد.")
                }
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                HqButton("برگشت با یادداشت", { mode = "return" }, size = BtnSize.SM, icon = DivanIcon.BACK)
                HqButton("نفرست", { mode = "reject" }, size = BtnSize.SM, variant = BtnVariant.DANGER, icon = DivanIcon.REJECT)
            }
        }
    }
    mode?.let { m ->
        AlertDialog(
            onDismissRequest = { mode = null },
            containerColor = c.overlay,
            title = { Text(if (m == "return") "برگشت به مشاور" else "این ایمیل فرستاده نشود", style = Divan.type.h3) },
            text = { HqTextField(note, { note = it }, if (m == "return") "چه چیزی عوض شود؟ (لازم)" else "دلیل (اختیاری)", Modifier.fillMaxWidth(), singleLine = false, minLines = 3, maxLength = 2000) },
            confirmButton = {
                HqButton(if (m == "return") "بفرست" else "نفرست", {
                    val ref = e.decisionRef ?: return@HqButton
                    other.media(toasts) {
                        if (m == "return") env.api.returnDecision(ref, note.trim()) else env.api.reject(ref, note.trim().ifEmpty { null }, null)
                        done()
                        mode = null; note = ""
                        toasts.info(if (m == "return") "برگشت؛ مشاور پیش‌نویس تازه مینویسد و کارت تازه میآید." else "رد شد؛ چیزی فرستاده نشد.")
                    }
                }, variant = if (m == "return") BtnVariant.PRIMARY else BtnVariant.DANGER, enabled = m != "return" || note.isNotBlank(), loading = other.busy)
            },
            dismissButton = { HqButton("انصراف", { mode = null }, variant = BtnVariant.GHOST) },
        )
    }
}

/** One message of the thread: out or in, its subject; open, the addresses, the Message-ID and the body. */
@Composable
private fun EmailItem(e: CaseEmail) {
    val c = Divan.colors
    var open by rememberSaveable(e.id) { mutableStateOf(false) }
    val out = e.direction == "out"
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(Modifier.fillMaxWidth().clickable(role = Role.Button, onClickLabel = if (open) "بستن" else "باز کردن") { open = !open }, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DIcon(if (out) DivanIcon.SEND else DivanIcon.MESSAGES, size = 15.dp, tint = if (out) c.goldInk else c.lapis)
            Text(if (out) "رفت" else "آمد", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
            Fig(e.subject, Modifier.weight(1f), style = Divan.type.figureSmall, color = c.textSecondary)
            com.coinepro.hq.designsystem.Chevron(open, tint = c.textMuted)
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(jDateTime(e.at), style = Divan.type.micro, color = c.textMuted)
            when (e.state) {
                "rejected" -> Pill("فرستاده نشد", Tone.NEUTRAL)
                "superseded" -> Pill("جایگزین شد", Tone.NEUTRAL)
            }
        }
        com.coinepro.hq.designsystem.Expand(open) { Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Fig("${e.from} → ${e.to.joinToString(", ")}" + (e.messageId?.let { " · $it" } ?: ""), style = Divan.type.figureSmall, color = c.textMuted, maxLines = 3)
            Fig(e.bodyMd.replace("**", ""), style = Divan.type.figureSmall.copy(lineHeight = Divan.type.small.lineHeight), color = c.textPrimary, maxLines = 60)
            if (e.decisionRef != null) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("با مُهر", style = Divan.type.micro, color = c.textMuted)
                RefChip(e.decisionRef)
            } else if (!out) Text("با کد خوانده و ماسک شد؛ مشاور بیدار شد.", style = Divan.type.micro, color = c.textMuted)
        } }
    }
}

/** A new case for any company or the holding: its kind, a title and what happened; screenshots go to thread L. */
@Composable
fun NewCase(onMade: (String) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    val companies = rememberCompanies()
    val key = remember { UUID.randomUUID().toString() }
    var company by rememberSaveable { mutableStateOf<String?>(null) }
    var kind by rememberSaveable { mutableStateOf("platform_restriction") }
    var title by rememberSaveable { mutableStateOf("") }
    var brief by rememberSaveable { mutableStateOf("") }
    val ok = company != null && title.trim().length >= 4 && brief.trim().length >= 10
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("برای کدام شرکت", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            ChipRow {
                for (co in companies) Chip(company == co.code, { company = co.code }) { ink ->
                    CoMark(co.code, height = 11.dp, ink = ink)
                    Text(co.nameFa ?: co.code, style = Divan.type.small, color = ink, maxLines = 1)
                }
            }
        }
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("نوع", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                for ((k, fa) in CASE_KIND) FilterChip(fa, kind == k, { kind = k })
            }
        }
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("عنوان", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            HqTextField(title, { title = it }, "مثلاً: محدودیت پاسخ به دایرکت اینستاگرام FX", Modifier.fillMaxWidth(), maxLength = 120)
        }
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("چه شده", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            HqTextField(brief, { brief = it }, "واقعیت‌ها، تاریخ، متن دقیق اعلان اگر هست", Modifier.fillMaxWidth(), singleLine = false, minLines = 5, maxLength = 5000)
            Text("اسکرین‌شات را در رشته‌ی L بفرست؛ مشاور آن را به پرونده میبندد.", style = Divan.type.micro, color = c.textMuted)
        }
        HqButton("باز کن", {
            val co = company ?: return@HqButton
            action.media(toasts) {
                val x = env.api.openCase(co, title.trim(), kind, brief.trim(), emptyList(), key)
                env.cache.invalidate("legal", "threads")
                toasts.ok("پرونده‌ی ${x.ref} باز شد؛ مشاور حقوقی بیدار شد.")
                onMade(x.ref)
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.SEND, enabled = ok, loading = action.busy)
    }
}

/** A §22 Markdown body in a tile (agent-written; refs and Latin kept Latin). */
@Composable
internal fun MdTile(text: String) {
    Md(text, Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(Divan.colors.tile).padding(12.dp), color = Divan.colors.textPrimary)
}
