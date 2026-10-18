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
import com.coinepro.hq.core.net.Hiring
import com.coinepro.hq.core.net.Hold
import com.coinepro.hq.core.net.Inquiry
import com.coinepro.hq.core.net.Lesson
import com.coinepro.hq.core.net.McpServer
import com.coinepro.hq.core.net.Message
import com.coinepro.hq.core.net.OversightSummary
import com.coinepro.hq.core.net.Page
import com.coinepro.hq.core.net.Protocol
import com.coinepro.hq.core.net.ProvisionRun
import com.coinepro.hq.core.net.RoleInfo
import com.coinepro.hq.core.net.ServerPlan
import com.coinepro.hq.core.net.ServiceAccount
import com.coinepro.hq.core.net.Skill
import com.coinepro.hq.core.net.StandingOrder
import com.coinepro.hq.core.net.StarRollup
import com.coinepro.hq.core.net.StarRubric
import com.coinepro.hq.core.net.Teaching
import com.coinepro.hq.core.net.ToolInfo
import com.coinepro.hq.core.net.hireableRoles
import com.coinepro.hq.core.net.effective
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
        assertTrue(list("/academy/evals", EvalSuite.serializer()).all { it.recent.isNotEmpty() })
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
        assertTrue(!b.wal.failing && b.baseBackup?.count == 9 && b.check?.ok == true && b.openbaoSnapshot.configured == false)
    }

    @Test
    fun academyMatchesTheContract() {
        // ⟨1.4.5⟩ §18.6: suites carry their cases and recent runs; runs carry their cost; every employee has a record.
        val suites = list("/academy/evals", com.coinepro.hq.core.net.EvalSuite.serializer())
        assertTrue(suites.all { it.cases.isNotEmpty() && it.recent.isNotEmpty() && it.baseline != null })
        val models = page("/academy/runs?latest=true&role=ceo&subject_kind=model", com.coinepro.hq.core.net.EvalRun.serializer())
        assertTrue(models.all { it.subject.kind == "model" && it.costUsd != null })
        assertEquals(3, models.map { it.subject.ref }.distinct().size)
        val r = decode("/academy/records/TY-CEO", com.coinepro.hq.core.net.TrainingRecord.serializer())
        assertTrue(r.trend.size == 12 && r.evals.isNotEmpty() && r.skills.isNotEmpty())
    }

    @Test
    fun backupStatusAsServedInPromptSeven() {
        // ⟨1.4.5⟩ §18.13: a failing WAL archive, a destination that errors, and nulls where nothing has run yet.
        val b = Api.json.decodeFromString(
            BackupStatus.serializer(),
            """{"hourly":{"last_at":null,"last_ok_at":null,"next_at":null,"ok":null,"error":"wal archive failing","stale":true,"snapshot":null,"size_bytes":null},
               "wal":{"last_archived_at":null,"lag_s":null,"failed_count":12,"failing":true,"ready_count":31},"base_backup":null,"check":null,
               "destinations":[{"key":"gdrive","configured":true,"ok":false,"error":"403","last_ok_at":null,"used_bytes":null,"quota_bytes":null}],
               "retention":{"hourly":168,"daily":90,"weekly":52,"monthly":36,"yearly":10},
               "restore_test":{"last_at":null,"ok":null,"duration_s":null,"notes":null,"pitr_target":null,"source":null},
               "openbao_snapshot":{"configured":false,"last_at":null,"ok":null},"encryption":"restic (AES-256)"}""",
        )
        assertTrue(b.wal.failing && b.wal.readyCount == 31 && b.hourly.stale == true && b.hourly.ok == null)
        assertEquals(false, b.destinations.single().ok)
    }

    @Test
    fun hiringIsClosedAndEveryCompanyHasSomeoneToHire() {
        // Owner, 2026-10-17: no hire now; the pending hire cards were withdrawn, not deleted.
        val h = decode("/owner/hiring", Hiring.serializer())
        assertEquals("closed", h.state)
        assertTrue(h.withdrawn.isNotEmpty())
        val all = page("/decisions?status=all", com.coinepro.hq.core.net.Decision.serializer())
        assertTrue(h.withdrawn.all { ref -> all.any { it.ref == ref && it.status == "withdrawn" } })
        assertTrue(all.none { it.kind == "hire" && it.status == "pending" })
        val roles = list("/roles", RoleInfo.serializer())
        assertTrue(hireableRoles(roles, "company", "TECH").any { it.role == "sre" })
        assertTrue(hireableRoles(roles, "holding", "OVS").size >= 3)
    }

    @Test
    fun storiesAndEnvelopesDecode() {
        val rings = list("/stories", com.coinepro.hq.core.net.StoryRing.serializer())
        assertTrue(rings.isNotEmpty() && rings.all { r -> r.items.isNotEmpty() && r.items.all { it.company == r.company && it.figures.size <= 3 } })
        assertTrue(rings.flatMap { it.items }.any { it.kind == "hire" && it.links.employee != null })
        // Rings with unseen stories come first.
        assertEquals(rings.sortedByDescending { it.unseen > 0 }.map { it.company }, rings.map { it.company })
        val h = decode("/owner/hiring", Hiring.serializer())
        assertTrue(h.envelopes.isNotEmpty() && h.envelopes.all { it.company != "HQ" })
        val roll = decode("/stars/rollup?period=week", com.coinepro.hq.core.net.StarRollup.serializer())
        assertTrue(roll.companies.all { it.parts.efficiency > 0 } && roll.employees.all { it.efficiency != null })
    }

    // ------------------------------------------------------------ ⟨1.4.4⟩ --
    @Test
    fun ownerToolsDecode() {
        assertTrue(page("/resolutions", com.coinepro.hq.core.net.Resolution.serializer()).any { it.source["decision"] != null })
        val ns = decode("/notification-settings", com.coinepro.hq.core.net.NotificationSettings.serializer())
        assertTrue(ns.matrix.containsKey("*"))
        assertEquals(true, ns.effective("TY", "urgent").inApp)
        val runs = page("/runs", com.coinepro.hq.core.net.Run.serializer())
        assertTrue(runs.any { it.state == "running" } && runs.any { it.state == "failed" })
        assertTrue(decode("/runs/run-0", com.coinepro.hq.core.net.Run.serializer()).stepsDetail.isNotEmpty())
        assertTrue(page("/treasury/calls", com.coinepro.hq.core.net.CallRow.serializer()).size > 25)
        assertEquals("ok", decode("/treasury/quota", com.coinepro.hq.core.net.QuotaView.serializer()).subscription.status)
        for (m in listOf("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5")) assertEquals(m, decode("/treasury/what-if?model=$m", com.coinepro.hq.core.net.WhatIf.serializer()).model)
        assertTrue(list("/budgets", com.coinepro.hq.core.net.BudgetUse.serializer()).any { it.scopeType == "holding" })
        assertTrue(list("/ops/sites", com.coinepro.hq.core.net.Site.serializer()).let { xs -> xs.any { it.canary } && xs.any { (it.uptime24h ?: 0.0) > 0.9 } })
        assertTrue(list("/ops/incidents", com.coinepro.hq.core.net.Incident.serializer()).any { it.closedAt == null })
        assertTrue(decode("/planner", com.coinepro.hq.core.net.Planner.serializer()).days.size > 60)
    }
}
