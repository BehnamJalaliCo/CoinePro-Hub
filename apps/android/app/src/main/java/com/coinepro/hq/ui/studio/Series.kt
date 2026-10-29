package com.coinepro.hq.ui.studio

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
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
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.actorFa
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.format.until
import com.coinepro.hq.core.net.KIND_ASPECTS
import com.coinepro.hq.core.net.KIND_CAP
import com.coinepro.hq.core.net.MEDIA_CHECKS
import com.coinepro.hq.core.net.Series
import com.coinepro.hq.core.net.SeriesFormat
import com.coinepro.hq.core.net.SeriesIn
import com.coinepro.hq.core.net.SeriesOverlay
import com.coinepro.hq.core.net.SeriesTarget
import com.coinepro.hq.core.net.Topics
import com.coinepro.hq.core.net.VoiceChoice
import com.coinepro.hq.core.net.accountKey
import com.coinepro.hq.core.net.placementFits
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
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.MeterBar
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.RichText
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.cartable.SealButton
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v16.Chip
import com.coinepro.hq.ui.v16.ChipRow
import com.coinepro.hq.ui.v16.prose
import com.coinepro.hq.ui.v17.CoMark
import com.coinepro.hq.ui.v17.RefChip
import com.coinepro.hq.ui.v17.ScopeChips
import com.coinepro.hq.ui.v19.CHANNEL_FA
import com.coinepro.hq.ui.v19.CHECK_FA
import com.coinepro.hq.ui.v19.DAY_FA
import com.coinepro.hq.ui.v19.DAY_ORDER
import com.coinepro.hq.ui.v19.DAY_SHORT
import com.coinepro.hq.ui.v19.KIND_FA
import com.coinepro.hq.ui.v19.LicenceBadge
import com.coinepro.hq.ui.v19.PLACEMENT_FA
import com.coinepro.hq.ui.v19.Rule
import com.coinepro.hq.ui.v19.SERIES_STATUS
import com.coinepro.hq.ui.v19.buildRrule
import com.coinepro.hq.ui.v19.hhmm
import com.coinepro.hq.ui.v19.media
import com.coinepro.hq.ui.v19.parseRrule
import com.coinepro.hq.ui.v19.scheduleText
import java.util.UUID

// The publishing series (contract §22.2), mirroring apps/web/src/app/(app)/media/series/page.tsx and components/v19/series.tsx: each
// company's series per channel, sealed once with the passkey on the series digest, the platforms' own limits, and the editor.

private val STATUSES = listOf<String?>(null, "proposed", "sealed", "draft", "paused", "retired")
private val RULES = listOf(
    "مُهر روی برنامه است" to "یک بار مُهر میکنی؛ بعد هر آیتمی که همه‌ی چک‌ها را رد کند، در زمان برنامه خودکار منتشر میشود.",
    "ویرایش، مُهر را برمیدارد" to "برنامه‌ی مُهرشده‌ی ویرایش‌شده «منتظر مُهر» میشود؛ تا مُهر دوباره هیچ چیز خودکار نمیرود (409 series_not_sealed).",
    "فقط API رسمی" to "Bot API تلگرام و Graph API اینستاگرام برای حساب تجاری؛ هیچ مرورگر و هیچ کوکی. استوری کانال تلگرام API ندارد: کارت با فایل.",
    "هر چک ردشده، کارت" to "آیتم بیرون از برنامه، یک‌باره، یا با یک چک رد: «منتظر تو» و کارت انتشار (A3).",
    "دو سقف" to "سقف روزانه‌ی هر برنامه و سقف خود پلتفرم (اینستاگرام: 50 پست API در ۲۴ ساعت برای هر حساب).",
    "همه‌ی ترمزها" to "کلید توقف شرکت، توقف deploy، نگه‌داشتن ناظر و حالت نگهبان، انتشار را هم متوقف میکنند.",
)

/** برنامه‌های انتشار: the series (a proposed one first), the week of every channel, the platforms' limits and the rules. [focus0] is the
 *  series a `media_series` card sent the owner to: it comes first, marked. */
@Composable
fun SeriesScreen(focus0: String? = null) {
    val c = Divan.colors
    var company by rememberSaveable { mutableStateOf<String?>(null) }
    var status by rememberSaveable { mutableStateOf<String?>(null) }
    var editing by remember { mutableStateOf<Series?>(null) }
    var making by remember { mutableStateOf(false) }
    val q = rememberQuery("media:series:${company ?: ""}:", "media") { series(company) }
    val r = refresher(q)
    val all = q.data.orEmpty()
    val xs = (if (status == null) all else all.filter { it.status == status })
        .sortedWith(compareBy<Series>({ it.ref != focus0 }, { it.status != "proposed" }, { it.company }))
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            PageHeader("برنامه‌های انتشار", eyebrow = "یک بار مُهر کن؛ بعد هر آیتمی که همه‌ی چک‌ها را رد کند خودش میرود") {
                HqButton("برنامه‌ی تازه", { making = true }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.ADD)
            }
        }
        item { ScopeChips(company, { company = it }, holding = false, allLabel = "همه‌ی شرکت‌ها") }
        item {
            ChipRow {
                for (s in STATUSES) FilterChip(s?.let { SERIES_STATUS[it]?.fa } ?: "همه", status == s, { status = s }, count = if (s == null) all.size else all.count { it.status == s })
            }
        }
        when {
            q.data == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            q.data == null -> item { Skeleton(Modifier.fillMaxWidth().height(320.dp), radius = 16.dp) }
            xs.isEmpty() -> item { HqCard(Modifier.fillMaxWidth()) { Empty("برنامه‌ای نیست", icon = DivanIcon.SEND, body = "برنامه‌ی تازه بساز، یا منتظر پیشنهاد مدیر رسانه بمان.") } }
            else -> for (s in xs) item(key = s.ref) { SeriesCard(s, focus = s.ref == focus0, onChanged = { q.refresh() }) { editing = it } }
        }
        item { ChannelWeek(all) }
        item { LimitsCard() }
        item {
            HqCard(Modifier.fillMaxWidth()) {
                SectionTitle("قاعده‌ی انتشار", note = "هیچ استثنایی ندارد")
                Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    for ((t, b) in RULES) Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        DIcon(DivanIcon.SEAL, Modifier.padding(top = 2.dp), size = 16.dp, tint = c.goldInk)
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Text(t, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                            Text(prose(b), style = Divan.type.caption, color = c.textSecondary)
                        }
                    }
                }
            }
        }
    }
    editing?.let { s ->
        HqSheet({ editing = null }, "ویرایش برنامه", ref = s.ref,
            sub = if (s.status == "sealed" || s.status == "paused") "این برنامه مُهر خورده؛ هر ویرایش آن را به «منتظر مُهر» برمیگرداند و تا مُهر دوباره چیزی خودکار منتشر نمیشود." else "تا مُهرش نکنی هیچ آیتمی نمیسازد.") {
            SeriesEditor(s) { editing = null; q.refresh() }
        }
    }
    if (making) HqSheet({ making = false }, "برنامه‌ی انتشار تازه", sub = "پیش‌نویس ساخته میشود؛ تا مُهرش نکنی هیچ آیتمی نمیسازد. مدیر رسانه هم میتواند پیشنهادش را بدهد.") {
        SeriesEditor(null) { making = false; q.refresh() }
    }
}

/** One series: what it is and where it goes, its schedule and topics, the next runs, and its seal on exactly this version. */
@Composable
private fun SeriesCard(s: Series, focus: Boolean, onChanged: () -> Unit, onEdit: (Series) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val companies = rememberCompanies()
    val accounts = rememberQuery("tools:accounts", "tools", maxAgeMs = 120_000) { serviceAccounts() }
    val seal = rememberAction()
    val other = rememberAction()
    var retire by remember { mutableStateOf(false) }
    val co = companyOf(companies, s.company)
    val st = SERIES_STATUS[s.status] ?: SERIES_STATUS.getValue("draft")
    val sealable = s.status in setOf("draft", "proposed", "paused")
    fun hasKey(acc: String) = accounts.data?.firstOrNull { it.key == acc }?.hasSecret
    fun done() { env.cache.invalidate("media", "decisions", "inbox"); onChanged() }
    HqCard(
        Modifier.fillMaxWidth().then(if (focus) Modifier.border(2.dp, c.goldInk, RoundedCornerShape(16.dp)) else Modifier),
        tahrir = s.status == "proposed" && !focus,
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Box(Modifier.size(44.dp).clip(RoundedCornerShape(12.dp)).background(c.tile), contentAlignment = Alignment.Center) {
                    DIcon(KIND_FA[s.kind]?.icon ?: DivanIcon.SEND, size = 22.dp, tint = c.goldInk)
                }
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(2.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                        CoMark(s.company, height = 11.dp)
                        Text(co.nameFa, style = Divan.type.micro, color = c.textMuted)
                        Fig(s.ref, style = Divan.type.figureSmall, color = c.textMuted)
                        Text(KIND_FA[s.kind]?.fa ?: s.kind, style = Divan.type.micro, color = c.textMuted)
                        Text("نسخه‌ی ${s.version}", style = Divan.type.micro, color = c.textMuted)
                    }
                    Text(s.titleFa, style = Divan.type.h3, color = c.textPrimary)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Pill(st.fa, st.tone, icon = st.icon)
                        if (s.autoPublish) Pill("انتشار خودکار", Tone.SILVER, icon = DivanIcon.SEND) else Pill("هر آیتم کارت", Tone.NEUTRAL, icon = DivanIcon.CARTABLE)
                    }
                }
            }
            s.statusNoteFa?.let { note ->
                Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(if (s.status == "paused") c.softWarning else c.tile).padding(12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    DIcon(DivanIcon.INFO, Modifier.padding(top = 2.dp), size = 16.dp, tint = c.warning)
                    RichText(note, Modifier.weight(1f), style = Divan.type.small, color = c.textPrimary)
                }
            }
            Fact("زمان‌بندی (منطقه‌ی زمانی تو)") {
                Text(buildAnnotatedString { append(scheduleText(s.schedule)); append(" · سقف روزانه ${s.maxPerDay}") }, style = Divan.type.small, color = c.textPrimary)
            }
            Fact("قالب") {
                Text(buildAnnotatedString {
                    fig(s.format.aspect)
                    s.format.durationS?.let { append("، "); fig("${it}s") }
                    append(if (s.format.voice != null) "، با صدای هاب" else "، بی‌صدا")
                    if (s.format.captions) append("، زیرنویس سوخته")
                    append("، " + if (s.format.music == "none") "بی‌موسیقی" else "موسیقی کتابخانه")
                }, style = Divan.type.small, color = c.textPrimary)
            }
            Fact("جای انتشار (فقط API رسمی)") {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    for (t in s.targets) {
                        val ok = hasKey(t.account)
                        Row(
                            Modifier.clip(CircleShape).background(if (ok == false) c.softWarning else c.tile).padding(horizontal = 10.dp, vertical = 4.dp),
                            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
                        ) {
                            Text(PLACEMENT_FA[t.placement] ?: t.placement, style = Divan.type.caption, color = if (ok == false) c.warning else c.textPrimary)
                            Fig(t.account, style = Divan.type.figureSmall, color = c.textMuted)
                            if (ok == false) Text("· بی‌کلید", style = Divan.type.micro, color = c.warning)
                            else if (t.placement == "telegram_story") Text("· کارت با فایل", style = Divan.type.micro, color = c.textMuted)
                        }
                    }
                }
            }
            Fact("موضوع‌ها") {
                val pool = s.topics?.pool.orEmpty()
                if (pool.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    for (t in pool) Text(prose(t), Modifier.clip(CircleShape).background(c.tile).padding(horizontal = 8.dp, vertical = 2.dp), style = Divan.type.caption, color = c.textSecondary)
                } else Text(prose(s.topics?.ruleFa ?: "—"), style = Divan.type.small, color = c.textSecondary)
            }
            if (s.status == "sealed" && s.nextAt.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                DIcon(DivanIcon.TIME, size = 14.dp, tint = c.textSecondary)
                Text("بعدی:", style = Divan.type.caption, color = c.textSecondary)
                s.nextAt.take(3).forEachIndexed { i, at ->
                    Text(jDateTime(at) + if (i == 0) " (${until(at)})" else "", Modifier.clip(CircleShape).background(if (i == 0) c.softGold else c.tile).padding(horizontal = 8.dp, vertical = 2.dp), style = Divan.type.micro, color = if (i == 0) c.goldInk else c.textSecondary)
                }
                s.today?.let { Text("· امروز ${it.made} ساخته، ${it.published} منتشر", style = Divan.type.micro, color = c.textMuted) }
            }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                Text("چک‌ها:", style = Divan.type.micro, color = c.textMuted)
                for (k in MEDIA_CHECKS) Text(CHECK_FA[k]?.fa ?: k, Modifier.clip(CircleShape).background(c.tile).padding(horizontal = 8.dp, vertical = 2.dp), style = Divan.type.micro, color = c.textMuted)
            }
            HorizontalDivider(color = c.lineDivider)
            when {
                sealable -> Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    SealButton(s.company, co.nameFa, co.nameEn, co.holding, busy = seal.busy, size = 64.dp) {
                        seal.media(toasts) {
                            env.api.sealSeries(s) { a, t -> env.auth.stepUp(act, a, t) }
                            done()
                            toasts.ok("برنامه‌ی ${s.ref} مُهر شد؛ از این به بعد هر آیتمی که همه‌ی چک‌ها را رد کند${if (s.autoPublish) " خودکار" else " با کارت تو"} منتشر میشود.")
                        }
                    }
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(if (s.status == "paused") "مُهر دوباره برای ادامه" else "مُهر این برنامه", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                        Text(buildAnnotatedString { append("یک بار، روی همین نسخه: "); fig("digest ${s.digest.take(12)}…") }, style = Divan.type.caption, color = c.textSecondary)
                    }
                }
                s.status == "sealed" -> Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        DIcon(DivanIcon.SEAL, size = 16.dp, tint = c.positive)
                        Text("مُهر خورد" + (s.sealedAt?.let { "، ${jDateTime(it)}" } ?: ""), style = Divan.type.caption, color = c.textSecondary)
                        s.decisionRef?.let { RefChip(it) }
                    }
                    Fig("digest ${s.digest.take(16)}…", style = Divan.type.figureSmall, color = c.textMuted)
                }
            }
            if (s.status != "retired") FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                HqButton("ویرایش", { onEdit(s) }, size = BtnSize.SM, icon = DivanIcon.EDIT)
                if (s.status == "sealed") HqButton("توقف", {
                    other.media(toasts) { env.api.pauseSeries(s.ref); done(); toasts.info("متوقف شد؛ با مُهر دوباره ادامه میدهد.") }
                }, size = BtnSize.SM, variant = BtnVariant.GHOST, icon = DivanIcon.PAUSE, loading = other.busy)
                HqButton("بازنشسته", { retire = true }, size = BtnSize.SM, variant = BtnVariant.GHOST, icon = DivanIcon.CLOSE)
            }
            s.proposedBy?.let { Text("پیشنهاد ${actorFa(it)}" + if (s.itemsTotal > 0) " · تا امروز ${s.itemsTotal} آیتم" else "", style = Divan.type.micro, color = c.textMuted) }
        }
    }
    if (retire) AlertDialog(
        onDismissRequest = { retire = false },
        containerColor = c.overlay,
        title = { Text("بازنشسته کردن برنامه", style = Divan.type.h3) },
        text = { Text("دیگر آیتم تازه‌ای نمیسازد؛ آیتم‌های ساخته‌شده و تاریخچه‌اش میمانند. برگرداندنش یعنی برنامه‌ی تازه و مُهر تازه.", style = Divan.type.small, color = c.textSecondary) },
        confirmButton = {
            HqButton("بازنشسته کن", {
                other.media(toasts) { env.api.retireSeries(s.ref); retire = false; done(); toasts.info("بازنشسته شد؛ دیگر آیتمی نمیسازد.") }
            }, variant = BtnVariant.DANGER, loading = other.busy)
        },
        dismissButton = { HqButton("نه", { retire = false }, variant = BtnVariant.GHOST) },
    )
}

@Composable
private fun Fact(label: String, content: @Composable () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(label, style = Divan.type.micro, color = Divan.colors.textMuted)
        content()
    }
}

/** A rounded outline in dashes: a slot no seal covers. */
private fun Modifier.dashed(color: androidx.compose.ui.graphics.Color) = drawBehind {
    drawRoundRect(color, cornerRadius = CornerRadius(6.dp.toPx()), style = Stroke(1.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(4.dp.toPx(), 3.dp.toPx()))))
}

private class Slot(val day: String, val time: String, val s: Series)
private class Row7(val account: String, val company: String, val channel: String, val slots: MutableList<Slot>)

/** The sealed schedule per channel: every account, its week from Saturday, each slot gold when a seal covers it. */
@Composable
private fun ChannelWeek(series: List<Series>) {
    val c = Divan.colors
    val companies = rememberCompanies()
    val rows = remember(series) {
        val m = linkedMapOf<String, Row7>()
        for (s in series.filter { it.status != "retired" }) {
            val r = parseRrule(s.schedule) ?: continue
            val days = if (r.freq == "DAILY") DAY_ORDER else r.days
            for (t in s.targets) {
                val row = m.getOrPut(t.account) { Row7(t.account, s.company, t.channel, mutableListOf()) }
                for (d in days) row.slots += Slot(d, hhmm(r.hour, r.minute), s)
            }
        }
        m.values.sortedWith(compareBy({ it.company }, { it.channel }))
    }
    if (rows.isEmpty()) return
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("هفته‌ی هر کانال", note = "طلایی: زیر مُهر، خودکار؛ خط‌چین: بی‌مُهر یا متوقف، چیزی خودکار نمیرود")
        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            for (r in rows) Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    CoMark(r.company, height = 11.dp)
                    Text("${CHANNEL_FA[r.channel] ?: r.channel} ${companyOf(companies, r.company).nameFa}", Modifier.weight(1f, fill = false), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Fig(r.account, style = Divan.type.figureSmall, color = c.textMuted)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    for (d in DAY_ORDER) Column(
                        Modifier.weight(1f).heightIn(min = 60.dp).clip(RoundedCornerShape(8.dp)).background(c.card).padding(3.dp),
                        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(3.dp),
                    ) {
                        Text(DAY_SHORT.getValue(d), style = Divan.type.micro, color = c.textMuted)
                        for (x in r.slots.filter { it.day == d }.sortedBy { it.time }) {
                            val sealed = x.s.status == "sealed"
                            Fig(
                                x.time,
                                Modifier.fillMaxWidth().clip(RoundedCornerShape(6.dp)).then(if (sealed) Modifier.background(c.softGold) else Modifier.dashed(c.lineStrong)).padding(vertical = 2.dp),
                                style = Divan.type.figureSmall.copy(fontSize = 10.sp, textAlign = TextAlign.Center), color = if (sealed) c.goldInk else c.textMuted,
                            )
                        }
                    }
                }
            }
        }
    }
}

/** Each publishing account's own limit and its use; separate from a series' daily cap. */
@Composable
private fun LimitsCard() {
    val c = Divan.colors
    val q = rememberQuery("media:limits", "media", maxAgeMs = 120_000) { mediaLimits() }
    val accounts = rememberQuery("tools:accounts", "tools", maxAgeMs = 120_000) { serviceAccounts() }
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("سقف خود پلتفرم‌ها", note = "جدا از سقف روزانه‌ی هر برنامه؛ پر شدنش یعنی 429 platform_limit و صبر تا ریست")
        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            val xs = q.data
            when {
                xs == null -> Skeleton(Modifier.fillMaxWidth().height(140.dp), radius = 12.dp)
                xs.isEmpty() -> Empty("حسابی تعریف نشده", icon = DivanIcon.SEND)
                else -> for (l in xs) {
                    val a = accounts.data?.firstOrNull { it.key == l.account }
                    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            CoMark(l.company, height = 11.dp)
                            Text(prose(a?.titleFa ?: l.account), Modifier.weight(1f), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            if (a != null) Pill(if (a.hasSecret) "کلید دارد" else "بی‌کلید", if (a.hasSecret) Tone.POS else Tone.WARN, dot = true)
                        }
                        Fig(l.account, style = Divan.type.figureSmall, color = c.textMuted)
                        val per = l.per24h
                        if (per != null && per > 0) {
                            val pct = l.used24h * 100.0 / per
                            MeterBar(pct, tone = if (pct >= 90) BarTone.NEG else if (pct >= 70) BarTone.WARN else BarTone.SILVER)
                            Text(buildAnnotatedString {
                                fig("${l.used24h} / $per", c.textSecondary); append(" پست API در ۲۴ ساعت")
                                l.resetsAt?.let { append(" · ریست ${until(it)}") }
                            }, style = Divan.type.micro, color = c.textMuted)
                        } else Text(buildAnnotatedString { fig(l.used24h.toString(), c.textSecondary); append(" ارسال در ۲۴ ساعت") }, style = Divan.type.micro, color = c.textMuted)
                        l.noteFa?.let { RichText(it, style = Divan.type.micro, color = c.textMuted) }
                    }
                }
            }
        }
    }
}

/** The series editor: company (a new one), title, kind and aspect, where it goes (only placements the platform takes), the schedule in
 *  the owner's zone, topics, the format, automatic publishing and the daily cap. The seven checks are always all seven. */
@Composable
fun SeriesEditor(s: Series?, onSaved: (String) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    val companies = rememberCompanies().filter { it.kind != "holding" }
    val voices = rememberQuery("media:voices", "media") { voices() }
    val key = remember { UUID.randomUUID().toString() }
    val rule0 = s?.let { parseRrule(it.schedule) } ?: Rule("WEEKLY", listOf("SA", "TU"), 18, 30)
    var company by rememberSaveable { mutableStateOf(s?.company) }
    var title by rememberSaveable { mutableStateOf(s?.titleFa.orEmpty()) }
    var kind by rememberSaveable { mutableStateOf(s?.kind?.takeIf { it in KIND_ASPECTS } ?: "reel") }
    var aspect by rememberSaveable { mutableStateOf(s?.format?.aspect ?: "9:16") }
    var targets by remember { mutableStateOf(s?.targets.orEmpty()) }
    var rule by remember { mutableStateOf(rule0) }
    var time by rememberSaveable { mutableStateOf(hhmm(rule0.hour, rule0.minute)) }
    var pool by rememberSaveable { mutableStateOf(s?.topics?.pool.orEmpty().joinToString("\n")) }
    var topicRule by rememberSaveable { mutableStateOf(s?.topics?.ruleFa.orEmpty()) }
    var duration by rememberSaveable { mutableStateOf<Int?>(s?.format?.durationS ?: 15) }
    // "active" = the hub's active voice at save time; null = silent.
    var voice by rememberSaveable { mutableStateOf(if (s != null) s.format.voice?.voiceId else "active") }
    var captions by rememberSaveable { mutableStateOf(s?.format?.captions ?: true) }
    var cta by rememberSaveable { mutableStateOf(s?.format?.overlay?.ctaFa.orEmpty()) }
    var mark by rememberSaveable { mutableStateOf(s?.format?.overlay?.mark ?: true) }
    var auto by rememberSaveable { mutableStateOf(s?.autoPublish ?: false) }
    var cap by rememberSaveable { mutableStateOf(s?.maxPerDay ?: KIND_CAP.getValue("reel")) }
    val active = voices.data?.firstOrNull { it.status == "active" }
    val voiceId = if (voice == "active") active?.id else voice
    val timed = kind == "reel" || kind == "story"
    val topics = Topics(pool.lines().map { it.trim() }.filter { it.isNotEmpty() }, topicRule.trim().ifEmpty { null })
    val ok = company != null && title.trim().length >= 3 && targets.isNotEmpty() && (topics.pool.isNotEmpty() || topics.ruleFa != null) && (rule.freq == "DAILY" || rule.days.isNotEmpty())
    val sealedNow = s?.status == "sealed" || s?.status == "paused"
    fun pickKind(k: String) {
        val a = KIND_ASPECTS.getValue(k).first()
        kind = k; aspect = a; cap = KIND_CAP.getValue(k)
        targets = targets.filter { placementFits(k, a, it.placement) == null }
    }
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        if (s == null) Labelled("کدام شرکت") {
            ChipRow {
                for (co in companies) Chip(company == co.code, { company = co.code; targets = emptyList() }) { ink ->
                    CoMark(co.code, height = 11.dp, ink = ink)
                    Text(co.nameFa ?: co.code, style = Divan.type.small, color = ink, maxLines = 1)
                }
            }
        }
        Labelled("عنوان") { HqTextField(title, { title = it }, "مثلاً: سطح‌های هفته‌ی طلا", Modifier.fillMaxWidth(), maxLength = 80) }
        Labelled("نوع و نسبت") {
            ChipRow { for (k in KIND_ASPECTS.keys) FilterChip(KIND_FA[k]?.fa ?: k, kind == k, { pickKind(k) }) }
            val aspects = KIND_ASPECTS.getValue(kind)
            if (aspects.size > 1) ChipRow {
                for (a in aspects) com.coinepro.hq.ui.v16.Chip(aspect == a, { aspect = a; targets = targets.filter { placementFits(kind, a, it.placement) == null } }) { ink -> Fig(a, style = Divan.type.figureSmall, color = ink) }
            } else Text(buildAnnotatedString { append("نسبت "); fig(aspect) }, style = Divan.type.micro, color = c.textMuted)
        }
        Labelled("جای انتشار (فقط API رسمی تلگرام و اینستاگرام)") {
            val co = company
            if (co == null) Text("اول شرکت را انتخاب کن.", style = Divan.type.caption, color = c.textMuted)
            else Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                for ((p, fa) in PLACEMENT_FA) {
                    val channel = if (p.startsWith("telegram")) "telegram" else "instagram"
                    val t = SeriesTarget(channel, accountKey(channel, co), p)
                    val why = placementFits(kind, aspect, p)
                    val on = targets.any { it.account == t.account && it.placement == p }
                    Row(
                        Modifier.fillMaxWidth().alpha(if (why != null) 0.5f else 1f).clip(RoundedCornerShape(10.dp)).background(if (on) c.softGold else c.tile)
                            .then(if (on) Modifier.border(1.dp, c.lineTahrir, RoundedCornerShape(10.dp)) else Modifier)
                            .clickable(enabled = why == null, role = Role.Checkbox) { targets = if (on) targets.filterNot { it.account == t.account && it.placement == p } else targets + t }
                            .padding(horizontal = 12.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        DIcon(if (on) DivanIcon.SEAL else DivanIcon.ADD, size = 16.dp, tint = if (on) c.goldInk else c.textSecondary)
                        Column(Modifier.weight(1f)) {
                            Text(fa, style = Divan.type.small, color = c.textPrimary)
                            Fig(t.account, style = Divan.type.figureSmall, color = c.textMuted)
                        }
                        if (why != null) Text(why, style = Divan.type.micro, color = c.textMuted)
                        else if (p == "telegram_story") Text("Bot API ندارد: همیشه کارت با فایل".let(::prose), Modifier.width(120.dp), style = Divan.type.micro, color = c.textMuted)
                    }
                }
            }
        }
        Labelled("زمان‌بندی (منطقه‌ی زمانی تو)") {
            Segmented(listOf(SegOption("DAILY", "هر روز"), SegOption("WEEKLY", "روزهای هفته")), rule.freq, { rule = rule.copy(freq = it) }, Modifier.fillMaxWidth())
            if (rule.freq == "WEEKLY") ChipRow {
                for (d in DAY_ORDER) FilterChip(DAY_FA.getValue(d), d in rule.days, { rule = rule.copy(days = if (d in rule.days) rule.days - d else rule.days + d) })
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("ساعت", style = Divan.type.small, color = c.textSecondary)
                HqTextField(time, { v ->
                    val t = v.filter { it.isDigit() || it == ':' }.take(5)
                    time = t
                    Regex("^(\\d{1,2}):(\\d{2})$").find(t)?.let { m ->
                        val h = m.groupValues[1].toInt(); val mi = m.groupValues[2].toInt()
                        if (h in 0..23 && mi in 0..59) rule = rule.copy(hour = h, minute = mi)
                    }
                }, "18:30", Modifier.width(96.dp), figure = true, maxLength = 5)
            }
            Text(buildAnnotatedString { append(scheduleText(buildRrule(rule))); append(" · "); fig(buildRrule(rule)) }, style = Divan.type.micro, color = c.textMuted)
        }
        Labelled("موضوع‌ها") {
            HqTextField(pool, { pool = it }, "هر خط یک موضوع؛ به ترتیب برداشته میشوند", Modifier.fillMaxWidth(), singleLine = false, minLines = 3, maxLength = 2000)
            HqTextField(topicRule, { topicRule = it }, "یا قاعده: مثلاً یک اصطلاح از دانشنامه‌ی آموزش، به ترتیب", Modifier.fillMaxWidth(), maxLength = 200)
        }
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("قالب", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            if (timed) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("مدت", style = Divan.type.small, color = c.textSecondary)
                    HqTextField(duration?.toString().orEmpty(), { v -> duration = v.filter(Char::isDigit).take(3).toIntOrNull() }, "15", Modifier.width(72.dp), figure = true, maxLength = 3)
                    Text("ثانیه", style = Divan.type.small, color = c.textSecondary)
                }
                Text("صدا", style = Divan.type.small, color = c.textSecondary)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    FilterChip("بی‌صدا", voice == null, { voice = null })
                    FilterChip("صدای فعال هاب", voice == "active", { voice = "active" })
                    for (v in voices.data.orEmpty().filter { it.heard.isNotEmpty() }) Chip(voice == v.id, { voice = v.id }) { ink -> Text(prose(v.nameFa), style = Divan.type.small, color = ink, maxLines = 1) }
                }
                voices.data?.firstOrNull { it.id == voiceId }?.let { LicenceBadge(it.licenceCommercial, it.licence) }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    HqSwitch(captions, { captions = it }, "زیرنویس فارسی سوخته")
                    Text("زیرنویس فارسی سوخته", style = Divan.type.small, color = c.textSecondary)
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                DIcon(DivanIcon.LOCK, size = 14.dp, tint = c.textMuted)
                Text("موسیقی: هیچ؛ کتابخانه‌ی موسیقی مجاز نداری.", style = Divan.type.caption, color = c.textMuted)
            }
            HqTextField(cta, { cta = it }, "دعوت روی تصویر (اختیاری)", Modifier.fillMaxWidth(), maxLength = 30)
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                HqSwitch(mark, { mark = it }, "نشان شرکت")
                Text("نشان شرکت", style = Divan.type.small, color = c.textSecondary)
            }
        }
        Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            HqSwitch(auto, { auto = it }, "انتشار خودکار")
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text("انتشار خودکار", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                Text("فقط وقتی هر هفت چک قبول باشد، در زمان برنامه. خاموش: هر آیتم کارت توست. برنامه‌ی تازه را خاموش شروع کن.", style = Divan.type.caption, color = c.textSecondary)
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("سقف روزانه", style = Divan.type.small, color = c.textSecondary)
            HqTextField(cap.toString(), { v -> cap = minOf(10, v.filter(Char::isDigit).take(2).toIntOrNull() ?: 1).coerceAtLeast(1) }, "2", Modifier.width(64.dp), figure = true, maxLength = 2)
            Text("آیتم در روز", style = Divan.type.small, color = c.textSecondary)
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            DIcon(DivanIcon.SEAL, size = 12.dp, tint = c.textMuted)
            Text("چک‌ها همیشه هر هفت تا:", style = Divan.type.micro, color = c.textMuted)
            for (k in MEDIA_CHECKS) Text(CHECK_FA[k]?.fa ?: k, Modifier.clip(CircleShape).background(c.tile).padding(horizontal = 8.dp, vertical = 2.dp), style = Divan.type.micro, color = c.textMuted)
        }
        HqButton(if (s == null) "بساز" else "ذخیره", {
            val co = company ?: return@HqButton
            val body = SeriesIn(
                co, title.trim(), kind, targets, buildRrule(rule), topics,
                SeriesFormat(aspect, if (timed) duration else null, if (timed && voiceId != null) VoiceChoice(voiceId) else null, timed && captions, "none", SeriesOverlay(cta.trim().ifEmpty { null }, mark)),
                MEDIA_CHECKS, auto, cap,
            )
            action.media(toasts) {
                val out = if (s != null) env.api.updateSeries(s, body) else env.api.createSeries(body, key)
                env.cache.invalidate("media", "decisions", "inbox")
                toasts.ok(
                    if (s == null) "برنامه‌ی ${out.ref} ساخته شد؛ تا مُهرش نکنی هیچ آیتمی نمیسازد."
                    else if (sealedNow) "ذخیره شد؛ مُهر قبلی دیگر این نسخه را نمیپوشاند. برای انتشار خودکار دوباره مُهر کن." else "ذخیره شد.",
                )
                onSaved(out.ref)
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = if (s == null) DivanIcon.ADD else DivanIcon.EDIT, enabled = ok, loading = action.busy)
    }
}

@Composable
private fun Labelled(label: String, content: @Composable () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(label, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = Divan.colors.textSecondary)
        content()
    }
}
