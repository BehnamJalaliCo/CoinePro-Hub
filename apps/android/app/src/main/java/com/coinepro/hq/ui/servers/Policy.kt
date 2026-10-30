package com.coinepro.hq.ui.servers

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.background
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.net.FREE_ON_SERVERS
import com.coinepro.hq.core.net.SEAL_CATEGORIES
import com.coinepro.hq.core.net.ServerPolicy
import com.coinepro.hq.core.net.sealCategory
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery

/**
 * «قوانین سرورها» (§26.3, `GET/PUT /control/server-policy`): everything on the companies' servers runs free; only the categories switched
 * on here wait for the owner's seal. A change is saved with the passkey on the exact body.
 */
@Composable
fun ServerPolicyScreen(draft0: ServerPolicy? = null) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val q = rememberQuery("server-policy", "servers", "control") { serverPolicy() }
    val save = rememberAction()
    var draft by remember(q.data) { mutableStateOf(draft0 ?: q.data) }
    val r = refresher(q)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item(key = "header") { PageHeader("قوانین سرورها", eyebrow = "کنترل بی‌اصطکاک سرورهای شرکت‌ها") }
        item(key = "free") {
            HqCard(Modifier.fillMaxWidth(), color = c.softPositive) {
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    DIcon(DivanIcon.RESUME, size = 20.dp, tint = c.positive)
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text("بقیه‌ی کارها آزاد است، بی‌کارت", style = Divan.type.bodyStrong)
                        Text("ایجنت‌ها هر کاری را که از شرکت بخواهی روی سرورها انجام میدهند؛ هر فراخوانی با فرمانش (رمزها ماسک‌شده) در Audit میماند و تو در «فعالیت» هر سرور زنده میبینی.", style = Divan.type.caption, color = c.textSecondary)
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            for (f in FREE_ON_SERVERS) Text(f, style = Divan.type.micro, color = c.textPrimary, modifier = Modifier.clip(RoundedCornerShape(8.dp)).background(c.card).padding(horizontal = 8.dp, vertical = 3.dp))
                        }
                    }
                }
            }
        }
        item(key = "rules") {
            val d = draft
            when {
                d == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
                d == null -> Skeleton(Modifier.fillMaxWidth().height(420.dp), radius = 16.dp)
                else -> PolicyRules(d) { key, on -> draft = d.with(key, on) }
            }
        }
        item(key = "save") {
            val base = q.data
            val d = draft
            val changes = if (base != null && d != null) base.changes(d) else emptyList()
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (changes.isNotEmpty()) for ((k, on) in changes) Text(
                    (if (on) "منتظر مُهر میشود: " else "بدون مُهر اجرا میشود: ") + (sealCategory(k)?.titleFa ?: k),
                    style = Divan.type.caption, color = if (on) c.goldInk else c.warning,
                )
                HqButton(
                    "با گذرکلید ذخیره کن", {
                        save.run(onError = { toasts.error(com.coinepro.hq.core.net.serverError(it)) }) {
                            val out = env.api.putServerPolicy(d!!) { a, t -> env.auth.stepUp(act, a, t) }
                            q.set(out)
                            env.cache.invalidate("servers")
                            toasts.ok("قوانین سرورها ذخیره شد.")
                        }
                    },
                    Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEAL, enabled = changes.isNotEmpty(), loading = save.busy,
                )
                if (changes.isNotEmpty()) HqButton("برگرداندن", { draft = base }, Modifier.fillMaxWidth(), variant = BtnVariant.GHOST, size = BtnSize.SM)
                Text("هشدار: دسته‌ای که خاموش کنی، از همان لحظه بی‌مُهر تو روی همه‌ی سرورهای همه‌ی شرکت‌ها اجرا میشود.", style = Divan.type.micro, color = c.textMuted)
            }
        }
    }
}

@Composable
fun PolicyRules(p: ServerPolicy, onToggle: (String, Boolean) -> Unit) {
    val c = Divan.colors
    val nav = LocalNav.current
    HqCard(Modifier.fillMaxWidth(), padding = androidx.compose.foundation.layout.PaddingValues(horizontal = 14.dp, vertical = 6.dp)) {
        Row(Modifier.padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("فقط این‌ها منتظر مُهر تو میمانند", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk, modifier = Modifier.weight(1f))
            Text("${p.sealRequired.count { k -> SEAL_CATEGORIES.any { it.key == k } }} از ${SEAL_CATEGORIES.size}", style = Divan.type.caption, color = c.textMuted)
        }
        SEAL_CATEGORIES.forEach { cat ->
            HorizontalDivider(color = c.lineDivider)
            Row(Modifier.fillMaxWidth().padding(vertical = 12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text(cat.titleFa, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                    Fig(cat.catches, style = Divan.type.figureSmall, color = c.textMuted, maxLines = 2)
                    Text(cat.whyFa, style = Divan.type.micro, color = c.textMuted)
                }
                HqSwitch(p.requires(cat.key), { onToggle(cat.key, it) }, label = cat.titleFa)
            }
        }
        HorizontalDivider(color = c.lineDivider)
        Text("دروازه هم از روی ابزار و هم از روی الگوی فرمان میگیرد؛ در Claude Code روی سرور هم همین الگوها پیش از اجرا جلویش را میگیرند و کارتش به کارتابل میاید.", Modifier.padding(vertical = 10.dp), style = Divan.type.micro, color = c.textMuted)
        HqButton("کارتابل", { nav.go("cartable") }, Modifier.padding(bottom = 6.dp), variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.CARTABLE)
    }
}

/** The row on «تنظیمات» and «کنترل» that opens the server rules. */
@Composable
fun ServerPolicyLink(modifier: Modifier = Modifier) {
    val nav = LocalNav.current
    val c = Divan.colors
    val q = rememberQuery("server-policy", "servers", "control", maxAgeMs = 120_000) { serverPolicy() }
    val servers = rememberServers()
    HqCard(modifier.fillMaxWidth(), onClick = { nav.go("server-policy") }, onClickLabel = "قوانین سرورها") {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            com.coinepro.hq.ui.v17.IconTile(DivanIcon.SERVER, c.goldInk, size = 40.dp)
            Column(Modifier.weight(1f)) {
                Text("سرورها و قوانینشان", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                Text(
                    listOfNotNull(
                        servers.data?.let { "${it.size} سرور" },
                        q.data?.let { "${it.sealRequired.size} کار ویرانگر منتظر مُهر؛ بقیه آزاد" },
                    ).joinToString("، ").ifBlank { "همه چیز آزاد، جز کارهای ویرانگر" },
                    style = Divan.type.caption, color = c.textMuted,
                )
            }
            HqButton("همه‌ی سرورها", { nav.go("servers") }, variant = BtnVariant.TEXT, size = BtnSize.SM)
        }
    }
}
