package com.coinepro.hq

import android.app.Application
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.ProcessLifecycleOwner
import com.coinepro.hq.core.AppGraph

/** Application: owns the graph; the live stream runs only while the app is in the foreground. */
class HqApp : Application() {
    lateinit var graph: AppGraph
        private set

    override fun onCreate() {
        super.onCreate()
        Demo.init(this)
        graph = AppGraph(this)
        ProcessLifecycleOwner.get().lifecycle.addObserver(graph.lock)
        ProcessLifecycleOwner.get().lifecycle.addObserver(object : DefaultLifecycleObserver {
            override fun onStart(owner: LifecycleOwner) {
                graph.errors.foreground = true
                val env = graph.env.value
                if (env.auth.signedIn.value) {
                    env.cache.refreshObserved()
                    env.stream.start()
                }
            }

            override fun onStop(owner: LifecycleOwner) {
                graph.errors.foreground = false
                graph.env.value.stream.stop()
            }
        })
    }
}
