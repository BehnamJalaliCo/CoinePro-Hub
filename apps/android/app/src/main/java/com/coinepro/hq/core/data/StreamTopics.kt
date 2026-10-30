package com.coinepro.hq.core.data

/**
 * The topics the app asks the live stream for (contract §7, `apps/api/src/hq_api/events.py` TOPICS), split into lanes the hub accepts.
 *
 * `GET /api/v1/stream` takes `topics` as one comma-separated value of at most [MAX] characters (`Query(max_length=200, pattern=
 * ^[a-z]+(,[a-z]+)*$)`, routes/stream.py). Up to 0.4.0 the app named all 42 topics in one value of 339 characters: every first
 * connection was `422 validation_failed`, and the reconnect two seconds later fell back to the eight core topics only (so the newer
 * topics never refreshed anything). Each lane is now one connection with a value the hub accepts; together they cover every topic.
 */
object StreamTopics {
    /** The hub's limit on `topics` (routes/stream.py). */
    const val MAX = 200

    val CORE = listOf("work", "decisions", "deliverables", "messages", "notifications", "activity", "llm", "control")

    /** Every topic the hub serves and the app uses: [CORE] first, then the newer ones (§16–§23). */
    val ALL = CORE + listOf(
        "runs", "files", "workshop", "orders", "oversight", "inquiries", "errands", "stars", "skills", "academy", "founding", "backups",
        "stories", "companies", "revenue", "support", "growth", "feedback", "meetings", "governance", "knowledge", "advisor", "ask",
        "reviews", "briefings", "people", "notes", "quality", "dceo", "treasury", "creatives", "media", "legal", "archive",
    )

    /**
     * What the phone must hear even with the app closed (the background link, `device/HubLinkService`): urgent notifications and cards
     * waiting for the seal (`notification.*`), cards decided elsewhere (`decision.*`), the owner's orders moving (`work.*` and
     * `deliverable.created`, the orders tracker's own events), new outputs, and the kill switches (`control.*`). Nothing chatty: no
     * `activity`, `llm` or `runs`, which would wake the phone for every model call.
     */
    val ALERTS = listOf("work", "decisions", "deliverables", "notifications", "control")

    /** The event types the [ALERTS] topics carry (events.py TOPICS: `control` also carries `presence.` and `hiring.`). */
    val ALERT_PREFIXES = listOf("work.", "decision.", "deliverable.", "notification.", "control.", "presence.", "hiring.")

    private val VALID = Regex("^[a-z]+(,[a-z]+)*$")

    /** Whether the hub accepts [value] as `topics`. */
    fun accepted(value: String): Boolean = value.length <= MAX && VALID.matches(value)

    /** [topics] packed in order into as few values of at most [max] characters as fit; the core topics stay together in the first. */
    fun lanes(topics: List<String> = ALL, max: Int = MAX): List<String> {
        val out = mutableListOf<String>()
        var cur = StringBuilder()
        for (t in topics.distinct()) {
            require(t.length <= max && Regex("^[a-z]+$").matches(t)) { "topic $t" }
            if (cur.isNotEmpty() && cur.length + 1 + t.length > max) { out += cur.toString(); cur = StringBuilder() }
            if (cur.isNotEmpty()) cur.append(',')
            cur.append(t)
        }
        if (cur.isNotEmpty()) out += cur.toString()
        return out
    }

    /**
     * The lanes the stream opens: the first is [ALERTS] alone (the connection that stays open in the background, so opening or closing the
     * app never reconnects it), then every other topic of [topics] packed into as few lanes as fit. Each topic is asked for exactly once.
     */
    fun split(topics: List<String> = ALL, max: Int = MAX): List<String> =
        listOf(ALERTS.joinToString(",")) + lanes(topics.filter { it !in ALERTS }, max)

    /** The query of one lane's connection. */
    fun query(lane: String): Map<String, String> = mapOf("topics" to lane)
}
