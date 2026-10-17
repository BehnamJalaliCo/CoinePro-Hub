package com.coinepro.hq.ui.workshop

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.actorFa
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.until
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.core.net.CodeSession
import com.coinepro.hq.core.net.Grant
import com.coinepro.hq.core.net.Workspace
import com.coinepro.hq.designsystem.Avatar
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.MeterBar
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.budgetTone
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.QueryHandle
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery

data class StateLabel(val fa: String, val tone: Tone, val live: Boolean = false)

val SESSION_STATE = mapOf(
    "starting" to StateLabel("در حال شروع", Tone.LAPIS, live = true),
    "working" to StateLabel("در حال کار", Tone.POS, live = true),
    "waiting_approval" to StateLabel("منتظر اجازه‌ی تو", Tone.GOLD),
    "idle" to StateLabel("منتظر راهنمایی", Tone.NEUTRAL),
    "done" to StateLabel("تمام شد", Tone.SILVER),
    "failed" to StateLabel("خطا", Tone.NEG),
    "stopped" to StateLabel("متوقف", Tone.WARN),
)

val ACTION_FA = linkedMapOf(
    "read" to "خواندن کد", "edit" to "ویرایش", "run" to "اجرای تست و فرمان", "push_branch" to "push به شاخه‌ی جدا", "open_pr" to "باز کردن PR",
)

@Composable
fun StatePill(state: String) {
    val s = SESSION_STATE[state] ?: StateLabel(state, Tone.NEUTRAL)
    Pill(s.fa, s.tone, live = s.live, dot = !s.live)
}

fun companyOf(workspaces: List<Workspace>?, code: String): String = workspaces?.firstOrNull { it.code == code }?.company ?: code.substringBefore('-')

@Composable
fun rememberWorkspaces(): QueryHandle<List<Workspace>> = rememberQuery("workshop:workspaces", "workshop", maxAgeMs = 60_000) { workspaces() }

@Composable
fun rememberGrants(): QueryHandle<List<Grant>> = rememberQuery("workshop:grants", "workshop") { grants(active = true) }

@Composable
fun rememberSessions(): QueryHandle<List<CodeSession>> = rememberQuery("workshop:sessions", "workshop", maxAgeMs = 10_000) { sessions().items }

/** One session in a list: where, what, who drives it, what it has cost. */
@Composable
fun SessionRow(s: CodeSession, workspaces: List<Workspace>?, grant: Grant?, onClick: () -> Unit) {
    val c = Divan.colors
    val ws = workspaces?.firstOrNull { it.code == s.workspace }
    val waiting = s.state == "waiting_approval"
    val shape = RoundedCornerShape(14.dp)
    Column(
        Modifier.fillMaxWidth().clip(shape).background(if (waiting) c.softGold else c.tile)
            .then(if (waiting) Modifier.border(1.dp, c.goldInk.copy(alpha = 0.45f), shape) else Modifier)
            .clickable(role = Role.Button, onClick = onClick).padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            CompanyMark(companyOf(workspaces, s.workspace), height = 15.dp, mono = true, ink = c.textSecondary, modifier = Modifier.padding(top = 3.dp))
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(s.title, style = Divan.type.bodyStrong, maxLines = 2, overflow = TextOverflow.Ellipsis)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Fig(s.ref, style = Divan.type.figureSmall, color = c.textMuted)
                    Fig(ws?.repo?.substringAfter('/') ?: s.workspace, style = Divan.type.figureSmall, color = c.textMuted)
                }
            }
            StatePill(s.state)
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Avatar(s.driver.kind, size = 20.dp, state = if (s.state == "working") "working" else "idle")
            Text(actorFa(s.driver), style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
            if (s.prUrl != null) Text("PR", style = Divan.type.caption, color = c.goldInk)
            Text(ago(s.updatedAt), style = Divan.type.micro, color = c.textMuted)
            Fig(usd(s.usage.usd) + (grant?.let { " / " + usd(it.budgetUsd, 0) } ?: ""), style = Divan.type.figureSmall, color = c.textSecondary)
        }
        if (grant != null && s.open) {
            val pct = (s.usage.usd / grant.budgetUsd * 100).coerceIn(0.0, 100.0)
            MeterBar(pct, tone = budgetTone(pct), height = 4.dp)
        }
    }
}

/** The Code Workshop (contract §17.3): managers and the chief advisor code on each company's repository under the
 *  owner's grant; the owner grants, watches live and can stop at any moment. Nothing reaches production. */
@Composable
fun WorkshopScreen(onNewSession: () -> Unit, onGrant: (String?) -> Unit) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val sessions = rememberSessions()
    val grants = rememberGrants()
    val workspaces = rememberWorkspaces()
    val meta = rememberQuery("meta", "meta", maxAgeMs = 300_000) { meta() }
    val r = refresher(sessions, grants, workspaces)
    val action = rememberAction()
    var revoke by remember { mutableStateOf<Grant?>(null) }
    val all = sessions.data.orEmpty()
    val open = all.filter { it.open }.sortedByDescending { it.state == "waiting_approval" }
    val past = all.filterNot { it.open }
    val grantOf = { ref: String -> grants.data?.firstOrNull { it.ref == ref } }

    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            PageHeader("Claude Code برای شرکت‌ها", eyebrow = "کارگاه کد") {
                if (meta.data?.workshop?.runtime != null) HqButton("جلسه‌ی تازه", onNewSession, variant = BtnVariant.PRIMARY, icon = DivanIcon.ADD)
            }
        }
        item {
            Text(
                if (meta.data?.workshop?.runtime != null) "مدیرها و مشاور کل با مجوز تو روی ریپوی هر شرکت کد میزنند. تو فقط مجوز میدهی، زنده تماشا میکنی و هر لحظه میتوانی متوقف کنی؛ هر push و PR اجازه‌ی تو را میخواهد و هیچ چیزی به production نمیرسد."
                else "جلسه‌های Claude Code در اپ Claude اجرا میشوند. مجوزها و تاریخچه‌ی کارگاه اینجا میمانند.",
                style = Divan.type.small, color = c.textSecondary,
            )
        }
        if (meta.data != null && meta.data?.workshop?.runtime == null) item {
            // The owner's own Claude Code sessions live in claude.ai/code and the Claude app; there is no official API to show them here.
            val uri = LocalUriHandler.current
            HqCard(color = c.softGold) {
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    DIcon(DivanIcon.CODE, tint = c.goldInk)
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text("جلسه‌های Claude Code تو در اپ Claude هستند", style = Divan.type.bodyStrong)
                        Text("همین گفت‌وگوها و نشست سرور، با همان اشتراک. اجرای کارگاه داخل هاب کنار گذاشته شد (تصمیم تو)؛ مجوزها و تاریخچه اینجا میمانند.", style = Divan.type.caption, color = c.textSecondary)
                    }
                }
                HqButton("باز کردن Claude Code", { uri.openUri("https://claude.ai/code") }, Modifier.fillMaxWidth().padding(top = 10.dp), variant = BtnVariant.PRIMARY, icon = DivanIcon.SHARE)
            }
        }
        item { SectionTitle("در جریان", note = "منتظرِ اجازه‌ها بالاتر") }
        when {
            sessions.data == null && sessions.error == null -> items(2) { Skeleton(Modifier.fillMaxWidth().height(110.dp), radius = 14.dp) }
            sessions.data == null -> item { ErrorBlock(sessions.error, { sessions.refresh() }) }
            open.isEmpty() -> item { Empty("جلسه‌ای در جریان نیست", icon = DivanIcon.CODE, body = "یک جلسه باز کن، یا با فرمان صوتی بگو؛ کار خودش به کارگاه میرسد.") }
            else -> items(open.size, key = { "o" + open[it].ref }) { i -> SessionRow(open[i], workspaces.data, grantOf(open[i].grant)) { nav.go("workshop/${open[i].ref}") } }
        }
        if (past.isNotEmpty()) {
            item { SectionTitle("گذشته", note = "تاریخچه و transcript کامل میماند") }
            items(past.size, key = { "p" + past[it].ref }) { i -> SessionRow(past[i], workspaces.data, grantOf(past[i].grant)) { nav.go("workshop/${past[i].ref}") } }
        }
        item {
            SectionTitle("مجوزهای تو", note = "لغو، جلسه‌هایش را همان لحظه متوقف میکند") {
                HqButton("مجوز تازه", { onGrant(null) }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.ADD)
            }
        }
        item {
            val list = grants.data
            when {
                list == null -> Skeleton(Modifier.fillMaxWidth().height(90.dp), radius = 14.dp)
                list.isEmpty() -> Text("مجوز فعالی نیست.", style = Divan.type.caption, color = c.textMuted)
                else -> Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    for (g in list) GrantCard(g, workspaces.data, all.filter { it.grant == g.ref }.sumOf { it.usage.usd }) { revoke = g }
                }
            }
        }
        item { SectionTitle("ریپوها", note = "فقط شاخه‌ی جدا و PR؛ ادغام و انتشار با مُهر تو") }
        item {
            HqCard(padding = androidx.compose.foundation.layout.PaddingValues(horizontal = 14.dp, vertical = 4.dp)) {
                workspaces.data.orEmpty().forEachIndexed { i, w ->
                    if (i > 0) HorizontalDivider(color = c.lineDivider)
                    Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        CompanyMark(w.company, height = 14.dp, mono = true, ink = c.textSecondary)
                        Column(Modifier.weight(1f)) {
                            Text(w.titleFa, style = Divan.type.small, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Fig(w.repo, style = Divan.type.figureSmall, color = c.textMuted)
                        }
                        if (w.status == "paused") Pill("متوقف", Tone.WARN, dot = true) else HqButton("مجوز", { onGrant(w.code) }, variant = BtnVariant.GHOST, size = BtnSize.SM)
                    }
                }
            }
        }
        item { PersonalSessions() }
    }

    revoke?.let { g ->
        AlertDialog(
            onDismissRequest = { revoke = null },
            containerColor = c.overlay,
            title = { Text("لغو مجوز ${g.ref}؟", style = Divan.type.h3) },
            text = { Text("جلسه‌های در جریان زیر این مجوز همین حالا متوقف میشوند. شاخه‌ها و تاریخچه میمانند.", style = Divan.type.small, color = c.textSecondary) },
            confirmButton = {
                HqButton("لغو کن", {
                    action.run {
                        env.api.revokeGrant(g.ref)
                        env.cache.invalidate("workshop")
                        revoke = null
                        toasts.ok("مجوز ${g.ref} لغو شد.")
                    }
                }, variant = BtnVariant.DANGER, loading = action.busy)
            },
            dismissButton = { HqButton("نه", { revoke = null }, variant = BtnVariant.GHOST) },
        )
    }
}

@Composable
private fun GrantCard(g: Grant, workspaces: List<Workspace>?, spent: Double, onRevoke: () -> Unit) {
    val c = Divan.colors
    val ws = workspaces?.firstOrNull { it.code == g.workspace }
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.card).padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            CompanyMark(companyOf(workspaces, g.workspace), height = 13.dp, mono = true, ink = c.textSecondary)
            Text(ws?.titleFa ?: g.workspace, style = Divan.type.small.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold), modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
            Fig(g.ref, style = Divan.type.figureSmall, color = c.textMuted)
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            for (a in g.actions) Text(ACTION_FA[a] ?: a, style = Divan.type.micro, color = c.textSecondary, modifier = Modifier.clip(CircleShape).background(c.tile).padding(horizontal = 8.dp, vertical = 2.dp))
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(g.driver?.let(::actorFa) ?: "خودت", style = Divan.type.caption, color = c.textSecondary)
            Fig("$" + String.format(java.util.Locale.US, "%.2f", spent) + " / $" + g.budgetUsd.toInt(), style = Divan.type.figureSmall, color = c.textSecondary)
            Text(until(g.expiresAt), style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f))
            Text("لغو", style = Divan.type.caption, color = c.negative, modifier = Modifier.clip(RoundedCornerShape(6.dp)).clickable(role = Role.Button, onClick = onRevoke).padding(horizontal = 6.dp, vertical = 2.dp))
        }
    }
}

/** The owner's own Claude sessions stay in the owner's Claude account (contract §17.5): linked, never stored. */
@Composable
private fun PersonalSessions() {
    val c = Divan.colors
    val context = LocalContext.current
    HqCard {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            androidx.compose.foundation.layout.Box(Modifier.size(40.dp).clip(CircleShape).background(c.softGold), contentAlignment = Alignment.Center) { DIcon(DivanIcon.CODE, size = 20.dp, tint = c.goldInk) }
            Column(Modifier.weight(1f)) {
                Text("سشن‌های خودت در Claude Code", style = Divan.type.bodyStrong)
                Text("با حساب Claude خودت", style = Divan.type.caption, color = c.textMuted)
            }
        }
        Spacer(Modifier.height(10.dp))
        Text("گفت‌وگوهای شخصی تو با Claude، مثل همانی که این اپ را ساخت، در حساب خودت میمانند. هاب آن‌ها را نگه نمیدارد و نمیخواند؛ با ورود خودت باز میشوند.", style = Divan.type.small, color = c.textSecondary)
        Spacer(Modifier.height(12.dp))
        HqButton("claude.ai/code", { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://claude.ai/code"))) }, Modifier.fillMaxWidth(), icon = DivanIcon.SHARE)
    }
}
