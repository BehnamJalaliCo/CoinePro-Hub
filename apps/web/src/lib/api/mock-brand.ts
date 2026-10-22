// Development-only fixtures for contract v1.4.6 (§18.14): the companies' brands and seals, used by mock.ts. Never bundled in
// production (next.config aliases the fixtures module away). The Android debug build reads the same data through
// scripts/dump_demo_fixtures.mjs. Relative imports only: the dump script runs this file under plain Node.

import { BRAND, type Mark } from '../../generated/brand';
import type { BrandMark, BrandOptions, CompanyBrand } from './brand';

const now = Date.now();
const iso = (minAgo: number) => new Date(now - minAgo * 60_000).toISOString();
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const problem = (status: number, code: string, message_fa: string, extra: Record<string, unknown> = {}) =>
  json({ code, message_fa, status, title: code, type: 'about:blank', ...extra }, status);

/** A stable 64-hex stand-in for the server's sha256 (the demo needs only that it changes with the content). */
function digestOf(text: string): string {
  let out = '';
  for (let seed = 0; out.length < 64; seed++) {
    let h = 0x811c9dc5 ^ seed;
    for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 0x01000193);
    out += (h >>> 0).toString(16).padStart(8, '0');
  }
  return out.slice(0, 64);
}

// ------------------------------------------------------------ contrast --
// The accent is checked against both themes' page surfaces (design/tokens); below 3:1 the demo darkens or lightens it until it
// passes, as the hub's media worker does in OKLCH.
const PAGE = { night: '#0B0D14', day: '#F3EEE3' };
const rgb = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const lum = (hex: string) => {
  const [r, g, b] = rgb(hex).map((v) => { const c = v / 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; });
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
};
const contrast = (a: string, b: string) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x! + 0.05) / (y! + 0.05); };
const toward = (hex: string, target: number, t: number) => `#${rgb(hex).map((v) => Math.round(v + (target - v) * t).toString(16).padStart(2, '0')).join('').toUpperCase()}`;
function passing(accent: string, theme: 'night' | 'day'): string | null {
  if (contrast(accent, PAGE[theme]) >= 3) return null;
  for (let t = 0.02; t <= 1; t += 0.02) {
    const c = toward(accent, theme === 'night' ? 255 : 0, t);
    if (contrast(c, PAGE[theme]) >= 3) return c;
  }
  return null;
}

// ------------------------------------------------------------- versions --
const colorsOf = (m: Mark | BrandMark) => ({
  ink: m.layers.find((l) => l.role === 'ink')?.color ?? '#111216',
  accent: m.layers.find((l) => l.role === 'accent')?.color ?? null,
});
const bytes = (...ms: Array<BrandMark | null>) => ms.reduce((n, m) => n + (m?.layers.reduce((k, l) => k + l.d.length, 0) ?? 0), 0);
const sized = (m: BrandMark) => { const [, , w, h] = m.vb.split(' ').map(Number); return { width: Math.round(w!), height: Math.round(h!) }; };
const sealDigest = (b: Pick<CompanyBrand, 'mark' | 'wordmark' | 'ink' | 'accent' | 'accent_night' | 'accent_day'>) =>
  digestOf(JSON.stringify([b.mark, b.wordmark, b.ink, b.accent, b.accent_night, b.accent_day]));

/** Version 1 of every company with a folder in design/brand/companies/, active, from its flat SVGs (§18.14 "Existing companies"). */
const versions: Record<string, CompanyBrand[]> = Object.fromEntries(Object.entries(BRAND.companies).map(([code, b]) => {
  const { ink, accent } = colorsOf(b.mark);
  const v: CompanyBrand = {
    company: code, version: 1, state: 'active',
    source: { kind: 'seed', file_id: null, path: `design/brand/companies/${code.toLowerCase()}/`, sha256: digestOf(`seed:${code}`), ...sized(b.mark), has_alpha: true },
    mark: b.mark, wordmark: b.wordmark ?? null, ink, accent, accent_night: null, accent_day: null,
    palette: [{ hex: ink, share: accent ? 0.7 : 1 }, ...(accent ? [{ hex: accent, share: 0.3 }] : [])],
    options: { colors: accent ? 2 : 1, detail: 3 },
    checks: { paths_bytes: bytes(b.mark, b.wordmark ?? null), min_feature_px_16: 1.2, iou: 1, contrast_night: accent ? +contrast(accent, PAGE.night).toFixed(2) : null, contrast_day: accent ? +contrast(accent, PAGE.day).toFixed(2) : null, warnings: [] },
    digest: '', status_reason: null, created_at: iso(60 * 24 * 3), activated_at: iso(60 * 24 * 3),
  };
  return [code, [{ ...v, digest: sealDigest(v) }]];
}));
let etag = 1;

const active = (code: string) => versions[code]?.find((v) => v.state === 'active') ?? null;
const newestProposed = (code: string) => (versions[code] ?? []).filter((v) => v.state === 'proposed').sort((a, b) => b.version - a.version)[0] ?? null;

/** `Company.brand_version` (§3.1). */
export const activeVersion = (code: string): number | null => active(code)?.version ?? null;

/** `Founding.brand` (§18.8): the step «مُهر شرکت» of the founding's company. */
export function brandOf(code: string | null): { state: 'missing' | 'proposed' | 'active'; version: number | null } {
  const a = code ? active(code) : null;
  if (a) return { state: 'active', version: a.version };
  const p = code ? newestProposed(code) : null;
  return p ? { state: 'proposed', version: p.version } : { state: 'missing', version: null };
}

/** The demo traces no PNG: the proposal borrows another company's two-colour mark, so the preview, the seal and the night and
 *  day accents have something real to show. A file named like a photo fails `no_background`, one named "complex" fails
 *  `too_complex` above detail 1, so the owner can see both failures. */
function trace(v: CompanyBrand, part: 'mark' | 'wordmark', name: string) {
  const donor = Object.entries(BRAND.companies).find(([c, b]) => c !== v.company && b.mark.layers.some((l) => l.role === 'accent'))![1];
  const detail = v.options.detail;
  if (/photo|عکس|img_/i.test(name)) return Object.assign(v, { state: 'failed', status_reason: 'no_background' });
  if (/complex|پیچیده/i.test(name) && detail > 1) return Object.assign(v, { state: 'failed', status_reason: 'too_complex' });
  const prev = active(v.company);
  let mark: BrandMark = part === 'mark' ? donor.mark : prev?.mark ?? donor.mark;
  let wordmark: BrandMark | null = part === 'wordmark' ? donor.wordmark ?? null : prev?.wordmark ?? null;
  // One colour asked for: every layer is the body.
  const mono = (m: BrandMark): BrandMark => ({ vb: m.vb, layers: m.layers.map((l) => ({ ...l, role: 'ink', color: colorsOf(m).ink })) });
  if (v.options.colors === 1) { mark = mono(mark); wordmark = wordmark && mono(wordmark); }
  const { ink, accent } = colorsOf(mark);
  const accent_night = accent ? passing(accent, 'night') : null;
  const accent_day = accent ? passing(accent, 'day') : null;
  const min = [1.6, 1.3, 1.1, 0.9, 0.7][detail - 1] ?? 1.1;
  const warnings = [
    ...(/\.(jpe?g|webp)$/i.test(name) ? ['بدون شفافیت'] : []),
    ...(min < 1 ? ['در اندازه‌ی کوچک جزئیات گم میشود'] : []),
    ...(accent_night ? ['رنگ امضا روی زمینه‌ی شب کم‌کنتراست بود؛ برای شب روشن‌تر شد'] : []),
    ...(accent_day ? ['رنگ امضا روی زمینه‌ی روز کم‌کنتراست بود؛ برای روز تیره‌تر شد'] : []),
  ];
  Object.assign(v, {
    state: 'proposed', mark, wordmark, ink, accent, accent_night, accent_day,
    // Left to the logo, the colour count is what the trace found.
    options: { colors: v.options.colors ?? new Set(mark.layers.map((l) => l.color)).size, detail },
    palette: [{ hex: ink, share: accent ? 0.64 : 1 }, ...(accent ? [{ hex: accent, share: 0.36 }] : [])],
    source: { ...v.source, ...sized(mark) },
    checks: { paths_bytes: bytes(mark, wordmark), min_feature_px_16: min, iou: +(0.9 + detail * 0.015).toFixed(3), contrast_night: accent ? +contrast(accent, PAGE.night).toFixed(2) : null, contrast_day: accent ? +contrast(accent, PAGE.day).toFixed(2) : null, warnings },
  });
  v.digest = sealDigest(v);
  return v;
}

/** Which part a version traced and from which file, so a retrace repeats it. */
const made = new WeakMap<CompanyBrand, { part: 'mark' | 'wordmark'; name: string }>();

/** A new `processing` version that the demo's media worker finishes about three seconds later. */
function start(code: string, source: CompanyBrand['source'], part: 'mark' | 'wordmark', options: BrandOptions, name: string): CompanyBrand {
  const list = (versions[code] ??= []);
  const v: CompanyBrand = {
    company: code, version: Math.max(0, ...list.map((x) => x.version)) + 1, state: 'processing', source,
    mark: null, wordmark: null, ink: '#111216', accent: null, accent_night: null, accent_day: null, palette: [],
    options: { colors: options.colors, detail: Math.min(5, Math.max(1, options.detail ?? 3)) },
    checks: null, digest: '', status_reason: null, created_at: new Date().toISOString(), activated_at: null,
  };
  list.push(v);
  made.set(v, { part, name });
  setTimeout(() => trace(v, part, name), 3_000);
  return v;
}

/** The brand routes; null when the path is not one of them. */
export async function handleBrand(req: Request, p: string, files: Map<string, { name?: string; mime?: string; width?: number; height?: number }>): Promise<Response | null> {
  const m = req.method;
  if (m === 'GET' && p === '/brands') {
    const companies = Object.fromEntries(Object.keys(versions).flatMap((code) => {
      const a = active(code);
      return a?.mark ? [[code, { version: a.version, mark: a.mark, wordmark: a.wordmark, ink: a.ink, accent: a.accent, accent_night: a.accent_night, accent_day: a.accent_day }]] : [];
    }));
    return json({ etag: `W/"brands-${etag}"`, companies });
  }
  const one = /^\/companies\/([A-Z0-9]+)\/brand(\/versions)?$/.exec(p);
  if (m === 'GET' && one) {
    const code = one[1]!;
    if (one[2]) return json([...(versions[code] ?? [])].sort((a, b) => b.version - a.version));
    return json({ active: active(code), proposed: newestProposed(code) });
  }
  if (m !== 'POST') return null;
  const body = async <T,>() => (await req.json().catch(() => ({}))) as T;
  if (one && !one[2]) {
    const b = await body<{ file_id: string; part?: 'mark' | 'wordmark'; options?: BrandOptions }>();
    const f = files.get(b.file_id);
    const name = f?.name ?? 'logo.png';
    const source = { kind: 'upload' as const, file_id: b.file_id, path: null, sha256: digestOf(b.file_id), width: f?.width ?? 1024, height: f?.height ?? 1024, has_alpha: !/\.(jpe?g)$/i.test(name) };
    return json(start(one[1]!, source, b.part ?? 'mark', b.options ?? { detail: 3 }, name), 202);
  }
  const act = /^\/companies\/([A-Z0-9]+)\/brand\/(\d+)\/(retrace|activate)$/.exec(p);
  if (!act) return null;
  const [, code, ver, verb] = act;
  const v = versions[code!]?.find((x) => x.version === Number(ver));
  if (!v) return problem(404, 'not_found', 'این نسخه پیدا نشد.');
  if (verb === 'retrace') {
    const b = await body<{ options: BrandOptions }>();
    const was = made.get(v);
    return json(start(code!, v.source, was?.part ?? 'mark', b.options ?? v.options, was?.name ?? 'logo.png'), 202);
  }
  if (v.state !== 'proposed') return problem(409, 'brand_not_proposed', 'این نسخه هنوز آماده‌ی مُهر نیست.');
  for (const x of versions[code!]!) if (x.state === 'active') x.state = 'retired';
  Object.assign(v, { state: 'active', activated_at: new Date().toISOString() });
  etag += 1;
  return json(v);
}
