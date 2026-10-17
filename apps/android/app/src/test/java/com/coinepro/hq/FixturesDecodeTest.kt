package com.coinepro.hq

import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.BackupStatus
import com.coinepro.hq.core.net.Challenge
import com.coinepro.hq.core.net.Curriculum
import com.coinepro.hq.core.net.EgressEntry
import com.coinepro.hq.core.net.EgressSummary
import com.coinepro.hq.core.net.Errand
import com.coinepro.hq.core.net.EvalSuite
import com.coinepro.hq.core.net.Finding
import com.coinepro.hq.core.net.Founding
import com.coinepro.hq.core.net.Hold
import com.coinepro.hq.core.net.Inquiry
import com.coinepro.hq.core.net.Lesson
import com.coinepro.hq.core.net.McpServer
import com.coinepro.hq.core.net.Message
import com.coinepro.hq.core.net.OversightSummary
import com.coinepro.hq.core.net.Page
import com.coinepro.hq.core.net.Protocol
import com.coinepro.hq.core.net.ProvisionRun
import com.coinepro.hq.core.net.ServerPlan
import com.coinepro.hq.core.net.ServiceAccount
import com.coinepro.hq.core.net.Skill
import com.coinepro.hq.core.net.StandingOrder
import com.coinepro.hq.core.net.StarRollup
import com.coinepro.hq.core.net.StarRubric
import com.coinepro.hq.core.net.Teaching
import com.coinepro.hq.core.net.ToolInfo
import java.io.File
import kotlinx.serialization.KSerializer
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** Every v1.4 response the demo serves (the same fixtures as the web's mock, written from contract §18) decodes into the
 *  app's models, and the parts the screens lean on are there. A field renamed on one side fails here, not on a phone. */
class FixturesDecodeTest {
    private val fixtures = Api.json.parseToJsonElement(File("src/debug/assets/demo-fixtures.json").readText()).jsonObject

    private fun body(key: String): JsonElement {
        val v = requireNotNull(fixtures[key]) { "missing fixture $key" }.jsonObject
        assertEquals("status of $key", "200", v["status"].toString())
        return v["body"]!!
    }

    private fun <T> decode(key: String, s: KSerializer<T>): T = Api.json.decodeFromJsonElement(s, body(key))
    private fun <T> list(key: String, s: KSerializer<T>): List<T> = decode(key, ListSerializer(s))
    private fun <T> page(key: String, s: KSerializer<T>): List<T> = decode(key, Page.serializer(s)).items

    @Test
    fun oversight() {
        val s = decode("/oversight/summary", OversightSummary.serializer())
        assertTrue(s.compliance.isNotEmpty() && s.compliance.all { it.trend.size >= 2 })
        assertTrue(list("/oversight/holds?state=held", Hold.serializer()).all { it.state == "held" })
        assertTrue(page("/oversight/findings", Finding.serializer()).any { it.severity == "critical" })
        assertTrue(list("/oversight/protocols", Protocol.serializer()).size >= 40)
        assertTrue(page("/oversight/challenges", Challenge.serializer()).isNotEmpty())
        assertTrue(list("/oversight/orders", StandingOrder.serializer()).any { it.status == "proposed" })
        assertTrue(page("/inquiries?from=HQ-ADV", Inquiry.serializer()).all { it.from.code == "HQ-ADV" })
        assertTrue(page("/threads/N/messages", Message.serializer()).isNotEmpty())
    }

    @Test
    fun assistantStarsSkillsAcademy() {
        assertTrue(page("/errands", Errand.serializer()).any { it.status == "waiting_owner" && it.decisionRef != null })
        assertTrue(page("/threads/P/messages", Message.serializer()).isNotEmpty())
        for (p in listOf("week", "month")) {
            val r = decode("/stars/rollup?period=$p", StarRollup.serializer())
            assertEquals(p, r.period)
            assertTrue(r.companies.any { it.company == r.bestCompany } && r.companies.all { it.stars in 0.0..5.0 })
        }
        assertTrue(list("/stars/rubrics", StarRubric.serializer()).all { it.criteria.sumOf { c -> c.weight } in 99.0..101.0 })
        assertTrue(page("/lessons", Lesson.serializer()).isNotEmpty())
        val skills = list("/skills", Skill.serializer())
        assertTrue(skills.any { it.status == "approved" && it.eval?.passed == true })
        assertTrue(list("/academy/curricula", Curriculum.serializer()).any { it.role == "overseer" })
        assertTrue(list("/academy/evals", EvalSuite.serializer()).all { it.runs.isNotEmpty() })
        assertTrue(list("/academy/teach", Teaching.serializer()).any { it.status == "proposed" })
    }

    @Test
    fun toolsFoundingBackups() {
        assertTrue(decode("/egress/summary?period=day", EgressSummary.serializer()).requests > 0)
        assertTrue(page("/egress", EgressEntry.serializer()).any { it.blockedReason != null })
        assertTrue(list("/tools/mcp", McpServer.serializer()).any { it.status == "pending" })
        assertTrue(list("/tools/accounts", ServiceAccount.serializer()).isNotEmpty())
        assertTrue(list("/tools/catalog", ToolInfo.serializer()).any { it.name == "web.search" })
        assertTrue(page("/foundings", Founding.serializer()).map { it.state }.containsAll(listOf("proposed", "ready_for_login")))
        assertEquals("proposed", decode("/foundings/C-0002", Founding.serializer()).state)
        val plan = decode("/provisioning/plans/PV-0002", ServerPlan.serializer())
        assertTrue(plan.digest.isNotBlank() && plan.state == "proposed")
        val run = decode("/provisioning/runs/r1", ProvisionRun.serializer())
        assertTrue(run.state == "done" && run.login != null && run.steps.all { it.state == "done" })
        val b = decode("/backups/status", BackupStatus.serializer())
        assertTrue(b.destinations.any { it.key == "gdrive" } && b.retention.hourly > 0)
    }
}
