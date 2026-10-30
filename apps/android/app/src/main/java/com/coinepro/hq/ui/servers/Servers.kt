package com.coinepro.hq.ui.servers

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.net.HubServer
import com.coinepro.hq.core.net.SERVER_DESTRUCTIVE
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.StatRow
import com.coinepro.hq.designsystem.StatTile
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.itemMotion
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery

/** The pending cards of destructive commands, from the cartable's own query (§26.3). */
@Composable
private fun rememberSeals(company: String? = null) =
    rememberQuery("decisions:pending", "decisions") { decisions("pending") }.data?.items.orEmpty()
        .filter { it.kind == SERVER_DESTRUCTIVE && (company == null || it.company == company) }

/** The owner's own words on what the holding may do on a server, shown above every server list. */
@Composable
fun ServersIntro(modifier: Modifier = Modifier) {
    val nav = LocalNav.current
    val c = Divan.colors
    Column(modifier, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(
            "ایجنت‌ها روی این سرورها کد میزنند، commit و push و deploy میکنند و هر کاری را که از شرکت بخواهی انجام میدهند؛ هر فراخوانی با فرمانش در Audit ثبت میشود. فقط شش کار ویرانگر منتظر مُهر تو میمانند.",
            style = Divan.type.small, color = c.textSecondary,
        )
        HqButton("قوانین سرورها", { nav.go("server-policy") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.LOCK)
    }
}

/** «همه‌ی سرورها» (the tools sheet): every company's servers, the cards waiting for the seal first, then each company's servers. */
@Composable
fun ServersScreen() {
    val nav = LocalNav.current
    val c = Divan.colors
    val q = rememberServers()
    val companies = rememberCompanies()
    val seals = rememberSeals()
    val r = refresher(q)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item(key = "header") {
            PageHeader("همه‌ی سرورها", eyebrow = "دسترسی کامل هلدینگ به سرورهای شرکت‌ها") {
                HqButton("وصل کردن", { nav.go("servers-attach") }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.ADD)
            }
        }
        item(key = "intro") { ServersIntro() }
        val list = q.data
        if (list != null && list.isNotEmpty()) item(key = "stats") {
            StatRow {
                StatTile("سرور", list.size.toString(), Modifier.weight(1f), figure = false)
                StatTile("در دسترس", list.count { it.reachable }.toString(), Modifier.weight(1f), figure = false, tone = com.coinepro.hq.core.format.Tone.POS)
                StatTile("منتظر مُهر", seals.size.toString(), Modifier.weight(1f), figure = false, tone = if (seals.isNotEmpty()) com.coinepro.hq.core.format.Tone.GOLD else null)
            }
        }
        if (seals.isNotEmpty()) item(key = "seals") { SealCards(seals) }
        when {
            list == null && q.error == null -> items(3, key = { "sk$it" }) { Skeleton(Modifier.fillMaxWidth().height(150.dp), radius = 16.dp) }
            list == null -> item(key = "error") { ErrorBlock(q.error, { q.refresh() }) }
            list.isEmpty() -> item(key = "empty") {
                Empty("هنوز سروری وصل نیست", icon = DivanIcon.SERVER, body = "سرور هر شرکت را با «وصل کردن» به هاب بده؛ Claude همان سرور با فایل راهنما آماده‌اش میکند.") {
                    HqButton("وصل کردن سرور", { nav.go("servers-attach") }, variant = BtnVariant.PRIMARY, icon = DivanIcon.ADD)
                }
            }
            else -> {
                // Companies are data: one group per company that has servers, in the companies' own order.
                val order = companies.map { it.code }
                val groups = list.groupBy { it.company }.toList().sortedBy { (co, _) -> order.indexOf(co).let { if (it < 0) Int.MAX_VALUE else it } }
                for ((co, servers) in groups) {
                    item(key = "co-$co") {
                        SectionTitle(companyOf(companies, co).nameFa, note = "${servers.size} سرور") {
                            CompanyMark(co, height = 14.dp, mono = true, ink = c.textSecondary)
                        }
                    }
                    items(servers.size, key = { "s-" + servers[it].id }) { i ->
                        val s = servers[i]
                        Box(itemMotion()) { ServerCard(s, rememberLocked(s.company)) { nav.go("servers/${s.id}") } }
                    }
                }
            }
        }
    }
}

/** The company page's «سرورها» tab: locked when the company is stopped, its seal cards, its servers, a task and attaching one. */
@Composable
fun CompanyServers(code: String) {
    val nav = LocalNav.current
    val c = Divan.colors
    val q = rememberServers()
    val locked = rememberLocked(code)
    val seals = rememberSeals(code)
    var task by remember { mutableStateOf(false) }
    val list = q.data?.filter { it.company == code }
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        if (locked) LockedBanner(code)
        ServersIntro()
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            HqButton("یک کار بسپار", { task = true }, Modifier.weight(1f), variant = BtnVariant.PRIMARY, icon = DivanIcon.CODE, enabled = !locked && list.orEmpty().any { it.reachable })
            HqButton("وصل کردن سرور", { nav.go("servers-attach/$code") }, icon = DivanIcon.ADD)
        }
        if (seals.isNotEmpty()) SealCards(seals)
        when {
            list == null && q.error == null -> Skeleton(Modifier.fillMaxWidth().height(160.dp), radius = 16.dp)
            list == null -> ErrorBlock(q.error, { q.refresh() })
            list.isEmpty() -> Empty("این شرکت هنوز سروری به هاب نداده", icon = DivanIcon.SERVER, body = "با «وصل کردن سرور» آدرس خصوصی و کاربر کاری را بده؛ کلید عمومی هاب را به Claude همان سرور میدهی.")
            else -> for (s in list) ServerCard(s, locked) { nav.go("servers/${s.id}") }
        }
        Text(buildAnnotatedString {
            append("هر سرور با کاربر کاری خودش و یک کلید جدا از شبکه‌ی خصوصی وصل است؛ کلید خصوصی فقط در OpenBao میماند. ")
            fig("SSH")
            append(" روی شبکه‌ی خصوصی رمز شده است.")
        }, style = Divan.type.micro, color = c.textMuted)
    }
    if (task && list != null) ServerTaskSheet(list.filter { it.reachable }, null) { task = false }
}

/** Which server of a list a task goes to, when the owner has not chosen yet: the only reachable one, else none. */
internal fun defaultServer(list: List<HubServer>, chosen: String?): HubServer? = list.firstOrNull { it.id == chosen } ?: list.singleOrNull()
