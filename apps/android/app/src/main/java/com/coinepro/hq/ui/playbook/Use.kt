package com.coinepro.hq.ui.playbook

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
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
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.UseDraft
import com.coinepro.hq.core.data.WEEK_DAYS
import com.coinepro.hq.core.data.accountsNamed
import com.coinepro.hq.core.data.applyTargets
import com.coinepro.hq.core.data.budgetFa
import com.coinepro.hq.core.data.clockOf
import com.coinepro.hq.core.data.dollarsOf
import com.coinepro.hq.core.data.faNum
import com.coinepro.hq.core.data.flowModeFa
import com.coinepro.hq.core.data.publishes
import com.coinepro.hq.core.data.useMissingFa
import com.coinepro.hq.core.data.versionFa
import com.coinepro.hq.core.data.versionsOf
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.ReplyPolicy
import com.coinepro.hq.core.net.SiteLinks
import com.coinepro.hq.core.net.SiteUrl
import com.coinepro.hq.core.net.UseBrand
import com.coinepro.hq.core.net.UseBudget
import com.coinepro.hq.core.net.UsePreview
import com.coinepro.hq.core.net.UseTime
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.DecisionBar
import com.coinepro.hq.designsystem.DecisionPage
import com.coinepro.hq.designsystem.DecisionPlace
import com.coinepro.hq.designsystem.DecisionState
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Expand
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.ScrollRow
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.SpringSheet
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.automation.LinksFields
import com.coinepro.hq.ui.automation.ReplyEditor
import com.coinepro.hq.ui.automation.rememberSiteLinks
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.served
import kotlinx.coroutines.launch
import java.util.UUID

// Contract §59.4 ⟨1.37⟩: «در شرکت دیگر به کار ببر», one form. The company and its accounts; the narrator (a sample to hear before
// choosing); the brand (the company's own unless he changes it); the company's links with the UTM of each path; the replies; the time
// (a fixed hour or the account's best one, which days, a story too); the budget of a run and of a day; «خودکار کامل» or «قبل از انتشار
// بپرس». Then the preview (what will happen each day, what it will cost, what the hub settles by itself) and «شروع», which makes the
// membership, its seats and its flow automation.

/** The form's state: one object whose fields are snapshot state, so a change recomposes only what reads it. */
@Stable
private class UseForm(version: Int) {
    var version by mutableStateOf(version)
    var company by mutableStateOf<String?>(null)
    var account by mutableStateOf("")
    var accountsNamed by mutableStateOf<List<String>>(emptyList())
    var voice by mutableStateOf<String?>(null)
    var style by mutableStateOf("")
    var ownBrand by mutableStateOf(true)
    var colors by mutableStateOf("")
    var font by mutableStateOf("")
    var logo by mutableStateOf<String?>(null)
    var links by mutableStateOf<SiteLinks?>(null)
    var replies by mutableStateOf(ReplyPolicy())
    var time by mutableStateOf(UseTime())
    var perRun by mutableStateOf("5")
    var perDay by mutableStateOf("8")
    var auto by mutableStateOf(true)

    fun draft(): UseDraft = UseDraft(
        version = version, company = company,
        accounts = listOfNotNull(account.trim().removePrefix("@").ifBlank { null }),
        voice = voice, styleFa = style,
        brand = if (ownBrand) null else UseBrand(colors.split(',', '،', ' ').map { it.trim() }.filter { Regex("^#?[0-9A-Fa-f]{6}$").matches(it) }.map { if (it.startsWith("#")) it else "#$it" }, font.trim().ifBlank { null }, logo),
        links = links?.takeIf { it.site.url.startsWith("https://") },
        replies = replies, time = time,
        budget = UseBudget(dollarsOf(perRun) ?: 0.0, dollarsOf(perDay) ?: 0.0),
        auto = auto,
    )
}

@Composable
fun UseScreen(ref: String) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val q = rememberPlaybook(ref)
    val pb = q.data
    val companies = rememberCompanies()
    val form = remember(pb?.ref) { UseForm(pb?.version ?: 1) }
    LaunchedEffect(pb?.version) { if (pb != null) form.version = pb.version }
    val links = rememberSiteLinks(form.company)
    LaunchedEffect(form.company, links.data) { form.links = links.data ?: form.company?.let { SiteLinks(company = it, site = SiteUrl()) } }
    var preview by remember { mutableStateOf<UsePreview?>(null) }
    val look = rememberAction()
    val start = rememberAction()
    val key = remember(form.company, form.version) { UUID.randomUUID().toString() }
    val draft = form.draft()
    val library = served(HubFeature.LIBRARY) && pb?.versioned != false
    val siteLinksOn = served(HubFeature.SITE_LINKS)
    val missing = if (pb == null) emptyList() else useMissingFa(draft, publishes(pb))

    DecisionPage(bar = if (pb != null && library) ({
        DecisionBar(
            "پیش‌نمایش", {
                look.run(onError = { e -> namedAccounts(e)?.let { form.accountsNamed = it }; toasts.error(e.messageFa) }) {
                    preview = env.api.usePreview(pb.ref, draft.body())
                }
            },
            context = missing.firstOrNull() ?: "اول ببین هر روز چه میشود؛ بعد «شروع»",
            enabled = missing.isEmpty(), state = if (look.busy) DecisionState.WORKING else DecisionState.IDLE, icon = DivanIcon.SCOPE, place = DecisionPlace.PAGE,
        )
    }) else null) {
        Page(onRefresh = { q.refresh() }, refreshing = q.state.refreshing) {
            item(key = "head") { PageHeader("در شرکت دیگر به کار ببر", eyebrow = pb?.titleFa?.ifBlank { null } ?: "کارگروه") }
            when {
                pb == null && q.error != null -> item(key = "err") { ErrorBlock(q.error, { q.refresh() }) }
                pb == null -> item(key = "sk") { Skeleton(Modifier.fillMaxWidth().height(420.dp), radius = 16.dp) }
                !library -> item(key = "none") { Empty("این فرم با به‌روزرسانی بعدی هاب می‌آید", icon = DivanIcon.DEPARTMENT, body = "تا آن وقت «تطبیق در جلسه‌ی تازه» همین کار را میکند.") }
                else -> {
                    val sealedVersions = versionsOf(pb).filter { it.state == "sealed" }
                    if (sealedVersions.size > 1) item(key = "version") {
                        Block("نسخه") { ScrollRow { for (v in sealedVersions) FilterChip(versionFa(v.version), form.version == v.version, { form.version = v.version }) } }
                    }
                    item(key = "company") {
                        Block("شرکت و حساب") {
                            val targets = applyTargets(pb, companies)
                            if (targets.isEmpty()) Text("همه‌ی شرکت‌ها همین حالا این کارگروه را دارند.", style = Divan.type.small, color = c.textSecondary)
                            else FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                for (co in targets) FilterChip(co.nameFa ?: co.code, form.company == co.code, { form.company = co.code; form.account = ""; form.accountsNamed = emptyList(); form.voice = null })
                            }
                            if (publishes(pb)) {
                                HqTextField(form.account, { form.account = it }, "@حساب اینستاگرام (خالی: حساب ثبت‌شده‌ی شرکت)", Modifier.fillMaxWidth(), maxLength = 40, figure = true)
                                if (form.accountsNamed.isNotEmpty()) ScrollRow { for (a in form.accountsNamed) FilterChip("@$a", form.account.removePrefix("@") == a, { form.account = a }) }
                            }
                        }
                    }
                    form.company?.let { co ->
                        item(key = "narrator") { NarratorBlock(co, form) }
                        item(key = "brand") { BrandBlock(co, form) }
                        item(key = "links") {
                            Block("لینک‌های شرکت", note = "n8n از این میداند هر جواب چه لینکی بفرستد") {
                                val v = form.links
                                if (!siteLinksOn) Text("هاب لینک سایت شرکت را خودش میگذارد.", style = Divan.type.small, color = c.textSecondary)
                                else if (v == null) Skeleton(Modifier.fillMaxWidth().height(80.dp), radius = 10.dp)
                                else LinksFields(v, { form.links = it }, campaign = (pb.titleFa.take(12).ifBlank { "flow" }))
                            }
                        }
                    }
                    item(key = "replies") {
                        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            SectionTitle("جواب‌ها", note = "کامنت، استوری و دایرکت")
                            ReplyEditor(form.replies, { form.replies = it }, form.links?.sections.orEmpty())
                        }
                    }
                    item(key = "time") { TimeBlock(form) }
                    item(key = "budget") {
                        Block("بودجه", note = "به سقف که برسد میایستد و میگوید") {
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Column(Modifier.weight(1f)) {
                                    Text("هر اجرا (دلار)", style = Divan.type.micro, color = c.textMuted)
                                    HqTextField(form.perRun, { form.perRun = it }, "5", Modifier.fillMaxWidth(), maxLength = 8, figure = true)
                                }
                                Column(Modifier.weight(1f)) {
                                    Text("هر روز (دلار)", style = Divan.type.micro, color = c.textMuted)
                                    HqTextField(form.perDay, { form.perDay = it }, "8", Modifier.fillMaxWidth(), maxLength = 8, figure = true)
                                }
                            }
                        }
                    }
                    item(key = "mode") {
                        Block("حالت") {
                            ScrollRow { FilterChip(flowModeFa("auto"), form.auto, { form.auto = true }); FilterChip(flowModeFa("ask"), !form.auto, { form.auto = false }) }
                            Text(
                                if (form.auto) "هر روز خودش میسازد و سر ساعت منتشر میکند؛ دکمه‌ای لازم نیست. کلید روشن و خاموشش در «اتوماسیون‌ها» با توست."
                                else "هر روز میسازد و ویدیو در «نوبت تو» منتظر یک ضربه‌ی تو میماند.",
                                style = Divan.type.micro, color = c.textMuted,
                            )
                        }
                    }
                }
            }
        }
    }
    val p = preview
    if (pb != null && p != null) SpringSheet({ preview = null }, "پیش‌نمایش", sub = form.company?.let { co -> companies.firstOrNull { it.code == co }?.nameFa } ?: "", bar = {
        DecisionBar(
            "شروع", {
                start.run(onError = { e -> namedAccounts(e)?.let { form.accountsNamed = it }; toasts.error(e.messageFa) }) {
                    val out = env.api.usePlaybook(pb.ref, draft.body(), key)
                    env.cache.invalidate(*PLAYBOOK_TAGS, "automations")
                    preview = null
                    toasts.ok("شروع شد؛ از نوبت بعد خودش کار میکند.")
                    out.automation?.ref?.let { nav.go("automation/$it") } ?: nav.go("playbook/${pb.ref}")
                }
            },
            context = budgetFa(draft.budget), state = if (start.busy) DecisionState.WORKING else DecisionState.IDLE, icon = DivanIcon.RESUME,
        )
    }) {
        Column(Modifier.testTag("use-preview"), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("هر روز", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
            p.linesFa.forEachIndexed { i, l -> Text(plain("${faNum(i + 1)}. $l"), style = Divan.type.small, color = c.textPrimary) }
            Text(
                plain(listOfNotNull(p.firstAt?.let { "اولین اجرا: ${jDateTime(it)}" }, p.costEstimateUsd?.let { "هزینه‌ی هر اجرا حدود ${usd(it)}" }).joinToString(" · ")),
                style = Divan.type.caption, color = c.textSecondary,
            )
            if (p.warnings.isNotEmpty()) {
                Text("پیش از شروع", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted, modifier = Modifier.padding(top = 6.dp))
                for (w in p.warnings) Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.Top) {
                    DIcon(if (w.byHub) DivanIcon.SETTINGS else DivanIcon.INFO, size = 14.dp, tint = c.silverInk)
                    Text(plain(w.textFa + if (w.byHub) " (هاب خودش انجامش میدهد)" else ""), style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.weight(1f))
                }
            }
        }
    }
}

/** A refusal that names the company's accounts (it has several and none was named): they become chips. */
private fun namedAccounts(e: ApiException): List<String>? =
    if (e.status == 422) (accountsNamed(e.fields["accounts"]) + accountsNamed(e.fields["account"])).distinct().ifEmpty { null } else null

@Composable
private fun Block(title: String, note: String? = null, content: @Composable () -> Unit) {
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle(title, note = note)
        Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) { content() }
    }
}

/** The narrator (§48): the company's own by default; another voice and its style, with a sample of each to hear first. */
@Composable
private fun NarratorBlock(company: String, form: UseForm) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val n = rememberNarrator(company).data
    val scope = rememberCoroutineScope()
    var sample by remember(company) { mutableStateOf<Pair<String, String>?>(null) }
    var loading by remember { mutableStateOf(false) }
    Block("گوینده", note = n?.takeIf { it.set }?.let { "الان: ${it.voice}" }) {
        if (n == null) Text("گوینده‌های شرکت با به‌روزرسانی هاب می‌آیند؛ تا آن وقت همان گوینده‌ی شرکت.", style = Divan.type.small, color = c.textSecondary)
        else {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                FilterChip(if (n.set) "همان ${n.voice}" else "گوینده‌ی شرکت", form.voice == null, { form.voice = null })
                for (v in n.voices.take(16)) FilterChip(v.name, form.voice == v.name, { form.voice = v.name })
            }
            n.voices.firstOrNull { it.name == form.voice }?.traitFa?.takeIf { it.isNotBlank() }?.let { Text(plain(it), style = Divan.type.micro, color = c.textMuted) }
            if (form.voice != null) HqTextField(form.style, { form.style = it }, "حالت گفتن (خالی: بی حالت)", Modifier.fillMaxWidth(), maxLength = 200)
            val voice = form.voice ?: n.voice.ifBlank { null }
            if (voice != null) HqButton("نمونه‌اش را بشنو", {
                if (loading) return@HqButton
                loading = true
                scope.launch {
                    try { sample = voice to env.api.narratorSample(voice, form.style).file.id } catch (e: ApiException) { toasts.error(e.messageFa) } finally { loading = false }
                }
            }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.MIC, loading = loading)
            sample?.let { (v, id) -> if (id.isNotBlank()) com.coinepro.hq.ui.v18.AudioPlayer(id, "نمونه‌ی $v", compact = true) }
        }
    }
}

/** The brand: the company's own (its mark shows), or colors, a font and a logo of this flow's own. */
@Composable
private fun BrandBlock(company: String, form: UseForm) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val context = LocalContext.current
    val c = Divan.colors
    val scope = rememberCoroutineScope()
    var uploading by remember { mutableStateOf(false) }
    val pick = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        uploading = true
        scope.launch {
            try {
                val bytes = context.contentResolver.openInputStream(uri)?.use { it.readBytes() } ?: return@launch
                val mime = context.contentResolver.getType(uri) ?: "image/png"
                form.logo = env.api.upload("logo.${mime.substringAfter('/')}", mime, bytes.size.toLong(), { bytes.inputStream() }).id
                toasts.ok("لوگو آماده شد.")
            } catch (e: ApiException) { toasts.error(e.messageFa) } catch (_: Exception) { toasts.error("لوگو بالا نرفت؛ دوباره امتحان کن.") } finally { uploading = false }
        }
    }
    Block("برند") {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Box(Modifier.size(34.dp).clip(CircleShape).background(c.tile), contentAlignment = Alignment.Center) { CompanyMark(company, height = 16.dp) }
            Column(Modifier.weight(1f)) {
                Text("برند خود شرکت", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                Text("رنگ، فونت و لوگویی که برای شرکت ثبت شده", style = Divan.type.micro, color = c.textMuted)
            }
            HqSwitch(form.ownBrand, { form.ownBrand = it }, "برند خود شرکت")
        }
        Expand(!form.ownBrand) {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                HqTextField(form.colors, { form.colors = it }, "رنگ‌ها، مثل #0B1F3A, #C9A227", Modifier.fillMaxWidth(), maxLength = 120, figure = true)
                val swatches = form.colors.split(',', '،', ' ').map { it.trim().removePrefix("#") }.filter { Regex("^[0-9A-Fa-f]{6}$").matches(it) }
                if (swatches.isNotEmpty()) Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    for (h in swatches) Box(Modifier.size(22.dp).clip(RoundedCornerShape(6.dp)).background(androidx.compose.ui.graphics.Color(("FF$h").toLong(16))))
                }
                HqTextField(form.font, { form.font = it }, "فونت، مثل Vazirmatn", Modifier.fillMaxWidth(), maxLength = 60, figure = true)
                HqButton(if (form.logo == null) "لوگو" else "لوگوی تازه", { pick.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) }, variant = BtnVariant.SECONDARY, size = BtnSize.SM, icon = DivanIcon.IMAGE, loading = uploading)
            }
        }
    }
}

/** The time: the best hour or a fixed one, which days, and the story beside the reel. */
@Composable
private fun TimeBlock(form: UseForm) {
    val c = Divan.colors
    val t = form.time
    Block("زمان") {
        ScrollRow {
            FilterChip("بهترین ساعت", t.mode == "best", { form.time = t.copy(mode = "best") })
            FilterChip("ساعت ثابت", t.mode == "fixed", { form.time = t.copy(mode = "fixed") })
        }
        if (t.mode == "fixed") HqTextField(t.at.orEmpty(), { form.time = t.copy(at = it) }, "مثل 18:30", Modifier.fillMaxWidth(), maxLength = 5, figure = true)
        else Text("هاب از روی لایک و کامنت پست‌های همین حساب بهترین ساعت را پیدا میکند؛ داده که کم باشد، همان لحظه‌ی آماده شدن.", style = Divan.type.micro, color = c.textMuted)
        if (t.mode == "fixed" && t.at != null && clockOf(t.at) == null) Text("ساعت را مثل 18:30 بنویس.", style = Divan.type.micro, color = c.negative)
        val days = t.days ?: WEEK_DAYS.map { it.first }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            for ((k, fa) in WEEK_DAYS) FilterChip(fa, k in days, {
                val next = if (k in days) days - k else WEEK_DAYS.map { it.first }.filter { it in days || it == k }
                form.time = t.copy(days = next.takeIf { it.size < 7 })
            })
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("استوری هم", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, modifier = Modifier.weight(1f))
            HqSwitch(t.story, { form.time = t.copy(story = it) }, "استوری هم")
        }
        Text("جواب استوری همان روز با ریلز یکی است.", style = Divan.type.micro, color = c.textMuted)
    }
}
