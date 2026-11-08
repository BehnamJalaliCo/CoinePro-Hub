# kotlinx.serialization: keep generated serializers of the API models.
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.**
-keepclassmembers @kotlinx.serialization.Serializable class com.coinepro.hq.** {
    *** Companion;
    kotlinx.serialization.KSerializer serializer(...);
}
-keepclasseswithmembers class com.coinepro.hq.** {
    kotlinx.serialization.KSerializer serializer(...);
}
# OkHttp ships its own consumer rules; these platforms are optional at runtime.
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**

# The error log names a failure by its class (e.g. a broken stream): keep exception class names
# readable in release builds instead of R8's short names («jk6» in the 0.18.0 log).
-keepnames class * extends java.lang.Throwable
