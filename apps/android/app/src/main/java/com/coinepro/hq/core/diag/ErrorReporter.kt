package com.coinepro.hq.core.diag

import android.content.Context
import com.coinepro.hq.core.net.Api
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.json.JsonArray

/** Which entries already reached the hub: their [ErrorReporter.keyOf]s, kept across launches. */
interface SentStore {
    fun keys(): Set<String>
    fun add(keys: Collection<String>)

    companion object {
        fun memory(): SentStore = object : SentStore {
            private val set = linkedSetOf<String>()
            @Synchronized override fun keys(): Set<String> = set.toSet()
            @Synchronized override fun add(keys: Collection<String>) { set.addAll(keys) }
        }
    }
}

/** The phone's record of what was sent, in the app's private preferences; only the last [ErrorReporter.KEEP] keys are kept. */
class PrefsSentStore(context: Context) : SentStore {
    private val sp = context.getSharedPreferences("hq.errors.sent", Context.MODE_PRIVATE)

    @Synchronized override fun keys(): Set<String> = sp.getString("keys", null)?.split('\n')?.filter { it.isNotBlank() }?.toSet().orEmpty()

    @Synchronized override fun add(keys: Collection<String>) {
        val all = (sp.getString("keys", null)?.split('\n')?.filter { it.isNotBlank() }.orEmpty() + keys).distinct().takeLast(ErrorReporter.KEEP)
        sp.edit().putString("keys", all.joinToString("\n")).apply()
    }
}

/**
 * ⟨1.10⟩ §28.3 «خطاخوان» reports to the hub: the log's errors and warnings (already masked on the phone, [ErrorLog.mask]) go to
 * `POST /client/errors` in batches of [BATCH], crashes first, then oldest first. Each entry goes once: what the hub took is marked in
 * [sent], and a failed batch is tried again on the next round (its own failure is taken back out of the log, so reporting never
 * reports itself). Rounds run at app start (a crash from the last run goes at once) and every [INTERVAL_MS] while the app is open,
 * only for a signed-in real session and only while the owner leaves «ارسال خطاها به ستاد» on.
 */
class ErrorReporter(
    private val entries: () -> List<ErrorEntry>,
    private val sent: SentStore,
    /** Sends one batch; throws when the hub did not take it. */
    private val upload: suspend (List<ErrorEntry>) -> Unit,
    /** The Settings switch, a real session and a signed-in owner. */
    private val allowed: () -> Boolean,
) {
    private val lock = Mutex()
    private val sentCount = MutableStateFlow(0)
    private var job: Job? = null

    /** How many of this version's entries reached the hub (for Settings). */
    val reported: StateFlow<Int> = sentCount.asStateFlow()

    init { recount() }

    /** One round: every entry not yet sent, in batches. Returns how many went. */
    suspend fun flush(): Int = lock.withLock {
        if (!allowed()) return 0
        val todo = pending(entries(), sent.keys())
        var n = 0
        for (batch in batches(todo)) {
            try {
                upload(batch)
            } catch (e: Exception) {
                if (e is kotlinx.coroutines.CancellationException) throw e
                break
            }
            sent.add(batch.map(::keyOf))
            n += batch.size
        }
        recount()
        n
    }

    /** Rounds while the app is open: one now, then every [INTERVAL_MS]. */
    fun start(scope: CoroutineScope) {
        if (job?.isActive == true) return
        job = scope.launch {
            while (true) {
                runCatching { flush() }
                delay(INTERVAL_MS)
            }
        }
    }

    fun stop() {
        job?.cancel()
        job = null
    }

    private fun recount() {
        val keys = sent.keys()
        sentCount.value = entries().count { keyOf(it) in keys }
    }

    /** The hub has no `/client/errors` yet: the round stops and the entries wait, unsent. */
    class NotServed : Exception("client errors not served by this hub")

    companion object {
        const val BATCH = 50
        const val INTERVAL_MS = 15 * 60 * 1000L
        /** Keys remembered on the phone (a version's log holds at most [ErrorLog.MAX]). */
        const val KEEP = 3000

        /** One entry's identity: its version, its number in that version's log and its first moment (a cleared log numbers again). */
        fun keyOf(e: ErrorEntry): String = "${e.app}#${e.id}#${e.at}"

        /** What should go: errors and warnings not yet sent (the session lines and other notes stay on the phone), crashes first,
         *  then oldest first. */
        fun pending(entries: List<ErrorEntry>, sent: Set<String>): List<ErrorEntry> =
            entries.filter { it.level != LEVEL_INFO && keyOf(it) !in sent }
                .sortedWith(compareBy<ErrorEntry>({ if (it.kind == "crash") 0 else 1 }, { it.at }, { it.id }))

        fun batches(entries: List<ErrorEntry>, size: Int = BATCH): List<List<ErrorEntry>> = entries.chunked(size)

        /** A batch as the wire carries it (snake_case, the same fields the log keeps). */
        fun wire(batch: List<ErrorEntry>): JsonArray =
            JsonArray(batch.map { Api.json.encodeToJsonElement(ErrorEntry.serializer(), it) })
    }
}
