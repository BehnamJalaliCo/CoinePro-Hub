// AGP 9 compiles Kotlin itself (built-in Kotlin); kotlin-android is declared only to pin KGP to the
// version the Compose and serialization compiler plugins are built for. It is never applied.
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.android) apply false
    alias(libs.plugins.kotlin.compose) apply false
    alias(libs.plugins.kotlin.serialization) apply false
    alias(libs.plugins.roborazzi) apply false
}
