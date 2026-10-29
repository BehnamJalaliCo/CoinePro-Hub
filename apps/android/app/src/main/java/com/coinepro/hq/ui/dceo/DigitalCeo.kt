package com.coinepro.hq.ui.dceo

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.decisionKind
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.net.DceoStats
import com.coinepro.hq.core.net.Principle
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
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.RichText
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.StatTile
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v16.ChipRow
import com.coinepro.hq.ui.v16.Notice
import com.coinepro.hq.ui.v17.RefChip
import com.coinepro.hq.ui.v17.RefTone
import com.coinepro.hq.ui.v18.Confidence
import com.coinepro.hq.ui.v18.PRINCIPLE
import com.coinepro.hq.ui.v18.VERDICT3
import com.coinepro.hq.ui.v18.mgmt
import com.coinepro.hq.ui.v18.pct01

// «مدیر کل دیجیتال» (contract §21.10), mirroring apps/web/src/app/(app)/digital-ceo/page.tsx: it only predicts. It never approves, rejects,
// messages or notifies, at any accuracy. Every prediction is sealed before the owner decides and scored after.

private val WINDOWS = listOf(SegOption("30d", "۳۰ روز"), SegOption("90d", "۹۰ روز"), SegOption("all", "همه"))

/** Reliability: each confidence bucket's hit rate against the bucket's middle (a calibrated predictor sits on it). Left to right. */
@Composable
private fun Calibration(s: DceoStats) {
    val c = Divan.colors
    if (s.calibration.isEmpty()) return Text("هنوز داده‌ای نیست.", style = Divan.type.caption, color = c.textMuted)
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        for (b in s.calibration) {
            val (lo, hi) = b.bucket.split('-').map { it.toFloatOrNull() ?: 0f }.let { (it.getOrNull(0) ?: 0f) to (it.getOrNull(1) ?: 1f) }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Fig(b.bucket, Modifier.width(64.dp), style = Divan.type.figureSmall, color = c.textMuted)
                CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                    Box(Modifier.weight(1f).height(12.dp).clip(CircleShape).background(c.tile)) {
                        Box(Modifier.fillMaxWidth(b.hitRate.toFloat().coerceIn(0f, 1f)).height(12.dp).clip(CircleShape).background(c.silverInk.copy(alpha = 0.7f)))
                        Box(Modifier.fillMaxWidth(((lo + hi) / 2).coerceIn(0f, 1f))) { Box(Modifier.align(Alignment.CenterEnd).width(2.dp).height(12.dp).background(c.goldFill)) }
                    }
                }
                Text(buildAnnotatedString { fig(pct01(b.hitRate)); append(" از ${b.n}") }, Modifier.width(76.dp), style = Divan.type.small, color = c.textSecondary, maxLines = 1)
            }
        }
        Text("نوار: درصد درست در هر بازه‌ی اطمینان؛ خط طلایی: آنچه پیش‌بین وعده داده بود.", style = Divan.type.micro, color = c.textMuted)
    }
}

@Composable
private fun PrincipleRow(p: Principle) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    var edit by rememberSaveable(p.ref) { mutableStateOf(false) }
    var text by rememberSaveable(p.ref) { mutableStateOf(p.textFa) }
    fun save(body: String, status: String) = action.mgmt(toasts) { env.api.editPrinciple(p, body, status); env.cache.invalidate("dceo"); edit = false }
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(if (p.status == "proposed") c.softGold else c.tile).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            Fig(p.ref, style = Divan.type.figureSmall, color = c.textMuted)
            Text(buildAnnotatedString { append("نسخه‌ی "); fig("${p.version}") }, style = Divan.type.micro, color = c.textMuted)
            if (p.editedByOwner) Text("ویرایش تو", style = Divan.type.micro, color = c.textMuted)
            Text(ago(p.updatedAt), style = Divan.type.micro, color = c.textMuted)
            LabelPill(PRINCIPLE[p.status], p.status)
        }
        if (edit) HqTextField(text, { text = it }, "متن ${p.ref}", Modifier.fillMaxWidth(), singleLine = false, minLines = 2, maxLength = 500)
        else Text(p.textFa, style = Divan.type.body.copy(textDecoration = if (p.status == "retired") TextDecoration.LineThrough else null), color = if (p.status == "retired") c.textMuted else c.textPrimary)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            p.sources.forEach { RefChip(it.ref, tone = RefTone.NEUTRAL) }
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            if (edit) {
                HqButton("نسخه‌ی تازه", { save(text.trim(), "active") }, size = BtnSize.SM, variant = BtnVariant.PRIMARY, enabled = text.isNotBlank() && text.trim() != p.textFa, loading = action.busy)
                HqButton("انصراف", { edit = false; text = p.textFa }, size = BtnSize.SM, variant = BtnVariant.GHOST)
            } else {
                if (p.status == "proposed") HqButton("بپذیر", { action.mgmt(toasts) { env.api.acceptPrinciple(p.ref); env.cache.invalidate("dceo") } }, size = BtnSize.SM, icon = DivanIcon.SEAL, loading = action.busy)
                if (p.status != "retired") {
                    HqButton("ویرایش", { edit = true }, size = BtnSize.SM, variant = BtnVariant.GHOST, icon = DivanIcon.EDIT)
                    HqButton("کنار بگذار", { save(p.textFa, "retired") }, size = BtnSize.SM, variant = BtnVariant.GHOST, icon = DivanIcon.CLOSE)
                } else HqButton("دوباره فعال", { save(p.textFa, "active") }, size = BtnSize.SM, variant = BtnVariant.GHOST, icon = DivanIcon.REFRESH)
            }
        }
    }
}

@Composable
fun DigitalCeoScreen() {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val view = rememberQuery("dceo:view", "dceo") { digitalCeo() }
    val settings = rememberQuery("owner-settings", "settings") { ownerSettings() }
    val principles = rememberQuery("dceo:principles", "dceo") { principles() }
    var win by rememberSaveable { mutableStateOf("90d") }
    var correct by rememberSaveable { mutableStateOf<Boolean?>(null) }
    val preds = rememberQuery("dceo:predictions:${correct ?: ""}", "dceo") { predictions(correct).items }
    val r = refresher(view, principles, preds)
    val action = rememberAction()
    var adding by remember { mutableStateOf(false) }
    var newText by remember { mutableStateOf("") }
    var confirmBefore by remember { mutableStateOf(false) }
    val s = view.data?.stats?.firstOrNull { it.window == win }
    val cfg = view.data?.settings
    val hidden = view.data?.hidden ?: 0
    fun setReveal(reveal: String) = action.mgmt(toasts) {
        val base = settings.data ?: env.api.ownerSettings()
        val cur = cfg ?: return@mgmt
        val out = env.api.saveOwnerSettings(base.version, mapOf("digital_ceo" to com.coinepro.hq.core.net.Api.jsonBody.encodeToJsonElement(com.coinepro.hq.core.net.DceoSettings.serializer(), cur.copy(reveal = reveal))))
        settings.set(out)
        env.cache.invalidate("dceo", "settings")
        confirmBefore = false
        toasts.ok(if (reveal == "before") "از این به بعد پیش‌بینی را پیش از تصمیم میبینی؛ این‌ها در دقت تمیز شمرده نمیشوند." else "پیش‌بینی تا تصمیم تو پنهان میماند.")
    }
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            PageHeader("مدیر کل دیجیتال", eyebrow = "فقط پیش‌بینی: هرگز تأیید، رد، پیام یا اعلان نمیسازد") {
                if (cfg != null) Segmented(listOf(SegOption("after", "بعد از تصمیم"), SegOption("before", "پیش از تصمیم")), cfg.reveal, { v -> if (v == "before" && hidden < 30) confirmBefore = true else setReveal(v) }, Modifier.fillMaxWidth())
            }
        }
        item {
            Text(
                "برای هر کارتی که تو تصمیم میگیری، پیش از تصمیمت پیش‌بینی میکند و آن را مُهر میکند: روش پایه (نرخ تأیید گذشته‌ی تو بر اساس نوع، ریسک و پیشنهاددهنده، بی‌مدل) و برای کارت متوسط و پرریسک پیش‌بینی مدل" +
                    (cfg?.let { " (حداکثر ${it.maxModelPerDay} در روز${if (it.modelPredictions) "" else "؛ الان خاموش"})" } ?: "") +
                    ". بعد از تصمیم تو سنجیده میشود. هر چه درباره‌ی تو ثبت میشود همین‌جا دیده میشود.",
                style = Divan.type.small, color = c.textSecondary,
            )
        }
        view.error?.let { e -> if (view.data == null) item { ErrorBlock(e, { view.refresh() }) } }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Segmented(WINDOWS, win, { win = it }, Modifier.fillMaxWidth())
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    if (cfg?.reveal == "before") {
                        DIcon(DivanIcon.URGENT, size = 14.dp, tint = c.warning)
                        Text("پیش‌بینی پیش از تصمیم دیده میشود؛ در دقت تمیز نیست", style = Divan.type.caption, color = c.warning)
                    } else {
                        DIcon(DivanIcon.LOCK, size = 14.dp, tint = c.textMuted)
                        Text("تا تصمیم تو پنهان؛ $hidden پیش‌بینی پنهان تا امروز", style = Divan.type.caption, color = c.textMuted)
                    }
                }
            }
        }
        item {
            if (s == null) Skeleton(Modifier.fillMaxWidth().height(220.dp), radius = 14.dp)
            else Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    StatTile("دقت", pct01(s.accuracy), Modifier.weight(1f), sub = "از ${s.n} پیش‌بینی پنهان")
                    StatTile("روش پایه", pct01(s.baselineAccuracy), Modifier.weight(1f), sub = "بی‌مدل")
                }
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    StatTile("مدل", pct01(s.modelAccuracy), Modifier.weight(1f), sub = "فقط کارت متوسط و پرریسک")
                    StatTile("Brier", s.brier?.let { com.coinepro.hq.ui.v17.num(it) } ?: "—", Modifier.weight(1f), sub = "کمتر بهتر؛ ۰ یعنی بی‌خطا")
                }
            }
        }
        if (hidden < 30) item {
            Notice(DivanIcon.URGENT, c.softWarning, c.warning) { Text("دقت هنوز سنجیده نشده: کمتر از ۳۰ پیش‌بینی پنهان داریم و عددها با چند کارت زیاد جابه‌جا میشوند.", style = Divan.type.caption, color = c.textPrimary) }
        }
        item {
            HqCard(Modifier.fillMaxWidth()) {
                SectionTitle("کالیبراسیون", note = "آیا «۷۰٪ مطمئنم» واقعاً ۷۰٪ درست است؟")
                Box(Modifier.padding(top = 10.dp)) { if (s != null) Calibration(s) else Skeleton(Modifier.fillMaxWidth().height(96.dp)) }
            }
        }
        item {
            HqCard(Modifier.fillMaxWidth()) {
                SectionTitle("به تفکیک نوع کارت")
                val kinds = s?.byKind?.entries?.sortedByDescending { it.value.n }.orEmpty()
                if (kinds.isEmpty()) Text("هنوز داده‌ای نیست.", Modifier.padding(top = 8.dp), style = Divan.type.caption, color = c.textMuted)
                else Column(Modifier.padding(top = 6.dp)) {
                    kinds.forEachIndexed { i, (k, v) ->
                        if (i > 0) HorizontalDivider(color = c.lineDivider)
                        val kind = decisionKind(k)
                        Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            DIcon(kind.icon, size = 15.dp, tint = c.goldInk)
                            Text(kind.fa, Modifier.weight(1f), style = Divan.type.small, color = c.textPrimary)
                            Text("${v.n} کارت", style = Divan.type.micro, color = c.textMuted)
                            Fig(pct01(v.accuracy), Modifier.width(44.dp), style = Divan.type.figureSmall.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                        }
                    }
                }
            }
        }
        item {
            HqCard(Modifier.fillMaxWidth()) {
                SectionTitle("اصول", note = "هر شنبه از تعامل‌های هفته و پیش‌بینی‌های غلط پیشنهاد میشود؛ تو میپذیری، ویرایش میکنی یا کنار میگذاری") {
                    HqButton("اصل تازه", { adding = true }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.ADD)
                }
                val order = listOf("proposed", "active", "retired")
                val ps = principles.data?.sortedWith(compareBy<Principle> { order.indexOf(it.status) }.thenBy { it.ref })
                Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    when {
                        ps == null -> Skeleton(Modifier.fillMaxWidth().height(160.dp))
                        ps.isEmpty() -> Empty("هنوز اصلی نیست", icon = DivanIcon.LEARNING)
                        else -> ps.forEach { PrincipleRow(it) }
                    }
                }
            }
        }
        item {
            HqCard(Modifier.fillMaxWidth()) {
                SectionTitle("پیش‌بینی‌ها", note = "فقط کارت‌های تصمیم‌گرفته (یا همه، وقتی پیش از تصمیم نشان داده شود)")
                Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    ChipRow {
                        FilterChip("همه", correct == null, { correct = null })
                        FilterChip("درست", correct == true, { correct = true })
                        FilterChip("نادرست", correct == false, { correct = false })
                    }
                    val list = preds.data
                    when {
                        list == null -> Skeleton(Modifier.fillMaxWidth().height(200.dp))
                        list.isEmpty() -> Empty("پیش‌بینی‌ای نیست", icon = DivanIcon.HOLDING)
                        else -> list.forEach { p ->
                            val v = VERDICT3[p.verdict] ?: VERDICT3.getValue("approve")
                            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    RefChip(p.decision)
                                    p.kind?.let { Text(decisionKind(it).fa, style = Divan.type.micro, color = c.textMuted) }
                                    Box(Modifier.weight(1f))
                                    if (p.correct == null) Pill("منتظر تصمیم", Tone.NEUTRAL) else Pill(if (p.correct) "درست" else "نادرست", if (p.correct) Tone.POS else Tone.NEG, icon = if (p.correct) DivanIcon.SEAL else DivanIcon.REJECT)
                                }
                                p.title?.let { Text(it, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary) }
                                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                                    Text("پیش‌بینی", style = Divan.type.caption, color = c.textSecondary)
                                    LabelPill(v)
                                    Confidence(p.confidence, silver = true)
                                    p.actual?.let { a -> Text("تصمیم تو", style = Divan.type.caption, color = c.textSecondary); LabelPill(VERDICT3[a], a) }
                                    Text(if (p.method == "model") "مدل" else "روش پایه", style = Divan.type.micro, color = c.textMuted)
                                    if (p.seenBefore) Text("پیش از تصمیم دیده شد", style = Divan.type.micro, color = c.warning)
                                }
                                p.rationaleFa?.let { RichText(it, style = Divan.type.caption) }
                                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(2.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                                    p.principles.forEach { Fig(it, style = Divan.type.figureSmall, color = c.textMuted) }
                                    Text("مُهر ${jDateTime(p.madeAt)}", style = Divan.type.micro, color = c.textMuted)
                                    Fig("sha256 ${p.sealedHash.take(12)}…", style = Divan.type.figureSmall, color = c.textMuted)
                                }
                            }
                        }
                    }
                    Text("هر پیش‌بینی پیش از تصمیم تو با sha256 همان لحظه مُهر میشود؛ پیش‌بینی‌ای که بعد از تصمیم نوشته شود دور ریخته میشود.", style = Divan.type.micro, color = c.textMuted)
                }
            }
        }
    }
    if (adding) AlertDialog(
        onDismissRequest = { adding = false },
        containerColor = c.overlay,
        title = { Text("اصل تازه", style = Divan.type.h3) },
        text = { HqTextField(newText, { newText = it }, "مثلاً: انتشار در روز تعطیل را مُهر نمیکنم.", Modifier.fillMaxWidth(), singleLine = false, minLines = 3, maxLength = 500) },
        confirmButton = {
            HqButton("ثبت", { action.mgmt(toasts) { env.api.addPrinciple(newText.trim()); env.cache.invalidate("dceo"); adding = false; newText = ""; toasts.ok("اصل فعال شد.") } },
                variant = BtnVariant.PRIMARY, enabled = newText.isNotBlank(), loading = action.busy)
        },
        dismissButton = { HqButton("انصراف", { adding = false }, variant = BtnVariant.GHOST) },
    )
    if (confirmBefore) AlertDialog(
        onDismissRequest = { confirmBefore = false },
        containerColor = c.overlay,
        title = { Text("پیش‌بینی پیش از تصمیم؟", style = Divan.type.h3) },
        text = { Text("دقت هنوز سنجیده نشده: فقط $hidden پیش‌بینی پنهان داریم (دست‌کم ۳۰ لازم است). از این به بعد پیش‌بینی‌هایی که پیش از تصمیم ببینی «دیده‌شده» ثبت میشوند و در دقت تمیز نمیآیند.", style = Divan.type.small, color = c.textSecondary) },
        confirmButton = { HqButton("با این حال نشان بده", { setReveal("before") }, variant = BtnVariant.PRIMARY, loading = action.busy) },
        dismissButton = { HqButton("بماند پنهان", { confirmBefore = false }, variant = BtnVariant.GHOST) },
    )
}
