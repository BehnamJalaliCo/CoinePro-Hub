package com.coinepro.hq.core.net

import kotlinx.serialization.Serializable

// ----------------------------------------------------------------- v1.16 / v1.17 --
// Contract §34 (the order answered live, nothing technical to the owner) and §35 (every order a session; the owner's office; company
// links and the canvas). Same rules as Models.kt: camelCase here, snake_case on the wire; a field the hub omits takes its default, so
// a hub before ⟨1.17⟩ still reads (its order reports simply have no session block).

// ------------------------------------------------------------------ §34.3 --
/** The owner's open turn on an order (`order.ask`): the question, when, who asked it, in plain words. */
@Serializable
data class OrderTurn(val questionFa: String = "", val at: String = "", val by: Actor? = null, val whoFa: String = "")

/** `POST /orders/{ref}/talk` → the order's conversation (made once). */
@Serializable
data class OrderTalk(val conversationRef: String = "")

// ------------------------------------------------------------------ §35.2 --
/** Who holds a session: the employee (or fixed persona) answering for it. */
@Serializable
data class SessionHolder(val code: String = "", val titleFa: String = "", val company: String? = null, val companyFa: String? = null)

/** «چه شد · حالا چه · از تو چه», always filled by the hub. */
@Serializable
data class SessionBrief(val doneFa: String = "", val nowFa: String = "", val needFa: String = "")

@Serializable
data class TaskCount(val done: Int = 0, val total: Int = 0)

/** Someone in the session: the holder, a person (any persona key) or a player (`player:gpt` …). */
@Serializable
data class SessionParticipant(
    /** role@CODE · advisor · overseer · assistant · secretary · player:gpt · player:gemini · player:deepseek */
    val key: String,
    /** holder · person · player */
    val kind: String = "person",
    val titleFa: String = "",
    val company: String? = null,
)

/** One line of the session's plan, like a Claude Code task list. */
@Serializable
data class SessionTask(
    val id: String,
    val n: Int = 0,
    val titleFa: String = "",
    /** todo · doing · done · dropped */
    val state: String = "todo",
    /** owner · agent */
    val by: String = "agent",
    val whoFa: String? = null,
    val workRef: String? = null,
)

/** One session in a list (`GET /sessions`, the office). [ref] is the app's key only: it is never shown. */
@Serializable
data class SessionCard(
    val ref: String,
    val conversationRef: String? = null,
    val titleFa: String = "",
    val holder: SessionHolder? = null,
    /** your_turn · ready · stuck · moving · closed */
    val badge: String = "moving",
    val reasonFa: String = "",
    val brief: SessionBrief = SessionBrief(),
    /** auto · step */
    val pace: String = "auto",
    val participants: List<SessionParticipant> = emptyList(),
    val tasks: TaskCount = TaskCount(),
    val openedAt: String = "",
    val lastAt: String = "",
    val closedAt: String? = null,
    val hidden: Boolean = false,
)

/** The session block of an order report (§35.2, additive). */
@Serializable
data class SessionState(
    /** open · closed */
    val state: String = "open",
    val badge: String = "moving",
    val reasonFa: String = "",
    val closedAt: String? = null,
    val hidden: Boolean = false,
)

// ------------------------------------------------------------------ §35.5 --
@Serializable
data class OfficeMoney(
    @Serializable(with = LenientDouble::class) val revenueMonthUsd: Double? = null,
    @Serializable(with = LenientDouble::class) val spendMonthUsd: Double = 0.0,
    @Serializable(with = LenientDouble::class) val budgetMonthUsd: Double? = null,
    val lineFa: String = "",
)

/** `GET /office`: the owner's office (the home). Nothing on it is fixed to one subject. */
@Serializable
data class Office(
    val sessions: List<SessionCard> = emptyList(),
    val approvals: List<Decision> = emptyList(),
    val approvalsTotal: Int = 0,
    val money: OfficeMoney = OfficeMoney(),
    val critical: List<Notification> = emptyList(),
    val suggestions: List<HomeSuggestion> = emptyList(),
    val canvas: Canvas = Canvas(),
)

// ------------------------------------------------------------------ §35.6 --
@Serializable
data class CanvasNode(
    val code: String,
    val nameFa: String = "",
    /** holding · company */
    val kind: String = "company",
    /** Where the owner put it, 0…1 of the canvas; null: laid out on a circle around the hub. */
    val x: Double? = null,
    val y: Double? = null,
    val lineFa: String = "",
    val openSessions: Int = 0,
)

@Serializable
data class CompanyLink(
    val id: String,
    val from: String = "",
    val to: String = "",
    /** serves · publishes · feeds · sells · supports */
    val kind: String = "serves",
    val purposeFa: String = "",
    /** on · off */
    val state: String = "on",
    val openWorks: Int = 0,
    val updatedAt: String = "",
)

/** `GET /links`, and the office's canvas: the hub in the centre, the companies around it, the links between them. */
@Serializable
data class Canvas(val nodes: List<CanvasNode> = emptyList(), val links: List<CompanyLink> = emptyList())
