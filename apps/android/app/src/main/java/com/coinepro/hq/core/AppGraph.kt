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
import com.coinepro.hq.core.net.Api
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Everything one session needs: the API, auth, the query cache and the live stream. A demo session (debug
 *  builds) swaps the network for fixtures and lives beside the real one without touching its token. */
class Env(val api: Api, val auth: Auth, val cache: QueryCache, val stream: HoldingStream, val demo: Boolean, private val scope: CoroutineScope) {
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
        val api = Api(BuildConfig.HQ_ORIGIN, tokens, if (demo) Demo.interceptor() else null)
        val cache = QueryCache(scope)
        return Env(api, Auth(api, tokens, demo), cache, HoldingStream(api, cache, scope, demo), demo, scope)
    }
}

/** Small device-local preferences (theme). Never secrets. */
class Prefs(context: Context) {
    private val sp = context.getSharedPreferences("hq.prefs", Context.MODE_PRIVATE)
    private val themeFlow = MutableStateFlow(ThemeMode.entries.firstOrNull { it.name == sp.getString("theme", null) } ?: ThemeMode.SYSTEM)
    val theme: StateFlow<ThemeMode> = themeFlow.asStateFlow()

    fun setTheme(mode: ThemeMode) {
        sp.edit().putString("theme", mode.name).apply()
        themeFlow.value = mode
    }
}

enum class ThemeMode { NIGHT, DAY, SYSTEM }
