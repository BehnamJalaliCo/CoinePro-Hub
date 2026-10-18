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
    val demo: Boolean,
    private val scope: CoroutineScope,
    /** When the screens are reading from the phone's offline copy (M13), the instant it was saved; null when live. */
    val offlineSince: StateFlow<String?> = MutableStateFlow(null),
) {
    fun close() {
        stream.stop()
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

    private val envFlow = MutableStateFlow(build(VaultTokens(vault), demo = false))
    val env: StateFlow<Env> = envFlow.asStateFlow()

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
    }

    private fun build(tokens: SessionTokens, demo: Boolean): Env {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        val api = Api(BuildConfig.HQ_ORIGIN, tokens, if (demo) Demo.interceptor() else offline)
        val cache = QueryCache(scope)
        return Env(api, Auth(api, tokens, demo), cache, HoldingStream(api, cache, scope, demo), MediaKit(app, api), demo, scope, if (demo) MutableStateFlow(null) else offline.since)
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
