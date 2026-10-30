package com.coinepro.hq

import com.coinepro.hq.core.format.HqClock
import java.time.LocalDate
import java.time.ZoneId
import java.time.temporal.ChronoUnit
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

/**
 * Debug builds only, for the owner's 0.4.0 findings:
 *
 * - **Removing a company** — the proposed `DELETE /companies/{code}` 🔏 `company.delete` (a server gap): `403 step_up_required` without
 *   the step-up, `409 company_has_history` for a company that has worked, staffed or earned (TradeYar, CoinePro FX, Pro-Chart), `204` for
 *   one made by mistake (a company the wizard just registered); `PATCH /companies/{code}` with If-Match (name, colour, `status: archived`
 *   with 🔏 `company.archive`) as the hub serves it.
 * - **The planner as the hub serves it** (⟨1.5⟩): `from`/`to` select the days, and today carries the board meeting (MT-0012, `kind:
 *   meeting`) and one of the owner's reminders (PL-…), so a meeting's row opens the meeting room, not the work page.
 * - **The founding's work refs** (§18.8): the audit's and the proposal's work items (`audit_work`, `proposal_work`), the audit's report.
 */
internal class CompaniesDemo(private val store: MutableMap<String, Pair<Int, JsonElement>>) {
    private val tehran = ZoneId.of("Asia/Tehran")

    init {
        val now = HqClock.now()
        // Today's board meeting (live since 26 minutes ago) and a reminder of the owner's own at 14:00 Tehran.
        val planner = store["/planner"]?.second?.jsonObject
        if (planner != null) {
            val today = LocalDate.ofInstant(now, java.time.ZoneOffset.UTC).toString()
            val meeting = buildJsonObject {
                put("ref", "MT-0012"); put("title", "هیئت‌مدیره‌ی هلدینگ"); put("company", "HQ"); put("status", "live"); put("priority", "P2")
                put("at", now.minus(26, ChronoUnit.MINUTES).toString()); put("assignee", JsonNull); put("recurring", true); put("kind", "meeting"); put("note", "board")
            }
            val reminder = buildJsonObject {
                put("ref", "PL-0004"); put("title", "تماس با وکیل درباره‌ی قرارداد سرور"); put("company", "HQ"); put("status", "reminder"); put("priority", "P3")
                put("at", LocalDate.ofInstant(now, tehran).atTime(14, 0).atZone(tehran).toInstant().toString()); put("assignee", JsonNull); put("recurring", false); put("kind", "reminder")
            }
            val days = planner["days"]!!.jsonArray.map { d ->
                val o = d.jsonObject
                if (o.str("date") != today) o
                else JsonObject(o + ("items" to JsonArray((o["items"]!!.jsonArray.map { it.jsonObject } + meeting + reminder).sortedBy { it.str("at") })))
            }
            store["/planner"] = 200 to JsonObject(planner + ("days" to JsonArray(days)))
        }
        // The founding's work items: the repository's audit (and its report), the proposals.
        founding("C-0002") { f ->
            val audit = f["audit"] as? JsonObject
            f + mapOf(
                "audit_work" to JsonPrimitive("W-000231"), "proposal_work" to JsonPrimitive("W-000234"),
                "audit" to (audit?.let { JsonObject(it + ("deliverable" to JsonPrimitive("O-000041"))) } ?: JsonNull),
            )
        }
        founding("C-0003") { it + ("proposal_work" to JsonPrimitive("W-000238")) }
        founding("C-0001") { it + ("proposal_work" to JsonPrimitive("W-000219")) }
    }

    fun handle(method: String, path: String, query: Map<String, String?>, body: JsonObject?, version: Int?, stepUp: String?): Pair<Int, JsonElement>? {
        if (method == "GET" && path == "/planner" && (query["from"] != null || query["to"] != null)) {
            val p = store["/planner"]?.second?.jsonObject ?: return null
            val from = query["from"]
            val to = query["to"] ?: from
            val days = p["days"]!!.jsonArray.filter { d -> val date = d.jsonObject.str("date").orEmpty(); (from == null || date >= from) && (to == null || date <= to) }
            return 200 to JsonObject(p + ("days" to JsonArray(days)))
        }
        val m = Regex("^/companies/([A-Z][A-Z0-9]{1,9})$").find(path) ?: return null
        val code = m.groupValues[1]
        val co = companies().firstOrNull { it.str("code") == code } ?: return if (method == "GET") null else 404 to problem(404, "not_found", "این شرکت پیدا نشد.")
        when (method) {
            "DELETE" -> {
                if (stepUp == null) return 403 to problem(403, "step_up_required", "این کار تأیید با گذرکلید لازم دارد.")
                if (co.str("kind") == "holding") return 422 to problem(422, "validation_failed", "هلدینگ حذف نمیشود.")
                val counts = co["counts"] as? JsonObject
                val worked = (counts?.get("work_open")?.jsonPrimitive?.intOrNull ?: 0) > 0 || (counts?.get("employees_active")?.jsonPrimitive?.intOrNull ?: 0) > 0
                if (worked || code in setOf("TY", "FX", "PC")) return 409 to problem(409, "company_has_history", "این شرکت کار، خروجی یا درآمد دارد و حذف نمیشود؛ بایگانی‌اش کن.")
                store["/companies"] = 200 to JsonArray(companies().filter { it.str("code") != code })
                store.remove("/companies/$code")
                return 204 to JsonObject(emptyMap())
            }
            "PATCH" -> {
                val cur = co["version"]?.jsonPrimitive?.intOrNull ?: 1
                if (version == null) return 428 to problem(428, "validation_failed", "If-Match لازم است.")
                if (version != cur) return 409 to problem(409, "version_conflict", "این شرکت تازه عوض شده؛ دوباره باز کن.")
                val archive = body?.get("status")?.jsonPrimitive?.contentOrNull == "archived"
                if (archive && stepUp == null) return 403 to problem(403, "step_up_required", "این کار تأیید با گذرکلید لازم دارد.")
                val fields = body.orEmpty().filterKeys { it in setOf("name_fa", "name_en", "color_index", "status") }
                val next = JsonObject(co + fields + ("version" to JsonPrimitive(cur + 1)))
                store["/companies"] = 200 to JsonArray(companies().map { if (it.str("code") == code) next else it })
                store["/companies/$code"] = 200 to next
                return 200 to next
            }
        }
        return null
    }

    private fun founding(ref: String, f: (JsonObject) -> Map<String, JsonElement>) {
        val one = store["/foundings/$ref"]?.second?.jsonObject ?: return
        val next = JsonObject(f(one))
        store["/foundings/$ref"] = 200 to next
        val list = store["/foundings"]?.second?.jsonObject ?: return
        val items = list["items"]!!.jsonArray.map { if (it.jsonObject.str("ref") == ref) JsonObject(f(it.jsonObject)) else it }
        store["/foundings"] = 200 to JsonObject(list + ("items" to JsonArray(items)))
    }

    private fun companies(): List<JsonObject> = store["/companies"]?.second?.jsonArray.orEmpty().map { it.jsonObject }

    private fun problem(status: Int, code: String, fa: String) = buildJsonObject { put("code", code); put("message_fa", fa); put("status", status); put("title", code); put("type", "about:blank") }

    private fun JsonObject.str(k: String): String? = (this[k] as? JsonPrimitive)?.takeIf { it.isString }?.content
}
