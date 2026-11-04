package com.coinepro.hq.ui.v30

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.assetKindFa
import com.coinepro.hq.core.data.costText
import com.coinepro.hq.core.data.lineModeFa
import com.coinepro.hq.core.data.lineModeTone
import com.coinepro.hq.core.data.lineStateFa
import com.coinepro.hq.core.data.lineStateTone
import com.coinepro.hq.core.data.settingLabelFa
import com.coinepro.hq.core.data.stepStateFa
import com.coinepro.hq.core.data.stepStateTone
import com.coinepro.hq.core.net.Line
import com.coinepro.hq.core.net.StepOutput
import com.coinepro.hq.core.net.StepRun
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.Para
import com.coinepro.hq.ui.v29.plain
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

// Contract §30 ⟨1.12⟩: the small pieces the lines' screens share: the pills of a line, and a step's output shown as it deserves (text with
// Md, audio in the player, an image or a film's poster, JSON data as a table).

/** A line's state (روشن · مکث · آماده‌سازی) and mode (خودکار · با مُهر تو). */
@Composable
fun LinePills(line: Line, modifier: Modifier = Modifier) {
    Row(modifier, horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
        Pill(lineStateFa(line.state), lineStateTone(line.state), dot = true)
        Pill(lineModeFa(line.mode), lineModeTone(line.mode), icon = if (line.mode == "auto") DivanIcon.RESUME else DivanIcon.SEAL)
    }
}

/** A step's output: its text, its files and its data, each in its own form. Nothing to show says so in one line. */
@Composable
fun OutputView(o: StepOutput, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        if (o.isEmpty) Text("این مرحله خروجی نداشت.", style = Divan.type.caption, color = c.textMuted)
        o.text?.takeIf { it.isNotBlank() }?.let { t ->
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp)) { Md(t, color = c.textPrimary) }
        }
        for (id in o.allFiles) FileOutput(id)
        if (o.data.isNotEmpty()) DataTable(o.data)
    }
}

/** One file of an output: audio in the player, an image or a film's poster (a film opens full screen), anything else as a chip. */
@Composable
fun FileOutput(id: String) {
    val q = rememberQuery("file-meta:$id", "files", maxAgeMs = 600_000) { fileMeta(id) }
    val f = q.data
    val c = Divan.colors
    when {
        f == null && q.error == null -> Skeleton(Modifier.fillMaxWidth().height(56.dp), radius = 12.dp)
        f == null -> Row(Modifier.clip(RoundedCornerShape(12.dp)).background(c.tile).padding(horizontal = 12.dp, vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
            DIcon(DivanIcon.ATTACH, size = 14.dp, tint = c.textMuted)
            Text("فایل خروجی", style = Divan.type.caption, color = c.textMuted)
        }
        f.mime.startsWith("audio/") || f.kind == "audio" -> com.coinepro.hq.ui.v18.AudioPlayer(f.id, f.name.ifBlank { "صدا" }, compact = true)
        f.mime.startsWith("video/") || f.kind == "video" ->
            com.coinepro.hq.ui.v19.RenderPreview(f, aspectOf(f, "9:16"), f.name.ifBlank { "ویدیو" }, Modifier.width(150.dp))
        f.mime.startsWith("image/") || f.kind == "image" ->
            com.coinepro.hq.ui.v19.RenderPreview(f, aspectOf(f, "1:1"), f.name.ifBlank { "تصویر" }, Modifier.width(200.dp))
        else -> com.coinepro.hq.ui.v19.FileChip(f)
    }
}

private fun aspectOf(f: com.coinepro.hq.core.net.FileRef, fallback: String): String {
    val w = f.width
    val h = f.height
    return if (w != null && h != null && w > 0 && h > 0) "$w:$h" else fallback
}

/** A value of the data as one line of words (a list joined, an object as «کلید: مقدار»). */
fun dataText(e: JsonElement?): String = when (e) {
    null, JsonNull -> "—"
    is JsonPrimitive -> e.contentOrNull ?: "—"
    is JsonArray -> e.joinToString("، ") { dataText(it) }
    is JsonObject -> e.entries.joinToString("، ") { (k, v) -> "${settingLabelFa(k)}: ${dataText(v)}" }
}

/** JSON data of an output as a table: a row per key; a list of objects is a table of its own (a column per key). */
@Composable
fun DataTable(data: JsonObject, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Column(modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(horizontal = 12.dp, vertical = 4.dp)) {
        data.entries.forEachIndexed { i, (k, v) ->
            if (i > 0) HorizontalDivider(color = c.lineDivider)
            val rows = (v as? JsonArray)?.mapNotNull { it as? JsonObject }.orEmpty()
            if (rows.isNotEmpty() && rows.size == (v as JsonArray).size) {
                Column(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(settingLabelFa(k), style = Divan.type.micro, color = c.textMuted)
                    val cols = rows.flatMap { it.keys }.distinct()
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        for (col in cols) Text(settingLabelFa(col), Modifier.weight(1f), style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary, maxLines = 1)
                    }
                    for (r in rows) Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        for (col in cols) Text(plain(dataText(r[col])), Modifier.weight(1f), style = Divan.type.caption, color = c.textPrimary)
                    }
                }
            } else {
                Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.Top) {
                    Text(settingLabelFa(k), Modifier.width(110.dp), style = Divan.type.caption, color = c.textMuted)
                    Text(plain(dataText(v)), Modifier.weight(1f), style = Divan.type.caption, color = c.textPrimary)
                }
            }
        }
    }
}

/** The answer of «آزمایش همین مرحله»: the step's state, its cost and what it produced (or why it did not). */
@Composable
fun StepTestResult(run: StepRun, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Column(modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.softGold).padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("نتیجه‌ی آزمایش", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, modifier = Modifier.weight(1f))
            Pill(stepStateFa(run.state), stepStateTone(run.state), dot = true)
        }
        val cost = costText(run.tokens, run.usdEquiv)
        if (cost.isNotBlank()) Text(plain("هزینه‌ی این آزمایش: $cost"), style = Divan.type.micro, color = c.textMuted)
        run.errorFa?.takeIf { it.isNotBlank() }?.let { Para(it, color = c.negative) }
        if (run.state != "failed") OutputView(run.output)
    }
}

/** A small «برچسب: مقدار» pair for the headers. */
@Composable
fun KeyValue(label: String, value: String, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Row(modifier, horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, style = Divan.type.micro, color = c.textMuted)
        Text(plain(value), style = Divan.type.caption, color = c.textPrimary, maxLines = 1)
    }
}

/** The kinds of a template's steps as small chips in order (the gallery's summary). */
@Composable
fun StepChips(kinds: List<String>, modifier: Modifier = Modifier) {
    val c = Divan.colors
    FlowRow(modifier, horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        kinds.forEach { k ->
            Row(Modifier.clip(RoundedCornerShape(8.dp)).background(c.tile).padding(horizontal = 8.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                DIcon(com.coinepro.hq.core.data.stepKindIcon(k), size = 12.dp, tint = c.textSecondary)
                Text(com.coinepro.hq.core.data.stepKindFa(k), style = Divan.type.micro, color = c.textSecondary, maxLines = 1)
            }
        }
    }
}

/** An asset's kind and title in one line (a run's library lists). */
fun assetLine(kind: String, title: String): String = assetKindFa(kind) + (if (title.isNotBlank()) "، $title" else "")
