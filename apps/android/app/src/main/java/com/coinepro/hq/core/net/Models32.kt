package com.coinepro.hq.core.net

import kotlinx.serialization.KSerializer
import kotlinx.serialization.Serializable
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonDecoder
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull

// ----------------------------------------------------------------- v1.14 --
// Contract §32 (prompt 23): talk. The owner's conversation with the holding secretary, the overseer, the assistant, the advisor and any
// manager, by text, by holding a button or hands-free; the voice engines with their key, light and meter. Same rules as Models.kt: camelCase
// here, snake_case on the wire; a field the hub omits takes its default. Money and prices are decimals on the hub, which may write them as a
// JSON number or as a string: [LenientDouble] reads both. An id the hub may write as a number or a string is a [JsonPrimitive] ([idText]).

/** A decimal the hub writes as a number or as a string ("0.4200"). */
object LenientDouble : KSerializer<Double> {
    override val descriptor: SerialDescriptor = PrimitiveSerialDescriptor("LenientDouble", PrimitiveKind.DOUBLE)
    override fun serialize(encoder: Encoder, value: Double) = encoder.encodeDouble(value)
    override fun deserialize(decoder: Decoder): Double {
        val e = (decoder as? JsonDecoder)?.decodeJsonElement() ?: return decoder.decodeDouble()
        return (e as? JsonPrimitive)?.let { it.doubleOrNull ?: it.contentOrNull?.toDoubleOrNull() } ?: 0.0
    }
}

// ---------------------------------------------------------------- §32.1 --
@Serializable
data class TalkVoicePick(val engine: String = "", val voice: String = "", val rate: Double = 1.0)

@Serializable
data class TalkBrain(val taskClass: String = "talk_turn", val effort: String? = null)

/** A persona is data: a charter, a voice, a brain setting and a tool allow-list. `manager` is the template filled by [role] and [company]. */
@Serializable
data class TalkPersona(
    /** secretary · overseer · assistant · advisor · manager */
    val key: String = "",
    val role: String = "",
    val titleFa: String = "",
    val company: String? = null,
    val voice: TalkVoicePick = TalkVoicePick(),
    val brain: TalkBrain = TalkBrain(),
    val tools: List<String> = emptyList(),
    /** The face: an avatar file of the hub. */
    val face: String? = null,
    val consultOnly: Boolean = false,
) {
    /** What the conversation's `persona` and `present` call it: the key, or `role@CODE` for a manager. */
    val id: String get() = if (key == "manager" && company != null && role.isNotBlank()) "$role@$company" else key
}

@Serializable
data class TalkCost(
    val tokens: Long = 0,
    @Serializable(with = LenientDouble::class) val usdEquiv: Double = 0.0,
    @Serializable(with = LenientDouble::class) val voiceUsd: Double = 0.0,
)

@Serializable
data class TalkConversation(
    val ref: String = "",
    val titleFa: String = "",
    /** The persona answering now: a key, or `role@CODE`. */
    val persona: String = "secretary",
    /** Who is in the room: keys, or objects the hub fills with the persona. Read with [presentIds]. */
    val present: List<JsonElement> = emptyList(),
    /** consult · work */
    val mode: String = "consult",
    val startedAt: String? = null,
    val lastTurnAt: String? = null,
    /** How many turns (the detail answer keeps the page of turns beside it, see [TalkDetail]). */
    val turns: Int = 0,
    val summaryFa: String? = null,
    val cost: TalkCost = TalkCost(),
    val openCards: Int = 0,
    /** ⟨1.16⟩ §34.2 the order this conversation is the session of: it opens as that session. */
    val orderRef: String? = null,
    /** ⟨1.17⟩ §35.3 a closed session's talk is read-only. */
    val closedAt: String? = null,
) {
    val presentIds: List<String>
        get() = present.mapNotNull { e ->
            when (e) {
                is JsonPrimitive -> e.contentOrNull
                is JsonObject -> (e["id"] as? JsonPrimitive)?.contentOrNull
                    ?: (e["key"] as? JsonPrimitive)?.contentOrNull?.let { k ->
                        val role = (e["role"] as? JsonPrimitive)?.contentOrNull
                        val co = (e["company"] as? JsonPrimitive)?.contentOrNull
                        if (k == "manager" && role != null && co != null) "$role@$co" else k
                    }
                else -> null
            }
        }.distinct()
}

@Serializable
data class TalkAudio(val seq: Int = 0, val fileId: String = "", val seconds: Double = 0.0, val engine: String = "")

@Serializable
data class TalkTokens(val input: Long = 0, val output: Long = 0, val cacheRead: Long = 0, val cacheWrite: Long = 0)

@Serializable
data class TalkTurnVoice(
    val engine: String = "",
    val seconds: Double = 0.0,
    val audioTokens: Long = 0,
    @Serializable(with = LenientDouble::class) val usd: Double = 0.0,
)

@Serializable
data class TalkTurn(
    val id: JsonPrimitive = JsonPrimitive(""),
    val conversation: String = "",
    val n: Int = 0,
    /** `owner`, or the persona that spoke (a key, or `role@CODE`). */
    val by: String = "owner",
    /** typed · hold · handsfree */
    val source: String = "typed",
    val text: String = "",
    val sayFa: String? = null,
    val showMd: String? = null,
    val cards: List<TalkCard> = emptyList(),
    val audio: List<TalkAudio> = emptyList(),
    val tokens: TalkTokens? = null,
    val voice: TalkTurnVoice? = null,
    /** streaming · done · stopped · failed */
    val state: String = "done",
    val reasonFa: String? = null,
    val at: String = "",
) {
    val owner: Boolean get() = by == "owner"
    /** What shows in the chat: the full answer of a persona, the words of the owner. */
    val shown: String get() = (if (owner) text else showMd ?: sayFa ?: text)
    val idText: String get() = id.contentOrNull.orEmpty()
}

@Serializable
data class TalkCard(
    val id: JsonPrimitive = JsonPrimitive(""),
    val turn: JsonPrimitive? = null,
    /** order · ask · hire · decision · planner · rule · automation · minutes · invite; ⟨1.17⟩ §35.4 delegate · budget · group · line */
    val kind: String = "order",
    val titleFa: String = "",
    val bodyFa: String = "",
    val payload: JsonObject = JsonObject(emptyMap()),
    /** offered · done · dismissed · failed */
    val state: String = "offered",
    val made: List<String> = emptyList(),
    val reasonFa: String? = null,
) {
    val idText: String get() = id.contentOrNull.orEmpty()
}

/** `POST /talk/conversations/{ref}/turns` → 202: the turn, and where its answer streams. */
@Serializable
data class TalkTurnOut(val turn: TalkTurn = TalkTurn(), val events: String? = null)

/** `POST /talk/cards/{id}/run` → what the card made. */
@Serializable
data class TalkCardRun(val made: List<String> = emptyList(), val card: TalkCard? = null)

/** A conversation and its page of turns, from `GET /talk/conversations/{ref}`: the hub may write the conversation's own fields with the
 *  turns beside them, or `{conversation, turns}`; read with [parse]. */
data class TalkDetail(val conversation: TalkConversation, val turns: List<TalkTurn>) {
    companion object {
        fun parse(e: JsonElement): TalkDetail {
            val o = e as? JsonObject ?: return TalkDetail(TalkConversation(), emptyList())
            val conv = (o["conversation"] as? JsonObject) ?: o
            val rawTurns = listOf("turns_page", "turns", "items", "page").firstNotNullOfOrNull { k ->
                o[k]?.takeIf { it is JsonArray || (it is JsonObject && it["items"] is JsonArray) }
            }
            val turns = rawTurns?.itemsOrSelf()?.map { Api.json.decodeFromJsonElement(TalkTurn.serializer(), it) }.orEmpty()
            // `turns` as a number is the conversation's count, not the page.
            val c = Api.json.decodeFromJsonElement(TalkConversation.serializer(), JsonObject(conv.filterKeys { k -> k != "turns" || conv[k] is JsonPrimitive }))
            return TalkDetail(c, turns)
        }
    }
}

// ---------------------------------------------------------------- §32.5 --
@Serializable
data class VoiceVoice(val name: String = "", val genderFa: String? = null, val sampleFile: String? = null)

@Serializable
data class VoicePriceNext(
    val from: String = "",
    @Serializable(with = LenientDouble::class) val textInPerM: Double = 0.0,
    @Serializable(with = LenientDouble::class) val audioOutPerM: Double = 0.0,
)

@Serializable
data class VoicePrice(
    @Serializable(with = LenientDouble::class) val textInPerM: Double = 0.0,
    @Serializable(with = LenientDouble::class) val audioOutPerM: Double = 0.0,
    @Serializable(with = LenientDouble::class) val audioTokensPerS: Double = 25.0,
    val validUntil: String? = null,
    val next: VoicePriceNext? = null,
    val sourceUrl: String? = null,
    val asOf: String? = null,
)

@Serializable
data class VoiceEngine(
    val key: String = "",
    val titleFa: String = "",
    /** google · local */
    val provider: String = "google",
    val model: String = "",
    val languages: Int = 0,
    val rankFa: String = "",
    /** The provider's key shape (a regex): a pasted key never goes into the composer. */
    val keyPattern: String? = null,
    /** missing · checking · ok · failing · capped */
    val state: String = "missing",
    val reasonFa: String? = null,
    val checkedAt: String? = null,
    val price: VoicePrice = VoicePrice(),
    val voices: List<VoiceVoice> = emptyList(),
)

/** `PUT /voice/providers/{provider}/secret` → 202 `{state: "checking"}`. */
@Serializable
data class VoiceSecretOut(val state: String = "checking")

/** `POST /voice/sample` → a short sample and what it cost. */
@Serializable
data class TalkVoiceSample(
    val fileId: String = "",
    val seconds: Double = 0.0,
    @Serializable(with = LenientDouble::class) val usd: Double = 0.0,
    val engine: String = "",
)

// ---------------------------------------------------------------- §32.6 --
@Serializable
data class MeterEngine(
    val engine: String = "",
    @Serializable(with = LenientDouble::class) val usd: Double = 0.0,
    @Serializable(with = LenientDouble::class) val seconds: Double = 0.0,
    val audioTokens: Long = 0,
)

@Serializable
data class MeterPersona(
    val persona: String = "",
    @Serializable(with = LenientDouble::class) val usd: Double = 0.0,
    @Serializable(with = LenientDouble::class) val seconds: Double = 0.0,
)

@Serializable
data class VoiceMeter(
    /** today · month */
    val period: String = "month",
    @Serializable(with = LenientDouble::class) val voiceUsd: Double = 0.0,
    @Serializable(with = LenientDouble::class) val capUsd: Double? = null,
    @Serializable(with = LenientDouble::class) val projectedUsd: Double = 0.0,
    val byEngine: List<MeterEngine> = emptyList(),
    val byPersona: List<MeterPersona> = emptyList(),
    /** The tokens of the talk turns: a number, or the ledger's parts (read with [tokensTotal]). */
    val talkTokens: JsonElement? = null,
    @Serializable(with = LenientDouble::class) val talkUsdEquiv: Double = 0.0,
    val priceNoteFa: String? = null,
    val updatedAt: String? = null,
) {
    val tokensTotal: Long
        get() = when (val t = talkTokens) {
            is JsonPrimitive -> t.contentOrNull?.toDoubleOrNull()?.toLong() ?: 0L
            is JsonObject -> t.values.sumOf { (it as? JsonPrimitive)?.contentOrNull?.toDoubleOrNull()?.toLong() ?: 0L }
            else -> 0L
        }
}

/** The `voice` block of `/owner/settings` (§32.6): the owner's cap, when to warn, and the chain after the persona's own engine. */
@Serializable
data class VoiceSettings(
    @Serializable(with = LenientDouble::class) val monthCapUsd: Double? = null,
    @Serializable(with = LenientDouble::class) val warnAt: Double = 0.8,
    val chain: List<String> = emptyList(),
)
