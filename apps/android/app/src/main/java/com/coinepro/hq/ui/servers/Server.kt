package com.coinepro.hq.ui.servers

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
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
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.instant
import com.coinepro.hq.core.format.until
import com.coinepro.hq.core.net.HubServer
import com.coinepro.hq.core.net.SERVER_DESTRUCTIVE
import com.coinepro.hq.core.net.ServerMap
import com.coinepro.hq.core.net.callRow
import com.coinepro.hq.core.net.sealCardOf
import com.coinepro.hq.core.net.serverError
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.IconBtn
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.shell.LocalLive
import com.coinepro.hq.ui.workshop.SessionRow
import com.coinepro.hq.ui.workshop.rememberGrants
import com.coinepro.hq.ui.workshop.rememberSessions
import com.coinepro.hq.ui.workshop.rememberWorkspaces

/** One company server (§26): its runner's state and its map, the jobs on it live, Claude Code sessions on it, the owner's terminal, its
 *  seals. */
@Composable
fun ServerScreen(id: String, tab0: String = "map") {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val q = rememberServers()
    val s = q.data?.firstOrNull { it.id == id }
    val locked = rememberLocked(s?.company)
    val name = rememberServerName(s?.company.orEmpty(), s?.name)
    var tab by rememberSaveable { mutableStateOf(tab0) }
    var task by remember { mutableStateOf(false) }
    var detach by remember { mutableStateOf(false) }
    var transcript by remember { mutableStateOf<String?>(null) }
    val map = rememberServerMap(id)
    val refresh = rememberAction()
    val seals = rememberQuery("decisions:pending", "decisions") { decisions("pending") }.data?.items.orEmpty()
        .filter { it.kind == SERVER_DESTRUCTIVE }.mapNotNull(::sealCardOf).filter { it.serverId == id || (s != null && it.company == s.company && it.serverName == s.name) }
    val r = refresher(q, map)

    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        if (s == null) {
            item { if (q.error != null) ErrorBlock(q.error, { q.refresh() }) else Skeleton(Modifier.fillMaxWidth().height(200.dp), radius = 16.dp) }
            if (q.data != null) item { Empty("این سرور دیگر به هاب وصل نیست", icon = DivanIcon.SERVER) }
            return@Page
        }
        item(key = "head") {
            HqCard(Modifier.fillMaxWidth()) {
                Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Box(Modifier.size(48.dp).clip(RoundedCornerShape(14.dp)).background(if (s.online && !locked) c.softGold else c.tile), contentAlignment = Alignment.Center) {
                        DIcon(DivanIcon.SERVER, size = 24.dp, tint = if (s.online && !locked) c.goldInk else c.textSecondary)
                    }
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                        // The owner's rule: the company is the server's name; the server's own name follows only when the company has several.
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            CompanyMark(s.company, height = 16.dp, mono = true, ink = c.textSecondary)
                            Text(name.companyFa, style = Divan.type.h2, color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                        name.server?.let { Fig(it, style = Divan.type.figureSmall, color = c.textSecondary) }
                    }
                    Box {
                        var menu by remember { mutableStateOf(false) }
                        IconBtn(DivanIcon.MORE, "کارهای این سرور", { menu = true })
                        DropdownMenu(menu, { menu = false }, containerColor = c.overlay) {
                            if (s.online) DropdownMenuItem({ Text("نقشه‌ی تازه بگیر", style = Divan.type.small) }, {
                                menu = false
                                refresh.run(onError = { toasts.error(serverError(it)) }) {
                                    val m = env.api.refreshMap(s.id)
                                    if (m != null) map.set(m) else toasts.info("نقشه‌برداری شروع شد؛ چند لحظه بعد اینجا میاید.")
                                    env.cache.invalidate("servers")
                                }
                            }, leadingIcon = { DIcon(DivanIcon.REFRESH, size = 18.dp) })
                            DropdownMenuItem({ Text("قوانین سرورها", style = Divan.type.small) }, { menu = false; nav.go("server-policy") }, leadingIcon = { DIcon(DivanIcon.SEAL, size = 18.dp) })
                            if (!s.revoked) DropdownMenuItem({ Text("جدا کردن از هاب", style = Divan.type.small, color = c.negative) }, { menu = false; detach = true }, leadingIcon = { DIcon(DivanIcon.CLOSE, size = 18.dp, tint = c.negative) })
                        }
                    }
                }
                FlowRow(Modifier.padding(top = 12.dp), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                    ServerStatePill(s.state, locked)
                    OriginPill(s.origin)
                    RunnerFacts(s)
                }
                FlowRow(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                    Fact("میزبان", s.hostname)
                    Fact("کاربر کاری", s.user.ifBlank { null })
                    Fact("آدرس خصوصی", s.privateIp.ifBlank { null })
                    // §26.1a / §26.6: how the runner reached the hub on its last poll.
                    s.via?.let { v -> Fact(if (v == "public") "به هاب از راه عمومی" else "به هاب از شبکه‌ی خصوصی", com.coinepro.hq.core.net.Network.ms(s.hubRttMs) ?: "—") }
                }
                Row(Modifier.padding(top = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    HqButton("یک کار بسپار", { task = true }, Modifier.weight(1f), variant = BtnVariant.PRIMARY, icon = DivanIcon.CODE, enabled = s.online && !locked)
                    HqButton("ترمینال", { nav.go("servers/${s.id}/terminal") }, Modifier.weight(1f), icon = DivanIcon.COMMAND, enabled = s.online && !locked)
                }
            }
        }
        if (locked) item(key = "locked") { LockedBanner(s.company) }
        when (s.state) {
            "pending" -> item(key = "pending") {
                com.coinepro.hq.ui.v16.Notice(DivanIcon.TIME, c.softGold, c.goldInk) {
                    Text("کد تأیید شد؛ منتظر runner", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                    Text(isolated("runner در تماس بعدی‌اش اعتبار خودش را میگیرد و سرور «آنلاین» میشود، معمولاً در چند ثانیه. اگر نشد، Claude همان سرور با hq-runner status وضعش را ببیند."), style = Divan.type.caption, color = c.textSecondary)
                }
            }
            "offline" -> item(key = "offline") {
                com.coinepro.hq.ui.v16.Notice(DivanIcon.OFFLINE, c.softWarning, c.warning) {
                    Text("runner این سرور تماس نمیگیرد", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                    Text(isolated("سرور خاموش است، سرویس hq-runner ایستاده یا سرور به اینترنت نمیرسد. تا runner برنگردد، هیچ کاری رویش اجرا نمیشود؛ Claude همان سرور با hq-runner status علتش را میبیند."), style = Divan.type.caption, color = c.textSecondary)
                }
            }
            "revoked" -> item(key = "revoked") {
                com.coinepro.hq.ui.v16.Notice(DivanIcon.CLOSE, c.tile, c.textSecondary) {
                    Text("runner این سرور باطل شده", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                    Text(isolated("هاب دیگر هیچ کاری به این سرور نمیدهد. تاریخچه‌ی کارها در Audit میماند. برای وصل دوباره، روی سرور hq-runner pair را از نو اجرا کن و کد تازه را در «وصل کردن سرور» تأیید کن."), style = Divan.type.caption, color = c.textSecondary)
                }
            }
        }
        if (seals.isNotEmpty()) item(key = "seals") { Column(verticalArrangement = Arrangement.spacedBy(12.dp)) { for (x in seals) ServerSealCard(x, compact = true) } }
        item(key = "tabs") {
            Segmented(listOf(SegOption("map", "نقشه"), SegOption("activity", "فعالیت"), SegOption("sessions", "جلسه‌ها")), tab, { tab = it }, Modifier.fillMaxWidth())
        }
        when (tab) {
            "activity" -> item(key = "activity") { ActivityTab(s) { transcript = it } }
            "sessions" -> item(key = "sessions") { SessionsTab(s, locked) { task = true } }
            else -> item(key = "map") {
                val m = map.data
                when {
                    m == null && map.loading -> Skeleton(Modifier.fillMaxWidth().height(320.dp), radius = 16.dp)
                    m == null && map.error != null -> ErrorBlock(map.error, { map.refresh() })
                    m == null -> Empty("هنوز نقشه‌ای گرفته نشده", icon = DivanIcon.SERVER, body = if (s.online) "با «نقشه‌ی تازه بگیر» runner سرور را میگردد: سیستم، دیسک، کانتینرها، سرویس‌ها، ریپوها و سایت‌ها." else "وقتی runner آنلاین شد، اولین نقشه خودکار گرفته میشود.") {
                        if (s.online) HqButton("نقشه‌ی تازه بگیر", { refresh.run { env.api.refreshMap(s.id)?.let(map::set); env.cache.invalidate("servers") } }, icon = DivanIcon.REFRESH, loading = refresh.busy)
                    }
                    else -> MapView(m, refreshing = refresh.busy) {
                        refresh.run(onError = { toasts.error(serverError(it)) }) {
                            val x = env.api.refreshMap(s.id)
                            if (x != null) map.set(x) else toasts.info("نقشه‌برداری شروع شد؛ چند لحظه بعد اینجا میاید.")
                            env.cache.invalidate("servers")
                        }
                    }
                }
            }
        }
    }
    if (task && s != null) ServerTaskSheet(listOf(s), s) { task = false }
    if (detach && s != null) DetachDialog(s) { detach = false }
    transcript?.let { TranscriptSheet(it) { transcript = null } }
}

@Composable
private fun ActivityTab(s: HubServer, onTranscript: (String) -> Unit) {
    val c = Divan.colors
    val live = LocalLive.current
    var mine by rememberSaveable { mutableStateOf(false) }
    val q = rememberQuery("server:activity:${s.id}:${if (mine) "owner" else ""}:", "servers", maxAgeMs = 15_000) { serverActivity(s.id, actor = if (mine) "owner" else null) }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip("همه", !mine, { mine = false })
            FilterChip("فقط من", mine, { mine = true })
            Box(Modifier.weight(1f))
            val on = live.state == com.coinepro.hq.core.data.StreamState.LIVE
            Pill(if (on) "زنده" else "در حال اتصال", if (on) Tone.POS else Tone.WARN, live = on)
        }
        val rows = q.data?.items
        when {
            rows == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
            rows == null -> Skeleton(Modifier.fillMaxWidth().height(260.dp), radius = 16.dp)
            rows.isEmpty() -> Empty("هنوز کاری روی این سرور ثبت نشده", icon = DivanIcon.AGENT, body = "هر کار روی سرور — فرمان، خواندن و نوشتن فایل، نقشه و جلسه‌ی Claude — با فرمان ماسک‌شده‌اش و وضعیتش اینجا میاید: در صف، در جریان، منتظر مُهر، تمام، ناموفق یا لغو.")
            else -> HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(horizontal = 14.dp, vertical = 4.dp)) {
                rows.forEachIndexed { i, x ->
                    if (i > 0) HorizontalDivider(color = c.lineDivider)
                    CallLine(callRow(x), onTranscript = onTranscript)
                }
            }
        }
        Text("رمزها پیش از ثبت با نام و الگو ماسک میشوند؛ متن کامل هر کار برای تو میماند. کلید توقف شرکت کارهای در صف و در جریان را لغو میکند.", style = Divan.type.micro, color = c.textMuted)
    }
}

@Composable
private fun SessionsTab(s: HubServer, locked: Boolean, onNew: () -> Unit) {
    val nav = LocalNav.current
    val c = Divan.colors
    val sessions = rememberSessions()
    val workspaces = rememberWorkspaces()
    val grants = rememberGrants()
    val list = sessions.data?.filter { it.onServer && it.server == s.id }
    val name = rememberServerName(s.company, s.name)
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        HqButton("یک کار روی این سرور بسپار", onNew, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.CODE, enabled = s.online && !locked)
        when {
            list == null -> Skeleton(Modifier.fillMaxWidth().height(120.dp), radius = 14.dp)
            list.isEmpty() -> Text("هنوز جلسه‌ای روی این سرور نبوده.", style = Divan.type.caption, color = c.textMuted)
            else -> for (x in list.sortedWith(compareByDescending<com.coinepro.hq.core.net.CodeSession> { it.open }.thenByDescending { it.updatedAt })) {
                SessionRow(x, workspaces.data, grants.data?.firstOrNull { it.ref == x.grant }, serverName = name.text) { nav.go("workshop/${x.ref}") }
            }
        }
        Text("Claude Code خود سرور با login همان سرور کار میکند؛ مصرفش از پاکت شرکت و خزانه‌ی توکن کم میشود.", style = Divan.type.micro, color = c.textMuted)
    }
}

// ------------------------------------------------------------------ the map --
@Composable
private fun MapSection(title: String, count: Int?, limit: Int = 6, total: Int = count ?: 0, content: @Composable ColumnScope.(showAll: Boolean) -> Unit) {
    val c = Divan.colors
    var all by remember { mutableStateOf(false) }
    HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(14.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(title, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk, modifier = Modifier.weight(1f))
            count?.let { Text("$it", style = Divan.type.caption, color = c.textMuted) }
        }
        Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) { content(all) }
        if (total > limit) HqButton(if (all) "کمتر" else "همه ($total)", { all = !all }, Modifier.padding(top = 6.dp), variant = BtnVariant.TEXT, size = BtnSize.SM)
    }
}

private fun uptimeFa(s: Long): String = when {
    s >= 86_400 -> "${s / 86_400} روز"
    s >= 3_600 -> "${s / 3_600} ساعت"
    else -> "${s / 60} دقیقه"
}

/** A time the map wrote: an instant ("in 3 hours", "2 hours ago"), or its own words kept as written. */
private fun whenFa(v: String?, future: Boolean): String? {
    v ?: return null
    if (instant(v) == null || !v.contains('T')) return v
    return if (future) until(v) else ago(v)
}

@Composable
private fun Dot(on: Boolean?) {
    val c = Divan.colors
    Box(Modifier.size(7.dp).clip(CircleShape).background(when (on) { true -> c.positive; false -> c.negative; null -> c.textMuted }))
}

/** `server.map` read for the owner: the machine, its resources, what runs on it and what it serves. */
@Composable
fun MapView(m: ServerMap, refreshing: Boolean = false, onRefresh: (() -> Unit)? = null) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(m.at?.let { "نقشه‌ی " + ago(it) } ?: "آخرین نقشه", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.weight(1f))
            onRefresh?.let { HqButton("نقشه‌ی تازه", it, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.REFRESH, loading = refreshing) }
        }
        HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(14.dp)) {
            Text("سیستم", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
            FlowRow(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                m.os?.let { Fig(it, style = Divan.type.figureSmall, color = c.textPrimary) }
                m.kernel?.let { Fig(it, style = Divan.type.figureSmall, color = c.textMuted) }
                m.hostname?.let { Fig(it, style = Divan.type.figureSmall, color = c.textMuted) }
                m.cpus?.let { Text(buildAnnotatedString { fig("$it"); append(" vCPU") }, style = Divan.type.caption, color = c.textSecondary) }
                m.load?.let { Text(buildAnnotatedString { append("بار "); fig(String.format(java.util.Locale.US, "%.2f", it)) }, style = Divan.type.caption, color = c.textSecondary) }
                m.uptimeS?.let { Text("روشن از " + uptimeFa(it) + " پیش", style = Divan.type.caption, color = c.textSecondary) }
            }
            if (m.disks.isNotEmpty() || m.memory != null) Column(Modifier.padding(top = 12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                for (d in m.disks) UsageBar(d, "دیسک ${d.label}")
                m.memory?.let { UsageBar(it, "رم") }
                m.swap?.let { UsageBar(it, "حافظه‌ی swap") }
            }
        }
        if (m.containers.isNotEmpty()) MapSection("کانتینرها", null, total = m.containers.size) { all ->
            Text("${m.runningContainers} در حال اجرا از ${m.containers.size}", style = Divan.type.caption, color = c.textMuted)
            for (x in m.containers.sortedByDescending { it.state == "running" }.let { if (all) it else it.take(6) }) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Dot(x.state == "running")
                    Column(Modifier.weight(1f)) {
                        Fig(x.name, style = Divan.type.figureSmall.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                        x.image?.let { Fig(it, style = Divan.type.figureSmall, color = c.textMuted) }
                    }
                    x.project?.let { Fig(it, Modifier.clip(RoundedCornerShape(6.dp)).background(c.tile).padding(horizontal = 6.dp, vertical = 1.dp), style = Divan.type.figureSmall, color = c.textSecondary) }
                    (x.status ?: x.health)?.let { Fig(it, style = Divan.type.figureSmall, color = if (x.health == "unhealthy") c.negative else c.textMuted) }
                }
            }
        }
        if (m.compose.isNotEmpty()) MapSection("پروژه‌های compose", m.compose.size) { all ->
            for (p in if (all) m.compose else m.compose.take(6)) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Column(Modifier.weight(1f)) {
                    Fig(p.project, style = Divan.type.figureSmall.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                    p.dir?.let { Fig(it, style = Divan.type.figureSmall, color = c.textMuted) }
                }
                // §26.5 lists a project's services, not how many run: counted from the containers of the same project.
                val running = p.running ?: m.containers.filter { it.project == p.project }.takeIf { it.isNotEmpty() }?.count { it.state == "running" }
                if (p.services != null) Fig("${running ?: "?"}/${p.services}", style = Divan.type.figureSmall, color = if (running == p.services) c.positive else c.warning)
            }
        }
        if (m.timers.isNotEmpty() || m.units.isNotEmpty()) MapSection("systemd", m.timers.size + m.units.size, total = m.timers.size) { all ->
            if (m.timers.isNotEmpty()) Text("تایمرها", style = Divan.type.caption, color = c.textMuted)
            for (t in if (all) m.timers else m.timers.take(6)) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                DIcon(DivanIcon.TIME, size = 14.dp, tint = c.textSecondary)
                Column(Modifier.weight(1f)) {
                    Fig(t.unit, style = Divan.type.figureSmall.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                    t.activates?.let { Fig("→ $it", style = Divan.type.figureSmall, color = c.textMuted) }
                }
                whenFa(t.next, true)?.let { Text(it, style = Divan.type.micro, color = c.textSecondary) }
            }
            if (m.units.isNotEmpty()) {
                Text("سرویس‌ها", style = Divan.type.caption, color = c.textMuted)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    for (u in m.units) Row(Modifier.clip(RoundedCornerShape(8.dp)).background(c.tile).padding(horizontal = 8.dp, vertical = 3.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                        Dot(u.state?.let { it == "active" || it == "running" })
                        Fig(u.name, style = Divan.type.figureSmall, color = c.textSecondary)
                    }
                }
            }
        }
        if (m.cron.isNotEmpty()) MapSection("cron", m.cron.size) { all ->
            for (x in if (all) m.cron else m.cron.take(6)) Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    // A schedule has no letter to set its direction: isolated left to right, it reads as cron wrote it.
                    Fig("\u2066${x.schedule}\u2069", style = Divan.type.figureSmall.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
                    x.user?.let { Fig(it, style = Divan.type.figureSmall, color = c.textMuted) }
                }
                CodeBlock(x.command)
            }
        }
        if (m.ports.isNotEmpty()) MapSection("پورت‌های باز", m.ports.size) { _ ->
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                for (p in m.ports) {
                    val public = p.public ?: (p.address == null || p.address == "0.0.0.0" || p.address == "*" || p.address == "[::]" || p.address == "::")
                    Fig(
                        "${p.port}/${p.proto}" + (p.process?.let { " $it" } ?: "") + (if (!public) " · ${p.address}" else ""),
                        Modifier.clip(RoundedCornerShape(8.dp)).background(if (public) c.softWarning else c.tile).padding(horizontal = 8.dp, vertical = 3.dp),
                        style = Divan.type.figureSmall, color = c.textPrimary,
                    )
                }
            }
            Text("زرد: روی همه‌ی آدرس‌ها باز است؛ بقیه فقط محلی یا شبکه‌ی خصوصی.", style = Divan.type.micro, color = c.textMuted)
        }
        if (m.repos.isNotEmpty()) MapSection("ریپوها", m.repos.size) { all ->
            for (x in if (all) m.repos else m.repos.take(6)) Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    DIcon(DivanIcon.CODE, size = 14.dp, tint = c.textSecondary)
                    Fig(x.path, Modifier.weight(1f), style = Divan.type.figureSmall.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                    if (x.dirty == true) Pill("تغییر ثبت‌نشده", Tone.WARN)
                }
                x.remote?.let { Fig(it, style = Divan.type.figureSmall, color = c.textMuted) }
                if (x.branch != null || x.head != null || x.lastCommitAt != null) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (x.branch != null || x.head != null) Fig(listOfNotNull(x.branch, x.head).joinToString(" @ "), style = Divan.type.figureSmall, color = c.textSecondary)
                    whenFa(x.lastCommitAt, false)?.let { Text("آخرین commit " + it, style = Divan.type.micro, color = c.textMuted) }
                }
            }
        }
        if (m.automations.isNotEmpty()) MapSection("n8n و اتوماسیون‌ها", m.automations.size) { all ->
            for (a in if (all) m.automations else m.automations.take(6)) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Dot(a.active)
                Column(Modifier.weight(1f)) {
                    Text(a.name, style = Divan.type.small, color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    a.detail?.let { Fig(it, style = Divan.type.figureSmall, color = c.textMuted) }
                }
                Fig(a.kind, Modifier.clip(RoundedCornerShape(6.dp)).background(c.tile).padding(horizontal = 6.dp, vertical = 1.dp), style = Divan.type.figureSmall, color = c.textSecondary)
            }
        }
        if (m.sites.isNotEmpty()) MapSection("سایت‌ها", m.sites.size) { all ->
            for (x in if (all) m.sites else m.sites.take(6)) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                DIcon(DivanIcon.GLOBE, size = 14.dp, tint = c.textSecondary)
                Column(Modifier.weight(1f)) {
                    Fig(x.domain, style = Divan.type.figureSmall.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                    x.upstream?.let { Fig("→ $it" + (x.server?.let { s -> " · $s" } ?: ""), style = Divan.type.figureSmall, color = c.textMuted) }
                }
                if (x.tls == true) Pill("HTTPS", Tone.POS, figure = true) else if (x.tls == false) Pill("HTTP", Tone.WARN, figure = true)
            }
        }
    }
}

@Composable
private fun Fact(label: String, value: String?) {
    value ?: return
    val c = Divan.colors
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
        Text(label, style = Divan.type.micro, color = c.textMuted)
        Fig(value, style = Divan.type.figureSmall, color = c.textSecondary)
    }
}

// ------------------------------------------------------------------ ⋮ actions --
@Composable
private fun DetachDialog(s: HubServer, onDone: () -> Unit) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val action = rememberAction()
    val label = rememberServerName(s.company, s.name).text
    AlertDialog(
        onDismissRequest = onDone,
        containerColor = c.overlay,
        title = { Text("جدا کردن سرور $label از هاب؟", style = Divan.type.h3) },
        text = {
            Text(isolated("اعتبار runner همین لحظه باطل میشود و runner در تماس بعدی‌اش میایستد؛ کارهای در صف لغو میشوند و دیگر هیچ ایجنتی کاری روی این سرور نمیکند. خود سرور دست نمیخورد: کاربر کاری، فایل‌ها و سرویس‌ها همان‌طور میمانند. تاریخچه‌ی کارها در Audit میماند."), style = Divan.type.small, color = c.textSecondary)
        },
        confirmButton = {
            HqButton("با اثر انگشت جدا کن", {
                action.run(onError = { toasts.error(serverError(it)) }) {
                    env.api.detachServer(s) { a, t -> env.auth.stepUp(act, a, t) }
                    env.cache.invalidate("servers")
                    toasts.ok("runner سرور ${label} باطل شد.")
                    onDone()
                    nav.back()
                }
            }, variant = BtnVariant.DANGER, icon = DivanIcon.CLOSE, loading = action.busy)
        },
        dismissButton = { HqButton("نه", onDone, variant = BtnVariant.GHOST) },
    )
}
