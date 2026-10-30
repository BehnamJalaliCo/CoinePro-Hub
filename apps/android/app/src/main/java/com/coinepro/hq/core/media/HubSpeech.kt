package com.coinepro.hq.core.media

import android.speech.SpeechRecognizer

// Contract §27.3 ⟨1.9⟩: speech to text on the hub. The phone's recogniser stays first for live dictation (words as the owner speaks);
// the hub (`POST /transcribe`, the pinned `small` faster-whisper; audio never leaves the hub) hears when the phone cannot: no recogniser,
// no Persian, or a recogniser that failed. Pure, so the choice is tested without a microphone.

/** Who hears the owner's voice. */
enum class SpeechEngine { PHONE, HUB, NONE }

/**
 * Whether the hub may be asked: not after it refused this session ([hubSession] false: `503 channel_not_configured`), yes when
 * `/meta.speech.enabled` says so, no when it says it is off; a hub that does not say (before ⟨1.9⟩) is tried once.
 */
fun hubUsable(hubEnabled: Boolean?, hubSession: Boolean?): Boolean = when {
    hubSession == false -> false
    hubEnabled != null -> hubEnabled
    else -> true
}

/** Who hears first: the phone when it has a recogniser that can do Persian, else the hub when it may be asked, else nobody (type). */
fun firstEngine(phoneAvailable: Boolean, phonePersian: Boolean?, hubEnabled: Boolean?, hubSession: Boolean?): SpeechEngine = when {
    phoneAvailable && phonePersian != false -> SpeechEngine.PHONE
    hubUsable(hubEnabled, hubSession) -> SpeechEngine.HUB
    else -> SpeechEngine.NONE
}

/** What follows a phone recogniser that ended without a result. */
enum class PhoneFallback {
    /** It had already heard words: they are what the owner said. */
    KEEP_WORDS,
    /** It failed: the hub records and transcribes instead (the owner says it again). */
    HUB,
    /** Nothing was said, or the microphone itself is the problem: tell the owner, the next tap tries again. */
    TELL,
    /** Neither can hear: say so, and offer to type. */
    TYPE,
}

/**
 * After the phone's recogniser failed with [code] (`SpeechRecognizer.ERROR_*`): words heard are kept; silence and a refused or busy
 * microphone are told (the hub needs the same microphone); any other failure (no Persian, no network for the phone's service, a busy or
 * broken recogniser) goes to the hub when it may be asked; otherwise the owner is told, or offered to type when the phone has no Persian.
 */
fun afterPhoneFailure(code: Int, unavailable: Boolean, heardWords: Boolean, hubOk: Boolean): PhoneFallback = when {
    heardWords -> PhoneFallback.KEEP_WORDS
    code == SpeechRecognizer.ERROR_NO_MATCH || code == SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> PhoneFallback.TELL
    code == SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS || code == SpeechRecognizer.ERROR_AUDIO -> PhoneFallback.TELL
    hubOk -> PhoneFallback.HUB
    unavailable -> PhoneFallback.TYPE
    else -> PhoneFallback.TELL
}

/** The sentence shown while the hub takes over from the phone. */
const val HUB_TAKES_OVER = "تشخیص گفتار گوشی کار نکرد؛ این بار هاب صدا را به متن میکند. دوباره بگو."

/** The line shown while the hub turns the recording into words. */
const val HUB_TRANSCRIBING = "هاب در حال تبدیل صدا…"
