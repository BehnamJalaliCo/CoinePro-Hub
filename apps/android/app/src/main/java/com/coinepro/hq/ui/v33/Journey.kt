package com.coinepro.hq.ui.v33

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import com.coinepro.hq.designsystem.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.EVIDENCE_KIND_FA
import com.coinepro.hq.core.data.evidenceRoute
import com.coinepro.hq.core.data.journeyCurrentIndex
import com.coinepro.hq.core.data.journeyReached
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.Journey
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BarTone
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.MeterBar
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.Para
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.served

// Contract §33.8 ⟨1.15⟩ «مسیر شرکت»: where a company stands on its way, from founded to break-even. Each stage is reached by code from
// existing rows, with its evidence (a tap opens it); the next step is one line written when a stage changes.

/** The company's «مسیر» tab. */
@Composable
fun CompanyJourney(code: String) {
    val q = rememberQuery("journey:$code", "journey", "money", maxAgeMs = 60_000) { gated(HubFeature.JOURNEY) { journey(code) } }
    val has = served(HubFeature.JOURNEY)
    val j = q.data
    when {
        !has -> Empty("مسیر شرکت با به‌روزرسانی بعدی هاب میاید", icon = DivanIcon.FOUND)
        j == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
        j == null -> Skeleton(Modifier.fillMaxWidth().height(360.dp), radius = 16.dp)
        else -> JourneyCard(j)
    }
}

/** A journey: how far, what comes next, and every stage with when it was reached and why. */
@Composable
fun JourneyCard(j: Journey, compact: Boolean = false) {
    val c = Divan.colors
    val nav = LocalNav.current
    val companies = rememberCompanies()
    val cur = journeyCurrentIndex(j)
    val reached = journeyReached(j)
    val current = j.stages.getOrNull(cur)
    HqCard(Modifier.fillMaxWidth(), tahrir = !compact, onClick = if (compact) ({ nav.go("companies/${j.company}/journey") }) else null) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(if (compact) companyOf(companies, j.company).nameFa else "مسیر شرکت", style = Divan.type.bodyStrong)
                Text(
                    plain("مرحله‌ی ${reached} از ${j.stages.size}" + (current?.let { "، «${it.titleFa}»" } ?: "") + if (j.daysInStage > 0) "، ${j.daysInStage} روز در این مرحله" else ""),
                    style = Divan.type.caption, color = c.textMuted,
                )
            }
        }
        MeterBar(if (j.stages.isEmpty()) 0.0 else reached * 100.0 / j.stages.size, Modifier.padding(top = 10.dp), tone = BarTone.SILVER, height = 6.dp)
        j.nextFa?.takeIf { it.isNotBlank() }?.let {
            Column(Modifier.padding(top = 12.dp).fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.softGold).padding(12.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text("قدم بعدی", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.silverInk)
                Para(it, style = Divan.type.small, color = c.textPrimary)
            }
        }
        if (!compact) Column(Modifier.padding(top = 14.dp)) {
            j.stages.forEachIndexed { i, s ->
                val done = s.reachedAt != null
                val isCur = i == cur
                val route = evidenceRoute(j.company, s)
                Row(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp))
                        .then(if (route != null && done) Modifier.clickable(role = Role.Button, onClickLabel = "ببین") { nav.go(route) } else Modifier)
                        .padding(vertical = 2.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    // The rail: a dot per stage, joined by a line; reached stages are filled, the current one ringed.
                    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.width(22.dp)) {
                        Box(
                            Modifier.size(if (isCur) 18.dp else 14.dp).clip(CircleShape)
                                .background(if (done) c.goldFill else c.tile)
                                .then(if (isCur) Modifier.border(2.dp, c.goldInk, CircleShape) else Modifier),
                            contentAlignment = Alignment.Center,
                        ) { if (done) DIcon(DivanIcon.SEAL, size = 9.dp, tint = c.onGold) }
                        if (i < j.stages.lastIndex) Box(Modifier.width(2.dp).height(34.dp).background(if (j.stages[i + 1].reachedAt != null) c.goldFill else c.lineDivider))
                    }
                    Column(Modifier.weight(1f).padding(bottom = 8.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(plain(s.titleFa), style = Divan.type.small.copy(fontWeight = if (isCur) FontWeight.Bold else FontWeight.SemiBold), color = if (done) c.textPrimary else c.textMuted)
                        val ev = s.evidence?.let { e -> EVIDENCE_KIND_FA[e.kind]?.let { k -> k + (e.ref?.takeIf { r -> r.isNotBlank() && r.length < 16 }?.let { " $it" } ?: "") } }
                        Text(
                            plain(if (done) listOfNotNull(jDate(s.reachedAt, withYear = true), ev).joinToString(" · ") else "هنوز نه"),
                            style = Divan.type.micro, color = if (route != null && done) c.goldInk else c.textMuted,
                        )
                    }
                }
            }
        }
    }
}

/** «مسیر شرکت‌ها»: every company's journey in one place, and every stage reached on one timeline, newest first. */
@Composable
fun JourneysScreen() {
    val nav = LocalNav.current
    val c = Divan.colors
    val companies = rememberCompanies()
    val q = rememberQuery("journeys", "journey", "money", maxAgeMs = 60_000) { gated(HubFeature.JOURNEY) { journeys() } }
    val r = refresher(q)
    val has = served(HubFeature.JOURNEY)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("مسیر شرکت‌ها", eyebrow = "هر شرکت کجای راه است: از تأسیس تا سربه‌سر شدن") }
        val b = q.data
        when {
            !has -> item { Empty("مسیر شرکت‌ها با به‌روزرسانی بعدی هاب میاید", icon = DivanIcon.FOUND) }
            b == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            b == null -> item { Skeleton(Modifier.fillMaxWidth().height(300.dp), radius = 16.dp) }
            b.journeys.isEmpty() -> item { Empty("هنوز شرکتی نیست", icon = DivanIcon.COMPANIES) }
            else -> {
                items(b.journeys.size, key = { "j-" + b.journeys[it].company }) { i -> JourneyCard(b.journeys[i], compact = true) }
                if (b.timeline.isNotEmpty()) item(key = "timeline") {
                    HqCard(Modifier.fillMaxWidth()) {
                        SectionTitle("خط زمان", note = "هر مرحله‌ای که شرکتی به آن رسید، تازه‌ترین اول")
                        Column(Modifier.padding(top = 8.dp)) {
                            b.timeline.take(60).forEachIndexed { i, e ->
                                if (i > 0) HorizontalDivider(color = c.lineDivider)
                                Row(
                                    Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).clickable(role = Role.Button) { nav.go("companies/${e.company}/journey") }.padding(vertical = 10.dp, horizontal = 4.dp),
                                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
                                ) {
                                    Box(Modifier.size(8.dp).clip(CircleShape).background(c.goldFill))
                                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                        Text(plain("${companyOf(companies, e.company).nameFa} به «${e.titleFa}» رسید"), style = Divan.type.small, color = c.textPrimary)
                                        Text(plain(jDate(e.at, withYear = true)), style = Divan.type.micro, color = c.textMuted)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
