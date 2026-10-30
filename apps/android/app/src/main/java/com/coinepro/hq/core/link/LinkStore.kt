package com.coinepro.hq.core.link

import android.content.Context

/**
 * What the background link keeps between process starts (the system may end the process and the watchdog or a reboot start it again):
 * the owner's switch, the pause until the app is opened, where the alert lane of the stream stopped (so it resumes with Last-Event-ID),
 * the events already told (so a replay never repeats one) and what the orders tracker had already said. Never a token or a body.
 */
interface LinkStore {
    /** The owner's switch; null until they touch it (then it follows the notification permission: on once it is granted). */
    var enabled: Boolean?

    /** «قطع تا بازگشت»: off until the app is opened again. */
    var pausedUntilReturn: Boolean

    /** The alert lane's last event id (the hub's JetStream sequence) and when it was saved (wall clock, ms). */
    var lastEventId: String?
    var lastEventAt: Long

    /** Whether the «برای ادامه‌ی اعلان‌ها وارد شو» notice is on show (so it is posted once and taken away after sign-in). */
    var expiredShown: Boolean

    /** The orders tracker's memory: every notice it told, and every order it knew (so a notice missed while the process was gone is told
     *  once it is back, and an order seen for the first time does not repeat what it had already reached). */
    var ordersTold: Set<String>
    var ordersKnown: Set<String>

    /** Whether [key] (an event id or an alert's subject) was already told. */
    fun told(key: String): Boolean

    /** Remembers [key]; the oldest are forgotten past [KEEP]. */
    fun remember(key: String)

    companion object {
        const val KEEP = 400
        /** A saved Last-Event-ID older than this is not resumed: what happened in between is read from the hub instead. */
        const val RESUME_MS = 6 * 60 * 60 * 1000L
    }
}

/** The demo, the tests and a session without a phone: nothing survives the process. */
class MemoryLinkStore : LinkStore {
    override var enabled: Boolean? = null
    override var pausedUntilReturn = false
    override var lastEventId: String? = null
    override var lastEventAt = 0L
    override var expiredShown = false
    override var ordersTold: Set<String> = emptySet()
    override var ordersKnown: Set<String> = emptySet()
    private val keys = LinkedHashSet<String>()

    @Synchronized override fun told(key: String) = key in keys

    @Synchronized override fun remember(key: String) {
        keys.remove(key)
        keys.add(key)
        while (keys.size > LinkStore.KEEP) keys.remove(keys.first())
    }
}

/** The real session's store: the app's private preferences (excluded from backups like the rest). */
class PrefsLinkStore(context: Context) : LinkStore {
    private val sp = context.getSharedPreferences("hq.link", Context.MODE_PRIVATE)
    private val keys: LinkedHashSet<String> = LinkedHashSet(sp.getString(K_TOLD, null)?.split('\n')?.filter { it.isNotBlank() }.orEmpty())

    override var enabled: Boolean?
        get() = if (sp.contains(K_ENABLED)) sp.getBoolean(K_ENABLED, true) else null
        set(v) { sp.edit().apply { if (v == null) remove(K_ENABLED) else putBoolean(K_ENABLED, v) }.apply() }

    override var pausedUntilReturn: Boolean
        get() = sp.getBoolean(K_PAUSED, false)
        set(v) { sp.edit().putBoolean(K_PAUSED, v).apply() }

    override var lastEventId: String?
        get() = sp.getString(K_LAST, null)
        set(v) { sp.edit().putString(K_LAST, v).apply() }

    override var lastEventAt: Long
        get() = sp.getLong(K_LAST_AT, 0L)
        set(v) { sp.edit().putLong(K_LAST_AT, v).apply() }

    override var expiredShown: Boolean
        get() = sp.getBoolean(K_EXPIRED, false)
        set(v) { sp.edit().putBoolean(K_EXPIRED, v).apply() }

    override var ordersTold: Set<String>
        get() = sp.getStringSet(K_ORDERS_TOLD, emptySet()).orEmpty().toSet()
        set(v) { sp.edit().putStringSet(K_ORDERS_TOLD, v.toList().takeLast(ORDERS_KEEP).toSet()).apply() }

    override var ordersKnown: Set<String>
        get() = sp.getStringSet(K_ORDERS_KNOWN, emptySet()).orEmpty().toSet()
        set(v) { sp.edit().putStringSet(K_ORDERS_KNOWN, v.toList().takeLast(ORDERS_KEEP).toSet()).apply() }

    @Synchronized override fun told(key: String) = key in keys

    @Synchronized override fun remember(key: String) {
        keys.remove(key)
        keys.add(key)
        while (keys.size > LinkStore.KEEP) keys.remove(keys.first())
        sp.edit().putString(K_TOLD, keys.joinToString("\n")).apply()
    }

    private companion object {
        const val K_ENABLED = "enabled"
        const val K_PAUSED = "paused_until_return"
        const val K_LAST = "last_event_id"
        const val K_LAST_AT = "last_event_at"
        const val K_EXPIRED = "expired_shown"
        const val K_ORDERS_TOLD = "orders_told"
        const val K_ORDERS_KNOWN = "orders_known"
        const val K_TOLD = "told"
        /** An order has at most four notices; the newest hundred orders are what the tracker reads. */
        const val ORDERS_KEEP = 1000
    }
}
