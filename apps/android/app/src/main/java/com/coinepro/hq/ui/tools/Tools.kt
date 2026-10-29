package com.coinepro.hq.ui.tools

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.format.roleFa
import com.coinepro.hq.core.net.companiesOf
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.StatTile
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.Tag
import java.util.Locale

private val BLOCK_FA = mapOf("private_network" to "شبکه‌ی خصوصی (مسدود)", "egress_limit" to "سقف (مسدود)", "internal_data" to "داده‌ی داخلی (مسدود)")

/** ابزارها و اینترنت (contract §18.7): agents reach the internet only through tools in the egress service and every
 *  request is logged; private networks and neighbours stay closed; commitments in the holding's name become decision
 *  cards. MCP servers come in only with the owner's seal; service-account secrets are injected at egress, never seen. */
@Composable
fun ToolsScreen() {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val sum = rememberQuery("tools:egress:summary", "tools", maxAgeMs = 60_000) { egressSummary() }
    val log = rememberQuery("tools:egress", "tools", maxAgeMs = 15_000) { egress().items }
    val mcp = rememberQuery("tools:mcp", "tools") { mcpServers() }
    val accounts = rememberQuery("tools:accounts", "tools", maxAgeMs = 120_000) { serviceAccounts() }
    val catalog = rememberQuery("tools:catalog", "tools", maxAgeMs = 300_000) { toolCatalog() }
    val r = refresher(sum, log, mcp, accounts, catalog)
    val action = rememberAction()

    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("ابزارها و اینترنت", eyebrow = "تصمیم تو: اینترنت کامل برای ایجنت‌ها؛ مهم برآیند و کیفیت کار است") }
        item { Text("جستجو، خواندن، مرورگر کامل و API بیرونی از درگاه خروجی؛ شبکه‌ی خصوصی و سرورهای همسایه بسته‌اند؛ تعهد بیرونی به نام هلدینگ (پرداخت، انتشار، پیام به آدم بیرونی، ساخت حساب) کارت تصمیم میشود.", style = Divan.type.small, color = c.textSecondary) }
        item {
            val s = sum.data
            if (s == null) Skeleton(Modifier.fillMaxWidth().height(200.dp), radius = 14.dp)
            else Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                val top = s.byTool.entries.maxByOrNull { it.value }
                com.coinepro.hq.designsystem.StatRow(gap = 10.dp) {
                    StatTile("درخواست امروز", String.format(Locale.US, "%,d", s.requests), Modifier.weight(1f), subRich = buildAnnotatedString { fig("${s.bytesIn / 1_000_000} MB") })
                    StatTile("مسدودشده", s.blocked.toString(), Modifier.weight(1f), sub = "شبکه‌ی خصوصی، داده‌ی داخلی، سقف", tone = if (s.blocked > 0) Tone.WARN else null)
                }
                com.coinepro.hq.designsystem.StatRow(gap = 10.dp) {
                    StatTile("به مُهر تو رسید", s.needsOwner?.toString() ?: "—", Modifier.weight(1f), sub = "تعهد بیرونی ← کارت تصمیم")
                    if (top == null && s.hosts != null) StatTile("مقصدهای متفاوت", s.hosts.toString(), Modifier.weight(1f), sub = "میزبان‌هایی که امروز خوانده شدند")
                    else StatTile("بیشترین ابزار", top?.key ?: "—", Modifier.weight(1f), subRich = top?.let { t -> buildAnnotatedString { fig(String.format(Locale.US, "%,d", t.value)); append(" درخواست") } })
                }
            }
        }
        item { SectionTitle("آخرین درخواست‌ها", note = "هر درخواست با ایجنت، ابزار، مقصد و نتیجه ثبت میشود") }
        item {
            val items = log.data
            if (items == null) Skeleton(Modifier.fillMaxWidth().height(200.dp), radius = 14.dp)
            else HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(horizontal = 12.dp, vertical = 4.dp)) {
                items.forEachIndexed { i, e ->
                    if (i > 0) HorizontalDivider(color = c.lineDivider)
                    Row(Modifier.padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text(jTime(e.at), style = Divan.type.micro, color = c.textMuted, modifier = Modifier.width(34.dp))
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Fig("${e.method} ${e.host}", style = Divan.type.figureSmall, color = c.textPrimary)
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                CompanyMark(e.company, height = 11.dp, mono = true, ink = c.textMuted)
                                Fig(e.actor, style = Divan.type.figureSmall, color = c.textSecondary)
                                Fig(e.tool, style = Divan.type.figureSmall, color = c.textMuted)
                            }
                        }
                        val b = e.blockedReason
                        when {
                            b == null -> Fig(e.status.toString(), style = Divan.type.figureSmall, color = if (e.status < 400) c.positive else c.negative)
                            b.startsWith("needs_owner") -> Pill("به مُهر تو", Tone.GOLD, dot = true)
                            else -> Pill(BLOCK_FA[b] ?: b, Tone.NEG, dot = true)
                        }
                    }
                }
            }
        }
        // ⟨1.5⟩ §21.7: a new model connection, sealed on its body; its key by the app or the owner's terminal.
        item { ConnectionsCard() }
        item { SectionTitle("سرورهای MCP", note = "فقط با مُهر تو روشن میشوند؛ ابزار تازه‌ی هر سرور دوباره مُهر میخواهد") }
        val servers = mcp.data
        if (servers == null) item { Skeleton(Modifier.fillMaxWidth().height(160.dp), radius = 14.dp) }
        else items(servers.size, key = { servers[it].key }) { i ->
            val m = servers[i]
            val pending = m.status == "pending"
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(if (pending) c.softGold else c.card).padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    DIcon(DivanIcon.SERVER, size = 16.dp, tint = c.textSecondary)
                    Text(m.titleFa, style = Divan.type.bodyStrong, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                    // ⟨1.5⟩ §21.11: a server in its own container on hq-mcp (pinned digest, no route out).
                    if (m.transport == "container") Pill("کانتینر", Tone.SILVER, icon = DivanIcon.SERVER)
                    when (m.status) {
                        "enabled" -> Pill("روشن", Tone.POS, dot = true)
                        "pending" -> Pill("منتظر مُهر", Tone.GOLD, dot = true)
                        else -> Pill("خاموش", dot = true)
                    }
                }
                FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    for (t in m.tools) Tag("${t.name} · ${t.`class`}", figure = true)
                }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    val cos = companiesOf(m.companies)
                    if (cos == null) Text("همه‌ی شرکت‌ها", style = Divan.type.micro, color = c.textMuted)
                    else for (k in cos) CompanyMark(k, height = 12.dp, mono = true, ink = c.textMuted)
                    androidx.compose.foundation.layout.Spacer(Modifier.weight(1f))
                    if (m.status == "enabled") HqButton("خاموش کن", {
                        action.run { env.api.disableMcp(m.key); env.cache.invalidate("tools") }
                    }, variant = BtnVariant.GHOST, size = BtnSize.SM)
                    else HqButton("مُهر و روشن", {
                        action.run {
                            env.api.enableMcp(m.key) { a, t -> env.auth.stepUp(act, a, t) }
                            env.cache.invalidate("tools")
                            toasts.ok("روشن شد.")
                        }
                    }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.SEAL, loading = action.busy)
                }
            }
        }
        item { SectionTitle("حساب‌های سرویس", note = "رمزشان را خودت روی سرور میگذاری؛ در لحظه‌ی خروج تزریق میشود و مدل نمیبیند") }
        item {
            val list = accounts.data
            if (list == null) Skeleton(Modifier.fillMaxWidth().height(100.dp), radius = 14.dp)
            else HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(horizontal = 14.dp, vertical = 4.dp)) {
                list.forEachIndexed { i, a ->
                    if (i > 0) HorizontalDivider(color = c.lineDivider)
                    Row(Modifier.padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        DIcon(DivanIcon.LOCK, size = 16.dp, tint = if (a.hasSecret) c.positive else c.textMuted)
                        Column(Modifier.weight(1f)) {
                            Text(a.titleFa, style = Divan.type.small)
                            Fig(a.site, style = Divan.type.figureSmall, color = c.textMuted)
                        }
                        if (a.hasSecret) Text(a.lastUsedAt?.let(::ago) ?: "آماده", style = Divan.type.micro, color = c.textMuted)
                        else Fig("make account-secret KEY=${a.key}", style = Divan.type.figureSmall, color = c.textMuted)
                    }
                }
            }
        }
        // ⟨1.5⟩ §19.8: the signed webhooks from outside (Telegram, Chatwoot, product events) beside the service accounts.
        item { IntakeCard() }
        item { SectionTitle("فهرست ابزارها", note = "کلاس هر ابزار و نقش‌هایی که آن را دارند") }
        item {
            val list = catalog.data
            if (list == null) Skeleton(Modifier.fillMaxWidth().height(200.dp), radius = 14.dp)
            else HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(horizontal = 14.dp, vertical = 4.dp)) {
                list.forEachIndexed { i, t ->
                    if (i > 0) HorizontalDivider(color = c.lineDivider)
                    Column(Modifier.padding(vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            Fig(t.name, Modifier.weight(1f), style = Divan.type.figureSmall, color = c.textPrimary)
                            Fig(t.`class`, style = Divan.type.figureSmall, color = c.goldInk)
                        }
                        Text(t.roles.joinToString("، ") { roleFa(it) }, style = Divan.type.micro, color = c.textMuted, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    }
                }
            }
        }
    }
}
