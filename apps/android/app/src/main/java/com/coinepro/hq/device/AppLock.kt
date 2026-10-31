package com.coinepro.hq.device

import android.app.Activity
import android.app.KeyguardManager
import android.content.Context
import android.hardware.biometrics.BiometricManager.Authenticators
import android.hardware.biometrics.BiometricPrompt
import android.os.Build
import android.os.CancellationSignal
import android.os.SystemClock
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import com.coinepro.hq.core.Prefs
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** The app lock (M11): with the setting on and a secure lock screen on the phone, the app opens locked and locks again
 *  after a minute in the background; fingerprint, face or the phone's PIN opens it. Sealed actions still need the passkey. */
class AppLock(private val context: Context, private val prefs: Prefs) : DefaultLifecycleObserver {
    private val state = MutableStateFlow(enabled())
    val locked: StateFlow<Boolean> = state.asStateFlow()
    private var stoppedAt: Long? = null

    /** The phone can verify its owner: without a secure lock screen there is nothing to unlock with. */
    fun available(): Boolean = context.getSystemService(KeyguardManager::class.java)?.isDeviceSecure == true

    fun enabled(): Boolean = prefs.appLock.value && available()

    fun setEnabled(on: Boolean) {
        prefs.setAppLock(on)
        if (!on) state.value = false
    }

    /** Until when a return does not lock: the app itself opened the camera, a picker or a share sheet. */
    @Volatile private var returningUntil = 0L

    /** The app is about to open another app's screen for the owner (camera, file picker, share): its return keeps the app open, so the
     *  half-written message and the picked file are not lost behind the lock. */
    fun leavingForResult() {
        returningUntil = SystemClock.elapsedRealtime() + PICKER_MS
    }

    override fun onStop(owner: LifecycleOwner) {
        stoppedAt = SystemClock.elapsedRealtime()
    }

    override fun onStart(owner: LifecycleOwner) {
        val at = stoppedAt ?: return
        val now = SystemClock.elapsedRealtime()
        val picker = now < returningUntil
        returningUntil = 0L
        if (enabled() && !picker && now - at > GRACE_MS) state.value = true
    }

    fun unlock(activity: Activity, onError: (String) -> Unit) {
        if (!enabled()) { state.value = false; return }
        val builder = BiometricPrompt.Builder(activity)
            .setTitle("باز کردن ستاد")
            .setSubtitle("با اثر انگشت، چهره یا قفل گوشی")
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) builder.setAllowedAuthenticators(Authenticators.BIOMETRIC_STRONG or Authenticators.DEVICE_CREDENTIAL)
        else @Suppress("DEPRECATION") builder.setDeviceCredentialAllowed(true)
        builder.build().authenticate(CancellationSignal(), activity.mainExecutor, object : BiometricPrompt.AuthenticationCallback() {
            override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) { state.value = false }
            override fun onAuthenticationError(code: Int, message: CharSequence) {
                if (code != BiometricPrompt.BIOMETRIC_ERROR_USER_CANCELED && code != BiometricPrompt.BIOMETRIC_ERROR_CANCELED) onError(message.toString())
            }
        })
    }

    private companion object {
        const val GRACE_MS = 60_000L
        /** How long a picker or the camera may take before coming back locks after all. */
        const val PICKER_MS = 10 * 60_000L
    }
}
