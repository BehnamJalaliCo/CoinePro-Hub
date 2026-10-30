package com.coinepro.hq.ui.servers

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.ExecIn
import com.coinepro.hq.core.net.HubServer
import com.coinepro.hq.core.net.TermEvent
import com.coinepro.hq.core.net.TermHistory
import com.coinepro.hq.core.net.TermKind
import com.coinepro.hq.core.net.TerminalBuffer
import com.coinepro.hq.core.net.serverError
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.rememberQuery
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

/** One server's terminal as it stays while the app runs: its lines (memory only) and the command that may be running. */
@Stable
class TermUi(val buffer: TerminalBuffer = TerminalBuffer()) {
    var version by mutableIntStateOf(0)
        private set
    var job: Job? = null

    fun changed() { version++ }

    companion object {
        private val byServer = mutableMapOf<String, TermUi>()
        @Synchronized fun of(server: String): TermUi = byServer.getOrPut(server) { TermUi() }
    }
}

/** The lines the panel draws at most (the buffer keeps more). */
private const val SHOWN = 800

/** A few starting points for the owner, all harmless (read-only). */
private val SUGGESTED = listOf("docker ps", "df -h", "free -h", "systemctl list-timers --no-pager", "git -C ~ status", "tail -n 50 /var/log/syslog")

/**
 * «ترمینال»: the owner's own command on a company server (§26.4 `POST /infra/servers/{id}/exec`, 🔏 `server.exec` per command), its output
 * streaming into a monospace, left-to-right panel inside the right-to-left app; the last commands a tap away. A destructive one waits for
 * the seal like any agent's; a stopped company refuses it (`423 company_locked`).
 */
@Composable
fun TerminalScreen(id: String, run0: String? = null) {
    val q = rememberServers()
    val s = q.data?.firstOrNull { it.id == id }
    when {
        s != null -> Terminal(s, run0)
        q.error != null -> Box(Modifier.padding(16.dp)) { ErrorBlock(q.error, { q.refresh() }) }
        else -> Box(Modifier.fillMaxSize().padding(16.dp)) { Skeleton(Modifier.fillMaxSize(), radius = 16.dp) }
    }
}

@Composable
private fun Terminal(s: HubServer, run0: String?) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val scope = rememberCoroutineScope()
    val term = remember(s.id) { TermUi.of(s.id) }
    val history = remember(s.id) { TermHistory.of(s.id) }
    val locked = rememberLocked(s.company)
    val mine = rememberQuery("server:activity:${s.id}:owner:", "servers", maxAgeMs = 30_000) { serverActivity(s.id, actor = "owner", limit = 20) }
    var cmd by rememberSaveable { mutableStateOf("") }
    var sudo by rememberSaveable { mutableStateOf(false) }
    val vertical = rememberScrollState()
    val version = term.version
    val lines = remember(version) { term.buffer.lines }
    LaunchedEffect(version) { androidx.compose.runtime.withFrameNanos { }; vertical.scrollTo(vertical.maxValue) }

    fun run(text: String) {
        val command = text.trim()
        if (command.isEmpty() || term.buffer.running) return
        history.add(command)
        term.buffer.command(command, s.login)
        term.changed()
        cmd = ""
        term.job = scope.launch {
            try {
                env.api.exec(s, ExecIn(command, sudo = sudo)) { a, t -> env.auth.stepUp(act, a, t) }.collect { e ->
                    term.buffer.apply(e)
                    term.changed()
                    if (e is TermEvent.AwaitingSeal) {
                        env.cache.invalidate("decisions", "inbox", "servers")
                        toasts.info("کارتش در کارتابل منتظر مُهر توست.", e.decisionRef?.let { "کارت" }) { e.decisionRef?.let { nav.go("cartable/$it") } }
                    }
                }
                term.buffer.ended("اتصال بسته شد؛ پایان فرمان نرسید. نتیجه در «فعالیت» ثبت است.")
            } catch (e: ApiException) {
                term.buffer.apply(TermEvent.Failed(e.code, serverError(e)))
            } catch (e: CancellationException) {
                term.buffer.ended("متوقف کردی؛ اتصال بسته شد.")
                throw e
            } catch (e: java.io.IOException) {
                term.buffer.apply(TermEvent.Failed("network_error", "اتصال قطع شد؛ نتیجه در «فعالیت» ثبت است."))
            } finally {
                term.changed()
                env.cache.invalidate("servers")
            }
        }
    }
    LaunchedEffect(run0) { if (run0 != null && lines.isEmpty()) run(run0) }

    val running = term.buffer.running
    val recorded = mine.data?.items.orEmpty().mapNotNull { it.cmdMasked }
    val recent = remember(version, recorded) { history.with(recorded) }

    Column(Modifier.fillMaxSize().imePadding().padding(horizontal = 16.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text("ترمینال", style = Divan.type.h2)
                ServerTitle(rememberServerName(s.company, s.name), style = Divan.type.caption, color = c.textSecondary)
            }
            ServerStatePill(s.state, locked)
        }
        if (locked) LockedBanner(s.company)
        else Text("هر فرمان با اثر انگشت تأیید میشود و با خروجی‌اش در «فعالیت» میماند؛ کارهای ویرانگر طبق قوانین سرورها منتظر مُهر میمانند.", style = Divan.type.caption, color = c.textMuted)

        // The panel: the server's own text, left to right in monospace, whatever the app's direction.
        CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
            Box(Modifier.weight(1f).fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.tile).border(1.dp, c.lineDivider, RoundedCornerShape(14.dp))) {
                if (lines.isEmpty()) Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("${s.login}:~\$", style = Mono, color = c.textMuted)
                    Text("# type a command below, or pick one:", style = Mono, color = c.textMuted)
                    for (x in SUGGESTED) Text("  $x", style = Mono, color = c.goldInk, modifier = Modifier.clickable(role = Role.Button) { cmd = x })
                } else {
                    // Lines are never wrapped (a table stays a table): the panel scrolls both ways, and follows the output down.
                    val shown = if (lines.size > SHOWN) lines.takeLast(SHOWN) else lines
                    Column(Modifier.fillMaxSize().verticalScroll(vertical).horizontalScroll(rememberScrollState()).padding(12.dp)) {
                        if (lines.size > SHOWN) Text("… ${lines.size - SHOWN} earlier lines", style = Mono, color = c.textMuted)
                        shown.forEachIndexed { i, l ->
                            Text(
                                l.text.ifEmpty { " " },
                                style = if (l.kind == TermKind.CMD) Mono.copy(fontWeight = FontWeight.Bold) else Mono,
                                color = colorOf(l.kind),
                                softWrap = false,
                                modifier = Modifier.padding(top = if (l.kind == TermKind.CMD && i > 0) 10.dp else 0.dp),
                            )
                        }
                        if (running) Row(Modifier.padding(top = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            if (!com.coinepro.hq.designsystem.LocalReducedMotion.current) CircularProgressIndicator(Modifier.size(10.dp), color = c.goldInk, strokeWidth = 1.5.dp)
                            Text("running…", style = Mono, color = c.textMuted)
                        }
                    }
                }
            }
        }

        if (recent.isNotEmpty()) CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
            LazyRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                items(recent) { h ->
                    Text(h, style = Mono, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.clip(RoundedCornerShape(8.dp)).background(c.card).clickable(role = Role.Button, onClickLabel = "دوباره بنویس") { cmd = h }.padding(horizontal = 10.dp, vertical = 6.dp))
                }
            }
        }

        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip("sudo", sudo, { sudo = !sudo })
            if (term.buffer.lines.isNotEmpty() && !running) HqButton("پاک کردن صفحه", { term.buffer.clear(); term.changed() }, variant = BtnVariant.GHOST, size = BtnSize.SM)
            Box(Modifier.weight(1f))
            term.buffer.lastExit?.takeIf { !running }?.let { Fig("exit $it", style = Divan.type.figureSmall, color = if (it == 0) c.positive else c.negative) }
        }
        CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.card).border(1.dp, c.lineStrong, RoundedCornerShape(12.dp)).padding(start = 12.dp, end = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(if (sudo) "#" else "$", style = Mono.copy(fontWeight = FontWeight.Bold), color = c.goldInk)
                BasicTextField(
                    cmd, { cmd = it.replace("\n", " ") },
                    Modifier.weight(1f).padding(horizontal = 8.dp, vertical = 14.dp),
                    enabled = !locked,
                    singleLine = true,
                    textStyle = Mono.copy(color = c.textPrimary),
                    cursorBrush = SolidColor(c.goldInk),
                    keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.None, autoCorrectEnabled = false, keyboardType = KeyboardType.Ascii, imeAction = ImeAction.Send),
                    keyboardActions = KeyboardActions(onSend = { run(cmd) }),
                    decorationBox = { inner ->
                        Box {
                            if (cmd.isEmpty()) Text(if (locked) "locked" else "command", style = Mono, color = c.textMuted)
                            inner()
                        }
                    },
                )
                if (running) HqButton(null, { term.job?.cancel() }, variant = BtnVariant.DANGER, size = BtnSize.MD, icon = DivanIcon.STOP, label = "توقف")
                else HqButton(null, { run(cmd) }, variant = BtnVariant.PRIMARY, size = BtnSize.MD, icon = DivanIcon.SEND, enabled = cmd.isNotBlank() && !locked && s.online, label = "اجرا با اثر انگشت")
            }
        }
    }
}

@Composable
private fun colorOf(k: TermKind): Color = with(Divan.colors) {
    when (k) {
        TermKind.CMD -> goldInk
        TermKind.OUT -> textPrimary
        TermKind.ERR -> negative
        TermKind.INFO -> textMuted
        TermKind.OK -> positive
        TermKind.FAIL -> negative
    }
}
