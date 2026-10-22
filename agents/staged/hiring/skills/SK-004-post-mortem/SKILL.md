---
ref: SK-004
name_fa: پس‌کاوی حادثه (post-mortem)
summary_fa: بعد از هر حادثه یک گزارش بی‌سرزنش با خط زمانی منبع‌دار، اثر، علت ریشه‌ای قابل اصلاح و اقدام‌هایی که صاحب، موعد و راه سنجش دارند؛ هر ری‌استارت، rollback یا تغییر فقط پیشنهاد است و هیچ‌چیز ناشناخته‌ای حدس زده نمیشود.
roles: [sre, db_reliability, appsec_engineer, cto, hub_platform_sre]
companies: all
version: 1
eval: EV-007
---
# Blameless post-mortem
A post-mortem explains **how the system allowed a failure** and what will stop it happening again. It is written after every incident
that affected users, data or money, or that raised an urgent notification, by the due time of its work item. It never names a person or
an agent as the cause; it names the missing guardrail, check, alert, test, rule or runbook.

## Method
1. **Gather before you write.** Collect only what your tools can read: the check results around the window (site checks, hub health,
   backup status, as your role has them), the incident's work items and messages, decision and deploy refs, Code Workshop session
   events, audit refs in deliverables. Each fact you will cite gets its ref now.
2. **Timeline.** One row per event, in UTC and the owner's time, each with its source. Mark at least: introduced, first failing check,
   detected, acknowledged, mitigated, resolved. A time you cannot source is marked «تخمینی» with why, or left blank as unknown.
3. **Impact.** Who (which product, channel or service; counts from the system, aggregated), how long (from the first failing check, or
   from when it was introduced if earlier, to recovery), data (lost, delayed, exposed, or none, with how you know), money (incomplete
   revenue days, tokens spent on the incident). Each figure sourced or «نمیدانم».
4. **Detection.** How it was found (a rule-based check, a user through support, an agent, the owner), how long after it began, and why
   not earlier: no check, wrong threshold, a flapping check that was ignored, an alert that reached nobody.
5. **Root cause: 5 whys.** Start from the failure; each answer needs evidence. Stop at the first cause that an action the company
   controls can fix (a check, a test, a limit, a config validated in review, a runbook step, a rule). Never stop at "human error" or "the
   agent made a mistake": ask why the system let it through. The cause that appeared first in time, or the most recent change, is a
   hypothesis until the timeline and the evidence confirm it. If the chain breaks for lack of evidence, stop there, write «نمیدانم» and
   what would answer it (which log, which metric, which retention).
6. **Contributing factors.** What made it worse or longer: no runbook, unclear owner, noisy alerts, a single point of failure, logs
   kept too briefly, a deploy outside the change calendar.
7. **What went well.** Checks, runbooks, decisions and handoffs that shortened it. Keep them.
8. **While it was open.** From the handoff record: what was tried (and its result), what was not tried and why, what was suspected and
   whether it was later confirmed or refuted. The next responder starts here.
9. **Actions.** Each one specific and testable, with: type (prevent / detect / mitigate / process), **owner role**, **due date**, **how
   to verify it worked**, and its `propose` or `W-…` ref. An action without an owner role, a due date or a verification is not an action:
   rewrite it or drop it. "Be more careful" is never an action.
10. **Repeats.** If an earlier post-mortem covers the same failure, link it and say which of its actions were not done.

## What the agent never does
- Restarts, rollbacks, failovers, deploys, scaling, config changes and restores are A3. In a post-mortem they appear only as what was
  done under the owner's decision (with its `D-…` ref) or as a new `propose` with what will happen, the cost, the risk and how to undo it.
  Writing "I restarted" or "we will roll back" as your own act is wrong; something is done only when its tool said `ok`.
- Deleting data or backups and changing keys, users, login or firewall settings are not actions for any agent and are not proposed.
- No legal conclusions, notifications to authorities or messages to users. If user data may have been exposed, state the facts, tell
  your manager, and leave every next step to the owner.

## Report (Persian headings; the owner reads it)
«خلاصه» (what happened, who was affected, how long, how it ended, severity) · «خط زمانی» (time UTC | owner time | event | source) ·
«اثر» · «کشف» · «علت ریشه‌ای» (the whys, numbered, each with evidence) · «عوامل همراه» · «چه خوب پیش رفت» ·
«در زمان باز بودن حادثه» (tried / not tried / suspected) · «اقدام‌ها» (# | action | type | owner role | due date | verification | ref) ·
«نامعلوم‌ها» (what is still unknown and what would answer it).
Facts, inferences and recommendations stay apart. No customer data, secrets or private message bodies: aggregated counts only.
