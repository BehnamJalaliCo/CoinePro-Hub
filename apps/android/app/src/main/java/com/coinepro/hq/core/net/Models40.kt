package com.coinepro.hq.core.net

import kotlinx.serialization.Serializable

// Contract §40 ⟨1.22⟩: a session remembers («تا اینجا», `OrderReport.memory_md`) and becomes a working group as data, a playbook: seats
// (who does what, with which helpers), routines (one small work each time, for a seat), KPIs, rules. Drafted by the holder from the
// session, edited in words there or lightly here, sealed by the owner (🔏 `playbook.seal`), then given to any company or platform
// (`apply`: a new session that adapts it there, or, sealed and «بدون تغییر», a membership at once). Same rules as Models.kt: camelCase
// here, snake_case on the wire; a field the hub omits takes its default.

/** A seat of the working group: a person of a company (an employee's, a manager's or the CEO's charter), what they do, their helpers. */
@Serializable
data class PlaybookSeat(
    val seat: String = "",
    /** The charter key (never shown: [titleFa] is the seat's name). */
    val role: String = "",
    val titleFa: String = "",
    val dutiesFa: String = "",
    /** gpt · gemini · deepseek · aistudio */
    val helpers: List<String> = emptyList(),
    val model: String? = null,
)

/** One small work for a seat's person each time its [schedule] (an RRULE, the owner's zone) comes round. */
@Serializable
data class PlaybookRoutine(
    val key: String = "",
    val titleFa: String = "",
    val seat: String = "",
    val schedule: String = "",
    val briefMd: String = "",
    val maxTokens: Int = 40_000,
)

@Serializable
data class PlaybookKpi(val key: String = "", val titleFa: String = "", val source: String = "", val unit: String = "")

/** The session a playbook was drafted from. */
@Serializable
data class PlaybookSource(val order: String = "", val company: String? = null, val conversation: String? = null)

/** A company the sealed group runs in: `on` or `paused`; [order] the session it came from for that company. */
@Serializable
data class PlaybookMember(
    val company: String = "",
    val nameFa: String = "",
    val state: String = "on",
    val order: String? = null,
    /** ⟨0.19.9⟩ §45 the owner's standing word on publishing for this company. */
    val publish: MemberPublish = MemberPublish(),
)

/** `GET /playbooks/{ref}` and every playbook route's answer. [ref] (`PB-0001`) is the app's key only: it is never shown. */
@Serializable
data class Playbook(
    val ref: String,
    val titleFa: String = "",
    val purposeFa: String = "",
    /** draft · sealed · retired */
    val state: String = "draft",
    val version: Int = 1,
    /** instagram · youtube · telegram · site · any */
    val platform: String = "any",
    val seats: List<PlaybookSeat> = emptyList(),
    val routines: List<PlaybookRoutine> = emptyList(),
    val kpis: List<PlaybookKpi> = emptyList(),
    val connections: List<String> = emptyList(),
    val rulesFa: List<String> = emptyList(),
    val source: PlaybookSource = PlaybookSource(),
    val members: List<PlaybookMember> = emptyList(),
    /** The playbook this one was adapted from (a version), if any. */
    val parent: String? = null,
    val createdAt: String = "",
    val sealedAt: String? = null,
    val retiredAt: String? = null,
    /** The working group's key once sealed (`pb_<n>`; its page is `groups/{key}`). */
    val group: String? = null,
    /** What the drafter dropped and why, in plain Persian. */
    val noteFa: String? = null,
) {
    val draft: Boolean get() = state == "draft"
    val sealed: Boolean get() = state == "sealed"
    val retired: Boolean get() = state == "retired"
}

/** `POST /playbooks/{ref}/apply`: as is, the membership; else the new session ([order], [conversation]) that adapts it. */
@Serializable
data class PlaybookApplied(val playbook: Playbook, val member: PlaybookMember? = null, val order: String? = null, val conversation: String? = null)
