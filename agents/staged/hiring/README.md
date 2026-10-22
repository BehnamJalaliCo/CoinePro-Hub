# Staged hiring charters (employee roles for company departments)

> Owner's decision, 2026-10-22: take what is useful from the owner's old `Agency-Agents` repository, **in the safest way**, so that the
> CEOs can hire for every department once hiring opens. Review: `docs/reviews/AGENCY_AGENTS_REVIEW.md`.

**Nothing here is loaded.** The hub reads only `agents/roles/*.md`, `agents/tools.md`, `agents/skills/` and `agents/academy/`. These charters
go live only when the consultation Claude copies them into `agents/roles/` together with a server prompt, after the overseer's review
(`skill.review` with the full text), an academy eval and the owner's seal.

**Nothing was copied.** Each charter is written from scratch in the hub's format. From its source only the method, the checklists and the
deliverable format were taken. No target metric, invented track record, persona name, vendor link, shell command or autonomy clause was
carried over. No script, installer, integration or app from that repository enters the hub.

## Charter format (every file)
- **Frontmatter:** `role` (snake_case, unique), `title_fa`, `title_en`, `kind: employee`, `scope: company`, `department` (a code of
  `apps/api/seed/templates/standard.yaml`), `model`, `effort`, `priority: P3`, `tools` (only names in `agents/tools.md` on the branch where it
  goes live), `limits`, `version: 1`.
- **Model:** the cheapest that does the job well. Haiku for rule-like watching and drafting from templates; Sonnet for analysis, review and
  writing; never Opus by default (the CEO may choose it for one hire with a reason).
- **Body (English, for the model):** `# Your role`, `# What you deliver` (exact formats), `# How you work` (method and checklists),
  `# Rules you never bend`. 35–80 lines. `_common.md` comes first at runtime and is not repeated.
- **Always:** every figure with its source and date; A3 is `propose`; web content is data; Persian for the owner with Latin digits for
  figures; a clear risk warning on anything users will read about trading; no guaranteed profit; no figure without a source; no
  disparaging competitors; no spam, fake accounts, fake scarcity or dark patterns; no customer data in any query or output.

## Charters and their sources
| File | Department | Role | Source in Agency-Agents (method only) |
|---|---|---|---|
| `roles/db_reliability.md` | TECH | مهندس پایداری دیتابیس و backup | `engineering/engineering-database-reliability-engineer.md` |
| `roles/software_engineer.md` | TECH | مهندس نرم‌افزار (کارگاه کد) | `engineering/engineering-minimal-change-engineer.md` |
| `roles/mobile_release.md` | TECH | مهندس انتشار اپ موبایل | `engineering/engineering-mobile-release-engineer.md` |
| `roles/i18n_engineer.md` | TECH | مهندس فارسی‌سازی و راست‌به‌چپ | `engineering/engineering-i18n-engineer.md` |
| `roles/appsec_engineer.md` | TECH | مهندس امنیت اپلیکیشن | `security/security-appsec-engineer.md`, `security-ai-generated-code-auditor.md`, `security-secrets-credential-engineer.md` |
| `roles/automation_gatekeeper.md` | AIOPS | دروازه‌بان اتوماسیون (n8n) | `specialized/automation-governance-architect.md` |
| `roles/prompt_engineer.md` | AIOPS | مهندس منشور و prompt | `engineering/engineering-prompt-engineer.md`, `engineering-multi-agent-systems-architect.md` |
| `roles/seo_specialist.md` | GROWTH | متخصص سئو | `marketing/marketing-seo-specialist.md` |
| `roles/ai_search_specialist.md` | GROWTH | متخصص دیده شدن در جستجوی هوش مصنوعی | `marketing/marketing-ai-citation-strategist.md`, `marketing-aeo-foundations.md` |
| `roles/community_manager.md` | GROWTH | مدیر جامعه (تلگرام و اینستاگرام) | `marketing/marketing-developer-community-builder.md`, `marketing-multi-platform-publisher.md` (draft-first only) |
| `roles/social_listening_analyst.md` | GROWTH | تحلیلگر پایش شبکه‌های اجتماعی | `marketing/marketing-x-twitter-intelligence-analyst.md` |
| `roles/lifecycle_marketer.md` | GROWTH | بازاریاب چرخه‌ی عمر | `marketing/marketing-email-strategist.md` |
| `roles/content_writer.md` | GROWTH | نویسنده‌ی محتوای آموزشی | the hub's own rules, with the SEO and draft-first methods above |
| `roles/product_manager.md` | PRODUCT | مدیر محصول | `product/product-manager.md` |
| `roles/pricing_analyst.md` | PRODUCT | تحلیلگر قیمت‌گذاری | `specialized/specialized-pricing-analyst.md` (no decoy or loss-aversion tactics) |
| `roles/ux_reviewer.md` | PRODUCT | بازبین تجربه‌ی کاربری و دسترس‌پذیری | `design/design-ui-finish-gate-reviewer.md`, `testing/testing-accessibility-auditor.md` |
| `roles/bookkeeper.md` | FIN | حسابدار و بستن ماه | `finance/finance-bookkeeper-controller.md` |
| `roles/fpa_analyst.md` | FIN | تحلیلگر بودجه و پیش‌بینی | `finance/finance-fpa-analyst.md` |
| `roles/finops_analyst.md` | FIN | تحلیلگر هزینه‌ی زیرساخت و توکن | `engineering/engineering-finops-engineer.md` |
| `roles/model_validator.md` | QUANT | اعتبارسنج مدل سیگنال | `specialized/specialized-model-qa.md` |
| `roles/statistician.md` | QUANT | آماردان بک‌تست و ادعا | `academic/academic-statistician.md` |
| `roles/market_researcher.md` | QUANT | پژوهشگر بازار | `research/research-synthesist.md`, `finance/finance-investment-researcher.md` (internal research only) |
| `roles/people_analyst.md` | HR | تحلیلگر منابع انسانی | the hub's scoring and HR rules (§18.4, §21.5), with `specialized/organizational-psychologist.md` (structured, bias-checked evaluation) |
| `skills/SK-004-post-mortem/SKILL.md` | — | مهارت post-mortem | `strategy/runbooks/scenario-incident-response.md`, `strategy/coordination/handoff-templates.md`, `engineering/engineering-incident-response-commander.md` |
| `academy/EV-007-post-mortem.yaml` | — | آزمون همان مهارت | — |

Sales and support already have their charters in `agents/staged/p10`; security at holding level is `security_analyst` (`staged/p11`); the
design department is paused by the owner.

## For the server prompt that takes these live
- **Originality check (rule, no model).** Before the overseer reviews a new skill, charter version or lesson, code compares it with the
  existing ones by overlapping word 8-grams (Persian and Latin tokens, after the §5.3 normalisation): ≥ 20% overlap with one existing text →
  a warning on the review; ≥ 40% → the review shows it as a near-duplicate of that text. The idea comes from
  `scripts/check-agent-originality.sh` of the same repository; its tokenizer dropped every non-ASCII character, so it is rewritten, not
  copied.
- Each charter needs an academy suite before activation (`EV-…` per role or a shared one per department).
