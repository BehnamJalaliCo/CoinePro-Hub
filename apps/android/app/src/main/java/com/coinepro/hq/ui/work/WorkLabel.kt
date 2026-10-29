package com.coinepro.hq.ui.work

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.coinepro.hq.core.data.LabelState
import com.coinepro.hq.ui.LocalEnv

/** A work item's ref and title for a line that carries only its id or ref; looked up once per session (the shared cache). */
@Composable
fun rememberWorkLabel(key: String?): LabelState? {
    if (key.isNullOrBlank()) return null
    val env = LocalEnv.current
    val map by env.works.labels.collectAsStateWithLifecycle()
    LaunchedEffect(env, key) { env.works.request(key) }
    return map[key] ?: LabelState.Loading
}
