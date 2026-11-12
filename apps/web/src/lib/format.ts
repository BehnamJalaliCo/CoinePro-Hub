// Digits: the text face renders ASCII digits as Persian (prose counts); figures
// (money, tokens, codes, model names) use the `.fig` class and stay Latin.

export const OWNER_TZ = 'Asia/Tehran';

/** What a number field reads before parsing: Persian (۰-۹) and Arabic-Indic (٠-٩) digits as ASCII, the Persian decimal sign (٫) as '.',
 *  thousands separators (٬ ,) dropped. JS `\d` is ASCII-only, so a field that filters first would silently lose every Persian digit. */
export function latinNum(s: string): string {
  return s.replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 0x06f0)).replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 0x0660)).replace(/٫/g, '.').replace(/[٬,]/g, '');
}
/** A typed number, or null when the text is empty or not a number (never a silent 0). `signed` allows a leading minus. */
export function parseNum(s: string, signed = false): number | null {
  const t = latinNum(s).trim();
  if (!(signed ? /^-?\d+(\.\d+)?$/ : /^\d+(\.\d+)?$/).test(t)) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}
/** The text a number field keeps while it is being typed: ASCII digits and one '.' (and a leading '-' when signed), so "2." survives. */
export function numText(s: string, signed = false): string {
  let t = latinNum(s).replace(signed ? /[^\d.-]/g : /[^\d.]/g, '');
  if (signed) t = (t.startsWith('-') ? '-' : '') + t.replace(/-/g, '');
  const dot = t.indexOf('.');
  return dot < 0 ? t : t.slice(0, dot + 1) + t.slice(dot + 1).replace(/\./g, '');
}

/** Persian decimal separator for prose numbers ("7٫9"); the text face draws Persian digits. */
export function faDecimal(n: number, digits = 1): string {
  return n.toFixed(digits).replace('.', '٫');
}

export function tokens(n: number | null | undefined): string {
  if (n == null) return '—';
  const a = Math.abs(n);
  if (a >= 1_000_000) return `${(n / 1_000_000).toFixed(a >= 10_000_000 ? 0 : 1).replace(/\.0$/, '')}M`;
  if (a >= 1_000) return `${(n / 1_000).toFixed(a >= 100_000 ? 0 : 1).replace(/\.0$/, '')}K`;
  return String(n);
}

export function usd(v: string | number | null | undefined, digits = 2): string {
  if (v == null || v === '') return '—';
  const n = typeof v === 'string' ? Number(v) : v;
  if (!Number.isFinite(n)) return '—';
  return `$${n.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
}

export function pct(v: number | null | undefined): string {
  return v == null ? '—' : `${Math.round(v)}٪`;
}

/**
 * A share as a percentage, whichever way the hub writes it: a fraction 0..1 (⟨1.10⟩ `uptime_24h`, rates, confidences) or a value that is
 * already a percentage (> 1; an older hub's uptime). Never more than 100%, never negative. [digits]: decimals kept below 100 (a full 100
 * is written whole). Latin digits (a figure), with the percent sign.
 */
export function percentOf(v: number | string | null | undefined, digits = 0): string {
  const n = typeof v === 'string' ? Number(v) : v;
  if (n == null || !Number.isFinite(n)) return '—';
  const p = Math.min(100, Math.max(0, n > 1 ? n : n * 100));
  return `${p === 100 ? '100' : p.toFixed(digits)}%`;
}
/** The same share as a number 0..100 (a bar's width). */
export const percentValue = (v: number | string | null | undefined) => {
  const n = typeof v === 'string' ? Number(v) : v;
  return n == null || !Number.isFinite(n) ? 0 : Math.min(100, Math.max(0, n > 1 ? n : n * 100));
};

const fmt = (o: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat('fa-IR-u-ca-persian-nu-latn', { timeZone: OWNER_TZ, ...o });
const dayMonth = fmt({ day: 'numeric', month: 'long' });
const dayMonthYear = fmt({ day: 'numeric', month: 'long', year: 'numeric' });
const weekdayDay = fmt({ weekday: 'long', day: 'numeric', month: 'long' });
const time = fmt({ hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });

/** "۲۵ مهر" — Jalali, in the owner's time zone. */
export function jDate(iso: string | null | undefined, withYear = false): string {
  if (!iso) return '—';
  return (withYear ? dayMonthYear : dayMonth).format(new Date(iso));
}
export function jWeekday(iso: string): string {
  return weekdayDay.format(new Date(iso));
}
export function jTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  return time.format(new Date(iso));
}
export function jDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  return `${jDate(iso)}، ${jTime(iso)}`;
}

/** "۵ دقیقه پیش" / "۳ ساعت پیش" / date. */
export function ago(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return '—';
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 45) return 'همین الان';
  const m = Math.round(s / 60);
  if (m < 60) return `${m} دقیقه پیش`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} ساعت پیش`;
  const d = Math.round(h / 24);
  if (d < 7) return `${d} روز پیش`;
  return jDate(iso);
}

/** Time left until an ISO instant, for expiries and freezes. */
export function until(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return '—';
  const m = Math.round((new Date(iso).getTime() - now) / 60000);
  if (m <= 0) return 'گذشته';
  if (m < 60) return `${m} دقیقه مانده`;
  const h = Math.round(m / 60);
  if (h < 48) return `${h} ساعت مانده`;
  return `${Math.round(h / 24)} روز مانده`;
}

/**
 * A link from data, only when it is the web's own kind: an absolute http(s) URL or a path on this origin (`/…`, not `//host`). Anything
 * else (`javascript:`, `data:`, an unknown scheme) gives null, and the caller shows the text without a link.
 */
export function safeHref(v: unknown): string | null {
  const s = typeof v === 'string' ? v.trim() : '';
  if (!s) return null;
  if (/^\/(?!\/)/.test(s)) return s;
  try { const u = new URL(s); return u.protocol === 'https:' || u.protocol === 'http:' ? u.href : null; } catch { return null; }
}

export function cx(...a: Array<string | false | null | undefined>): string {
  return a.filter(Boolean).join(' ');
}

/** "claude-sonnet-5-5" → "Sonnet 5.5" (model names stay Latin). */
/** A ledger row's model is a real model: Claude Code records its own local messages (an interruption, an API error notice) as
 *  `<synthetic>`, with no tokens and no cost, so such a placeholder never shows as a model. */
export function isRealModel(id: string | null | undefined): id is string {
  return !!id && !id.startsWith('<');
}

export function modelLabel(id: string | null | undefined): string {
  if (!id) return '—';
  const m = /^claude-([a-z]+)-(\d+)(?:-(\d+))?/.exec(id);
  if (!m) return id;
  return `${m[1]!.charAt(0).toUpperCase()}${m[1]!.slice(1)} ${m[2]}${m[3] ? `.${m[3]}` : ''}`;
}
