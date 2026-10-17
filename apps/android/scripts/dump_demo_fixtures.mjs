// Dumps the web's development fixtures (apps/web/src/lib/api/mock.ts) into the Android debug assets, so the
// demo on both clients shows the same holding. Instants become offsets from "now" ("@-42m"), which the
// Android demo resolves at load time, so relative times ("5 minutes ago") stay true.
// Usage: node --experimental-strip-types scripts/dump_demo_fixtures.mjs
import { writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

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
const dst = join(here, '../app/src/debug/assets/demo-fixtures.json');
writeFileSync(dst, JSON.stringify(out, null, 1) + '\n');
console.log(`demo fixtures: ${paths.length} responses -> ${dst}`);
