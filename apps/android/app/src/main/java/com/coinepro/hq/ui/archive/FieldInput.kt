package com.coinepro.hq.ui.archive

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.net.FieldDef
import com.coinepro.hq.core.net.PartyIn
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import java.util.UUID
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

// One metadata input per field type (§23.2), mirroring apps/web/src/components/v20/field-input.tsx: the editor never offers a shape the
// server would refuse. A type added to the closed list later is a plain line of text until the app learns it.

private val NUM = Regex("^-?\\d+(\\.\\d+)?$")

/** A typed number when it reads as one, the raw text while it is still being typed («4.»), nothing when empty. */
private fun numOrRaw(s: String): JsonElement? {
    val t = s.trim().map { ch -> "۰۱۲۳۴۵۶۷۸۹".indexOf(ch).takeIf { it >= 0 }?.digitToChar() ?: ch }.joinToString("")
    return when {
        t.isEmpty() -> null
        NUM.matches(t) -> JsonPrimitive(t.toBigDecimal())
        else -> JsonPrimitive(t)
    }
}

private fun latinDigits(s: String) = s.map { ch -> "۰۱۲۳۴۵۶۷۸۹".indexOf(ch).takeIf { it >= 0 }?.digitToChar() ?: ch }.joinToString("")

/** The required, active fields a metadata object still misses. */
fun missingRequired(fields: List<FieldDef>, md: Map<String, JsonElement>): List<FieldDef> = fields.filter { it.required && it.status == "active" && emptyValue(md[it.key]) }

/** The server's `metadata.<key>` errors, by field key. */
fun metaErrors(fields: Map<String, String>): Map<String, String> = fields.filterKeys { it.startsWith("metadata.") }.mapKeys { it.key.removePrefix("metadata.") }

/** A party from the registry, or a new one made right here (kind and Persian name; the rest later in settings). */
@Composable
fun PartyPicker(value: String?, onChange: (String?) -> Unit, label: String, m: ArchiveMaps, scope: String?, error: Boolean = false) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    var making by remember { mutableStateOf(false) }
    var kind by remember { mutableStateOf<String?>(null) }
    var name by remember { mutableStateOf("") }
    // One key per party: a retry after a lost answer reuses it, a new party (or a refused one corrected) gets a fresh one.
    var key by remember { mutableStateOf(UUID.randomUUID().toString()) }
    val list = m.parties.filter { it.status == "active" || it.ref == value }
    // The scope's own parties first; a party of another scope is still allowed (a registry office serves every company).
    val sorted = if (scope != null) list.sortedBy { if (scope in it.scopes) 0 else 1 } else list
    val kinds = m.schema?.partyKinds.orEmpty().filter { it.status != "retired" }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Select(value, sorted.map { Opt(it.ref, it.nameFa + (it.nameEn?.let { e -> " ($e)" } ?: "")) }, onChange, label, Modifier.weight(1f), nullable = true, none = "—", error = error)
            HqButton(null, { making = !making }, variant = BtnVariant.GHOST, icon = DivanIcon.ADD, label = "طرف تازه")
        }
        if (making) Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(8.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Select(kind ?: kinds.firstOrNull()?.key, kinds.map { Opt(it.key, it.titleFa) }, { kind = it }, "نوع طرف", Modifier.width(112.dp))
            HqTextField(name, { name = it }, "نام فارسی", Modifier.weight(1f), maxLength = 120)
            HqButton("بساز", {
                action.archive(toasts, onError = { e -> if (e.status != 0) key = UUID.randomUUID().toString(); false }) {
                    val p = env.api.createParty(PartyIn(kind ?: kinds.firstOrNull()?.key ?: "other", name.trim(), null, emptyMap(), listOfNotNull(scope)), key)
                    env.cache.invalidate("archive")
                    onChange(p.ref)
                    key = UUID.randomUUID().toString()
                    making = false
                    name = ""
                    toasts.ok("طرف ${p.ref} به رجیستری اضافه شد.")
                }
            }, size = BtnSize.SM, enabled = name.isNotBlank(), loading = action.busy)
        }
    }
}

/** One metadata input, typed by its field (§23.2). */
@Composable
fun FieldInput(f: FieldDef, value: JsonElement?, onChange: (JsonElement?) -> Unit, m: ArchiveMaps, scope: String?, error: String? = null) {
    val c = Divan.colors
    val companies = rememberCompanies()
    val bad = error != null
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        FieldLabel(f.titleFa, f.required, m.typeFa(f.type), f.sensitive)
        when (f.type) {
            "long_text" -> HqTextField(value.prim.orEmpty(), { onChange(it.takeIf(String::isNotEmpty)?.let(::JsonPrimitive)) }, f.titleFa, Modifier.fillMaxWidth(), singleLine = false, minLines = 3, maxLength = 10_000)
            "number", "percent" -> Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                HqTextField(value.prim.orEmpty(), { onChange(numOrRaw(it)) }, "0", Modifier.weight(1f), maxLength = 24, figure = true)
                if (f.type == "percent") Fig("%", style = Divan.type.figureSmall, color = c.textMuted)
            }
            "money" -> {
                val v = value.obj
                val cur = f.currency ?: v?.get("currency").prim ?: m.vocab.currencies.firstOrNull() ?: "USD"
                val other = v != null && f.currency != null && v["currency"].prim != f.currency
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        HqTextField(v?.get("amount").prim.orEmpty(), { t ->
                            val a = latinDigits(t.trim()).replace(",", "")
                            onChange(if (a.isEmpty()) null else jobj("amount" to JsonPrimitive(a), "currency" to JsonPrimitive(f.currency ?: v?.get("currency").prim ?: cur)))
                        }, "0.00", Modifier.weight(1f), maxLength = 32, figure = true)
                        if (f.currency != null) Fig(f.currency, style = Divan.type.figureSmall, color = c.textSecondary)
                        else Select(cur, m.vocab.currencies.ifEmpty { listOf(cur) }.map { Opt(it, it, figure = true) }, { x -> onChange(jobj("amount" to JsonPrimitive(v?.get("amount").prim.orEmpty()), "currency" to jstr(x))) }, "${f.titleFa}: واحد", Modifier.width(104.dp))
                    }
                    if (other) Text("واحد این مبلغ ${v?.get("currency").prim} است؛ این فیلد ${f.currency} میخواهد. با ویرایش مبلغ، واحد درست میشود.", style = Divan.type.micro, color = c.warning)
                }
            }
            "date" -> DateField(value.prim, { onChange(it?.let(::JsonPrimitive)) }, f.titleFa, error = bad)
            "date_range" -> {
                val r = value.obj
                fun set(k: String, v: String?) {
                    val from = if (k == "from") v else r?.get("from").prim
                    val to = if (k == "to") v else r?.get("to").prim
                    onChange(if (from == null && to == null) null else JsonObject(listOfNotNull(from?.let { "from" to JsonPrimitive(it) }, to?.let { "to" to JsonPrimitive(it) }).toMap()))
                }
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    DateField(r?.get("from").prim, { set("from", it) }, "${f.titleFa}: از", error = bad)
                    Text("تا", style = Divan.type.caption, color = c.textMuted)
                    DateField(r?.get("to").prim, { set("to", it) }, "${f.titleFa}: تا", error = bad)
                }
            }
            "enum" -> Select(value.prim, f.options.map { Opt(it.key, it.titleFa) }, { onChange(it?.let(::JsonPrimitive)) }, f.titleFa, Modifier.fillMaxWidth(), nullable = true, none = "—", error = bad)
            "multi_enum" -> {
                val xs = value.strings()
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    for (o in f.options) FilterChip(o.titleFa, o.key in xs, {
                        val n = if (o.key in xs) xs - o.key else xs + o.key
                        onChange(if (n.isEmpty()) null else jarr(n))
                    })
                }
            }
            "boolean" -> Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                FilterChip("بله", value.bool == true, { onChange(if (value.bool == true) null else JsonPrimitive(true)) })
                FilterChip("نه", value.bool == false, { onChange(if (value.bool == false) null else JsonPrimitive(false)) })
            }
            "party" -> PartyPicker(value.str, { onChange(it?.let(::JsonPrimitive)) }, f.titleFa, m, scope, bad)
            "company" -> Select(value.prim, companies.map { Opt(it.code, it.nameFa ?: it.code) }, { onChange(it?.let(::JsonPrimitive)) }, f.titleFa, Modifier.fillMaxWidth(), nullable = true, none = "—", error = bad)
            "ref" -> {
                val r = value.obj
                val kinds = f.refKinds.ifEmpty { m.vocab.refKinds }
                val kind = r?.get("kind").prim?.takeIf { it in kinds } ?: kinds.firstOrNull() ?: "record"
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    if (kinds.size > 1) Select(kind, kinds.map { Opt(it, REF_KIND_FA[it] ?: it) }, { k -> r?.get("ref").prim?.let { ref -> onChange(jobj("kind" to jstr(k), "ref" to JsonPrimitive(ref))) } }, "${f.titleFa}: نوع", Modifier.width(132.dp))
                    else Text(REF_KIND_FA[kind] ?: kind, style = Divan.type.caption, color = c.textMuted)
                    HqTextField(r?.get("ref").prim.orEmpty(), { t ->
                        onChange(if (t.isBlank()) null else jobj("kind" to JsonPrimitive(kind), "ref" to JsonPrimitive(t.trim().uppercase())))
                    }, when (kind) { "case" -> "LC-0001"; "decision" -> "D-000000"; "record" -> "AR-000000"; else -> "" }, Modifier.weight(1f), maxLength = 40, figure = true)
                }
            }
            "url", "email", "phone", "id_code", "iban" ->
                HqTextField(value.prim.orEmpty(), { onChange(if (it.isBlank()) null else JsonPrimitive(it.trim())) }, when (f.type) { "url" -> "https://"; "email" -> "name@example.com"; "iban" -> "IR00 0000 …"; else -> "" }, Modifier.fillMaxWidth(), maxLength = 200, figure = true)
            else -> HqTextField(value.prim.orEmpty(), { onChange(it.takeIf(String::isNotEmpty)?.let(::JsonPrimitive)) }, f.titleFa, Modifier.fillMaxWidth(), maxLength = 500)
        }
        when {
            error != null -> Text(error, style = Divan.type.caption, color = c.negative)
            !f.helpFa.isNullOrBlank() -> Text(f.helpFa, style = Divan.type.micro, color = c.textMuted)
        }
    }
}
