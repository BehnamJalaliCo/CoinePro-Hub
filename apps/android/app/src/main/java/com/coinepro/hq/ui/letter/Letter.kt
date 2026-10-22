package com.coinepro.hq.ui.letter

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.format.jWeekday
import com.coinepro.hq.core.net.Briefing
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
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v16.ChipRow
import com.coinepro.hq.ui.v16.prose
import com.coinepro.hq.ui.v17.CoMark
import com.coinepro.hq.ui.v17.RefChip
import com.coinepro.hq.ui.v17.ScopeChips
import com.coinepro.hq.ui.v18.AUDIO_STATE
import com.coinepro.hq.ui.v18.AudioPlayer

// گزارش صوتی و نامه‌ی هفتگی (contract §21.4), mirroring apps/web/src/app/(app)/letter/page.tsx: the morning report with its audio, and
// each CEO's Saturday letter (≤ 600 words, from a facts pack built by code; a figure not in it is flagged «عدد بی‌منبع»).

private val KIND_FA = mapOf("morning" to "گزارش صبحگاهی", "ceo_letter" to "نامه‌ی هفتگی")

/** The briefing's voice: the player when ready, else why there is none (the text is unchanged). */
@Composable
fun BriefingVoice(b: Briefing) {
    val c = Divan.colors
    val a = b.audio
    if (a != null && b.audioState == "ready") return AudioPlayer(a.id, "${KIND_FA[b.kind] ?: b.kind} ${b.ref}")
    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.tile).padding(12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        DIcon(DivanIcon.MIC, size = 16.dp, tint = c.textSecondary)
        LabelPill(AUDIO_STATE[b.audioState], b.audioState)
        Text(when (b.audioState) { "failed" -> "متن بی‌تغییر همین‌جاست."; "off" -> "صدا در تنظیمات خاموش است."; else -> "چند دقیقه‌ی دیگر." }, style = Divan.type.caption, color = c.textSecondary)
    }
}

@Composable
private fun VoiceNote(b: Briefing) {
    val v = b.voice ?: return
    Text(buildAnnotatedString {
        append("صدا روی خود هاب ساخته شد: "); fig("${v.engine} ${v.version} · ${v.voice}")
        append(" · لایسنس صدا: "); append(prose(v.license))
        append(". متن گفتاری را کد میسازد: هیچ رقم لاتینی نمیماند.")
    }, style = Divan.type.micro, color = Divan.colors.textMuted)
}

/** One briefing whole: its voice, the text, the deliverable it is, a reply to the CEO. */
@Composable
fun BriefingView(ref: String) {
    val nav = LocalNav.current
    val c = Divan.colors
    val q = rememberQuery("briefings:$ref", "briefings") { briefing(ref) }
    val b = q.data
    when {
        b == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
        b == null -> Skeleton(Modifier.fillMaxWidth().height(240.dp), radius = 12.dp)
        else -> Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                CoMark(b.company, height = 11.dp)
                Text("${jDate(b.period.from)} تا ${jDate(b.period.to)}", style = Divan.type.caption, color = c.textMuted)
            }
            BriefingVoice(b)
            Md(b.textMd, style = Divan.type.body, color = c.textPrimary)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                RefChip(b.deliverableRef, note = "خروجی")
                if (b.kind == "ceo_letter") HqButton("جواب به مدیرعامل", { nav.go("messages/${b.company}-CEO") }, size = BtnSize.SM, variant = BtnVariant.TEXT, icon = DivanIcon.MESSAGES)
            }
            VoiceNote(b)
        }
    }
}

@Composable
fun LetterScreen(open0: String? = null) {
    val c = Divan.colors
    val companies = rememberCompanies()
    val settings = rememberQuery("owner-settings", "settings") { ownerSettings() }
    var kind by rememberSaveable { mutableStateOf<String?>(null) }
    var company by rememberSaveable { mutableStateOf<String?>(null) }
    var open by rememberSaveable { mutableStateOf(open0) }
    val morning = rememberQuery("briefings:latest:morning", "briefings") { latestBriefing("morning") }
    val hist = rememberQuery("briefings:list:${kind ?: ""}:${company ?: ""}", "briefings") { briefings(kind, company).items }
    val r = refresher(morning, hist)
    val operating = companies.filter { it.kind != "holding" }
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("گزارش صوتی و نامه‌ها", eyebrow = "صدا روی خود هاب ساخته میشود؛ هیچ صدایی از هاب بیرون نمیرود") }
        item {
            val a = settings.data?.audioBriefings
            Text(
                "گزارش صبحگاهی همان متن نوشته‌شده است، با صدا. هر شنبه هر مدیرعامل یک نامه‌ی حداکثر ۶۰۰ کلمه‌ای از روی بسته‌ی واقعیت‌هایی که کد میسازد مینویسد؛ عددی که در آن بسته نباشد نامه را یک بار برمیگرداند و بار دوم با برچسب «عدد بی‌منبع» منتشر میشود." +
                    (a?.let { " صدای صبح ${if (it.morning) "روشن" else "خاموش"}، صدای نامه‌ها ${if (it.ceoLetters) "روشن" else "خاموش"} (تنظیمات)." } ?: ""),
                style = Divan.type.small, color = c.textSecondary,
            )
        }
        item {
            HqCard(Modifier.fillMaxWidth()) {
                val b = morning.data
                SectionTitle("گزارش صبحگاهی", note = b?.let { "${jWeekday(it.createdAt)}، ${ago(it.createdAt)}" } ?: "هر روز بعد از نسخه‌ی نوشته‌شده") {
                    if (b != null) HqButton("کامل", { open = b.ref }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.NEXT)
                }
                Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    when {
                        b == null && morning.state.loading -> Skeleton(Modifier.fillMaxWidth().height(160.dp), radius = 12.dp)
                        b == null -> Empty("گزارش امروز هنوز نیامده", icon = DivanIcon.REPORT)
                        else -> {
                            BriefingVoice(b)
                            Md(b.textMd, style = Divan.type.body, color = c.textPrimary)
                            VoiceNote(b)
                        }
                    }
                }
            }
        }
        for (co in operating) item(key = "letter:${co.code}") { LetterCard(co.code, co.nameFa ?: co.code) { open = it } }
        item {
            HqCard(Modifier.fillMaxWidth()) {
                SectionTitle("همه‌ی گزارش‌ها و نامه‌ها")
                Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    ChipRow {
                        FilterChip("همه", kind == null, { kind = null })
                        FilterChip("صبحگاهی", kind == "morning", { kind = "morning" })
                        FilterChip("نامه‌ها", kind == "ceo_letter", { kind = "ceo_letter" })
                    }
                    ScopeChips(company, { company = it }, allLabel = "همه‌ی شرکت‌ها")
                    val list = hist.data
                    when {
                        list == null -> Skeleton(Modifier.fillMaxWidth().height(160.dp), radius = 12.dp)
                        list.isEmpty() -> Text("چیزی نیست.", style = Divan.type.caption, color = c.textMuted)
                        else -> Column {
                            list.forEachIndexed { i, b ->
                                if (i > 0) HorizontalDivider(color = c.lineDivider)
                                Row(
                                    Modifier.fillMaxWidth().clickable(role = Role.Button) { open = b.ref }.padding(vertical = 10.dp),
                                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
                                ) {
                                    Box(Modifier.size(32.dp).clip(CircleShape).background(c.tile), contentAlignment = Alignment.Center) {
                                        DIcon(if (b.kind == "morning") DivanIcon.REPORT else DivanIcon.MESSAGES, size = 16.dp, tint = if (b.kind == "morning") c.goldInk else c.textSecondary)
                                    }
                                    Column(Modifier.weight(1f)) {
                                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                            CoMark(b.company, height = 11.dp)
                                            Text(KIND_FA[b.kind] ?: b.kind, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                                        }
                                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                            Text(jWeekday(b.createdAt), style = Divan.type.micro, color = c.textMuted)
                                            Fig(b.ref, style = Divan.type.figureSmall, color = c.textMuted)
                                        }
                                    }
                                    LabelPill(AUDIO_STATE[b.audioState], b.audioState)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    open?.let { ref -> HqSheet({ open = null }, KIND_FA[hist.data?.firstOrNull { it.ref == ref }?.kind ?: morning.data?.takeIf { it.ref == ref }?.kind] ?: "گزارش", ref = ref) { BriefingView(ref) } }
}

@Composable
private fun LetterCard(company: String, name: String, onOpen: (String) -> Unit) {
    val c = Divan.colors
    val q = rememberQuery("briefings:latest:ceo_letter:$company", "briefings") { latestBriefing("ceo_letter", company) }
    val b = q.data
    val flagged = b?.textMd?.contains("عدد بی‌منبع") == true
    HqCard(Modifier.fillMaxWidth()) {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                CoMark(company, height = 14.dp)
                Text("نامه‌ی مدیرعامل $name", Modifier.weight(1f), style = Divan.type.bodyStrong)
                if (flagged) Pill("عدد بی‌منبع", Tone.NEG, icon = DivanIcon.URGENT)
            }
            when {
                b == null && q.state.loading -> Skeleton(Modifier.fillMaxWidth().height(110.dp), radius = 12.dp)
                b == null -> Text("نامه‌ی این هفته هنوز نیامده.", style = Divan.type.caption, color = c.textMuted)
                else -> {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text("هفته‌ی منتهی به ${jDate(b.period.to)} ·", style = Divan.type.micro, color = c.textMuted)
                        Fig(b.ref, style = Divan.type.figureSmall, color = c.textMuted)
                    }
                    BriefingVoice(b)
                    val plain = b.textMd.lines().filterNot { it.startsWith(">") }.joinToString(" ") { it.replace(Regex("^\\s*-\\s+"), "") }.replace(Regex("[*#`]"), "").replace(Regex("\\s+"), " ").trim()
                    Text(prose(plain), style = Divan.type.small, color = c.textSecondary, maxLines = 4, overflow = TextOverflow.Ellipsis)
                    HqButton("خواندن کامل", { onOpen(b.ref) }, size = BtnSize.SM)
                }
            }
        }
    }
}
