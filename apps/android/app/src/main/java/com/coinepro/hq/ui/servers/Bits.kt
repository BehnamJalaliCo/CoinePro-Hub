package com.coinepro.hq.ui.servers

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.data.coState
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.actorFa
import com.coinepro.hq.core.format.agentKindOf
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.deptOf
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.net.CallOutcome
import com.coinepro.hq.core.net.ServerCallRow
import com.coinepro.hq.core.net.Decision
import com.coinepro.hq.core.net.HubServer
import com.coinepro.hq.core.net.SealCard
import com.coinepro.hq.core.net.ServerMap
import com.coinepro.hq.core.net.ServerMaps
import com.coinepro.hq.core.net.DiskUsage
import com.coinepro.hq.core.net.callRow
import com.coinepro.hq.core.net.sealCardOf
import com.coinepro.hq.designsystem.Avatar
import com.coinepro.hq.designsystem.BarTone
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.MeterBar
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.RichText
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.QueryHandle
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery

// ⟨1.8⟩ Contract §26: the companies' servers under the holding's control, each through its own `hq-runner`. The pieces every server page
// shares.

data class ServerStateFa(val fa: String, val tone: Tone, val icon: DivanIcon? = null, val live: Boolean = false)

/** §26.4's runner states. */
val SERVER_STATE = mapOf(
    "pending" to ServerStateFa("منتظر runner", Tone.GOLD, DivanIcon.TIME),
    "online" to ServerStateFa("آنلاین", Tone.POS, live = true),
    "offline" to ServerStateFa("آفلاین", Tone.NEG, DivanIcon.OFFLINE),
    "revoked" to ServerStateFa("باطل‌شده", Tone.NEUTRAL, DivanIcon.CLOSE),
)

/** The owner's monospace for a server's own text (commands, output): columns line up, Latin stays Latin, left to right. */
val Mono = TextStyle(fontFamily = FontFamily.Monospace, fontSize = 12.5.sp, lineHeight = 18.sp)

@Composable
fun rememberServers(): QueryHandle<List<com.coinepro.hq.core.net.HubServer>> = rememberQuery("servers", "servers", maxAgeMs = 30_000) { servers() }

@Composable
fun rememberServerMap(id: String): QueryHandle<ServerMap?> = rememberQuery("server:map:$id", "servers", maxAgeMs = 60_000) { serverMap(id) }

/**
 * The owner's rule (2026-10-30): a server is called by its company — «تریدیار», «کوینه‌پرو FX» — never by its hostname or address. When the
 * company has more than one server, the server's own name follows, small: «تریدیار · ty-web». Hostname and address are details of the
 * server's own page.
 */
data class ServerName(val company: String, val companyFa: String, val server: String?) {
    val text: String get() = if (server == null) companyFa else "$companyFa · $server"
}

/** [siblings]: how many servers the company has (the revoked count too: their history is still listed). */
fun serverNameOf(company: String, companyFa: String?, server: String?, siblings: Int): ServerName =
    ServerName(company, companyFa?.takeIf { it.isNotBlank() } ?: company, server?.takeIf { siblings > 1 && it.isNotBlank() })

/** The name of [company]'s server [server], from the companies and the servers the app already reads. */
@Composable
fun rememberServerName(company: String, server: String?): ServerName {
    val companies = rememberCompanies()
    val list = rememberServers().data
    return serverNameOf(company, com.coinepro.hq.ui.companyOf(companies, company).nameFa, server, list?.count { it.company == company } ?: 1)
}

/** A server's name as a title: its company's mark and name, the server's own name after it, small, when the company has several. */
@Composable
fun ServerTitle(
    name: ServerName,
    modifier: Modifier = Modifier,
    style: TextStyle = Divan.type.bodyStrong,
    color: Color = Divan.colors.textPrimary,
    markHeight: androidx.compose.ui.unit.Dp = 14.dp,
    mark: Boolean = true,
) {
    val c = Divan.colors
    Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        if (mark) CompanyMark(name.company, height = markHeight, mono = true, ink = c.textSecondary)
        Text(name.companyFa, style = style, color = color, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
        name.server?.let {
            Text("·", style = Divan.type.caption, color = c.textMuted)
            Fig(it, style = Divan.type.figureSmall, color = c.textMuted)
        }
    }
}

/** Whether the company's kill switch (or the holding's) stands: then its servers are locked (§26.3 `423 company_locked`). */
@Composable
fun rememberLocked(company: String?): Boolean {
    val control = rememberQuery("control", "control") { control() }
    if (company == null) return false
    return !coState(company, false, control.data).running && control.data != null
}

@Composable
fun ServerStatePill(state: String, locked: Boolean = false) {
    if (locked) return Pill("قفل؛ شرکت متوقف است", Tone.WARN, icon = DivanIcon.LOCK)
    val s = SERVER_STATE[state] ?: ServerStateFa(state, Tone.NEUTRAL)
    Pill(s.fa, s.tone, icon = s.icon, live = s.live, dot = s.icon == null && !s.live)
}

@Composable
fun OriginPill(origin: String) =
    Pill(if (origin == "provisioned") "ساخته‌ی هاب" else "وصل‌شده", Tone.SILVER)

/** A line of a server's own text — a command, a path, a key — left to right in monospace; it scrolls sideways instead of wrapping. */
@Composable
fun CodeBlock(text: String, modifier: Modifier = Modifier, prefix: String? = null, color: Color? = null, bg: Color? = null, wrap: Boolean = false) {
    val c = Divan.colors
    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
        Box(modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(bg ?: c.page).then(if (wrap) Modifier else Modifier.horizontalScroll(rememberScrollState())).padding(horizontal = 12.dp, vertical = 9.dp)) {
            Text(buildAnnotatedString { if (prefix != null) fig(prefix, c.textMuted); append(text) }, style = Mono, color = color ?: c.textPrimary, softWrap = wrap)
        }
    }
}

/** A company stopped by its own switch or the holding's: everything on its servers stands, every new call is refused. */
@Composable
fun LockedBanner(company: String, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val name = com.coinepro.hq.ui.companyOf(rememberCompanies(), company).nameFa
    com.coinepro.hq.ui.v16.Notice(DivanIcon.LOCK, c.softWarning, c.warning, modifier) {
        Text("سرورهای $name قفل‌اند", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
        Text("کلید توقف این شرکت زده شده؛ جلسه‌های Claude روی سرورهایش همان لحظه ایستادند و هر فرمان تازه، حتی از ترمینال تو، رد میشود. با ادامه‌ی کار شرکت باز میشوند.", style = Divan.type.caption, color = c.textSecondary)
    }
}

/** Used against total, with its label and figures. */
@Composable
fun UsageBar(u: DiskUsage, label: String = u.label, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Column(modifier, verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(label, Modifier.weight(1f), style = Divan.type.caption, color = c.textSecondary)
            Fig("${ServerMaps.size(u.usedBytes)} / ${ServerMaps.size(u.totalBytes)}", style = Divan.type.figureSmall, color = c.textPrimary)
        }
        MeterBar(u.pct, tone = when { u.pct >= 90 -> BarTone.NEG; u.pct >= 75 -> BarTone.WARN; else -> BarTone.SILVER }, height = 5.dp)
    }
}

/** One server at a glance: its company (the server's own name too when the company has several), its runner's state, version and last
 *  poll, a road to the hub over the public address, and from its map disk, memory and what runs on it. */
@Composable
fun ServerCard(s: HubServer, locked: Boolean, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val c = Divan.colors
    val map = if (s.mapAt != null) rememberServerMap(s.id).data else null
    val name = rememberServerName(s.company, s.name)
    HqCard(modifier.fillMaxWidth(), onClick = onClick, onClickLabel = "باز کردن سرور ${name.text}") {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Box(Modifier.size(42.dp).clip(RoundedCornerShape(12.dp)).background(if (s.online && !locked) c.softGold else c.tile), contentAlignment = Alignment.Center) {
                DIcon(DivanIcon.SERVER, size = 21.dp, tint = if (s.online && !locked) c.goldInk else c.textSecondary)
            }
            ServerTitle(name, Modifier.weight(1f))
            DIcon(DivanIcon.NEXT, size = 16.dp, tint = c.textMuted)
        }
        FlowRow(Modifier.padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            ServerStatePill(s.state, locked)
            OriginPill(s.origin)
            if (s.via == "public" && s.online) Pill("از راه عمومی", Tone.WARN, icon = DivanIcon.GLOBE)
            RunnerFacts(s)
        }
        if (map != null && !map.empty) {
            Column(Modifier.padding(top = 12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                map.disks.firstOrNull()?.let { UsageBar(it, "دیسک") }
                map.memory?.let { UsageBar(it, "رم") }
                Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                    Count("کانتینر", "${map.runningContainers}/${map.containers.size}")
                    Count("سایت", map.sites.size.toString())
                    Count("ریپو", map.repos.size.toString())
                    Count("اتوماسیون", map.automations.size.toString())
                }
            }
        }
    }
}

/** The runner's version and its last poll ("آخرین تماس ۲ دقیقه پیش"). */
@Composable
fun RunnerFacts(s: HubServer) {
    val c = Divan.colors
    s.runnerVersion?.let { Fig("runner $it", style = Divan.type.figureSmall, color = c.textSecondary) }
    Text(s.lastSeenAt?.let { "آخرین تماس " + ago(it) } ?: "runner هنوز تماس نگرفته", style = Divan.type.micro, color = c.textMuted)
}

@Composable
private fun Count(label: String, value: String) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        Fig(value, style = Divan.type.figureSmall.copy(fontWeight = FontWeight.SemiBold), color = Divan.colors.textPrimary)
        Text(label, style = Divan.type.micro, color = Divan.colors.textMuted)
    }
}

// ------------------------------------------------------------------ activity --
/** A job's state (§26.2) as a pill: in the queue, running, held for the seal, done (with its exit), failed, cancelled; or refused. */
internal fun outcomePill(o: CallOutcome, exit: Int?): Pair<String, Tone> = when (o) {
    CallOutcome.QUEUED -> "در صف" to Tone.SILVER
    CallOutcome.RUNNING -> "در جریان" to Tone.LAPIS
    CallOutcome.AWAITING_SEAL -> "منتظر مُهر" to Tone.GOLD
    CallOutcome.OK -> (if (exit != null) "exit $exit" else "انجام شد") to Tone.POS
    CallOutcome.FAILED -> (if (exit != null) "exit $exit" else "ناموفق") to Tone.NEG
    CallOutcome.CANCELLED -> "لغو شد" to Tone.NEUTRAL
    CallOutcome.REFUSED -> "رد شد" to Tone.WARN
}

/** One job (or command) on a server: who, with which tool, what (the masked command, in its folder), its state and how long it took; its
 *  Claude session and its full transcript a tap away. */
@Composable
fun CallLine(r: ServerCallRow, serverName: String? = null, onTranscript: ((String) -> Unit)? = null) {
    val c = Divan.colors
    val nav = LocalNav.current
    Column(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Avatar(if (r.byOwner) "owner" else agentKindOf(r.actor.code, r.actor.kind), dept = deptOf(r.actor.code), size = 30.dp, state = if (r.outcome == CallOutcome.RUNNING) "working" else "idle")
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(1.dp)) {
                Text(buildAnnotatedString {
                    append(if (r.byOwner) "تو" else actorFa(r.actor))
                    append(" · " + r.toolFa)
                    if (serverName != null) { append(" · "); fig(serverName) }
                }, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), maxLines = 1, overflow = TextOverflow.Ellipsis)
                if (r.summaryFa.isNotBlank()) RichText(r.summaryFa, style = Divan.type.caption, color = c.textSecondary, maxLines = 2)
            }
            Text(jTime(r.at), style = Divan.type.micro, color = c.textMuted)
        }
        when {
            r.cmd != null -> CodeBlock(r.cmd, prefix = (r.cwd?.let { "$it " } ?: "") + "$ ")
            r.cwd != null -> Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                DIcon(DivanIcon.CODE, size = 14.dp, tint = c.textMuted)
                Fig(r.cwd, style = Divan.type.figureSmall, color = c.textSecondary)
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            val (t, tone) = outcomePill(r.outcome, r.exitCode)
            Pill(t, tone, dot = r.outcome != CallOutcome.RUNNING, live = r.outcome == CallOutcome.RUNNING, figure = t.startsWith("exit"))
            r.duration?.let { Fig(it, style = Divan.type.figureSmall, color = c.textMuted) }
            Box(Modifier.weight(1f))
            r.sessionRef?.let { ref -> HqButton("جلسه $ref", { nav.go("workshop/$ref") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.CODE) }
            if (r.transcriptUrl != null && onTranscript != null) HqButton("متن کامل", { onTranscript(r.transcriptUrl) }, variant = BtnVariant.GHOST, size = BtnSize.SM, icon = DivanIcon.REPORT)
        }
    }
}

/** A full transcript as the hub keeps it (§26.3), in monospace, read on the phone. */
@Composable
fun TranscriptSheet(url: String, onDismiss: () -> Unit) {
    val q = rememberQuery("transcript:$url", "servers", maxAgeMs = 300_000) { transcript(url) }
    com.coinepro.hq.ui.v14.HqSheet(onDismiss, "متن کامل", sub = "خروجی همان‌طور که روی سرور آمد؛ رمزها پیش از ذخیره ماسک شده‌اند.") {
        com.coinepro.hq.ui.Loadable(q) { text -> CodeBlock(text.trimEnd(), wrap = true) }
    }
}

// ------------------------------------------------------------------ the seal (§26.3) --
/** The cartable's cards for destructive commands on servers, each with the command itself and the seal or a no, on the spot. */
@Composable
fun SealCards(cards: List<Decision>) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        for (d in cards) sealCardOf(d)?.let { ServerSealCard(it) }
    }
}

/**
 * «کار ویرانگر منتظر مُهر تو»: what exactly would run, where, what kind of loss it is, who asked from which session. The seal is the
 * passkey on `server.destructive` (`<CODE>:<server>`); a no needs none (like engaging a kill switch).
 */
@Composable
fun ServerSealCard(card: SealCard, modifier: Modifier = Modifier, compact: Boolean = false) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val seal = rememberAction()
    val no = rememberAction()
    var reject by remember { mutableStateOf(false) }
    var done by remember(card.ref) { mutableStateOf<Boolean?>(null) }
    val where = rememberServerName(card.company, card.serverName)
    val shape = RoundedCornerShape(16.dp)
    Column(
        modifier.fillMaxWidth().clip(shape).background(c.card).border(1.dp, c.negative.copy(alpha = 0.55f), shape).padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Box(Modifier.size(34.dp).clip(CircleShape).background(c.softNegative), contentAlignment = Alignment.Center) { DIcon(DivanIcon.URGENT, size = 18.dp, tint = c.negative) }
            Column(Modifier.weight(1f)) {
                Text("کار ویرانگر منتظر مُهر تو", style = Divan.type.bodyStrong, color = c.textPrimary)
                Text(buildAnnotatedString {
                    append(where.text); append(" · ")
                    append(card.category?.titleFa ?: "دسته‌ی ویرانگر"); append(" · "); fig(card.ref)
                }, style = Divan.type.caption, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            CompanyMark(card.company, height = 14.dp, mono = true, ink = c.textSecondary)
        }
        // The whole command, wrapped: the owner seals exactly what will run, so nothing of it may hide off screen.
        CodeBlock(card.cmd.ifBlank { "—" }, prefix = (card.cwd?.let { "$it " } ?: "") + "$ ", bg = c.softNegative, wrap = true)
        Text(buildAnnotatedString {
            append(if (card.actor.kind == "owner") "از ترمینال تو" else actorFa(card.actor))
            card.sessionRef?.let { append(" در جلسه‌ی "); fig(it) }
            append("، " + ago(card.createdAt) + ". ")
            append(card.category?.whyFa ?: "")
        }, style = Divan.type.caption, color = c.textSecondary)
        if (!compact && card.detectedBy != null) Text(buildAnnotatedString {
            append(if (card.detectedBy == "tool") "دروازه از روی ابزار گرفت" else "دروازه از روی الگو گرفت")
            card.pattern?.let { append(": "); fig(it) }
        }, style = Divan.type.micro, color = c.textMuted)
        when {
            done == true -> Pill("مُهر خورد؛ اجرا میشود", Tone.GOLD, icon = DivanIcon.SEAL)
            done == false -> Pill("اجازه ندادی؛ اجرا نمیشود", Tone.NEUTRAL, icon = DivanIcon.REJECT)
            !card.pending -> Pill("تصمیم گرفته شد", Tone.NEUTRAL)
            else -> Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                HqButton("مُهر بزن", {
                    seal.run(onError = { toasts.error(com.coinepro.hq.core.net.serverError(it)) }) {
                        val token = env.auth.stepUp(act, "server.destructive", card.target)
                        env.api.approve(card.ref, null, token)
                        env.cache.invalidate("decisions", "inbox", "servers", "resolutions")
                        done = true
                        toasts.ok("مُهر خورد؛ فرمان روی سرور ${where.text} اجرا میشود.")
                    }
                }, variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, loading = seal.busy)
                HqButton("نه", { reject = true }, variant = BtnVariant.DANGER, icon = DivanIcon.REJECT, enabled = !seal.busy)
                Box(Modifier.weight(1f))
                if (!compact) HqButton(null, { nav.go("cartable/${card.ref}") }, variant = BtnVariant.GHOST, size = BtnSize.SM, icon = DivanIcon.NEXT, label = "باز کردن کارت")
            }
        }
        if (card.pending && done == null) Text("مُهر با اثر انگشت یا چهره؛ «نه» بی‌گذرکلید است.", style = Divan.type.micro, color = c.textMuted)
    }
    if (reject) AlertDialog(
        onDismissRequest = { reject = false },
        containerColor = c.overlay,
        title = { Text("اجرا نشود؟", style = Divan.type.h3) },
        text = { Text("فرمان روی سرور ${where.text} اجرا نمیشود و ${if (card.actor.kind == "owner") "" else actorFa(card.actor) + " "}خبردار میشود؛ میتواند راه دیگری پیشنهاد بدهد.", style = Divan.type.small, color = c.textSecondary) },
        confirmButton = {
            HqButton("اجرا نشود", {
                no.run {
                    env.api.reject(card.ref, "مدیر کل اجازه‌ی این کار ویرانگر را نداد.", "risk")
                    env.cache.invalidate("decisions", "inbox", "servers")
                    done = false
                    reject = false
                }
            }, variant = BtnVariant.DANGER, loading = no.busy)
        },
        dismissButton = { HqButton("برگشت", { reject = false }, variant = BtnVariant.GHOST) },
    )
}

/** The decision page's payload of a `server_destructive` card: the same facts, without its own buttons (the page has the seal). */
@Composable
fun SealPayload(d: Decision) {
    val c = Divan.colors
    val card = sealCardOf(d) ?: return
    val where = rememberServerName(card.company, card.serverName)
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("فرمانی که اجرا میشود", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
        CodeBlock(card.cmd.ifBlank { "—" }, prefix = (card.cwd?.let { "$it " } ?: "") + "$ ", bg = c.softNegative, wrap = true)
        Text(buildAnnotatedString {
            append("سرور "); append(where.text); append(" · ")
            append(card.category?.titleFa ?: "ویرانگر")
            card.sessionRef?.let { append(" · جلسه‌ی "); fig(it) }
        }, style = Divan.type.small, color = c.textSecondary)
        card.category?.let { Text(it.whyFa + " با مُهر، همین فرمان یک بار اجرا میشود؛ هر تغییری کارت تازه میخواهد.", style = Divan.type.caption, color = c.textMuted) }
    }
}

// ------------------------------------------------------------------ the control room --
/**
 * The control room's servers: how many, in which state, and the calls on them as they happen (`server.call` refreshes the rows); locked
 * when the company is stopped. [company] null: every company's (the holding's control room).
 */
@Composable
fun ServersControlCard(company: String?, stopped: Boolean, onOpen: () -> Unit) {
    val c = Divan.colors
    val q = rememberServers()
    val companies = rememberCompanies()
    val all = q.data ?: return
    val list = all.filter { company == null || it.company == company }
    // The last jobs on every online server (a handful of servers per company), newest first.
    val calls = list.filter { it.online }.take(6).flatMap { s ->
        androidx.compose.runtime.key(s.id) {
            rememberQuery("server:activity:${s.id}::", "servers", maxAgeMs = 15_000) { serverActivity(s.id, limit = 3) }.data?.items.orEmpty().map { serverNameOf(s.company, com.coinepro.hq.ui.companyOf(companies, s.company).nameFa, s.name, list.count { it.company == s.company }).text to it }
        }
    }.sortedByDescending { it.second.at }.take(3)
    HqCard(Modifier.fillMaxWidth(), onClick = onOpen, onClickLabel = "سرورها") {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            com.coinepro.hq.ui.v17.IconTile(DivanIcon.SERVER, c.goldInk, size = 36.dp)
            Column(Modifier.weight(1f)) {
                Text("سرورها", style = Divan.type.bodyStrong)
                Text(
                    if (list.isEmpty()) "هنوز سروری وصل نیست" else "${list.size} سرور، ${list.count { it.online }} آنلاین" +
                        list.count { it.state == "offline" }.takeIf { it > 0 }?.let { "، $it آفلاین" }.orEmpty() +
                        list.count { it.state == "pending" }.takeIf { it > 0 }?.let { "، $it منتظر runner" }.orEmpty(),
                    style = Divan.type.caption, color = c.textMuted,
                )
            }
            if (stopped) Pill("قفل", Tone.WARN, icon = DivanIcon.LOCK) else if (calls.any { callRow(it.second).outcome == CallOutcome.RUNNING }) Pill("زنده", Tone.POS, live = true)
            DIcon(DivanIcon.NEXT, size = 16.dp, tint = c.textMuted)
        }
        if (stopped && list.isNotEmpty()) Text("کلید توقف زده شده؛ کار روی سرورها ایستاده و فرمان تازه رد میشود.", Modifier.padding(top = 8.dp), style = Divan.type.caption, color = c.warning)
        else if (calls.isNotEmpty()) Column(Modifier.padding(top = 6.dp)) {
            calls.forEachIndexed { i, (server, x) ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                val r = callRow(x)
                Row(Modifier.padding(vertical = 7.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Box(Modifier.size(6.dp).clip(CircleShape).background(when (r.outcome) { CallOutcome.OK -> c.positive; CallOutcome.FAILED -> c.negative; CallOutcome.RUNNING -> c.lapis; CallOutcome.QUEUED, CallOutcome.CANCELLED -> c.textMuted; else -> c.warning }))
                    Text(buildAnnotatedString { append(if (r.byOwner) "تو" else actorFa(r.actor)); append(": "); append(r.summaryFa.ifBlank { r.toolFa }) }, style = Divan.type.caption, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                    Text(server, style = Divan.type.micro, color = c.textMuted, maxLines = 1)
                    Text(ago(r.at), style = Divan.type.micro, color = c.textMuted)
                }
            }
        }
        // The holding's control room: the network map (§26.6) one tap away.
        if (company == null && list.isNotEmpty()) {
            val nav = LocalNav.current
            HqButton("شبکه‌ی هلدینگ", { nav.go("network") }, Modifier.padding(top = 4.dp), variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.GLOBE)
        }
    }
}
