package com.coinepro.hq

/**
 * ⟨1.0.1⟩ Pictures in a screenshot: Coil decodes with the platform's `ImageDecoder` into hardware bitmaps from Android 10 on, and
 * the tests' JVM has neither (every picture was an empty frame). A test class that draws files calls [picturesOn] before it enters
 * the demo and [picturesOff] after, so the demo's posters and pictures are decoded by `BitmapFactory` into software bitmaps and drawn.
 */
fun picturesOn() { com.coinepro.hq.core.media.softwarePictures = true }

fun picturesOff() { com.coinepro.hq.core.media.softwarePictures = false }
