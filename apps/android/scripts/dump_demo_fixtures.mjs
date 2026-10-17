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

const here = dirname(fileURLToPath(import.meta.url));
const { handle } = await import(join(here, '../../web/src/lib/api/mock.ts'));
const t0 = Date.now();

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
  '/foundings', '/foundings/C-0001', '/foundings/C-0002', '/provisioning/plans/PV-0001', '/provisioning/plans/PV-0002', '/provisioning/runs/r1',
  '/backups/status', '/threads/N/messages', '/threads/P/messages',
  // ⟨1.4.2⟩ hiring starts with the owner: the state and the charters the owner hires from.
  '/owner/hiring', '/roles',
  // ⟨1.4.3⟩ the companies' stories
  '/stories',
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
for (const p of paths) {
  const r = await handle(new Request(`http://demo/api/v1${p}`));
  out[p] = { status: r.status, body: rel(await r.json()) };
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
const dst = join(here, '../app/src/debug/assets/demo-fixtures.json');
writeFileSync(dst, JSON.stringify(out, null, 1) + '\n');
console.log(`demo fixtures: ${paths.length} responses -> ${dst}`);
