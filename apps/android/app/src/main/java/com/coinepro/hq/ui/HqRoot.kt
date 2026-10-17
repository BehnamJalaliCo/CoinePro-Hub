package com.coinepro.hq.ui

import android.app.Activity
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.coinepro.hq.core.AppGraph
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.ui.auth.EnrolScreen
import com.coinepro.hq.ui.auth.LoginScreen
import com.coinepro.hq.ui.shell.Shell

/** Signed out → sign-in (or enrolment when an enrolment link opened the app); signed in → the shell. */
@Composable
fun HqRoot(graph: AppGraph, night: Boolean, enrolToken: String?, onEnrolConsumed: () -> Unit) {
    val env by graph.env.collectAsStateWithLifecycle()
    val signedIn by env.auth.signedIn.collectAsStateWithLifecycle()
    val toasts = remember { Toasts() }
    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val w = (view.context as Activity).window
            WindowCompat.getInsetsController(w, view).apply {
                isAppearanceLightStatusBars = !night
                isAppearanceLightNavigationBars = !night
            }
        }
    }
    LaunchedEffect(env, signedIn) {
        if (signedIn) env.stream.start() else {
            env.stream.stop()
            env.cache.clear()
        }
    }
    CompositionLocalProvider(LocalEnv provides env, LocalToasts provides toasts) {
        Box(Modifier.fillMaxSize().background(Divan.colors.page)) {
            when {
                enrolToken != null -> EnrolScreen(enrolToken, onDone = onEnrolConsumed)
                !signedIn -> LoginScreen(graph)
                else -> Shell(graph)
            }
            ToastHost(toasts)
        }
    }
}
