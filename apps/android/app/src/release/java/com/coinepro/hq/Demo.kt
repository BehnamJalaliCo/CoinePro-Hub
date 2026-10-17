package com.coinepro.hq

import android.content.Context
import okhttp3.Interceptor

/** Release builds have no demo: no fixtures ship to the owner's phone. */
object Demo {
    const val available = false
    fun init(context: Context) = Unit
    fun interceptor(): Interceptor? = null
}
