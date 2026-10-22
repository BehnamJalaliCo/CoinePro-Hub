// Dumps the web's development fixtures (apps/web/src/lib/api/mock.ts) into the Android debug assets, so the
// demo on both clients shows the same holding. Instants become offsets from "now" ("@-42m"), which the
// Android demo resolves at load time, so relative times ("5 minutes ago") stay true.
// Usage: node --experimental-strip-types scripts/dump_demo_fixtures.mjs (from apps/android)
import { writeFileSync } from 'node:fs';
import { register } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

// The fixtures import their siblings without an extension (as the web's bundler allows); Node needs one.
register('data:text/javascript,' + encodeURIComponent(
  'export async function resolve(s, c, next) { try { return await next(s, c); } catch (e) { if (s.startsWith(".") && !s.endsWith(".ts")) return next(s + ".ts", c); throw e; } }',
));

// The mock's clock is pinned to the instant the screenshot tests fix (ScreensTest, HqClock), so fixtures aligned to a
// day (the planner) dump to the same offsets whatever time of day the script runs.
const FIXED = Date.parse('2026-10-17T08:30:00Z');
// ⟨1.5⟩ The clock moves only at the end, to collect what a live meeting says next (below); every fixture is read at FIXED.
let clock = FIXED;
const RealDate = Date;
globalThis.Date = class extends RealDate {
  constructor(...a) { super(...(a.length ? a : [clock])); }
  static now() { return clock; }
};

const here = dirname(fileURLToPath(import.meta.url));
const { handle } = await import(join(here, '../../web/src/lib/api/mock.ts'));
const t0 = Date.now();
const getJson = async (p) => (await handle(new Request(`http://demo/api/v1${p}`))).json();
const employeeCodes = ((await getJson('/employees')).items ?? []).map((e) => e.code);
const academyRoles = (await getJson('/academy/curricula')).map((c) => c.role);
// ⟨1.5⟩ Companies, conversations and rescue cases are data: the lists below follow what the mock holds.
const listOf = (x) => (Array.isArray(x) ? x : x.items ?? []);
const operating = listOf(await getJson('/companies')).filter((c) => c.kind !== 'holding').map((c) => c.code);
const conversationRefs = listOf(await getJson('/support/conversations')).map((c) => c.ref);
const rescueRefs = listOf(await getJson('/growth/rescue')).map((r) => r.ref);
const cards16 = listOf(await getJson('/decisions?status=all')).filter((d) => ['message_template', 'lifecycle_rule', 'support_go_live'].includes(d.kind)).map((d) => d.ref);
// ⟨1.5⟩ governance (§20): meetings, charter scopes and versions, knowledge, OKRs, risks and KPI keys are data too.
const meetings = listOf(await getJson('/meetings'));
const charterScopes = listOf(await getJson('/charter'));
const knowledgeRefs = listOf(await getJson('/knowledge?include_expired=true')).map((k) => k.ref);
const objectiveRefs = listOf(await getJson('/okr')).map((o) => o.ref);
const riskRefs = listOf(await getJson('/risks')).map((r) => r.ref);
const kpiKeys = Object.fromEntries(await Promise.all(operating.map(async (c) => [c, (await getJson(`/kpis/${c}`)).kpis.map((k) => k.key)])));
const GOVERNANCE = ['meeting_resolution', 'charter_amendment', 'okr', 'knowledge_entry', 'risk_acceptance', 'authority_change'];
const cards17 = listOf(await getJson('/decisions?status=all')).filter((d) => GOVERNANCE.includes(d.kind) || d.expected).map((d) => d.ref);
// ⟨1.5⟩ management tools (§21): the cards §21 adds to or changes (a memo, an evaluation, a deploy with its diff), every file of a
// deploy diff the hub cut short (its whole patch), and thirty settled days of waste for the holding and for every company.
const cards18 = listOf(await getJson('/decisions?status=all')).filter((d) => d.kind === 'evaluation' || d.kind === 'deploy' || d.memos?.length).map((d) => d.ref);
const cutFiles = listOf(await getJson('/decisions?status=all')).filter((d) => d.kind === 'deploy').flatMap((d) => (d.payload?.diff?.files ?? []).filter((f) => f.truncated).map((f) => `/decisions/${d.ref}/diff?file=${f.path}`));
const tehDay = (n) => new Date(FIXED + 3.5 * 3_600_000 - n * 86_400_000).toISOString().slice(0, 10);
const wasteRange = `from=${tehDay(30)}&to=${tehDay(1)}`;
const allCompanies = listOf(await getJson('/companies')).map((c) => c.code);
// ⟨1.6⟩ the media studio and the legal counsel (§22): every case (each with its email thread) and the cards §22 makes.
const caseRefs = listOf(await getJson('/legal/cases')).map((c) => c.ref);
const cards19 = listOf(await getJson('/decisions?status=all')).filter((d) => ['media_series', 'media_publish', 'email_send', 'role_new'].includes(d.kind)).map((d) => d.ref);

const paths = [
  '/auth/session', '/meta', '/inbox/summary', '/owner/presence', '/owner/away-summary', '/owner/settings',
  '/decisions?status=pending', '/decisions?status=all', '/deliverables', '/deliverables?unrated=true',
  '/companies', '/work', '/planner', '/threads', '/notifications', '/control/state',
  '/treasury/summary', '/treasury/breakdown?by=model', '/treasury/breakdown?by=company', '/treasury/breakdown?by=day',
  '/connections', '/audit', '/audit/verify', '/auth/devices',
  ...['D-000014', 'D-000015', 'D-000016', 'D-000017', 'D-000011'].map((r) => `/decisions/${r}`),
  ...['O-000031', 'O-000030', 'O-000029'].map((r) => `/deliverables/${r}`),
  ...['HQ', 'TY', 'FX', 'PC'].flatMap((c) => [`/companies/${c}`, `/companies/${c}/departments`, `/org/${c}/chart`, `/employees?company=${c}`]),
  '/employees',
  ...['TY-CEO', 'FX-CEO', 'PC-CEO', 'TY-TECH-MGR', 'FX-TECH-MGR', 'PC-TECH-MGR', 'TY-GROWTH-MGR', 'FX-GROWTH-MGR', 'PC-GROWTH-MGR', 'TY-GROWTH-01', 'FX-QUANT-02', 'HQ-OVS-MGR', 'HQ-AIOPS-MGR', 'HQ-ADV'].map((c) => `/employees/${c}`),
  ...['w0', 'w1', 'w2', 'w3'].map((w) => `/work/${w}`),
  ...['A', 'FX-CEO', 'TY-TECH-MGR'].map((t) => `/threads/${t}/messages`),
  // ⟨1.3⟩ the Code Workshop and voice orders
  '/workshop/workspaces', '/workshop/grants?active=true', '/workshop/sessions', '/orders',
  ...['S-0004', 'S-0003', 'S-0002', 'S-0001'].flatMap((r) => [`/workshop/sessions/${r}`, `/workshop/sessions/${r}/events`]),
  // ⟨1.4⟩ oversight, inquiries, the assistant, stars, skills, the academy, egress and MCP, founding, backups.
  // Keys carry only the parameters the Android demo matches on (limit and cursor never; period and from where they select).
  '/oversight/summary', '/oversight/holds?state=held', '/oversight/findings', '/oversight/protocols', '/oversight/challenges', '/oversight/orders',
  '/inquiries?from=HQ-ADV', '/errands', '/stars/rollup?period=week', '/stars/rollup?period=month', '/stars/rubrics', '/lessons',
  '/skills', '/academy/curricula', '/academy/evals', '/academy/teach',
  '/egress/summary?period=day', '/egress', '/tools/mcp', '/tools/accounts', '/tools/catalog',
  '/foundings', '/foundings/C-0001', '/foundings/C-0002', '/foundings/C-0003', '/provisioning/plans/PV-0001', '/provisioning/plans/PV-0002', '/provisioning/plans/PV-0003', '/provisioning/runs/r1',
  '/backups/status', '/threads/N/messages', '/threads/P/messages',
  // ⟨1.4.2⟩ hiring starts with the owner: the state and the charters the owner hires from.
  '/owner/hiring', '/roles',
  // ⟨1.4.3⟩ the companies' stories
  '/stories',
  // ⟨1.4.4⟩ the owner's tools on existing APIs (gap analysis v2 §5A); the demo filters these lists itself.
  '/resolutions', '/notification-settings', '/treasury/quota', '/budgets', '/ops/sites', '/ops/incidents',
  ...['claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-5-5'].map((m) => `/treasury/what-if?model=${m}`),
  ['/runs', '/runs?limit=500'], ...Array.from({ length: 9 }, (_, i) => `/runs/run-${i}`),
  ['/treasury/calls', '/treasury/calls?limit=500'],
  // ⟨1.4.5⟩ every employee's training record (item 16) and each role's model comparison (item 30).
  ...employeeCodes.map((c) => `/academy/records/${c}`),
  ...academyRoles.map((r) => `/academy/runs?latest=true&role=${r}&subject_kind=model`),
  // ⟨1.4.6⟩ the companies' brands and seals: every active brand, and each company's versions (the founding's company too).
  '/brands', ...['TY', 'FX', 'PC', 'AC'].flatMap((c) => [`/companies/${c}/brand`, `/companies/${c}/brand/versions`]),
  // A wide planner (eight weeks either side) the demo cuts to the asked range and scope.
  ['/planner', `/planner?from=${new Date(Date.now() - 56 * 86_400_000).toISOString().slice(0, 10)}&to=${new Date(Date.now() + 56 * 86_400_000).toISOString().slice(0, 10)}`],
  // ⟨1.5⟩ revenue and support (§19). Whole lists the demo filters and changes itself (channels, conversations with their
  // messages, knowledge, templates, rules, NPS, rescue, feedback, intake), the 30 settled days of every account, and the
  // summaries and funnels it serves as they are, for every period and company.
  '/revenue/accounts', '/revenue/days',
  ...['day', 'week', 'month'].flatMap((p) => [`/revenue/summary?period=${p}`, ...operating.map((c) => `/revenue/summary?company=${c}&period=${p}`)]),
  ...operating.flatMap((c) => ['week', 'month'].map((p) => `/growth/funnel?company=${c}&period=${p}`)),
  '/growth/rescue', ...rescueRefs.map((r) => `/growth/rescue/${r}`), '/growth/templates', '/growth/rules', '/growth/nps',
  '/support/channels', '/support/conversations', ...conversationRefs.map((r) => `/support/conversations/${r}`), '/support/queue', '/support/kb', '/support/shadow',
  '/feedback', '/intake/sources', ...cards16.map((r) => `/decisions/${r}`),
  // ⟨1.5⟩ governance (§20). Whole lists the demo filters and changes itself (meetings, knowledge with the expired and the
  // support view, OKRs, outcomes, risks, the calendar with every conflict), every meeting with its turns, every charter version
  // and the diff of every pair, each company's three cards, KPI definitions and values, and the cards the governance kinds made.
  '/meetings', '/meetings/settings', ...meetings.flatMap((m) => [`/meetings/${m.ref}`, `/meetings/${m.ref}/turns`]),
  '/charter', ...charterScopes.flatMap((x) => [`/charter/${x.scope}/versions`, ...x.versions.flatMap((v) => [
    `/charter/${x.scope}/versions/${v.version}`,
    ...x.versions.filter((w) => w.version !== v.version).map((w) => `/charter/${x.scope}/versions/${v.version}/diff?against=${w.version}`),
  ])]),
  ['/knowledge', '/knowledge?include_expired=true'], ...knowledgeRefs.flatMap((r) => [`/knowledge/${r}`, `/knowledge/${r}/versions`]),
  '/cards', ...operating.map((c) => `/cards?company=${c}`), '/scorecards',
  ...operating.flatMap((c) => [`/kpis/${c}`, ...kpiKeys[c].map((k) => `/kpis/${c}/${k}/values`)]),
  '/okr', ...objectiveRefs.map((r) => `/okr/${r}`), '/outcomes', '/outcomes?due=true',
  '/authority', '/risks', ...riskRefs.map((r) => `/risks/${r}`), '/risks/matrix', '/calendar', '/decisions/batchable',
  ...cards17.map((r) => `/decisions/${r}`),
  // ⟨1.5⟩ management tools (§21). Whole lists the demo filters and changes itself (memos, proactive triggers, asks, weekly reviews,
  // briefings and letters, HR rounds, notes, checked claims, predictions, principles, substitutes, creatives), both periods of the
  // department ranks and the health board, waste (keyed bare and by company, the demo cuts the range and the day), ROI by every
  // axis and period (the demo filters by company), the deploy diff's full patches and the cards §21 touches.
  '/advisor/memos', '/advisor/triggers', '/ask', '/reviews/weekly', '/briefings', '/hr/rounds', '/notes', '/claims',
  '/rankings/departments?period=week', '/rankings/departments?period=month', '/runs/health?period=7d', '/runs/health?period=30d',
  ['/treasury/waste', `/treasury/waste?${wasteRange}`], ...allCompanies.map((c) => [`/treasury/waste?company=${c}`, `/treasury/waste?company=${c}&${wasteRange}`]),
  ...['company', 'department', 'employee'].flatMap((by) => ['week', 'month'].map((p) => `/treasury/roi?by=${by}&period=${p}`)),
  '/digital-ceo', '/digital-ceo/predictions', '/digital-ceo/principles', '/substitutes', '/creatives',
  ...cutFiles, ...cards18.map((r) => `/decisions/${r}`),
  // ⟨1.6⟩ the media studio and the legal counsel (§22). Whole lists the demo filters and changes itself (series, items with every
  // step, voices with their clips, the platforms' limits, role drafts), the owner's voice reference, every case with its emails,
  // the counsel's thread L and the four §22 cards. Departments (with their mandate), roles, accounts, threads and stories above
  // already carry what §22 adds to them.
  '/media/series', '/media/items', '/media/voices', '/media/voices/reference', '/media/limits', '/roles/drafts',
  '/legal/cases', ...caseRefs.map((r) => `/legal/cases/${r}`), '/threads/L/messages', ...cards19.map((r) => `/decisions/${r}`),
];

const ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/;
const DAY = /^\d{4}-\d{2}-\d{2}$/;
const rel = (v) => {
  if (typeof v === 'string' && ISO.test(v)) return `@${Math.round((Date.parse(v) - t0) / 60000)}m`;
  if (typeof v === 'string' && DAY.test(v)) return `@${Math.round((Date.parse(`${v}T00:00:00Z`) - Date.parse(new Date(t0).toISOString().slice(0, 10) + 'T00:00:00Z')) / 86400000)}d`;
  if (Array.isArray(v)) return v.map(rel);
  if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, rel(x)]));
  return v;
};

const out = {};
for (const entry of paths) {
  // An entry is a path, or [the key the demo looks up, the request that fills it].
  const [key, p] = Array.isArray(entry) ? entry : [entry, entry];
  const r = await handle(new Request(`http://demo/api/v1${p}`));
  out[key] = { status: r.status, body: rel(await r.json()) };
}
// A working session's next steps, so the Android demo can play them live (the web's mock reveals one per poll).
for (const ref of ['S-0003']) {
  const seen = out[`/workshop/sessions/${ref}/events`].body.items;
  let last = seen.at(-1)?.seq ?? 0;
  const script = [];
  for (let quiet = 0; quiet < 12; ) {
    const r = await handle(new Request(`http://demo/api/v1/workshop/sessions/${ref}/events?after=${last}`));
    const items = (await r.json()).items;
    if (!items.length) { quiet++; continue; }
    quiet = 0;
    for (const e of items) { script.push(rel(e)); last = e.seq; }
  }
  out[`#script:${ref}`] = { status: 200, body: { items: script } };
}
// ⟨1.5⟩ What a live meeting says next, so the Android demo reveals it as the web's mock does (one turn per poll after a pause).
for (const m of meetings.filter((x) => x.state === 'live')) {
  const seen = new Set(out[`/meetings/${m.ref}/turns`].body.items.map((t) => t.id));
  const script = [];
  for (let k = 1; k <= 8; k++) {
    clock = FIXED + k * 9_000;
    for (const t of (await getJson(`/meetings/${m.ref}/turns`)).items) if (!seen.has(t.id)) { seen.add(t.id); const { id: _i, n: _n, at: _a, ...rest } = t; script.push(rest); }
  }
  clock = FIXED;
  out[`#script:${m.ref}`] = { status: 200, body: { items: script } };
}
const dst = join(here, '../app/src/debug/assets/demo-fixtures.json');
writeFileSync(dst, JSON.stringify(out, null, 1) + '\n');
console.log(`demo fixtures: ${paths.length} responses -> ${dst}`);
