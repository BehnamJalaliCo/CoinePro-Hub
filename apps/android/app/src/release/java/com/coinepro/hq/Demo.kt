package com.coinepro.hq

import android.content.Context
import com.coinepro.hq.core.net.StreamEvent
import okhttp3.Interceptor

/** Release builds have no demo: no fixtures ship to the owner's phone. */
object Demo {
    const val available = false
    fun init(context: Context) = Unit
    fun interceptor(): Interceptor? = null
    fun next(tick: Int): List<StreamEvent> = emptyList()
}
