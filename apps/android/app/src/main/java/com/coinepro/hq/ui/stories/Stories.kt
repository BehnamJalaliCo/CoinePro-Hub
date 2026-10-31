package com.coinepro.hq.ui.stories

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import coil3.compose.AsyncImage
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.net.Company
import com.coinepro.hq.core.net.StoryRing
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.IconBtn
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.figs
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

private val KIND = mapOf(
    "hire" to (DivanIcon.HIRE to "استخدام تازه"), "deliverable" to (DivanIcon.DELIVERABLE to "خروجی برجسته"), "stars" to (DivanIcon.STAR to "ستاره‌ی هفته"),
    "milestone" to (DivanIcon.CHART to "هدف رسید"), "post" to (DivanIcon.MESSAGES to "از مدیرعامل"),
    // ⟨1.6⟩ §22.5: a role written on demand became active; the owner can retire it from the story.
    "role" to (DivanIcon.DEPARTMENT to "نقش تازه"),
)
private const val SECONDS = 6f

/** A company's accent: its fixed slot in the categorical palette; none = silver. */
@Composable
private fun accentOf(companies: List<Company>, code: String): Color {
    val c = Divan.colors
    val i = companyOf(companies, code).colorIndex
    return if (i != null && i in 1..c.chart.size) c.chart[i - 1] else c.silverInk
}

/** Contract §18.12: the companies' stories, a row of rings at the top of «فرمان» (owner, 2026-10-17). Gold while something is unseen. */
@Composable
fun StoriesBar() {
    val stories = rememberQuery("stories", "stories", maxAgeMs = 60_000) { stories() }
    val companies = rememberCompanies()
    val rings = stories.data.orEmpty()
    var open by rememberSaveable { mutableStateOf<Int?>(null) }
    val c = Divan.colors
    if (rings.isEmpty()) return
    com.coinepro.hq.designsystem.ScrollRow(spacing = 12.dp) {
        rings.forEachIndexed { i, r ->
            val name = companyOf(companies, r.company).nameFa
            val accent = accentOf(companies, r.company)
            Column(
                Modifier.width(72.dp).clip(RoundedCornerShape(12.dp)).clickable(role = Role.Button) { open = i }
                    .semantics { contentDescription = "استوری $name" + if (r.unseen > 0) "، ${r.unseen} تازه" else "" }.padding(vertical = 4.dp),
                horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                val ring = if (r.unseen > 0) Brush.sweepGradient(listOf(c.goldBright, c.goldInk, accent, c.goldBright)) else Brush.linearGradient(listOf(c.lineStrong, c.lineStrong))
                Box(Modifier.size(66.dp).clip(CircleShape).background(ring).padding(2.5.dp), contentAlignment = Alignment.Center) {
                    Box(Modifier.fillMaxSize().clip(CircleShape).background(c.page).padding(3.dp)) {
                        Box(Modifier.fillMaxSize().clip(CircleShape).background(c.card), contentAlignment = Alignment.Center) { CompanyMark(r.company, height = 24.dp) }
                    }
                }
                Text(
                    name, style = Divan.type.micro.copy(fontWeight = if (r.unseen > 0) FontWeight.SemiBold else FontWeight.Normal),
                    color = if (r.unseen > 0) c.textPrimary else c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
    open?.let { start ->
        Dialog(onDismissRequest = { open = null }, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
            StoryPlayer(rings, start, onClose = { open = null })
        }
    }
}

/** The player: one ring after another, six seconds a card, hold to pause; a tap on the left goes forward (RTL), on the right back.
 *  `autoplay = false` holds the first card still (screenshots). */
@Composable
fun StoryPlayer(live: List<StoryRing>, start: Int, onClose: () -> Unit, autoplay: Boolean = true, kind0: String? = null) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val nav = LocalNav.current
    val act = activity()
    val c = Divan.colors
    val companies = rememberCompanies()
    // A snapshot, so a refetch while watching never reorders what is playing.
    val rings = remember { live }
    fun first(r: StoryRing?) = r?.items?.indexOfFirst { !it.seen }?.coerceAtLeast(0) ?: 0
    var ring by remember { mutableStateOf(start) }
    var item by remember { mutableStateOf(rings.getOrNull(start)?.items?.indexOfFirst { it.kind == kind0 }?.takeIf { kind0 != null && it >= 0 } ?: first(rings.getOrNull(start))) }
    var elapsed by remember { mutableFloatStateOf(0f) }
    var held by remember { mutableStateOf(false) }
    var paused by remember { mutableStateOf(!autoplay) }
    var confirm by remember { mutableStateOf(false) }
    val welcomed = remember { mutableStateMapOf<String, Boolean>() }
    val action = rememberAction()
    val scope = rememberCoroutineScope()
    val r = rings[ring]
    val story = r.items[item]

    fun next() {
        elapsed = 0f
        when {
            item < r.items.size - 1 -> item += 1
            ring < rings.size - 1 -> { ring += 1; item = first(rings[ring]) }
            else -> onClose()
        }
    }
    fun prev() {
        elapsed = 0f
        when {
            item > 0 -> item -= 1
            ring > 0 -> { ring -= 1; item = 0 }
        }
    }

    // Seen as soon as it is on screen; the rings refresh when the player closes.
    LaunchedEffect(story.ref) {
        if (!story.seen && autoplay) runCatching { env.api.storiesSeen(listOf(story.ref)) }
        env.cache.invalidate("stories")
    }
    LaunchedEffect(story.ref, held, paused, confirm) {
        if (held || paused || confirm) return@LaunchedEffect
        while (elapsed < SECONDS) { delay(50); elapsed += 0.05f }
        next()
    }

    val accent = accentOf(companies, r.company)
    val name = companyOf(companies, r.company).nameFa
    Box(
        Modifier.fillMaxSize().background(Brush.verticalGradient(0f to lerp(c.page, accent, 0.34f), 0.72f to c.page)),
    ) {
        Column(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding()) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp).padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                r.items.forEachIndexed { i, _ ->
                    val f = when { i < item -> 1f; i > item -> 0f; else -> (elapsed / SECONDS).coerceIn(0f, 1f) }
                    Box(Modifier.weight(1f).height(3.dp).clip(CircleShape).background(c.textPrimary.copy(alpha = 0.22f))) {
                        Box(Modifier.fillMaxHeight().fillMaxWidth(f).clip(CircleShape).background(c.textPrimary))
                    }
                }
            }
            Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Box(Modifier.size(36.dp).clip(CircleShape).background(c.card), contentAlignment = Alignment.Center) { CompanyMark(r.company, height = 18.dp) }
                Column(Modifier.weight(1f)) {
                    Text(name, style = Divan.type.bodyStrong, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(
                        // The author's code is a figure; the relative time is prose, so its count keeps Persian digits (as ago() does everywhere).
                        buildAnnotatedString {
                            val a = story.author
                            if (a == null || a.kind == "system" || a.kind == "service") append("سیستم") else { append("مدیرعامل، "); fig(a.code) }
                            append("، " + ago(story.createdAt))
                        },
                        style = Divan.type.micro, color = c.textMuted, maxLines = 1,
                    )
                }
                val stopped = held || paused || confirm
                IconBtn(if (stopped) DivanIcon.RESUME else DivanIcon.PAUSE, if (stopped) "ادامه" else "مکث", { paused = !paused })
                IconBtn(DivanIcon.CLOSE, "بستن", onClose)
            }

            // The card: press and hold pauses; a short tap on the left goes forward, on the right goes back.
            Column(
                Modifier.weight(1f).fillMaxWidth().pointerInput(story.ref) {
                    detectTapGestures(
                        onPress = { held = true; tryAwaitRelease(); held = false },
                        onTap = { o -> if (o.x < size.width / 2f) next() else prev() },
                    )
                }.padding(horizontal = 24.dp),
                verticalArrangement = Arrangement.spacedBy(18.dp, Alignment.CenterVertically),
            ) {
                val (icon, fa) = KIND[story.kind] ?: (DivanIcon.INFO to story.kind)
                Row(
                    Modifier.clip(CircleShape).background(c.card.copy(alpha = 0.8f)).padding(horizontal = 12.dp, vertical = 6.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    DIcon(icon, size = 15.dp, tint = c.textPrimary)
                    Text(fa, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold))
                }
                Text(figs(story.titleFa), style = Divan.type.h1.copy(fontSize = 26.sp, lineHeight = 36.sp, fontWeight = FontWeight.Bold))
                story.media?.takeIf { it.kind == "image" }?.let { m ->
                    AsyncImage(
                        env.media.imageModel(m.id, null), m.name, env.media.images,
                        Modifier.fillMaxWidth().aspectRatio(16f / 10f).clip(RoundedCornerShape(16.dp)), contentScale = ContentScale.Crop,
                    )
                }
                if (story.bodyFa.isNotBlank()) Text(figs(story.bodyFa), style = Divan.type.body.copy(fontSize = 16.sp, lineHeight = 30.sp), color = c.textSecondary)
                // The tiles share one height: a value on two lines ("Sonnet 5.5") does not leave the others short.
                if (story.figures.isNotEmpty()) Row(Modifier.height(IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    for (f in story.figures) {
                        Column(
                            Modifier.weight(1f).fillMaxHeight().clip(RoundedCornerShape(14.dp)).background(c.card.copy(alpha = 0.78f)).padding(12.dp),
                            verticalArrangement = Arrangement.spacedBy(6.dp),
                        ) {
                            Fig(f.value, style = Divan.type.figureL.copy(fontSize = if (f.value.length > 6) 18.sp else 24.sp, fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 2)
                            Text(f.labelFa, style = Divan.type.micro, color = c.textMuted, maxLines = 1)
                        }
                    }
                }
            }

            HorizontalDivider(color = c.lineDivider)
            Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                val code = story.links.employee
                if (story.kind == "hire" && code != null) {
                    val done = story.welcomed || welcomed[story.ref] == true
                    HqButton(if (done) "خوش‌آمد گفتی" else "خوش‌آمد", {
                        action.run { env.api.welcomeStory(story.ref); welcomed[story.ref] = true; toasts.ok("خوش‌آمدت به مدیر و مدیرعاملش رسید.") }
                    }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.RATE, enabled = !done, loading = action.busy)
                    HqButton("برکنار کن", { confirm = true }, variant = BtnVariant.DANGER, size = BtnSize.SM, icon = DivanIcon.DISMISS)
                } else if (story.kind == "role" && story.links.roleDraft != null) {
                    HqButton("بازنشسته کن", { confirm = true }, variant = BtnVariant.DANGER, size = BtnSize.SM, icon = DivanIcon.PAUSE)
                }
                Spacer(Modifier.weight(1f))
                val link = when {
                    story.links.roleDraft != null -> "roles/${story.links.roleDraft}" to "دیدن نقش"
                    code != null -> "employees/$code" to "دیدن کارمند"
                    story.links.deliverable != null -> "outputs/${story.links.deliverable}" to "دیدن خروجی"
                    story.links.decision != null -> "cartable/${story.links.decision}" to "در کارتابل"
                    story.kind == "stars" -> "stars" to "ستاره‌ها"
                    else -> null
                }
                link?.let { (route, fa) -> HqButton(fa, { onClose(); nav.go(route) }, variant = BtnVariant.TEXT, size = BtnSize.SM) }
            }
        }
    }

    // ⟨1.6⟩ §22.7: retiring a role from its story needs no passkey; employees on it keep running until moved or dismissed.
    val draft = story.links.roleDraft
    if (confirm && story.kind == "role" && draft != null) AlertDialog(
        onDismissRequest = { confirm = false },
        containerColor = c.overlay,
        title = { Text(buildAnnotatedString { append("نقش "); fig(draft); append(" بازنشسته شود؟") }, style = Divan.type.h3) },
        text = { Text("کسی دیگر روی این نقش استخدام نمیشود؛ کارمندهایی که دارد تا جابه‌جایی یا برکناری کار میکنند. منشورش در تاریخچه میماند.", style = Divan.type.small, color = c.textSecondary) },
        confirmButton = {
            HqButton("بازنشسته کن", {
                action.run(onError = { e -> toasts.error(com.coinepro.hq.core.net.mediaError(e)) }) {
                    env.api.retireRoleDraft(draft)
                    env.cache.invalidate("roles", "stories", "hiring")
                    toasts.info("نقش $draft بازنشسته شد؛ استخدام تازه روی آن نیست و کارمندهایش تا جابه‌جایی کار میکنند.")
                    confirm = false
                    scope.launch { next() }
                }
            }, variant = BtnVariant.DANGER, icon = DivanIcon.PAUSE, loading = action.busy)
        },
        dismissButton = { HqButton("نه", { confirm = false }, variant = BtnVariant.GHOST) },
    ) else if (confirm) AlertDialog(
        onDismissRequest = { confirm = false },
        containerColor = c.overlay,
        title = { Fig("${story.links.employee} برکنار شود؟", style = Divan.type.h3) },
        text = { Text("کارهای بازش به مدیرش برمیگردد و کدش دوباره استفاده نمیشود. با اثر انگشت تأیید میشود.", style = Divan.type.small, color = c.textSecondary) },
        confirmButton = {
            HqButton("با اثر انگشت برکنار کن", {
                val code = story.links.employee ?: return@HqButton
                action.run {
                    env.api.dismissEmployee(code, "مالک: از استوری") { a, t -> env.auth.stepUp(act, a, t) }
                    env.cache.invalidate("employees", "companies", "hiring", "stories")
                    toasts.info("$code برکنار شد؛ کارهای بازش به مدیرش برگشت.")
                    confirm = false
                    scope.launch { next() }
                }
            }, variant = BtnVariant.DANGER, icon = DivanIcon.SEAL, loading = action.busy)
        },
        dismissButton = { HqButton("نه", { confirm = false }, variant = BtnVariant.GHOST) },
    )
}

/** For screenshots: the stories of one company, still on the first card (or on the story of [kind]). */
@Composable
fun StoryPreview(company: String, kind: String? = null) {
    val stories = rememberQuery("stories", "stories") { stories() }
    val rings = stories.data ?: return
    val i = rings.indexOfFirst { it.company == company }.coerceAtLeast(0)
    if (rings.isNotEmpty()) StoryPlayer(rings, i, onClose = {}, autoplay = false, kind0 = kind)
}
