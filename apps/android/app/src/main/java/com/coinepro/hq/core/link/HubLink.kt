package com.coinepro.hq.core.link

import com.coinepro.hq.core.data.LaneStatus
import com.coinepro.hq.core.data.LinkPhase
import com.coinepro.hq.core.data.StreamMode
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.Deliverable
import com.coinepro.hq.core.net.Notification
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.launch

/** What the settings and the background link's own notification show. */
enum class LinkShown { LIVE, CONNECTING, DOWN, OFF, PAUSED, NO_PERMISSION, SIGNED_OUT }

data class LinkView(val shown: LinkShown, val why: String? = null) {
    /** «وصل، زنده», «در حال اتصال…», «قطع: اینترنت نیست»… */
    val fa: String get() = when (shown) {
        LinkShown.LIVE -> "وصل، زنده"
        LinkShown.CONNECTING -> "در حال اتصال…"
        LinkShown.DOWN -> "قطع: " + LinkPolicy.whyFa(why)
        LinkShown.OFF -> "خاموش"
        LinkShown.PAUSED -> "قطع تا وقتی اپ را دوباره باز کنی"
        LinkShown.NO_PERMISSION -> "اجازه‌ی اعلان داده نشده"
        LinkShown.SIGNED_OUT -> "بیرون از حساب؛ اول وارد شو"
    }
}

/** What the decisions read: the owner's switch, the phone's permission, the session and the pause. */
data class LinkInputs(val pref: Boolean?, val allowed: Boolean, val signedIn: Boolean, val paused: Boolean)

/** The background link's decisions, with no Android in them (`LinkPolicyTest`). */
object LinkPolicy {
    /** The switch as the owner sees it: their choice, or, before they made one, on once notifications are allowed. */
    fun switchOn(i: LinkInputs): Boolean = (i.pref ?: true) && i.allowed

    /** Whether the foreground service should run (and the watchdog watch it): signed in, allowed, switched on, not paused. */
    fun wantService(i: LinkInputs): Boolean = i.signedIn && !i.paused && switchOn(i)

    /** What the stream keeps open: everything while the app is on screen, the alert lane while the service runs, otherwise nothing. */
    fun mode(i: LinkInputs, foreground: Boolean): StreamMode = when {
        !i.signedIn -> StreamMode.OFF
        foreground -> StreamMode.FULL
        wantService(i) -> StreamMode.ALERTS
        else -> StreamMode.OFF
    }

    /** After a reboot or an update of the app: start again only if it should run. */
    fun onBoot(i: LinkInputs): Boolean = wantService(i)

    /** What the owner reads about the link. */
    fun view(i: LinkInputs, lane: LaneStatus, refused: Boolean = false): LinkView = when {
        !i.signedIn -> LinkView(LinkShown.SIGNED_OUT)
        !i.allowed -> LinkView(LinkShown.NO_PERMISSION)
        i.pref == false -> LinkView(LinkShown.OFF)
        i.paused -> LinkView(LinkShown.PAUSED)
        refused -> LinkView(LinkShown.DOWN, "start refused")
        lane.phase == LinkPhase.LIVE -> LinkView(LinkShown.LIVE)
        lane.phase == LinkPhase.CONNECTING || lane.phase == LinkPhase.OFF -> LinkView(LinkShown.CONNECTING)
        lane.phase == LinkPhase.WAITING_NETWORK -> LinkView(LinkShown.DOWN, "no network")
        else -> LinkView(LinkShown.DOWN, lane.why)
    }

    /** Why the link is down, in Persian. */
    fun whyFa(why: String?): String = when {
        why == null -> "دوباره وصل میشوم"
        why == "no network" -> "اینترنت نیست؛ با برگشتنش وصل میشوم"
        why == "network changed" -> "شبکه عوض شد؛ دوباره وصل میشوم"
        why == "session expired" -> "نشست تمام شد؛ دوباره وارد شو"
        why == "start refused" -> "اندروید اجازه‌ی شروع در پس‌زمینه نداد؛ یک بار اپ را باز کن"
        why == "HTTP 422" -> "ستاد این اتصال را نپذیرفت"
        why.startsWith("silent") -> "اتصال بی‌صدا ماند؛ دوباره وصل میشوم"
        else -> "ستاد جواب نمیدهد؛ خودکار دوباره تلاش میکنم"
    }
}

/** The stream as the link drives it ([com.coinepro.hq.core.data.HoldingStream]). */
interface LinkStream {
    val mode: StateFlow<StreamMode>
    val alertLane: StateFlow<LaneStatus>
    fun setMode(m: StreamMode)
    fun nudge()
}

/** A session as the link sees it (the app's [Env], real or demo). */
interface LinkSession {
    val signedIn: StateFlow<Boolean>
    val linkStream: LinkStream
    val demo: Boolean
    fun startAlerts()
    fun stopAlerts()
}

/** Starts and stops the foreground service and its watchdog (the device's, or a fake in the tests). */
interface ServiceControl {
    /** Asks for the foreground service; false when the system refused (a background start Android does not allow). */
    fun start(reason: String): Boolean
    fun stop()
    fun watchdog(on: Boolean)
}

/**
 * The background link, for the whole process: it decides what the stream keeps open ([LinkPolicy.mode]), runs the alerts while anything is
 * open, and keeps the foreground service (`device/HubLinkService`) running while the owner wants alerts with the app closed. The service
 * holds nothing itself: it keeps the process in the foreground so the stream's alert lane (the same connection the app uses, never a
 * second one) stays open, and shows the link's state.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class HubLink(
    private val store: LinkStore,
    private val env: StateFlow<LinkSession>,
    private val sink: AlertSink,
    private val service: ServiceControl,
    /** «خطاخوان» at info level, collapsed ([LinkJournal]); null in the tests. */
    private val note: ((title: String, detail: String) -> Unit)? = null,
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate),
    private val now: () -> Long = System::currentTimeMillis,
) {
    private val fg = MutableStateFlow(false)
    val foreground: StateFlow<Boolean> = fg.asStateFlow()
    private val up = MutableStateFlow(false)
    /** Whether the foreground service is running. */
    val serviceRunning: StateFlow<Boolean> = up.asStateFlow()
    private val refused = MutableStateFlow(false)
    private val tick = MutableStateFlow(0)
    private val viewFlow = MutableStateFlow(LinkView(LinkShown.OFF))
    val view: StateFlow<LinkView> = viewFlow.asStateFlow()
    private val journal = note?.let { LinkJournal(it) }
    private var lastPhase: LinkPhase = LinkPhase.OFF
    private var watchdogOn: Boolean? = null

    fun inputs(e: LinkSession = env.value): LinkInputs = LinkInputs(store.enabled, sink.allowed(), e.signedIn.value, store.pausedUntilReturn)

    /** Begins following the session and the stream (once, from the application). */
    fun attach() {
        scope.launch {
            env.flatMapLatest { e -> combine(e.signedIn, tick) { s, _ -> s } }.collect { reconcile() }
        }
        scope.launch {
            env.flatMapLatest { e -> combine(e.linkStream.alertLane, tick, refused) { lane, _, r -> lane to r } }.collectLatest { (lane, r) ->
                viewFlow.value = LinkPolicy.view(inputs(), lane, r)
                journalLane(lane)
            }
        }
    }

    /** The app came to the screen or left it. Coming back ends «قطع تا بازگشت». */
    fun setForeground(on: Boolean) {
        if (on && store.pausedUntilReturn) store.pausedUntilReturn = false
        // On screen, Android lets the app start its service: a refusal in the background is tried again.
        if (on) refused.value = false
        fg.value = on
        reconcile()
    }

    /** The owner's switch in the settings. */
    fun setEnabled(on: Boolean) {
        store.enabled = on
        store.pausedUntilReturn = false
        note("link switched", if (on) "the owner switched the background link on" else "the owner switched the background link off")
        reconcile()
    }

    /** «قطع تا بازگشت» on the link's notification: off until the app is opened again. */
    fun pauseUntilReturn() {
        store.pausedUntilReturn = true
        note("link paused", "paused from its notification until the app is opened")
        reconcile()
    }

    /** Something outside changed (the notification permission, the app lock): read everything again. */
    fun refresh() { tick.value++ }

    fun serviceUp() {
        up.value = true
        refused.value = false
        reconcile()
    }

    fun serviceDown() {
        up.value = false
        reconcile()
    }

    /**
     * After a reboot, an update of the app, or the watchdog: start the service again if it should run and is not running. Returns
     * whether it is running (or was asked to start).
     */
    fun revive(reason: String): Boolean {
        val i = inputs()
        if (!LinkPolicy.onBoot(i)) { watchdogOn = false; service.watchdog(false); return false }
        watchdogOn = true
        service.watchdog(true)
        if (up.value) { env.value.linkStream.nudge(); return true }
        val ok = service.start(reason)
        refused.value = !ok
        note(if (ok) "link restarted" else "link start refused", if (ok) "the background link was started again ($reason)" else "Android did not let the background link start ($reason)")
        return ok
    }

    /** The hub answered 401: the session is gone. With the app closed the owner is told once; the link stops either way. */
    fun expired() {
        if (env.value.demo) return
        val wanted = up.value || LinkPolicy.wantService(inputs().copy(signedIn = true))
        if (!fg.value && wanted && !store.expiredShown) {
            store.expiredShown = true
            sink.sessionExpired(true)
        }
        note("session expired", "the hub answered 401; the background link stops until the owner signs in")
    }

    /** Puts everything where the inputs say: the stream's lanes, the alerts, the service and its watchdog. */
    fun reconcile() {
        val e = env.value
        val i = inputs(e)
        if (i.signedIn && store.expiredShown) {
            store.expiredShown = false
            sink.sessionExpired(false)
        }
        val mode = LinkPolicy.mode(i, fg.value)
        e.linkStream.setMode(mode)
        if (mode == StreamMode.OFF) e.stopAlerts() else e.startAlerts()
        val want = LinkPolicy.wantService(i)
        if (watchdogOn != want) { watchdogOn = want; service.watchdog(want) }
        when {
            // Started from the screen (allowed); from the background only by [revive] (a reboot, an update, the watchdog), where Android's
            // exemptions are known. A process the system restarted for the sticky service gets the service back on its own.
            want && !up.value && fg.value -> refused.value = !service.start("app open")
            !want && up.value -> service.stop()
        }
        viewFlow.value = LinkPolicy.view(i, e.linkStream.alertLane.value, refused.value && !up.value)
    }

    private fun journalLane(lane: LaneStatus) {
        val before = lastPhase
        lastPhase = lane.phase
        // While the app is open the stream writes its own lines; the journal speaks for the link with the app closed.
        if (env.value.linkStream.mode.value != StreamMode.ALERTS || env.value.demo) return
        when {
            lane.phase == LinkPhase.LIVE && before != LinkPhase.LIVE -> journal?.live(now(), lane.resumed)
            before == LinkPhase.LIVE && lane.phase != LinkPhase.LIVE -> journal?.dropped(now(), lane.why ?: lane.phase.name.lowercase())
        }
    }

    private fun note(title: String, detail: String) {
        if (!env.value.demo) journal?.note(now(), title, detail)
    }
}

/** The alerts' reads, from the API. */
class ApiAlertSource(private val api: Api) : AlertSource {
    override suspend fun unread(limit: Int): List<Notification> = api.notifications(unread = true, limit = limit).items

    override suspend fun decisionStatus(ref: String): String? = runCatching { api.decision(ref).status }.getOrNull()

    override suspend fun deliverable(ref: String): OutputBrief? = runCatching {
        val d: Deliverable = api.deliverable(ref)
        OutputBrief(d.ref, d.title, d.company, d.seenAt != null, d.kind == "report")
    }.getOrNull()
}
