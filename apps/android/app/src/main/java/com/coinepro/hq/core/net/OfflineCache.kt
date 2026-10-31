package com.coinepro.hq.core.net

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.io.File
import java.io.IOException
import java.security.KeyStore
import java.time.Instant
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Protocol
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody

/** Offline reading (M13): the last good answer of the screens the owner reads is kept on the phone, encrypted with a
 *  Keystore key, and served when the network is gone; [since] then says from when. Nothing is ever written offline:
 *  every action still goes to the hub and fails without it. Cleared on sign-out. */
class OfflineCache(context: Context) : Interceptor {
    private val dir = File(context.filesDir, "offline").apply { mkdirs() }
    private val state = MutableStateFlow<String?>(null)

    /** When the answers on screen were saved, while the app is reading from the phone; null when live. */
    val since: StateFlow<String?> = state.asStateFlow()

    override fun intercept(chain: Interceptor.Chain): Response {
        val req = chain.request()
        val path = req.url.encodedPath.removePrefix("/api/v1")
        // A search or a further page is not kept: only what a screen shows first, so the copy stays small.
        val keep = req.method == "GET" && KEEP.any { path == it || path.startsWith("$it/") || path.startsWith("$it?") } &&
            req.url.queryParameter("cursor") == null && req.url.queryParameter("q") == null
        if (!keep) return chain.proceed(req)
        val file = File(dir, Api.sha256(req.url.toString()))
        val res = try {
            chain.proceed(req)
        } catch (e: IOException) {
            val saved = runCatching { read(file) }.getOrNull() ?: throw e
            state.value = saved.first
            return Response.Builder().request(req).protocol(Protocol.HTTP_1_1).code(200).message("offline")
                .header("X-HQ-Offline", saved.first).body(saved.second.toResponseBody("application/json".toMediaType())).build()
        }
        state.value = null
        if (res.code != 200) return res
        val body = res.peekBody(MAX_BYTES + 1).bytes()
        if (body.size <= MAX_BYTES) runCatching { write(file, body); prune() }
        return res
    }

    @Volatile private var writes = 0

    /** At most [MAX_TOTAL] bytes on the phone: the oldest answers go first (checked every few writes). */
    private fun prune() {
        if (++writes % 20 != 0) return
        val files = dir.listFiles()?.sortedByDescending { it.lastModified() } ?: return
        var total = 0L
        for (f in files) { total += f.length(); if (total > MAX_TOTAL) f.delete() }
    }

    fun clear() {
        dir.listFiles()?.forEach { it.delete() }
        state.value = null
    }

    private fun write(file: File, body: ByteArray) {
        val c = Cipher.getInstance(TRANSFORM).apply { init(Cipher.ENCRYPT_MODE, key()) }
        val stamp = Instant.now().toString().toByteArray()
        val sealed = c.doFinal(body)
        file.writeBytes(byteArrayOf(c.iv.size.toByte()) + c.iv + byteArrayOf(stamp.size.toByte()) + stamp + sealed)
    }

    private fun read(file: File): Pair<String, ByteArray>? {
        if (!file.exists()) return null
        val all = file.readBytes()
        val ivLen = all[0].toInt()
        val iv = all.copyOfRange(1, 1 + ivLen)
        val stampLen = all[1 + ivLen].toInt()
        val stamp = String(all.copyOfRange(2 + ivLen, 2 + ivLen + stampLen))
        val c = Cipher.getInstance(TRANSFORM).apply { init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, iv)) }
        return stamp to c.doFinal(all.copyOfRange(2 + ivLen + stampLen, all.size))
    }

    private fun key(): SecretKey {
        val ks = KeyStore.getInstance(KEYSTORE).apply { load(null) }
        (ks.getEntry(ALIAS, null) as? KeyStore.SecretKeyEntry)?.let { return it.secretKey }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE)
        gen.init(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).setKeySize(256).build(),
        )
        return gen.generateKey()
    }

    private companion object {
        const val KEYSTORE = "AndroidKeyStore"
        const val ALIAS = "hq-offline"
        const val TRANSFORM = "AES/GCM/NoPadding"
        const val MAX_BYTES = 512L * 1024
        /** The whole offline copy's ceiling. */
        const val MAX_TOTAL = 20L * 1024 * 1024
        /** What the owner reads; never files, the stream or anything sealed. */
        val KEEP = listOf(
            "/meta", "/inbox/summary", "/owner/away-summary", "/owner/presence", "/owner/hiring", "/decisions", "/deliverables", "/companies",
            "/employees", "/org", "/work", "/planner", "/threads", "/notifications", "/control/state", "/treasury/summary", "/treasury/quota",
            "/stories", "/oversight/summary", "/resolutions", "/ops/sites", "/ops/incidents", "/runs", "/stars/rollup",
        )
    }
}
