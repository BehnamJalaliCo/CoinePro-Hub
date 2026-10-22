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
}
