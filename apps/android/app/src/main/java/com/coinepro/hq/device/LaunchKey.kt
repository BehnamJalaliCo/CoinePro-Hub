package com.coinepro.hq.device

import android.content.Context
import android.content.Intent
import java.security.SecureRandom

/**
 * The app's own launches (a notification, the widget, the quick-settings tile) carry a secret only this app knows, kept in its private
 * preferences: an intent from another app (MainActivity is exported for the enrolment link) cannot open a page or mark a notification
 * read. Routes are further checked before navigating ([routeAllowed]).
 */
object LaunchKey {
    const val EXTRA = "com.coinepro.hq.KEY"
    private const val PREFS = "hq.launch"

    @Synchronized
    fun of(context: Context): String {
        val sp = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        sp.getString("key", null)?.let { return it }
        val k = ByteArray(24).also { SecureRandom().nextBytes(it) }.joinToString("") { "%02x".format(it) }
        sp.edit().putString("key", k).apply()
        return k
    }

    /** Signs [i] as the app's own. */
    fun sign(context: Context, i: Intent): Intent = i.putExtra(EXTRA, of(context))

    /** Whether [i] came from the app itself. */
    fun trusted(context: Context, i: Intent?): Boolean = i?.getStringExtra(EXTRA)?.let { it == of(context) } == true

    /** A route an outside launch may open: a known top-level place or a ref's page, letters, digits and `-/:` only. */
    fun routeAllowed(route: String?): Boolean =
        route != null && route.length <= 80 && Regex("^[a-z][a-z0-9-]*(/[A-Za-z0-9-]{1,40}){0,2}$").matches(route)
}
