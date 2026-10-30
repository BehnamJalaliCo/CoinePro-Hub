package com.coinepro.hq

import android.app.Application
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.ProcessLifecycleOwner
import com.coinepro.hq.core.AppGraph

/** Application: owns the graph. The live stream opens every lane while the app is on screen and keeps its alert lane open with the app
 *  closed while the background link runs ([com.coinepro.hq.core.link.HubLink], `device/HubLinkService`). */
class HqApp : Application() {
    lateinit var graph: AppGraph
        private set

    override fun onCreate() {
        super.onCreate()
        Demo.init(this)
        graph = AppGraph(this)
        ProcessLifecycleOwner.get().lifecycle.addObserver(graph.lock)
        graph.link.attach()
        ProcessLifecycleOwner.get().lifecycle.addObserver(object : DefaultLifecycleObserver {
            override fun onStart(owner: LifecycleOwner) {
                graph.errors.foreground = true
                val env = graph.env.value
                if (env.auth.signedIn.value) env.cache.refreshObserved()
                graph.link.setForeground(true)
            }

            override fun onStop(owner: LifecycleOwner) {
                graph.errors.foreground = false
                graph.link.setForeground(false)
            }
        })
    }
}
