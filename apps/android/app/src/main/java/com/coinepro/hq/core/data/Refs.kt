package com.coinepro.hq.core.data

/**
 * Where a reference opens in the app: one router for every place that turns a ref, a notification's link or a planner row into a
 * route. A ref's prefix says what it is (the hub's own sequences, `apps/api/migrations`): `W-` a work item, `MT-` a meeting, `D-` a
 * card, `O-` an output, `AR-` an archive record, `C-` a founding… Only a work item opens the work page: `GET /work/{id}` takes a UUID
 * (the app resolves a `W-` ref first), so anything else sent there is `422 validation_failed` (0.4.0: `GET /work/MT-0077`).
 */
object Refs {
    private val UUID = Regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

    /** Prefix → route; `$` stands for the ref itself. Longer prefixes first, so `MT-` is never read as `M-`. */
    private val ROUTES: List<Pair<String, String>> = listOf(
        // the work and the owner's day
        "W" to "work/$", "D" to "cartable/$", "O" to "outputs/$", "MT" to "meetings/$", "PL" to "planner",
        // the workshop, founding and servers (§17, §18.8)
        "S" to "workshop/$", "G" to "workshop", "AP" to "workshop", "C" to "founding/$", "PV" to "founding/$",
        // the overseer (findings, holds, challenges, standing orders), inquiries, errands, incidents (§18)
        "FI" to "oversight", "H" to "oversight", "CH" to "oversight", "SO" to "oversight",
        "Q" to "advisor", "E" to "assistant", "I" to "sites", "TE" to "academy",
        // revenue, support and growth (§19)
        "SC" to "support/$", "FB" to "feedback", "TM" to "growth", "LR" to "growth", "RC" to "growth",
        // governance (§20)
        "K" to "knowledge/$", "KB" to "knowledge/$", "OB" to "okr", "KR" to "okr", "RK" to "risks/$", "CE" to "calendar",
        "OR" to "outcomes", "M" to "resolutions", "B" to "cartable",
        // management tools (§21)
        "NT" to "notes/$", "BR" to "letter/$", "CR" to "substitutes/$", "DM" to "advisor", "WR" to "advisor", "DP" to "digital-ceo",
        "CL" to "runs", "AK" to "home",
        // media and legal (§22)
        "SR" to "series/$", "MI" to "studio/$", "LC" to "legal/$", "RD" to "roles/$", "L" to "messages/L",
        // the archive (§23): a record, a hold, a party's records, a folder's records, the open layer's rows
        "AR" to "archive/$", "LH" to "archive-holds/$", "PT" to "archive-in/party/$", "FP" to "archive-in/folder/$",
        "RR" to "archive-settings/retention/$", "RM" to "archive-settings/reminders/$", "AU" to "archive-settings/automations/$",
    ).sortedByDescending { it.first.length }

    private val REF = Regex("^([A-Z]{1,3})-(\\d{1,10})$")
    private val CHARTER = Regex("^(?:[A-Z]{2,5}|holding)@\\d+$")

    /** The prefix of a ref (`MT` of `MT-0077`), or null when [s] is not a ref. */
    fun prefix(s: String?): String? = s?.let { REF.find(it.trim())?.groupValues?.get(1) }

    fun isWork(s: String?): Boolean = prefix(s) == "W"
    fun isUuid(s: String?): Boolean = s != null && UUID.matches(s)

    /** The page [ref] opens, or null when it has none. */
    fun route(ref: String): String? {
        val r = ref.trim()
        if (CHARTER.matches(r)) return "charter"
        val p = prefix(r) ?: return null
        val to = ROUTES.firstOrNull { it.first == p }?.second ?: return null
        return to.replace("$", r)
    }

    /** A notification's `link` (contract §6; the kinds the hub raises, `domain/notify.raise_notification` callers). */
    fun forLink(kind: String?, ref: String?): String? {
        val r = ref?.trim()?.ifBlank { null }
        return when (kind) {
            null -> r?.let(::route)
            "decision" -> r?.let { "cartable/$it" } ?: "cartable"
            "deliverable" -> r?.let { "outputs/$it" } ?: "outputs"
            "work" -> r?.let { if (isWork(it) || isUuid(it)) "work/$it" else route(it) } ?: "orders"
            "thread" -> r?.let { "messages/$it" } ?: "messages"
            "message" -> "advisor"
            "finding", "hold", "challenge" -> "oversight"
            "inquiry" -> "advisor"
            "meeting" -> r?.let { "meetings/$it" } ?: "meetings"
            "founding", "provision_run" -> r?.takeIf { prefix(it) == "C" }?.let { "founding/$it" } ?: "founding"
            "server_plan" -> r?.takeIf { prefix(it) == "PV" }?.let { "founding/$it" } ?: "founding"
            "code_session" -> r?.takeIf { prefix(it) == "S" }?.let { "workshop/$it" } ?: "workshop"
            "archive_record" -> r?.takeIf { prefix(it) == "AR" }?.let { "archive/$it" } ?: "archive"
            "archive_fixity" -> "archive"
            "support_conversation" -> r?.takeIf { prefix(it) == "SC" }?.let { "support/$it" } ?: "support"
            "support_queue" -> "support"
            "revenue_alert" -> "revenue"
            "substitute" -> "substitutes"
            "employee" -> r?.let { "employees/$it" }
            "treasury" -> "treasury"
            "academy" -> "academy"
            "backup" -> "control"
            "audit" -> "audit"
            "device" -> "settings"
            else -> r?.let(::route)
        }
    }

    /** A planner row (§1.9, ⟨1.5⟩): work, the owner's reminders (no page of their own), meetings and change-calendar events. */
    fun forPlanner(kind: String?, ref: String): String? = when (kind) {
        "meeting" -> "meetings/$ref"
        "calendar" -> "calendar"
        "reminder" -> null
        else -> route(ref)
    }

    /**
     * The last guard before navigating: a `work/…` route whose key is a ref of something else goes to that thing's page instead
     * (and one that is neither a work ref nor an id goes nowhere rather than to a 422).
     */
    fun normalize(route: String): String? {
        if (!route.startsWith("work/")) return route
        val key = route.removePrefix("work/")
        if (key.isEmpty()) return null
        if (isWork(key) || isUuid(key)) return route
        // A demo or test id ("w0"), or another kind of ref.
        return if (prefix(key) != null) route(key) else route
    }
}
