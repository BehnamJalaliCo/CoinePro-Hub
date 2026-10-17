// Digits: the text face renders ASCII digits as Persian (prose counts); figures
// (money, tokens, codes, model names) use the `.fig` class and stay Latin.

export const OWNER_TZ = 'Asia/Tehran';

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

export function cx(...a: Array<string | false | null | undefined>): string {
  return a.filter(Boolean).join(' ');
}

/** "claude-sonnet-5-5" → "Sonnet 5.5" (model names stay Latin). */
export function modelLabel(id: string | null | undefined): string {
  if (!id) return '—';
  const m = /^claude-([a-z]+)-(\d+)(?:-(\d+))?/.exec(id);
  if (!m) return id;
  return `${m[1]!.charAt(0).toUpperCase()}${m[1]!.slice(1)} ${m[2]}${m[3] ? `.${m[3]}` : ''}`;
}
