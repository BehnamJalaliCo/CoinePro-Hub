package com.coinepro.hq.core.net

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// ------------------------------------------------------------------ v1.4.4 --
// The owner's tools on APIs the hub already serves (docs/GAP_ANALYSIS_v2.md §5A): resolutions, notification settings,
// message search, deploy freezes, work and employee actions, agent runs, the treasury's what-if, calls, quota and budgets,
// connections, site checks and incidents. Same rules as Models.kt: camelCase here, snake_case on the wire.

@Serializable
data class Resolution(
    val id: String = "",
    val ref: String,
    val company: String? = null,
    val title: String,
    val body: String = "",
    val source: Map<String, String?> = emptyMap(),
    val sealedBy: Actor? = null,
    val sealedAt: String,
    val sentTo: List<String> = emptyList(),
    val followUpWorkId: String? = null,
)

@Serializable
data class LevelSettings(val inApp: Boolean? = null, val push: Boolean? = null, val sound: Boolean? = null, val mutedUntil: String? = null)

@Serializable
data class NotificationSettings(val matrix: Map<String, Map<String, LevelSettings>> = emptyMap(), val version: Int = 1)

@Serializable
data class NotificationSettingsIn(val matrix: Map<String, Map<String, LevelSettings>>)

/** What one level does for one company: its own row over the "*" row over the contract's defaults (§6). */
fun NotificationSettings.effective(scope: String, level: String): LevelSettings {
    val all = matrix["*"]?.get(level)
    val own = if (scope == "*") null else matrix[scope]?.get(level)
    return LevelSettings(
        inApp = own?.inApp ?: all?.inApp ?: true,
        push = own?.push ?: all?.push ?: (level == "urgent" || level == "decision"),
        sound = own?.sound ?: all?.sound ?: (level == "urgent"),
        mutedUntil = own?.mutedUntil ?: all?.mutedUntil,
    )
}

@Serializable
data class SearchHit(
    val id: String,
    val ref: String,
    val thread: String,
    val author: Actor,
    val body: String = "",
    val kind: String = "text",
    val createdAt: String,
    val rank: Double = 0.0,
)

@Serializable
data class FreezeOut(val company: String, val active: Boolean, val until: String)

@Serializable
data class EvidenceIn(val kind: String, val ref: String, val note: String? = null)

@Serializable
data class WorkPatch(val title: String? = null, val brief: String? = null, val priority: String? = null, val dueAt: String? = null)

@Serializable
data class DismissOut(val workReturned: Int = 0, val transferWork: String? = null)

// ------------------------------------------------------------------ runs --
@Serializable
data class RunTokens(val input: Long = 0, val output: Long = 0, val cacheRead: Long = 0, val cacheWrite: Long = 0)

@Serializable
data class StepAction(val tool: String, val outcome: String, val ref: String? = null)

@Serializable
data class AgentStep(val n: Int, val at: String, val summaryFa: String = "", val actions: List<StepAction> = emptyList())

@Serializable
data class Run(
    val id: String,
    val employee: String,
    val company: String,
    val workRef: String? = null,
    val thread: String? = null,
    val state: String,
    val trigger: String = "",
    val reason: String = "",
    val priority: String = "P3",
    val model: String? = null,
    val effort: String? = null,
    val queuedAt: String,
    val startedAt: String? = null,
    val finishedAt: String? = null,
    val steps: Int = 0,
    val toolCalls: Int = 0,
    val tokens: RunTokens = RunTokens(),
    val equivCostUsd: String = "0",
    val errorCode: String? = null,
    val stepsDetail: List<AgentStep> = emptyList(),
)

// -------------------------------------------------------------- treasury --
@Serializable
data class Subscription(
    val status: String = "ok",
    val window: String? = null,
    val resetsAt: String? = null,
    val source: String? = null,
    val utilization: String? = null,
    val connection: String? = null,
    val changedAt: String? = null,
)

@Serializable
data class Throttle(val pausedPriorities: List<String> = emptyList())

@Serializable
data class QuotaView(val subscription: Subscription = Subscription(), val throttle: Throttle = Throttle())

@Serializable
data class WhatIf(
    val model: String,
    val calls: Long = 0,
    val pricedCalls: Long = 0,
    val actualUsd: String = "0",
    val whatIfUsd: String? = null,
    val differenceUsd: String? = null,
    val sourceUrl: String? = null,
    val asOf: String? = null,
)

@Serializable
data class CallRow(
    val id: String,
    val startedAt: String,
    val actor: String,
    val company: String,
    val workRef: String? = null,
    val model: String? = null,
    val status: String,
    val errorClass: String? = null,
    val inputTokens: Long? = null,
    val outputTokens: Long? = null,
    val cacheReadTokens: Long? = null,
    val latencyMs: Long? = null,
    val equivCostUsd: String? = null,
)

/** One row of PUT /budgets (§9); the whole body is sealed on its SHA-256. */
@Serializable
data class BudgetRowIn(
    val company: String,
    val scopeType: String,
    val scopeRef: String,
    val period: String,
    val tokenLimit: Long? = null,
    val usdLimit: String? = null,
    val enabled: Boolean = true,
)

@Serializable
data class BudgetsBody(val budgets: List<BudgetRowIn>)

@Serializable
data class ConnectionPatch(val displayName: String? = null, val status: String? = null)

// ------------------------------------------------------------------- ops --
@Serializable
data class SiteCheck(val at: String? = null, val status: Int? = null, val ms: Long? = null, val ok: Boolean? = null, val error: String? = null)

@Serializable
data class Site(
    val id: String,
    val company: String,
    val url: String,
    val kind: String = "web",
    val method: String = "GET",
    val intervalS: Int = 60,
    val enabled: Boolean = true,
    val canary: Boolean = false,
    val consecutiveFailures: Int = 0,
    val last: SiteCheck? = null,
    @SerialName("uptime_24h") val uptime24h: Double? = null,
    val version: Int = 1,
)

@Serializable
data class SiteIn(val url: String, val kind: String = "web", val method: String = "GET", val intervalS: Int = 60, val enabled: Boolean = true)

@Serializable
data class SitesBody(val company: String, val sites: List<SiteIn>)

@Serializable
data class Incident(
    val id: String,
    val ref: String,
    val company: String,
    val url: String,
    val severity: String = "medium",
    val openedAt: String,
    val closedAt: String? = null,
    val checksFailed: Int = 0,
    val lastStatus: Int? = null,
    val lastError: String? = null,
    val workRef: String? = null,
)

@Serializable
data class CompanyIn(val code: String, val nameFa: String, val nameEn: String, val template: String = "standard")
