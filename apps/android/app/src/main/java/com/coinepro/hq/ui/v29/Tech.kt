package com.coinepro.hq.ui.v29

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.Finding
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery

// Contract §29.1 ⟨1.11⟩: where the technical goes. Servers, the network, the watch, the error reader and the technical findings of a
// company live only here, under «شرکت ← فنی»; they are handled by the company's own technical manager, and only a critical item (a data
// leak, a product down, money, legal) reaches the owner's home.

/** The company's «فنی» tab: the note on who handles it, the catalogue, the technical findings and the servers. */
@Composable
fun CompanyTech(code: String) {
    val c = Divan.colors
    val nav = LocalNav.current
    val name = companyOf(rememberCompanies(), code).nameFa
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Text(
            "کارهای فنی $name پیش مدیر فنی و مسئول پایداری همین شرکت میرود و همان‌ها درستش میکنند. به خانه‌ی تو فقط چیزی میرسد که بحرانی باشد: نشت داده، از دسترس افتادن محصول، پول یا موضوع حقوقی. خلاصه‌ی فنی هفته هم شنبه‌ها میاید.",
            style = Divan.type.caption.copy(textAlign = TextAlign.Justify), color = c.textMuted,
        )
        com.coinepro.hq.ui.servers.CompanyServers(code)
        TechFindingsCard(code)
        com.coinepro.hq.ui.companies.CatalogueCard(code, name)
        HqButton("دیده‌بان همه‌ی شرکت‌ها", { nav.go("watch") }, Modifier.fillMaxWidth(), variant = BtnVariant.GHOST, icon = DivanIcon.SCOPE)
    }
}

/** The company's technical findings (tech, infra, security), not only what reaches the owner; each opens with its fix. */
@Composable
private fun TechFindingsCard(code: String) {
    val c = Divan.colors
    val nav = LocalNav.current
    val q = rememberQuery("tech-findings:$code", "oversight", maxAgeMs = 30_000) { techFindings(code) }
    var open by rememberSaveable(code) { mutableStateOf<String?>(null) }
    // A hub before ⟨1.11⟩ ignores `scope` and `domain`: the list is narrowed here too.
    val list = q.data?.filter { it.company == code && (it.domain == null || it.domain in Api.TECH_DOMAINS) }
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("یافته‌های فنی", note = list?.let { l -> if (l.none { live(it) }) "یافته‌ی بازی نیست" else "${l.count { live(it) }} یافته‌ی باز؛ پیش مدیر فنی شرکت" }, icon = DivanIcon.SCOPE)
        Column(Modifier.padding(top = 6.dp)) {
            when {
                list == null && q.error != null -> Text(q.error?.messageFa.orEmpty(), style = Divan.type.caption, color = c.negative)
                list == null -> Skeleton(Modifier.fillMaxWidth().height(80.dp))
                list.isEmpty() -> Text("یافته‌ای ثبت نشده.", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.padding(vertical = 8.dp))
                else -> list.take(12).forEachIndexed { i, f ->
                    if (i > 0) HorizontalDivider(color = c.lineDivider)
                    Row(
                        Modifier.fillMaxWidth().clickable(role = Role.Button, onClickLabel = "جزئیات") { open = f.ref }.padding(vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        com.coinepro.hq.ui.v14.SeverityPill(f.severity)
                        Column(Modifier.weight(1f)) {
                            Text(plain(f.titleFa), style = Divan.type.small, maxLines = 2, overflow = TextOverflow.Ellipsis)
                            Text(plain(listOfNotNull(com.coinepro.hq.ui.v14.FINDING_STATUS[f.status]?.fa, ago(f.openedAt)).joinToString(" · ")), style = Divan.type.micro, color = c.textMuted)
                        }
                    }
                }
            }
        }
        if ((list?.size ?: 0) > 12) HqButton("همه در دیده‌بان", { nav.go("watch") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.NEXT)
    }
    open?.let { ref -> list?.firstOrNull { it.ref == ref }?.let { f -> com.coinepro.hq.ui.oversight.FindingSheet(f) { open = null } } }
}

private fun live(f: Finding): Boolean = f.status !in setOf("closed", "verified")
