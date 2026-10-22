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
import com.coinepro.hq.core.net.management
import com.coinepro.hq.core.net.draft
import com.coinepro.hq.core.net.payloadAs
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
        assertTrue(page("/foundings", Founding.serializer()).map { it.state }.containsAll(listOf("auditing", "proposed", "ready_for_login")))
        val c2 = decode("/foundings/C-0002", Founding.serializer())
        assertEquals("proposed", c2.state)
        // ⟨1.4.8⟩ §18.16: money is a decimal string, audit scores are 0..10, the plan is a ref beside its detail.
        assertEquals("60.00", c2.proposal?.monthlyUsd)
        assertTrue(c2.audit!!.scores.values.all { it == null || it in 0.0..10.0 } && c2.planDetail?.ref == c2.plan)
        val c3 = decode("/foundings/C-0003", Founding.serializer())
        assertTrue(c3.nameFa == null && c3.code == null && c3.title.isNotBlank())
        val plan = decode("/provisioning/plans/PV-0002", ServerPlan.serializer())
        assertTrue(plan.digest.isNotBlank() && plan.state == "proposed" && plan.sealable)
        val unpriced = decode("/provisioning/plans/PV-0003", ServerPlan.serializer())
        assertTrue(unpriced.founding == null && unpriced.monthlyEur == null && unpriced.problems.isNotEmpty() && !unpriced.sealable)
        assertTrue(decode("/provisioning/plans/PV-0001", ServerPlan.serializer()).firewall.any { it.protocol == "icmp" && it.port == null })
        val run = decode("/provisioning/runs/r1", ProvisionRun.serializer())
        assertTrue(run.state == "done" && run.login != null && run.steps.all { it.state == "done" && it.logTail.isNotEmpty() })
        assertTrue(run.server!!.hostKeys.isNotEmpty())
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

    // ------------------------------------------------------------ ⟨1.4.6⟩ --
    @Test
    fun brandsAndSealsDecode() {
        // §18.14: every built-in company has an active seed version 1 in /brands, with the same layers its versions carry.
        val brands = decode("/brands", com.coinepro.hq.core.net.Brands.serializer())
        assertEquals(setOf("FX", "PC", "TY"), brands.companies.keys)
        assertTrue(brands.companies.values.all { b -> b.version == 1 && b.mark.layers.isNotEmpty() && b.mark.layers.all { it.d.isNotBlank() && it.role in setOf("ink", "accent") } })
        assertTrue(brands.companies.values.all { b -> (b.accent != null) == b.mark.layers.any { it.role == "accent" } })
        for (code in brands.companies.keys) {
            val view = decode("/companies/$code/brand", com.coinepro.hq.core.net.CompanyBrandView.serializer())
            val active = requireNotNull(view.active)
            assertTrue(active.state == "active" && active.source.kind == "seed" && active.digest.length == 64 && view.proposed == null)
            assertEquals(brands.companies.getValue(code).mark, active.mark)
            assertTrue(active.checks!!.warnings.isEmpty() && active.checks!!.minFeaturePx16 > 0)
            assertEquals(listOf(active), list("/companies/$code/brand/versions", com.coinepro.hq.core.net.CompanyBrand.serializer()))
        }
        // A founded company with no brand yet: nothing to draw, so it shows its code, and the founding's step says so.
        assertEquals(com.coinepro.hq.core.net.CompanyBrandView(), decode("/companies/AC/brand", com.coinepro.hq.core.net.CompanyBrandView.serializer()))
        assertTrue(list("/companies/AC/brand/versions", com.coinepro.hq.core.net.CompanyBrand.serializer()).isEmpty())
        val f = decode("/foundings/C-0001", Founding.serializer())
        assertTrue(f.company == "AC" && f.brand.state == "missing" && f.brand.version == null)
        assertTrue(page("/foundings", Founding.serializer()).all { it.company != null || it.brand.state == "missing" })
        val companies = list("/companies", com.coinepro.hq.core.net.Company.serializer())
        assertTrue(companies.all { c -> c.brandVersion == brands.companies[c.code]?.version })
    }

    @Test
    fun brandVersionsAsTheContractDescribesThem() {
        // A proposal from an upload, and a failed one: mark null, the reason stable.
        val v = Api.json.decodeFromString(
            com.coinepro.hq.core.net.CompanyBrand.serializer(),
            """{"company":"AC","version":2,"state":"proposed","source":{"kind":"upload","file_id":"f1","path":null,"sha256":"ab","width":1200,"height":800,"has_alpha":true},
               "mark":{"vb":"0 0 120 80","layers":[{"role":"ink","color":"#111216","d":"M0 0L1 1Z"},{"role":"accent","color":"#0FB5AE","d":"M2 2L3 3Z"}]},"wordmark":null,
               "ink":"#111216","accent":"#0FB5AE","accent_night":null,"accent_day":"#08756F","palette":[{"hex":"#111216","share":0.7},{"hex":"#0FB5AE","share":0.3}],
               "options":{"colors":2,"detail":3},"checks":{"paths_bytes":20,"min_feature_px_16":0.8,"iou":0.93,"contrast_night":7.6,"contrast_day":2.2,
               "warnings":["در اندازه‌ی کوچک جزئیات گم میشود"]},"digest":"d1","status_reason":null,"created_at":"2026-10-22T08:00:00Z","activated_at":null}""",
        )
        assertTrue(v.checks!!.minFeaturePx16 < 1 && v.accentDay == "#08756F" && v.accentNight == null && v.options.colors == 2 && v.source.hasAlpha)
        val failed = Api.json.decodeFromString(com.coinepro.hq.core.net.CompanyBrand.serializer(), """{"company":"AC","version":3,"state":"failed","mark":null,"checks":null,"status_reason":"no_background"}""")
        assertTrue(failed.mark == null && failed.statusReason == "no_background")
        // 409 not_ready names what is missing (§18.8).
        val p = Api.json.decodeFromString(com.coinepro.hq.core.net.Problem.serializer(), """{"code":"not_ready","message_fa":"…","missing":["brand"],"status":409}""")
        assertEquals(listOf("brand"), p.missing)
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

    // ------------------------------------------------------------ ⟨1.5⟩ --
    private val operating: List<String> get() = list("/companies", com.coinepro.hq.core.net.Company.serializer()).filter { it.kind != "holding" }.map { it.code }

    @Test
    fun revenueRadarFunnelAndRescueDecode() {
        // §19.1: the accounts, 30 settled days of each, and every period's summary for the holding and for each company.
        val accounts = list("/revenue/accounts", com.coinepro.hq.core.net.RevenueAccount.serializer())
        assertTrue(accounts.isNotEmpty() && accounts.any { it.status == "error" && it.lastError != null } && accounts.any { it.status == "ok" && it.lastPullAt != null })
        val days = list("/revenue/days", com.coinepro.hq.core.net.RevenueDay.serializer())
        assertEquals(30, days.map { it.day }.distinct().size)
        assertTrue(days.all { it.commissionUsdt.toDouble() >= 0 && it.byCoin.isNotEmpty() && it.source.endpoints.isNotEmpty() })
        assertTrue(days.map { it.account }.toSet() == accounts.map { it.id }.toSet())
        for (p in listOf("day", "week", "month")) {
            val s = decode("/revenue/summary?period=$p", com.coinepro.hq.core.net.RevenueSummary.serializer())
            assertEquals(p, s.period)
            // ⟨1.5.1⟩ shares are 0..1 and add up; money is a decimal string.
            assertTrue(s.byCompany.all { it.share in 0.0..1.0 })
            assertEquals(1.0, s.byCompany.sumOf { it.share }, 0.001)
            assertEquals(s.totalUsdt.toDouble(), s.byCompany.sumOf { it.usdt.toDouble() }, 0.05)
            for (co in operating) {
                val one = decode("/revenue/summary?company=$co&period=$p", com.coinepro.hq.core.net.RevenueSummary.serializer())
                assertTrue(one.byCompany.all { it.company == co } && one.alerts.all { it.company == co })
            }
        }
        val month = decode("/revenue/summary?period=month", com.coinepro.hq.core.net.RevenueSummary.serializer())
        assertTrue(month.alerts.any { it.kind == "drop" } && month.alerts.any { it.kind == "pull_failed" } && month.prevTotalUsdt != null)
        assertEquals(30, month.trend.size)
        // §19.2: a stage with no source has no count, and a rate is never estimated.
        for (co in operating) for (p in listOf("week", "month")) {
            val f = decode("/growth/funnel?company=$co&period=$p", com.coinepro.hq.core.net.Funnel.serializer())
            assertTrue(f.stages.size == 5 && f.stages.all { (it.count != null) == it.connected && (it.source != null) == it.connected })
            assertTrue(f.conversions.all { c -> c.rate == null || c.rate!! in 0.0..1.0 } && f.leaks.all { it.rate in 0.0..1.0 && it.medianRate in 0.0..1.0 })
        }
        val rescue = page("/growth/rescue", com.coinepro.hq.core.net.RescueCase.serializer())
        assertTrue(rescue.map { it.state }.containsAll(listOf("open", "contacted", "rescued", "lost", "opted_out")))
        for (rc in rescue) assertEquals(rc, decode("/growth/rescue/${rc.ref}", com.coinepro.hq.core.net.RescueCase.serializer()))
        assertTrue(rescue.all { it.subject.startsWith("sb_") && (it.state != "rescued" || it.rescuedAt != null) })
    }

    @Test
    fun supportDeskDecodes() {
        // §19.3: channels in every state, every conversation with its messages, and the teaching queue.
        val channels = list("/support/channels", com.coinepro.hq.core.net.SupportChannel.serializer())
        assertTrue(channels.map { it.state }.toSet().containsAll(listOf("live", "shadow", "paused", "not_configured")))
        assertTrue(channels.filter { it.state == "paused" || it.state == "live" }.all { it.liveSince != null } && channels.all { it.version >= 1 })
        val convs = page("/support/conversations", com.coinepro.hq.core.net.Conversation.serializer())
        assertTrue(convs.isNotEmpty() && convs.all { it.messages.isEmpty() })
        for (c in convs) {
            val d = decode("/support/conversations/${c.ref}", com.coinepro.hq.core.net.Conversation.serializer())
            assertTrue(d.messages.isNotEmpty() && d.messages.all { it.conversation == c.ref } && d.lastMessageAt == c.lastMessageAt)
        }
        // The agent's draft the guard refused: stored, never sent, with its reasons.
        val blocked = decode("/support/conversations/SC-000411", com.coinepro.hq.core.net.Conversation.serializer()).messages.single { it.status == "blocked" }
        assertTrue(blocked.checks.guard == "fail" && blocked.blockedReasons == listOf("unknown_link") && blocked.kbRefs.isNotEmpty() && blocked.confidence != null)
        assertTrue(convs.any { it.mystery } && convs.any { it.handoff?.reason == "security" } && convs.any { it.csat != null })
        val queue = list("/support/queue", com.coinepro.hq.core.net.QueueItem.serializer())
        assertTrue(queue.isNotEmpty() && queue.all { q -> convs.any { it.ref == q.conversation && it.state == "waiting_owner" } })
        assertTrue(queue.any { it.kind == "blocked" && it.draft?.blockedReasons == listOf("unknown_link") } && queue.any { it.draft == null })
        // §19.4: knowledge with its digest, the policy key, approved links and codes; the shadow reports.
        val kb = list("/support/kb", com.coinepro.hq.core.net.KbArticle.serializer())
        assertTrue(kb.all { it.sha256.length == 64 && it.expiresAt.isNotEmpty() } && kb.map { it.status }.toSet() == setOf("proposed", "approved", "expired", "retired"))
        assertTrue(kb.any { it.kind == "referral" && it.status == "approved" && it.codes.isNotEmpty() && it.links.isNotEmpty() } && kb.any { it.key == "vip.min_balance" })
        val shadow = list("/support/shadow", com.coinepro.hq.core.net.ShadowReport.serializer())
        assertTrue(shadow.any { it.pass } && shadow.any { !it.pass && it.safetyFailures > 0 } && shadow.all { it.correct + it.partial + it.wrong == it.total && it.threshold == 0.9 })
    }

    @Test
    fun growthFeedbackIntakeAndTheirCardsDecode() {
        // §19.5: templates with their digest, rules naming a template version, NPS waves (no score without answers).
        val templates = list("/growth/templates", com.coinepro.hq.core.net.Template.serializer())
        assertTrue(templates.all { it.sha256.length == 64 } && templates.any { it.status == "proposed" } && templates.any { it.status == "sealed" && it.sealedAt != null })
        val rules = list("/growth/rules", com.coinepro.hq.core.net.LifecycleRule.serializer())
        assertTrue(rules.all { Regex("^TM-\\d{4}@\\d+$").matches(it.template) && it.limits.quietHours.size == 2 } && rules.map { it.status }.toSet() == setOf("active", "paused", "proposed"))
        assertTrue(rules.any { it.trigger.rrule != null } && rules.any { it.trigger.inactiveDays != null } && rules.any { it.trigger.event != null })
        val waves = list("/growth/nps", com.coinepro.hq.core.net.NpsWave.serializer())
        assertTrue(waves.all { w -> (w.score == null) == (w.responses == 0) && (w.score ?: 0) in -100..100 && w.promoters + w.passives + w.detractors == w.responses })
        // §19.7: most frequent first, at most three masked quotes.
        val feedback = page("/feedback", com.coinepro.hq.core.net.FeedbackItem.serializer())
        assertEquals(feedback.sortedByDescending { it.count }, feedback)
        assertTrue(feedback.all { it.quotes.size <= 3 && it.sources.all { s -> s.startsWith("SC-") || s.startsWith("NP-") } } && feedback.any { it.workRef != null })
        // §19.8
        val intake = list("/intake/sources", com.coinepro.hq.core.net.IntakeSource.serializer())
        assertTrue(intake.any { it.configured && it.events24h > 0 } && intake.any { !it.configured && it.lastEventAt == null })
        // §19.9 ⟨1.5.1⟩: the three cards wait in the cartable, each payload in the shape the apps read.
        val pending = page("/decisions?status=pending", com.coinepro.hq.core.net.Decision.serializer())
        val cards = pending.filter { it.kind in setOf("message_template", "lifecycle_rule", "support_go_live") }
        assertEquals(setOf("message_template", "lifecycle_rule", "support_go_live"), cards.map { it.kind }.toSet())
        for (d in cards) assertEquals(d.ref, decode("/decisions/${d.ref}", com.coinepro.hq.core.net.Decision.serializer()).ref)
        val tpl = cards.single { it.kind == "message_template" }.payload
        val t = Api.json.decodeFromJsonElement(com.coinepro.hq.core.net.Template.serializer(), tpl["template"]!!)
        assertEquals(t.sha256, (tpl["sha256"] as kotlinx.serialization.json.JsonPrimitive).content)
        val rule = cards.single { it.kind == "lifecycle_rule" }.payload
        val r = Api.json.decodeFromJsonElement(com.coinepro.hq.core.net.LifecycleRule.serializer(), rule["rule"]!!)
        assertEquals(r.template, (rule["template"] as kotlinx.serialization.json.JsonPrimitive).content)
        assertEquals(r.limits, Api.json.decodeFromJsonElement(com.coinepro.hq.core.net.RuleLimits.serializer(), rule["limits"]!!))
        val live = cards.single { it.kind == "support_go_live" }.payload
        val report = Api.json.decodeFromJsonElement(com.coinepro.hq.core.net.ShadowReport.serializer(), live["shadow_report"]!!)
        assertTrue(report.pass && channels(live["channel"]).let { ch -> ch.state == "shadow" && ch.liveSince == null })
    }

    private fun channels(kind: kotlinx.serialization.json.JsonElement?): com.coinepro.hq.core.net.SupportChannel =
        list("/support/channels", com.coinepro.hq.core.net.SupportChannel.serializer()).first { it.kind == (kind as kotlinx.serialization.json.JsonPrimitive).content }

    @Test
    fun guardRefusalDecodes() {
        // §19.9: `422 send_blocked` carries the guard's codes.
        val p = Api.json.decodeFromString(com.coinepro.hq.core.net.Problem.serializer(), """{"code":"send_blocked","message_fa":"…","status":422,"blocked_reasons":["unknown_link","profit_promise"]}""")
        assertEquals(listOf("unknown_link", "profit_promise"), p.blockedReasons)
    }

    // ------------------------------------------------------------ ⟨1.5⟩ §20 --
    @Test
    fun meetingsDecode() {
        val types = list("/meetings/settings", com.coinepro.hq.core.net.MeetingType.serializer())
        // Only the war room has no meeting cap; it and the post-mortem are opened by an event.
        assertTrue(types.single { it.key == "war_room" }.let { it.budgetTokens == null && it.schedule == null })
        assertTrue(types.filter { it.key != "war_room" }.all { it.budgetTokens != null && it.maxRounds in 1..3 && it.maxSpeakers in 2..8 })
        val ms = page("/meetings", com.coinepro.hq.core.net.Meeting.serializer())
        assertTrue(ms.map { it.state }.containsAll(listOf("live", "prep", "scheduled", "ended")))
        assertTrue(ms.any { it.mode == "written" && it.trimmedFa != null } && ms.any { it.type == "war_room" && it.budget.cap == null && it.incident != null })
        for (m in ms) {
            assertEquals(m, decode("/meetings/${m.ref}", com.coinepro.hq.core.net.Meeting.serializer()))
            val t = decode("/meetings/${m.ref}/turns", com.coinepro.hq.core.net.TurnsPage.serializer())
            assertTrue(t.items.all { it.meeting == m.ref } && m.participants.count { it.devil } <= 1)
            // Before it starts a meeting shows its estimate; once started its budget counts every turn's tokens.
            if (m.before) assertEquals(0L, m.budget.used) else assertTrue(m.budget.used >= t.items.sumOf { it.tokens })
        }
        val live = ms.single { it.state == "live" }
        val turns = decode("/meetings/${live.ref}/turns", com.coinepro.hq.core.net.TurnsPage.serializer())
        assertTrue(turns.whispers.isNotEmpty() && live.currentItem != null && live.drafts.isNotEmpty() && live.drafts.all { it.decision == null })
        assertTrue(turns.items.flatMap { it.claims }.any { it.status == "unsourced" && it.source == null })
        assertTrue(body("#script:${live.ref}").jsonObject["items"]!!.let { it as kotlinx.serialization.json.JsonArray }.isNotEmpty())
        val ended = ms.first { it.state == "ended" && it.drafts.isNotEmpty() }
        assertTrue(ended.minutes != null && ended.drafts.all { it.decision != null })
        val votes = decode("/meetings/${ended.ref}/turns", com.coinepro.hq.core.net.TurnsPage.serializer()).items.filter { it.kind == "vote" }
        assertTrue(votes.all { it.stance != null })
        assertEquals(votes.size, ended.drafts.first().votes.total)
    }

    @Test
    fun charterAndKnowledgeDecode() {
        val scopes = list("/charter", com.coinepro.hq.core.net.CharterScope.serializer())
        assertEquals("holding", scopes.first().scope)
        assertTrue(scopes.any { it.proposed != null && it.sealed == null } && scopes.any { it.versions.size > 1 })
        for (s in scopes) {
            val vs = list("/charter/${s.scope}/versions", com.coinepro.hq.core.net.Charter.serializer())
            assertEquals(s.versions.map { it.version }, vs.map { it.version })
            assertTrue(vs.all { it.bodySha256.length == 64 && it.bodyMd.length <= com.coinepro.hq.core.net.charterMax(it.scope) })
            for (v in vs) assertEquals(v, decode("/charter/${s.scope}/versions/${v.version}", com.coinepro.hq.core.net.Charter.serializer()))
        }
        val d = decode("/charter/TY/versions/2/diff?against=1", com.coinepro.hq.core.net.CharterDiff.serializer())
        assertTrue(d.diff.startsWith("--- TY@1") && d.diff.lines().any { it.startsWith("+") && !it.startsWith("+++") })
        assertTrue(scopes.flatMap { listOfNotNull(it.sealed, it.proposed) }.flatMap { it.redLines }.let { r -> r.any { it.check == "rule" && !it.patterns.isNullOrEmpty() } && r.any { it.check == "sample" && it.patterns == null } })
        val ks = page("/knowledge", com.coinepro.hq.core.net.KnowledgeEntry.serializer())
        assertEquals(setOf("holding", "company", "department", "employee"), ks.map { it.layer }.toSet())
        assertTrue(ks.map { it.status }.containsAll(listOf("approved", "in_review", "draft", "expired", "retired")))
        assertTrue(ks.all { it.sources.isNotEmpty() && it.validUntil.isNotEmpty() })
        // Support articles appear read-only with their KB- refs; the employee layer is read-only too.
        assertTrue(ks.any { it.kind == "support" && it.ref.startsWith("KB-") && it.readOnly } && ks.filter { it.layer == "employee" }.all { it.readOnly })
        assertTrue(ks.any { it.review?.verdict == "changes" && it.review!!.checks.containsValue(false) })
        for (k in ks) {
            assertEquals(k, decode("/knowledge/${k.ref}", com.coinepro.hq.core.net.KnowledgeEntry.serializer()))
            assertTrue(list("/knowledge/${k.ref}/versions", com.coinepro.hq.core.net.KnowledgeEntry.serializer()).first().ref == k.ref)
        }
    }

    @Test
    fun cardsScorecardOkrAndOutcomesDecode() {
        assertEquals(listOf("stability", "growth", "safety_cost"), list("/cards", com.coinepro.hq.core.net.KpiCard.serializer()).map { it.card })
        for (co in operating) {
            val cards = list("/cards?company=$co", com.coinepro.hq.core.net.KpiCard.serializer())
            val set = decode("/kpis/$co", com.coinepro.hq.core.net.KpiSet.serializer())
            assertEquals(listOf("stability", "growth", "safety_cost"), cards.map { it.card })
            assertTrue(cards.flatMap { it.kpis }.all { k -> set.kpis.any { it.key == k.key } })
            for (k in cards.flatMap { it.kpis }) {
                assertEquals(30, k.trend.size)
                // A KPI without a source has no value and no trend, never a zero.
                if (k.state == "no_source") assertTrue(k.value == null && k.sourceRef == null && k.trend.all { it == null })
            }
            for (def in set.kpis) list("/kpis/$co/${def.key}/values", com.coinepro.hq.core.net.KpiValue.serializer())
        }
        val rows = page("/scorecards", com.coinepro.hq.core.net.ScorecardRow.serializer())
        assertEquals(operating.toSet(), rows.map { it.company }.toSet())
        assertTrue(rows.all { r -> r.kpis.isNotEmpty() && r.kpis.all { it.card != null && it.direction != null } })
        val okr = list("/okr", com.coinepro.hq.core.net.Objective.serializer())
        assertTrue(okr.any { it.status == "active" } && okr.all { o -> o.keyResults.all { it.progress in 0.0..1.0 && it.objective == o.ref } && o.progress in 0.0..1.0 })
        for (o in okr) assertEquals(o, decode("/okr/${o.ref}", com.coinepro.hq.core.net.Objective.serializer()))
        val outcomes = page("/outcomes", com.coinepro.hq.core.net.OutcomeReview.serializer())
        assertTrue(outcomes.map { it.verdict }.containsAll(listOf("met", "partly", "missed", "pending")))
        assertTrue(page("/outcomes?due=true", com.coinepro.hq.core.net.OutcomeReview.serializer()).let { due -> due.isNotEmpty() && due.all { it.status == "due" } })
        // Prediction accuracy: met 1, partly ½, missed 0; pending does not count.
        assertEquals(0.75, com.coinepro.hq.core.net.accuracy(outcomes.filter { it.decision == "D-000004" })!!, 0.001)
    }

    @Test
    fun authorityRisksCalendarAndBatchDecode() {
        val rules = list("/authority", com.coinepro.hq.core.net.AuthorityRule.serializer())
        assertTrue(rules.any { it.locked } && rules.any { !it.locked && it.bounds != null && com.coinepro.hq.core.net.limitNumber(it.limit) != null } && rules.any { it.actionClass == "A4" && it.locked })
        assertEquals("items" to 20.0, com.coinepro.hq.core.net.limitNumber(rules.single { it.key == "batch.max_items" }.limit))
        assertEquals(listOf("TH", "FR"), com.coinepro.hq.core.net.limitDays(rules.single { it.key == "deploy.blackout_days" }.limit))
        val risks = page("/risks", com.coinepro.hq.core.net.Risk.serializer())
        assertTrue(risks.all { it.score == it.likelihood * it.impact } && risks.any { it.accepted != null } && risks.any { it.score >= 15 && it.mitigationMd == null && it.accepted == null })
        for (r in risks) assertEquals(r, decode("/risks/${r.ref}", com.coinepro.hq.core.net.Risk.serializer()))
        val m = decode("/risks/matrix", com.coinepro.hq.core.net.RiskMatrix.serializer())
        assertTrue(m.counts.size == 5 && m.counts.all { it.size == 5 })
        assertEquals(risks.count { it.status != "closed" }, m.counts.sumOf { it.sum() })
        assertTrue(risks.filter { it.status != "closed" }.all { m.at(it.likelihood, it.impact) > 0 })
        val cal = decode("/calendar", com.coinepro.hq.core.net.CalendarView.serializer())
        assertTrue(cal.events.all { it.version != null } && cal.events.any { it.company == null && it.kind == "holiday" })
        assertTrue(cal.conflicts.any { it.severity == "high" } && cal.conflicts.any { it.a == it.b } && cal.conflicts.all { c -> cal.events.any { it.ref == c.a } })
        val batch = list("/decisions/batchable", com.coinepro.hq.core.net.Batchable.serializer())
        val pending = page("/decisions?status=pending", com.coinepro.hq.core.net.Decision.serializer())
        assertTrue(batch.isNotEmpty() && batch.all { b -> b.kind in com.coinepro.hq.core.net.BATCH_KINDS && b.risk == "low" && pending.any { it.ref == b.ref && it.version == b.version } })
        assertTrue(batch.all { (it.quotaEstimate.usd?.toDouble() ?: 0.0) <= com.coinepro.hq.core.net.limitNumber(rules.single { r -> r.key == "batch.max_usd" }.limit)!!.second })
    }

    @Test
    fun governanceCardsDecode() {
        val all = page("/decisions?status=all", com.coinepro.hq.core.net.Decision.serializer())
        val gov = all.filter { it.kind in setOf("meeting_resolution", "charter_amendment", "okr", "knowledge_entry", "risk_acceptance", "authority_change") || it.expected != null }
        assertTrue(gov.map { it.kind }.containsAll(listOf("meeting_resolution", "charter_amendment", "okr", "risk_acceptance", "proposal")))
        for (d in gov) assertEquals(d, decode("/decisions/${d.ref}", com.coinepro.hq.core.net.Decision.serializer()))
        // ⟨1.5.1⟩ payloads: a resolution carries its votes and sourced claims, an amendment its diff and the version's hash.
        val res = gov.first { it.kind == "meeting_resolution" }.payload
        val votes = Api.json.decodeFromJsonElement(com.coinepro.hq.core.net.Votes.serializer(), res["votes"]!!)
        val claims = Api.json.decodeFromJsonElement(ListSerializer(com.coinepro.hq.core.net.Claim.serializer()), res["claims"]!!)
        assertTrue(votes.total > 0 && claims.all { it.status == "sourced" && it.source != null })
        val amend = gov.single { it.kind == "charter_amendment" }.payload
        val ty = decode("/charter/TY/versions/2", com.coinepro.hq.core.net.Charter.serializer())
        assertEquals(ty.bodySha256, (amend["body_sha256"] as kotlinx.serialization.json.JsonPrimitive).content)
        assertTrue((amend["diff_md"] as kotlinx.serialization.json.JsonPrimitive).content.startsWith("--- TY@1"))
        val okr = gov.single { it.kind == "okr" }.payload
        assertTrue(list("/okr", com.coinepro.hq.core.net.Objective.serializer()).any { it.ref == (okr["objective"] as kotlinx.serialization.json.JsonPrimitive).content })
        val acc = gov.single { it.kind == "risk_acceptance" }
        assertTrue(page("/risks", com.coinepro.hq.core.net.Risk.serializer()).any { it.accepted?.decision == acc.ref && it.ref == (acc.payload["risk"] as kotlinx.serialization.json.JsonPrimitive).content })
        // §20.6: a pending proposal carries its promise; a sealed one has its reviews at 30, 60 and 90 days.
        assertTrue(gov.any { it.status == "pending" && it.kind == "proposal" && it.expected != null })
        val outcomes = page("/outcomes", com.coinepro.hq.core.net.OutcomeReview.serializer())
        for (d in gov.filter { it.status == "approved" && it.expected != null }) {
            assertEquals(listOf(30, 60, 90).filter { it <= d.expected!!.byDays }, outcomes.filter { it.decision == d.ref }.map { it.day }.sorted())
        }
    }

    @Test
    fun batchRefusalDecodes() {
        // §20.12: `422 batch_not_eligible` names each card and why in `fields.items`; a field error still reads as JSON.
        val p = Api.json.decodeFromString(com.coinepro.hq.core.net.Problem.serializer(), """{"code":"batch_not_eligible","message_fa":"…","status":422,"fields":{"items":[{"ref":"D-000035","reason":"changed"}]}}""")
        assertEquals("D-000035", ((p.fields!!["items"] as kotlinx.serialization.json.JsonArray)[0] as kotlinx.serialization.json.JsonObject)["ref"].toString().trim('"'))
        val v = Api.json.decodeFromString(com.coinepro.hq.core.net.Problem.serializer(), """{"code":"validation_failed","message_fa":"…","status":422,"fields":{"title":"لازم است"}}""")
        assertEquals("validation_failed", v.code)
    }
    // ------------------------------------------------------------ ⟨1.5⟩ §21 --
    @Test
    fun memosAskAndReviewDecode() {
        // §21.1: a ready memo always has the case against; a standard one may carry the substitutes' opinions, with `agrees` by code.
        val memos = page("/advisor/memos", com.coinepro.hq.core.net.DecisionMemo.serializer())
        assertTrue(memos.isNotEmpty() && memos.all { it.state != "ready" || it.againstMd.isNotBlank() })
        assertTrue(memos.any { it.mode == "devil" } && memos.any { it.secondOpinion != null })
        for (m in memos) {
            m.secondOpinion?.let { assertEquals(it.recommendation == m.recommendation, it.agrees) }
            m.thirdOpinion?.let { assertEquals(it.recommendation == m.recommendation, it.agrees) }
        }
        val all = page("/decisions?status=all", com.coinepro.hq.core.net.Decision.serializer())
        // Each card lists exactly its memos.
        for (d in all) assertEquals(memos.filter { it.decision == d.ref }.map { it.ref }.toSet(), d.memos.map { it.ref }.toSet())
        val triggers = list("/advisor/triggers", com.coinepro.hq.core.net.AdvisorTrigger.serializer())
        assertTrue(triggers.any { it.state == "capped" && it.messageRef == null } && triggers.filter { it.state == "sent" }.all { it.messageRef != null })
        // Thread A carries the proactive notes and the devil mode in `meta`.
        val a = page("/threads/A/messages", com.coinepro.hq.core.net.Message.serializer())
        assertTrue(a.any { it.meta?.proactive != null } && a.any { it.meta?.mode == "devil" })
        assertTrue(triggers.filter { it.messageRef != null }.all { t -> a.any { it.ref == t.messageRef } })
        // §21.2: an answer cites its sources; nothing found is an answer too, with no citations and no cost.
        val asks = page("/ask", com.coinepro.hq.core.net.Ask.serializer())
        assertTrue(asks.all { it.q.length <= com.coinepro.hq.core.net.ASK_MAX && it.state == "done" })
        assertTrue(asks.any { it.found > 0 && it.citations.isNotEmpty() } && asks.any { it.found == 0 && it.citations.isEmpty() && it.usage.tokens == 0L })
        assertTrue(asks.flatMap { it.citations }.any { it.kind == "code" && it.lines?.size == 2 } && asks.any { it.notIndexed.isNotEmpty() })
        // §21.3: one review ready with its agenda; a done one has its minutes and duration.
        val reviews = list("/reviews/weekly", com.coinepro.hq.core.net.WeeklyReview.serializer())
        assertEquals("ready", reviews.first().state)
        assertTrue(reviews.first().agenda.isNotEmpty() && reviews.first().agenda.map { it.n } == (1..reviews.first().agenda.size).toList())
        assertTrue(reviews.any { it.state == "done" && it.minutesRef != null && it.durationS != null } && reviews.any { it.state == "skipped" })
    }

    @Test
    fun briefingsRanksAndHrDecode() {
        // §21.4: the morning briefing and one letter per operating company, each with its voice or why there is none.
        val bs = page("/briefings", com.coinepro.hq.core.net.Briefing.serializer())
        assertTrue(bs.any { it.kind == "morning" })
        assertEquals(operating.toSet(), bs.filter { it.kind == "ceo_letter" }.map { it.company }.toSet())
        assertTrue(bs.all { (it.audioState == "ready") == (it.audio != null) })
        val delivs = page("/deliverables", com.coinepro.hq.core.net.Deliverable.serializer()).map { it.ref }.toSet()
        assertTrue(bs.filter { it.kind == "ceo_letter" }.all { it.deliverableRef in delivs })
        // §21.5: 35/30/20/15, the owner's weight spread when there are no owner ratings; rank inside the company by score.
        for (p in listOf("week", "month")) {
            val rs = list("/rankings/departments?period=$p", com.coinepro.hq.core.net.DepartmentRank.serializer())
            assertTrue(rs.isNotEmpty() && rs.all { it.trend.isNotEmpty() })
            for (r in rs) {
                val x = r.parts
                val score = if (x.owner == null) (0.35 * x.people + 0.3 * x.delivery + 0.2 * x.efficiency) / 0.85 else 0.35 * x.people + 0.3 * x.delivery + 0.2 * x.efficiency + 0.15 * x.owner!!
                assertEquals(score, r.score, 0.06)
                assertEquals(rs.count { it.company == r.company && it.score > r.score } + 1, r.rankCompany)
            }
        }
        val rounds = list("/hr/rounds", com.coinepro.hq.core.net.HrRound.serializer())
        assertTrue(rounds.any { it.state == "proposed" && it.decisions.isNotEmpty() } && rounds.flatMap { it.employees }.any { "promote_candidate" in it.flags })
        val all = page("/decisions?status=all", com.coinepro.hq.core.net.Decision.serializer())
        // The round's evaluation card: payload v2, the employee flagged in its round.
        val ev = all.single { it.kind == "evaluation" }
        val p = Api.json.decodeFromJsonElement(com.coinepro.hq.core.net.EvaluationPayload.serializer(), kotlinx.serialization.json.JsonObject(ev.payload))
        val round = rounds.single { it.ref == p.round }
        assertTrue(ev.ref in round.decisions && round.employees.any { it.code == p.employee && "promote_candidate" in it.flags } && p.change?.model != null)
        // §21.8 reminders: a pending card without expiry is reminded at 24 h, 72 h and 7 days, as far as it has waited.
        assertEquals(listOf("age_24h", "age_72h", "age_7d"), ev.reminders.map { it.kind })
        assertTrue((ev.waitingH ?: 0) >= 168 && ev.digitalCeoPrediction == null)
    }

    @Test
    fun deployDiffAndPredictionsDecode() {
        val d = decode("/decisions/D-000017", com.coinepro.hq.core.net.Decision.serializer())
        val p = Api.json.decodeFromJsonElement(com.coinepro.hq.core.net.DeployPayload.serializer(), kotlinx.serialization.json.JsonObject(d.payload))
        val diff = requireNotNull(p.diff)
        assertEquals(diff.totalFiles, diff.files.size)
        assertTrue(diff.files.any { it.truncated } && diff.files.any { it.binary && it.patch == null } && diff.files.any { it.secretMasked })
        assertTrue(p.headSha == diff.headSha && p.secondReview != null && p.secondReview!!.findings.isNotEmpty())
        // The whole patch of a cut file is longer and not cut.
        val cut = diff.files.first { it.truncated }
        val whole = decode("/decisions/D-000017/diff?file=${cut.path}", com.coinepro.hq.core.net.DiffFile.serializer())
        assertTrue(!whole.truncated && whole.patch!!.length > cut.patch!!.length && whole.patch!!.startsWith(cut.patch!!))
        // §21.10: a prediction is shown only after the owner decided; its hash is the SHA-256 of the sealed fields.
        val all = page("/decisions?status=all", com.coinepro.hq.core.net.Decision.serializer())
        assertTrue(all.filter { it.status == "pending" }.all { it.digitalCeoPrediction == null } && all.any { it.digitalCeoPrediction?.correct != null })
        val preds = page("/digital-ceo/predictions", com.coinepro.hq.core.net.Prediction.serializer())
        assertTrue(preds.isNotEmpty() && preds.all { it.sealedHash.length == 64 && it.actual != null && it.correct == (it.verdict == it.actual) })
        for (x in preds) assertEquals(all.single { it.ref == x.decision }.digitalCeoPrediction?.verdict, x.verdict)
        val v = decode("/digital-ceo", com.coinepro.hq.core.net.DceoView.serializer())
        assertEquals(listOf("30d", "90d", "all"), v.stats.map { it.window })
        assertEquals(preds.size, v.stats.last().n)
        assertEquals(preds.count { it.correct == true }.toDouble() / preds.size, v.stats.last().accuracy!!, 0.0001)
        assertEquals(preds.size, v.hidden)
        val ps = list("/digital-ceo/principles", com.coinepro.hq.core.net.Principle.serializer())
        assertTrue(ps.map { it.status }.containsAll(listOf("active", "proposed", "retired")) && ps.all { it.sources.isNotEmpty() })
    }

    @Test
    fun treasuryNotesAndHealthDecode() {
        // §21.7: a day's waste is the sum of its categories; the range is one row per day.
        val range = list("/treasury/waste", com.coinepro.hq.core.net.WasteDay.serializer())
        assertEquals(30, range.size)
        for (w in range) assertEquals(w.items.sumOf { it.tokens }, w.wasteTokens)
        for (co in list("/companies", com.coinepro.hq.core.net.Company.serializer()).map { it.code }) {
            val xs = list("/treasury/waste?company=$co", com.coinepro.hq.core.net.WasteDay.serializer())
            assertTrue(xs.all { it.company == co })
        }
        for (by in listOf("company", "department", "employee")) for (p in listOf("week", "month")) {
            val rows = list("/treasury/roi?by=$by&period=$p", com.coinepro.hq.core.net.RoiRow.serializer())
            assertTrue(rows.isNotEmpty() && rows.all { it.by == by && it.period == p })
            // Revenue is never estimated: only a company with real revenue has an ROI.
            assertTrue(rows.all { (it.roi == null) == (it.revenueUsd == null) })
        }
        // §21.8: no delete — an archived note stays; a promoted one names where it went.
        val notes = page("/notes", com.coinepro.hq.core.net.OwnerNote.serializer())
        assertTrue(notes.map { it.status }.containsAll(listOf("open", "promoted", "archived")) && notes.filter { it.status == "promoted" }.all { it.promotedTo != null })
        assertTrue(notes.any { it.source == "voice" && it.fileId != null } && notes.all { it.tags.size <= 8 })
        // §21.9: a refuted claim always carries its evidence; the flags are rules.
        val claims = page("/claims", com.coinepro.hq.core.net.CheckedClaim.serializer())
        assertTrue(claims.filter { it.verdict == "refuted" }.all { it.evidence.isNotEmpty() })
        for (p in listOf("7d", "30d")) for (h in page("/runs/health?period=$p", com.coinepro.hq.core.net.AgentHealth.serializer())) {
            assertEquals(h.refutedShare != null && h.claimsChecked >= 5 && h.refutedShare!! >= 0.2, "truth" in h.flags)
            assertEquals(h.failedShare >= 0.25, "reliability" in h.flags)
            assertEquals(h.retryLoops >= 2, "loops" in h.flags)
        }
    }

    @Test
    fun settingsSubstitutesAndCreativesDecode() {
        // §21.12: every management block is there, so the settings card shows.
        val s = decode("/owner/settings", com.coinepro.hq.core.net.OwnerSettings.serializer())
        val base = requireNotNull(s.management())
        val changed = base.copy(reminders = base.reminders.copy(enabled = !base.reminders.enabled)).changedFrom(base)
        assertEquals(setOf("reminders"), changed.keys)
        assertTrue(changed.getValue("reminders").toString().contains("\"ages_h\""))
        // §21.13: players are data; a player without a CLI has web seats only; the value ratio is null when it costs nothing.
        val subs = list("/substitutes", com.coinepro.hq.core.net.Substitute.serializer())
        assertTrue(subs.size >= 2 && subs.filter { it.runner == null }.all { x -> x.seats.all { it.via == "web" } })
        assertTrue(subs.all { x -> x.seats.all { it.model in x.models.map { mm -> mm.id } && it.usedToday <= maxOf(it.perDay, it.usedToday) } })
        assertTrue(subs.any { it.month.valueRatio == null && it.month.priceUsd.toDouble() == 0.0 } && subs.any { it.status == "limited" && it.limitedUntil != null })
        val conns = list("/connections", com.coinepro.hq.core.net.Connection.serializer())
        assertTrue(subs.all { x -> conns.any { it.key == x.connection && it.kind == "subscription" } })
        val cs = page("/creatives", com.coinepro.hq.core.net.Creative.serializer())
        assertTrue(cs.map { it.state }.containsAll(listOf("generating", "review", "accepted", "failed", "rejected")))
        assertTrue(cs.all { it.aspect == com.coinepro.hq.core.net.PLACEMENT_ASPECT[it.placement] && it.aiGenerated && it.promptMd.contains("No text") })
        assertTrue(cs.filter { it.kind == "video" }.all { it.player == "gemini" && (it.durationS ?: 0) in 1..10 })
        assertTrue(cs.filter { it.state == "failed" }.all { !it.reviewMd.isNullOrBlank() })
    }
    // ------------------------------------------------------------ ⟨1.6⟩ §22 --
    @Test
    fun departmentsCarryTheirMandateAndTeam() {
        // §22.1: every operating company has MEDIA, defined by its mandate, identity and a starting team; the holding has LEGAL with HQ-LGL.
        for (co in listOf("TY", "FX", "PC")) {
            val ds = list("/companies/$co/departments", com.coinepro.hq.core.net.Department.serializer())
            val media = ds.single { it.code == "MEDIA" }
            val m = requireNotNull(media.mandate)
            assertTrue(m.fromFa.isNotBlank() && m.toFa.isNotBlank() && m.outputsFa.isNotEmpty() && m.modelCeiling in com.coinepro.hq.core.net.MODEL_CEILINGS)
            assertTrue("media.item" in m.toolCeiling && media.team.any { it.first } && !media.identityMd.isNullOrBlank() && media.version >= 1)
        }
        val legal = list("/companies/HQ/departments", com.coinepro.hq.core.net.Department.serializer()).single { it.code == "LEGAL" }
        assertEquals("HQ-LGL", legal.manager?.code)
        assertTrue("email.draft" in requireNotNull(legal.mandate).toolCeiling)
    }

    @Test
    fun rolesWrittenOnDemandDecode() {
        // §22.5: a draft past writing carries at least three eval cases and the overseer's five checks; an active one its approval.
        val ds = page("/roles/drafts", com.coinepro.hq.core.net.RoleDraft.serializer())
        assertTrue(ds.map { it.state }.containsAll(listOf("active", "eval", "in_review", "rejected")))
        assertTrue(ds.filter { it.state != "drafting" }.all { it.eval.cases.size >= 3 && it.charterMd.isNotBlank() && it.originality != null })
        assertTrue(ds.mapNotNull { it.review }.all { r -> r.checks.keys == setOf("injection", "secrets", "conflicts", "policy", "ceiling") && r.sha256.length == 64 })
        val active = ds.single { it.state == "active" }
        assertTrue(active.approver != null && active.decisionRef != null && active.evalRun?.passed == true)
        assertTrue(ds.filter { it.state == "rejected" }.all { !it.stateNoteFa.isNullOrBlank() && it.review?.verdict == "reject" })
        assertTrue(ds.single { it.state == "eval" }.evalRun!!.let { it.live && it.score == null && it.passed == null })
        // GET /roles lists the active draft beside the file charters; it is hireable only in its own company and department.
        val roles = list("/roles", RoleInfo.serializer())
        val draft = roles.single { it.source == "draft" }
        assertEquals(active.ref to active.company, draft.draft to draft.company)
        assertTrue(draft in hireableRoles(roles, "company", active.department, active.company))
        assertTrue(draft !in hireableRoles(roles, "company", active.department, "TY"))
        // §22.7: the role's story names its draft.
        val story = list("/stories", com.coinepro.hq.core.net.StoryRing.serializer()).flatMap { it.items }.single { it.kind == "role" }
        assertEquals(active.ref, story.links.roleDraft)
    }

    @Test
    fun studioDecodes() {
        // §22.2: a sealed series has its next runs and a digest; every series carries all seven checks and only placements the platform takes.
        val series = page("/media/series", com.coinepro.hq.core.net.Series.serializer())
        assertTrue(series.map { it.status }.containsAll(listOf("draft", "proposed", "sealed", "paused")))
        assertTrue(series.all { it.digest.length == 64 && it.checks == com.coinepro.hq.core.net.MEDIA_CHECKS && it.targets.isNotEmpty() })
        assertTrue(series.filter { it.status == "sealed" }.all { it.nextAt.isNotEmpty() && it.today != null && it.sealedAt != null })
        assertTrue(series.all { s -> s.targets.all { com.coinepro.hq.core.net.placementFits(s.kind, s.format.aspect, it.placement) == null && it.account == com.coinepro.hq.core.net.accountKey(it.channel, s.company) } })
        // Items: every state of the board; a waiting item has its card; a design never goes out; a held one failed a check; all AI-made.
        val items = page("/media/items", com.coinepro.hq.core.net.MediaItem.serializer())
        assertTrue(items.map { it.state }.containsAll(listOf("scripting", "directing", "composing", "voicing", "rendering", "checking", "review", "scheduled", "published", "waiting_owner", "held", "failed")))
        assertTrue(items.all { it.aiGenerated } && items.filter { it.state == "waiting_owner" }.all { it.decisionRef != null })
        assertTrue(items.filter { it.kind == "design" }.all { it.publish.isEmpty() && it.series == null })
        assertTrue(items.filter { it.state == "held" }.all { x -> x.checks.any { it.result == "fail" } && !x.stateNoteFa.isNullOrBlank() })
        assertTrue(items.filter { it.state == "published" }.all { x -> x.publish.any { it.externalId != null } })
        assertTrue(items.mapNotNull { it.script }.filter { it.sources.isNotEmpty() }.all { s -> s.sources.all { it.note.isNotBlank() } })
        val reel = items.single { it.ref == "MI-0014" }
        assertTrue(reel.render!!.mime == "video/mp4" && reel.render!!.width == 360 && reel.voice != null && reel.direction!!.shots.size >= 3 && reel.qc?.verdict == "pass")
        // §22.3: one active voice; a non-commercial one says so; measured voices have their clips; the owner's reference is ready.
        val voices = list("/media/voices", com.coinepro.hq.core.net.Voice.serializer())
        assertEquals(1, voices.count { it.status == "active" })
        assertTrue(voices.any { !it.licenceCommercial } && voices.filter { it.measuredAt != null }.all { it.samples.size == 3 && it.rtf != null })
        assertTrue(voices.any { it.speaker == "owner" && it.clones } && voices.filter { it.samples.isEmpty() }.all { it.rtf == null })
        assertEquals("ready", decode("/media/voices/reference", com.coinepro.hq.core.net.VoiceReference.serializer()).state)
        // ⟨1.6.1⟩ the platforms' own limits: Instagram counts posts; the Bot API has no daily cap.
        val limits = list("/media/limits", com.coinepro.hq.core.net.PlatformLimit.serializer())
        assertTrue(limits.filter { it.channel == "instagram" }.all { it.per24h == 50 } && limits.filter { it.channel == "telegram" }.all { it.per24h == null })
    }

    @Test
    fun legalCounselDecodes() {
        // §22.4: the cases; one has its whole thread, an email waiting for the seal bound to its digest, and deadlines.
        val cases = page("/legal/cases", com.coinepro.hq.core.net.LegalCase.serializer())
        assertTrue(cases.size >= 3 && cases.all { it.timeline.isNotEmpty() && it.emails.isEmpty() })
        val c = decode("/legal/cases/LC-0001", com.coinepro.hq.core.net.LegalCase.serializer())
        assertTrue(c.deadlines.isNotEmpty() && c.emails.map { it.direction }.toSet() == setOf("out", "in"))
        val waiting = c.emails.single { it.state == "waiting_seal" }
        assertTrue(waiting.digest.length == 64 && waiting.decisionRef != null && waiting.messageId == null && waiting.attachments.isNotEmpty())
        // The card is sealed on the message digest, not on its ref (§22.6).
        val card = decode("/decisions/${waiting.decisionRef}", com.coinepro.hq.core.net.Decision.serializer())
        assertEquals("email_send", card.kind)
        assertEquals(waiting.digest, com.coinepro.hq.core.net.sealTarget(card))
        assertEquals(waiting.draft(), card.payloadAs(com.coinepro.hq.core.net.EmailDraft.serializer()))
        // Thread L: the counsel's conversation with the owner, its messages linking the case.
        val l = page("/threads/L/messages", Message.serializer())
        assertTrue(l.isNotEmpty() && l.any { it.links["case"]?.toString()?.contains("LC-0001") == true })
    }

    @Test
    fun section22CardsDecode() {
        val all = page("/decisions?status=all", com.coinepro.hq.core.net.Decision.serializer())
        assertTrue(all.map { it.kind }.containsAll(com.coinepro.hq.core.net.MEDIA_KINDS))
        // `media_publish`: a channel story goes by the owner's hand; a placement without a key is blocked this time.
        val pub = decode("/decisions/D-000087", com.coinepro.hq.core.net.Decision.serializer()).payloadAs(com.coinepro.hq.core.net.PublishPayload.serializer())!!
        assertTrue(pub.placements.any { it.via == "manual" && it.placement == "telegram_story" } && pub.placements.any { it.blocked == "account_not_configured" })
        assertTrue(pub.render?.mime == "video/mp4" && pub.checks.size == 7)
        // `media_series`: bound to the digest of the series it seals.
        val sr = decode("/decisions/D-000081", com.coinepro.hq.core.net.Decision.serializer()).payloadAs(com.coinepro.hq.core.net.SeriesPayload.serializer())!!
        assertEquals(page("/media/series", com.coinepro.hq.core.net.Series.serializer()).single { it.ref == sr.series }.digest, sr.digest)
        // `role_new` ⟨1.6.1⟩
        val rn = decode("/decisions/D-000084", com.coinepro.hq.core.net.Decision.serializer()).payloadAs(com.coinepro.hq.core.net.RoleNewPayload.serializer())!!
        assertTrue(rn.draft == "RD-0001" && rn.review == "pass" && (rn.evalScore ?: 0.0) >= 80 && rn.limits!!.tokensPerRun > 0 && rn.sha256!!.length == 64)
    }

    // ------------------------------------------------------------ ⟨1.7⟩ §23 --
    @Test
    fun archiveSchemaDecodes() {
        val s = com.coinepro.hq.core.net.ArchiveSchema(body("/archive/schema").jsonObject)
        // §23.4: the seeded levels 0, 10, 20, 30; «سری» needs a passkey to view; the agents' ceiling is one level below it.
        assertEquals(listOf(0, 10, 20, 30), s.levels.map { it.rank })
        val secret = s.levels.single { it.key == "secret" }
        assertTrue(secret.titleFa == "سری" && secret.stepUpToView && !secret.agentsMax)
        assertEquals("confidential", s.levels.single { it.agentsMax }.key)
        // The open layer: classes over the closed field types; a money field names its currency; a ref field its kinds.
        val types = s.fieldTypes.map { it.key }
        assertTrue(s.classes.size >= 10 && s.classes.all { c -> c.fields.all { it.type in types } && c.allowedMime.all { it in s.vocab.mimes } })
        assertTrue(s.classes.flatMap { it.fields }.filter { it.type == "money" }.all { it.currency in s.vocab.currencies })
        assertTrue(s.classes.flatMap { it.fields }.filter { it.type == "ref" }.all { f -> f.refKinds.isNotEmpty() && f.refKinds.all { it in s.vocab.refKinds } })
        assertTrue(s.classes.all { it.retention == null || s.retention.any { r -> r.ref == it.retention } })
        // Clearance is one row per grant on the wire and grouped per subject for the editor.
        val grouped = s.rows("clearance")
        assertTrue(grouped.isNotEmpty() && grouped.size <= (body("/archive/schema").jsonObject["clearance"] as kotlinx.serialization.json.JsonArray).size)
        // Automations speak only the closed vocabulary; reminders point at a date field of their class.
        assertTrue(s.automations.all { a -> a.on in s.vocab.events && a.steps.all { (it["action"] as kotlinx.serialization.json.JsonPrimitive).content in s.vocab.actions } })
        assertTrue(s.reminders.all { r -> s.classes.single { it.key == r.cls }.fields.single { it.key == r.field }.type in setOf("date", "date_range") })
        assertTrue(s.retention.any { it.permanent } && s.retention.any { it.years > 0 && it.then == "dispose_card" })
        assertEquals(com.coinepro.hq.core.net.SCHEMA_PARTS, s.parts)
        // The sources: one switch each, off is off.
        val src = list("/archive/sources", com.coinepro.hq.core.net.SourceSwitch.serializer())
        assertTrue(src.any { !it.enabled && !it.noteFa.isNullOrBlank() } && src.all { x -> s.classes.any { it.key == x.cls } })
    }

    @Test
    fun archiveRecordsDecode() {
        val s = com.coinepro.hq.core.net.ArchiveSchema(body("/archive/schema").jsonObject)
        val rs = page("/archive/records", com.coinepro.hq.core.net.ArchiveRecord.serializer())
        assertTrue(rs.map { it.state }.containsAll(listOf("draft", "filed", "sealed")))
        // Every version's manifest is a SHA-256; the current one exists; a sealed record's current version is sealed.
        assertTrue(rs.all { r -> r.current != null && r.versions.all { it.manifestSha256.length == 64 && it.files.all { f -> f.sha256.length == 64 } } })
        assertTrue(rs.filter { it.state == "sealed" }.all { it.current!!.sealed && it.sealedAt != null })
        // A draft carries its suggestion, never filed by itself.
        val drafts = rs.filter { it.state == "draft" }
        assertTrue(drafts.isNotEmpty() && drafts.all { it.suggestion != null && it.filedAt == null })
        // Levels and classes are keys of the schema; two versions of one record; a held record names its hold.
        assertTrue(rs.all { r -> s.levels.any { it.key == r.level } && (r.cls == null || s.classes.any { it.key == r.cls }) })
        assertTrue(rs.any { it.versions.size >= 2 && it.versions.count { v -> v.state == "current" } == 1 })
        assertTrue(rs.single { it.ref == "AR-000180" }.let { it.level == "secret" && it.state == "sealed" })
        val holds = page("/archive/holds", com.coinepro.hq.core.net.LegalHold.serializer())
        assertTrue(holds.all { h -> h.state == "active" && !h.scope.empty && h.recordRefs.size == h.records && h.recordRefs.all { ref -> rs.single { it.ref == ref }.holds.contains(h.ref) } })
        assertTrue(holds.any { it.case != null } && holds.any { it.scope.records.isNotEmpty() })
        // Parties carry their kind; a record's party is in the registry.
        val parties = page("/archive/parties", com.coinepro.hq.core.net.Party.serializer())
        assertTrue(rs.flatMap { it.parties }.all { p -> parties.any { it.ref == p.party } } && parties.all { p -> s.partyKinds.any { it.key == p.kind } })
        // Search: snippets from the files' text; the same records as the list's `q`.
        val hits = page("/archive/search?q=هتزنر", com.coinepro.hq.core.net.ArchiveHit.serializer())
        assertTrue(hits.isNotEmpty() && hits.all { it.snippetFa.isNotBlank() && it.score > 0 })
        assertEquals(hits.map { it.ref }, page("/archive/records?q=هتزنر", com.coinepro.hq.core.net.ArchiveRecord.serializer()).map { it.ref })
    }

    @Test
    fun archiveDueListsAndCardsDecode() {
        val reminders = page("/archive/reminders", com.coinepro.hq.core.net.DueReminder.serializer())
        assertTrue(reminders.isNotEmpty() && reminders.all { it.id == "${it.record}:${it.field}" && it.state == "sent" && it.daysLeft <= it.leadDays })
        val due = page("/archive/retention/due", com.coinepro.hq.core.net.RetentionDue.serializer())
        assertTrue(due.size >= 2 && due.any { it.holds.isNotEmpty() } && due.all { it.decisionRef == "D-000093" && it.then == "dispose_card" })
        val fx = decode("/archive/fixity", com.coinepro.hq.core.net.Fixity.serializer())
        assertTrue(fx.checked > 0 && fx.failed.isEmpty())
        // §23.11: both kinds are listed; the schema card carries the exact body and its base version, the disposal card its records.
        val all = page("/decisions?status=all", com.coinepro.hq.core.net.Decision.serializer())
        assertTrue(all.map { it.kind }.containsAll(com.coinepro.hq.core.net.ARCHIVE_KINDS))
        val sc = decode("/decisions/D-000092", com.coinepro.hq.core.net.Decision.serializer()).payloadAs(com.coinepro.hq.core.net.SchemaCardPayload.serializer())!!
        assertTrue(sc.part in com.coinepro.hq.core.net.SCHEMA_PARTS && sc.key.isNotBlank() && sc.body.isNotEmpty())
        val dc = decode("/decisions/D-000093", com.coinepro.hq.core.net.Decision.serializer()).payloadAs(com.coinepro.hq.core.net.DisposalCardPayload.serializer())!!
        assertEquals(due.map { it.ref }.toSet(), dc.records.map { it.ref }.toSet())
    }
}
