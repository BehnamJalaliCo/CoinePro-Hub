import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.roborazzi)
}

// Release signing comes from the owner: keystore.properties (git-ignored, mode 600) on their machine, or the
// HQ_SIGNING_* environment variables in CI. Without it the release build is signed with the debug key and is
// only fit for side-loading; passkeys need the owner's key (its SHA-256 goes into assetlinks and the API).
val signing = Properties().apply {
    val f = rootProject.file("keystore.properties")
    if (f.exists()) f.inputStream().use(::load)
}
fun signingValue(key: String, env: String): String? = signing.getProperty(key) ?: System.getenv(env)

android {
    namespace = "com.coinepro.hq"
    compileSdk = 37

    defaultConfig {
        applicationId = "com.coinepro.hq"
        minSdk = 28
        targetSdk = 36
        versionCode = 1
        versionName = "1.0.0"
        // The hub's public origin; also the WebAuthn relying party (contract §2).
        buildConfigField("String", "HQ_ORIGIN", "\"https://hq.coinepro.com\"")
    }

    signingConfigs {
        val store = signingValue("storeFile", "HQ_SIGNING_STORE_FILE")
        if (store != null) {
            create("owner") {
                storeFile = file(store)
                storePassword = signingValue("storePassword", "HQ_SIGNING_STORE_PASSWORD")
                keyAlias = signingValue("keyAlias", "HQ_SIGNING_KEY_ALIAS")
                keyPassword = signingValue("keyPassword", "HQ_SIGNING_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = signingConfigs.findByName("owner") ?: signingConfigs.getByName("debug")
        }
    }

    androidResources {
        localeFilters += listOf("fa", "en")
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    testOptions {
        unitTests {
            isIncludeAndroidResources = true
        }
    }

    packaging {
        resources.excludes += setOf("/META-INF/{AL2.0,LGPL2.1}", "/META-INF/versions/9/OSGI-INF/MANIFEST.MF")
    }
}

roborazzi {
    outputDir.set(file("src/test/screenshots"))
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.process)
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.graphics)
    implementation(libs.compose.ui.text)
    implementation(libs.compose.foundation)
    implementation(libs.compose.animation)
    implementation(libs.compose.material3)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.credentials)
    implementation(libs.credentials.play.services)
    implementation(libs.okhttp)
    implementation(libs.okhttp.sse)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.kotlinx.coroutines.android)
    debugImplementation(libs.compose.ui.tooling)
    debugImplementation(libs.compose.ui.test.manifest)

    testImplementation(libs.junit)
    testImplementation(libs.androidx.test.core)
    testImplementation(libs.kotlinx.coroutines.test)
    testImplementation(libs.okhttp.mockwebserver)
    testImplementation(libs.robolectric)
    testImplementation(platform(libs.compose.bom))
    testImplementation(libs.compose.ui.test.junit4)
    testImplementation(libs.roborazzi)
    testImplementation(libs.roborazzi.compose)
    testImplementation(libs.roborazzi.junit.rule)
}
