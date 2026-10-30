package com.coinepro.hq.core.link

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow

/** Whether the phone has a network, and when its default network changes (the stream reconnects on the new one at once). */
interface Connectivity {
    val online: StateFlow<Boolean>
    /** A new default network (Wi-Fi to cellular and back): an open socket on the old one may hang until it times out. */
    val changed: SharedFlow<Unit>
}

/** Always online (the demo and the tests). */
object AlwaysOnline : Connectivity {
    override val online: StateFlow<Boolean> = MutableStateFlow(true)
    override val changed: SharedFlow<Unit> = MutableSharedFlow()
}

/**
 * The phone's default network, from a [ConnectivityManager.NetworkCallback] (no polling). A network counts when it has the internet
 * capability; it need not be "validated": the system's check reaches Google's servers, which some networks (Iran's among them) do not,
 * and the hub is reachable all the same.
 */
class NetworkWatch(context: Context) : Connectivity {
    private val cm = context.getSystemService(ConnectivityManager::class.java)
    private val state = MutableStateFlow(current())
    private val change = MutableSharedFlow<Unit>(extraBufferCapacity = 4)
    override val online: StateFlow<Boolean> = state.asStateFlow()
    override val changed: SharedFlow<Unit> = change.asSharedFlow()
    @Volatile private var network: Network? = null
    @Volatile private var registered = false

    private val callback = object : ConnectivityManager.NetworkCallback() {
        override fun onAvailable(n: Network) {
            val before = network
            network = n
            state.value = true
            // Coming back from no network wakes the waiting lanes through [online]; only a switch between two networks is a change.
            if (before != null && before != n) change.tryEmit(Unit)
        }

        override fun onLost(n: Network) {
            if (network == n) {
                // The default network is gone; the next one (if any) arrives through onAvailable.
                network = null
                state.value = false
            }
        }
    }

    /** Starts listening (idempotent); the process keeps one callback for its life. */
    fun start() {
        if (registered || cm == null) return
        network = runCatching { cm.activeNetwork }.getOrNull()
        registered = runCatching { cm.registerDefaultNetworkCallback(callback); true }.getOrDefault(false)
    }

    private fun current(): Boolean = runCatching {
        val caps = cm?.getNetworkCapabilities(cm.activeNetwork) ?: return@runCatching false
        caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }.getOrDefault(true)

    /** wifi · cellular · ethernet · vpn · offline · other, for the status line and the log. */
    fun kind(): String = runCatching {
        val caps = cm?.getNetworkCapabilities(cm.activeNetwork) ?: return@runCatching "offline"
        when {
            caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN) -> "vpn"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "wifi"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "cellular"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "ethernet"
            else -> "other"
        }
    }.getOrDefault("other")
}
