package com.coinepro.hq.ui.founding

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import coil3.compose.AsyncImage
import com.coinepro.hq.core.data.FoundingBrandStore
import com.coinepro.hq.core.data.FoundingBrief
import com.coinepro.hq.core.data.FoundingDraft
import com.coinepro.hq.core.data.FoundingPath
import com.coinepro.hq.core.data.FoundingRules
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.BrandOptions
import com.coinepro.hq.core.net.CompanyIn
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Radius
import com.coinepro.hq.designsystem.Space
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.media.rememberAttachments
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.workshop.SpokenField
import kotlinx.coroutines.launch

private val STEP_FA = listOf("کیست", "شروع", "نشان", "تأیید")

/** The three ways a company starts, each with what happens next in one line. */
private data class Way(val path: FoundingPath, val title: String, val icon: DivanIcon, val what: String, val next: String)

private val WAYS = listOf(
    Way(
        FoundingPath.IDEA, "از یک ایده", DivanIcon.LEARNING, "بگو چه میخواهی بسازی؛ مشتری، کار اصلی و درآمد.",
        "مدیر AI Ops پیشنهاد کامل مینویسد (ساختار، تیم، بودجه، نقشه‌ی ۹۰ روزه) و برای مُهر به کارتابلت میاید.",
    ),
    Way(
        FoundingPath.REPO, "از یک ریپوی GitHub", DivanIcon.CODE, "کدی که داری؛ آدرس ریپو را بده.",
        "اول ممیزی فقط‌خواندنی کد (معماری، کیفیت، امنیت، تست، بدهی فنی)، بعد پیشنهاد کامل؛ هر دو به کارتابلت میاید.",
    ),
    Way(
        FoundingPath.REGISTER, "فقط ثبت کن، بعداً کامل میکنم", DivanIcon.COMPANIES, "شرکت همین حالا با نام و کدش ثبت میشود.",
        "با دپارتمان‌های الگوی استاندارد و بی‌کارمند و بی‌سرور ساخته میشود؛ استخدام، نشان و سرور را بعداً از صفحه‌ی شرکت کامل میکنی.",
    ),
)

private val DraftSaver = androidx.compose.runtime.saveable.listSaver<FoundingDraft, String>(
    save = { listOf(it.nameFa, it.code, it.tagline, it.path?.name.orEmpty(), it.idea, it.repo, it.nameEn, it.colorIndex?.toString().orEmpty(), it.logoFileId.orEmpty()) },
    restore = { l ->
        FoundingDraft(l[0], l[1], l[2], l[3].takeIf { it.isNotEmpty() }?.let(FoundingPath::valueOf), l[4], l[5], l[6], l[7].toIntOrNull(), l[8].ifEmpty { null })
    },
)

/**
 * «تأسیس شرکت» — the one way to make a company, in four short steps: who it is (Persian name, a 2–4 letter code, one line), how it
 * starts (an idea, a GitHub repository, or only registered for now), its brand (a logo seen in its circle and a colour, optional),
 * and a review that says exactly what happens next. Nothing reaches the hub before the last step.
 */
@Composable
fun FoundingWizard(step0: Int = 1, draft0: FoundingDraft = FoundingDraft(), tried0: Boolean = false) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    var step by rememberSaveable { mutableStateOf(step0) }
    var d by rememberSaveable(stateSaver = DraftSaver) { mutableStateOf(draft0) }
    // Errors show once the owner tried to go on (or typed in a field), never on an empty form at first sight.
    var tried by rememberSaveable { mutableStateOf(tried0) }
    var busy by remember { mutableStateOf(false) }
    val scope = androidx.compose.runtime.rememberCoroutineScope()
    val companies = rememberCompanies()
    val foundings = rememberQuery("founding:list", "founding", maxAgeMs = 15_000) { foundings() }
    val taken = remember(companies, foundings.data) {
        companies.map { it.code }.toSet() + foundings.data?.items.orEmpty().filter { it.state != "cancelled" }
            .mapNotNull { it.code ?: FoundingBrief.parse(it.source.briefMd).code }
    }
    val errors = FoundingRules.errors(step, d, taken)

    fun submit() {
        if (busy || FoundingRules.firstIncomplete(d, taken) != null) { tried = true; return }
        busy = true
        scope.launch {
            try {
                if (d.path == FoundingPath.REGISTER) {
                    val co = env.api.createCompany(CompanyIn(d.code, d.nameFa.trim(), d.nameEn.trim().ifEmpty { d.code }, colorIndex = d.colorIndex)) { a, t -> env.auth.stepUp(act, a, t) }
                    var traced = false
                    d.logoFileId?.let { id ->
                        // The mark is traced from the logo and waits for the owner's seal on the company's page (§18.14).
                        traced = runCatching { env.api.uploadBrand(co.code, id, "mark", BrandOptions(null, 3)) }.isSuccess
                    }
                    env.cache.invalidate("companies", "brands", "brand", "control")
                    toasts.ok(if (traced) "${co.nameFa ?: co.code} ثبت شد؛ نشانش در صفحه‌ی شرکت منتظر مُهر توست." else "${co.nameFa ?: co.code} ثبت شد.")
                    nav.back()
                    nav.go("companies/${co.code}")
                } else {
                    val kind = if (d.path == FoundingPath.REPO) "repo" else "idea"
                    val f = env.api.startFounding(kind, if (kind == "repo") FoundingRules.repo(d.repo) else null, FoundingRules.brief(d))
                    if (d.logoFileId != null || d.colorIndex != null) env.foundingBrand.put(f.ref, FoundingBrandStore.Pending(d.logoFileId, d.colorIndex))
                    env.cache.invalidate("founding")
                    toasts.ok(if (kind == "repo") "تأسیس شروع شد؛ ممیزی ریپو در جریان است." else "تأسیس شروع شد؛ پیشنهاد در حال نوشتن است.")
                    nav.back()
                    nav.go("founding/${f.ref}")
                }
            } catch (e: ApiException) {
                toasts.error(e.messageFa)
            } finally {
                busy = false
            }
        }
    }

    Page {
        item { PageHeader("تأسیس شرکت", eyebrow = "چهار قدم کوتاه؛ تا قدم آخر چیزی ساخته نمیشود") }
        item { Steps(step) { if (it < step) step = it } }
        item {
            when (step) {
                1 -> WhoStep(d, { d = it }, if (tried) errors else emptyMap())
                2 -> HowStep(d, { d = it }, if (tried) errors else emptyMap())
                3 -> BrandStep(d, { d = it }, companies.filter { it.code != d.code }.mapNotNull { it.colorIndex }.toSet())
                else -> Review(d) { step = it }
            }
        }
        item {
            Row(Modifier.fillMaxWidth().padding(top = Space.xs), horizontalArrangement = Arrangement.spacedBy(Space.xs)) {
                if (step > 1) HqButton("قبلی", { step--; tried = false }, Modifier.weight(1f), variant = BtnVariant.GHOST, icon = DivanIcon.BACK)
                when {
                    step < FoundingRules.STEPS -> HqButton(
                        if (step == 3 && d.logoFileId == null && d.colorIndex == null) "بعداً؛ بعدی" else "بعدی",
                        { if (errors.isEmpty()) { step++; tried = false } else tried = true },
                        Modifier.weight(1f), variant = BtnVariant.PRIMARY, icon = DivanIcon.NEXT,
                    )
                    d.path == FoundingPath.REGISTER -> HqButton("ثبت با گذرکلید", ::submit, Modifier.weight(1.4f), variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, loading = busy)
                    else -> HqButton("شروع تأسیس", ::submit, Modifier.weight(1.4f), variant = BtnVariant.PRIMARY, icon = DivanIcon.FOUND, loading = busy)
                }
            }
        }
    }
}

/** Four numbered steps; a done one is ticked and goes back when touched. */
@Composable
private fun Steps(at: Int, onBack: (Int) -> Unit) {
    val c = Divan.colors
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
        STEP_FA.forEachIndexed { i, fa ->
            val n = i + 1
            val (bg, fg) = when { n < at -> c.softPositive to c.positive; n == at -> c.softGold to c.goldInk; else -> c.tile to c.textMuted }
            Row(
                Modifier.weight(1f).height(32.dp).clip(CircleShape).background(bg)
                    .then(if (n < at) Modifier.clickable(role = Role.Button, onClickLabel = "برگرد به $fa") { onBack(n) } else Modifier)
                    .padding(horizontal = 8.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp, Alignment.CenterHorizontally),
            ) {
                if (n < at) DIcon(DivanIcon.SEAL, size = 12.dp, tint = fg, active = true) else Text("$n", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = fg)
                Text(fa, style = Divan.type.caption.copy(fontWeight = if (n == at) FontWeight.SemiBold else FontWeight.Normal), color = fg, maxLines = 1)
            }
        }
    }
}

@Composable
private fun FieldError(text: String?) {
    if (text != null) Text(text, style = Divan.type.caption, color = Divan.colors.negative)
}

@Composable
private fun Label(text: String, note: String? = null) {
    val c = Divan.colors
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(text, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        if (note != null) Text(note, style = Divan.type.micro, color = c.textMuted)
    }
}

/** Step 1: the Persian name, the code (2–4 Latin letters, checked against every company and open founding) and one line. */
@Composable
private fun WhoStep(d: FoundingDraft, set: (FoundingDraft) -> Unit, errors: Map<String, String>) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth()) {
        Column(verticalArrangement = Arrangement.spacedBy(Space.sm)) {
            Text("شرکت تازه چیست؟", style = Divan.type.h3)
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Label("نام شرکت")
                HqTextField(d.nameFa, { set(d.copy(nameFa = it)) }, "مثلاً دایرکت هوشمند", Modifier.fillMaxWidth(), maxLength = 60)
                FieldError(errors["name"])
            }
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Label("کد", "۲ تا ۴ حرف لاتین؛ یک بار داده میشود و عوض نمیشود")
                CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                    HqTextField(d.code, { set(d.copy(code = FoundingRules.cleanCode(it))) }, "IG", Modifier.fillMaxWidth(), maxLength = 4, figure = true)
                }
                FieldError(errors["code"])
            }
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Label("در یک خط چه میکند")
                HqTextField(d.tagline, { set(d.copy(tagline = it.replace('\n', ' '))) }, "مثلاً پاسخ خودکار و فروش در دایرکت اینستاگرام", Modifier.fillMaxWidth(), maxLength = 140)
                FieldError(errors["tagline"])
            }
            Text("کد روی کارت‌ها، کارمندها (مثل IG-CEO) و گزارش‌ها میاید.", style = Divan.type.caption, color = c.textMuted)
        }
    }
}

/** Step 2: three clear ways to start, each saying what happens next; the chosen one asks for what it needs. */
@Composable
private fun HowStep(d: FoundingDraft, set: (FoundingDraft) -> Unit, errors: Map<String, String>) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(Space.sm)) {
        Text("از کجا شروع کنیم؟", style = Divan.type.h3)
        for (w in WAYS) {
            val on = d.path == w.path
            Column(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(Radius.card)).background(if (on) c.softGold else c.card)
                    .border(1.dp, if (on) c.lineTahrir else Color.Transparent, RoundedCornerShape(Radius.card))
                    .clickable(role = Role.RadioButton, onClickLabel = w.title) { set(d.copy(path = w.path)) }.padding(Space.md),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Space.sm)) {
                    Box(Modifier.size(40.dp).clip(CircleShape).background(if (on) c.goldFill else c.tile), contentAlignment = Alignment.Center) {
                        DIcon(w.icon, size = 20.dp, tint = if (on) c.onGold else c.textSecondary)
                    }
                    Column(Modifier.weight(1f)) {
                        Text(w.title, style = Divan.type.bodyStrong)
                        Text(w.what, style = Divan.type.caption, color = c.textSecondary)
                    }
                    Box(Modifier.size(20.dp).clip(CircleShape).border(2.dp, if (on) c.goldInk else c.lineStrong, CircleShape), contentAlignment = Alignment.Center) {
                        if (on) Box(Modifier.size(10.dp).clip(CircleShape).background(c.goldInk))
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("بعدش:", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
                    Text(w.next, style = Divan.type.caption, color = c.textMuted, modifier = Modifier.weight(1f))
                }
                if (on) Column(Modifier.padding(top = 6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    when (w.path) {
                        FoundingPath.IDEA -> SpokenField("ایده", d.idea, { set(d.copy(idea = it)) }, "چه میسازد، برای چه کسی، از کجا درآمد دارد، چه محدودیتی هست")
                        FoundingPath.REPO -> CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                            HqTextField(d.repo, { set(d.copy(repo = it.trim())) }, "github.com/owner/name", Modifier.fillMaxWidth(), maxLength = 220, figure = true)
                        }
                        FoundingPath.REGISTER -> {
                            Label("نام لاتین", "اختیاری؛ خالی بماند کد به کار میرود")
                            CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                                HqTextField(d.nameEn, { set(d.copy(nameEn = it)) }, d.code.ifEmpty { "Smart Direct" }, Modifier.fillMaxWidth(), maxLength = 80)
                            }
                        }
                    }
                    FieldError(errors["path"])
                }
            }
        }
        if (d.path == null) FieldError(errors["path"])
    }
}

/** Step 3 (optional): the logo, seen in its circle as the company's mark will be, and a colour from the companies' palette. */
@Composable
private fun BrandStep(d: FoundingDraft, set: (FoundingDraft) -> Unit, usedSlots: Set<Int>) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val ctx = LocalContext.current
    val c = Divan.colors
    val files = rememberAttachments(1)
    val pick = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        if (ctx.contentResolver.getType(uri) !in setOf("image/png", "image/webp", "image/jpeg")) toasts.error("لوگو باید PNG (بهتر با زمینه‌ی شفاف)، WebP یا JPEG باشد.")
        else { files.clear(); files.add(listOf(uri)) }
    }
    val pending = files.items.firstOrNull()
    LaunchedEffect(pending?.state, pending?.ref) { pending?.ref?.id?.let { if (pending.state == "ready") set(d.copy(logoFileId = it)) } }
    HqCard(Modifier.fillMaxWidth()) {
        Column(verticalArrangement = Arrangement.spacedBy(Space.md)) {
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text("نشان و رنگ", style = Divan.type.h3)
                Text("اختیاری؛ میتوانی بعداً از صفحه‌ی شرکت بدهی. تا آن موقع کد جای نشان را میگیرد.", style = Divan.type.caption, color = c.textMuted)
            }
            val shown: Any? = pending?.file?.uri ?: d.logoFileId?.let { env.media.imageModel(it) }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Space.md)) {
                val slot = d.colorIndex?.let { c.chart.getOrNull(it - 1) }
                Box(
                    Modifier.size(112.dp).clip(CircleShape).background(c.tile).border(3.dp, slot ?: c.lineStrong, CircleShape),
                    contentAlignment = Alignment.Center,
                ) {
                    if (shown != null) LogoInCircle(shown, Modifier.fillMaxSize())
                    else Fig(d.code.ifEmpty { "IG" }, style = Divan.type.figureL, color = slot ?: c.textSecondary)
                }
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(if (shown != null) "این‌طور در دایره دیده میشود" else "هنوز لوگو نداده‌ای", style = Divan.type.small, color = c.textPrimary)
                    when (pending?.state) {
                        "uploading" -> Fig("${(pending.progress * 100).toInt()}%", style = Divan.type.figureSmall, color = c.textMuted)
                        "failed" -> Text(pending.error ?: "بارگذاری نشد.", style = Divan.type.caption, color = c.negative)
                        else -> Text("PNG با زمینه‌ی شفاف بهترین است؛ نشان نهایی از آن ساخته میشود و پیش از مُهر می‌بینی‌اش.", style = Divan.type.caption, color = c.textMuted)
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        HqButton(if (d.logoFileId == null && pending == null) "انتخاب لوگو" else "عوض کن", { pick.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) }, size = BtnSize.SM, icon = DivanIcon.IMAGE)
                        if (pending?.state == "failed") HqButton("دوباره", { files.retry(pending) }, size = BtnSize.SM, variant = BtnVariant.GHOST, icon = DivanIcon.REFRESH)
                        if (d.logoFileId != null || pending != null) HqButton("بردار", { files.clear(); set(d.copy(logoFileId = null)) }, size = BtnSize.SM, variant = BtnVariant.TEXT, icon = DivanIcon.CLOSE)
                    }
                }
            }
            Column(verticalArrangement = Arrangement.spacedBy(Space.xs)) {
                Label("رنگ شرکت", "در نمودارها و کارت‌ها؛ رنگ‌های گرفته‌شده کم‌رنگ‌اند")
                FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Swatch(null, d.colorIndex == null, false) { set(d.copy(colorIndex = null)) }
                    c.chart.forEachIndexed { i, col ->
                        val n = i + 1
                        Swatch(col, d.colorIndex == n, n in usedSlots && d.colorIndex != n) { set(d.copy(colorIndex = n)) }
                    }
                }
            }
            if (d.path != FoundingPath.REGISTER) Text(
                "شرکت بعد از مُهر پیشنهاد ساخته میشود؛ لوگو و رنگ تا آن موقع روی همین گوشی میمانند و در قدم «مُهر شرکت» به کار میروند.",
                style = Divan.type.caption, color = c.textMuted,
            )
        }
    }
}

/** One colour of the palette (null: «خودکار», the hub picks a free one). */
@Composable
private fun Swatch(color: Color?, on: Boolean, used: Boolean, onPick: () -> Unit) {
    val c = Divan.colors
    Box(
        Modifier.size(36.dp).alpha(if (used) 0.35f else 1f).clip(CircleShape).background(color ?: c.tile)
            .border(if (on) 3.dp else 1.dp, if (on) c.goldInk else c.lineStrong, CircleShape)
            .clickable(enabled = !used, role = Role.RadioButton, onClick = onPick)
            .semantics { contentDescription = if (color == null) "رنگ خودکار" else if (used) "این رنگ را شرکت دیگری دارد" else "رنگ شرکت" },
        contentAlignment = Alignment.Center,
    ) {
        if (color == null) Text("خودکار", style = Divan.type.micro, color = c.textSecondary)
        else if (on) DIcon(DivanIcon.SEAL, size = 14.dp, tint = Color.White, active = true)
    }
}

/** Step 4: everything on one card, each part with «ویرایش», and what happens the moment the owner confirms. */
@Composable
private fun Review(d: FoundingDraft, edit: (Int) -> Unit) {
    val env = LocalEnv.current
    val c = Divan.colors
    val way = WAYS.firstOrNull { it.path == d.path }
    Column(verticalArrangement = Arrangement.spacedBy(Space.sm)) {
        HqCard(Modifier.fillMaxWidth()) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Space.sm)) {
                val slot = d.colorIndex?.let { c.chart.getOrNull(it - 1) }
                Box(Modifier.size(56.dp).clip(CircleShape).background(c.tile).border(2.dp, slot ?: c.lineStrong, CircleShape), contentAlignment = Alignment.Center) {
                    d.logoFileId?.let { LogoInCircle(env.media.imageModel(it), Modifier.fillMaxSize()) }
                        ?: Fig(d.code, style = Divan.type.figure, color = slot ?: c.textSecondary)
                }
                Column(Modifier.weight(1f)) {
                    Text(d.nameFa.trim(), style = Divan.type.h2)
                    Text(buildAnnotatedString { fig(d.code, c.textMuted); append("  ·  "); append(d.tagline.trim()) }, style = Divan.type.caption, color = c.textSecondary, maxLines = 2)
                }
                HqButton("ویرایش", { edit(1) }, size = BtnSize.SM, variant = BtnVariant.TEXT)
            }
            Box(Modifier.fillMaxWidth().padding(vertical = Space.sm).height(1.dp).background(c.lineDivider))
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Space.sm)) {
                way?.let { DIcon(it.icon, size = 18.dp, tint = c.goldInk) }
                Column(Modifier.weight(1f)) {
                    Text(way?.title ?: "—", style = Divan.type.bodyStrong)
                    when (d.path) {
                        FoundingPath.REPO -> Fig(FoundingRules.repo(d.repo) ?: d.repo, style = Divan.type.figureSmall, color = c.textMuted)
                        FoundingPath.IDEA -> Text(d.idea.trim(), style = Divan.type.caption, color = c.textMuted, maxLines = 3)
                        FoundingPath.REGISTER -> Text(buildAnnotatedString { append("نام لاتین: "); fig(d.nameEn.trim().ifEmpty { d.code }) }, style = Divan.type.caption, color = c.textMuted)
                        null -> Unit
                    }
                }
                HqButton("ویرایش", { edit(2) }, size = BtnSize.SM, variant = BtnVariant.TEXT)
            }
            Box(Modifier.fillMaxWidth().padding(vertical = Space.sm).height(1.dp).background(c.lineDivider))
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Space.sm)) {
                DIcon(DivanIcon.IMAGE, size = 18.dp, tint = c.textSecondary)
                Text(
                    listOfNotNull(if (d.logoFileId != null) "لوگو داده شد" else "بی‌لوگو (بعداً)", if (d.colorIndex != null) "رنگ انتخاب شد" else "رنگ خودکار").joinToString("، "),
                    style = Divan.type.small, color = c.textSecondary, modifier = Modifier.weight(1f),
                )
                HqButton("ویرایش", { edit(3) }, size = BtnSize.SM, variant = BtnVariant.TEXT)
            }
        }
        HqCard(Modifier.fillMaxWidth(), color = c.softGold) {
            Text("با تأیید تو", style = Divan.type.bodyStrong, color = c.goldInk)
            Column(Modifier.padding(top = 6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                val lines = when (d.path) {
                    FoundingPath.REGISTER -> listOf(
                        "با اثر انگشت یا چهره شرکت ثبت میشود؛ با دپارتمان‌های الگوی استاندارد، بی‌کارمند و بی‌سرور.",
                        if (d.logoFileId != null) "نشانش از لوگو ساخته میشود و در صفحه‌ی شرکت منتظر مُهر تو میماند." else "تا نشان بدهی، کد جای نشان را میگیرد.",
                        "استخدام، نشان و سرور را هر وقت خواستی از صفحه‌ی شرکت کامل کن.",
                    )
                    FoundingPath.REPO -> listOf(
                        "ممیزی فقط‌خواندنی ریپو شروع میشود؛ هیچ چیز اجرا یا push نمیشود.",
                        "بعد پیشنهاد کامل (نام، تیم، بودجه، نقشه‌ی راه) و طرح سرور به کارتابلت میاید.",
                        "شرکت فقط با مُهر تو ساخته میشود و سرور با مُهر جدا (هزینه‌ی واقعی).",
                    )
                    else -> listOf(
                        "پیشنهاد کامل (ساختار، تیم، بودجه، نقشه‌ی ۹۰ روزه) نوشته میشود و به کارتابلت میاید.",
                        "شرکت فقط با مُهر تو ساخته میشود و سرور با مُهر جدا (هزینه‌ی واقعی).",
                        "هر قدم را در صفحه‌ی تأسیس می‌بینی؛ تا پیش از ساخت سرور میتوانی لغوش کنی.",
                    )
                }
                lines.forEachIndexed { i, l ->
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("${i + 1}.", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk, modifier = Modifier.width(18.dp))
                        Text(l, style = Divan.type.small, color = c.textPrimary, modifier = Modifier.weight(1f))
                    }
                }
            }
        }
    }
}

/** The logo cropped to its circle, as the company's mark is seen. Bytes (the demo's data: ids) are decoded at once; a picked file or an
 *  upload is loaded like every other image. */
@Composable
private fun LogoInCircle(model: Any, modifier: Modifier) {
    val env = LocalEnv.current
    val bytes = model as? ByteArray
    val bitmap = remember(bytes) { bytes?.let { runCatching { android.graphics.BitmapFactory.decodeByteArray(it, 0, it.size)?.asImageBitmap() }.getOrNull() } }
    if (bitmap != null) androidx.compose.foundation.Image(bitmap, "لوگو در دایره", modifier.clip(CircleShape), contentScale = ContentScale.Crop)
    else AsyncImage(model, "لوگو در دایره", env.media.images, modifier.clip(CircleShape), contentScale = ContentScale.Crop)
}
