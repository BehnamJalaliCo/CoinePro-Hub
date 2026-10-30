package com.coinepro.hq.core

import android.content.Context
import com.coinepro.hq.BuildConfig
import com.coinepro.hq.Demo
import com.coinepro.hq.core.auth.Auth
import com.coinepro.hq.core.auth.DemoTokens
import com.coinepro.hq.core.auth.SessionTokens
import com.coinepro.hq.core.auth.TokenVault
import com.coinepro.hq.core.auth.VaultTokens
import com.coinepro.hq.core.data.HoldingStream
import com.coinepro.hq.core.data.QueryCache
import com.coinepro.hq.core.media.MediaKit
import com.coinepro.hq.core.net.Api
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Everything one session needs: the API, auth, the query cache, the live stream and media loading. A demo session
 *  (debug builds) swaps the network for fixtures and lives beside the real one without touching its token. */
class Env(
    val api: Api,
    val auth: Auth,
    val cache: QueryCache,
    val stream: HoldingStream,
    val media: MediaKit,
    override val demo: Boolean,
    private val scope: CoroutineScope,
    /** When the screens are reading from the phone's offline copy (M13), the instant it was saved; null when live. */
    val offlineSince: StateFlow<String?> = MutableStateFlow(null),
    /** ⟨1.7.3⟩ outputs marked seen on the phone while the hub could not keep it. */
    val seen: com.coinepro.hq.core.data.SeenStore = com.coinepro.hq.core.data.SeenStore.memory(),
    /** Whether the hub answers (a restart's burst of 502s turns into one banner and a quiet wait). */
    val hub: com.coinepro.hq.core.net.HubHealth = com.coinepro.hq.core.net.HubHealth(),
    /** The logo and colour the founding wizard kept for a company the hub has not made yet. */
    val foundingBrand: com.coinepro.hq.core.data.FoundingBrandStore = com.coinepro.hq.core.data.FoundingBrandStore.memory(),
    /** The background link's memory (told events, the orders tracker's); the demo's lives in memory. */
    linkStore: com.coinepro.hq.core.link.LinkStore = com.coinepro.hq.core.link.MemoryLinkStore(),
    /** Where alerts go with the app off screen (the phone's notifications). */
    sink: com.coinepro.hq.core.link.AlertSink = com.coinepro.hq.core.link.NoAlerts,
    /** Whether the app is on screen (then the app's toasts speak, not the notifications). */
    foreground: () -> Boolean = { true },
    /** Keeps the CPU awake for a moment while an alert is read and told. */
    awake: (Long) -> Unit = {},
) : com.coinepro.hq.core.link.LinkSession {
    override val signedIn: StateFlow<Boolean> get() = auth.signedIn
    override val linkStream: com.coinepro.hq.core.link.LinkStream get() = stream

    /** Work refs and titles for lines that carry only an id (the live stream). */
    val works = com.coinepro.hq.core.data.WorkTitles(scope) { key ->
        try {
            api.workOne(key)
        } catch (e: com.coinepro.hq.core.net.ApiException) {
            if (e.status == 404) { e.logged?.let { api.failures?.forget(it) }; null } else throw e
        }
    }

    /** Notifications marked read: sent to the hub after a short grace (undo), at once when opened. */
    val reads: com.coinepro.hq.core.data.NotificationReads = com.coinepro.hq.core.data.NotificationReads(
        scope,
        readOne = { id -> api.readNotification(id) },
        readAll = { before, level -> api.readAll(before, level) },
        onSent = { cache.invalidate("notifications", "inbox") },
        onMarked = { ids -> alerts.read(ids) },
    )

    /** The owner's orders, watched on the stream for a change of stage. */
    val orders = com.coinepro.hq.core.data.OrderWatcher(api, stream.events, scope, works, linkStore)

    /** The stream's events and the orders' notices made alerts: a toast with the app on screen, a notification otherwise. */
    val alerts: com.coinepro.hq.core.link.AlertCenter = com.coinepro.hq.core.link.AlertCenter(
        scope, com.coinepro.hq.core.link.ApiAlertSource(api), linkStore, sink, foreground,
        readHere = { it in reads.marked.value },
        seenHere = { it in seen.refs.value },
        ownerOrder = orders::owns,
        awake = awake,
    )

    init {
        // An order's notice refreshes what shows orders and work.
        scope.launch { orders.notices.collect { cache.invalidate("work", "orders") } }
    }

    /** The alerts and the orders tracker run while the stream has anything open ([com.coinepro.hq.core.link.HubLink]). */
    override fun startAlerts() {
        orders.start()
        alerts.start(stream.events, orders.notices)
    }

    override fun stopAlerts() {
        alerts.stop()
        orders.stop()
    }

    fun close() {
        stream.stop()
        stopAlerts()
        scope.cancel()
    }
}

/** Manual dependency graph (the app is small enough that a DI framework would only add weight). */
class AppGraph(context: Context) {
    private val app = context.applicationContext
    private val vault = TokenVault(app)
    val prefs = Prefs(app)
    val lock = com.coinepro.hq.device.AppLock(app, prefs)
    /** The real session's offline copy; the demo never touches it. */
    val offline = com.coinepro.hq.core.net.OfflineCache(app)
    /** «خطاخوان»: the last failed calls, contract mismatches and crashes, on this phone only (the demo never writes to it). */
    val errors = com.coinepro.hq.core.diag.ErrorLog(app).also { it.installCrashHandler() }
    /** ⟨1.7.3⟩ outputs the owner marked seen while the hub could not keep it (before ⟨1.7.3⟩). */
    val seen = com.coinepro.hq.core.data.SeenStore(app)
    private val foundingBrand = com.coinepro.hq.core.data.FoundingBrandStore(app)
    /** The background link's memory for the real session (the switch, the pause, the last event, what was told). */
    val linkStore = com.coinepro.hq.core.link.PrefsLinkStore(app)
    /** The phone's network, from a callback: the stream waits for it instead of retrying blind, and reconnects when it changes. */
    val network = com.coinepro.hq.core.link.NetworkWatch(app).also { it.start() }
    /** The phone's notifications for the alerts (channels, groups, the lock screen's public version). */
    val notifier = com.coinepro.hq.device.AlertNotifier(app) { lock.enabled() }
    private val wake = com.coinepro.hq.device.Wake(app)
    private var linkRef: com.coinepro.hq.core.link.HubLink? = null

    private val envFlow = MutableStateFlow(build(VaultTokens(vault), demo = false))
    val env: StateFlow<Env> = envFlow.asStateFlow()

    /** The background link: what the stream keeps open, the alerts, the foreground service and its watchdog. */
    val link: com.coinepro.hq.core.link.HubLink = com.coinepro.hq.core.link.HubLink(
        linkStore, env, notifier, com.coinepro.hq.device.HubLinkService.control(app),
        note = { title, detail -> errors.note("link", com.coinepro.hq.core.diag.LEVEL_INFO, title, detail) },
    ).also { linkRef = it }

    val demoAvailable: Boolean get() = Demo.available

    fun enterDemo() {
        if (!Demo.available) return
        swap(build(DemoTokens(::leaveDemo), demo = true))
    }

    private fun leaveDemo() = swap(build(VaultTokens(vault), demo = false))

    private fun swap(next: Env) {
        val old = envFlow.value
        envFlow.value = next
        old.close()
        linkRef?.reconcile()
    }

    private fun build(tokens: SessionTokens, demo: Boolean): Env {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        val api = Api(BuildConfig.HQ_ORIGIN, tokens, if (demo) Demo.interceptor() else offline)
        if (!demo) api.failures = errors
        com.coinepro.hq.core.diag.Diag.log = if (demo) null else errors
        val hub = com.coinepro.hq.core.net.HubHealth()
        api.hub = hub
        val cache = QueryCache(scope, hub)
        val stream = HoldingStream(
            api, cache, scope, demo, if (demo) null else errors,
            net = if (demo) com.coinepro.hq.core.link.AlwaysOnline else network, store = if (demo) null else linkStore,
        )
        watchHub(hub, api, scope, if (demo) null else errors)
        api.onExpired = { scope.launch { linkRef?.expired() } }
        return Env(
            api, Auth(api, tokens, demo), cache, stream, MediaKit(app, api), demo, scope,
            if (demo) MutableStateFlow(null) else offline.since,
            seen = if (demo) com.coinepro.hq.core.data.SeenStore.memory() else seen,
            hub = hub,
            foundingBrand = if (demo) com.coinepro.hq.core.data.FoundingBrandStore.memory() else foundingBrand,
            linkStore = if (demo) com.coinepro.hq.core.link.MemoryLinkStore() else linkStore,
            sink = notifier,
            foreground = { linkRef?.foreground?.value ?: false },
            awake = { ms -> if (linkRef?.foreground?.value != true) wake.hold(ms) },
        )
    }
}

/** While the hub is away: probe it with a growing pause until it answers, and note in the log how long it was gone. */
private fun watchHub(hub: com.coinepro.hq.core.net.HubHealth, api: Api, scope: CoroutineScope, log: com.coinepro.hq.core.diag.ErrorLog?) {
    scope.launch {
        hub.state.collectLatest { s ->
            if (s != com.coinepro.hq.core.net.HubState.RESTARTING) return@collectLatest
            log?.crumb("hub unreachable")
            var attempt = 0
            while (hub.outage) {
                delay(com.coinepro.hq.core.net.HubHealth.backoff(attempt++))
                if (api.probe()) hub.ok()
            }
        }
    }
    scope.launch {
        hub.recovered.collect { ms ->
            log?.note("hub", com.coinepro.hq.core.diag.LEVEL_INFO, "hub reachable again", "the hub answered again after ${(ms + 500) / 1000} s")
        }
    }
}

/** Small device-local preferences (theme, app lock). Never secrets. */
class Prefs(context: Context) {
    private val sp = context.getSharedPreferences("hq.prefs", Context.MODE_PRIVATE)
    private val themeFlow = MutableStateFlow(ThemeMode.entries.firstOrNull { it.name == sp.getString("theme", null) } ?: ThemeMode.SYSTEM)
    val theme: StateFlow<ThemeMode> = themeFlow.asStateFlow()

    fun setTheme(mode: ThemeMode) {
        sp.edit().putString("theme", mode.name).apply()
        themeFlow.value = mode
    }

    private val lockFlow = MutableStateFlow(sp.getBoolean("app_lock", true))
    /** The app lock (M11); on by default, effective only when the phone has a secure lock screen. */
    val appLock: StateFlow<Boolean> = lockFlow.asStateFlow()

    fun setAppLock(on: Boolean) {
        sp.edit().putBoolean("app_lock", on).apply()
        lockFlow.value = on
    }
}

enum class ThemeMode { NIGHT, DAY, SYSTEM }
