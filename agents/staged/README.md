# Staged agent changes (prompts 10–13, and the hiring charters)

Charter and tool-catalog changes that go live **with** prompts 10, 11 and 12. Nothing here is loaded: the hub reads only
`agents/roles/*.md`, `agents/tools.md` and `agents/protocols/`.

**Why staged.** The charter loader grants every tool a charter names that `tools.md` lists. If these changes sat in `agents/` before the
server built the tools, agents would be offered tools that answer "unknown tool", charters would describe duties that do not exist yet, and
the new roles (support, revenue) would be hireable — a CEO hiring inside its envelope could hire a support agent before there is a support
desk.

**How they go live.** When the consultation Claude sends prompt N, it copies `staged/pN/roles/*.md` into `agents/roles/` and
`staged/pN/tools.md` over `agents/tools.md`, in the same commit as the prompt. Each stage is cumulative: `p11` contains `p10`'s changes,
and `p12` contains both. The new protocols of each prompt are already in `agents/protocols/oversight.yaml`, seeded `paused`; each prompt
switches its own on.

| Stage | Roles changed | New roles | Tools |
|---|---|---|---|
| `p10` | ceo, manager, overseer, advisor | support_lead, support_agent, referral_rescue, revenue_analyst | revenue and support (contract §19.10) |
| `p11` | + ai_safety, aiops_head, cto, inspector, security_analyst, sre | secretary | governance (§20.11); `knowledge.search` kind `knowledge`; `propose.expected` |
| `p12` | advisor v6, assistant v2, ceo, cto v4, fact_checker, inspector, overseer | librarian | `memo.write`, `ask.answer`, `claim.verdict`, `substitute.call` (§21.13); `knowledge.search` kinds `docs`, `code`, `notes` |
| `p13` | manager v6, ceo v7 (roles written on demand) | media_director (MEDIA head), scriptwriter, video_director, motion_designer, voice_producer, visual_designer, ui_designer, legal_counsel (holding, LEGAL) | media studio and legal (§22): `media.item`, `media.render`, `media.voice`, `media.review`, `series.propose`, `case.open`, `case.note`, `email.draft`, `mail.read`, `role.draft`, `role.decide` |
| `p14` | legal_counsel v2 (archive search, filing, links, legal holds) | archivist (system, holding) | the archive (§23.11): `archive.search`, `archive.read`, `archive.file`, `archive.link`, `archive.hold`; `knowledge.search` kind `records` |

`hiring/` holds 23 employee charters for the standard departments, written from the review of the owner's Agency-Agents repository
(`docs/reviews/AGENCY_AGENTS_REVIEW.md`); they go live with a server prompt once reviewed, evaluated and sealed.

Prompt 12 also adds `calendar: jalali` to `PR-082` in `oversight.yaml` when it is sent (the prompt 8 loader does not know the key).
