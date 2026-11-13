package com.coinepro.hq.ui.automation

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDirection
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.linksProblemsFa
import com.coinepro.hq.core.data.pathLinks
import com.coinepro.hq.core.data.sectionKey
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.SiteLinks
import com.coinepro.hq.core.net.SiteSection
import com.coinepro.hq.core.net.SiteUrl
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DecisionBar
import com.coinepro.hq.designsystem.DecisionState
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.IconBtn
import com.coinepro.hq.designsystem.ScrollRow
import com.coinepro.hq.designsystem.SheetBar
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.served

// Contract §59.5 ⟨1.37⟩: a company's own links (`/links` is the companies' canvas). The site, and each of its sections with a short key a
// button may name; under them the three links one section sends, one per path (comment, story, DM), each with its own UTM, built by the
// hub's code. Pro-Chart today: `pro-chart.com` (it opens `/next/` itself) and no sections.

/** The links as he edits them; null until the hub's are read (a hub without §59.5 starts from an empty site). */
@Composable
internal fun LinksFields(value: SiteLinks, onChange: (SiteLinks) -> Unit, campaign: String) {
    val c = Divan.colors
    var preview by remember { mutableStateOf<String?>(null) }
    Column(Modifier.testTag("links-editor"), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("سایت", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
        HqTextField(value.site.url, { onChange(value.copy(site = value.site.copy(url = it.trim()))) }, "https://…", Modifier.fillMaxWidth(), maxLength = 300, figure = true)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("بخش‌ها", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted, modifier = Modifier.weight(1f))
            HqButton("بخش", {
                val taken = value.sections.map { it.key }.toSet()
                onChange(value.copy(sections = value.sections + SiteSection(sectionKey("", "", taken), "", "https://")))
            }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.ADD)
        }
        if (value.sections.isEmpty()) Text("بخش جدایی نیست؛ هر جواب به سایت میرود.", style = Divan.type.micro, color = c.textMuted)
        value.sections.forEachIndexed { i, s ->
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    HqTextField(s.titleFa, { t -> onChange(value.copy(sections = value.sections.mapIndexed { j, x -> if (j == i) x.copy(titleFa = t) else x })) }, "نام بخش، مثل «بازپخش»", Modifier.weight(1f), maxLength = 60)
                    IconBtn(DivanIcon.CLOSE, "این بخش را بردار", { onChange(value.copy(sections = value.sections.filterIndexed { j, _ -> j != i })) }, tint = c.textMuted)
                }
                HqTextField(s.url, { u ->
                    val taken = value.sections.filterIndexed { j, _ -> j != i }.map { it.key }.toSet()
                    onChange(value.copy(sections = value.sections.mapIndexed { j, x -> if (j == i) x.copy(url = u.trim(), key = sectionKey(x.titleFa, u, taken)) else x }))
                }, "https://…", Modifier.fillMaxWidth(), maxLength = 300, figure = true)
            }
        }
        val problems = remember(value) { if (value.site.url.isBlank()) emptyList() else linksProblemsFa(value) }
        for (p in problems) Text(plain(p), style = Divan.type.caption, color = c.negative)
        if (value.site.url.startsWith("https://")) {
            Text("آنچه هر مسیر میفرستد", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
            if (value.sections.isNotEmpty()) ScrollRow {
                FilterChip("سایت", preview == null, { preview = null })
                for (s in value.sections) FilterChip(s.titleFa.ifBlank { s.key }, preview == s.key, { preview = s.key })
            }
            val today = com.coinepro.hq.core.format.HqClock.now().toString().take(10).replace("-", "")
            for ((fa, url) in remember(value, preview, campaign, today) { pathLinks(value, preview, campaign, today) }) Column(Modifier.fillMaxWidth()) {
                Text(fa, style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                Text(url, style = Divan.type.micro.copy(textDirection = TextDirection.Ltr), color = c.textMuted, maxLines = 2)
            }
        }
    }
}

/** The links of [company] in a sheet: read, edited, saved with one tap. */
@Composable
internal fun SiteLinksEditor(company: String, campaign: String, onDone: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val q = rememberSiteLinks(company)
    var edit by remember(company) { mutableStateOf<SiteLinks?>(null) }
    LaunchedEffect(q.data) { if (edit == null) q.data?.let { edit = it } }
    val on = served(com.coinepro.hq.core.net.HubFeature.SITE_LINKS)
    val save = rememberAction()
    val v = edit
    when {
        !on -> Text("لینک‌های شرکت با به‌روزرسانی بعدی هاب این‌جا می‌آیند؛ تا آن وقت هاب لینک سایت را خودش میگذارد.", style = Divan.type.small, color = c.textSecondary)
        v == null -> Skeleton(Modifier.fillMaxWidth().height(140.dp), radius = 12.dp)
        else -> {
            LinksFields(v, { edit = it }, campaign)
            val ok = v.site.url.startsWith("https://") && linksProblemsFa(v).isEmpty()
            SheetBar {
                DecisionBar("ذخیره", {
                    save.run {
                        val out = env.api.putSiteLinks(company, Api.jsonBody.encodeToJsonElement(SiteLinks.serializer(), v.copy(company = company)) as kotlinx.serialization.json.JsonObject)
                        q.set(out); env.cache.invalidate("site-links", "automations")
                        toasts.ok("لینک‌ها ذخیره شد؛ از جواب بعدی همین‌ها میروند.")
                        onDone()
                    }
                }, enabled = ok && v != q.data, state = if (save.busy) DecisionState.WORKING else DecisionState.IDLE, icon = DivanIcon.GLOBE)
            }
        }
    }
}

/** An empty set of links for a company that has none yet. */
internal fun emptyLinks(company: String) = SiteLinks(company = company, site = SiteUrl(url = "", titleFa = ""))
