package com.coinepro.hq.core.data

import com.coinepro.hq.core.net.Finding
import com.coinepro.hq.core.net.Protocol

/**
 * ⟨1.10⟩ §28.3 the watch (دیده‌بان): the overseer's findings from its new protocols, read from the same `/oversight/findings`, grouped
 * by what they watch. The hub names the kind on the finding (`kind`); a finding without it is placed by its protocol (the security
 * area, or the protocol's title), and anything else is not the watch's.
 */
enum class WatchKind(val key: String, val fa: String, val note: String) {
    SECURITY("security", "امنیت", "پورت‌های باز، CVE، گواهی TLS، ورودهای ناموفق، رمز در ریپو و تازگی backup"),
    APP_HEALTH("app_health", "سلامت اپ", "خطاهایی که اپ‌ها خودشان فرستاده‌اند، با علت در کد"),
    CODE("code", "کد", "بازبینی هفتگی هر ریپو: باگ، کد مرده، تست جاافتاده"),
    GROWTH("growth", "رشد", "سه حرکت پرارزش هر شرکت از مشاور کل"),
    HOLDING("holding", "پیشنهاد هلدینگ", "فرصت‌های میان شرکت‌ها از مدیر کل دیجیتال"),
    ;

    companion object {
        fun of(key: String?): WatchKind? = entries.firstOrNull { it.key == key }
    }
}

object Watch {
    private val TITLES = listOf(
        WatchKind.APP_HEALTH to Regex("سلامت.{0,20}اپ|خطای\\s*اپ|خطاهای\\s*اپ|app[ _-]?health|client errors", RegexOption.IGNORE_CASE),
        WatchKind.CODE to Regex("بازبینی\\s*کد|code[ _-]?review", RegexOption.IGNORE_CASE),
        WatchKind.GROWTH to Regex("رشد|growth", RegexOption.IGNORE_CASE),
        WatchKind.HOLDING to Regex("پیشنهاد\\s*هلدینگ|holding proposal", RegexOption.IGNORE_CASE),
        WatchKind.SECURITY to Regex("امنیت|security", RegexOption.IGNORE_CASE),
    )

    /** What [f] watches, or null when it is not a watch finding. */
    fun kindOf(f: Finding, protocols: List<Protocol>?): WatchKind? {
        WatchKind.of(f.kind)?.let { return it }
        val p = protocols?.firstOrNull { it.ref == f.protocol } ?: return null
        TITLES.firstOrNull { (_, re) -> re.containsMatchIn(p.titleFa) }?.let { return it.first }
        return if (p.area == "security") WatchKind.SECURITY else null
    }

    /** Whether the owner still has something to do with it. */
    fun open(f: Finding): Boolean = f.status !in setOf("verified", "closed")

    /** The open watch findings by kind (in [WatchKind] order), the most severe first inside each. */
    fun groups(findings: List<Finding>, protocols: List<Protocol>?, includeClosed: Boolean = false): List<Pair<WatchKind, List<Finding>>> {
        val by = findings.filter { includeClosed || open(it) }.mapNotNull { f -> kindOf(f, protocols)?.let { it to f } }.groupBy({ it.first }, { it.second })
        return WatchKind.entries.mapNotNull { k -> by[k]?.sortedBy { SEVERITY.indexOf(it.severity).let { i -> if (i < 0) SEVERITY.size else i } }?.let { k to it } }
    }

    /** The priority a fix's work item gets from the finding's severity. */
    fun priorityOf(severity: String): String = when (severity) { "critical" -> "P1"; "high" -> "P2"; "medium" -> "P3"; else -> "P4" }

    private val SEVERITY = listOf("critical", "high", "medium", "low", "info")
}
