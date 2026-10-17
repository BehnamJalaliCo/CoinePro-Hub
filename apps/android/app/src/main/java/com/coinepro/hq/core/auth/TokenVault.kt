package com.coinepro.hq.core.auth

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import com.coinepro.hq.core.net.TokenSource
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** The session token (contract §2: opaque Bearer, sliding 30 days, absolute 90), encrypted at rest with an
 *  AES-GCM key that never leaves the Android Keystore. Excluded from backups (data_extraction_rules). */
class TokenVault(context: Context) : TokenSource {
    private val prefs = context.getSharedPreferences("hq.session", Context.MODE_PRIVATE)

    @Volatile private var cached: String? = runCatching { read() }.getOrNull()
    private val present = MutableStateFlow(cached != null)

    /** True while a session token is stored. Turns false on sign-out and on any 401. */
    val signedIn: StateFlow<Boolean> = present.asStateFlow()

    override fun token(): String? = cached

    fun save(token: String) {
        val c = Cipher.getInstance(TRANSFORM).apply { init(Cipher.ENCRYPT_MODE, key()) }
        val sealed = c.doFinal(token.toByteArray(Charsets.UTF_8))
        prefs.edit()
            .putString(K_IV, Base64.encodeToString(c.iv, Base64.NO_WRAP))
            .putString(K_DATA, Base64.encodeToString(sealed, Base64.NO_WRAP))
            .apply()
        cached = token
        present.value = true
    }

    override fun clear() {
        prefs.edit().clear().apply()
        cached = null
        present.value = false
    }

    private fun read(): String? {
        val iv = prefs.getString(K_IV, null) ?: return null
        val data = prefs.getString(K_DATA, null) ?: return null
        val c = Cipher.getInstance(TRANSFORM)
        c.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP)))
        return String(c.doFinal(Base64.decode(data, Base64.NO_WRAP)), Charsets.UTF_8)
    }

    private fun key(): SecretKey {
        val ks = KeyStore.getInstance(KEYSTORE).apply { load(null) }
        (ks.getEntry(ALIAS, null) as? KeyStore.SecretKeyEntry)?.let { return it.secretKey }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE)
        gen.init(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build(),
        )
        return gen.generateKey()
    }

    private companion object {
        const val KEYSTORE = "AndroidKeyStore"
        const val ALIAS = "hq-session"
        const val TRANSFORM = "AES/GCM/NoPadding"
        const val K_IV = "iv"
        const val K_DATA = "token"
    }
}
