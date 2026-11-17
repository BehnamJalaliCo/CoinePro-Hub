package com.coinepro.hq.ui.automation

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.J_WEEK_FA
import com.coinepro.hq.core.data.clockOf
import com.coinepro.hq.core.data.faNum
import com.coinepro.hq.core.data.faText
import com.coinepro.hq.core.data.flowEffortFa
import com.coinepro.hq.core.data.jDayFa
import com.coinepro.hq.core.data.modelShort
import com.coinepro.hq.core.data.usdShort
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.net.FlowKit
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.publish.Avatar
import com.coinepro.hq.ui.publish.Count
import com.coinepro.hq.ui.publish.PubCover
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.served
import java.time.ZoneId
import java.util.UUID
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

// ⟨1.39⟩ Contract §61.5 and §61.7, D6: «اتوماسیون تازه» in six steps (the page, the kit, the hours, model and the day's warning line,
// the preview with the kit's map, «بساز و روشن کن»), «کیت تازه» as a direct session with the workshop, and the week's summary.

private val STEPS = listOf("پیج", "قالب", "ساعت‌ها", "مدل و هزینه", "پیش‌نمایش", "ساخت")

private fun minus90(hm: String): String {
    val m = (hm.substring(0, 2).toInt() * 60 + hm.substring(3, 5).toInt() - 90).let { if (it < 0) it + 1440 else it }
    return "%02d:%02d".format(m / 60, m % 60)
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun NewFlowScreen(account0: String? = null, step0: Int = 0, kit0: String? = null) {
    val c = Divan.colors
    val nav = LocalNav.current
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = rememberAction()
    val more = served(HubFeature.FLOWS_MORE)
    val flows = rememberFlows().data
    val o = rememberFlowOptions().data
    var step by rememberSaveable { mutableStateOf(step0) }
    var account by rememberSaveable { mutableStateOf(account0) }
    var kitKey by rememberSaveable { mutableStateOf(kit0) }
    var hour by rememberSaveable { mutableStateOf("17:00") }
    var trigger by rememberSaveable { mutableStateOf("15:30") }
    var sameDay by rememberSaveable { mutableStateOf(true) }
    var model by rememberSaveable { mutableStateOf<String?>(null) }
    var effort by rememberSaveable { mutableStateOf("xhigh") }
    var cap by rememberSaveable { mutableStateOf(15.0) }
    var title by rememberSaveable { mutableStateOf("") }
    var asking by rememberSaveable { mutableStateOf(false) }
    var askNote by rememberSaveable { mutableStateOf("") }
    val accounts = remember(flows) { flows?.items.orEmpty().filter { it.account.isNotBlank() }.groupBy { it.account } }
    val kit: FlowKit? = o?.kits?.firstOrNull { it.key == kitKey }
    val m = model ?: o?.models?.firstOrNull()?.id ?: ""
    Box(Modifier.fillMaxSize()) {
        Page {
            item(key = "head") { PageHeader("اتوماسیون تازه", eyebrow = "${faNum(step + 1)} از ${faNum(STEPS.size)} · ${STEPS[step]}") }
            item(key = "steps") {
                Row(Modifier.fillMaxWidth().testTag("wizard-steps"), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    for (i in STEPS.indices) Box(Modifier.weight(1f).height(4.dp).clip(RoundedCornerShape(2.dp)).background(if (i <= step) c.goldFill else c.raised))
                }
            }
            if (!more) { item(key = "old") { Empty("ساختن اتوماسیون تازه با به‌روزرسانی بعدی هاب می‌آید", icon = DivanIcon.ADD, body = "تا آن موقع، همین را در گفتگو به Claude سرور هاب بگو.") }; return@Page }
            if (o == null) { item(key = "sk") { Skeleton(Modifier.fillMaxWidth().height(300.dp), radius = 18.dp) }; return@Page }
            // 1 · the page (done above once picked)
            item(key = "s1") {
                HqCard(Modifier.fillMaxWidth().testTag("wizard-page")) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("۱ · پیج", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f))
                        if (account != null && step > 0) HqButton("عوض کن", { step = 0 }, variant = BtnVariant.TEXT, size = BtnSize.SM)
                    }
                    if (step == 0 || account == null) FlowRow(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        for ((a, list) in accounts) FilterChip("@$a · ${list.first().companyFa}", account == a, { account = a; if (step == 0) step = 1 }, figure = true)
                    } else {
                        val list = accounts[account].orEmpty()
                        Row(Modifier.padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            Avatar(account!!, 36.dp)
                            Column(Modifier.weight(1f)) {
                                Text(plain("@$account"), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                                Text(plain("${list.firstOrNull()?.companyFa.orEmpty()} · اینستاگرام · ${faNum(list.size)} اتوماسیون دارد"), style = Divan.type.micro, color = c.textMuted)
                            }
                            Pill("راه انتشار آماده", Tone.POS)
                        }
                    }
                }
            }
            if (step >= 1 && account != null) item(key = "s2") {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("۲ · قالب", style = Divan.type.h3, modifier = Modifier.weight(1f))
                        Text("کیت‌هایی که امروز کار میکنند", style = Divan.type.micro, color = c.textMuted)
                    }
                    for (row in o.kits.chunked(2)) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        for (k in row) KitCard(k, kitKey == k.key, Modifier.weight(1f)) {
                            kitKey = k.key; if (title.isBlank() || o.kits.any { t -> title.startsWith(t.titleFa) }) title = "${k.titleFa} @$account"; if (step == 1) step = 2
                        }
                        if (row.size == 1) Spacer(Modifier.weight(1f))
                    }
                    Column(
                        Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).border(1.dp, c.lineStrong, RoundedCornerShape(18.dp)).padding(12.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text("کیت تازه میخواهی؟", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), modifier = Modifier.weight(1f))
                            Pill("کارگاه", Tone.LAPIS)
                        }
                        Text("به Claude هاب بگو چه میخواهی؛ نمونه‌اش را در جلسه میبینی و تأیید میکنی، بعد همین‌جا قالب میشود.", style = Divan.type.micro, color = c.textSecondary)
                        if (asking) {
                            Box(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp)) {
                                HqTextField(askNote, { askNote = it }, "مثلاً ریلز ۳۰ ثانیه‌ای خبر بازار با نمودار روز", Modifier.fillMaxWidth(), singleLine = false, minLines = 2, maxLength = 1000)
                            }
                            HqButton("بفرست برای Claude هاب", {
                                act.run {
                                    val out = env.api.requestKit(account!!, askNote.trim(), UUID.randomUUID().toString())
                                    asking = false; askNote = ""
                                    val order = (out?.get("order") as? JsonPrimitive)?.content
                                    toasts.ok("جلسه‌ی کیت تازه باز شد", action = order?.let { "باز کن" }) { order?.let { nav.go("order/$it") } }
                                }
                            }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, enabled = askNote.isNotBlank(), loading = act.busy)
                        } else HqButton("از Claude هاب بخواه", { asking = true }, Modifier.fillMaxWidth(), variant = BtnVariant.SECONDARY, size = BtnSize.SM)
                    }
                }
            }
            if (step >= 2 && kit != null) item(key = "s3") {
                HqCard(Modifier.fillMaxWidth().testTag("wizard-hours")) {
                    Text("۳ · ساعت‌ها", style = Divan.type.micro, color = c.textMuted)
                    WizardHour("انتشار", hour) { v -> hour = v; trigger = minus90(v) }
                    WizardHour("شروع ساخت", trigger) { trigger = it }
                    Row(Modifier.padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text("همان روز انتشار بساز", style = Divan.type.small, color = c.textSecondary, modifier = Modifier.weight(1f))
                        HqSwitch(sameDay, { sameDay = it }, label = "همان روز")
                    }
                    val clash = flows?.items.orEmpty().filter { it.account == account && it.kind != "stories" }.flatMap { it.schedule.hours.filterNotNull() }.distinct()
                    Text(
                        plain(if (hour in clash) "هم‌دقیقه‌ی ریلز ${faText(hour)} همین پیج است؛ ساعت دیگری بگذار." else if (clash.isEmpty()) "روزها: هر روز" else "با ریلزهای ${clash.sorted().joinToString(" و ") { faText(it) }} همین پیج فاصله دارد"),
                        style = Divan.type.micro, color = if (hour in clash) c.negative else c.positive, modifier = Modifier.padding(top = 6.dp),
                    )
                    if (step == 2) HqButton("بعدی: مدل و هزینه", { step = 3 }, Modifier.fillMaxWidth().padding(top = 8.dp), variant = BtnVariant.PRIMARY, enabled = hour !in clash)
                }
            }
            if (step >= 3 && kit != null) item(key = "s4") {
                HqCard(Modifier.fillMaxWidth().testTag("wizard-model")) {
                    Text("۴ · مدل و هزینه", style = Divan.type.micro, color = c.textMuted)
                    FlowRow(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        for (x in o.models) FilterChip(modelShort(x.id, x.nameFa), m == x.id, { model = x.id }, figure = true)
                    }
                    FlowRow(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        for (e in o.efforts) FilterChip(flowEffortFa(e), effort == e, { effort = e })
                    }
                    Row(Modifier.padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text("هشدار هزینه‌ی روز", style = Divan.type.small, modifier = Modifier.weight(1f))
                        Text(plain(usdShort(cap)), style = Divan.type.h3)
                    }
                    Slider(cap.toFloat(), { cap = Math.round(it).toDouble().coerceAtLeast(o.usdCap.min.toDouble()) }, valueRange = o.usdCap.min.toFloat()..o.usdCap.max.toFloat(),
                        colors = SliderDefaults.colors(thumbColor = c.goldFill, activeTrackColor = c.goldFill, inactiveTrackColor = c.tile))
                    Text(plain("${estimateFa(cap)} · از آن بگذرد فقط هشدار میدهد؛ ساخت نمی‌ایستد."), style = Divan.type.micro, color = c.textMuted)
                    if (step == 3) HqButton("بعدی: پیش‌نمایش", { step = 4 }, Modifier.fillMaxWidth().padding(top = 8.dp), variant = BtnVariant.PRIMARY)
                }
            }
            if (step >= 4 && kit != null) item(key = "s5") { Preview(kit, account!!, hour, trigger, sameDay, title) { title = it } }
            item(key = "room") { Spacer(Modifier.height(80.dp)) }
        }
        if (more && o != null) Row(
            Modifier.align(Alignment.BottomCenter).fillMaxWidth().background(c.card).border(1.dp, c.lineHairline).padding(horizontal = 16.dp, vertical = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            if (step >= 4 && kit != null) HqButton("بساز و روشن کن", {
                act.run {
                    val body = buildJsonObject {
                        put("account", JsonPrimitive(account)); put("channel", JsonPrimitive("instagram")); put("kit", JsonPrimitive(kit.key))
                        put("title_fa", JsonPrimitive(title.ifBlank { kit.titleFa }))
                        put("schedule", buildJsonObject {
                            put("hours", JsonArray(listOf(JsonPrimitive(hour)))); put("trigger_at", JsonPrimitive(trigger)); put("same_day", JsonPrimitive(sameDay))
                            put("days", JsonArray((0..6).map { JsonPrimitive(it) }))
                        })
                        put("model", JsonPrimitive(m)); put("effort", JsonPrimitive(effort)); put("usd_cap", JsonPrimitive(cap))
                    }
                    val out = env.api.newFlow(body, UUID.randomUUID().toString())
                    env.cache.invalidate(*FLOW_TAGS)
                    toasts.ok("«${out.titleFa}» ساخته و روشن شد")
                    nav.go("automation/${out.ref}")
                }
            }, Modifier.weight(2f), variant = BtnVariant.PRIMARY, size = BtnSize.LG, loading = act.busy)
            else HqButton("بعدی", { step = (step + 1).coerceAtMost(STEPS.lastIndex) }, Modifier.weight(2f), variant = BtnVariant.PRIMARY, size = BtnSize.LG,
                enabled = (step == 0 && account != null) || (step == 1 && kit != null) || step in 2..3)
            HqButton("قبلی", { if (step == 0) nav.back() else step -= 1 }, Modifier.weight(1f), variant = BtnVariant.SECONDARY, size = BtnSize.LG)
        }
    }
}

@Composable
private fun KitCard(k: FlowKit, on: Boolean, modifier: Modifier, onPick: () -> Unit) {
    val c = Divan.colors
    val shape = RoundedCornerShape(18.dp)
    Column(
        modifier.fillMaxHeight().testTag("kit-card").clip(shape).background(c.card).border(if (on) 1.5.dp else 1.dp, if (on) c.goldFill else c.lineHairline, shape)
            .clickable(role = Role.RadioButton, onClickLabel = k.titleFa) { onPick() }.padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Text(plain(k.titleFa), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
        Text(plain(k.aboutFa), style = Divan.type.micro, color = c.textMuted, maxLines = 3, overflow = TextOverflow.Ellipsis)
        Text(plain(listOfNotNull(k.avgUsd?.let { "≈ ${usdShort(it)}" }, k.avgMinutes?.let { "${faNum(it.toInt())} دقیقه" }).joinToString(" · ")), style = Divan.type.micro, color = c.textSecondary)
        if (k.usedOn.isNotEmpty()) Text(plain("در " + k.usedOn.joinToString(" و ") { "@$it" }), style = Divan.type.micro, color = c.goldInk, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
private fun WizardHour(label: String, value: String, onChange: (String) -> Unit) {
    val c = Divan.colors
    var text by remember(value) { mutableStateOf(faText(value)) }
    Row(Modifier.fillMaxWidth().padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, style = Divan.type.small, modifier = Modifier.weight(1f))
        Box(Modifier.clip(RoundedCornerShape(12.dp)).background(c.softGold).border(1.dp, c.goldFill, RoundedCornerShape(12.dp)).padding(horizontal = 12.dp, vertical = 8.dp)) {
            HqTextField(text, { t -> text = t; clockOf(t)?.let(onChange) }, "18:00", Modifier.width(72.dp), maxLength = 5, figure = true)
        }
    }
}

@Composable
private fun Preview(kit: FlowKit, account: String, hour: String, trigger: String, sameDay: Boolean, title: String, onTitle: (String) -> Unit) {
    val c = Divan.colors
    val g = rememberQuery("kit-graph:${kit.key}", *FLOW_TAGS, maxAgeMs = 300_000) { gated(HubFeature.FLOWS_MORE) { kitGraph(kit.key) } }.data
    val tomorrow = HqClock.now().atZone(ZoneId.of(com.coinepro.hq.core.format.OWNER_TZ)).toLocalDate().plusDays(1)
    HqCard(Modifier.fillMaxWidth().testTag("wizard-preview")) {
        Text("۵ · پیش‌نمایش", style = Divan.type.micro, color = c.textMuted)
        Box(Modifier.fillMaxWidth().padding(top = 8.dp).clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp)) {
            HqTextField(title, onTitle, "نام اتوماسیون", Modifier.fillMaxWidth(), maxLength = 80)
        }
        if (g != null && g.nodes.isNotEmpty()) FlowCanvas(g, emptyMap(), Modifier.fillMaxWidth().height(220.dp).padding(top = 8.dp), onNode = {})
        Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            PreviewLine("اولین ساخت", "${if (sameDay) jDayFa(tomorrow) else jDayFa(tomorrow.minusDays(0))} · ${faText(trigger)}")
            PreviewLine("اولین انتشار", "${if (sameDay) "همان روز" else "روز بعد"} · ${faText(hour)}")
            PreviewLine("کلمه‌ی کامنت", "هر روز تازه، از موضوع")
            PreviewLine("تقویم", "از فردا هر روز یک ${if ("stories" in kit.kinds) "دسته استوری" else "ریلز"} کم‌رنگ «ساخته میشود»")
        }
        Text("بعد از ساخت، اتوماسیون روشن است و نسخه‌ی ۱ ثبت میشود. ساعت‌ها، هزینه و مدل را هر وقت خواستی در «تنظیمات» عوض میکنی.", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.padding(top = 8.dp))
    }
}

@Composable
private fun PreviewLine(k: String, v: String) {
    val c = Divan.colors
    Row(Modifier.fillMaxWidth()) {
        Text(k, style = Divan.type.small, color = c.textSecondary, modifier = Modifier.weight(1f))
        Text(plain(v), style = Divan.type.small)
    }
}

// ------------------------------------------------------------------------------------------------------------- the week --
@Composable
fun FlowWeekScreen() {
    val c = Divan.colors
    val nav = LocalNav.current
    val more = served(HubFeature.FLOWS_MORE)
    val q = rememberQuery("flow-week", *FLOW_TAGS, maxAgeMs = 60_000) { gated(HubFeature.FLOWS_MORE) { flowWeek() } }
    val w = q.data
    Page(onRefresh = { q.refresh() }, refreshing = q.state.refreshing) {
        item(key = "head") {
            PageHeader("خلاصه‌ی هفته", eyebrow = w?.let { x ->
                val a = runCatching { java.time.LocalDate.parse(x.from) }.getOrNull(); val b = runCatching { java.time.LocalDate.parse(x.to) }.getOrNull()
                if (a != null && b != null) "${jDayFa(a)} تا ${jDayFa(b)}" else null
            })
        }
        when {
            // a hub before §61 P2 reads `/automations/week` as §59's automation «week»: its own 404 is the same «not yet»
            !more || (w == null && q.error?.status == 404) -> item(key = "old") { Empty("خلاصه‌ی هفته با به‌روزرسانی بعدی هاب می‌آید", icon = DivanIcon.CHART) }
            w == null && q.error != null -> item(key = "error") { ErrorBlock(q.error, { q.refresh() }) }
            w == null -> item(key = "sk") { Skeleton(Modifier.fillMaxWidth().height(320.dp), radius = 18.dp) }
            else -> {
                item(key = "totals") {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Count(w.totals.runs, "ساخت")
                        Count(w.totals.published, "انتشار")
                        Column(Modifier.weight(1f).clip(RoundedCornerShape(14.dp)).background(c.tile).padding(horizontal = 10.dp, vertical = 8.dp)) {
                            Text(plain(usdShort(w.totals.costUsd)), style = Divan.type.h2.copy(fontWeight = FontWeight.Bold))
                            Text("هزینه", style = Divan.type.micro, color = c.textSecondary)
                        }
                    }
                }
                item(key = "days") {
                    HqCard(Modifier.fillMaxWidth().testTag("week-days")) {
                        Text("انتشار هر روز", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                        val top = (w.byDay.maxOfOrNull { maxOf(it.published, it.planned) } ?: 1).coerceAtLeast(1)
                        Row(Modifier.fillMaxWidth().height(80.dp).padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.Bottom) {
                            for ((i, d) in w.byDay.withIndex()) Column(Modifier.weight(1f).fillMaxHeight(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Bottom) {
                                val planned = d.published == 0 && d.planned > 0
                                Box(
                                    Modifier.fillMaxWidth().fillMaxHeight(((if (planned) d.planned else d.published).toFloat() / top).coerceIn(0.04f, 0.85f)).clip(RoundedCornerShape(topStart = 4.dp, topEnd = 4.dp))
                                        .then(if (planned) Modifier.border(1.dp, c.lineStrong, RoundedCornerShape(topStart = 4.dp, topEnd = 4.dp)) else Modifier.background(c.goldFill)),
                                )
                                Text(J_WEEK_FA.getOrElse(i) { "" }, style = Divan.type.micro, color = c.textMuted, modifier = Modifier.padding(top = 4.dp))
                            }
                        }
                        Text("خط‌چین: روزهای مانده، از برنامه‌ی اتوماسیون‌ها", style = Divan.type.micro, color = c.textMuted)
                    }
                }
                item(key = "accounts") {
                    HqCard(Modifier.fillMaxWidth().testTag("week-accounts")) {
                        for ((i, a) in w.accounts.withIndex()) {
                            if (i > 0) Box(Modifier.fillMaxWidth().height(1.dp).background(c.lineHairline))
                            Column(Modifier.padding(vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Text(plain("@${a.account} · ${a.companyFa}"), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), modifier = Modifier.weight(1f))
                                    Pill("${faNum(a.flows)} اتوماسیون", Tone.NEUTRAL)
                                }
                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Num(a.runs.toString(), "ساخت", Modifier.weight(1f)); Num(a.published.toString(), "انتشار", Modifier.weight(1f)); Num(usdShort(a.costUsd), "هزینه", Modifier.weight(1f), latin = true)
                                }
                                val best = a.best
                                if (best != null) Row(
                                    Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).clickable(role = Role.Button) { nav.go("publication/${best.ref}") },
                                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
                                ) {
                                    PubCover(best.account, "", best.thumbFileId, Modifier.size(width = 30.dp, height = 42.dp), radius = 8.dp, text = false)
                                    Text(plain("بهترین: ${best.titleFa}"), style = Divan.type.micro, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                                } else Text("بهترین: وقتی بازدیدها برسد", style = Divan.type.micro, color = c.textMuted)
                            }
                        }
                    }
                }
                item(key = "foot") { Text("همین خلاصه، آخر هفته در گزارش هفتگی تو هم می‌آید.", style = Divan.type.micro, color = c.textMuted) }
            }
        }
    }
}

@Composable
private fun Num(v: String, label: String, modifier: Modifier, latin: Boolean = false) {
    val c = Divan.colors
    Column(modifier) {
        Text(if (latin) plain(v) else androidx.compose.ui.text.AnnotatedString(faText(v)), style = Divan.type.bodyStrong)
        Text(label, style = Divan.type.micro, color = c.textMuted)
    }
}
