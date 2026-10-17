package com.coinepro.hq.core.auth

import android.app.Activity
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.TokenSource
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.serialization.json.JsonElement

/** Where a session token is kept and whether one is present. */
interface SessionTokens : TokenSource {
    val signedIn: StateFlow<Boolean>
    fun save(token: String)
}

class VaultTokens(private val vault: TokenVault) : SessionTokens {
    override val signedIn: StateFlow<Boolean> = vault.signedIn
    override fun token(): String? = vault.token()
    override fun save(token: String) = vault.save(token)
    override fun clear() = vault.clear()
}

/** The demo session (debug builds only): always signed in until the owner leaves the demo. */
class DemoTokens(private val onLeave: () -> Unit) : SessionTokens {
    private val state = MutableStateFlow(true)
    override val signedIn: StateFlow<Boolean> = state
    override fun token(): String = "demo"
    override fun save(token: String) { state.value = true }
    override fun clear() { state.value = false; onLeave() }
}

/** Owner sign-in, enrolment and step-up (contract §2). No password exists anywhere: every ceremony is a passkey. */
class Auth(private val api: Api, private val tokens: SessionTokens, private val demo: Boolean) {
    val signedIn: StateFlow<Boolean> get() = tokens.signedIn

    /** Discoverable-credential sign-in: no passkey id is revealed before the assertion. */
    suspend fun signIn(activity: Activity) {
        if (demo) return tokens.save("demo")
        val options = api.loginOptions()
        val credential = Passkeys.get(activity, options.toString())
        val out = api.loginVerify(parse(credential), Passkeys.deviceName())
        val token = out.session.token
            ?: throw ApiException(500, "contract_mismatch", "سرور توکن نشست اندروید را نفرستاد.")
        tokens.save(token)
    }

    /** First enrolment from the one-time link (`make owner-enroll`), or adding this device with a step-up.
     *  Registration returns only the device; a sign-in follows so the owner lands inside. */
    suspend fun enrol(activity: Activity, enrolmentToken: String?, stepUpToken: String? = null) {
        if (demo) return tokens.save("demo")
        val options = api.registerOptions(enrolmentToken, stepUpToken)
        val credential = Passkeys.create(activity, options.toString())
        api.registerVerify(parse(credential), Passkeys.deviceName())
        if (!tokens.signedIn.value) signIn(activity)
    }

    /** A fresh assertion bound to one action and target; the token is single-use and lives 120 s. */
    suspend fun stepUp(activity: Activity, action: String, target: String): String {
        if (demo) return "demo"
        val options = api.stepUpOptions(action, target)
        val credential = Passkeys.get(activity, options.toString())
        return api.stepUpVerify(parse(credential)).stepUpToken
    }

    suspend fun signOut() {
        if (!demo) runCatching { api.logout() }
        tokens.clear()
    }

    private fun parse(credential: String): JsonElement = Api.json.parseToJsonElement(credential)
}
