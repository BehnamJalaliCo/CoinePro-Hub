package com.coinepro.hq.core.auth

import android.app.Activity
import android.content.pm.PackageManager
import android.os.Build
import android.util.Base64
import androidx.credentials.CreatePublicKeyCredentialRequest
import androidx.credentials.CreatePublicKeyCredentialResponse
import androidx.credentials.CredentialManager
import androidx.credentials.GetCredentialRequest
import androidx.credentials.GetPublicKeyCredentialOption
import androidx.credentials.PublicKeyCredential
import androidx.credentials.exceptions.CreateCredentialCancellationException
import androidx.credentials.exceptions.CreateCredentialException
import androidx.credentials.exceptions.GetCredentialCancellationException
import androidx.credentials.exceptions.GetCredentialException
import androidx.credentials.exceptions.NoCredentialException
import androidx.credentials.exceptions.domerrors.InvalidStateError
import androidx.credentials.exceptions.domerrors.NotAllowedError
import androidx.credentials.exceptions.domerrors.SecurityError
import androidx.credentials.exceptions.publickeycredential.CreatePublicKeyCredentialDomException
import androidx.credentials.exceptions.publickeycredential.GetPublicKeyCredentialDomException
import com.coinepro.hq.core.net.ApiException
import java.security.MessageDigest

/** WebAuthn on Android through Credential Manager. The relying party is the hub's domain; the app proves it
 *  belongs to that domain through Digital Asset Links (`/.well-known/assetlinks.json`), and the API accepts the
 *  app's origin `android:apk-key-hash:…` from its allow-list (contract §2). */
object Passkeys {

    /** Runs a registration ceremony; returns the credential JSON for `/auth/passkey/register/verify`. */
    suspend fun create(activity: Activity, optionsJson: String): String = try {
        val r = CredentialManager.create(activity).createCredential(activity, CreatePublicKeyCredentialRequest(optionsJson))
        (r as CreatePublicKeyCredentialResponse).registrationResponseJson
    } catch (e: CreateCredentialException) {
        throw ceremony(e)
    }

    /** Runs an assertion (sign-in or step-up); returns the credential JSON for the verify call. */
    suspend fun get(activity: Activity, optionsJson: String): String = try {
        val r = CredentialManager.create(activity).getCredential(activity, GetCredentialRequest(listOf(GetPublicKeyCredentialOption(optionsJson))))
        (r.credential as? PublicKeyCredential)?.authenticationResponseJson ?: throw failed()
    } catch (e: GetCredentialException) {
        throw ceremony(e)
    }

    /** "Pixel 9 · Android 16" — the name this device gets in the device list. */
    fun deviceName(): String = "${Build.MODEL.trim()} · Android ${Build.VERSION.RELEASE}"

    /** SHA-256 fingerprints of the app's signing certificates, colon hex — the value assetlinks.json lists. */
    fun signingFingerprints(activity: Activity): List<String> = certs(activity).map { d -> d.joinToString(":") { "%02X".format(it) } }

    /** The WebAuthn origin this app presents (`android:apk-key-hash:<base64url sha-256>`), for the API allow-list. */
    fun origins(activity: Activity): List<String> =
        certs(activity).map { "android:apk-key-hash:" + Base64.encodeToString(it, Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP) }

    private fun certs(activity: Activity): List<ByteArray> {
        val info = activity.packageManager.getPackageInfo(activity.packageName, PackageManager.GET_SIGNING_CERTIFICATES)
        val signers = info.signingInfo?.apkContentsSigners.orEmpty()
        return signers.map { MessageDigest.getInstance("SHA-256").digest(it.toByteArray()) }
    }

    private fun failed() = ApiException(400, "passkey_ceremony_failed", "تأیید هویت انجام نشد؛ دوباره تلاش کن.")

    private fun ceremony(e: Exception): ApiException {
        val fa = when {
            e is CreateCredentialCancellationException || e is GetCredentialCancellationException -> "تأیید با اثر انگشت یا چهره لغو شد."
            e is NoCredentialException -> "روی این دستگاه passkeyی برای ستاد نیست. اول با لینک ثبت‌نام، این دستگاه را اضافه کن."
            e is CreatePublicKeyCredentialDomException && e.domError is InvalidStateError -> "این دستگاه قبلاً ثبت شده است."
            (e is CreatePublicKeyCredentialDomException && e.domError is SecurityError) ||
                (e is GetPublicKeyCredentialDomException && e.domError is SecurityError) ->
                "اپ هنوز به دامنه‌ی ستاد وصل نشده است (assetlinks). از تنظیمات، اثر انگشت امضای اپ را به سرور بده."
            (e is CreatePublicKeyCredentialDomException && e.domError is NotAllowedError) ||
                (e is GetPublicKeyCredentialDomException && e.domError is NotAllowedError) -> "تأیید با اثر انگشت یا چهره لغو شد یا زمانش گذشت."
            else -> "تأیید هویت انجام نشد؛ دوباره تلاش کن."
        }
        return ApiException(400, "passkey_ceremony_failed", fa)
    }
}
