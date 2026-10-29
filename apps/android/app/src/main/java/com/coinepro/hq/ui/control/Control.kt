package com.coinepro.hq.ui.control

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.Space
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.companies.CompanyControlCard
import com.coinepro.hq.ui.companies.ControlSheets
import com.coinepro.hq.ui.companies.HoldingControlCard
import com.coinepro.hq.ui.companies.rememberControlData
import com.coinepro.hq.ui.companies.rememberControlUi
import com.coinepro.hq.ui.itemMotion
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.v14.BackupsCard
import com.coinepro.hq.ui.v17.IconTile

/** Control (OPERATING_MODEL §1.12, contract §9): the holding's kill switch, the one that stops everything, then every company with
 *  its switch and its deploys. Stopping is instant (speed matters); resuming and opening deploys take the passkey; a switch the owner
 *  engaged is released only by the owner. The same cards and sheets as the companies list. Then backups and the authority matrix. */
@Composable
fun ControlScreen() {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val c = Divan.colors
    val q = rememberQuery("companies", "companies", maxAgeMs = 30_000) { companies() }
    val d = rememberControlData()
    val ui = rememberControlUi()
    val r = refresher(q)
    Page(onRefresh = { r.refresh(); env.cache.invalidate("control", "runs", "treasury", "backups") }, refreshing = r.refreshing) {
        item(key = "header") { PageHeader("کنترل", eyebrow = "کلید توقف و deploy، برای کل هلدینگ و هر شرکت") }
        val list = q.data
        when {
            list == null && q.error == null -> items(3, key = { "skeleton-$it" }) { Skeleton(Modifier.fillMaxWidth().height(if (it == 0) 236.dp else 222.dp), radius = 16.dp) }
            list == null -> item(key = "error") { ErrorBlock(q.error, { q.refresh() }) }
            else -> {
                val holding = list.firstOrNull { it.kind == "holding" }
                if (holding != null) item(key = holding.code) { HoldingControlCard(holding, list, d, ui, itemMotion()) { nav.go("companies/${holding.code}") } }
                item(key = "companies-title") {
                    SectionTitle("شرکت‌ها", note = "مدیرعامل هر شرکت هم میتواند کلید شرکت خودش را بزند؛ کلیدی را که تو زده‌ای فقط خودت آزاد میکنی.")
                }
                items(list.filter { it.kind != "holding" }, key = { it.code }) { co ->
                    CompanyControlCard(co, d, ui, holding?.nameFa, itemMotion()) { nav.go("companies/${co.code}") }
                }
            }
        }
        item(key = "backups") { BackupsCard() }
        // ⟨1.5⟩ §20.7: who may do what, and up to how much, lives in the authority matrix.
        item(key = "authority") {
            HqCard(Modifier.fillMaxWidth(), onClick = { nav.go("authority") }) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Space.sm)) {
                    IconTile(DivanIcon.LOCK, c.goldInk, size = 40.dp)
                    Column(Modifier.weight(1f)) {
                        Text("ماتریس اختیار", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                        Text("سقف‌ها، سهمیه‌ها و این‌که چه کسی تأیید میکند؛ ثابت‌های قفل مستقل از داده‌اند.", style = Divan.type.caption, color = c.textMuted)
                    }
                    DIcon(DivanIcon.NEXT, size = 18.dp, tint = c.textMuted)
                }
            }
        }
    }
    ControlSheets(ui)
}
