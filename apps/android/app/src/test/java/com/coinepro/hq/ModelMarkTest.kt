package com.coinepro.hq

import androidx.compose.ui.graphics.vector.addPathNodes
import com.coinepro.hq.designsystem.generated.PROVIDER_LOGOS
import com.coinepro.hq.designsystem.providerOf
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** The treasury's provider logos: every model the connections seed names maps to its provider, and every logo path parses. */
class ModelMarkTest {
    @Test
    fun modelsMapToTheirProvider() {
        val cases = mapOf(
            "claude-opus-5-5" to "anthropic", "gpt-5-mini" to "openai", "o3" to "openai", "gemini-2.5-pro" to "google",
            "deepseek-chat" to "deepseek", "glm-4.6" to "zhipu", "kimi-k2" to "moonshot", "qwen3-coder" to "qwen",
            "mistral-large" to "mistral", "grok-4" to "xai", "llama-4" to "meta", "openrouter/deepseek-r1" to "deepseek",
        )
        cases.forEach { (model, provider) -> assertEquals(model, provider, providerOf(model)) }
        assertEquals("google", providerOf("anything", "gemini"))
        assertEquals("deepseek", providerOf("deepseek-chat", "openai_compatible"))
        assertNull(providerOf("some-new-model"))
    }

    @Test
    fun everyLogoParses() {
        PROVIDER_LOGOS.forEach { (key, logo) ->
            assertTrue(key, logo.paths.isNotEmpty())
            logo.paths.forEach { assertTrue(key, addPathNodes(it.d).isNotEmpty()) }
        }
    }
}
