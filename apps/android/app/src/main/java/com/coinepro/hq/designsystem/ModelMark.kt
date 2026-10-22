package com.coinepro.hq.designsystem

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.size
import androidx.compose.material3.LocalContentColor
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathFillType
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.addPathNodes
import androidx.compose.ui.graphics.vector.rememberVectorPainter
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.modelLabel
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.generated.PROVIDER_LOGOS

// The provider's logo beside a model in the treasury (mirrors apps/web/src/components/brand/model-mark.tsx).

private val PREFIX = Regex("^[a-z0-9_-]+/")

/** The provider a model belongs to. Connections carry `provider`; treasury rows carry only the model id, so the id decides. */
fun providerOf(model: String?, provider: String? = null): String? {
    val p = provider.orEmpty().lowercase().let { if (it == "gemini") "google" else it }
    if (p.isNotEmpty() && PROVIDER_LOGOS.containsKey(p)) return p
    val m = model.orEmpty().lowercase().replace(PREFIX, "")
    return when {
        m.startsWith("claude") -> "anthropic"
        Regex("^(gpt|o\\d|chatgpt)").containsMatchIn(m) -> "openai"
        m.startsWith("gemini") || m.startsWith("gemma") -> "google"
        m.startsWith("deepseek") -> "deepseek"
        m.startsWith("glm") || m.startsWith("chatglm") -> "zhipu"
        m.startsWith("kimi") || m.startsWith("moonshot") -> "moonshot"
        m.startsWith("qwen") || m.startsWith("qwq") -> "qwen"
        Regex("^(mistral|codestral|ministral|magistral|devstral|pixtral)").containsMatchIn(m) -> "mistral"
        m.startsWith("grok") -> "xai"
        m.startsWith("llama") -> "meta"
        else -> null
    }
}

/** A model of an unknown provider gets the neutral model glyph. Paths without their own colour take the text colour. */
@Composable
fun ModelMark(model: String?, modifier: Modifier = Modifier, provider: String? = null, size: Dp = 14.dp) {
    val key = providerOf(model, provider)
    val logo = key?.let { PROVIDER_LOGOS[it] }
    if (logo == null) {
        DIcon(DivanIcon.MODEL, modifier, size = size, tint = Divan.colors.textMuted)
        return
    }
    val tint = LocalContentColor.current
    val vector = remember(key, tint) {
        ImageVector.Builder(name = key, defaultWidth = 24.dp, defaultHeight = 24.dp, viewportWidth = 24f, viewportHeight = 24f).apply {
            logo.paths.forEach { p ->
                addPath(
                    pathData = addPathNodes(p.d),
                    fill = SolidColor(p.fill?.let { Color(it) } ?: tint),
                    pathFillType = if (logo.evenOdd) PathFillType.EvenOdd else PathFillType.NonZero,
                )
            }
        }.build()
    }
    Image(rememberVectorPainter(vector), contentDescription = logo.title, modifier = modifier.size(size))
}

/** A model's name with its provider's logo before it (Latin figures, as every model name). */
@Composable
fun ModelName(model: String, modifier: Modifier = Modifier, provider: String? = null, size: Dp = 14.dp, style: TextStyle = Divan.type.figure, color: Color = LocalContentColor.current) {
    Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        ModelMark(model, provider = provider, size = size)
        Fig(modelLabel(model), style = style, color = color)
    }
}
