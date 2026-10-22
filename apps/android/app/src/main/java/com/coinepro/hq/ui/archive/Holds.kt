package com.coinepro.hq.ui.archive

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
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
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.actorFa
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.ArchiveRecord
import com.coinepro.hq.core.net.HoldIn
import com.coinepro.hq.core.net.HoldScope
import com.coinepro.hq.core.net.LegalHold
import com.coinepro.hq.core.net.RecordFilters
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v16.ChipRow
import com.coinepro.hq.ui.v17.ActorAvatar
import com.coinepro.hq.ui.v17.RefChip
import com.coinepro.hq.ui.v17.RefTone
import com.coinepro.hq.ui.v16.prose
import java.util.UUID
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

// Legal holds (contract §23.5, §23.12), mirroring apps/web/src/components/v20/holds.tsx and the /archive/holds page: what is frozen, for
// which case, and the owner's release with the passkey; a new hold names records, or facets that must all match.

/** Does a hold cover a record (§23.12): an explicit record always; otherwise every facet it names must match. */
fun covers(m: ArchiveMaps, s: HoldScope, r: ArchiveRecord): Boolean {
    if (r.ref in s.records) return true
    val facets = listOf(s.folders.isNotEmpty(), s.classes.isNotEmpty(), s.parties.isNotEmpty(), s.from != null || s.to != null).count { it }
    if (facets == 0) return false
    if (s.folders.isNotEmpty() && s.folders.none { f -> m.folderPath(r.folder).any { it.ref == f } }) return false
    if (s.classes.isNotEmpty() && r.cls !in s.classes) return false
    if (s.parties.isNotEmpty() && r.parties.none { it.party in s.parties }) return false
    val d = r.docDate
    if (s.from != null && (d == null || d < s.from)) return false
    if (s.to != null && (d == null || d > s.to)) return false
    return true
}

/** The facets of a hold in words: explicit records, then folders, classes, parties and dates that must all match. */
@Composable
fun HoldScopeLine(s: HoldScope, m: ArchiveMaps) {
    val c = Divan.colors
    val facets = buildList {
        if (s.folders.isNotEmpty()) add("پوشه‌ی " + s.folders.joinToString(" یا ") { m.folder(it)?.titleFa ?: it })
        if (s.classes.isNotEmpty()) add("نوع " + s.classes.joinToString(" یا ") { m.cls(it)?.titleFa ?: it })
        if (s.parties.isNotEmpty()) add("با " + s.parties.joinToString(" یا ") { m.party(it)?.nameFa ?: it })
    }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        if (s.records.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            Text("این سندها:", style = Divan.type.caption, color = c.textSecondary)
            for (r in s.records) RefChip(r, tone = RefTone.NEUTRAL)
        }
        if (facets.isNotEmpty() || s.from != null || s.to != null) Text(buildAnnotatedString {
            if (s.records.isNotEmpty()) append("و ")
            append("هر سند " + facets.joinToString(" و "))
            if (s.from != null || s.to != null) {
                if (facets.isNotEmpty()) append(" و")
                append(" تاریخ سند")
                s.from?.let { append(" از "); append(jDay(it)) }
                s.to?.let { append(" تا "); append(jDay(it)) }
            }
        }, style = Divan.type.caption, color = c.textSecondary)
    }
}

@Composable
fun HoldCard(h: LegalHold, m: ArchiveMaps, highlight: Boolean = false, onChanged: () -> Unit = {}) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val action = rememberAction()
    var asking by remember { mutableStateOf(false) }
    var failure by remember { mutableStateOf<ApiException?>(null) }
    val active = h.state == "active"
    val shape = RoundedCornerShape(16.dp)
    Column(
        Modifier.fillMaxWidth().clip(shape).background(c.card).then(if (highlight) Modifier.border(2.dp, c.goldInk, shape) else Modifier).alpha(if (active) 1f else 0.8f).padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DIcon(DivanIcon.LOCK, size = 18.dp, tint = if (active) c.negative else c.textMuted)
            Text(prose(h.titleFa), Modifier.weight(1f), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
            Fig(h.ref, style = Divan.type.figureSmall, color = c.textMuted)
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            if (active) Pill("فعال", Tone.NEG, dot = true) else Pill("آزادشده", Tone.NEUTRAL)
            if (h.case != null) RefChip(h.case, note = "پرونده") else Text("بی‌پرونده", style = Divan.type.micro, color = c.textMuted)
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                ActorAvatar(h.placedBy, size = 18.dp)
                Text(buildAnnotatedString { append(actorFa(h.placedBy) + "، "); append(jStamp(h.placedAt, year = true)) }, style = Divan.type.micro, color = c.textMuted)
            }
            h.releasedAt?.let { Text(buildAnnotatedString { append("آزاد: "); append(jStamp(it, year = true)) }, style = Divan.type.micro, color = c.textMuted) }
        }
        Md(h.reasonMd, style = Divan.type.caption)
        HoldScopeLine(h.scope, m)
        if (active) Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(
                when (h.records) {
                    0 -> "فعلاً سندی زیر آن نیست؛ سند تازه‌ای که بخورد، از همان لحظه توقیف است."
                    1 -> "یک سند زیر این توقیف است؛ جز نسخه‌ی تازه تغییری نمیپذیرد و امحا نمیشود."
                    else -> "${h.records} سند زیر این توقیف‌اند؛ جز نسخه‌ی تازه تغییری نمیپذیرند و امحا نمیشوند."
                },
                style = Divan.type.caption, color = c.textSecondary,
            )
            if (h.recordRefs.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) { for (r in h.recordRefs) RefChip(r) }
        }
        ErrorLine(failure)
        if (active) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            HqButton("آزاد کن", { asking = true }, size = BtnSize.SM, icon = DivanIcon.LOCK)
            Text("آزاد کردن فقط با passkey توست.", style = Divan.type.micro, color = c.textMuted)
        }
    }
    if (asking) AlertDialog(
        onDismissRequest = { asking = false },
        containerColor = c.overlay,
        title = { Text(buildAnnotatedString { append("آزاد کردن "); fig(h.ref) }, style = Divan.type.h3) },
        text = {
            Text(buildAnnotatedString {
                append(
                    when (h.records) {
                        1 -> "یک سند زیر آن دوباره تغییرپذیر میشود و اگر نگهداری‌اش تمام شده باشد، در کارت امحای بعدی میآید."
                        0 -> "سندهای زیر آن دوباره تغییرپذیر میشوند و اگر نگهداری‌شان تمام شده باشد، در کارت امحای بعدی میآیند."
                        else -> "${h.records} سند زیر آن دوباره تغییرپذیر میشوند و اگر نگهداری‌شان تمام شده باشد، در کارت امحای بعدی میآیند."
                    },
                )
                append(" passkey بسته به "); fig(h.ref); append(" است.")
            }, style = Divan.type.small, color = c.textSecondary)
        },
        confirmButton = {
            HqButton("با passkey آزاد کن", {
                failure = null
                action.run(onError = { asking = false; failure = it }) {
                    env.api.releaseLegalHold(h.ref) { a, t -> env.auth.stepUp(act, a, t) }
                    env.cache.invalidate("archive", "legal", "decisions")
                    asking = false
                    onChanged()
                    toasts.ok("توقیف ${h.ref} آزاد شد.")
                }
            }, variant = BtnVariant.PRIMARY, icon = DivanIcon.LOCK, loading = action.busy)
        },
        dismissButton = { HqButton("نه", { asking = false }, variant = BtnVariant.GHOST) },
    )
}

private val REF_RE = Regex("^AR-\\d{6}$")

/** «توقیف تازه»: a title, the case, the reason, and a scope of explicit records or facets that must all match (§23.12). */
@Composable
fun NewHoldContent(caseRef: String?, onClose: () -> Unit, onMade: (String) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val arch = rememberArchive()
    val m = arch.m
    val action = rememberAction()
    val cases = rememberQuery("legal:cases::", "legal") { cases(null, null).items }
    val all = rememberQuery("archive:records:all", "archive") { records(RecordFilters()).items }
    var key by remember { mutableStateOf(UUID.randomUUID().toString()) }
    var title by rememberSaveable { mutableStateOf("") }
    var kase by rememberSaveable { mutableStateOf(caseRef) }
    var reason by rememberSaveable { mutableStateOf("") }
    var s by remember { mutableStateOf(HoldScope()) }
    var refText by remember { mutableStateOf("") }
    var errors by remember { mutableStateOf<Map<String, String>>(emptyMap()) }
    var failure by remember { mutableStateOf<ApiException?>(null) }
    fun toggle(xs: List<String>, v: String) = if (v in xs) xs - v else xs + v
    val hit = all.data.orEmpty().filter { covers(m, s, it) }
    val ok = title.trim().length >= 3 && reason.trim().length >= 10 && !s.empty
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            FieldLabel("عنوان")
            HqTextField(title, { title = it }, "مثلاً: اختلاف با صرافی بر سر کمیسیون", Modifier.fillMaxWidth(), maxLength = 160)
        }
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            FieldLabel("پرونده‌ی حقوقی")
            val list = cases.data.orEmpty()
            Select(kase, list.map { Opt(it.ref, "${it.ref} · ${it.titleFa}") } + listOfNotNull(kase?.takeIf { k -> list.none { it.ref == k } }?.let { Opt(it, it, figure = true) }),
                { kase = it }, "پرونده‌ی حقوقی", Modifier.fillMaxWidth(), nullable = true, none = "— بدون پرونده —", error = errors["case"] != null)
        }
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            FieldLabel("دلیل")
            HqTextField(reason, { reason = it }, "چه چیزی باید دست‌نخورده بماند و تا کی", Modifier.fillMaxWidth(), singleLine = false, minLines = 3, maxLength = 5000)
        }
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(buildAnnotatedString {
                append("سندهایی که نام میبری همیشه زیر توقیف‌اند؛ بقیه‌ی سندها فقط وقتی که ")
                append(androidx.compose.ui.text.AnnotatedString("همه‌ی", androidx.compose.ui.text.SpanStyle(fontWeight = FontWeight.SemiBold)))
                append(" قیدهای پایین را داشته باشند.")
            }, style = Divan.type.caption, color = c.textSecondary)
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                FieldLabel("سند به سند")
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    HqTextField(refText, { refText = it.uppercase() }, "AR-000000", Modifier.weight(1f), maxLength = 12, figure = true)
                    HqButton("افزودن", {
                        val r = refText.trim().uppercase()
                        if (REF_RE.matches(r)) { s = s.copy(records = (s.records + r).distinct()); refText = "" }
                    }, size = BtnSize.SM, enabled = REF_RE.matches(refText.trim().uppercase()))
                }
                if (s.records.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    for (r in s.records) com.coinepro.hq.ui.v16.Chip(true, { s = s.copy(records = s.records - r) }) { ink ->
                        Fig(r, style = Divan.type.figureSmall, color = ink)
                        DIcon(DivanIcon.CLOSE, size = 12.dp, tint = ink)
                    }
                }
            }
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                FieldLabel("پوشه (با زیرپوشه‌ها)")
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    for (f in m.folders.filter { it.status == "active" && it.parent == null }.flatMap { r -> listOf(r) + m.folders.filter { it.parent == r.ref } }) {
                        com.coinepro.hq.ui.v16.Chip(f.ref in s.folders, { s = s.copy(folders = toggle(s.folders, f.ref)) }) { ink ->
                            Text(f.titleFa, style = Divan.type.small, color = ink, maxLines = 1)
                            Fig(f.scope, style = Divan.type.figureSmall, color = ink.copy(alpha = 0.7f))
                        }
                    }
                }
            }
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                FieldLabel("نوع سند")
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    for (k in m.classes.filter { it.status == "active" }) FilterChip(k.titleFa, k.key in s.classes, { s = s.copy(classes = toggle(s.classes, k.key)) })
                }
            }
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                FieldLabel("طرف")
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    for (p in m.parties.filter { it.status == "active" }) FilterChip(p.nameFa, p.ref in s.parties, { s = s.copy(parties = toggle(s.parties, p.ref)) })
                }
            }
            Labelled("تاریخ سند از") { DateField(s.from, { s = s.copy(from = it) }, "توقیف: تاریخ سند از") }
            Labelled("تا") { DateField(s.to, { s = s.copy(to = it) }, "توقیف: تاریخ سند تا") }
            if (errors["scope"] != null) Text("دامنه‌ی توقیف خالی است.", style = Divan.type.caption, color = c.negative)
            if (!s.empty) Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(
                    when { all.data == null -> "در حال شمردن…"; hit.isNotEmpty() -> "${hit.size} سند فعلی را میگیرد:"; else -> "فعلاً سندی را نمیگیرد؛ سندهای آینده‌ای که بخورند را میگیرد." },
                    style = Divan.type.caption, color = c.textSecondary,
                )
                if (hit.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    for (r in hit.take(24)) RefChip(r.ref, note = r.titleFa, tone = RefTone.NEUTRAL)
                }
            }
        }
        ErrorLine(failure)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            HqButton("توقیف کن", {
                errors = emptyMap(); failure = null
                action.run(onError = { e -> if (e.status != 0) key = UUID.randomUUID().toString(); errors = e.fields; failure = e }) {
                    val scope = JsonObject(buildMap {
                        if (s.records.isNotEmpty()) put("records", jarr(s.records))
                        if (s.folders.isNotEmpty()) put("folders", jarr(s.folders))
                        if (s.classes.isNotEmpty()) put("classes", jarr(s.classes))
                        if (s.parties.isNotEmpty()) put("parties", jarr(s.parties))
                        s.from?.let { put("from", JsonPrimitive(it)) }
                        s.to?.let { put("to", JsonPrimitive(it)) }
                    })
                    val h = env.api.placeHold(HoldIn(title.trim(), kase, reason.trim(), scope), key)
                    env.cache.invalidate("archive", "legal", "decisions")
                    toasts.ok("توقیف ${h.ref} گذاشته شد؛ ${h.records} سند زیر آن است.")
                    onMade(h.ref)
                }
            }, variant = BtnVariant.PRIMARY, icon = DivanIcon.LOCK, enabled = ok, loading = action.busy)
            HqButton("انصراف", onClose, variant = BtnVariant.GHOST)
            if (!s.empty) Text("اکنون ${hit.size} سند را میگیرد.", style = Divan.type.caption, color = c.textMuted)
        }
    }
}

/** توقیف‌های قانونی (contract §23.5): what is frozen, for which case, and the owner's release with the passkey. */
@Composable
fun HoldsScreen(focus0: String? = null, newFor: String? = null) {
    val nav = LocalNav.current
    val c = Divan.colors
    val arch = rememberArchive()
    var state by rememberSaveable { mutableStateOf<String?>(null) }
    var making by remember { mutableStateOf(newFor != null) }
    var focus by remember { mutableStateOf(focus0) }
    val q = rememberQuery("archive:holds:${state ?: ""}:", "archive") { legalHolds(state) }
    val r = refresher(q, arch.q)
    val xs = q.data.orEmpty().sortedWith(compareByDescending<LegalHold> { it.state == "active" }.thenByDescending { it.placedAt })
    val n = q.data.orEmpty().count { it.state == "active" }
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            PageHeader("توقیف‌های قانونی", eyebrow = "بایگانی · سندهایی که تا آخر پرونده دست نمیخورند") {
                HqButton("توقیف تازه", { making = true }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.LOCK)
            }
        }
        item {
            Text(
                "سند زیر توقیف جز نسخه‌ی تازه هیچ تغییری نمیپذیرد و حتی اگر نگهداری‌اش تمام شده باشد، از کارت امحا رد میشود. مشاور حقوقی با پرونده‌اش توقیف میگذارد؛ آزاد کردن فقط با passkey توست.",
                style = Divan.type.small, color = c.textSecondary,
            )
        }
        item {
            ChipRow {
                FilterChip("همه", state == null, { state = null })
                FilterChip("فعال", state == "active", { state = "active" }, count = if (state == null && n > 0) n else null)
                FilterChip("آزادشده", state == "released", { state = "released" })
            }
        }
        holdList(q.data, q.error, xs, arch.m, focus, { q.refresh() })
    }
    if (making) HqSheet({ making = false }, "توقیف تازه", sub = "سندهای زیر توقیف جز نسخه‌ی تازه تغییری نمیپذیرند و تا آزاد شدن امحا نمیشوند. آزاد کردن فقط با passkey توست.") {
        NewHoldContent(newFor, { making = false }) { ref -> making = false; focus = ref; nav.go("archive-holds/$ref") }
    }
}

private fun LazyListScope.holdList(data: List<LegalHold>?, error: ApiException?, xs: List<LegalHold>, m: ArchiveMaps, focus: String?, retry: () -> Unit) {
    when {
        data == null && error != null -> item { ErrorBlock(error, retry) }
        data == null -> item { Skeleton(Modifier.fillMaxWidth().height(200.dp), radius = 16.dp) }
        xs.isEmpty() -> item { Empty("توقیفی نیست", icon = DivanIcon.LOCK, body = "مشاور حقوقی با پرونده‌اش توقیف میگذارد؛ تو هم از همین‌جا.") }
        // A hold named in the link (from a record, a case or a ref chip) comes first and is marked.
        else -> for (h in xs.sortedByDescending { it.ref == focus }) item(key = h.ref) { HoldCard(h, m, highlight = h.ref == focus, onChanged = retry) }
    }
}

/** A case's holds on the legal page: what the counsel or the owner froze for it, and a new one tied to this case. */
@Composable
fun CaseHolds(caseRef: String) {
    val c = Divan.colors
    val nav = LocalNav.current
    val q = rememberQuery("archive:holds::$caseRef", "archive") { legalHolds(case = caseRef) }
    val xs = q.data
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("توقیف‌های بایگانی", Modifier.weight(1f), style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
            Row(Modifier.clickable(role = Role.Button) { nav.go("archive-holds-new/$caseRef") }, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                DIcon(DivanIcon.ADD, size = 14.dp, tint = c.goldInk)
                Text("توقیف تازه", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
            }
        }
        when {
            xs == null && q.error != null -> Text(com.coinepro.hq.core.net.archiveError(q.error!!), style = Divan.type.caption, color = c.negative)
            xs == null -> Skeleton(Modifier.fillMaxWidth().height(48.dp), radius = 10.dp)
            xs.isEmpty() -> Text("برای این پرونده سندی توقیف نشده.", style = Divan.type.caption, color = c.textMuted)
            else -> for (h in xs) Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).clickable(role = Role.Button) { nav.go("archive-holds/${h.ref}") }.padding(horizontal = 12.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                DIcon(DivanIcon.LOCK, size = 14.dp, tint = if (h.state == "active") c.negative else c.textMuted)
                Fig(h.ref, style = Divan.type.figureSmall, color = c.textMuted)
                Text(prose(h.titleFa), Modifier.weight(1f), style = Divan.type.caption, color = c.textPrimary, maxLines = 1, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                if (h.state == "active") Text(if (h.records > 0) "${h.records} سند" else "بی‌سند", style = Divan.type.caption, color = c.textSecondary) else Pill("آزادشده", Tone.NEUTRAL)
            }
        }
    }
}
