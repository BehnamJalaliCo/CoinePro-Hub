package com.coinepro.hq.ui.v32

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import com.coinepro.hq.designsystem.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import coil3.compose.AsyncImage
import com.coinepro.hq.core.data.personaTitle
import com.coinepro.hq.core.net.TalkPersona
import com.coinepro.hq.designsystem.Avatar
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.Orb
import com.coinepro.hq.designsystem.Sentinel
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.rememberBreath
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery

// Contract §32.1: the faces at the top of the talk screen. Each persona has a face (an avatar file of the hub, else a medallion in the
// app's own language); the one that speaks wears a soft ring that breathes (still when animations are removed).

/** One persona's face, with the ring that says it is speaking ([speaking]) or chosen ([selected]). */
@Composable
fun PersonaFace(p: TalkPersona, size: Dp = 52.dp, speaking: Boolean = false, selected: Boolean = false, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val breath = rememberBreath(speaking, periodMs = 1600)
    val media = LocalEnv.current.media
    Box(modifier.size(size + 12.dp), contentAlignment = Alignment.Center) {
        // The ring lives in the draw phase: a speaking face never recomposes its row.
        Canvas(Modifier.size(size + 12.dp)) {
            val r = this.size.minDimension / 2
            if (speaking) {
                val k = breath.value
                drawCircle(c.goldFill.copy(alpha = 0.10f + 0.12f * k), r)
                drawCircle(c.goldFill.copy(alpha = 0.45f + 0.35f * k), r - 1.5.dp.toPx() - 2.dp.toPx() * (1 - k), style = Stroke(2.dp.toPx()))
            } else if (selected) {
                drawCircle(c.goldFill.copy(alpha = 0.85f), r - 1.5.dp.toPx(), style = Stroke(2.dp.toPx()))
            } else {
                drawCircle(c.lineStrong, r - 1.dp.toPx(), style = Stroke(1.dp.toPx()))
            }
        }
        val title = personaTitle(p)
        when {
            p.face != null -> AsyncImage(media.imageModel(p.face), title, media.images, Modifier.size(size).clip(CircleShape), contentScale = ContentScale.Crop)
            p.key == "advisor" -> Orb(size, state = if (speaking) "speaking" else "rest", label = title)
            p.key == "overseer" -> Sentinel(size, state = if (speaking) "working" else "idle", label = title)
            p.key == "assistant" -> Avatar("assistant", size = size, state = if (speaking) "working" else "idle", label = title)
            p.key == "secretary" -> SecretaryFace(size, speaking, title)
            // ⟨1.17⟩ §35.4 a council model in a session: its own mark on a quiet disc.
            p.key.startsWith("player:") -> Box(Modifier.size(size).clip(CircleShape).background(c.tile).semantics { contentDescription = title }, contentAlignment = Alignment.Center) {
                com.coinepro.hq.ui.work.PlayerLogo(com.coinepro.hq.core.data.PlayerOption.entries.firstOrNull { it.key == p.key.removePrefix("player:") } ?: com.coinepro.hq.core.data.PlayerOption.AUTO, size = size * 0.5f)
            }
            else -> Avatar(if (p.role == "ceo") "ceo" else "manager", size = size, state = if (speaking) "working" else "idle", label = title)
        }
    }
}

/** The holding secretary's medallion: a lapis disc with the meeting glyph and a gold rim (she sits between the owner and every company). */
@Composable
private fun SecretaryFace(size: Dp, speaking: Boolean, label: String) {
    val c = Divan.colors
    Box(
        Modifier.size(size).clip(CircleShape).background(com.coinepro.hq.designsystem.generated.DivanFixed.lapisDisc).semantics { contentDescription = label },
        contentAlignment = Alignment.Center,
    ) {
        Canvas(Modifier.size(size)) {
            drawCircle(c.goldFill.copy(alpha = if (speaking) 0.9f else 0.55f), this.size.minDimension / 2 - 1.dp.toPx(), style = Stroke(1.5.dp.toPx()))
        }
        DIcon(DivanIcon.MEETING, size = size * 0.46f, tint = c.goldBright)
    }
}

/** The row of faces: the standing four, every manager in the room, and «+». */
@Composable
fun FacesRow(
    faces: List<TalkPersona>,
    current: String?,
    speaking: Boolean,
    onPick: (TalkPersona) -> Unit,
    onAdd: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val c = Divan.colors
    val scroll = rememberScrollState()
    // A manager brought in sits after the standing faces: the row moves to show whoever answers.
    androidx.compose.runtime.LaunchedEffect(current, faces.size) { if (current != null && faces.indexOfFirst { it.id == current } >= 4) scroll.animateScrollTo(scroll.maxValue) }
    Row(modifier.fillMaxWidth().horizontalScroll(scroll).padding(horizontal = 12.dp), horizontalArrangement = Arrangement.spacedBy(2.dp), verticalAlignment = Alignment.Top) {
        for (p in faces) {
            val on = p.id == current
            Column(
                Modifier.width(72.dp).clip(RoundedCornerShape(12.dp)).clickable(role = Role.Button, onClickLabel = "حرف زدن با ${personaTitle(p)}") { onPick(p) }.padding(vertical = 4.dp),
                horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(2.dp),
            ) {
                PersonaFace(p, speaking = on && speaking, selected = on)
                Text(
                    personaTitle(p), style = Divan.type.micro.copy(fontWeight = if (on) FontWeight.Bold else FontWeight.Normal, textAlign = TextAlign.Center),
                    color = if (on) c.textPrimary else c.textSecondary, maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.width(68.dp),
                )
            }
        }
        Column(
            Modifier.width(72.dp).clip(RoundedCornerShape(12.dp)).clickable(role = Role.Button, onClickLabel = "آوردن مدیر به گفتگو", onClick = onAdd).padding(vertical = 4.dp),
            horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
            Box(Modifier.size(64.dp), contentAlignment = Alignment.Center) {
                Box(Modifier.size(52.dp).clip(CircleShape).background(c.tile), contentAlignment = Alignment.Center) { DIcon(DivanIcon.ADD, size = 22.dp, tint = c.goldInk) }
            }
            Text("مدیر", style = Divan.type.micro, color = c.textSecondary)
        }
    }
}

/**
 * «+»: the manager to bring in. First the company (a company is data; none is named here), then the role: its CEO or the manager of one
 * of its departments. Picking calls [onPick] with the hub's `role`, the company and, for a department manager, the department.
 */
@Composable
fun InviteBody(onPick: (role: String, company: String, department: String?) -> Unit, company0: String? = null) {
    val c = Divan.colors
    val companies = rememberCompanies().filter { it.kind != "holding" && it.status == "active" }
    var company by rememberSaveable { mutableStateOf(company0) }
    Text("مدیر کدام شرکت؟", style = Divan.type.h2)
    Text("منشی هلدینگ همیشه کنار توست؛ مدیر فقط از داده‌ی شرکت خودش جواب میدهد و کار را به فرمان تبدیل میکند.", style = Divan.type.caption, color = c.textMuted)
    val chosen = company
    if (chosen == null) {
        if (companies.isEmpty()) Text("هنوز شرکتی نیست.", style = Divan.type.small, color = c.textMuted)
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(c.card)) {
            companies.forEachIndexed { i, co ->
                if (i > 0) androidx.compose.material3.HorizontalDivider(color = c.lineDivider)
                Row(
                    Modifier.fillMaxWidth().clickable(role = Role.Button) { company = co.code }.padding(14.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    CompanyMark(co.code, height = 16.dp, ink = c.textPrimary)
                    Text(co.nameFa ?: co.code, style = Divan.type.bodyStrong, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                    DIcon(DivanIcon.CHEVRON, size = 16.dp, tint = c.textMuted)
                }
            }
        }
    } else {
        val name = companyOf(companies, chosen).nameFa
        val deps = rememberQuery("departments:$chosen", "companies", maxAgeMs = 60_000) { departments(chosen) }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            CompanyMark(chosen, height = 16.dp, ink = c.textPrimary)
            Text(name, style = Divan.type.bodyStrong, modifier = Modifier.weight(1f))
            HqButton("شرکت دیگر", { company = null }, variant = BtnVariant.TEXT, size = com.coinepro.hq.designsystem.BtnSize.SM)
        }
        Text("کدام نقش؟", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(c.card)) {
            RoleRow("مدیرعامل $name", "با او درباره‌ی کل شرکت حرف بزن") { onPick("ceo", chosen, null) }
            for (d in deps.data.orEmpty().filter { it.status == "active" }.sortedBy { it.sort }) {
                androidx.compose.material3.HorizontalDivider(color = c.lineDivider)
                RoleRow(d.managerTitleFa.ifBlank { "مدیر ${d.nameFa}" }, d.nameFa) { onPick("manager", chosen, d.code) }
            }
        }
    }
}

@Composable
private fun RoleRow(title: String, sub: String, onClick: () -> Unit) {
    val c = Divan.colors
    Row(
        Modifier.fillMaxWidth().clickable(role = Role.Button, onClick = onClick).padding(14.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Column(Modifier.weight(1f)) {
            Text(title, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(sub, style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        DIcon(DivanIcon.ADD, size = 18.dp, tint = c.goldInk)
    }
}
