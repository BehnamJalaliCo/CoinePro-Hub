package com.coinepro.hq.core.net

import kotlinx.serialization.Serializable

// Contract §38.3 ⟨1.20⟩: the owner's «سرویس‌ها» page. Each optional service of the hub on or off with one switch, the free memory above;
// his word is audited and the hub-ops dispatcher runs it, the memory budget checked, and the answer comes back as a job.

/** The dispatcher's latest snapshot (≤ 60 s old). Null while it has never reported: the hub part is not installed yet. */
@Serializable
data class HubMemory(
    @Serializable(with = LenientDouble::class) val totalMb: Double = 0.0,
    @Serializable(with = LenientDouble::class) val budgetMb: Double = 0.0,
    @Serializable(with = LenientDouble::class) val capsMb: Double = 0.0,
    @Serializable(with = LenientDouble::class) val freeMb: Double = 0.0,
)

@Serializable
data class HubService(
    val key: String = "",
    val titleFa: String = "",
    /** One plain line: what it is for. */
    val whatFa: String = "",
    /** on · off · starting · failed */
    val state: String = "off",
    val optional: Boolean = false,
    @Serializable(with = LenientDouble::class) val memCapMb: Double = 0.0,
    val memUsedMb: Double? = null,
    val canToggle: Boolean = false,
    val noteFa: String? = null,
)

/** `GET /hub/services`. */
@Serializable
data class HubServices(val memory: HubMemory? = null, val services: List<HubService> = emptyList(), val at: String? = null)

/** An optional service that is on and holds memory another one needs (largest first). */
@Serializable
data class HubBlocking(val key: String = "", val titleFa: String = "", @Serializable(with = LenientDouble::class) val memCapMb: Double = 0.0)

/** `POST /hub/services/{key}` → 202, and `GET /hub/jobs/{ref}`: queued · running · done · failed · refused. */
@Serializable
data class HubJob(val ref: String = "", val state: String = "queued", val resultFa: String? = null, val blocking: List<HubBlocking> = emptyList()) {
    /** The job has its answer: done, failed, or refused by the memory budget. */
    val finished: Boolean get() = state == "done" || state == "failed" || state == "refused"
}

/** «در حال روشن شدن…» / «در حال خاموش شدن…»: a switch the owner just turned, until its job answers. */
fun hubPendingFa(on: Boolean): String = if (on) "در حال روشن شدن…" else "در حال خاموش شدن…"

/** A service's state as the owner reads it. */
fun hubStateFa(state: String): String = when (state) {
    "on" -> "روشن"
    "off" -> "خاموش"
    "starting" -> "در حال روشن شدن"
    "failed" -> "خطا"
    else -> state
}

/**
 * What to turn off so [need] fits ([freeMb] is free now): the blocking services largest first, as few as fit; all of them when even all
 * do not (the hub then says so again).
 */
fun hubToTurnOff(blocking: List<HubBlocking>, need: Double, freeMb: Double): List<HubBlocking> {
    val out = mutableListOf<HubBlocking>()
    var free = freeMb
    for (b in blocking.sortedByDescending { it.memCapMb }) {
        if (free >= need && out.isNotEmpty()) break
        out += b
        free += b.memCapMb
        if (free >= need) break
    }
    return out
}

/** «<x> را خاموش کن و <y> را روشن کن», the refused sheet's one tap. */
fun hubSwapFa(off: List<HubBlocking>, on: String): String = "${off.joinToString(" و ") { it.titleFa.ifBlank { it.key } }} را خاموش کن و $on را روشن کن"

/** Megabytes as a figure («1,536 MB»): Latin digits, as every figure of the app. */
fun mbFig(mb: Double): String = String.format(java.util.Locale.US, "%,d MB", mb.toLong())
