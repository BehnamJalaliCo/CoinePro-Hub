package com.coinepro.hq.ui.owner

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.items
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.LEVEL
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.format.actorFa
import com.coinepro.hq.core.net.LevelSettings
import com.coinepro.hq.core.net.NotificationSettings
import com.coinepro.hq.core.net.Resolution
import com.coinepro.hq.core.net.effective
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
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.v14.HqSheet
import java.time.Instant
import kotlinx.coroutines.delay

/** The resolutions book (دفتر مصوبات): every sealed decision and every resolution the owner recorded; numbered, append-only. */
@Composable
fun ResolutionsScreen() {
    val c = Divan.colors
    val nav = LocalNav.current
    val ctx = LocalContext.current
    var text by rememberSaveable { mutableStateOf("") }
    var query by remember { mutableStateOf("") }
    androidx.compose.runtime.LaunchedEffect(text) { delay(300); query = text.trim() }
    val q = rememberQuery("resolutions:$query", "resolutions") { resolutions(q = query.takeIf { it.length >= 2 }) }
    val r = refresher(q)
    var open by remember { mutableStateOf<Resolution?>(null) }
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            PageHeader("دفتر مصوبات", eyebrow = "هر تصمیم مُهرشده و هر مصوبه‌ای که تو ثبت کردی؛ شماره‌دار و تغییرناپذیر") {
                val items = q.data?.items.orEmpty()
                if (items.isNotEmpty()) ExportButton {
                    shareCsv(ctx, "resolutions.csv", listOf("ref", "company", "title", "body", "source", "sealed_at", "sent_to"),
                        items.map { listOf(it.ref, it.company ?: "HQ", it.title, it.body, it.source["decision"] ?: it.source["message"], it.sealedAt, it.sentTo.joinToString(" ")) })
                }
            }
        }
        item { HqTextField(text, { text = it }, "جستجو در عنوان و متن", Modifier.fillMaxWidth(), maxLength = 200) }
        val items = q.data?.items
        when {
            items == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            items == null -> items(3) { Skeleton(Modifier.fillMaxWidth().height(96.dp), radius = 14.dp) }
            items.isEmpty() -> item { Empty(if (query.isNotEmpty()) "مصوبه‌ای با این عبارت نیست" else "هنوز مصوبه‌ای نیست", icon = DivanIcon.SEAL, body = "با مُهر هر تصمیم، مصوبه‌اش اینجا ثبت میشود. از هر پیام هم میتوانی مصوبه ثبت کنی.") }
            else -> items(items, key = { it.ref }) { res ->
                HqCard(Modifier.fillMaxWidth().clickable { open = res }) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Fig(res.ref, style = Divan.type.figureSmall.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
                        if (res.company != null) CompanyMark(res.company, height = 12.dp, mono = true, ink = c.textSecondary) else Pill("هلدینگ")
                        Text(jDate(res.sealedAt, withYear = true), style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f))
                        (res.source["decision"] ?: res.source["message"])?.let { Fig(it, style = Divan.type.figureSmall, color = c.textMuted) }
                    }
                    Text(res.title, style = Divan.type.body.copy(fontWeight = FontWeight.SemiBold), modifier = Modifier.padding(top = 6.dp))
                    Text(res.body, style = Divan.type.small, color = c.textSecondary, maxLines = 2, overflow = TextOverflow.Ellipsis)
                }
            }
        }
    }
    open?.let { res ->
        HqSheet({ open = null }, res.title, ref = res.ref) {
            Md(res.body)
            Text("مُهر: ${actorFa(res.sealedBy)}، ${jDateTime(res.sealedAt)}", style = Divan.type.caption, color = c.textMuted)
            res.source["decision"]?.let { d -> HqButton("تصمیم $d", { open = null; nav.go("cartable/$d") }, size = BtnSize.SM, variant = BtnVariant.TEXT) }
            res.source["message"]?.let { m -> Text("از پیام $m", style = Divan.type.caption, color = c.textMuted) }
            if (res.sentTo.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("ابلاغ به", style = Divan.type.caption, color = c.textMuted)
                res.sentTo.forEach { code -> Fig(code, style = Divan.type.figureSmall, color = c.textSecondary, modifier = Modifier.clip(RoundedCornerShape(20.dp)).background(c.tile).clickable { open = null; nav.go("employees/$code") }.padding(horizontal = 8.dp, vertical = 2.dp)) }
            }
            res.followUpWorkId?.let { w -> HqButton("کار پیگیری", { open = null; nav.go("work/$w") }, size = BtnSize.SM, variant = BtnVariant.TEXT) }
        }
    }
}

private val LEVELS = listOf("urgent", "decision", "report", "info", "learning")
private val MUTES = listOf<Pair<String, Long?>>("بی‌صدا نیست" to null, "یک ساعت" to 3_600_000L, "هشت ساعت" to 8 * 3_600_000L, "یک هفته" to 7 * 86_400_000L)

/** The per-company, per-level matrix (§6): "*" is every company's default, a company row overrides it. Urgent always arrives. */
@Composable
fun NotificationMatrixCard() {
    val c = Divan.colors
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val action = rememberAction()
    val companies = rememberCompanies()
    val q = rememberQuery("notification-settings", "notification-settings", maxAgeMs = 60_000) { notificationSettings() }
    var scope by rememberSaveable { mutableStateOf("*") }
    var edits by remember { mutableStateOf<NotificationSettings?>(null) }
    val base = q.data
    val draft = edits ?: base
    fun set(level: String, f: (LevelSettings) -> LevelSettings) {
        val m = draft ?: return
        val row = m.matrix[scope].orEmpty()
        edits = m.copy(matrix = m.matrix + (scope to (row + (level to f(row[level] ?: LevelSettings())))))
    }
    fun reset(level: String) {
        val m = draft ?: return
        val row = m.matrix[scope].orEmpty() - level
        edits = m.copy(matrix = if (row.isEmpty()) m.matrix - scope else m.matrix + (scope to row))
    }
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("اعلان‌ها برای هر شرکت", note = "ردیف هر شرکت جای پیش‌فرض «همه» را میگیرد. فوری همیشه میرسد.")
        when {
            draft == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
            draft == null -> Skeleton(Modifier.fillMaxWidth().height(200.dp))
            else -> Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip("همه‌ی شرکت‌ها", scope == "*", { scope = "*" })
                    companies.forEach { co -> FilterChip(co.nameFa ?: co.code, scope == co.code, { scope = co.code }) }
                }
                Row(Modifier.fillMaxWidth()) {
                    Text("سطح", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f))
                    listOf("در اپ", "push", "صدا").forEach { Text(it, style = Divan.type.micro, color = c.textMuted, modifier = Modifier.width(56.dp)) }
                }
                for (level in LEVELS) {
                    val e = draft.effective(scope, level)
                    val urgent = level == "urgent"
                    val own = scope != "*" && draft.matrix[scope]?.containsKey(level) == true
                    val muted = e.mutedUntil?.takeIf { runCatching { Instant.parse(it).isAfter(Instant.now()) }.getOrDefault(false) }
                    HorizontalDivider(color = c.lineDivider)
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Row(Modifier.weight(1f), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            DIcon(LEVEL.getValue(level).icon, size = 18.dp)
                            Text(LEVEL.getValue(level).fa, style = Divan.type.small)
                            if (own) Text("مثل همه", style = Divan.type.micro, color = c.goldInk, modifier = Modifier.clickable { reset(level) })
                        }
                        Row(Modifier.width(56.dp)) { HqSwitch(urgent || e.inApp == true, { v -> set(level) { it.copy(inApp = v) } }, "${LEVEL.getValue(level).fa}: در اپ", enabled = !urgent) }
                        Row(Modifier.width(56.dp)) { HqSwitch(urgent || e.push == true, { v -> set(level) { it.copy(push = v) } }, "${LEVEL.getValue(level).fa}: push", enabled = !urgent) }
                        Row(Modifier.width(56.dp)) { HqSwitch(e.sound == true, { v -> set(level) { it.copy(sound = v) } }, "${LEVEL.getValue(level).fa}: صدا") }
                    }
                    if (!urgent) Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text("بی‌صدا", style = Divan.type.micro, color = c.textMuted)
                        if (muted != null) Pill("تا ${jDateTime(muted)}", Tone.WARN)
                        MUTES.forEach { (label, ms) ->
                            FilterChip(label, if (ms == null) muted == null else false, { set(level) { it.copy(mutedUntil = ms?.let { d -> Instant.now().plusMillis(d).toString() } ?: "") } })
                        }
                    }
                }
                val dirty = edits != null && edits != base
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    HqButton("ذخیره", {
                        action.run(onError = { e -> if (e.code == "version_conflict") { edits = null; q.refresh() }; toasts.error(e.messageFa) }) {
                            // An empty mute means "not muted": the server drops nulls, so it is cleared here.
                            val clean = edits!!.copy(matrix = edits!!.matrix.mapValues { (_, row) -> row.mapValues { (_, s) -> if (s.mutedUntil == "") s.copy(mutedUntil = null) else s } })
                            q.set(env.api.saveNotificationSettings(clean.copy(version = base!!.version)))
                            edits = null
                            toasts.ok("تنظیمات اعلان ذخیره شد.")
                        }
                    }, variant = BtnVariant.PRIMARY, enabled = dirty, loading = action.busy)
                    HqButton("برگرداندن", { edits = null }, variant = BtnVariant.GHOST, enabled = dirty)
                }
            }
        }
    }
}
