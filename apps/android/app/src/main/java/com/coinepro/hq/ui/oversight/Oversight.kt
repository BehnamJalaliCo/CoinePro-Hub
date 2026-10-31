package com.coinepro.hq.ui.oversight

import androidx.compose.foundation.layout.Box
import com.coinepro.hq.ui.itemMotion
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
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
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDirection
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.actorFa
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.format.until
import com.coinepro.hq.core.net.Finding
import com.coinepro.hq.core.net.Protocol
import com.coinepro.hq.designsystem.Avatar
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.RichText
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.media.Composer
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.AREA_FA
import com.coinepro.hq.ui.v14.CHALLENGE_STATUS
import com.coinepro.hq.ui.v14.FINDING_STATUS
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v14.METHOD_FA
import com.coinepro.hq.ui.v14.ORDER_STATUS
import com.coinepro.hq.ui.v14.SEVERITY_ORDER
import com.coinepro.hq.ui.v14.ScoreBar
import com.coinepro.hq.ui.v14.SeverityPill
import com.coinepro.hq.ui.v14.Spark
import com.coinepro.hq.ui.v14.Tag
import com.coinepro.hq.ui.v14.rruleFa
import com.coinepro.hq.ui.v14.spoken

private enum class Tab(val fa: String) { SUMMARY("خلاصه"), FINDINGS("یافته‌ها"), PROTOCOLS("پروتکل‌ها"), CHALLENGES("چالش‌ها"), ORDERS("دستورهای دائمی") }

private fun Finding.live() = status !in setOf("verified", "closed")

/** ناظر کل (contract §18.1): the owner's eyes on everything — holds waiting on the owner, compliance, findings, the
 *  protocol register, challenges and standing orders; the conversation (thread N) is one tap away. */
@Composable
fun OversightScreen() {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val summary = rememberQuery("oversight:summary", "oversight", maxAgeMs = 30_000) { oversight() }
    val holds = rememberQuery("oversight:holds", "oversight") { holds() }
    val findings = rememberQuery("oversight:findings", "oversight") { findings().items }
    val protocols = rememberQuery("oversight:protocols", "oversight", maxAgeMs = 120_000) { protocols() }
    val challenges = rememberQuery("oversight:challenges", "oversight") { challenges().items }
    val orders = rememberQuery("oversight:orders", "oversight") { standingOrders() }
    val r = refresher(summary, holds, findings, protocols, challenges, orders)
    val action = rememberAction()
    var tab by rememberSaveable { mutableStateOf(Tab.SUMMARY) }
    var finding by remember { mutableStateOf<Finding?>(null) }
    var protocol by remember { mutableStateOf<Protocol?>(null) }
    var showClosed by rememberSaveable { mutableStateOf(false) }
    var area by rememberSaveable { mutableStateOf<String?>(null) }
    var forAll by rememberSaveable { mutableStateOf(false) }

    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            // The eyebrow gets the full width; the chat button sits on the title's line, so neither wraps beside the other.
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("رتبه‌ی دوم، کنار مشاور کل؛ در نبود تو بالاتر", style = Divan.type.caption, color = c.textMuted)
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                    Avatar("overseer", size = 52.dp, state = "working")
                    Text("ناظر کل", style = Divan.type.h1, modifier = Modifier.weight(1f))
                    HqButton("گفت‌وگو", { nav.go("oversight/chat") }, size = BtnSize.SM, icon = DivanIcon.MESSAGES)
                }
            }
        }
        item {
            com.coinepro.hq.designsystem.ScrollRow {
                for (t in Tab.entries) {
                    val n = when (t) {
                        Tab.FINDINGS -> findings.data?.count { it.live() }
                        Tab.SUMMARY -> holds.data?.size?.takeIf { it > 0 }
                        else -> null
                    }
                    FilterChip(t.fa, tab == t, { tab = t }, count = n)
                }
            }
        }
        when (tab) {
            Tab.SUMMARY -> {
                val hs = holds.data.orEmpty()
                if (hs.isNotEmpty()) item {
                    HqCard(Modifier.fillMaxWidth(), tahrir = true) {
                        SectionTitle("نگه‌داشته‌ها، منتظر تو", note = "ناظر نگه داشته؛ فقط تو آزاد یا لغو میکنی")
                        for (h in hs) {
                            Column(Modifier.padding(top = 10.dp).fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.softGold).padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    CompanyMark(h.company, height = 14.dp, mono = true, ink = c.textSecondary)
                                    RichText(h.action.summaryFa, Modifier.weight(1f), style = Divan.type.bodyStrong, color = c.textPrimary)
                                    Fig(h.ref, style = Divan.type.figureSmall, color = c.textMuted)
                                }
                                RichText(h.reasonMd, style = Divan.type.small)
                                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    HqButton("آزاد کن", {
                                        action.run {
                                            env.api.releaseHold(h.ref) { a, t -> env.auth.stepUp(act, a, t) }
                                            env.cache.invalidate("oversight", "inbox")
                                            toasts.ok("آزاد شد؛ اقدام ادامه پیدا میکند.")
                                        }
                                    }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.SEAL, loading = action.busy)
                                    HqButton("لغو کن", {
                                        action.run {
                                            env.api.cancelHold(h.ref)
                                            env.cache.invalidate("oversight", "inbox")
                                            toasts.info("لغو شد؛ اقدام انجام نمیشود.")
                                        }
                                    }, variant = BtnVariant.DANGER, size = BtnSize.SM)
                                    Text(ago(h.heldAt), style = Divan.type.micro, color = c.textMuted)
                                }
                            }
                        }
                    }
                }
                val s = summary.data
                when {
                    s == null && summary.error != null -> item { ErrorBlock(summary.error, { summary.refresh() }) }
                    s == null -> item { Skeleton(Modifier.fillMaxWidth().height(220.dp), radius = 16.dp) }
                    else -> {
                        item {
                            HqCard(Modifier.fillMaxWidth()) {
                                SectionTitle(if (s.watch.on) "در نبودت (در جریان)" else "آخرین «در نبودت»", note = s.watch.since?.let { "از ${jDateTime(it)}" }) {
                                    if (s.watch.on) Pill("نگهبان روشن", Tone.GOLD, live = true)
                                }
                                Md(s.watch.summaryMd, Modifier.padding(top = 8.dp))
                            }
                        }
                        item {
                            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                val open = s.findingsOpen
                                Tile("یافته‌ی باز", "${SEVERITY_ORDER.sumOf { open[it] ?: 0 }}", "${open["critical"] ?: 0} بحرانی، ${open["high"] ?: 0} بالا", Modifier.weight(1f), c.negative) { tab = Tab.FINDINGS }
                                Tile("پروتکل فعال", "${s.protocols.active}", "${s.protocols.failedToday} با مشکل در آخرین اجرا", Modifier.weight(1f)) { tab = Tab.PROTOCOLS }
                            }
                        }
                        item {
                            val w = s.challengesWeek
                            Row(
                                Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.card).clickable(role = Role.Button) { tab = Tab.CHALLENGES }.padding(14.dp),
                                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
                            ) {
                                DIcon(DivanIcon.STAR, size = 20.dp, tint = c.goldInk)
                                Text("چالش‌های این هفته: ${w.issued + w.accepted} در جریان، ${w.submitted} تحویل شده", style = Divan.type.small, modifier = Modifier.weight(1f))
                                DIcon(DivanIcon.NEXT, size = 16.dp, tint = c.textMuted)
                            }
                        }
                        item {
                            HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(horizontal = 14.dp, vertical = 12.dp)) {
                                SectionTitle("انطباق شرکت‌ها", note = "نتیجه‌ی پروتکل‌ها و یافته‌های باز؛ روند پنج روز")
                                s.compliance.sortedByDescending { it.score }.forEachIndexed { i, k ->
                                    if (i > 0) HorizontalDivider(color = c.lineDivider)
                                    Column(Modifier.padding(vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                            CompanyMark(k.company, height = 14.dp, mono = true, ink = c.textSecondary, modifier = Modifier.width(32.dp))
                                            ScoreBar(k.score, Modifier.weight(1f))
                                            Spark(k.trend, min = 40.0, max = 100.0)
                                        }
                                        FlowRow(Modifier.padding(start = 42.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                            for ((a, v) in k.byArea) Text("${AREA_FA[a] ?: a} ${v.toInt()}", style = Divan.type.micro, color = if (v < 65) c.negative else c.textMuted)
                                            if (k.findingsOpen.critical > 0) Text("${k.findingsOpen.critical} یافته‌ی بحرانی", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.negative)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
            Tab.FINDINGS -> {
                val all = findings.data
                item {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        FilterChip("باز", !showClosed, { showClosed = false }, count = all?.count { it.live() })
                        FilterChip("بسته و تأییدشده", showClosed, { showClosed = true }, count = all?.count { !it.live() })
                    }
                }
                val list = all.orEmpty().filter { it.live() != showClosed }.sortedBy { SEVERITY_ORDER.indexOf(it.severity) }
                when {
                    all == null && findings.error != null -> item { ErrorBlock(findings.error, { findings.refresh() }) }
                    all == null -> items(3) { Skeleton(Modifier.fillMaxWidth().height(72.dp), radius = 14.dp) }
                    list.isEmpty() -> item { Empty("یافته‌ای نیست", icon = DivanIcon.OVERSEER) }
                    else -> items(list.size, key = { list[it].ref }) { i -> Box(itemMotion()) { FindingRow(list[i]) { finding = list[i] } }}
                }
            }
            Tab.PROTOCOLS -> {
                val all = protocols.data
                item {
                    Text("وظایف نوشته‌شده‌ی ناظر؛ نسخه‌ی تازه فقط با مُهر تو", style = Divan.type.caption, color = c.textMuted)
                }
                item {
                    com.coinepro.hq.designsystem.ScrollRow {
                        FilterChip("همه", area == null, { area = null }, count = all?.size)
                        for (a in all.orEmpty().map { it.area }.distinct()) FilterChip(AREA_FA[a] ?: a, area == a, { area = a }, count = all.orEmpty().count { it.area == a })
                    }
                }
                val list = all.orEmpty().filter { area == null || it.area == area }
                if (all == null) item { Skeleton(Modifier.fillMaxWidth().height(240.dp), radius = 16.dp) }
                else item {
                    HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(horizontal = 12.dp, vertical = 4.dp)) {
                        list.forEachIndexed { i, p ->
                            if (i > 0) HorizontalDivider(color = c.lineDivider)
                            Row(Modifier.fillMaxWidth().clickable(role = Role.Button) { protocol = p }.padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                Fig(p.ref, Modifier.width(52.dp), style = Divan.type.figureSmall, color = c.textMuted)
                                Column(Modifier.weight(1f)) {
                                    Text(p.titleFa, style = Divan.type.small, color = c.textPrimary, maxLines = 2)
                                    Text("${METHOD_FA[p.method] ?: p.method} · ${rruleFa(p.schedule)}", style = Divan.type.micro, color = c.textMuted)
                                }
                                if (p.status == "paused") Pill("متوقف") else ResultPill(p.lastRun?.result)
                            }
                        }
                    }
                }
            }
            Tab.CHALLENGES -> {
                val list = challenges.data
                when {
                    list == null && challenges.error != null -> item { ErrorBlock(challenges.error, { challenges.refresh() }) }
                    list == null -> items(2) { Skeleton(Modifier.fillMaxWidth().height(140.dp), radius = 16.dp) }
                    list.isEmpty() -> item { Empty("چالشی نیست", icon = DivanIcon.STAR) }
                    else -> items(list.size, key = { list[it].ref }) { i -> Box(itemMotion()) {
                        val k = list[i]
                        HqCard(Modifier.fillMaxWidth()) {
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                CompanyMark(k.company, height = 14.dp, mono = true, ink = c.textSecondary)
                                RichText(k.titleFa, Modifier.weight(1f), style = Divan.type.bodyStrong, color = c.textPrimary, maxLines = 2)
                                LabelPill(CHALLENGE_STATUS[k.status], k.status)
                            }
                            Text(k.briefMd, style = Divan.type.small, color = c.textSecondary, modifier = Modifier.padding(top = 6.dp))
                            FlowRow(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(4.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                for (cr in k.criteria) Tag("${cr.nameFa} ${cr.weight.toInt()}٪")
                            }
                            Row(Modifier.padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Fig(k.ref, style = Divan.type.figureSmall, color = c.textMuted)
                                Text("داور: ${actorFa(k.judge)}", style = Divan.type.micro, color = c.textMuted)
                                Text(if (k.status == "scored") "" else until(k.dueAt), style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f))
                                k.score?.let { ScoreBar(it, Modifier.width(110.dp)) }
                            }
                        }
                    }}
                }
            }
            Tab.ORDERS -> {
                item {
                    HqCard(Modifier.fillMaxWidth()) {
                        SectionTitle("دستور تازه", note = "بگو یا بنویس؛ ناظر آن را دقیق میکند و تو مُهر میکنی")
                        Row(Modifier.padding(vertical = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            FilterChip("برای ناظر", !forAll, { forAll = false })
                            FilterChip("برای همه‌ی ایجنت‌ها", forAll, { forAll = true })
                        }
                        Composer("مثلاً: هر انتشار بدون تست بار پنج‌سناریویی را نگه دار", onSend = { body, files ->
                            val v = spoken(body, files)
                            try {
                                env.api.newStandingOrder(v.text, v.source, v.fileId, if (forAll) "all" else "overseer")
                                env.cache.invalidate("oversight")
                                toasts.ok("ثبت شد؛ برای مُهر در فهرست آمد.")
                            } catch (e: com.coinepro.hq.core.net.ApiException) {
                                toasts.error(e.messageFa)
                                throw e
                            }
                        }, purpose = "note", allowFiles = false, draftKey = "standing-order")
                    }
                }
                item { SectionTitle("دستورهای دائمی تو", note = "با مُهر تو قطعی میشوند؛ ناظر طبق آن‌ها داوری میکند") }
                val list = orders.data
                when {
                    list == null -> item { Skeleton(Modifier.fillMaxWidth().height(120.dp), radius = 14.dp) }
                    list.isEmpty() -> item { Empty("هنوز دستور دائمی نداده‌ای", icon = DivanIcon.SEAL) }
                    else -> items(list.size, key = { list[it].ref }) { i -> Box(itemMotion()) {
                        val o = list[i]
                        val proposed = o.status == "proposed"
                        Column(
                            Modifier.fillMaxWidth().alpha(if (o.status == "retired") 0.6f else 1f).clip(RoundedCornerShape(14.dp)).background(if (proposed) c.softGold else c.card).padding(14.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Fig(o.ref, style = Divan.type.figureSmall, color = c.textMuted)
                                if (o.source == "voice") DIcon(DivanIcon.MIC, size = 12.dp, tint = c.textMuted)
                                Text(if (o.appliesTo == "all") "برای همه" else "برای ناظر", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f))
                                LabelPill(ORDER_STATUS[o.status], o.status)
                            }
                            RichText(o.textMd, style = Divan.type.body, color = c.textPrimary)
                            if (proposed) HqButton("مُهر کن", {
                                action.run {
                                    env.api.sealStandingOrder(o.ref) { a, t -> env.auth.stepUp(act, a, t) }
                                    env.cache.invalidate("oversight")
                                    toasts.ok("مُهر شد؛ از همین حالا اجرا میشود.")
                                }
                            }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.SEAL, loading = action.busy)
                            else if (o.status == "sealed") HqButton("بازنشسته کن", {
                                action.run { env.api.retireStandingOrder(o.ref); env.cache.invalidate("oversight") }
                            }, variant = BtnVariant.GHOST, size = BtnSize.SM)
                        }
                    }}
                }
            }
        }
    }

    finding?.let { FindingSheet(it) { finding = null } }
    protocol?.let { p ->
        HqSheet({ protocol = null }, p.titleFa, ref = p.ref) {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Pill(AREA_FA[p.area] ?: p.area)
                Pill(METHOD_FA[p.method] ?: p.method)
                SeverityPill(p.severity)
                Pill(rruleFa(p.schedule))
            }
            Text("چه چیزی چک میشود", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            Text(p.checkMd, style = Divan.type.figureSmall.copy(textDirection = TextDirection.Ltr), color = c.textPrimary, modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(12.dp))
            Text("شاهد", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            Text(p.evidenceMd, style = Divan.type.figureSmall.copy(textDirection = TextDirection.Ltr), color = c.textSecondary)
            if (p.status == "paused") Text(
                "متوقف است، چون قابلیتی که میسنجد هنوز ساخته نشده. با ساخته شدنش روشن میشود و تا آن موقع هیچ یافته‌ای نمیسازد.",
                style = Divan.type.caption, color = c.textSecondary,
                modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(12.dp),
            )
            Text(
                "پاسخ‌گو: ${p.answerable} · نسخه‌ی ${p.version}" + (p.lastRun?.let { " · آخرین اجرا ${ago(it.at)}، ${it.findings} یافته" } ?: ""),
                style = Divan.type.caption, color = c.textMuted,
            )
        }
    }
}

@Composable
private fun Tile(label: String, value: String, sub: String, modifier: Modifier, subColor: androidx.compose.ui.graphics.Color? = null, onClick: () -> Unit) {
    val c = Divan.colors
    Column(modifier.clip(RoundedCornerShape(14.dp)).background(c.card).clickable(role = Role.Button, onClick = onClick).padding(14.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(label, style = Divan.type.caption, color = c.textMuted)
        Text(value, style = Divan.type.h1)
        Text(sub, style = Divan.type.micro, color = subColor ?: c.textSecondary, maxLines = 2)
    }
}

@Composable
private fun ResultPill(result: String?) = when (result) {
    "pass" -> Pill("قبول", Tone.POS, dot = true)
    "fail" -> Pill("رد", Tone.NEG, dot = true)
    "partial" -> Pill("نیمه", Tone.WARN, dot = true)
    "deferred" -> Pill("به فردا")
    else -> Pill("هنوز نه")
}

@Composable
private fun FindingRow(f: Finding, onClick: () -> Unit) {
    val c = Divan.colors
    val critical = f.severity == "critical" && f.live()
    val shape = RoundedCornerShape(14.dp)
    Row(
        Modifier.fillMaxWidth().clip(shape).background(c.card).then(if (critical) Modifier.border(1.dp, c.negative.copy(alpha = 0.45f), shape) else Modifier)
            .clickable(role = Role.Button, onClick = onClick).padding(14.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        SeverityPill(f.severity)
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            RichText(f.titleFa, style = Divan.type.bodyStrong, color = c.textPrimary, maxLines = 3)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(2.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                Fig(f.ref, style = Divan.type.figureSmall, color = c.textMuted)
                CompanyMark(f.company, height = 11.dp, mono = true, ink = c.textMuted)
                Text(actorFa(f.answerable), style = Divan.type.micro, color = c.textMuted)
                Text(FINDING_STATUS[f.status]?.fa ?: f.status, style = Divan.type.micro, color = c.textMuted)
                if (f.live()) Text(until(f.dueAt), style = Divan.type.micro, color = c.textMuted)
            }
        }
    }
}

/** One finding: the evidence, the trail, and the owner's verdict on a fix (verify, reopen or close). */
@Composable
internal fun FindingSheet(f: Finding, onClose: () -> Unit) {
    val env = LocalEnv.current
    val c = Divan.colors
    val action = rememberAction()
    var note by rememberSaveable(f.ref) { mutableStateOf("") }
    fun set(status: String) = action.run {
        env.api.findingStatus(f.ref, status, note.trim())
        env.cache.invalidate("oversight")
        onClose()
    }
    HqSheet(onClose, f.titleFa, ref = f.ref) {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            SeverityPill(f.severity)
            LabelPill(FINDING_STATUS[f.status], f.status)
            CompanyMark(f.company, height = 12.dp, mono = true, ink = c.textSecondary)
            Text(actorFa(f.answerable), style = Divan.type.caption, color = c.textSecondary)
            f.protocol?.let { Fig(it, style = Divan.type.figureSmall, color = c.textMuted) }
            if (f.live()) Text("موعد: ${until(f.dueAt)}", style = Divan.type.caption, color = c.textMuted)
        }
        Md(f.bodyMd, style = Divan.type.body, color = c.textPrimary)
        if (f.evidence.isNotEmpty()) {
            Text("شاهد", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            for (e in f.evidence) {
                Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(horizontal = 12.dp, vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Fig(e.kind, style = Divan.type.figureSmall, color = c.textMuted)
                    Fig(e.ref, style = Divan.type.figureSmall, color = c.goldInk)
                    e.note?.let { RichText(it, Modifier.weight(1f), style = Divan.type.caption) }
                }
            }
        }
        if (f.history.isNotEmpty()) {
            Text("تاریخچه", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            for (h in f.history) Text(com.coinepro.hq.designsystem.timesFig("${jDateTime(h.at)}، ${actorFa(h.by)}، ${FINDING_STATUS[h.status]?.fa ?: h.status}${if (h.note.isNotBlank()) " — ${h.note}" else ""}"), style = Divan.type.caption, color = c.textSecondary)
        }
        if (f.live()) {
            HqTextField(note, { note = it }, "یادداشت تو (اختیاری)", Modifier.fillMaxWidth(), singleLine = false, minLines = 2, maxLength = 2000)
            if (f.status == "fixed" || f.status == "disputed") {
                HqButton("رفع را تأیید کن", { set("verified") }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEAL, loading = action.busy)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    HqButton("دوباره باز کن", { set("open") }, Modifier.weight(1f))
                    HqButton("ببند", { set("closed") }, Modifier.weight(1f), variant = BtnVariant.GHOST)
                }
            } else HqButton("ببند (بی‌اثر یا تکراری)", { set("closed") }, Modifier.fillMaxWidth(), variant = BtnVariant.GHOST, loading = action.busy)
        }
    }
}
