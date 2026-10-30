package com.coinepro.hq.ui.work

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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.StreamState
import com.coinepro.hq.core.data.SynthKind
import com.coinepro.hq.core.data.SynthSection
import com.coinepro.hq.core.data.councilProgressFa
import com.coinepro.hq.core.data.councilStateFa
import com.coinepro.hq.core.data.memberStateFa
import com.coinepro.hq.core.data.playerFa
import com.coinepro.hq.core.data.providerOfPlayer
import com.coinepro.hq.core.data.synthesisSections
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.net.Council
import com.coinepro.hq.core.net.CouncilMember
import com.coinepro.hq.core.net.Work
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.ModelMark
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Radius
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.Space
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.smoothSize
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Loadable
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.shell.LocalLive
import com.coinepro.hq.ui.substitutes.Thumb
import com.coinepro.hq.ui.v18.mgmt
import com.coinepro.hq.ui.v18.subModel

// Contract §27.2 ⟨1.9⟩: the council of models. The same brief runs independently on every available player (Claude plus every ready
// substitute); each member's answer is its own output, and Claude writes the synthesis: where they agree, where they differ and why,
// the recommendation, each answer whole. For images and videos every player that can make the kind makes its own Creative, shown side
// by side for the owner to pick (and an image to animate). Live: the stream's `work.council` refreshes it.

/** The council of an order: [w] given with `mode: "council"`. */
@Composable
fun rememberCouncil(w: Work) = rememberQuery("council:${w.id}", "council", maxAgeMs = 15_000) { council(w.id) }

/** The «شورا» section of an order's page: each member (logo, model, state, its answer), then Claude's synthesis or the media gallery. */
@Composable
fun CouncilCard(w: Work) {
    val q = rememberCouncil(w)
    val c = q.data
    HqCard(Modifier.fillMaxWidth(), tahrir = c?.state == "done") {
        SectionTitle("شورا", note = "همان شرح، جدا از هم؛ هیچ پاسخی به‌تنهایی شاهد نیست", icon = DivanIcon.MEETING) {
            c?.let { CouncilState(it) }
        }
        Spacer(Modifier.height(Space.sm))
        Loadable(q, skeleton = { Skeleton(Modifier.fillMaxWidth().height(180.dp), radius = Radius.tile) }) { k ->
            Column(Modifier.smoothSize(), verticalArrangement = Arrangement.spacedBy(Space.sm)) {
                Text(councilProgressFa(k), style = Divan.type.caption, color = Divan.colors.textSecondary)
                Column {
                    k.members.forEachIndexed { i, m ->
                        if (i > 0) HorizontalDivider(color = Divan.colors.lineDivider)
                        MemberRow(m)
                    }
                }
                if (k.mediaCouncil) MediaGallery(k) else Synthesis(k)
            }
        }
    }
}

@Composable
private fun CouncilState(k: Council) {
    val live = LocalLive.current
    val moving = k.state == "running" || k.state == "synthesising"
    when {
        k.state == "failed" -> Pill(councilStateFa(k), Tone.NEG, dot = true)
        moving -> Pill(if (live.state == StreamState.LIVE) "زنده" else councilStateFa(k), Tone.GOLD, live = live.state == StreamState.LIVE)
        k.mediaCouncil -> Pill(councilStateFa(k), Tone.GOLD, icon = DivanIcon.IMAGE)
        else -> Pill(councilStateFa(k), Tone.POS, icon = DivanIcon.SEAL)
    }
}

/** One player of the council: its logo, name and model, its state (and why, when it was skipped or failed), a way to its answer. */
@Composable
private fun MemberRow(m: CouncilMember) {
    val nav = LocalNav.current
    val c = Divan.colors
    val out = m.state == "skipped" || m.state == "failed"
    Row(
        Modifier.fillMaxWidth().padding(vertical = 10.dp).semantics(mergeDescendants = true) { contentDescription = "${playerFa(m.player)}: ${memberStateFa(m)}" },
        verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Box(Modifier.size(36.dp).alpha(if (out) 0.5f else 1f).clip(RoundedCornerShape(10.dp)).background(c.tile), contentAlignment = Alignment.Center) {
            ModelMark(m.model.ifBlank { null }, provider = providerOfPlayer(m.player), size = 20.dp)
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(playerFa(m.player), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = if (out) c.textSecondary else c.textPrimary)
                if (m.model.isNotBlank()) Fig(if (m.player == "claude") com.coinepro.hq.core.format.modelLabel(m.model) else subModel(m.model), style = Divan.type.figureSmall, color = c.textMuted)
            }
            m.reason?.takeIf { out }?.let { Text(it, style = Divan.type.micro, color = if (m.state == "failed") c.negative else c.textMuted, maxLines = 3) }
            m.deliverableRef?.takeIf { m.state == "done" && !m.creative }?.let { ref ->
                Row(
                    Modifier.clip(RoundedCornerShape(8.dp)).clickable(role = Role.Button, onClickLabel = "دیدن پاسخ") { nav.go("outputs/$ref") }.padding(vertical = 2.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    DIcon(DivanIcon.DELIVERABLE, size = 13.dp, tint = c.goldInk)
                    Text("پاسخ کامل", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
                    Fig(ref, style = Divan.type.figureSmall, color = c.goldInk)
                }
            }
        }
        Pill(
            memberStateFa(m),
            when (m.state) { "working" -> Tone.GOLD; "done" -> Tone.POS; "failed" -> Tone.NEG; "skipped" -> Tone.SILVER; else -> Tone.NEUTRAL },
            dot = m.state == "queued", live = m.state == "working",
        )
    }
}

// --------------------------------------------------------------- synthesis --
/** Claude's synthesis, highlighted: where the players agree, where they differ and why, the recommendation; each answer whole a tap away. */
@Composable
private fun Synthesis(k: Council) {
    val c = Divan.colors
    val ref = k.synthesisRef
    when {
        ref != null -> {
            val q = rememberQuery("deliverable:$ref", "deliverables") { deliverable(ref) }
            Loadable(q, skeleton = { Skeleton(Modifier.fillMaxWidth().height(220.dp), radius = Radius.tile) }) { d -> SynthesisView(ref, d.title, d.body ?: d.summary, (d.producedWith["model"] as? kotlinx.serialization.json.JsonPrimitive)?.content) }
        }
        k.state == "synthesising" -> Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(Radius.tile)).background(c.softGold).padding(14.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            CircularProgressIndicator(Modifier.size(16.dp), color = c.goldInk, strokeWidth = 2.dp)
            Text("Claude جمع‌بندی را مینویسد: کجا هم‌نظرند، کجا نه و چرا، و پیشنهاد.", style = Divan.type.small, color = c.textPrimary)
        }
        k.state == "running" -> Text("جمع‌بندی بعد از پاسخ همه‌ی بازیکن‌ها نوشته میشود.", style = Divan.type.micro, color = c.textMuted)
    }
}

/** The synthesis on its own: the deliverable's markdown split at its headings, each part with its colour. */
@Composable
fun SynthesisView(ref: String, title: String, body: String, model: String?) {
    val nav = LocalNav.current
    val c = Divan.colors
    val parts = synthesisSections(body)
    var answers by rememberSaveable(ref) { mutableStateOf(false) }
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(Radius.tile)).background(c.softGold).border(1.dp, c.lineTahrir, RoundedCornerShape(Radius.tile)).padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            ModelMark(model ?: "claude", provider = "anthropic", size = 18.dp)
            Column(Modifier.weight(1f)) {
                Text("جمع‌بندی Claude", style = Divan.type.bodyStrong, color = c.goldInk)
                Text(title, style = Divan.type.micro, color = c.textSecondary, maxLines = 2)
            }
            Fig(ref, style = Divan.type.figureSmall, color = c.textMuted)
        }
        for (p in parts) when (p.kind) {
            SynthKind.ANSWERS -> Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                HqButton(if (answers) "بستن پاسخ‌ها" else p.title.ifBlank { "پاسخ هر بازیکن، کامل" }, { answers = !answers }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.REPORT)
                if (answers) Md(p.body, color = c.textPrimary)
            }
            else -> Part(p)
        }
        HqButton("دیدن جمع‌بندی در خروجی‌ها", { nav.go("outputs/$ref") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.NEXT)
    }
}

@Composable
private fun Part(p: SynthSection) {
    val c = Divan.colors
    val (icon, tint) = when (p.kind) {
        SynthKind.AGREE -> DivanIcon.SEAL to c.positive
        SynthKind.DIFFER -> DivanIcon.DELEGATE to c.warning
        SynthKind.RECOMMEND -> DivanIcon.STAR to c.goldInk
        else -> DivanIcon.INFO to c.silverInk
    }
    val rec = p.kind == SynthKind.RECOMMEND
    Column(
        Modifier.fillMaxWidth().then(if (rec) Modifier.clip(RoundedCornerShape(12.dp)).background(c.card).padding(12.dp) else Modifier),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        if (p.title.isNotBlank()) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Box(Modifier.size(22.dp).clip(RoundedCornerShape(11.dp)).background(tint.copy(alpha = 0.14f)), contentAlignment = Alignment.Center) { DIcon(icon, size = 13.dp, tint = tint) }
            Text(p.title, style = Divan.type.small.copy(fontWeight = FontWeight.Bold), color = if (rec) c.goldInk else c.textPrimary)
        }
        Md(p.body, color = if (rec) c.textPrimary else c.textSecondary)
    }
}

// ------------------------------------------------------------------- media --
/** A media council: every player's Creative side by side; the owner picks one, and an image can be made into a video. */
@Composable
private fun MediaGallery(k: Council) {
    val c = Divan.colors
    val shown = k.members.filter { it.creative }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("هر بازیکن نسخه‌ی خودش را ساخت؛ یکی را انتخاب کن. متن فارسی را هاب روی آن میچیند، نه مدل.", style = Divan.type.micro, color = c.textMuted)
        for (row in shown.chunked(2)) Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            for (m in row) CreativePick(m, Modifier.weight(1f))
            if (row.size == 1) Box(Modifier.weight(1f))
        }
    }
}

@Composable
private fun CreativePick(m: CouncilMember, modifier: Modifier) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val ref = m.creativeOf ?: return
    val q = rememberQuery("creatives:$ref", "creatives") { creative(ref) }
    val x = q.data
    val action = rememberAction()
    val picked = x?.pickedAt != null
    Column(
        modifier.clip(RoundedCornerShape(14.dp)).background(if (picked) c.softGold else c.tile)
            .then(if (picked) Modifier.border(1.dp, c.lineTahrir, RoundedCornerShape(14.dp)) else Modifier).padding(8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            ModelMark(m.model.ifBlank { null }, provider = providerOfPlayer(m.player), size = 15.dp)
            Text(playerFa(m.player), Modifier.weight(1f), style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
            Fig(ref, style = Divan.type.figureSmall, color = c.textMuted)
        }
        if (x == null) Skeleton(Modifier.fillMaxWidth().height(220.dp), radius = 12.dp)
        else {
            Box(Modifier.clip(RoundedCornerShape(12.dp)).clickable(role = Role.Button, onClickLabel = "باز کردن") { nav.go("substitutes/$ref") }) { Thumb(x, Modifier.fillMaxWidth()) }
            if (picked) Pill("انتخاب تو", Tone.GOLD, icon = DivanIcon.SEAL)
            else if (x.state == "review") HqButton("این را انتخاب کن", {
                action.mgmt(toasts) {
                    q.set(env.api.pickCreative(ref))
                    env.cache.invalidate("creatives", "council")
                    toasts.ok("نسخه‌ی ${playerFa(m.player)} انتخاب شد. انتشارش جایی همچنان کارت تصمیم میخواهد.")
                }
            }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.SEAL, loading = action.busy)
            else Pill(com.coinepro.hq.ui.v18.CREATIVE[x.state]?.fa ?: x.state, Tone.NEUTRAL)
            if (x.kind == "image" && (x.state == "review" || picked)) HqButton("ویدیو بساز از این", {
                action.mgmt(toasts) {
                    // A video is made from the picked image: animating another version picks it first.
                    if (!picked) q.set(env.api.pickCreative(ref))
                    val v = env.api.animateCreative(ref)
                    env.cache.invalidate("creatives", "council")
                    toasts.ok("ویدیوی ${v.ref} از این تصویر در حال ساخت است.", "دیدن") { nav.go("substitutes/${v.ref}") }
                }
            }, Modifier.fillMaxWidth(), variant = BtnVariant.GHOST, size = BtnSize.SM, icon = DivanIcon.VIDEO, loading = action.busy)
        }
    }
}
