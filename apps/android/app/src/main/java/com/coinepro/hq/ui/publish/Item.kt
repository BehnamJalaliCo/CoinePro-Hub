package com.coinepro.hq.ui.publish

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.data.allTexts
import com.coinepro.hq.core.data.atHandle
import com.coinepro.hq.core.data.downloadable
import com.coinepro.hq.core.data.faHour
import com.coinepro.hq.core.data.faNum
import com.coinepro.hq.core.data.fileRoleFa
import com.coinepro.hq.core.data.jDayFa
import com.coinepro.hq.core.data.pubKindFa
import com.coinepro.hq.core.data.pubStateFa
import com.coinepro.hq.core.data.pubStateTone
import com.coinepro.hq.core.data.sizeFa
import com.coinepro.hq.core.data.tehranDate
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.PubFile
import com.coinepro.hq.core.net.Publication
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.IconBtn
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.CopyAction
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.look.FileFace
import com.coinepro.hq.ui.look.FileViewer
import com.coinepro.hq.ui.look.PlaySign
import com.coinepro.hq.ui.media.openFile
import com.coinepro.hq.ui.rememberCopy
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.served
import kotlinx.coroutines.launch

// ⟨1.39⟩ Contract §60.1 and D6: one publication, whole (its media with its cover, every text with «کپی», its hours, what made it, its
// files, its place for insights), and a set of stories as a full-screen swipe, each slide with its own hour.

/** «۲۵ آبان · ۱۹:۰۰». */
private fun dayHour(iso: String?): String = "${tehranDate(iso)?.let { jDayFa(it) } ?: "—"} · ${faHour(iso)}"

@Composable
fun PublicationScreen(ref: String) {
    val c = Divan.colors
    val nav = LocalNav.current
    val q = rememberPublication(ref)
    OnPublication { q.refresh() }
    val has = served(HubFeature.PUBLICATIONS)
    Page(onRefresh = { q.refresh() }, refreshing = q.state.refreshing) {
        val p = q.data
        when {
            !has -> item(key = "old") { Empty("این صفحه با به‌روزرسانی بعدی هاب می‌آید", icon = DivanIcon.SEND) }
            p == null && q.error != null -> item(key = "error") { ErrorBlock(q.error, { q.refresh() }) }
            p == null -> item(key = "sk") { Skeleton(Modifier.fillMaxWidth().height(420.dp), radius = 18.dp) }
            else -> {
                item(key = "head") { PageHeader("${pubKindFa(p.kind)} · @${p.account}", eyebrow = "${p.companyFa} · ${p.ref}") }
                item(key = "media") { Media(p) }
                item(key = "title") {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(plain(p.titleFa), style = Divan.type.h2, modifier = Modifier.semantics { heading() })
                        @OptIn(ExperimentalLayoutApi::class)
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Pill(pubStateFa(p.state), pubStateTone(p.state), icon = if (p.state == "published") DivanIcon.SEAL else null, dot = p.state != "published")
                            Pill(dayHour(p.publishedAt ?: p.scheduledAt ?: p.at), Tone.NEUTRAL)
                            p.topicFa?.let { Pill("موضوع: $it", Tone.NEUTRAL) }
                        }
                        p.stateNoteFa?.takeIf { p.state in setOf("held", "failed", "cancelled") }?.let {
                            Text(plain(it), style = Divan.type.small, color = if (p.state == "failed") c.negative else c.warning)
                        }
                    }
                }
                item(key = "quick") { Quick(p) }
                item(key = "texts") { Texts(p) }
                item(key = "times") {
                    HqCard(Modifier.fillMaxWidth()) {
                        KV("زمان‌بندی", p.scheduledAt?.let(::dayHour) ?: "—")
                        KV("انتشار", p.publishedAt?.let { "${faHour(it)} · ${if (p.url != null) "لینک ثبت شد" else "منتشر شد"}" } ?: pubStateFa(p.state))
                        val s = p.source
                        if (s.automation != null) KV("ساخته‌شده با", "${s.automationFa ?: s.automation}${s.version?.let { " · نسخه‌ی ${faNum(it)}" } ?: ""}", gold = true) { nav.go("automation/${s.automation}") }
                        s.order?.let { o -> KV("جلسه", o, gold = true) { nav.go("order/$o") } }
                    }
                }
                val files = downloadable(p)
                if (files.isNotEmpty()) item(key = "files") {
                    HqCard(Modifier.fillMaxWidth().testTag("pub-files")) { for ((i, f) in files.withIndex()) FileLine(f, last = i == files.lastIndex) }
                }
                item(key = "insights") { Insights(p) }
                item(key = "keep") { Text("فایل‌های این ردیف همیشه میمانند؛ پاک‌سازی ۷۲ ساعته به آن‌ها دست نمیزند.", style = Divan.type.micro, color = c.textMuted) }
            }
        }
    }
}

/** The media: the video (its cover over it until played) or the picture, at 9:16; the cover beside it, small. A slide opens its set. */
@Composable
private fun Media(p: Publication) {
    val c = Divan.colors
    val nav = LocalNav.current
    var open by remember { mutableStateOf<com.coinepro.hq.core.net.FileRef?>(null) }
    val video = p.files.firstOrNull { it.role == "video" }
    val cover = p.files.firstOrNull { it.role == "cover" }
    val picture = p.files.firstOrNull { it.role == "image" && (it.mime ?: "").startsWith("image/") } ?: p.files.firstOrNull { it.role == "slide" }
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp, Alignment.CenterHorizontally), verticalAlignment = Alignment.Bottom) {
        Box(
            Modifier.width(230.dp).aspectRatio(9f / 16f).testTag("pub-media").clip(RoundedCornerShape(20.dp)).background(tintOf(p.account))
                .clickable(role = Role.Button, onClickLabel = if (video != null) "پخش" else "نمایش") {
                    if (p.set != null) nav.go("publication/${p.ref}/set") else open = (video ?: picture)?.asFile()
                },
        ) {
            Text(plain(p.titleFa), style = Divan.type.h3.copy(fontWeight = FontWeight.Bold), color = Color(0xFFF7F2E6), modifier = Modifier.align(Alignment.BottomStart).padding(16.dp))
            val face = cover ?: picture
            if (face != null) FileFace(face.asFile(), large = true, mark = false)
            if (video != null) PlaySign(56.dp)
        }
        if (video != null && cover != null) Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Box(Modifier.size(width = 72.dp, height = 128.dp).clip(RoundedCornerShape(12.dp)).background(tintOf(p.account)).clickable(role = Role.Button, onClickLabel = "کاور") { open = cover.asFile() }) {
                FileFace(cover.asFile(), mark = false)
            }
            Text("کاور", style = Divan.type.micro, color = c.textMuted)
        }
    }
    open?.let { f -> FileViewer(f) { open = null } }
}

@Composable
private fun RowScope.QuickBtn(icon: DivanIcon, label: String, onClick: () -> Unit) {
    val c = Divan.colors
    Column(
        Modifier.weight(1f).clip(RoundedCornerShape(16.dp)).background(c.card).border(1.dp, c.lineHairline, RoundedCornerShape(16.dp))
            .clickable(role = Role.Button, onClickLabel = label) { onClick() }.padding(vertical = 10.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        DIcon(icon, size = 20.dp, tint = c.goldInk)
        Text(label, style = Divan.type.micro, maxLines = 1)
    }
}

@Composable
private fun Quick(p: Publication) {
    val nav = LocalNav.current
    val uri = LocalUriHandler.current
    val copy = rememberCopy()
    val env = LocalEnv.current
    val context = LocalContext.current
    val toasts = LocalToasts.current
    val scope = rememberCoroutineScope()
    Row(Modifier.testTag("pub-quick"), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        p.url?.let { u -> QuickBtn(DivanIcon.GLOBE, "اینستاگرام") { runCatching { uri.openUri(u) } } }
        QuickBtn(DivanIcon.SHARE, "کپی همه") { copy(allTexts(p)) }
        downloadable(p).firstOrNull()?.let { f -> QuickBtn(DivanIcon.DOWNLOAD, "دانلود") { scope.launch { try { openFile(env, context, f.asFile()) } catch (_: Exception) { toasts.error("فایل باز نشد.") } } } }
        p.source.automation?.let { a -> QuickBtn(DivanIcon.SETTINGS, "اتوماسیون") { nav.go("automation/$a") } }
    }
}

@Composable
private fun Block(title: String, copyText: String?, content: @Composable () -> Unit) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(title, style = Divan.type.bodyStrong, modifier = Modifier.weight(1f))
            if (copyText != null) CopyAction(copyText)
        }
        content()
    }
}

@Composable
private fun Boxed(text: String) {
    val c = Divan.colors
    Text(plain(text), style = Divan.type.small, color = c.textPrimary, modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.tile).padding(horizontal = 14.dp, vertical = 12.dp))
}

/** Every text of the row, each with «کپی»: caption, the comment's words, the DM and its buttons, the public replies in their turn. */
@Composable
private fun Texts(p: Publication) {
    val c = Divan.colors
    val uri = LocalUriHandler.current
    val cm = p.comment
    val any = !p.caption.isNullOrBlank() || cm != null || !p.storyWord.isNullOrBlank()
    if (!any) return
    HqCard(Modifier.fillMaxWidth().testTag("pub-texts")) {
        Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
            p.caption?.trim()?.ifEmpty { null }?.let { cap -> Block("کپشن", cap) { Boxed(cap) } }
            if (cm != null && cm.keywords.isNotEmpty()) Block("کلمه‌ی کامنت", cm.keywords.joinToString("، ")) {
                @OptIn(ExperimentalLayoutApi::class)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    for (w in cm.keywords) Box(Modifier.clip(CircleShape).background(c.softGold).padding(horizontal = 10.dp, vertical = 3.dp)) {
                        Text(plain(w), style = Divan.type.small.copy(fontWeight = FontWeight.Bold), color = c.goldInk)
                    }
                }
                Text("هر کامنتی که یکی از این‌ها را داشته باشد", style = Divan.type.micro, color = c.textMuted)
            }
            cm?.reply?.trim()?.ifEmpty { null }?.let { dm ->
                Block("پیام دایرکت", dm) {
                    Boxed(dm)
                    if (cm.buttons.isNotEmpty()) Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        for (b in cm.buttons) Box(
                            Modifier.weight(1f).clip(RoundedCornerShape(12.dp)).border(1.dp, c.lineStrong, RoundedCornerShape(12.dp))
                                .clickable(role = Role.Button, onClickLabel = b.title) { runCatching { uri.openUri(b.url) } }.padding(vertical = 10.dp),
                            contentAlignment = Alignment.Center,
                        ) { Text(plain(b.title), style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), maxLines = 1) }
                    }
                }
            }
            if (cm != null && cm.publicReplies.isNotEmpty()) Block("جواب‌های عمومی زیر کامنت", cm.publicReplies.joinToString("\n")) {
                for ((i, r) in cm.publicReplies.withIndex()) Text(plain("${faNum(i + 1)} · $r"), style = Divan.type.small)
                Text("به همین ترتیب، به نوبت فرستاده میشوند", style = Divan.type.micro, color = c.textMuted)
            }
            p.storyWord?.trim()?.ifEmpty { null }?.let { w -> Block("کلمه‌ی ریپلای استوری", w) { Boxed("«$w»") } }
        }
    }
}

@Composable
private fun KV(k: String, v: String, gold: Boolean = false, onClick: (() -> Unit)? = null) {
    val c = Divan.colors
    Row(
        Modifier.fillMaxWidth().then(if (onClick != null) Modifier.clip(RoundedCornerShape(8.dp)).clickable(role = Role.Button, onClickLabel = k) { onClick() } else Modifier).padding(vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(k, style = Divan.type.small, color = c.textSecondary)
        Spacer(Modifier.weight(1f))
        Text(plain(v), style = Divan.type.small.copy(fontWeight = if (gold) FontWeight.SemiBold else FontWeight.Normal), color = if (gold) c.goldInk else c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
private fun FileLine(f: PubFile, last: Boolean) {
    val c = Divan.colors
    val env = LocalEnv.current
    val context = LocalContext.current
    val toasts = LocalToasts.current
    val scope = rememberCoroutineScope()
    Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Pill(fileRoleFa(f.role) + (f.n?.let { " ${faNum(it)}" } ?: ""), Tone.NEUTRAL)
        Text(plain(f.name ?: f.fileId), style = Divan.type.small, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
        sizeFa(f.size)?.let { Text(it, style = Divan.type.micro, color = c.textMuted) }
        IconBtn(DivanIcon.DOWNLOAD, "دانلود ${fileRoleFa(f.role)}", { scope.launch { try { openFile(env, context, f.asFile()) } catch (_: Exception) { toasts.error("فایل باز نشد.") } } })
    }
    if (!last) Box(Modifier.fillMaxWidth().height(1.dp).background(c.lineHairline))
}

/** The place for insights: the figures once the hub has them; until then a quiet dashed line (never an error, never «به‌زودی»). */
@Composable
private fun Insights(p: Publication) {
    val c = Divan.colors
    val i = p.insights
    val shape = RoundedCornerShape(18.dp)
    if (i == null || listOf(i.views, i.likes, i.comments, i.dms).all { it == null }) {
        Row(Modifier.fillMaxWidth().testTag("pub-insights").clip(shape).drawWithDash(c.lineStrong, 18.dp).padding(horizontal = 16.dp, vertical = 14.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("بینش", style = Divan.type.small, color = c.textMuted, modifier = Modifier.weight(1f))
            Text("بازدید، کامنت، دایرکت و بهترین ساعت؛ وقتی داده برسد", style = Divan.type.micro, color = c.textMuted)
        }
    } else Row(Modifier.testTag("pub-insights"), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        i.views?.let { Count(it.toInt(), "بازدید") }
        i.comments?.let { Count(it.toInt(), "کامنت") }
        i.dms?.let { Count(it.toInt(), "دایرکت") }
        i.likes?.let { Count(it.toInt(), "لایک") }
    }
}

// --------------------------------------------------------------------------------------------------------- a set --
/** A set of stories, full screen: swipe from slide to slide, each with its hour and whether it went out; the reply word; the strip. */
@OptIn(ExperimentalFoundationApi::class)
@Composable
fun StorySetScreen(ref: String) {
    val nav = LocalNav.current
    val q = rememberPublication(ref)
    val copy = rememberCopy()
    val env = LocalEnv.current
    val context = LocalContext.current
    val toasts = LocalToasts.current
    val scope = rememberCoroutineScope()
    val p = q.data
    val ink = Color(0xFFF7F2E6)
    Box(Modifier.fillMaxSize().background(Color(0xFF05060A)).testTag("story-set")) {
        if (p == null) {
            if (q.error != null) Box(Modifier.padding(24.dp)) { ErrorBlock(q.error, { q.refresh() }) }
            return@Box
        }
        val slides = p.set?.sortedBy { it.n ?: 0 }.orEmpty().ifEmpty { listOf(com.coinepro.hq.core.net.SetItem(p.ref, 1, p.at, p.state, p.files.firstOrNull()?.fileId)) }
        val start = slides.indexOfFirst { it.ref == p.ref }.coerceAtLeast(0)
        val pager = rememberPagerState(initialPage = start) { slides.size }
        Column(Modifier.fillMaxSize().padding(10.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Box(Modifier.fillMaxWidth().weight(1f).clip(RoundedCornerShape(22.dp)).background(tintOf(p.account))) {
                HorizontalPager(pager, Modifier.fillMaxSize()) { i ->
                    val s = slides[i]
                    Box(Modifier.fillMaxSize()) {
                        s.fileId?.let { FileFace(imageRef(it, "slide_${s.n ?: (i + 1)}.jpg"), large = true, mark = false) }
                    }
                }
                Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Row(Modifier.fillMaxWidth().height(3.dp), horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                        for ((i, s) in slides.withIndex()) Box(Modifier.weight(1f).fillMaxSize().clip(RoundedCornerShape(2.dp)).background(if (i <= pager.currentPage || s.state == "published") ink.copy(alpha = if (i == pager.currentPage) 1f else 0.8f) else ink.copy(alpha = 0.25f)))
                    }
                    val s = slides[pager.currentPage]
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Avatar(p.account, 32.dp)
                        Column(Modifier.weight(1f)) {
                            Text(plain(atHandle(p.account)), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = ink)
                            Text("اسلاید ${faNum(pager.currentPage + 1)} از ${faNum(slides.size)} · ${if (s.state == "published") "منتشر شد" else pubStateFa(s.state)} ${faHour(s.at)}",
                                style = Divan.type.micro, color = ink.copy(alpha = 0.75f), modifier = Modifier.testTag("slide-line"))
                        }
                        IconBtn(DivanIcon.CLOSE, "بستن", { nav.back() }, tint = ink)
                    }
                }
                // a slide whose picture is not there (yet): the day's title, never an empty frame
                if (slides[pager.currentPage].fileId == null) Text(plain(p.titleFa), style = Divan.type.h2, color = ink, modifier = Modifier.align(Alignment.Center).padding(24.dp))
                p.storyWord?.let { w ->
                    Row(
                        Modifier.align(Alignment.BottomCenter).padding(12.dp).fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Color.Black.copy(alpha = 0.45f)).padding(horizontal = 12.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(plain("کلمه‌ی ریپلای: «$w»"), style = Divan.type.small, color = ink, modifier = Modifier.weight(1f))
                        IconBtn(DivanIcon.SHARE, "کپی کلمه", { copy(w) }, tint = ink)
                    }
                }
            }
            Row(Modifier.fillMaxWidth().testTag("slide-strip"), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                val from = (pager.currentPage - 3).coerceAtLeast(0)
                for (i in from until (from + 7).coerceAtMost(slides.size)) {
                    val s = slides[i]
                    val on = i == pager.currentPage
                    Box(
                        Modifier.size(width = 44.dp, height = 78.dp).clip(RoundedCornerShape(9.dp)).background(tintOf(p.account).copy(alpha = if (s.state == "published") 1f else 0.55f))
                            .then(if (on) Modifier.border(2.dp, Divan.colors.goldFill, RoundedCornerShape(9.dp)) else Modifier)
                            .clickable(role = Role.Button, onClickLabel = "اسلاید ${faNum(i + 1)}") { scope.launch { pager.animateScrollToPage(i) } },
                        contentAlignment = Alignment.BottomCenter,
                    ) {
                        Text(faHour(s.at) + if (s.state == "published") "\n✓" else "", style = Divan.type.micro.copy(fontSize = 9.sp, lineHeight = 12.sp, fontWeight = FontWeight.Bold), color = ink, modifier = Modifier.padding(4.dp))
                    }
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                val s = slides[pager.currentPage]
                com.coinepro.hq.designsystem.HqButton("همه‌ی متن‌ها و فایل‌ها", { nav.go("publication/${p.ref}") }, Modifier.weight(1f), variant = com.coinepro.hq.designsystem.BtnVariant.SECONDARY)
                s.fileId?.let { id ->
                    com.coinepro.hq.designsystem.HqButton("دانلود این اسلاید", { scope.launch { try { openFile(env, context, imageRef(id, "slide_${s.n ?: 1}.jpg")) } catch (_: Exception) { toasts.error("فایل باز نشد.") } } },
                        Modifier.weight(1f), variant = com.coinepro.hq.designsystem.BtnVariant.PRIMARY, icon = DivanIcon.DOWNLOAD)
                }
            }
            Text("ورق بزن؛ هر اسلاید ساعت خودش را دارد. ✓ یعنی رفت؛ کم‌رنگ یعنی هنوز در صف.", style = Divan.type.micro, color = ink.copy(alpha = 0.55f), modifier = Modifier.fillMaxWidth())
        }
    }
}
