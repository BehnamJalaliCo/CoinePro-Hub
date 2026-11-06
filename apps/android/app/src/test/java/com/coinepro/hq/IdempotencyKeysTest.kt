package com.coinepro.hq

import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The owner's log, 0.15.0: «لغو این فرمان» sent `Idempotency-Key: <uuid>-cancel` and the hub answered 422 (a key is a UUID). No key of
 * the app is made from another one: every press that needs its own key has its own `UUID.randomUUID()`.
 */
class IdempotencyKeysTest {
    @Test
    fun noKeyIsMadeFromAnotherKey() {
        val src = File("src/main/java").takeIf { it.isDirectory } ?: File("app/src/main/java")
        assertTrue("sources not found from ${File(".").absolutePath}", src.isDirectory)
        // "$key-cancel", "${key}2", "$idemKey:retry", "$clientId-x" handed to the API: a key with something glued to it. (A cache's own
        // key, never sent, is not one.)
        val derived = Regex("\"\\$\\{?(key|[a-z]*Key|clientId|idem[A-Za-z]*)\\}?[^\"\\s]+\"")
        val sent = Regex("\\bapi\\.|Idempotency|\\bkey = ")
        val found = src.walkTopDown().filter { it.extension == "kt" }.flatMap { f ->
            f.readLines().mapIndexedNotNull { i, line -> if (derived.containsMatchIn(line) && sent.containsMatchIn(line)) "${f.name}:${i + 1}: ${line.trim()}" else null }
        }.toList()
        assertEquals(emptyList<String>(), found)
    }
}
