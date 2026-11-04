package com.coinepro.hq.ui.v31

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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.COMPETITOR_KEY_FA
import com.coinepro.hq.core.data.competitorFigure
import com.coinepro.hq.core.data.competitorNewPages
import com.coinepro.hq.core.data.rankMove
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.net.Competitor
import com.coinepro.hq.core.net.CompetitorDaily
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.Keyword
import com.coinepro.hq.core.net.RankDaily
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.core.net.idText
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.ChartLine
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.LinesChart
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.served

// Contract §31.4 ⟨1.13⟩ the company's «سئو و رقبا» tab: the keywords it watches with their place in the search results, one chart of the
// ranks (a smaller number is a better place), and the competitors with their public figures. No model reads a figure.

@Composable
fun CompanySeo(code: String) {
    val kws = rememberQuery("seo-keywords:$code", "seo", "growth", maxAgeMs = 30_000) { gated(HubFeature.GROWTH) { keywords(code) } }
    val ranks = rememberQuery("seo-ranks:$code", "seo", "growth", maxAgeMs = 60_000) { gated(HubFeature.GROWTH) { ranks(code) } }
    val comps = rememberQuery("seo-competitors:$code", "seo", "growth", maxAgeMs = 30_000) { gated(HubFeature.GROWTH) { competitors(code) } }
    val daily = rememberQuery("seo-competitor-daily:$code", "seo", "growth", maxAgeMs = 60_000) { gated(HubFeature.GROWTH) { competitorDaily(code) } }
    val has = served(HubFeature.GROWTH)
    var addKw by rememberSaveable { mutableStateOf(false) }
    var addCo by rememberSaveable { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        val k = kws.data
        when {
            !has -> Empty("سئو و رقبا با به‌روزرسانی بعدی هاب میاید", icon = DivanIcon.SEARCH)
            k == null && kws.error != null -> ErrorBlock(kws.error, { kws.refresh() })
            k == null -> Skeleton(Modifier.fillMaxWidth().height(180.dp), radius = 16.dp)
            else -> {
                KeywordsCard(code, k, ranks.data.orEmpty()) { addKw = true }
                CompetitorsCard(code, comps.data.orEmpty(), daily.data.orEmpty()) { addCo = true }
            }
        }
    }
    if (addKw) com.coinepro.hq.ui.v14.HqSheet({ addKw = false }, "عبارت تازه", sub = "هر روز جای سایت در نتیجه‌ی جست‌وجو برایش ثبت میشود.") { KeywordForm(code) { addKw = false } }
    if (addCo) com.coinepro.hq.ui.v14.HqSheet({ addCo = false }, "رقیب تازه", sub = "فقط عددهای عمومی‌اش را میخوانیم.") { CompetitorForm(code) { addCo = false } }
}

/** The keywords, the rank chart and, per keyword, the place now and the move since about a week ago. */
@Composable
fun KeywordsCard(code: String, kws: List<Keyword>, ranks: List<RankDaily>, onAdd: () -> Unit) {
    val env = LocalEnv.current
    val c = Divan.colors
    val toasts = LocalToasts.current
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("عبارت‌های جست‌وجو", note = "کمتر یعنی بهتر؛ رتبه ۱ بالای صفحه‌ی اول است") {
            HqButton("عبارت تازه", onAdd, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.ADD)
        }
        if (kws.isEmpty()) Empty("هنوز عبارتی نمیپاییم", icon = DivanIcon.SEARCH, body = "عبارتی را اضافه کن که میخواهی در گوگل بالا بیاید.")
        else Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            val days = ranks.map { it.day }.distinct().sorted()
            val series = kws.filter { k -> ranks.any { it.keyword.idText == k.id.idText && it.position != null } }
            if (days.size >= 2 && series.isNotEmpty()) {
                val lines = series.mapIndexed { i, k ->
                    val byDay = ranks.filter { it.keyword.idText == k.id.idText }.associate { it.day to it.position }
                    ChartLine(k.id.idText, k.phrase, c.chart[i % c.chart.size], days.map { byDay[it] })
                }
                LinesChart(days.map { jDate(it) }, lines, fmt = { String.format(java.util.Locale.US, "%.0f", it) }, label = "رتبه‌ی عبارت‌ها در جست‌وجو", height = 200.dp)
            } else Text("هنوز رتبه‌ای ثبت نشده؛ بعد از اولین خواندن روزانه میاید.", style = Divan.type.caption, color = c.textMuted)
            kws.forEachIndexed { i, k ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                val mv = rankMove(ranks, k.id.idText)
                val remove = rememberAction()
                val state = rememberAction()
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Column(Modifier.weight(1f)) {
                            Text(plain(k.phrase), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                            Text(plain(k.site + (k.targetUrl?.let { "، هدف: $it" } ?: "")), style = Divan.type.micro, color = c.textMuted, maxLines = 1)
                        }
                        Text(mv.latest?.let { "رتبه " + String.format(java.util.Locale.US, "%.0f", it) } ?: "بدون رتبه", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                        mv.up?.takeIf { it != 0 }?.let { u -> Pill(if (u > 0) "$u پله بهتر" else "${-u} پله بدتر", if (u > 0) Tone.POS else Tone.NEG) }
                        if (mv.approximate) Pill("تقریبی", Tone.SILVER)
                    }
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        HqSwitch(k.state == "on", { on -> state.run { env.api.setKeywordState(code, k.id.idText, if (on) "on" else "paused"); env.cache.invalidate("seo") } }, "پایش این عبارت")
                        Text(if (k.state == "on") "پایش روشن" else "پایش متوقف", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.weight(1f))
                        HqButton("حذف", { remove.run { env.api.deleteKeyword(code, k.id.idText); env.cache.invalidate("seo"); toasts.ok("حذف شد.") } }, variant = BtnVariant.GHOST, size = BtnSize.SM, loading = remove.busy)
                    }
                }
            }
        }
    }
}

/** The competitors with the latest of each public figure, its change over the window, and the new pages they published. */
@Composable
fun CompetitorsCard(code: String, comps: List<Competitor>, daily: List<CompetitorDaily>, onAdd: () -> Unit) {
    val env = LocalEnv.current
    val c = Divan.colors
    val toasts = LocalToasts.current
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("رقبا", note = "عددهای عمومی هر روز؛ پرش بزرگ را مدیر رشد میبیند") {
            HqButton("رقیب تازه", onAdd, variant = BtnVariant.SILVER, size = BtnSize.SM, icon = DivanIcon.ADD)
        }
        if (comps.isEmpty()) Empty("هنوز رقیبی ثبت نشده", icon = DivanIcon.COMPANIES, body = "نام و نشانی صفحه‌هایش را بده تا عددهایش را کنار عددهای خودت ببینی.")
        else Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            comps.forEachIndexed { i, co ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                val remove = rememberAction()
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(plain(co.nameFa), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), modifier = Modifier.weight(1f))
                        HqButton("حذف", { remove.run { env.api.deleteCompetitor(code, co.id.idText); env.cache.invalidate("seo"); toasts.ok("حذف شد.") } }, variant = BtnVariant.GHOST, size = BtnSize.SM, loading = remove.busy)
                    }
                    val where = listOfNotNull(co.site, co.instagram?.let { "اینستاگرام: $it" }, co.youtube?.let { "یوتیوب: $it" }, co.telegram?.let { "تلگرام: $it" }).joinToString("، ")
                    if (where.isNotBlank()) Text(plain(where), style = Divan.type.micro, color = c.textMuted, maxLines = 2)
                    for (key in listOf("followers", "subscribers", "posts")) competitorFigure(daily, co.id.idText, key)?.let { (v, d) ->
                        val move = if (d == 0.0) "بدون تغییر" else (if (d > 0) "+" else "") + String.format(java.util.Locale.US, "%,.0f", d)
                        Text(plain("${COMPETITOR_KEY_FA[key]}: " + String.format(java.util.Locale.US, "%,.0f", v) + " ($move)"), style = Divan.type.caption, color = c.textSecondary)
                    }
                    val pages = competitorNewPages(daily, co.id.idText)
                    if (pages > 0) Text(plain("صفحه‌ی تازه در این ماه: ${pages.toInt()}"), style = Divan.type.caption, color = c.textSecondary)
                }
            }
        }
    }
}

@Composable
fun KeywordForm(code: String, onDone: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val action = rememberAction()
    val c = Divan.colors
    var phrase by rememberSaveable { mutableStateOf("") }
    var site by rememberSaveable { mutableStateOf("") }
    var target by rememberSaveable { mutableStateOf("") }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("عبارت", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        HqTextField(phrase, { phrase = it }, "مثلاً سیگنال رایگان طلا", Modifier.fillMaxWidth(), maxLength = 120)
        Text("سایت", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        HqTextField(site, { site = it }, "example.com", Modifier.fillMaxWidth(), figure = true, maxLength = 120)
        Text("صفحه‌ی هدف (اختیاری)", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        HqTextField(target, { target = it }, "https://example.com/page", Modifier.fillMaxWidth(), figure = true, maxLength = 300)
        HqButton("اضافه کن", {
            action.run { env.api.addKeyword(code, phrase.trim(), site.trim(), target.trim().ifBlank { null }); env.cache.invalidate("seo"); toasts.ok("عبارت اضافه شد."); onDone() }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.ADD, enabled = phrase.trim().length >= 2 && site.trim().length >= 3, loading = action.busy)
    }
}

@Composable
fun CompetitorForm(code: String, onDone: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val action = rememberAction()
    val c = Divan.colors
    var name by rememberSaveable { mutableStateOf("") }
    var site by rememberSaveable { mutableStateOf("") }
    var insta by rememberSaveable { mutableStateOf("") }
    var yt by rememberSaveable { mutableStateOf("") }
    var tg by rememberSaveable { mutableStateOf("") }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("نام", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        HqTextField(name, { name = it }, "نام رقیب", Modifier.fillMaxWidth(), maxLength = 80)
        for ((label, v, set) in listOf(Triple("سایت", site, { x: String -> site = x }), Triple("اینستاگرام", insta, { x: String -> insta = x }), Triple("یوتیوب", yt, { x: String -> yt = x }), Triple("تلگرام", tg, { x: String -> tg = x }))) {
            Text("$label (اختیاری)", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            HqTextField(v, set, label, Modifier.fillMaxWidth(), figure = true, maxLength = 150)
        }
        HqButton("اضافه کن", {
            action.run {
                env.api.addCompetitor(code, name.trim(), site.trim().ifBlank { null }, insta.trim().ifBlank { null }, yt.trim().ifBlank { null }, tg.trim().ifBlank { null })
                env.cache.invalidate("seo"); toasts.ok("رقیب اضافه شد."); onDone()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.ADD, enabled = name.trim().length >= 2, loading = action.busy)
    }
}
