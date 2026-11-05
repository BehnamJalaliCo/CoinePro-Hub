package com.coinepro.hq.ui.v33

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
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
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.leadEventFa
import com.coinepro.hq.core.data.leadSourceFa
import com.coinepro.hq.core.data.leadStageFa
import com.coinepro.hq.core.data.leadStageTone
import com.coinepro.hq.core.data.leadStages
import com.coinepro.hq.core.data.leadTitle
import com.coinepro.hq.core.data.moneyFigure
import com.coinepro.hq.core.data.nextAtIso
import com.coinepro.hq.core.data.rateText
import com.coinepro.hq.core.data.usdtInput
import com.coinepro.hq.core.data.usdtText
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.LeadDraft
import com.coinepro.hq.core.net.LeadIn
import com.coinepro.hq.core.net.PipeStage
import com.coinepro.hq.core.net.SalesLead
import com.coinepro.hq.core.net.SalesPipeline
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BarTone
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.MeterBar
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.ScrollRow
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.StatRow
import com.coinepro.hq.designsystem.StatTile
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.Para
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.served
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

// Contract §33.4 ⟨1.15⟩ «فروش»: a small CRM per company. The pipeline by the company's own stages (data), the leads (a pseudonym and a
// display name only; the contact stays in the company's systems), one lead with its trail, and a follow-up drafted in the company's voice
// that the hub never sends by itself.

/** The company's «فروش» tab. */
@Composable
fun CompanySales(code: String, newLead0: Boolean = false) {
    val nav = LocalNav.current
    val has = served(HubFeature.MONEY)
    var stage by rememberSaveable { mutableStateOf<String?>(null) }
    var adding by rememberSaveable { mutableStateOf(newLead0) }
    val pipe = rememberQuery("pipeline:$code", "money", "leads", maxAgeMs = 30_000) { gated(HubFeature.MONEY) { pipeline(code) } }
    val leads = rememberQuery("leads:$code:${stage ?: "all"}", "money", "leads", maxAgeMs = 30_000) { gated(HubFeature.MONEY) { leads(code, stage = stage) } }
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        if (!has) {
            Empty("فروش با به‌روزرسانی بعدی هاب میاید", icon = DivanIcon.CHART)
            return@Column
        }
        pipe.data?.let { PipelineCard(it, stage) { s -> stage = if (stage == s) null else s } }
            ?: if (pipe.error != null) ErrorBlock(pipe.error, { pipe.refresh() }) else Skeleton(Modifier.fillMaxWidth().height(180.dp), radius = 16.dp)
        SectionTitle("سرنخ‌ها", note = stage?.let { s -> "فقط «${leadStageFa(s, pipe.data?.stages?.firstOrNull { it.stage == s }?.titleFa)}»" } ?: "تازه‌ترین تغییر اول") {
            HqButton("سرنخ تازه", { adding = true }, variant = BtnVariant.SILVER, size = BtnSize.SM, icon = DivanIcon.ADD)
        }
        val list = leads.data?.items
        when {
            list == null && leads.error != null -> ErrorBlock(leads.error, { leads.refresh() })
            list == null -> Skeleton(Modifier.fillMaxWidth().height(200.dp), radius = 16.dp)
            list.isEmpty() -> Empty(
                if (stage == null) "هنوز سرنخی نیست" else "در این مرحله سرنخی نیست", icon = DivanIcon.OWNER,
                body = "سرنخ‌ها از پشتیبانی، تلگرام، پرداخت‌های بی‌مشتری یا دستی این‌جا میایند.",
            )
            else -> HqCard(Modifier.fillMaxWidth(), padding = androidx.compose.foundation.layout.PaddingValues(horizontal = 12.dp, vertical = 6.dp)) {
                list.forEachIndexed { i, l ->
                    if (i > 0) HorizontalDivider(color = Divan.colors.lineDivider)
                    androidx.compose.runtime.key(l.ref) { LeadRow(l, pipe.data) { nav.go("leads/${l.ref}") } }
                }
            }
        }
    }
    if (adding) com.coinepro.hq.ui.v14.HqSheet({ adding = false }, "سرنخ تازه", sub = "فقط یک نام نمایشی و یک نام مستعار؛ شماره و نشانی در سیستم خود شرکت میماند.") {
        NewLeadForm(code) { ref -> adding = false; if (ref != null) nav.go("leads/$ref") }
    }
}

/** The pipeline: one bar per stage (count and value), and the win rate. A tap on a stage filters the list. */
@Composable
fun PipelineCard(p: SalesPipeline, chosen: String?, onStage: (String) -> Unit) {
    val c = Divan.colors
    val max = (p.stages.maxOfOrNull { it.count } ?: 0).coerceAtLeast(1)
    HqCard(Modifier.fillMaxWidth(), tahrir = true) {
        StatRow {
            StatTile("سرنخ باز", "${p.openCount}", Modifier.weight(1f), sub = "از ${p.total} سرنخ", count = true)
            StatTile("ارزش باز", moneyFigure(p.openValueUsdt), Modifier.weight(1f), sub = "USDT")
            StatTile("نرخ برد", rateText(p.winRate), Modifier.weight(1f), sub = "${p.wonCount} برد، ${p.lostCount} باخت", tone = p.winRate?.let { if (it >= 0.3) Tone.POS else null })
        }
        Column(Modifier.padding(top = 14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            for (s in p.stages) StageBar(s, max, chosen == s.stage) { onStage(s.stage) }
        }
    }
}

@Composable
private fun StageBar(s: PipeStage, max: Int, chosen: Boolean, onClick: () -> Unit) {
    val c = Divan.colors
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(if (chosen) c.softGold else androidx.compose.ui.graphics.Color.Transparent)
            .clickable(role = Role.Button, onClickLabel = "فقط این مرحله", onClick = onClick).padding(horizontal = 6.dp, vertical = 4.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(leadStageFa(s.stage, s.titleFa), Modifier.weight(1f), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
            s.medianDays?.let { Text(plain("حدود ${moneyFigure(it)} روز"), style = Divan.type.micro, color = c.textMuted) }
            Fig("${s.count}", style = Divan.type.figure, color = c.textPrimary)
            if (s.valueUsdt > 0) Fig(usdtText(s.valueUsdt), style = Divan.type.figureSmall, color = c.textMuted)
        }
        MeterBar(s.count * 100.0 / max, tone = when (s.kind) { "won" -> BarTone.POS; "lost" -> BarTone.SILVER; else -> BarTone.GOLD }, height = 5.dp)
    }
}

@Composable
fun LeadRow(l: SalesLead, pipe: SalesPipeline?, onClick: () -> Unit) {
    val c = Divan.colors
    val title = pipe?.stages?.firstOrNull { it.stage == l.stage }?.titleFa
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).clickable(role = Role.Button, onClick = onClick).padding(vertical = 10.dp, horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(plain(leadTitle(l)), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 1)
            Text(
                plain(listOfNotNull(leadSourceFa(l.source), l.nextFa?.takeIf { it.isNotBlank() }?.let { n -> l.nextAt?.let { "$n · ${jDate(it)}" } ?: n }).joinToString(" · ")),
                style = Divan.type.micro, color = c.textMuted, maxLines = 1,
            )
        }
        Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(4.dp)) {
            l.valueUsdt?.let { Fig(usdtText(it), style = Divan.type.figureSmall, color = c.textPrimary) }
            Pill(leadStageFa(l.stage, title), leadStageTone(l.stage), dot = true)
        }
    }
}

/** A lead by hand: a display name, a pseudonym (the hub makes one when left empty), a value and the next step. */
@Composable
fun NewLeadForm(code: String, onDone: (String?) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val save = rememberAction()
    var name by rememberSaveable { mutableStateOf("") }
    var contact by rememberSaveable { mutableStateOf("") }
    var value by rememberSaveable { mutableStateOf("") }
    var next by rememberSaveable { mutableStateOf("") }
    var nextIn by rememberSaveable { mutableStateOf<Long?>(1L) }
    var note by rememberSaveable { mutableStateOf("") }
    val valueOk = value.isBlank() || usdtInput(value) != null
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Label("نام نمایشی")
        HqTextField(name, { name = it }, "مثلاً مشتری کانال تلگرام", Modifier.fillMaxWidth(), maxLength = 200)
        Label("نام مستعار (اختیاری)")
        HqTextField(contact, { contact = it.trim() }, "tg-user-41", Modifier.fillMaxWidth(), figure = true, maxLength = 80)
        Label("ارزش تقریبی (USDT)")
        HqTextField(value, { value = it }, "120", Modifier.fillMaxWidth(), figure = true, maxLength = 14)
        if (!valueOk) Text("فقط عدد بنویس.", style = Divan.type.caption, color = c.warning)
        Label("قدم بعدی")
        HqTextField(next, { next = it }, "مثلاً پیام معرفی دوره‌ی آزمایشی", Modifier.fillMaxWidth(), maxLength = 300)
        NextWhen(nextIn) { nextIn = it }
        Label("یادداشت (اختیاری)")
        HqTextField(note, { note = it }, "", Modifier.fillMaxWidth(), singleLine = false, minLines = 2, maxLength = 1000)
        HqButton("ثبت سرنخ", {
            save.run {
                val l = env.api.createLead(code, LeadIn(
                    source = "manual", nameFa = name.trim().ifEmpty { null }, contact = contact.ifEmpty { null }, valueUsdt = usdtInput(value),
                    nextFa = next.trim().ifEmpty { null }, nextAt = if (next.isBlank()) null else nextIn?.let { nextAtIso(it) }, noteFa = note.trim().ifEmpty { null },
                ))
                env.cache.invalidate("leads")
                toasts.ok("سرنخ ثبت شد.")
                onDone(l.ref)
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.ADD, enabled = valueOk && (name.isNotBlank() || contact.isNotBlank()), loading = save.busy)
    }
}

@Composable
private fun Label(t: String) = Text(t, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = Divan.colors.textSecondary)

/** When the next step is due: tomorrow, in three days, in a week, or no reminder. */
@Composable
private fun NextWhen(days: Long?, onPick: (Long?) -> Unit) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        for ((d, l) in listOf(1L to "فردا", 3L to "3 روز بعد", 7L to "یک هفته بعد")) FilterChip(l, days == d, { onPick(d) })
        FilterChip("بدون یادآوری", days == null, { onPick(null) })
    }
}

// ---------------------------------------------------------------- one lead --
/** «سرنخ»: one lead with its stage, value, next step and trail; the follow-up draft on demand (never sent from here). */
@Composable
fun LeadScreen(ref: String, draft0: LeadDraft? = null) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val companies = rememberCompanies()
    val q = rememberQuery("lead:$ref", "leads", maxAgeMs = 20_000) { lead(ref) }
    val l = q.data
    val pipe = if (l != null) rememberQuery("pipeline:${l.company}", "money", "leads", maxAgeMs = 60_000) { gated(HubFeature.MONEY) { pipeline(l.company) } } else null
    val r = refresher(q)
    val save = rememberAction()
    val drafting = rememberAction()
    var draft by remember(ref) { mutableStateOf(draft0) }
    var editing by rememberSaveable { mutableStateOf(false) }
    var losing by rememberSaveable { mutableStateOf<String?>(null) }
    fun patch(body: kotlinx.serialization.json.JsonObject, done: String) = save.run {
        val cur = q.data ?: return@run
        q.set(env.api.patchLead(cur, body))
        env.cache.invalidate("leads")
        toasts.ok(done)
    }
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        when {
            l == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            l == null -> item { Skeleton(Modifier.fillMaxWidth().height(260.dp), radius = 16.dp) }
            else -> {
                val stages = leadStages(pipe?.data)
                item(key = "head") {
                    HqCard(Modifier.fillMaxWidth(), tahrir = true) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            Box(Modifier.size(44.dp).clip(CircleShape).background(c.tile), contentAlignment = Alignment.Center) { DIcon(DivanIcon.OWNER, size = 22.dp, tint = c.goldInk) }
                            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                Text(plain(leadTitle(l)), style = Divan.type.h2)
                                Text(plain("${companyOf(companies, l.company).nameFa} · از ${leadSourceFa(l.source)} · ${ago(l.createdAt)}"), style = Divan.type.caption, color = c.textMuted)
                            }
                            Pill(leadStageFa(l.stage, stages.firstOrNull { it.stage == l.stage }?.titleFa), leadStageTone(l.stage), dot = true)
                        }
                        Row(Modifier.padding(top = 12.dp), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                            Fact("نام مستعار", l.contact, figure = true)
                            Fact("ارزش", usdtText(l.valueUsdt), figure = true)
                            l.assignee?.let { a -> Fact("مسئول", a.displayFa ?: a.code) }
                        }
                        if (!l.nextFa.isNullOrBlank() || l.nextAt != null) Column(
                            Modifier.padding(top = 12.dp).fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp),
                            verticalArrangement = Arrangement.spacedBy(2.dp),
                        ) {
                            Text("قدم بعدی", style = Divan.type.micro, color = c.textMuted)
                            Text(plain(l.nextFa ?: "پیگیری"), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                            l.nextAt?.let { Text(plain(jDateTime(it)), style = Divan.type.micro, color = c.textMuted) }
                        }
                        l.lostReasonFa?.takeIf { it.isNotBlank() && l.stage == "lost" }?.let { Para("چرا از دست رفت: $it", Modifier.padding(top = 8.dp), style = Divan.type.caption, color = c.textMuted) }
                    }
                }
                item(key = "stage") {
                    HqCard(Modifier.fillMaxWidth()) {
                        SectionTitle("مرحله", note = "با یک ضربه جابه‌جا کن")
                        FlowRow(Modifier.padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            for (s in stages) FilterChip(leadStageFa(s.stage, s.titleFa), l.stage == s.stage, {
                                if (s.stage == l.stage || save.busy) return@FilterChip
                                if (s.kind == "lost") losing = s.stage
                                else patch(buildJsonObject { put("stage", JsonPrimitive(s.stage)) }, "مرحله عوض شد.")
                            })
                        }
                        if (stages.any { it.kind == "won" }) Text("«پرداخت کرد» را وقتی پرداختی با همین نام مستعار برسد، خود هاب میزند.", Modifier.padding(top = 8.dp), style = Divan.type.micro, color = c.textMuted)
                    }
                }
                item(key = "actions") {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        HqButton("پیش‌نویس پیگیری", {
                            drafting.run { draft = env.api.leadDraft(l.ref); env.cache.invalidate("leads") }
                        }, Modifier.weight(1f), variant = BtnVariant.PRIMARY, icon = DivanIcon.EDIT, loading = drafting.busy)
                        HqButton("تغییر", { editing = true }, Modifier.weight(1f), variant = BtnVariant.SILVER, icon = DivanIcon.SETTINGS)
                    }
                }
                draft?.let { d -> item(key = "draft") { DraftCard(d) } }
                if (l.events.isNotEmpty()) item(key = "events") {
                    HqCard(Modifier.fillMaxWidth()) {
                        SectionTitle("ماجرا", note = "تازه‌ترین اول")
                        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            for (e in l.events.sortedByDescending { it.at }) Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                Box(Modifier.padding(top = 6.dp).size(7.dp).clip(CircleShape).background(c.goldInk))
                                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                    Text(plain(leadEventFa(e.kind) + " · " + jDateTime(e.at)), style = Divan.type.micro, color = c.textMuted)
                                    if (e.noteFa.isNotBlank()) Para(e.noteFa, style = Divan.type.small, color = c.textPrimary)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    val cur = q.data
    if (editing && cur != null) com.coinepro.hq.ui.v14.HqSheet({ editing = false }, "تغییر سرنخ", sub = leadTitle(cur)) {
        LeadEditForm(cur, save.busy) { body -> patch(body, "ذخیره شد."); editing = false }
    }
    losing?.let { st ->
        com.coinepro.hq.ui.v14.HqSheet({ losing = null }, "از دست رفت", sub = "در یک جمله بنویس چرا؛ برای یاد گرفتن است.") {
            var why by rememberSaveable { mutableStateOf("") }
            HqTextField(why, { why = it }, "مثلاً قیمت برایش زیاد بود", Modifier.fillMaxWidth(), singleLine = false, minLines = 2, maxLength = 300)
            HqButton("ثبت", {
                patch(buildJsonObject { put("stage", JsonPrimitive(st)); if (why.isNotBlank()) put("lost_reason_fa", JsonPrimitive(why.trim())) }, "ثبت شد.")
                losing = null
            }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, loading = save.busy)
        }
    }
}

@Composable
private fun Fact(label: String, value: String, figure: Boolean = false) {
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(label, style = Divan.type.micro, color = Divan.colors.textMuted)
        if (figure) Fig(value, style = Divan.type.figureSmall, color = Divan.colors.textPrimary) else Text(plain(value), style = Divan.type.small, color = Divan.colors.textPrimary)
    }
}

/** The drafted follow-up: what the outbound guard said about it, and the text. Sending stays with the company's own channel rules. */
@Composable
fun DraftCard(d: LeadDraft) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Box(Modifier.weight(1f)) { SectionTitle("پیش‌نویس پیگیری", note = "فرستاده نشده؛ فقط پیش‌نویس است") }
            if (d.guardOk) Pill("قابل ارسال", Tone.POS, icon = DivanIcon.SEAL) else Pill("نگه داشته شد", Tone.WARN, icon = DivanIcon.LOCK)
        }
        if (d.draftFa.isNotBlank()) Column(Modifier.padding(top = 10.dp).fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp)) {
            Para(d.draftFa, style = Divan.type.body, color = c.textPrimary)
        }
        if (!d.guardOk && d.blockedReasons.isNotEmpty()) Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("چرا نگه داشته شد", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.warning)
            for (x in d.blockedReasons) Para("• $x", style = Divan.type.caption, color = c.textSecondary)
        }
    }
}

/** The fields of a lead the owner changes by hand; only what changed is sent (a cleared field as null). */
@Composable
private fun LeadEditForm(l: SalesLead, busy: Boolean, onSave: (kotlinx.serialization.json.JsonObject) -> Unit) {
    val c = Divan.colors
    var name by rememberSaveable(l.ref) { mutableStateOf(l.nameFa.orEmpty()) }
    var value by rememberSaveable(l.ref) { mutableStateOf(l.valueUsdt?.let { moneyFigure(it).replace(",", "") }.orEmpty()) }
    var next by rememberSaveable(l.ref) { mutableStateOf(l.nextFa.orEmpty()) }
    var nextIn by rememberSaveable(l.ref) { mutableStateOf<Long?>(if (l.nextAt == null) null else -1L) }
    var note by rememberSaveable(l.ref) { mutableStateOf("") }
    val valueOk = value.isBlank() || usdtInput(value) != null
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Label("نام نمایشی")
        HqTextField(name, { name = it }, "", Modifier.fillMaxWidth(), maxLength = 200)
        Label("ارزش تقریبی (USDT)")
        HqTextField(value, { value = it }, "120", Modifier.fillMaxWidth(), figure = true, maxLength = 14)
        if (!valueOk) Text("فقط عدد بنویس.", style = Divan.type.caption, color = c.warning)
        Label("قدم بعدی")
        HqTextField(next, { next = it }, "", Modifier.fillMaxWidth(), maxLength = 300)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            if (l.nextAt != null) FilterChip("همان زمان", nextIn == -1L, { nextIn = -1L })
            for ((d, lb) in listOf(1L to "فردا", 3L to "3 روز بعد", 7L to "یک هفته بعد")) FilterChip(lb, nextIn == d, { nextIn = d })
            FilterChip("بدون یادآوری", nextIn == null, { nextIn = null })
        }
        Label("یادداشت تازه (اختیاری)")
        HqTextField(note, { note = it }, "", Modifier.fillMaxWidth(), singleLine = false, minLines = 2, maxLength = 1000)
        HqButton("ذخیره", {
            onSave(buildJsonObject {
                if (name.trim() != l.nameFa.orEmpty() && name.isNotBlank()) put("name_fa", JsonPrimitive(name.trim()))
                val v = usdtInput(value)
                val valueChanged = if (v == null) l.valueUsdt != null else l.valueUsdt == null || v.toBigDecimal().compareTo(l.valueUsdt.toBigDecimal()) != 0
                if (valueChanged) put("value_usdt", v?.let(::JsonPrimitive) ?: JsonNull)
                if (next.trim() != l.nextFa.orEmpty()) put("next_fa", next.trim().ifEmpty { null }?.let(::JsonPrimitive) ?: JsonNull)
                when (nextIn) {
                    -1L -> Unit
                    null -> if (l.nextAt != null) put("next_at", JsonNull)
                    else -> put("next_at", JsonPrimitive(nextAtIso(nextIn!!)))
                }
                if (note.isNotBlank()) put("note_fa", JsonPrimitive(note.trim()))
            })
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, enabled = valueOk, loading = busy)
    }
}
