package com.coinepro.hq

import android.content.Context
import com.coinepro.hq.core.format.HqClock
import java.io.File
import java.net.URI
import java.security.MessageDigest
import java.time.LocalDate
import java.time.ZoneOffset
import java.time.temporal.ChronoUnit
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody

/** Debug builds only: the archive of record (contract §23) as the web's mock-v20.ts serves it, reduced to what a demo needs. The fixtures
 *  hold every record as the hub serves it, the schema whole, the holds, parties and sources; this keeps them and answers every read and
 *  write the mock answers. What the hub does by code is code here too: clearance (the reader is the owner), the SHA-256 of every file and
 *  the manifest of every version, the seal on that manifest, `sealed_record`, legal holds (423), the secret scan at upload, validation of
 *  every schema change against the closed vocabulary with its impact, retire-never-delete, retention and reminders by rule, and
 *  Persian-normalised search (over titles, fields and the files' own text layer). The documents are the web's demo files (assets/demo/archive). */
internal class ArchiveDemo(private val context: Context, private val store: MutableMap<String, Pair<Int, JsonElement>>, private val uploads: Map<String, JsonObject>) {
    private val owner = jo("kind" to "owner", "code" to "owner", "display_fa" to "مدیر کل")
    private val system = jo("kind" to "system", "code" to "system", "display_fa" to "سیستم")

    // ------------------------------------------------------------------ state --
    private val schema: MutableMap<String, JsonElement> = LinkedHashMap(store.getValue("/archive/schema").second.jsonObject)
    /** Each record with only its own links (another record's link to it is computed on the way out). */
    private val records: MutableList<JsonObject> = items("/archive/records").map { r -> JsonObject(r - "at" + ("links" to ja(r.arr("links").filter { !it.bool("inverse") }))) }.toMutableList()
    private val holds: MutableList<JsonObject> = items("/archive/holds").map { JsonObject(it - "records" - "record_refs") }.toMutableList()
    private val sources: MutableList<JsonObject> = items("/archive/sources").toMutableList()
    private val parties: MutableList<JsonObject> = items("/archive/parties").toMutableList()
    private val fixity: JsonElement = store.getValue("/archive/fixity").second
    private val access = mutableMapOf<String, MutableList<JsonObject>>()
    private val keys = mutableMapOf<String, Pair<Int, JsonElement>>()
    private val remindersDone = mutableSetOf<String>()
    private val destroyed = mutableSetOf<String>()
    /** Every file a record holds or the intake read, by id; where its bytes are; and its text (the PDF's own text layer). */
    private val files = LinkedHashMap<String, JsonObject>().apply { for (r in records) for (v in r.arr("versions")) for (f in v.arr("files")) put(f.s("file_id")!!, f) }
    private val paths = mutableMapOf<String, String>()
    private val texts = mutableMapOf<String, String>()

    private fun items(key: String): List<JsonObject> = store[key]?.second?.let { (it as? JsonObject)?.get("items") ?: it }?.jsonArray.orEmpty().map { it.jsonObject }
    private fun stamp() = HqClock.now().toString()
    private fun today(): LocalDate = LocalDate.ofInstant(HqClock.now(), ZoneOffset.UTC)
    private fun daysTo(d: String): Long = runCatching { ChronoUnit.DAYS.between(today(), LocalDate.parse(d.take(10))) }.getOrDefault(0)

    // ------------------------------------------------------------------ the schema --
    private fun part(p: String): List<JsonObject> = (schema[p] as? JsonArray)?.map { it.jsonObject }.orEmpty()
    private fun savePart(p: String, xs: List<JsonObject>) { schema[p] = ja(xs) }
    private fun classOf(k: String?): JsonObject? = k?.let { key -> part("classes").firstOrNull { it.s("key") == key } }
    private fun levelOf(k: String?): JsonObject? = k?.let { key -> part("levels").firstOrNull { it.s("key") == key } }
    private fun rankOf(k: String?): Int = levelOf(k)?.int("rank") ?: 0
    private fun folderOf(r: String?): JsonObject? = r?.let { ref -> part("folders").firstOrNull { it.s("ref") == ref } }
    private fun partyOf(r: String?): JsonObject? = r?.let { ref -> parties.firstOrNull { it.s("ref") == ref } }
    private fun recordOf(ref: String): JsonObject? = records.firstOrNull { it.s("ref") == ref }
    private fun descendants(ref: String): List<String> = listOf(ref) + part("folders").filter { it.s("parent") == ref }.flatMap { descendants(it.s("ref")!!) }
    private fun scopesNow(): List<String> = listOf("HQ") + items("/companies").mapNotNull { it.s("code") }.filter { it != "HQ" }
    private fun keyOf(p: String, x: JsonObject): String? = if (p in REF_PARTS) x.s("ref") else x.s("key")

    private fun schemaView(): JsonObject {
        val out = LinkedHashMap(schema)
        out["classes"] = ja(part("classes").map { it.with("records" to records.count { r -> r.s("class") == it.s("key") && r.s("state") != "disposed" }) })
        out["folders"] = ja(part("folders").map { f -> f.with("records" to records.count { r -> r.s("folder") in descendants(f.s("ref")!!) }) })
        out["levels"] = ja(part("levels").map { l -> l.with("records" to records.count { r -> r.s("level") == l.s("key") }) })
        out["retention"] = ja(part("retention").map { x -> x.with("records" to records.count { r -> classOf(r.s("class"))?.s("retention") == x.s("ref") }) })
        out["party_kinds"] = ja(part("party_kinds").map { k -> k.with("parties" to parties.count { it.s("kind") == k.s("key") }) })
        out["link_kinds"] = ja(part("link_kinds").map { k -> k.with("records" to records.count { r -> r.arr("links").any { it.s("kind") == k.s("key") } }) })
        out["parties"] = ja(parties.map(::partyOut))
        out["sources"] = ja(sources)
        return JsonObject(out)
    }

    private fun partyOut(p: JsonObject) = p.with("records" to records.count { r -> r.arr("parties").any { it.s("party") == p.s("ref") } })

    // ------------------------------------------------------------------ rules by code: dates, holds, retention, reminders --
    private fun dateField(r: JsonObject, key: String): String? {
        val v = r.obj("metadata")[key]
        val s = (v as? JsonPrimitive)?.contentOrNull
        if (s != null && DATE.matches(s)) return s
        return (v as? JsonObject)?.s("to")?.takeIf { DATE.matches(it) }
    }

    private fun docDate(r: JsonObject): String? {
        for (f in classOf(r.s("class"))?.arr("fields").orEmpty()) if (f.s("type") == "date") (r.obj("metadata")[f.s("key")] as? JsonPrimitive)?.contentOrNull?.let { return it }
        return (r.s("filed_at") ?: r.s("created_at"))?.take(10)
    }

    private fun covers(h: JsonObject, r: JsonObject): Boolean {
        val s = h.obj("scope")
        if (r.s("ref") in s.strs("records")) return true
        val facets = listOf("folders", "classes", "parties").count { s.strs(it).isNotEmpty() } + if (s.s("from") != null || s.s("to") != null) 1 else 0
        if (facets == 0) return false
        if (s.strs("folders").isNotEmpty() && r.s("folder") !in s.strs("folders").flatMap(::descendants)) return false
        if (s.strs("classes").isNotEmpty() && r.s("class") !in s.strs("classes")) return false
        if (s.strs("parties").isNotEmpty() && r.arr("parties").none { it.s("party") in s.strs("parties") }) return false
        val d = docDate(r)
        if (s.s("from") != null && (d == null || d < s.s("from")!!)) return false
        if (s.s("to") != null && (d == null || d > s.s("to")!!)) return false
        return true
    }

    private fun holdsOf(r: JsonObject): List<String> = holds.filter { it.s("state") == "active" && covers(it, r) }.mapNotNull { it.s("ref") }

    private class Ret(val rule: String?, val trigger: String?, val due: String?, val then: String?, val disposable: Boolean)

    private fun retentionOf(r: JsonObject): Ret {
        val rule = part("retention").firstOrNull { it.s("ref") == classOf(r.s("class"))?.s("retention") && it.s("status") == "active" } ?: return Ret(null, null, null, null, false)
        val t = rule.s("trigger").orEmpty()
        val trigger = when {
            t == "filed" -> r.s("filed_at")?.take(10)
            t.startsWith("field:") -> dateField(r, t.removePrefix("field:"))
            else -> null // case_closed and superseded wait for their event
        }
        val keep = rule["keep"]
        val due = if ((keep as? JsonPrimitive)?.contentOrNull == "permanent" || trigger == null) null
        else LocalDate.parse(trigger).plusYears((keep as? JsonObject)?.int("years")?.toLong() ?: 0).plusMonths((keep as? JsonObject)?.int("months")?.toLong() ?: 0).toString()
        val ended = due != null && due <= today().toString() && r.s("state") != "draft" && r.s("state") != "disposed"
        return Ret(rule.s("ref"), trigger, due, rule.s("then"), ended && rule.s("then") == "dispose_card" && holdsOf(r).isEmpty())
    }

    private class Rem(val field: String, val at: String, val lead: Int, val state: String, val rule: String?, val id: String, val left: Long)

    private fun remindersOf(r: JsonObject): List<Rem> {
        if (r.s("state") == "draft" || r.s("state") == "disposed") return emptyList()
        return part("reminders").filter { it.s("status") == "active" && it.s("class") == r.s("class") }.mapNotNull { rule ->
            val field = rule.s("field").orEmpty()
            val at = dateField(r, field) ?: return@mapNotNull null
            val left = daysTo(at)
            val leads = rule.items("lead_days").mapNotNull { (it as? JsonPrimitive)?.contentOrNull?.toIntOrNull() }.sortedDescending()
            val reached = leads.filter { left <= it }
            val id = "${r.s("ref")}:$field"
            val state = if (id in remindersDone) "done" else if (reached.isNotEmpty() && left >= -30) "sent" else "pending"
            Rem(field, at, reached.minOrNull() ?: leads.lastOrNull() ?: 0, state, rule.s("ref"), id, left)
        }
    }

    private fun linksOf(r: JsonObject): List<JsonElement> {
        val own = r.arr("links").map { l -> l.with("title_fa" to if (l.obj("to").s("kind") == "record") recordOf(l.obj("to").s("ref").orEmpty())?.s("title_fa") else null) }
        val inverse = records.filter { it !== r }.flatMap { x ->
            x.arr("links").filter { it.obj("to").s("kind") == "record" && it.obj("to").s("ref") == r.s("ref") }.map { l ->
                jo("kind" to l.s("kind"), "to" to jo("kind" to "record", "ref" to x.s("ref")), "at" to l["at"], "by" to l["by"], "sealed" to (l["sealed"] ?: JsonPrimitive(false)), "title_fa" to x.s("title_fa"), "inverse" to true)
            }
        }
        return own + inverse
    }

    private fun recordOut(r: JsonObject): JsonObject {
        val ret = retentionOf(r)
        return JsonObject(r + mapOf(
            "holds" to ja(holdsOf(r).map(::JsonPrimitive)), "links" to ja(linksOf(r)), "doc_date" to (docDate(r)?.let(::JsonPrimitive) ?: JsonNull), "masked" to ja(emptyList()),
            "retention" to jo("rule" to ret.rule, "trigger_at" to ret.trigger, "review_at" to if (ret.then == "review") ret.due else null, "disposable" to ret.disposable),
            "reminders" to ja(remindersOf(r).map { jo("field" to it.field, "at" to it.at, "lead_days" to it.lead, "state" to it.state) }),
        ))
    }

    // ------------------------------------------------------------------ search (§23.9) --
    private fun norm(s: String): String = s.lowercase()
        .replace(Regex("[يى]"), "ی").replace('ك', 'ک').replace('ة', 'ه').replace(Regex("[أإآ]"), "ا").replace('ؤ', 'و')
        .replace(Regex("[\\u064B-\\u0652\\u0670\\u0640]"), "").replace(Regex("[\\u200c\\u200f\\u200e]"), " ")
        .map { ch -> "۰۱۲۳۴۵۶۷۸۹".indexOf(ch).takeIf { it >= 0 }?.digitToChar() ?: "٠١٢٣٤٥٦٧٨٩".indexOf(ch).takeIf { it >= 0 }?.digitToChar() ?: ch }.joinToString("")
        .replace(Regex("\\s+"), " ")

    private fun searchableText(r: JsonObject): String = classOf(r.s("class"))?.arr("fields").orEmpty().filter { it.bool("searchable") || it.s("type") in setOf("party", "text") }.joinToString(" ") { f ->
        val v = r.obj("metadata")[f.s("key")]
        if (f.s("type") == "party") partyOf((v as? JsonPrimitive)?.contentOrNull)?.let { "${it.s("name_fa")} ${it.s("name_en").orEmpty()}" }.orEmpty()
        else (v as? JsonPrimitive)?.contentOrNull.orEmpty()
    }

    private fun fileText(id: String): String = texts.getOrPut(id) {
        val bytes = bytesOf(id) ?: return@getOrPut ""
        val raw = String(bytes, Charsets.ISO_8859_1)
        Regex("\\(((?:\\\\.|[^\\\\)])*)\\)\\s*Tj").findAll(raw).joinToString(" ") { it.groupValues[1].replace("\\(", "(").replace("\\)", ")").replace("\\\\", "\\") }
    }

    private fun recordText(r: JsonObject): String = currentVersion(r)?.arr("files").orEmpty().joinToString(" ") { fileText(it.s("file_id").orEmpty()) }

    private fun scoreOf(r: JsonObject, q: String): Pair<Double, String>? {
        val terms = norm(q).split(' ').filter { it.length >= 2 }
        if (terms.isEmpty()) return null
        val title = norm(r.s("title_fa").orEmpty())
        val fields = searchableText(r)
        val text = recordText(r)
        var score = 0.0
        for (t in terms) {
            val s = (if (t in title) 3 else 0) + (if (t in norm(fields)) 2 else 0) + (if (t in norm(text)) 1 else 0)
            if (s == 0) return null
            score += s
        }
        val t0 = terms.first()
        val src = if (t0 in norm(text)) text else if (t0 in norm(fields)) fields else r.s("title_fa").orEmpty()
        val at = norm(src).indexOf(t0).coerceAtLeast(0)
        val from = maxOf(0, at - 50)
        val end = minOf(src.length, from + 150)
        return score to (if (from > 0) "… " else "") + src.substring(from.coerceAtMost(src.length), end).trim() + if (end < src.length) " …" else ""
    }

    /** Hits for a query: as the hub ranked them when the fixtures were made (with their snippets from the files' text), else ranked here. */
    private fun hits(q: String, pool: List<JsonObject>): List<Triple<JsonObject, Double, String>> {
        val dumped = store["/archive/search?q=${q.trim()}"]?.second?.jsonObject?.arr("items")
        if (dumped != null) return dumped.mapNotNull { h -> pool.firstOrNull { it.s("ref") == h.s("ref") }?.let { Triple(it, h.dbl("score"), h.s("snippet_fa").orEmpty()) } }
        return pool.mapNotNull { r -> scoreOf(r, q)?.let { Triple(r, it.first, it.second) } }.sortedByDescending { it.second }
    }

    // ------------------------------------------------------------------ files --
    private fun bytesOf(id: String): ByteArray? {
        paths[id]?.let { p -> return runCatching { File(p).readBytes() }.getOrNull() }
        val name = files[id]?.s("name")
        if (id.startsWith("arf-") && name != null) return runCatching { context.assets.open("demo/archive/$name").use { it.readBytes() } }.getOrNull()
        if (id.startsWith("file:")) return runCatching { File(URI(id)).readBytes() }.getOrNull()
        return null
    }

    private fun sha256(b: ByteArray): String = MessageDigest.getInstance("SHA-256").digest(b).joinToString("") { "%02x".format(it) }
    private fun manifestOf(ids: List<String>): String = sha256(ids.map { files[it]!! }.map { "${it.s("sha256")}  ${it.s("name")}" }.sorted().joinToString("\n").toByteArray())

    /** A file the owner just uploaded (§17.1): its bytes are read here for the secret scan, the hash and a text layer. */
    private fun intake(id: String): Pair<JsonObject?, String?> {
        files[id]?.let { return it to null }
        val meta = uploads[id] ?: jo("name" to "file", "mime" to "application/octet-stream")
        val bytes = bytesOf(id) ?: ByteArray(0)
        val name = meta.s("name") ?: "file"
        val mime = meta.s("mime") ?: "application/octet-stream"
        val raw = String(bytes.copyOf(minOf(bytes.size, 200_000)), Charsets.UTF_8)
        // Refused before anything is stored or logged: only the file's name comes back.
        if (SECRET.containsMatchIn("$name\n$raw")) return null to name
        val pdf = mime == "application/pdf"
        val textLayer = if (pdf) "/Font" in raw else mime.startsWith("text/")
        val f = jo(
            "file_id" to id, "name" to name, "mime" to mime, "size_bytes" to bytes.size, "sha256" to sha256(bytes),
            "pages" to if (pdf) maxOf(1, Regex("/Type\\s*/Page\\b").findAll(raw).count()) else null,
            "text_state" to if (textLayer) "text_layer" else if (mime.startsWith("image/") || pdf) "ocr" else "none",
            "ocr_confidence" to if (!textLayer && (mime.startsWith("image/") || pdf)) 0.84 else null,
        )
        if (mime.startsWith("text/")) texts[id] = raw.take(4000)
        files[id] = f
        return f to null
    }

    private fun intakeAll(ids: List<String>): Pair<List<JsonObject>?, Pair<Int, JsonElement>?> {
        val out = ArrayList<JsonObject>()
        for (id in ids) {
            val (f, secret) = intake(id)
            if (secret != null) return null to (422 to problem(422, "secret_in_document", "در «$secret» الگوی رمز، کلید خصوصی یا عبارت بازیابی پیدا شد؛ فایل ذخیره نشد.", jo(secret to "secret_pattern")))
            out += f!!
        }
        return out to null
    }

    /** Rules first (§23.9): the class from words in the name and text, dates from the text, known parties from the registry. */
    private fun suggest(fs: List<JsonObject>): JsonElement {
        val all = norm(fs.joinToString(" ") { "${it.s("name")} ${fileText(it.s("file_id").orEmpty())}" })
        val cls = when {
            Regex("invoice|فاکتور|رسید").containsMatchIn(all) -> "invoice"
            Regex("affiliate|افیلیت").containsMatchIn(all) -> "affiliate_agreement"
            Regex("licen[cs]e|مجوز|لایسنس").containsMatchIn(all) -> "license"
            Regex("domain|دامنه").containsMatchIn(all) -> "domain"
            Regex("agreement|contract|قرارداد|اجاره").containsMatchIn(all) -> "contract"
            Regex("ثبت شرکت|آگهی تاسیس").containsMatchIn(all) -> "company_registration"
            else -> null
        }
        val known = parties.filter { p -> norm(p.s("name_fa").orEmpty()) in all || p.s("name_en")?.let { norm(it).split(' ').first() in all } == true }
        val date = Regex("(\\d{4}-\\d{2}-\\d{2})").find(all)?.groupValues?.get(1)
        val md = LinkedHashMap<String, JsonElement>()
        val c = classOf(cls)
        if (c != null && date != null) c.arr("fields").firstOrNull { it.s("type") == "date" }?.let { md[it.s("key")!!] = JsonPrimitive(date) }
        if (c != null && known.isNotEmpty()) c.arr("fields").firstOrNull { it.s("type") == "party" }?.let { md[it.s("key")!!] = JsonPrimitive(known.first().s("ref")) }
        if (cls == null && known.isEmpty()) return JsonNull
        return jo("class" to cls, "title_fa" to null, "metadata" to JsonObject(md), "parties" to ja(known.mapNotNull { it.s("ref") }.map(::JsonPrimitive)), "by" to "rules",
            "note_fa" to if (cls != null) "از واژه‌های نام و متن فایل؛ فقط پیشنهاد است." else "نوع سند از متن پیدا نشد؛ طرف‌های شناخته از رجیستری.")
    }

    // ------------------------------------------------------------------ validation against the class (§23.2) --
    private fun isEmpty(v: JsonElement?): Boolean = v == null || v is JsonNull || (v is JsonPrimitive && v.isString && v.content.isEmpty()) ||
        (v is JsonArray && v.isEmpty()) || (v is JsonObject && v.containsKey("amount") && (v["amount"] as? JsonPrimitive)?.contentOrNull.isNullOrEmpty())

    private fun valueProblem(f: JsonObject, v: JsonElement, scopes: List<String>): String? {
        val s = (v as? JsonPrimitive)?.takeIf { it.isString }?.content
        val n = (v as? JsonPrimitive)?.takeIf { !it.isString }?.contentOrNull?.toDoubleOrNull()
        val o = v as? JsonObject
        return when (f.s("type")) {
            "text" -> if (s != null && s.length <= 500) null else "متن کوتاه (تا ۵۰۰ نویسه)"
            "long_text" -> if (s != null) null else "متن"
            "number" -> if (n != null) null else "عدد"
            "percent" -> if (n != null && n in 0.0..100.0) null else "درصد بین 0 و 100"
            "money" -> if (o != null && Regex("^-?\\d+(\\.\\d{1,8})?$").matches(o.s("amount").orEmpty()) && (f.s("currency") == null || o.s("currency") == f.s("currency"))) null else "مبلغ به ${f.s("currency") ?: "واحد"}"
            "date" -> if (s != null && DATE.matches(s)) null else "تاریخ"
            "date_range" -> if (o != null && DATE.matches(o.s("from").orEmpty()) && DATE.matches(o.s("to").orEmpty()) && o.s("from")!! <= o.s("to")!!) null else "بازه‌ی تاریخ (از ≤ تا)"
            "enum" -> if (f.arr("options").any { it.s("key") == s }) null else "یکی از گزینه‌ها"
            "multi_enum" -> if (v is JsonArray && v.all { x -> f.arr("options").any { it.s("key") == (x as? JsonPrimitive)?.contentOrNull } }) null else "از گزینه‌ها"
            "boolean" -> if (v is JsonPrimitive && !v.isString && v.contentOrNull?.toBooleanStrictOrNull() != null) null else "بله یا نه"
            "party" -> if (partyOf(s) != null) null else "طرفی از رجیستری"
            "company" -> if (s in scopes) null else "شرکتی از هلدینگ"
            "ref" -> if (o != null && o.s("kind") in f.strs("ref_kinds") && !o.s("ref").isNullOrBlank()) null else "ارجاع ${f.strs("ref_kinds").joinToString("/")}"
            "url" -> if (s != null && Regex("^https?://\\S+$").matches(s)) null else "نشانی http یا https"
            "email" -> if (s != null && Regex("^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$").matches(s)) null else "ایمیل"
            "phone" -> if (s != null && Regex("^\\+?[0-9 ()-]{6,20}$").matches(s)) null else "تلفن"
            "id_code" -> if (s != null && Regex("^[A-Za-z0-9-]{3,40}$").matches(s)) null else "شناسه (حرف و عدد لاتین)"
            "iban" -> if (s != null && Regex("^[A-Z]{2}\\d{2}[A-Z0-9]{10,30}$").matches(s.replace(" ", ""))) null else "شبا (IR و ۲۴ رقم)"
            else -> "نوع ناشناخته"
        }
    }

    private fun metadataProblems(fields: List<JsonObject>, md: Map<String, JsonElement>, filing: Boolean): Map<String, String> {
        val out = LinkedHashMap<String, String>()
        for (f in fields) {
            val v = md[f.s("key")]
            if (isEmpty(v)) { if (filing && f.bool("required") && f.s("status") == "active") out["metadata.${f.s("key")}"] = "«${f.s("title_fa")}» لازم است"; continue }
            valueProblem(f, v!!, scopesNow())?.let { out["metadata.${f.s("key")}"] = "«${f.s("title_fa")}»: $it" }
        }
        for (k in md.keys) if (fields.none { it.s("key") == k }) out["metadata.$k"] = "این فیلد در این نوع سند نیست"
        return out
    }

    private fun cleanMeta(md: JsonObject?): JsonObject = JsonObject(md.orEmpty().filterValues { !isEmpty(it) })

    // ------------------------------------------------------------------ automations, rules only (§23.7) --
    private fun runAutomations(on: String, r0: JsonObject): JsonObject {
        var r = r0
        val all = part("automations")
        savePart("automations", all.map { a ->
            if (a.s("status") != "active" || a.s("on") != on) return@map a
            val w = a.obj("when")
            if (w.s("class") != null && w.s("class") != r.s("class")) return@map a
            if (w.s("scope") != null && w.s("scope") != r.s("scope")) return@map a
            if (w.s("level_min") != null && rankOf(r.s("level")) < rankOf(w.s("level_min"))) return@map a
            w["field"]?.let { fe ->
                val fo = fe as? JsonObject ?: return@map a
                val raw = r.obj("metadata")[fo.s("key")]
                val v = (raw as? JsonObject)?.s("amount") ?: (raw as? JsonPrimitive)?.contentOrNull
                val x = (fo["value"] as? JsonPrimitive)?.contentOrNull.orEmpty()
                val ok = when (fo.s("op")) {
                    "eq" -> v == x
                    "lt" -> (v?.toDoubleOrNull() ?: Double.NaN) < (x.toDoubleOrNull() ?: Double.NaN)
                    "gt" -> (v?.toDoubleOrNull() ?: Double.NaN) > (x.toDoubleOrNull() ?: Double.NaN)
                    else -> v.orEmpty().contains(x)
                }
                if (!ok) return@map a
            }
            for (s in a.arr("do")) {
                val args = s.obj("args")
                when (s.s("action")) {
                    "raise_level" -> if (rankOf(args.s("level")) > rankOf(r.s("level"))) r = r.with("level" to args.s("level"))
                    "move_to_folder" -> if (part("folders").any { it.s("ref") == args.s("folder") && it.s("scope") == r.s("scope") }) r = r.with("folder" to args.s("folder"))
                    "link" -> if (args.s("kind") != null && args["to"] is JsonObject) r = r.with("links" to ja(r.arr("links") + jo("kind" to args.s("kind"), "to" to args["to"], "at" to stamp(), "by" to system)))
                }
            }
            a.with("runs_30d" to a.int("runs_30d") + 1, "last_run_at" to stamp())
        })
        return r
    }

    // ------------------------------------------------------------------ schema validation (§23.10) --
    private fun fieldProblems(fs: JsonElement?, prefix: String, before: List<JsonObject>?): Map<String, String> {
        val out = LinkedHashMap<String, String>()
        val list = (fs as? JsonArray)?.mapNotNull { it as? JsonObject } ?: return mapOf(prefix to "فهرست فیلدها لازم است")
        val types = part("field_types").mapNotNull { it.s("key") }
        val refKinds = (schema["vocab"] as? JsonObject)?.strs("ref_kinds").orEmpty()
        val currencies = (schema["vocab"] as? JsonObject)?.strs("currencies").orEmpty()
        val seen = mutableSetOf<String>()
        list.forEachIndexed { i, f ->
            val key = f.s("key").orEmpty()
            val at = "$prefix.${key.ifEmpty { "$i" }}"
            if (!KEY.matches(key)) out["$at.key"] = "کلید فیلد: حروف کوچک لاتین، عدد و _" else if (!seen.add(key)) out["$at.key"] = "کلید «$key» دو بار آمده"
            if (f.s("title_fa").isNullOrBlank()) out["$at.title_fa"] = "عنوان فیلد لازم است"
            val t = f.s("type")
            if (t !in types) out["$at.type"] = "نوع «$t» در واژگان بسته نیست"
            if ((t == "enum" || t == "multi_enum")) {
                val opts = f.arr("options")
                if (opts.none { KEY.matches(it.s("key").orEmpty()) && !it.s("title_fa").isNullOrBlank() }) out["$at.options"] = "«${f.s("title_fa") ?: key}»: گزینه‌ای ندارد"
                else if (opts.map { it.s("key") }.distinct().size != opts.size) out["$at.options"] = "کلید گزینه تکراری است"
            }
            if (t == "ref" && (f.strs("ref_kinds").isEmpty() || f.strs("ref_kinds").any { it !in refKinds })) out["$at.ref_kinds"] = "«${f.s("title_fa") ?: key}»: نوع ارجاع از فهرست بسته لازم است"
            if (t == "money" && f.s("currency") !in currencies) out["$at.currency"] = "«${f.s("title_fa") ?: key}»: واحد پول لازم است"
            if (f.s("status") == "retired" && f.bool("required")) out["$at.required"] = "فیلد بازنشسته اجباری نمیشود"
            val old = before?.firstOrNull { it.s("key") == key }
            if (old != null && old.s("type") != t) out["$at.type"] = "نوع فیلد «${old.s("title_fa")}» بعد از ساخت عوض نمیشود؛ فیلد تازه بساز و این را بازنشسته کن"
        }
        for (old in before.orEmpty()) if (list.none { it.s("key") == old.s("key") }) out["$prefix.${old.s("key")}"] = "فیلد «${old.s("title_fa")}» حذف نمیشود؛ فقط بازنشسته"
        return out
    }

    private fun agentsMax(): Int = part("levels").filter { it.bool("agents_max") && it.s("status") == "active" }.maxOfOrNull { it.int("rank") } ?: 0

    private fun validatePart(p: String, key: String, b: JsonObject, cur: JsonObject?): Map<String, String> {
        val out = LinkedHashMap<String, String>()
        fun lv(k: String?) = part("levels").any { it.s("key") == k }
        val vocab = schema["vocab"] as? JsonObject ?: JsonObject(emptyMap())
        when (p) {
            "classes" -> {
                if (!KEY.matches(key)) out["key"] = "کلید کلاس: حروف کوچک لاتین، عدد و _"
                if (b.s("title_fa").isNullOrBlank()) out["title_fa"] = "عنوان لازم است"
                out += fieldProblems(b["fields"], "fields", cur?.arr("fields"))
                if (!lv(b.s("default_level"))) out["default_level"] = "سطح پیش‌فرض نامعتبر است"
                b.s("default_folder")?.let { if (folderOf(it) == null) out["default_folder"] = "پوشه‌ی پیش‌فرض پیدا نشد" }
                b.s("retention")?.let { r -> if (part("retention").none { it.s("ref") == r }) out["retention"] = "قاعده‌ی نگهداری پیدا نشد" }
                b.s("parent")?.let { if (it == key || classOf(it) == null) out["parent"] = "کلاس والد نامعتبر است" }
                val mimes = b.strs("allowed_mime")
                if (mimes.isEmpty() || mimes.any { it !in vocab.strs("mimes") }) out["allowed_mime"] = "نوع فایل‌های مجاز از فهرست"
                val rf = (b["required_files"] as? JsonPrimitive)?.contentOrNull?.toIntOrNull()
                if (rf == null || rf !in 0..20) out["required_files"] = "تعداد فایل لازم ۰ تا ۲۰"
                for (k in b.strs("reminder_fields")) { val f = b.arr("fields").firstOrNull { it.s("key") == k }; if (f == null || f.s("type") !in setOf("date", "date_range") || f.s("status") == "retired") out["reminder_fields"] = "«$k» فیلد تاریخ فعال نیست" }
                for (al in b.arr("auto_link")) { val f = b.arr("fields").firstOrNull { it.s("key") == al.s("field") }; if (f == null || f.s("type") != "ref" || part("link_kinds").none { it.s("key") == al.s("link_kind") }) out["auto_link"] = "پیوند خودکار فقط از فیلد ارجاع با نوع پیوند موجود" }
                val sc = b["scopes"]
                if (!((sc as? JsonPrimitive)?.contentOrNull == "all" || (sc is JsonArray && sc.isNotEmpty() && sc.all { (it as? JsonPrimitive)?.contentOrNull in scopesNow() }))) out["scopes"] = "دامنه: همه یا فهرستی از شرکت‌ها"
            }
            "folders" -> {
                if (b.s("title_fa").isNullOrBlank()) out["title_fa"] = "عنوان لازم است"
                if (b.s("scope") !in scopesNow()) out["scope"] = "دامنه‌ی پوشه نامعتبر است"
                b.s("parent")?.let { parent -> val pf = folderOf(parent); if (pf == null || pf.s("scope") != b.s("scope")) out["parent"] = "پوشه‌ی والد باید در همین دامنه باشد" else if (cur != null && parent in descendants(cur.s("ref")!!)) out["parent"] = "پوشه زیرمجموعه‌ی خودش نمیشود" }
                if (b.strs("classes").any { classOf(it) == null }) out["classes"] = "کلاس ناشناخته"
                b.s("default_level")?.let { if (!lv(it)) out["default_level"] = "سطح نامعتبر" }
            }
            "levels" -> {
                if (!KEY.matches(key)) out["key"] = "کلید سطح: حروف کوچک لاتین"
                if (b.s("title_fa").isNullOrBlank()) out["title_fa"] = "عنوان لازم است"
                val rank = (b["rank"] as? JsonPrimitive)?.contentOrNull?.toIntOrNull()
                val usedBy = records.count { it.s("level") == key }
                when {
                    rank == null || rank !in 0..1000 -> out["rank"] = "رتبه عدد صحیح ۰ تا ۱۰۰۰"
                    part("levels").any { it.s("key") != key && it.int("rank") == rank } -> out["rank"] = "رتبه‌ی تکراری؛ بین دو سطح، رتبه‌ای میانشان بده"
                    cur != null && cur.int("rank") != rank && usedBy > 0 -> out["rank"] = "رتبه‌ی «${cur.s("title_fa")}» بعد از استفاده عوض نمیشود ($usedBy سند)"
                }
                val ci = (b["color_index"] as? JsonPrimitive)?.contentOrNull?.toIntOrNull()
                if (ci == null || ci !in 0..5) out["color_index"] = "رنگ ۰ تا ۵"
                if (b.bool("agents_max") && b.bool("step_up_to_view")) out["agents_max"] = "سطحی که دیدنش passkey میخواهد سقف ایجنت‌ها نمیشود"
            }
            "clearance" -> {
                if (!Regex("^(role|employee):[\\w*-]+$").matches(key)) out["key"] = "کلید: role:<نقش> یا employee:<کد>"
                b.arr("grants").forEachIndexed { i, g ->
                    if (g.s("scope") !in listOf("own", "all") + scopesNow()) out["grants.$i.scope"] = "دامنه نامعتبر"
                    if (!lv(g.s("level"))) out["grants.$i.level"] = "سطح نامعتبر"
                    else if (rankOf(g.s("level")) > agentsMax()) out["grants.$i.level"] = "هیچ ایجنتی بالاتر از سقف ایجنت‌ها (${part("levels").firstOrNull { it.int("rank") == agentsMax() }?.s("title_fa")}) مجوز نمیگیرد"
                }
                b.s("metadata_level")?.let { if (!lv(it)) out["metadata_level"] = "سطح متادیتا نامعتبر" }
            }
            "retention" -> {
                if (b.s("title_fa").isNullOrBlank()) out["title_fa"] = "عنوان لازم است"
                val t = b.s("trigger").orEmpty()
                if (!(t in setOf("filed", "case_closed", "superseded") || Regex("^field:[a-z][a-z0-9_]*$").matches(t))) out["trigger"] = "آغاز: ثبت، فیلد تاریخ، بسته شدن پرونده یا جایگزینی"
                val k = b["keep"]
                val y = (k as? JsonObject)?.int("years") ?: 0
                val mo = (k as? JsonObject)?.int("months") ?: 0
                if ((k as? JsonPrimitive)?.contentOrNull != "permanent" && (k !is JsonObject || (y <= 0 && mo <= 0) || y > 100 || mo > 11)) out["keep"] = "مدت: سال (تا ۱۰۰) و ماه (تا ۱۱)، یا دائمی"
                if (b.s("then") !in setOf("review", "dispose_card")) out["then"] = "پایان: بازبینی یا کارت امحا"
            }
            "reminders" -> {
                val c = classOf(b.s("class"))
                if (c == null) out["class"] = "کلاس پیدا نشد"
                else { val f = c.arr("fields").firstOrNull { it.s("key") == b.s("field") }; if (f == null || f.s("type") !in setOf("date", "date_range") || f.s("status") == "retired") out["field"] = "فیلد تاریخ فعالِ همین کلاس" }
                val lead = b.items("lead_days").mapNotNull { (it as? JsonPrimitive)?.contentOrNull?.toIntOrNull() }
                if (lead.isEmpty() || lead.size != b.items("lead_days").size || lead.any { it !in 1..365 } || lead.distinct().size != lead.size) out["lead_days"] = "روزهای پیش از موعد: عدد ۱ تا ۳۶۵، بی‌تکرار"
                val to = b["to"]
                if (!((to as? JsonPrimitive)?.contentOrNull == "owner" || !(to as? JsonObject)?.s("role").isNullOrBlank() || (to as? JsonObject)?.bool("company_ceo") == true)) out["to"] = "گیرنده: مدیر کل، یک نقش یا مدیرعامل شرکت"
                if (b.s("channel") !in setOf("cartable", "digest")) out["channel"] = "کانال: کارتابل یا خلاصه"
            }
            "party_kinds" -> {
                if (!KEY.matches(key)) out["key"] = "کلید: حروف کوچک لاتین"
                if (b.s("title_fa").isNullOrBlank()) out["title_fa"] = "عنوان لازم است"
                out += fieldProblems(b["identifier_fields"], "identifier_fields", cur?.arr("identifier_fields"))
            }
            "link_kinds" -> {
                if (!KEY.matches(key)) out["key"] = "کلید: حروف کوچک لاتین"
                if (b.s("title_fa").isNullOrBlank()) out["title_fa"] = "عنوان لازم است"
                if (b.s("inverse_fa").isNullOrBlank()) out["inverse_fa"] = "عنوان سوی دیگر لازم است"
                if (b.strs("to_kinds").isEmpty() || b.strs("to_kinds").any { it !in vocab.strs("ref_kinds") }) out["to_kinds"] = "به چه چیزهایی: از فهرست بسته"
            }
            "automations" -> {
                if (b.s("title_fa").isNullOrBlank()) out["title_fa"] = "عنوان لازم است"
                if (b.s("on") !in vocab.strs("events")) out["on"] = "رویداد «${b.s("on")}» در واژگان بسته نیست"
                val w = b.obj("when")
                w.s("class")?.let { if (classOf(it) == null) out["when.class"] = "کلاس ناشناخته" }
                w.s("scope")?.let { if (it !in scopesNow()) out["when.scope"] = "دامنه ناشناخته" }
                w.s("level_min")?.let { if (!lv(it)) out["when.level_min"] = "سطح ناشناخته" }
                (w["field"] as? JsonObject)?.let { if (it.s("key").isNullOrBlank() || it.s("op") !in vocab.strs("ops")) out["when.field"] = "شرط فیلد: کلید و یکی از eq، lt، gt، contains" }
                if (b.arr("do").isEmpty()) out["do"] = "دست‌کم یک اقدام"
                b.arr("do").forEachIndexed { i, s ->
                    val a = s.obj("args")
                    when {
                        s.s("action") !in vocab.strs("actions") -> out["do.$i.action"] = "اقدام «${s.s("action")}» در واژگان بسته نیست"
                        s.s("action") == "notify" && a.s("level") !in setOf("info", "report", "decision") -> out["do.$i.level"] = "اعلان: اطلاع، گزارش یا تصمیم؛ هرگز فوری"
                        s.s("action") == "work_item" && (a.s("role").isNullOrBlank() || Regex("[@\\s]").containsMatchIn(a.s("role").orEmpty())) -> out["do.$i.role"] = "کار فقط برای یک نقش هاب، نه یک شخص"
                        s.s("action") == "link" && (part("link_kinds").none { it.s("key") == a.s("kind") } || a.obj("to").s("ref").isNullOrBlank()) -> out["do.$i.args"] = "پیوند: نوع و مقصد"
                        s.s("action") == "move_to_folder" && folderOf(a.s("folder")) == null -> out["do.$i.folder"] = "پوشه پیدا نشد"
                        s.s("action") == "raise_level" && !lv(a.s("level")) -> out["do.$i.level"] = "سطح ناشناخته"
                        s.s("action") == "add_reminder" && (a.s("field").isNullOrBlank() || a.items("lead_days").isEmpty()) -> out["do.$i.args"] = "یادآور: فیلد و روزها"
                    }
                }
            }
        }
        return out
    }

    private fun impactOf(p: String, key: String, b: JsonObject): JsonObject {
        val n: Int
        var missing = 0
        when (p) {
            "classes" -> {
                val rs = records.filter { it.s("class") == key && it.s("state") != "disposed" && it.s("state") != "draft" }
                val req = b.arr("fields").filter { it.bool("required") && it.s("status") != "retired" }
                n = rs.size
                missing = rs.count { r -> req.any { isEmpty(r.obj("metadata")[it.s("key")]) } }
            }
            "clearance" -> n = records.count { r -> b.arr("grants").any { g -> (g.s("scope") in setOf("all", "own", r.s("scope"))) && rankOf(r.s("level")) <= rankOf(g.s("level")) } }
            "automations" -> n = records.count { r -> (b.obj("when").s("class") == null || r.s("class") == b.obj("when").s("class")) && (b.obj("when").s("scope") == null || r.s("scope") == b.obj("when").s("scope")) }
            "reminders" -> n = records.count { it.s("class") == b.s("class") && dateField(it, b.s("field").orEmpty()) != null }
            "folders" -> n = records.count { it.s("folder") in descendants(key) }
            "levels" -> n = records.count { it.s("level") == key }
            "retention" -> n = records.count { classOf(it.s("class"))?.s("retention") == key }
            "party_kinds" -> n = records.count { r -> r.arr("parties").any { partyOf(it.s("party"))?.s("kind") == key } }
            "link_kinds" -> n = records.count { r -> r.arr("links").any { it.s("kind") == key } }
            else -> n = 0
        }
        return jo("records" to n, "missing_required" to missing)
    }

    private fun nextRef(p: String): String {
        val prefix = PREFIX.getValue(p)
        return "%s-%04d".format(prefix, (part(p).mapNotNull { it.s("ref")?.substringAfter('-')?.toIntOrNull() }.maxOrNull() ?: 0) + 1)
    }

    private fun clearanceRows(key: String) = part("clearance").filter { "${it.obj("subject").s("kind")}:${it.obj("subject").s("ref")}" == key }

    private fun applyPut(p: String, key: String, b: JsonObject): JsonObject {
        if (p == "clearance") {
            val kind = key.substringBefore(':')
            val ref = key.substringAfter(':')
            val v = (clearanceRows(key).firstOrNull()?.int("version") ?: 0) + 1
            val rest = part("clearance").filter { "${it.obj("subject").s("kind")}:${it.obj("subject").s("ref")}" != key }
            savePart("clearance", rest + b.arr("grants").map { g -> jo("subject" to jo("kind" to kind, "ref" to ref), "scope" to g["scope"], "level" to g["level"], "metadata_level" to b["metadata_level"], "version" to v) })
            return jo("subject" to jo("kind" to kind, "ref" to ref), "grants" to b["grants"], "metadata_level" to b["metadata_level"], "version" to v)
        }
        val list = part(p)
        val realKey = if (key == "new") nextRef(p) else key
        val cur = list.firstOrNull { keyOf(p, it) == realKey }
        var row = JsonObject((cur ?: jo("status" to "active")) + b + mapOf((if (p in REF_PARTS) "ref" else "key") to JsonPrimitive(realKey), "version" to JsonPrimitive((cur?.int("version") ?: 0) + 1)))
        if (p == "classes") row = row.with("fields" to ja(b.arr("fields").map { f -> JsonObject(jo("required" to false, "searchable" to false, "sensitive" to false, "help_fa" to null, "status" to "active") + f) }))
        if (p == "folders" && cur == null) row = row.with("order" to list.size)
        savePart(p, if (cur != null) list.map { if (keyOf(p, it) == realKey) row else it } else list + row)
        return row
    }

    // ------------------------------------------------------------------ the routes --
    /** The §23 routes (and the approval of the two §23 cards); null when the request is not one of them. */
    fun handle(req: Request, path: String, raw: JsonElement?, q: Map<String, String?>): Response? {
        val m = req.method
        Regex("^/decisions/(D-\\d+)/approve$").find(path)?.let { mm -> return approveCheck(req, mm.groupValues[1])?.let { respond(req, it) } }
        if (!path.startsWith("/archive/")) return null
        if (m == "GET") {
            Regex("^/archive/records/(AR-\\d+)/files/([^/]+)$").find(path)?.let { mm -> return file(req, mm.groupValues[1], mm.groupValues[2]) }
            return respond(req, read(path, q))
        }
        return respond(req, write(req, m, path, raw as? JsonObject ?: JsonObject(emptyMap()), q) ?: (404 to problem(404, "not_found", "پیدا نشد.")))
    }

    private fun read(path: String, q: Map<String, String?>): Pair<Int, JsonElement> {
        when (path) {
            "/archive/schema" -> return 200 to schemaView()
            "/archive/sources" -> return 200 to ja(sources)
            "/archive/fixity" -> return 200 to fixity
            "/archive/records" -> {
                var xs = records.filter { it.s("state") != "disposed" || q["state"] == "disposed" }
                q["scope"]?.let { s -> xs = xs.filter { it.s("scope") == s } }
                q["class"]?.let { s -> xs = xs.filter { it.s("class") == s } }
                q["folder"]?.let { s -> val d = descendants(s); xs = xs.filter { it.s("folder") in d } }
                q["level"]?.let { s -> xs = xs.filter { it.s("level") == s } }
                q["state"]?.let { s -> xs = xs.filter { it.s("state") == s } }
                q["party"]?.let { s -> xs = xs.filter { r -> r.arr("parties").any { it.s("party") == s } } }
                q["from"]?.let { s -> xs = xs.filter { (docDate(it) ?: "") >= s } }
                q["to"]?.let { s -> xs = xs.filter { (docDate(it) ?: "") <= s } }
                q["expiring_within_days"]?.toLongOrNull()?.let { n -> xs = xs.filter { r -> remindersOf(r).any { it.state != "done" && it.left <= n && it.left >= -30 } } }
                if (q["held"] == "true") xs = xs.filter { holdsOf(it).isNotEmpty() }
                val text = q["q"]?.trim().orEmpty()
                if (text.isNotEmpty()) return 200 to page(hits(text, xs).map { recordOut(it.first) })
                return 200 to page(xs.sortedByDescending { it.s("filed_at") ?: it.s("created_at") }.map(::recordOut))
            }
            "/archive/search" -> {
                var xs = records.filter { it.s("state") != "disposed" }
                q["scope"]?.let { s -> xs = xs.filter { it.s("scope") == s } }
                q["class"]?.let { s -> xs = xs.filter { it.s("class") == s } }
                q["level"]?.let { s -> xs = xs.filter { it.s("level") == s } }
                q["from"]?.let { s -> xs = xs.filter { (docDate(it) ?: "") >= s } }
                q["to"]?.let { s -> xs = xs.filter { (docDate(it) ?: "") <= s } }
                return 200 to page(hits(q["q"].orEmpty(), xs).map { (r, score, snippet) -> jo("ref" to r.s("ref"), "title_fa" to r.s("title_fa"), "class" to r.s("class"), "snippet_fa" to snippet, "score" to score) })
            }
            "/archive/parties" -> {
                val t = norm(q["q"].orEmpty())
                return 200 to page(parties.filter { p -> (q["kind"] == null || p.s("kind") == q["kind"]) && (q["scope"] == null || q["scope"] in p.strs("scopes")) && (t.isEmpty() || t in norm("${p.s("name_fa")} ${p.s("name_en").orEmpty()}")) }.map(::partyOut))
            }
            "/archive/holds" -> return 200 to page(holds.filter { h -> (q["state"] == null || h.s("state") == q["state"]) && (q["case"] == null || h.s("case") == q["case"]) }.map(::holdOut))
            "/archive/reminders" -> {
                val out = records.flatMap { r ->
                    remindersOf(r).filter { it.state == "sent" || (it.state == "done" && it.left in -30..90) }.map { x ->
                        val rule = part("reminders").firstOrNull { it.s("ref") == x.rule }
                        jo("id" to x.id, "record" to r.s("ref"), "title_fa" to r.s("title_fa"), "scope" to r.s("scope"), "class" to r.s("class"), "field" to x.field, "at" to x.at, "lead_days" to x.lead,
                            "days_left" to x.left, "state" to x.state, "rule" to x.rule, "to" to (rule?.get("to") ?: JsonPrimitive("owner")), "channel" to (rule?.s("channel") ?: "cartable"))
                    }
                }
                return 200 to page(out.sortedBy { it.int("days_left") })
            }
            "/archive/retention/due" -> {
                val disposal = decisions().firstOrNull { it.s("kind") == "archive_disposal" && it.s("status") == "pending" }
                val out = records.filter { it.s("state") != "disposed" }.mapNotNull { r ->
                    val x = retentionOf(r)
                    if (x.due == null || x.due > today().toString()) return@mapNotNull null
                    jo("ref" to r.s("ref"), "title_fa" to r.s("title_fa"), "scope" to r.s("scope"), "class" to r.s("class"), "rule" to x.rule, "trigger_at" to x.trigger, "due_at" to x.due, "then" to x.then,
                        "holds" to ja(holdsOf(r).map(::JsonPrimitive)), "decision_ref" to if (disposal?.obj("payload")?.arr("records")?.any { it.s("ref") == r.s("ref") } == true) disposal.s("ref") else null)
                }
                return 200 to page(out)
            }
        }
        Regex("^/archive/records/(AR-\\d+)/access$").find(path)?.let { mm ->
            if (recordOf(mm.groupValues[1]) == null) return 404 to problem(404, "not_found", "این سند پیدا نشد.")
            return 200 to page(access[mm.groupValues[1]].orEmpty())
        }
        Regex("^/archive/records/(AR-\\d+)$").find(path)?.let { mm ->
            return recordOf(mm.groupValues[1])?.let { 200 to recordOut(it) } ?: (404 to problem(404, "not_found", "این سند پیدا نشد."))
        }
        return 404 to problem(404, "not_found", "پیدا نشد.")
    }

    private fun holdOut(h: JsonObject): JsonObject {
        val rs = if (h.s("state") == "active") records.filter { covers(h, it) } else emptyList()
        return h.with("records" to rs.size, "record_refs" to ja(rs.mapNotNull { it.s("ref") }.map(::JsonPrimitive)))
    }

    private fun file(req: Request, ref: String, id0: String): Response {
        val id = java.net.URLDecoder.decode(id0, "UTF-8")
        val r = recordOf(ref) ?: return respond(req, 404 to problem(404, "not_found", "این سند پیدا نشد."))
        val v = r.arr("versions").firstOrNull { vv -> vv.arr("files").any { it.s("file_id") == id } } ?: return respond(req, 404 to problem(404, "not_found", "این فایل در این سند نیست."))
        val lvl = levelOf(r.s("level"))
        if (lvl?.bool("step_up_to_view") == true && req.header("X-Step-Up") == null) return respond(req, 403 to problem(403, "step_up_required", "دیدن سند این سطح تأیید با اثر انگشت یا چهره میخواهد."))
        if (id in destroyed) return respond(req, 404 to problem(404, "not_found", "این فایل با کارت امحا نابود شده؛ فقط سنگ‌نشانش مانده."))
        val bytes = bytesOf(id) ?: return respond(req, 404 to problem(404, "not_found", "پیدا نشد."))
        access.getOrPut(ref) { mutableListOf() }.add(0, jo("at" to stamp(), "actor" to owner, "action" to "view", "file_id" to id, "version" to v.int("n"),
            "step_up" to (lvl?.bool("step_up_to_view") == true), "watermarked" to (lvl?.bool("watermark") == true)))
        val mime = files[id]?.s("mime") ?: "application/octet-stream"
        return Response.Builder().request(req).protocol(Protocol.HTTP_1_1).code(200).message("demo").body(bytes.toResponseBody(mime.toMediaType())).build()
    }

    private fun currentVersion(r: JsonObject): JsonObject? = r.arr("versions").firstOrNull { it.int("n") == r.int("current_version") } ?: r.arr("versions").lastOrNull()

    private fun versionCheck(req: Request, version: Int?): Pair<Int, JsonElement>? {
        val mm = req.header("If-Match")?.trim('"')
        val none = req.header("If-None-Match")
        if (version == null) return if (mm != null && mm != "0") 409 to problem(409, "version_conflict", "این کلید هنوز وجود ندارد؛ صفحه را تازه کن.") else null
        if (none == "*") return 409 to problem(409, "version_conflict", "این کلید از قبل هست؛ کلید دیگری انتخاب کن.")
        if (mm == null) return 428 to problem(428, "precondition_required", "نسخه همراه درخواست نیامد.")
        if (mm != version.toString()) return 409 to problem(409, "version_conflict", "همین حالا عوض شده؛ دوباره نگاه کن.")
        return null
    }

    private fun stepUpMissing(req: Request): Pair<Int, JsonElement>? = if (req.header("X-Step-Up") == null) 403 to problem(403, "step_up_required", "این کار تأیید با اثر انگشت یا چهره میخواهد.") else null
    private fun bad(fa: String, fields: JsonObject = JsonObject(emptyMap()), status: Int = 422, code: String = "validation_failed") = status to problem(status, code, fa, fields)
    private fun saveRecord(r: JsonObject) { val i = records.indexOfFirst { it.s("ref") == r.s("ref") }; if (i >= 0) records[i] = r else records.add(0, r) }
    private fun nextRecordRef(): String = "AR-%06d".format((records.mapNotNull { it.s("ref")?.substringAfter('-')?.toIntOrNull() }.maxOrNull() ?: 0) + 1)

    private fun write(req: Request, m: String, path: String, b: JsonObject, q: Map<String, String?>): Pair<Int, JsonElement>? {
        val idem = req.header("Idempotency-Key")
        if (path == "/archive/intake" && m == "POST") {
            val ids = b.strs("file_ids")
            if (ids.isEmpty()) return bad("فایلی نیامد.", jo("file_ids" to "required"))
            val (fs, refused) = intakeAll(ids)
            if (refused != null) return refused
            return 200 to jo("files" to ja(fs!!), "suggestion" to suggest(fs))
        }
        if (path == "/archive/records" && m == "POST") {
            if (idem == null) return bad("Idempotency-Key لازم است.", status = 400)
            keys[idem]?.let { return it }
            val c = classOf(b.s("class"))
            val scope = b.s("scope")
            if (scope !in scopesNow()) return bad("دامنه‌ی سند نامعتبر است.", jo("scope" to "unknown"))
            if (c == null || c.s("status") != "active") return bad("نوع سند پیدا نشد یا بازنشسته است.", jo("class" to "unknown"))
            if (b.s("title_fa").isNullOrBlank()) return bad("عنوان لازم است.", jo("title_fa" to "required"))
            val level = b.s("level") ?: c.s("default_level")
            if (levelOf(level)?.s("status") != "active") return bad("سطح نامعتبر است.", jo("level" to "unknown"))
            b.s("folder")?.let { f -> if (folderOf(f)?.s("scope") != scope) return bad("پوشه باید در همین دامنه باشد.", jo("folder" to "scope")) }
            val md = cleanMeta(b.obj("metadata"))
            val filing = b.bool("file")
            metadataProblems(c.arr("fields"), md, filing).takeIf { it.isNotEmpty() }?.let { return bad(it.values.first(), JsonObject(it.mapValues { e -> JsonPrimitive(e.value) })) }
            val ids = b.strs("file_ids")
            if (filing && ids.size < c.int("required_files")) return bad("این نوع سند دست‌کم ${c.int("required_files")} فایل میخواهد.", jo("file_ids" to "required"))
            val (fs, refused) = intakeAll(ids)
            if (refused != null) return refused
            fs!!.firstOrNull { it.s("mime") !in c.strs("allowed_mime") }?.let { return bad("نوع فایل «${it.s("name")}» برای ${c.s("title_fa")} مجاز نیست.", jo("file_ids" to it.s("mime"))) }
            for (pt in b.arr("parties")) if (partyOf(pt.s("party")) == null) return bad("طرف پیدا نشد.", jo("parties" to pt.s("party")))
            val ref = nextRecordRef()
            var links = b.arr("links").map { it.with("at" to stamp(), "by" to owner) }
            for (al in c.arr("auto_link")) (md[al.s("field")] as? JsonObject)?.let { v -> if (v.s("ref") != null && links.none { it.obj("to").s("ref") == v.s("ref") }) links = links + jo("kind" to al.s("link_kind"), "to" to jo("kind" to v.s("kind"), "ref" to v.s("ref")), "at" to stamp(), "by" to system) }
            var r = jo(
                "id" to "ar-$ref", "ref" to ref, "scope" to scope, "class" to c.s("key"), "class_version" to c.int("version"), "title_fa" to b.s("title_fa")!!.trim(), "folder" to b.s("folder"),
                "level" to level, "state" to if (filing) "filed" else "draft", "metadata" to md, "parties" to ja(b.arr("parties")), "links" to ja(links), "current_version" to 1,
                "versions" to ja(listOf(jo("n" to 1, "files" to ja(fs), "manifest_sha256" to manifestOf(fs.mapNotNull { it.s("file_id") }), "note_fa" to null, "created_by" to owner, "created_at" to stamp(), "sealed" to false, "state" to "current"))),
                "source" to jo("kind" to "owner", "ref" to null), "created_by" to owner, "created_at" to stamp(), "filed_at" to if (filing) stamp() else null, "sealed_at" to null, "version" to 1, "suggestion" to null,
            )
            if (filing) r = runAutomations("filed", r)
            saveRecord(r)
            return (201 to (recordOut(r) as JsonElement)).also { keys[idem] = it }
        }
        if (path == "/archive/import" && m == "POST") {
            val scope = b.s("scope")
            if (scope == null || scope !in scopesNow()) return bad("دامنه لازم است.", jo("scope" to "required"))
            val ids = b.strs("file_ids")
            if (ids.isEmpty()) return bad("فایلی نیامد.", jo("file_ids" to "required"))
            val (fs, refused) = intakeAll(ids)
            if (refused != null) return refused
            val out = fs!!.map { f ->
                val ref = nextRecordRef()
                val r = jo(
                    "id" to "ar-$ref", "ref" to ref, "scope" to scope, "class" to b.s("class"), "class_version" to null, "title_fa" to "ورود: ${f.s("name")}", "folder" to null, "level" to "internal", "state" to "draft",
                    "metadata" to JsonObject(emptyMap()), "parties" to ja(emptyList()), "links" to ja(emptyList()), "current_version" to 1,
                    "versions" to ja(listOf(jo("n" to 1, "files" to ja(listOf(f)), "manifest_sha256" to manifestOf(listOf(f.s("file_id")!!)), "note_fa" to "ورود دسته‌ای مالک", "created_by" to owner, "created_at" to stamp(), "sealed" to false, "state" to "current"))),
                    "source" to jo("kind" to "owner", "ref" to null), "created_by" to owner, "created_at" to stamp(), "filed_at" to null, "sealed_at" to null, "version" to 1, "suggestion" to suggest(listOf(f)),
                )
                saveRecord(r)
                recordOut(r)
            }
            return 201 to page(out)
        }
        Regex("^/archive/records/(AR-\\d+)(?:/(versions|seal|links|file))?$").find(path)?.let { mm ->
            val r = recordOf(mm.groupValues[1]) ?: return 404 to problem(404, "not_found", "این سند پیدا نشد.")
            if (r.s("state") == "disposed") return bad("این سند امحا شده؛ فقط سنگ‌نشانش مانده.", status = 409)
            val held = holdsOf(r)
            val ver = r.int("version")
            when (mm.groupValues[2]) {
                "" -> {
                    if (m != "PATCH") return null
                    versionCheck(req, ver)?.let { return it }
                    if (held.isNotEmpty()) return 423 to problem(423, "held", "توقیف ${held.joinToString("، ")}: جز نسخه‌ی تازه هیچ تغییری پذیرفته نمیشود.")
                    // §23.1 ⟨1.7.1⟩: the level is access metadata outside the sealed manifest, so a sealed record takes a PATCH whose only field is level.
                    if (r.s("state") == "sealed" && b.keys.any { it != "level" }) return 409 to problem(409, "sealed_record", "این سند مُهر خورده؛ اصلاح یعنی نسخه‌ی تازه. فقط سطحش عوض میشود.")
                    var cls = classOf(r.s("class"))
                    if (b.containsKey("class") && b.s("class") != r.s("class")) {
                        if (r.s("state") != "draft") return bad("نوع سند ثبت‌شده عوض نمیشود؛ سند تازه بساز و این را با «جایگزین میکند» پیوند بده.", jo("class" to "filed"), status = 409)
                        cls = classOf(b.s("class"))
                        if (cls == null || cls.s("status") != "active") return bad("نوع سند پیدا نشد یا بازنشسته است.", jo("class" to "unknown"))
                    }
                    val level = b.s("level")
                    if (level != null && rankOf(level) < rankOf(r.s("level")) && req.header("X-Step-Up") == null) return 403 to problem(403, "step_up_required", "پایین آوردن سطح فقط با اثر انگشت مدیر کل است.")
                    if (level != null && levelOf(level) == null) return bad("سطح نامعتبر است.", jo("level" to "unknown"))
                    b.s("folder")?.let { f -> if (folderOf(f)?.s("scope") != r.s("scope")) return bad("پوشه باید در همین دامنه باشد.", jo("folder" to "scope")) }
                    var next = r
                    if (b.containsKey("metadata") && cls != null) {
                        val md = cleanMeta(b.obj("metadata"))
                        metadataProblems(cls.arr("fields"), md, r.s("state") != "draft").takeIf { it.isNotEmpty() }?.let { return bad(it.values.first(), JsonObject(it.mapValues { e -> JsonPrimitive(e.value) })) }
                        next = next.with("metadata" to md)
                    }
                    if (cls != null && cls.s("key") != r.s("class")) next = next.with("class" to cls.s("key"), "class_version" to cls.int("version"))
                    // A level change is a row of the record's access log (action `level`, with the two levels).
                    if (level != null && level != r.s("level")) access.getOrPut(r.s("ref")!!) { mutableListOf() }.add(0, jo("at" to stamp(), "actor" to owner, "action" to "level", "file_id" to null, "version" to r.int("current_version"),
                        "step_up" to (rankOf(level) < rankOf(r.s("level"))), "watermarked" to false, "level_from" to r.s("level"), "level_to" to level))
                    for (k in listOf("title_fa", "folder", "parties", "level")) if (b.containsKey(k)) next = next.with(k to b[k])
                    next = next.with("version" to ver + 1)
                    saveRecord(next)
                    return 200 to recordOut(next)
                }
                "file" -> {
                    versionCheck(req, ver)?.let { return it }
                    if (r.s("state") != "draft") return bad("فقط پیش‌نویس ثبت میشود.", status = 409)
                    val c = classOf(r.s("class")) ?: return bad("نوع سند هنوز انتخاب نشده.", jo("class" to "required"))
                    metadataProblems(c.arr("fields"), r.obj("metadata"), true).takeIf { it.isNotEmpty() }?.let { return bad(it.values.first(), JsonObject(it.mapValues { e -> JsonPrimitive(e.value) })) }
                    val next = runAutomations("filed", r.with("state" to "filed", "filed_at" to stamp(), "version" to ver + 1, "suggestion" to null))
                    saveRecord(next)
                    return 200 to recordOut(next)
                }
                "versions" -> {
                    // A new version is the one change a held record accepts.
                    val ids = b.strs("file_ids")
                    if (ids.isEmpty()) return bad("فایل نسخه‌ی تازه لازم است.", jo("file_ids" to "required"))
                    val (fs, refused) = intakeAll(ids)
                    if (refused != null) return refused
                    val c = classOf(r.s("class"))
                    fs!!.firstOrNull { c != null && it.s("mime") !in c.strs("allowed_mime") }?.let { return bad("نوع فایل «${it.s("name")}» برای ${c?.s("title_fa")} مجاز نیست.", jo("file_ids" to it.s("mime"))) }
                    val n = r.arr("versions").size + 1
                    val vs = r.arr("versions").map { it.with("state" to "superseded") } + jo("n" to n, "files" to ja(fs), "manifest_sha256" to manifestOf(fs.mapNotNull { it.s("file_id") }),
                        "note_fa" to b.s("note_fa")?.trim()?.ifEmpty { null }, "created_by" to owner, "created_at" to stamp(), "sealed" to false, "state" to "current")
                    var next = r.with("versions" to ja(vs), "current_version" to n, "version" to ver + 1)
                    if (r.s("state") == "sealed") next = next.with("state" to "filed")
                    next = runAutomations("version_added", next)
                    saveRecord(next)
                    return 201 to recordOut(next)
                }
                "seal" -> {
                    stepUpMissing(req)?.let { return it }
                    if (held.isNotEmpty()) return 423 to problem(423, "held", "توقیف ${held.joinToString("، ")}: تا آزاد شدن، مُهر هم تغییر حساب میشود.")
                    if (r.s("state") == "sealed") return 409 to problem(409, "sealed_record", "همین نسخه مُهر خورده است.")
                    if (r.s("state") == "draft") return bad("پیش‌نویس مُهر نمیشود؛ اول ثبتش کن.", status = 409)
                    val cur = currentVersion(r)!!
                    val again = manifestOf(cur.arr("files").mapNotNull { it.s("file_id") })
                    if (again != cur.s("manifest_sha256") || (b.s("manifest_sha256") != null && b.s("manifest_sha256") != again)) return 409 to problem(409, "version_conflict", "فهرست فایل‌ها بعد از دیدن تو عوض شده؛ مُهر روی manifest تازه است. دوباره نگاه کن.")
                    var next = r.with(
                        "versions" to ja(r.arr("versions").map { if (it.int("n") == cur.int("n")) it.with("sealed" to true) else it }),
                        "links" to ja(r.arr("links").map { it.with("sealed" to true) }), "state" to "sealed", "sealed_at" to stamp(), "version" to ver + 1,
                    )
                    next = runAutomations("sealed", next)
                    saveRecord(next)
                    return 200 to recordOut(next)
                }
                else -> {
                    if (held.isNotEmpty()) return 423 to problem(423, "held", "توقیف ${held.joinToString("، ")}: پیوندها هم تا آزاد شدن دست نمیخورند.")
                    val links = r.arr("links")
                    val next = if (m == "POST") {
                        val lk = part("link_kinds").firstOrNull { it.s("key") == b.s("kind") && it.s("status") == "active" } ?: return bad("نوع پیوند پیدا نشد.", jo("kind" to "unknown"))
                        val to = b.obj("to")
                        val ref = to.s("ref")?.trim().orEmpty()
                        if (to.s("kind") !in lk.strs("to_kinds") || ref.isEmpty()) return bad("«${lk.s("title_fa")}» به ${lk.strs("to_kinds").joinToString("، ")} وصل میشود.", jo("to" to "kind"))
                        if (to.s("kind") == "record" && (recordOf(ref) == null || ref == r.s("ref"))) return bad("سند مقصد پیدا نشد.", jo("to" to "not_found"))
                        if (links.any { it.s("kind") == b.s("kind") && it.obj("to").s("ref") == ref }) return bad("همین پیوند هست.", status = 409)
                        r.with("links" to ja(links + jo("kind" to lk.s("key"), "to" to jo("kind" to to.s("kind"), "ref" to ref), "at" to stamp(), "by" to owner, "sealed" to false)))
                    } else if (m == "DELETE") {
                        val i = links.indexOfFirst { it.s("kind") == q["kind"] && it.obj("to").s("kind") == q["to_kind"] && it.obj("to").s("ref") == q["to_ref"] }
                        if (i < 0) return 404 to problem(404, "not_found", "این پیوند نیست.")
                        if (links[i].bool("sealed")) return 409 to problem(409, "sealed_record", "این پیوند با نسخه‌ی مُهرشده آمده و برداشته نمیشود.")
                        r.with("links" to ja(links.filterIndexed { j, _ -> j != i }))
                    } else return null
                    val out = next.with("version" to ver + 1)
                    saveRecord(out)
                    return 200 to recordOut(out)
                }
            }
        }
        // ---- §23.10 schema
        Regex("^/archive/schema/([a-z_]+)/([^/]+?)(/retire)?$").find(path)?.let { mm ->
            val p = mm.groupValues[1]
            val key = java.net.URLDecoder.decode(mm.groupValues[2], "UTF-8")
            val retire = mm.groupValues[3].isNotEmpty()
            val dry = q["dry_run"] == "1"
            if (p !in SCHEMA_PARTS) return 404 to problem(404, "not_found", "این بخش از طرح نیست.")
            if (p == "clearance") {
                if (retire) return 422 to problem(422, "schema_invalid", "مجوز بازنشسته نمیشود؛ سطحش را عوض کن.", jo("clearance" to "retire"))
                if (m != "PUT") return null
                val rows = clearanceRows(key)
                versionCheck(req, rows.firstOrNull()?.int("version"))?.let { return it }
                validatePart(p, key, b, null).takeIf { it.isNotEmpty() }?.let { return invalid(it) }
                val impact = impactOf(p, key, b)
                val v = (rows.firstOrNull()?.int("version") ?: 0) + 1
                if (dry) return 200 to jo("part" to p, "key" to key, "version" to v, "impact" to impact, "row" to null, "dry_run" to true)
                stepUpMissing(req)?.let { return it }
                return 200 to jo("part" to p, "key" to key, "version" to v, "impact" to impact, "row" to applyPut(p, key, b))
            }
            val list = part(p)
            val cur = if (key == "new") null else list.firstOrNull { keyOf(p, it) == key }
            if (retire && m == "POST") {
                if (cur == null) return 404 to problem(404, "not_found", "پیدا نشد.")
                if (cur.s("status") == "retired") return bad("همین حالا بازنشسته است.", status = 409)
                if (p == "levels" && part("levels").count { it.s("status") == "active" } <= 2) return invalid(mapOf("level" to "دست‌کم دو سطح فعال لازم است"))
                val impact = impactOf(p, key, cur)
                if (dry) return 200 to jo("part" to p, "key" to key, "version" to cur.int("version") + 1, "impact" to impact, "row" to null, "dry_run" to true)
                stepUpMissing(req)?.let { return it }
                val row = cur.with("status" to "retired", "version" to cur.int("version") + 1)
                savePart(p, list.map { if (keyOf(p, it) == key) row else it })
                return 200 to jo("part" to p, "key" to key, "version" to row.int("version"), "impact" to impact, "row" to row)
            }
            if (m == "PUT") {
                if (p !in REF_PARTS && key == "new") return invalid(mapOf("key" to "کلید لازم است"))
                if (p in REF_PARTS && key != "new" && cur == null) return 404 to problem(404, "not_found", "پیدا نشد.")
                versionCheck(req, cur?.int("version"))?.let { return it }
                validatePart(p, key, b, cur).takeIf { it.isNotEmpty() }?.let { return invalid(it) }
                val impact = impactOf(p, key, b)
                if (dry) return 200 to jo("part" to p, "key" to key, "version" to (cur?.int("version") ?: 0) + 1, "impact" to impact, "row" to null, "dry_run" to true)
                stepUpMissing(req)?.let { return it }
                val row = applyPut(p, key, b)
                return 200 to jo("part" to p, "key" to keyOf(p, row), "version" to row.int("version"), "impact" to impact, "row" to row)
            }
            return null
        }
        if (path == "/archive/sources" && m == "PUT") {
            for ((k, v) in b) {
                val i = sources.indexOfFirst { it.s("key") == k }
                if (i < 0) return bad("منبع «$k» در فهرست بسته نیست.", jo(k to "unknown"))
                sources[i] = sources[i].with("enabled" to ((v as? JsonPrimitive)?.contentOrNull == "true"))
            }
            return 200 to ja(sources)
        }
        // ---- parties
        if (path == "/archive/parties" && m == "POST") {
            idem?.let { k -> keys[k]?.let { return it } }
            partyProblems(b)?.let { return it }
            val ref = "PT-%04d".format((parties.mapNotNull { it.s("ref")?.substringAfter('-')?.toIntOrNull() }.maxOrNull() ?: 0) + 1)
            val x = jo("ref" to ref, "kind" to b.s("kind"), "name_fa" to b.s("name_fa")!!.trim(), "name_en" to b.s("name_en")?.trim()?.ifEmpty { null }, "identifiers" to cleanMeta(b.obj("identifiers")),
                "scopes" to ja(b.arr("scopes")), "status" to "active", "version" to 1)
            parties += x
            return (201 to (partyOut(x) as JsonElement)).also { r -> idem?.let { keys[it] = r } }
        }
        Regex("^/archive/parties/(PT-\\d+)$").find(path)?.let { mm ->
            if (m != "PATCH") return null
            val i = parties.indexOfFirst { it.s("ref") == mm.groupValues[1] }
            if (i < 0) return 404 to problem(404, "not_found", "این طرف پیدا نشد.")
            val x = parties[i]
            versionCheck(req, x.int("version"))?.let { return it }
            val merged = JsonObject(x + b)
            partyProblems(merged)?.let { return it }
            val next = merged.with("identifiers" to cleanMeta(merged.obj("identifiers")), "version" to x.int("version") + 1)
            parties[i] = next
            return 200 to partyOut(next)
        }
        // ---- holds
        if (path == "/archive/holds" && m == "POST") {
            idem?.let { k -> keys[k]?.let { return it } }
            if (b.s("title_fa").isNullOrBlank()) return bad("عنوان توقیف لازم است.", jo("title_fa" to "required"))
            if (b.s("reason_md").isNullOrBlank()) return bad("دلیل توقیف لازم است.", jo("reason_md" to "required"))
            b.s("case")?.let { if (!Regex("^LC-\\d{4}$").matches(it)) return bad("پرونده باید LC-… باشد.", jo("case" to "format")) }
            val s = b.obj("scope")
            if (listOf("records", "folders", "classes", "parties").none { s.strs(it).isNotEmpty() } && s.s("from") == null && s.s("to") == null) return bad("دامنه‌ی توقیف خالی است.", jo("scope" to "required"))
            val ref = "LH-%04d".format((holds.mapNotNull { it.s("ref")?.substringAfter('-')?.toIntOrNull() }.maxOrNull() ?: 0) + 1)
            val h = jo("ref" to ref, "title_fa" to b.s("title_fa")!!.trim(), "case" to b.s("case"), "reason_md" to b.s("reason_md")!!.trim(), "scope" to s, "state" to "active",
                "placed_by" to owner, "placed_at" to stamp(), "released_at" to null)
            holds.add(0, h)
            for (r in records.filter { covers(h, it) }) saveRecord(runAutomations("hold_set", r))
            return (201 to (holdOut(h) as JsonElement)).also { r -> idem?.let { keys[it] = r } }
        }
        Regex("^/archive/holds/(LH-\\d+)/release$").find(path)?.let { mm ->
            val i = holds.indexOfFirst { it.s("ref") == mm.groupValues[1] }
            if (i < 0) return 404 to problem(404, "not_found", "این توقیف پیدا نشد.")
            stepUpMissing(req)?.let { return it }
            if (holds[i].s("state") != "active") return bad("این توقیف همین حالا آزاد است.", status = 409)
            holds[i] = holds[i].with("state" to "released", "released_at" to stamp())
            return 200 to holdOut(holds[i])
        }
        // ---- reminders
        Regex("^/archive/reminders/([^/]+)/done$").find(path)?.let { mm ->
            val id = java.net.URLDecoder.decode(mm.groupValues[1], "UTF-8")
            val r = recordOf(id.substringBefore(':'))
            if (r == null || remindersOf(r).none { it.id == id }) return 404 to problem(404, "not_found", "این یادآور پیدا نشد.")
            remindersDone += id
            val x = remindersOf(r).first { it.id == id }
            return 200 to jo("field" to x.field, "at" to x.at, "lead_days" to x.lead, "state" to x.state, "rule" to x.rule, "id" to x.id)
        }
        return null
    }

    private fun partyProblems(b: JsonObject): Pair<Int, JsonElement>? {
        val k = part("party_kinds").firstOrNull { it.s("key") == b.s("kind") && it.s("status") == "active" } ?: return bad("نوع طرف پیدا نشد.", jo("kind" to "unknown"))
        if (b.s("name_fa").isNullOrBlank()) return bad("نام فارسی لازم است.", jo("name_fa" to "required"))
        metadataProblems(k.arr("identifier_fields"), cleanMeta(b.obj("identifiers")), true).takeIf { it.isNotEmpty() }?.let { return bad(it.values.first(), JsonObject(it.mapValues { e -> JsonPrimitive(e.value) })) }
        if (b.strs("scopes").any { it !in scopesNow() }) return bad("دامنه‌ی ناشناخته.", jo("scopes" to "unknown"))
        return null
    }

    private fun invalid(fields: Map<String, String>): Pair<Int, JsonElement> =
        422 to problem(422, "schema_invalid", "با واژگان بسته نمیخواند: ${fields.values.first()}", JsonObject(fields.mapValues { JsonPrimitive(it.value) }))

    // ------------------------------------------------------------------ the two cards (§23.11) --
    private fun decisions(): List<JsonObject> = items("/decisions?status=all")
    private fun decisionOf(ref: String): JsonObject? = store["/decisions/$ref"]?.second as? JsonObject ?: decisions().firstOrNull { it.s("ref") == ref }

    /** An archive_schema card is void when its row changed after it was written; a step-up is required for both kinds. */
    private fun approveCheck(req: Request, ref: String): Pair<Int, JsonElement>? {
        val d = decisionOf(ref) ?: return null
        if (d.s("kind") !in setOf("archive_schema", "archive_disposal")) return null
        stepUpMissing(req)?.let { return it }
        if (d.s("kind") == "archive_schema") {
            val p = d.obj("payload")
            val part = p.s("part").orEmpty()
            val key = p.s("key").orEmpty()
            val cur = if (part == "clearance") clearanceRows(key).firstOrNull() else part(part).firstOrNull { keyOf(part, it) == key }
            val base = (p["base_version"] as? JsonPrimitive)?.contentOrNull?.toIntOrNull()
            if (cur?.int("version")?.takeIf { cur.containsKey("version") } != base) return 409 to problem(409, "version_conflict", "این بخش از طرح بعد از نوشتن کارت عوض شده؛ کارت باطل است و بایگان پیشنهاد تازه مینویسد.")
            validatePart(part, key, p.obj("body"), cur).takeIf { it.isNotEmpty() }?.let { return invalid(it) }
        }
        return null
    }

    /** What deciding a §23 card does (the web's decided20): a schema change applied, or the batch disposed with tombstones (held skipped). */
    fun decided(d: JsonObject) {
        if (d.s("status") != "approved") return
        val p = d.obj("payload")
        when (d.s("kind")) {
            "archive_schema" -> applyPut(p.s("part").orEmpty(), p.s("key").orEmpty(), p.obj("body"))
            "archive_disposal" -> for (x in p.arr("records")) {
                val r = recordOf(x.s("ref").orEmpty()) ?: continue
                if (holdsOf(r).isNotEmpty() || r.s("state") == "disposed") continue // a held record is skipped and stays
                val fs = r.arr("versions").flatMap { it.arr("files") }
                destroyed += fs.mapNotNull { it.s("file_id") }
                saveRecord(r.with("state" to "disposed", "version" to r.int("version") + 1,
                    "tombstone" to jo("decision" to d.s("ref"), "at" to stamp(), "hashes" to ja(fs.map { jo("name" to it.s("name"), "sha256" to it.s("sha256")) }))))
            }
        }
    }

    // ------------------------------------------------------------------ plumbing --
    private fun respond(req: Request, r: Pair<Int, JsonElement>): Response = Response.Builder().request(req).protocol(Protocol.HTTP_1_1).code(r.first).message("demo")
        .body(r.second.toString().toResponseBody("application/json".toMediaType())).build()

    private fun page(xs: List<JsonElement>) = jo("items" to ja(xs), "next_cursor" to null)
    private fun problem(status: Int, code: String, fa: String, fields: JsonObject = JsonObject(emptyMap())) =
        JsonObject(jo("type" to "about:blank", "title" to code, "status" to status, "code" to code, "message_fa" to fa) + if (fields.isNotEmpty()) mapOf("fields" to fields) else emptyMap())

    private companion object {
        val DATE = Regex("^\\d{4}-\\d{2}-\\d{2}$")
        val KEY = Regex("^[a-z][a-z0-9_]{1,39}$")
        /** The same patterns as gitleaks and the outbound guard (§19.6), reduced to what the demo needs. */
        val SECRET = Regex("seed|private[\\s_-]?key|mnemonic|-----BEGIN [A-Z ]*PRIVATE KEY-----|عبارت بازیابی|کلید خصوصی", RegexOption.IGNORE_CASE)
        val SCHEMA_PARTS = listOf("classes", "folders", "levels", "clearance", "retention", "reminders", "party_kinds", "link_kinds", "automations")
        val REF_PARTS = setOf("folders", "retention", "reminders", "automations")
        val PREFIX = mapOf("folders" to "FP", "retention" to "RR", "reminders" to "RM", "automations" to "AU")

        fun JsonElement?.s(): String? = (this as? JsonPrimitive)?.takeIf { it.isString }?.content
        fun JsonObject.s(k: String): String? = (this[k] as? JsonPrimitive)?.takeIf { it.isString }?.content
        fun JsonObject.int(k: String): Int = (this[k] as? JsonPrimitive)?.contentOrNull?.toDoubleOrNull()?.toInt() ?: 0
        fun JsonObject.dbl(k: String): Double = (this[k] as? JsonPrimitive)?.contentOrNull?.toDoubleOrNull() ?: 0.0
        fun JsonObject.bool(k: String): Boolean = (this[k] as? JsonPrimitive)?.contentOrNull == "true"
        fun JsonElement.bool(k: String): Boolean = (this as? JsonObject)?.bool(k) == true
        fun JsonObject.obj(k: String): JsonObject = this[k] as? JsonObject ?: JsonObject(emptyMap())
        fun JsonObject.arr(k: String): List<JsonObject> = (this[k] as? JsonArray)?.mapNotNull { it as? JsonObject }.orEmpty()
        /** Any array's elements (numbers too; [arr] keeps only objects). */
        fun JsonObject.items(k: String): List<JsonElement> = (this[k] as? JsonArray)?.toList().orEmpty()
        fun JsonObject.strs(k: String): List<String> = (this[k] as? JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.contentOrNull }.orEmpty()
        fun JsonObject?.orEmpty(): JsonObject = this ?: JsonObject(emptyMap())
        fun JsonObject.with(vararg kv: Pair<String, Any?>): JsonObject = JsonObject(this + jo(*kv))
        fun ja(xs: List<JsonElement>) = JsonArray(xs)
        fun jo(vararg kv: Pair<String, Any?>): JsonObject = JsonObject(kv.associate { (k, v) ->
            k to when (v) {
                null -> JsonNull; is JsonElement -> v; is String -> JsonPrimitive(v); is Number -> JsonPrimitive(v); is Boolean -> JsonPrimitive(v)
                else -> error("unsupported ${v::class}")
            }
        })
    }
}
