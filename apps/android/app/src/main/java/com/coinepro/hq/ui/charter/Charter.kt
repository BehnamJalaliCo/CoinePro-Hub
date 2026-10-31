package com.coinepro.hq.ui.charter

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.actorFa
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.net.Charter
import com.coinepro.hq.core.net.CharterIn
import com.coinepro.hq.core.net.CharterScope
import com.coinepro.hq.core.net.RedLine
import com.coinepro.hq.core.net.charterMax
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
import com.coinepro.hq.designsystem.IconBtn
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.MeterBar
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
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
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v16.Chip
import com.coinepro.hq.ui.v16.ChipRow
import com.coinepro.hq.ui.v16.Labelled
import com.coinepro.hq.ui.v17.CHARTER_STATUS
import com.coinepro.hq.ui.v17.DiffView
import com.coinepro.hq.ui.v17.Heading
import com.coinepro.hq.ui.v17.gov
import java.util.Locale

/** «سند هلدینگ», «الحاقیه‌ی تریدیار». */
@Composable
private fun scopeName(scope: String): String =
    if (scope == "holding") "سند هلدینگ" else "الحاقیه‌ی ${companyOf(rememberCompanies(), scope).nameFa}"

/** اساسنامه (contract §20.2): one holding charter and a company addendum each, versioned; agents read the sealed versions, only the
 *  owner seals. [diff0] opens the shown version against the one before it. */
@Composable
fun CharterScreen(scope0: String? = null, diff0: Boolean = false) {
    val c = Divan.colors
    val q = rememberQuery("charter", "charter") { charter() }
    val companies = rememberCompanies()
    var pick by rememberSaveable { mutableStateOf(scope0) }
    var edit by remember { mutableStateOf<Pair<String, Charter?>?>(null) }
    val r = refresher(q)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("اساسنامه", eyebrow = "ایجنت‌ها میخوانند، هرگز نمینویسند؛ فقط تو مُهر میکنی") }
        item {
            Text(
                "یک سند هلدینگ و برای هر شرکت یک الحاقیه که با آن تعارض ندارد. هر تغییر نسخه‌ی تازه است و تا مُهر تو، هیچ ایجنتی آن را نمیخواند. ایجنت‌ها فقط اصلاحیه پیشنهاد میدهند (کارت «اصلاحیه‌ی اساسنامه» در کارتابل).",
                style = Divan.type.small, color = c.textSecondary,
            )
        }
        val scopes = q.data
        when {
            scopes == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            scopes == null -> item { Skeleton(Modifier.fillMaxWidth().height(360.dp), radius = 16.dp) }
            scopes.isEmpty() -> item { Empty("هنوز اساسنامه‌ای نیست", icon = DivanIcon.REPORT) }
            else -> {
                val s = scopes.firstOrNull { it.scope == (pick ?: scopes.first().scope) } ?: scopes.first()
                // A company without an addendum can get one: companies are data, so every one of them is offered.
                val missing = companies.filter { it.kind != "holding" && scopes.none { x -> x.scope == it.code } }
                item {
                    ChipRow {
                        for (x in scopes) Chip(s.scope == x.scope, { pick = x.scope }) { ink ->
                            if (x.scope == "holding") com.coinepro.hq.designsystem.Monogram(14.dp, ink = ink) else com.coinepro.hq.designsystem.CompanyMark(x.scope, height = 12.dp, mono = true, ink = ink)
                            Text(scopeName(x.scope), style = Divan.type.small.copy(fontWeight = if (s.scope == x.scope) FontWeight.SemiBold else FontWeight.Normal), color = ink, maxLines = 1)
                            if (x.proposed != null) Box(Modifier.size(6.dp).clip(CircleShape).background(c.goldInk))
                        }
                        for (co in missing) FilterChip("+ الحاقیه‌ی ${co.nameFa ?: co.code}", false, { edit = co.code to null })
                    }
                }
                scopeView(s, diff0) { edit = s.scope to (s.proposed ?: s.sealed) }
            }
        }
    }
    edit?.let { (scope, from) -> CharterEditor(scope, from) { edit = null } }
}

private fun androidx.compose.foundation.lazy.LazyListScope.scopeView(s: CharterScope, diff0: Boolean, onEdit: () -> Unit) {
    s.proposed?.let { p -> item(key = "proposed:${s.scope}@${p.version}") { Proposed(s, p) } }
    item(key = "viewer:${s.scope}") { Versions(s, diff0, onEdit) }
    item(key = "how:${s.scope}") {
        val c = Divan.colors
        HqCard(Modifier.fillMaxWidth()) {
            SectionTitle("ایجنت‌ها چطور میخوانند")
            Spacer(Modifier.height(8.dp))
            Text(buildAnnotatedString {
                append("نسخه‌ی مُهرشده‌ی سند هلدینگ و الحاقیه‌ی شرکت، بعد از دستورهای مشترک و پیش از منشور نقش، در بخش cache‌شده‌ی هر اجرا میاید و هر اجرا ثبت میکند کدام نسخه را خواند (مثل ")
                fig("holding@1"); append("). هیچ ابزار نوشتنی برای اساسنامه نیست.")
            }, style = Divan.type.caption, color = c.textSecondary)
            Spacer(Modifier.height(6.dp))
            Text("خط قرمزِ «قاعده» را کد روی خروجی‌ها، پیام‌ها و استوری‌ها میسنجد و متن مشتری را پیش از ارسال نگه میدارد؛ «نمونه‌برداری» کار ناظر است.", style = Divan.type.caption, color = c.textSecondary)
            s.sealed?.let { Spacer(Modifier.height(10.dp)); LengthMeter(it.scope, it.bodyMd) }
        }
    }
}

@Composable
private fun RedLines(lines: List<RedLine>) {
    val c = Divan.colors
    if (lines.isEmpty()) { Text("این نسخه خط قرمز تازه‌ای ندارد؛ خطوط قرمز سند هلدینگ برقرارند.", style = Divan.type.caption, color = c.textMuted); return }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        for (r in lines) Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            DIcon(DivanIcon.LOCK, Modifier.padding(top = 2.dp), size = 16.dp, tint = c.negative)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(r.textFa, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Fig(r.key, style = Divan.type.figureSmall, color = c.textMuted)
                    Pill(if (r.check == "rule") "قاعده: کد میسنجد" else "نمونه‌برداری ناظر", if (r.check == "rule") Tone.LAPIS else Tone.NEUTRAL)
                    r.patterns?.takeIf { it.isNotEmpty() }?.let { Text("${it.size} الگو", style = Divan.type.micro, color = c.textMuted) }
                }
            }
        }
    }
}

/** The length against the limit: the sealed text is read in every run. */
@Composable
private fun LengthMeter(scope: String, body: String) {
    val c = Divan.colors
    val max = charterMax(scope)
    val pct = body.length * 100.0 / max
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row {
            Text("طول (در هر اجرا خوانده میشود)", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f))
            Fig(String.format(Locale.US, "%,d / %,d", body.length, max), style = Divan.type.figureSmall, color = c.textMuted)
        }
        MeterBar(pct, tone = if (pct > 100) BarTone.NEG else if (pct > 85) BarTone.WARN else BarTone.SILVER)
    }
}

/** The proposed version: what changes against the sealed one, its red lines, and the seal bound to its body_sha256. */
@Composable
private fun Proposed(s: CharterScope, p: Charter) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val action = rememberAction()
    val sealed = s.sealed
    var view by rememberSaveable(s.scope) { mutableStateOf(if (sealed != null) "diff" else "text") }
    val diff = if (sealed != null) rememberQuery("charter:diff:${s.scope}:${p.version}:${sealed.version}", "charter") { charterDiff(s.scope, p.version, sealed.version) } else null
    val companies = rememberCompanies()
    val co = companyOf(companies, if (s.scope == "holding") companies.firstOrNull { it.kind == "holding" }?.code else s.scope)
    val name = scopeName(s.scope)
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(c.card).border(1.dp, c.goldInk, RoundedCornerShape(16.dp)).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            LabelPill(CHARTER_STATUS["proposed"])
            Text(buildAnnotatedString { append("نسخه‌ی "); fig(p.version.toString()) }, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
        }
        Text(com.coinepro.hq.designsystem.timesFig("${actorFa(p.createdBy)}، ${jDateTime(p.createdAt)}"), style = Divan.type.caption, color = c.textMuted)
        if (sealed != null) Segmented(listOf(SegOption("diff", "تفاوت با نسخه‌ی ${sealed.version}"), SegOption("text", "متن کامل")), view, { view = it }, Modifier.fillMaxWidth())
        if (view == "diff" && diff != null) {
            val d = diff.data
            if (d == null) Skeleton(Modifier.fillMaxWidth().height(180.dp)) else DiffView(d.diff, Modifier.heightIn(max = 420.dp).verticalScroll(rememberScrollState()))
        } else Box(Modifier.fillMaxWidth().heightIn(max = 420.dp).clip(RoundedCornerShape(12.dp)).background(c.tile).verticalScroll(rememberScrollState()).padding(14.dp)) { Md(p.bodyMd) }
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Heading("خطوط قرمز این نسخه")
            RedLines(p.redLines)
        }
        LengthMeter(p.scope, p.bodyMd)
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(c.tile).padding(16.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
            SealButton(co.code.ifBlank { s.scope }, co.nameFa, co.nameEn, s.scope == "holding" || co.holding, busy = action.busy) {
                action.gov(toasts) {
                    env.api.sealCharter(p) { a, x -> env.auth.stepUp(act, a, x) }
                    env.cache.invalidate("charter", "decisions")
                    toasts.ok("$name، نسخه‌ی ${p.version} مُهر شد؛ از اجرای بعد همه‌ی ایجنت‌ها آن را میخوانند.")
                }
            }
            Text(buildAnnotatedString {
                append("مُهر به همین متن و همین خطوط قرمز بسته است ("); fig("sha256 ${p.bodySha256.take(16)}…"); append(")؛ سرور hash را دوباره حساب میکند.")
            }, style = Divan.type.caption, color = c.textMuted)
        }
    }
}

/** The version list, and one version as text or against the version before it. */
@Composable
private fun Versions(s: CharterScope, diff0: Boolean, onEdit: () -> Unit) {
    val c = Divan.colors
    val versions = rememberQuery("charter:versions:${s.scope}", "charter") { charterVersions(s.scope) }
    var picked by rememberSaveable(s.scope) { mutableStateOf<Int?>(null) }
    val list = versions.data.orEmpty()
    val shown = picked ?: s.sealed?.version
    val prev = shown?.let { v -> list.map { it.version }.filter { it < v }.maxOrNull() }
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        if (shown != null) Viewer(s.scope, shown, prev, diff0)
        else if (s.proposed == null) HqCard(Modifier.fillMaxWidth()) { Empty("هنوز نسخه‌ی مُهرشده‌ای نیست", icon = DivanIcon.REPORT, body = "تا مُهر نشده، فقط چهار خط قرمز مدل عملیاتی اجرا میشود.") }
        HqCard(Modifier.fillMaxWidth()) {
            SectionTitle("نسخه‌ها", note = "هر تغییر نسخه‌ی تازه است؛ هیچ نسخه‌ای پاک نمیشود") {
                HqButton("نسخه‌ی تازه", onEdit, size = BtnSize.SM, icon = DivanIcon.EDIT)
            }
            Spacer(Modifier.height(8.dp))
            if (versions.data == null) Skeleton(Modifier.fillMaxWidth().height(96.dp))
            for (v in list) Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(if (shown == v.version) c.hover else Color.Transparent)
                    .clickable(role = Role.Tab) { picked = v.version }.padding(horizontal = 8.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Fig("v${v.version}", Modifier.width(28.dp), style = Divan.type.figure, color = c.textPrimary)
                Column(Modifier.weight(1f)) {
                    Text(actorFa(v.createdBy), style = Divan.type.caption, color = c.textSecondary)
                    Text(jDate(v.sealedAt ?: v.createdAt, withYear = true), style = Divan.type.micro, color = c.textMuted)
                }
                LabelPill(CHARTER_STATUS[v.status], v.status)
            }
        }
    }
}

@Composable
private fun Viewer(scope: String, version: Int, prev: Int?, diff0: Boolean) {
    val c = Divan.colors
    val q = rememberQuery("charter:version:$scope:$version", "charter") { charterVersion(scope, version) }
    var picked by rememberSaveable(scope, version) { mutableStateOf<String?>(null) }
    val view = picked ?: if (diff0 && prev != null) "diff" else "text"
    val diff = if (view == "diff" && prev != null) rememberQuery("charter:diff:$scope:$version:$prev", "charter") { charterDiff(scope, version, prev) } else null
    val ch = q.data
    if (ch == null) { Skeleton(Modifier.fillMaxWidth().height(360.dp), radius = 16.dp); return }
    HqCard(Modifier.fillMaxWidth()) {
        Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                LabelPill(CHARTER_STATUS[ch.status], ch.status)
                Text(buildAnnotatedString { append("نسخه‌ی "); fig(ch.version.toString()) }, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                Text(if (ch.sealedAt != null) "مُهر ${actorFa(ch.sealedBy)}، ${jDate(ch.sealedAt, withYear = true)}" else jDate(ch.createdAt, withYear = true), style = Divan.type.caption, color = c.textMuted, modifier = Modifier.weight(1f))
            }
            if (prev != null) Segmented(listOf(SegOption("text", "متن"), SegOption("diff", "تفاوت با $prev")), view, { picked = it }, Modifier.fillMaxWidth())
            if (view == "diff" && diff != null) { val d = diff.data; if (d == null) Skeleton(Modifier.fillMaxWidth().height(180.dp)) else DiffView(d.diff) }
            else Md(ch.bodyMd)
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Heading("خطوط قرمز")
                RedLines(ch.redLines)
            }
            Fig("sha256 ${ch.bodySha256}", style = Divan.type.figureSmall, color = c.textMuted, maxLines = 2)
        }
    }
}

/** A new proposed version: the text and the red lines, both bound by the seal. */
@Composable
private fun CharterEditor(scope: String, from: Charter?, onClose: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    var body by rememberSaveable { mutableStateOf(from?.bodyMd ?: "") }
    val lines = remember { mutableStateListOf<RedLine>().apply { addAll(from?.redLines.orEmpty()) } }
    val max = charterMax(scope)
    val bad = body.isBlank() || body.length > max || lines.any { it.key.isBlank() || it.textFa.isBlank() }
    HqSheet(onClose, "${scopeName(scope)}، نسخه‌ی تازه", sub = "نسخه‌ی پیشنهادی میماند تا خودت مُهرش کنی.") {
        Labelled("متن (Markdown)") {
            HqTextField(body, { body = it }, "متن اساسنامه", Modifier.fillMaxWidth(), singleLine = false, minLines = 10, maxLength = max + 2000)
            Fig(String.format(Locale.US, "%,d / %,d", body.length, max), Modifier.align(Alignment.End), style = Divan.type.figureSmall, color = if (body.length > max) c.negative else c.textMuted)
        }
        Labelled("خطوط قرمز") {
            lines.forEachIndexed { i, r ->
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).border(1.dp, c.lineDivider, RoundedCornerShape(12.dp)).padding(10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                            HqTextField(r.key, { v -> lines[i] = r.copy(key = v.filter { it.isLetterOrDigit() || it == '_' }.lowercase()) }, "key", Modifier.width(150.dp), maxLength = 60, figure = true)
                        }
                        FilterChip("قاعده (کد)", r.check == "rule", { lines[i] = r.copy(check = "rule") })
                        FilterChip("نمونه‌برداری", r.check == "sample", { lines[i] = r.copy(check = "sample") })
                        Spacer(Modifier.weight(1f))
                        IconBtn(DivanIcon.CLOSE, "حذف خط قرمز", { lines.removeAt(i) })
                    }
                    HqTextField(r.textFa, { lines[i] = r.copy(textFa = it) }, "متن خط قرمز", Modifier.fillMaxWidth(), maxLength = 300)
                    if (r.check == "rule") CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                        HqTextField(r.patterns.orEmpty().joinToString("\n"), { v -> lines[i] = r.copy(patterns = v.split('\n').let { xs -> xs.filterIndexed { k, x -> x.isNotBlank() || k < xs.size - 1 } }) }, "الگوها، هر خط یکی", Modifier.fillMaxWidth(), singleLine = false, minLines = 2, figure = true)
                    }
                }
            }
            HqButton("خط قرمز تازه", { lines.add(RedLine("", "", "sample", null)) }, variant = BtnVariant.GHOST, size = BtnSize.SM, icon = DivanIcon.ADD)
        }
        HqButton("ثبت نسخه‌ی پیشنهادی", {
            action.gov(toasts) {
                val out = env.api.proposeCharter(scope, CharterIn(body, lines.map { r -> r.copy(key = r.key.trim(), patterns = if (r.check == "rule") r.patterns?.filter { it.isNotBlank() }?.ifEmpty { null } else null) }))
                env.cache.invalidate("charter")
                toasts.ok("نسخه‌ی ${out.version} پیشنهاد شد؛ تا مُهر تو هیچ ایجنتی آن را نمیخواند.")
                onClose()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEND, enabled = !bad, loading = action.busy)
    }
}
