package com.coinepro.hq.core.net

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

// Contract §61 ⟨1.39⟩: the automations as data. Every daily flow that publishes is a row the owner edits in the app (hours, days, the
// build's start, model and effort, the day's warning line, the cycle, the stories, the reply word, the note), each save a version he
// can go back to, started by the hub's own minute clock. The old `N8:<key>` refs of §59.7.1 keep resolving ([FlowDef.legacyRef]).

/** The round of weeks: [hours] one per week (`null`: that week's best hour, §49), [days] Saturday = 0 … Friday = 6 (the publish day). */
@Serializable
data class FlowDefSchedule(
    val hours: List<String?> = emptyList(),
    val bestWeek: Boolean = false,
    val days: List<Int> = listOf(0, 1, 2, 3, 4, 5, 6),
    val stories: List<String> = emptyList(),
    val triggerAt: String = "",
    val sameDay: Boolean = false,
    val start: String = "",
    val whenFa: String = "",
)

/** ⟨the owner, 2026-11-17⟩ [usdCap] is the day's warning line, never a stop; no month envelope applies to automations. */
@Serializable
data class FlowDefBudget(
    val usdCap: Double = 0.0,
    val monthEstimateUsd: Double = 0.0,
    val envelopeUsd: Double? = null,
    val envelopeLeftUsd: Double? = null,
    val overEnvelope: Boolean = false,
)

@Serializable
data class FlowDefNext(val buildAt: String = "", val publishAt: String = "", val kindFa: String? = null)

@Serializable
data class FlowDefToday(val runs: Int = 0, val published: Int = 0, val costUsd: Double = 0.0)

/** `ok` · `warn` · `down`, said plainly. */
@Serializable
data class FlowDefHealth(val state: String = "ok", val noteFa: String = "")

/** One automation (§61.1). */
@Serializable
data class FlowDef(
    val ref: String = "",
    val key: String = "",
    val company: String = "",
    val companyFa: String = "",
    val channel: String = "instagram",
    /** "" for a pilot that publishes nothing. */
    val account: String = "",
    val titleFa: String = "",
    val kit: String = "",
    val kitFa: String = "",
    /** `reel` · `stories` · `short` · `video` · `article` · `tg_post` */
    val kind: String = "reel",
    /** `on` · `off` · `paused` */
    val state: String = "on",
    val pausedUntil: String? = null,
    val schedule: FlowDefSchedule = FlowDefSchedule(),
    val model: String = "",
    val modelFa: String = "",
    /** `high` · `xhigh` · `max` */
    val effort: String = "xhigh",
    val budget: FlowDefBudget = FlowDefBudget(),
    val cycle: List<String> = emptyList(),
    /** `fixed` · `fresh` */
    val storyWordMode: String = "fresh",
    val storyWord: String? = null,
    val noteFa: String? = null,
    val pair: String? = null,
    val recipe: String? = null,
    val version: Int = 1,
    val next: FlowDefNext? = null,
    val today: FlowDefToday = FlowDefToday(),
    val monthCostUsd: Double = 0.0,
    val health: FlowDefHealth = FlowDefHealth(),
    val alertsOpen: Int = 0,
    /** `N8:<key>`: the same automation in §59.7.1's routes (its map, its days). */
    val legacyRef: String = "",
    val createdAt: String? = null,
    val updatedAt: String? = null,
)

/** `GET /automations/flows`. */
@Serializable
data class FlowList(val items: List<FlowDef> = emptyList(), val health: List<Health> = emptyList(), val today: FlowDefToday = FlowDefToday())

@Serializable
data class ModelOption(val id: String = "", val nameFa: String = "", val efforts: List<String> = emptyList())

@Serializable
data class UsdRange(val min: Int = 1, val max: Int = 500)

/** A kit that runs today (§61.5). */
@Serializable
data class FlowKit(
    val key: String = "",
    val titleFa: String = "",
    val aboutFa: String = "",
    val kinds: List<String> = emptyList(),
    val avgUsd: Double? = null,
    val avgMinutes: Double? = null,
    val usedOn: List<String> = emptyList(),
)

/** `GET /automations/flows/options`: what the editor may offer; the app never writes a model of its own. */
@Serializable
data class FlowOptions(
    val models: List<ModelOption> = emptyList(),
    val efforts: List<String> = listOf("high", "xhigh", "max"),
    val usdCap: UsdRange = UsdRange(),
    val storiesMax: Int = 15,
    val cycleMax: Int = 7,
    val noteMax: Int = 2000,
    val kits: List<FlowKit> = emptyList(),
)

/** One field of a save, in the owner's words. */
@Serializable
data class FlowChange(val field: String = "", val labelFa: String = "", val beforeFa: String = "", val afterFa: String = "")

@Serializable
data class FlowVersion(
    val version: Int = 1,
    val at: String = "",
    val byFa: String = "",
    val noteFa: String? = null,
    val changes: List<FlowChange> = emptyList(),
    val body: JsonObject? = null,
)

/** One day of a flow (`GET …/runs`). */
@Serializable
data class FlowRunDay(
    val run: String = "",
    val day: String = "",
    val state: String = "",
    val topicFa: String? = null,
    val startedAt: String? = null,
    val endedAt: String? = null,
    val costUsd: Double = 0.0,
    val publications: List<PublicationCard> = emptyList(),
    val noteFa: String = "",
)

@Serializable
data class FlowRunDays(val items: List<FlowRunDay> = emptyList(), val next: String? = null)

/** A code-made alert (§61.6): `run_failed` · `cap_reached` · `page_held` · `login_expired` · `clock_missed` · `late`. */
@Serializable
data class FlowAlert(
    val kind: String = "",
    val state: String = "open",
    val openedAt: String = "",
    val closedAt: String? = null,
    val noteFa: String = "",
)

@Serializable
data class SuccessRatio(val ok: Int = 0, val all: Int = 0)

@Serializable
data class CostPair(val today: Double = 0.0, val month: Double = 0.0)

/** `GET …/health`. */
@Serializable
data class FlowHealthReport(
    val state: String = "ok",
    val noteFa: String = "",
    val lastRun: FlowRunDay? = null,
    val success30d: SuccessRatio = SuccessRatio(),
    val cost: CostPair = CostPair(),
    val next: FlowDefNext? = null,
    val alerts: List<FlowAlert> = emptyList(),
)

@Serializable
data class WeekTotals(val runs: Int = 0, val published: Int = 0, val costUsd: Double = 0.0)

@Serializable
data class WeekDay(val day: String = "", val published: Int = 0, val planned: Int = 0)

@Serializable
data class WeekAccount(
    val company: String = "",
    val companyFa: String = "",
    val account: String = "",
    val runs: Int = 0,
    val published: Int = 0,
    val costUsd: Double = 0.0,
    val flows: Int = 0,
    val best: PublicationCard? = null,
)

/** `GET /automations/week`. */
@Serializable
data class FlowWeek(
    val from: String = "",
    val to: String = "",
    val totals: WeekTotals = WeekTotals(),
    val byDay: List<WeekDay> = emptyList(),
    val accounts: List<WeekAccount> = emptyList(),
)

/** `409 version_conflict` / `already_ran`, `422 invalid_flow` carry their Persian lines; the editor shows each under its field. */
@Serializable
data class FieldError(val field: String = "", val messageFa: String = "")
