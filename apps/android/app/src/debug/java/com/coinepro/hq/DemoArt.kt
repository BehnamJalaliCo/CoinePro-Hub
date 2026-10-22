package com.coinepro.hq

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.graphics.Shader
import android.graphics.Typeface
import android.text.Layout
import android.text.StaticLayout
import android.text.TextDirectionHeuristics
import android.text.TextPaint
import androidx.core.content.res.ResourcesCompat
import java.io.File
import kotlin.math.floor
import kotlin.math.min
import kotlin.math.roundToInt
import kotlin.math.sin

/** Debug only: the demo's stand-in for a substitute's render and the hub's composition (§21.13), as the web's mock-v18 draws it on a
 *  canvas: the brand's gradient and motif, never any text; with an overlay, the Persian text in the placement's safe margin. */
internal object DemoArt {
    val ASPECT = mapOf("telegram_post" to "16:9", "telegram_story" to "9:16", "instagram_post" to "4:5", "instagram_story" to "9:16", "banner" to "16:9", "other" to "1:1")
    private val SIZE = mapOf("1:1" to (640 to 640), "4:5" to (640 to 800), "9:16" to (540 to 960), "16:9" to (800 to 450))

    private class Safe(val top: Float, val bottom: Float, val side: Float)
    private val SAFE = mapOf(
        "telegram_post" to Safe(0.07f, 0.09f, 0.06f), "telegram_story" to Safe(0.14f, 0.2f, 0.08f), "instagram_post" to Safe(0.06f, 0.08f, 0.06f),
        "instagram_story" to Safe(0.14f, 0.2f, 0.08f), "banner" to Safe(0.08f, 0.08f, 0.05f), "other" to Safe(0.06f, 0.06f, 0.06f),
    )

    class Brand(val bg0: Int, val bg1: Int, val accent: Int, val motif: String, val mark: String)
    val BRAND = mapOf(
        "FX" to Brand(0xFF0E1422.toInt(), 0xFF3A2A0C.toInt(), 0xFFD8A848.toInt(), "candles", "CoinePro FX"),
        "TY" to Brand(0xFF06221E.toInt(), 0xFF0B3B4A.toInt(), 0xFF00AB8E.toInt(), "waves", "TradeYar"),
        "PC" to Brand(0xFF101830.toInt(), 0xFF2A1E40.toInt(), 0xFF6591E1.toInt(), "rings", "Pro-Chart"),
        "HQ" to Brand(0xFF0B0D14.toInt(), 0xFF2A2418.toInt(), 0xFFD8A848.toInt(), "rings", "CoinePro HQ"),
    )
    private const val INK = 0xFFF2EEE4.toInt()
    private const val NEG = 0xFFC94B5B.toInt()

    /** Deterministic 0..1, so every reload draws the same picture. */
    fun noise(seed: Int, i: Int): Double { val x = sin(seed * 9301.0 + i * 49297.0) * 233280; return x - floor(x) }
    fun seedOf(s: String): Int = s.fold(7) { a, c -> (a * 31 + c.code) % 9973 }

    class Overlay(val title: String, val body: String?, val cta: String?, val mark: Boolean)

    /** Draws one picture into [out] (JPEG) and answers its pixel size. */
    fun render(context: Context, company: String, placement: String, seed: Int, overlay: Overlay?, out: File): Pair<Int, Int> {
        val (w, h) = SIZE[ASPECT[placement] ?: "1:1"] ?: (640 to 640)
        val b = BRAND[company] ?: BRAND.getValue("HQ")
        val bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        val g = Canvas(bmp)
        val fill = Paint(Paint.ANTI_ALIAS_FLAG)
        fill.shader = LinearGradient(0f, 0f, w.toFloat(), h.toFloat(), b.bg0, b.bg1, Shader.TileMode.CLAMP)
        g.drawRect(0f, 0f, w.toFloat(), h.toFloat(), fill)
        fun rnd(i: Int) = noise(seed, i)
        val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE }
        val solid = Paint(Paint.ANTI_ALIAS_FLAG)
        when (b.motif) {
            "candles" -> {
                val n = 22
                val cw = w / n.toFloat()
                var y = h * 0.55f
                for (i in 0 until n) {
                    val up = rnd(i) > 0.42
                    val body = (h * (0.03 + rnd(i + 40) * 0.08)).toFloat()
                    y += (if (up) -1 else 1) * body * 0.6f
                    val col = if (up) b.accent else NEG
                    stroke.color = col; stroke.alpha = 230; stroke.strokeWidth = 2f
                    solid.color = col; solid.alpha = 230
                    g.drawLine(i * cw + cw / 2, y - body * 0.9f, i * cw + cw / 2, y + body * 1.4f, stroke)
                    g.drawRect(i * cw + cw * 0.22f, y, i * cw + cw * 0.78f, y + body, solid)
                }
            }
            "waves" -> for (k in 0 until 6) {
                stroke.color = if (k % 2 == 1) b.accent else INK
                stroke.alpha = ((0.25 + k * 0.1) * 255).roundToInt().coerceAtMost(255)
                stroke.strokeWidth = 3f
                val p = Path()
                var x = 0
                while (x <= w) {
                    val yy = (h * (0.3 + k * 0.07) + sin(x / (40.0 + k * 9) + rnd(k) * 6) * (18 + k * 4)).toFloat()
                    if (x == 0) p.moveTo(0f, yy) else p.lineTo(x.toFloat(), yy)
                    x += 8
                }
                g.drawPath(p, stroke)
            }
            else -> for (k in 0 until 7) {
                stroke.color = if (k % 2 == 1) b.accent else 0xFFAEB8C7.toInt()
                stroke.alpha = ((0.2 + k * 0.08) * 255).roundToInt().coerceAtMost(255)
                stroke.strokeWidth = 2f + k
                val r = 30f + k * 34
                val cx = w * 0.72f
                val cy = h * 0.32f
                g.drawArc(RectF(cx - r, cy - r, cx + r, cy + r), 0f, (180 * (1 + rnd(k))).toFloat(), false, stroke)
            }
        }
        if (overlay != null) compose(context, g, w, h, placement, b, overlay)
        out.parentFile?.mkdirs()
        out.outputStream().use { bmp.compress(Bitmap.CompressFormat.JPEG, 86, it) }
        bmp.recycle()
        return w to h
    }

    private fun compose(context: Context, g: Canvas, w: Int, h: Int, placement: String, b: Brand, o: Overlay) {
        val fa = ResourcesCompat.getFont(context, R.font.iranyekanx_fanum) ?: Typeface.DEFAULT
        val la = ResourcesCompat.getFont(context, R.font.iranyekanx_latin) ?: Typeface.DEFAULT
        val s = SAFE[placement] ?: SAFE.getValue("other")
        val x0 = w * s.side
        val x1 = w * (1 - s.side)
        val maxW = (x1 - x0).toInt()
        val scrim = Paint().apply { shader = LinearGradient(0f, h * 0.42f, 0f, h.toFloat(), 0x000B0D14, 0xE00B0D14.toInt(), Shader.TileMode.CLAMP) }
        g.drawRect(0f, h * 0.42f, w.toFloat(), h.toFloat(), scrim)
        val tSize = (w * (if (h > w) 0.085f else 0.06f)).roundToInt().toFloat()
        val bSize = (tSize * 0.52f).roundToInt().toFloat()
        fun layout(text: String, face: Typeface, size: Float, spacing: Float): StaticLayout {
            val p = TextPaint(Paint.ANTI_ALIAS_FLAG).apply { typeface = face; textSize = size; color = INK }
            return StaticLayout.Builder.obtain(text, 0, text.length, p, maxW)
                .setAlignment(Layout.Alignment.ALIGN_NORMAL).setTextDirection(TextDirectionHeuristics.RTL).setLineSpacing(0f, spacing).build()
        }
        val blocks = listOfNotNull(layout(o.title, Typeface.create(fa, 700, false), tSize, 1.1f), o.body?.takeIf { it.isNotBlank() }?.let { layout(it, fa, bSize, 1.3f) })
        val ctaH = if (o.cta.isNullOrBlank()) 0f else bSize * 2.2f
        val bottom = h * (1 - s.bottom)
        var y = bottom - ctaH - (if (ctaH > 0) bSize else 0f) - blocks.sumOf { it.height }
        for (l in blocks) {
            g.save(); g.translate(x0, y); l.draw(g); g.restore()
            y += l.height
        }
        if (!o.cta.isNullOrBlank()) {
            val p = TextPaint(Paint.ANTI_ALIAS_FLAG).apply { typeface = Typeface.create(fa, 700, false); textSize = bSize; color = 0xFF0B0D14.toInt(); textAlign = Paint.Align.RIGHT }
            val tw = min(p.measureText(o.cta) + bSize * 2, maxW.toFloat())
            val by = bottom - ctaH
            g.drawRoundRect(RectF(x1 - tw, by, x1, by + ctaH), ctaH / 2, ctaH / 2, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = b.accent })
            g.drawText(o.cta, x1 - bSize, by + ctaH * 0.66f, p)
        }
        if (o.mark) {
            val p = TextPaint(Paint.ANTI_ALIAS_FLAG).apply { typeface = Typeface.create(la, 600, false); textSize = (bSize * 0.9f).roundToInt().toFloat(); color = b.accent }
            g.drawText(b.mark, x0, h * s.top + bSize, p)
        }
    }
}
