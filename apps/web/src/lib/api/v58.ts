/**
 * ⟨1.0.3⟩ Contract §58 «room to write, a session that leaves its working group, a lighter desk». No new route of the app's own: what
 * the redesigned pieces read from the shapes they already have, each read leniently (the hub names its new fields as it builds them):
 * - §58.1 the question card above the composer, its «خروجی آخر» chip (the session's newest output);
 * - §58.2 a closed session that left its working group's draft in the library: `playbook_kept` (true, a ref, or the playbook) or
 *   `playbook` on the session, its card, or the close's answer;
 * - §58.3 a sealed working group's day as one line, from its routine's time and each member's standing word (§45);
 * - §58.4 what stayed after a publication: `archived` and `freed_bytes` on a desk card (or on its publication);
 * - §58.5 the desk's channels (`DeskCard.channel`, Instagram when it says none).
 */
import type { MemberPublish } from './v44';
import type { PlaybookPlatform, PlaybookRoutine } from './v40';

// ======================================================================================== §58.1 the owner's turn ==
export const MORE_FA = 'بیشتر';
export const LESS_FA = 'کمتر';
export const latestFa = (title: string) => `خروجی آخر: ${title}`;
/** The question card shows this many lines until «بیشتر». */
export const QUESTION_LINES = 3;
/** The composer grows to this many lines, then scrolls inside itself. */
export const COMPOSER_LINES = 5;

// ============================================================================= §58.2 the working group kept ==
export const PLAYBOOK_KEPT_FA = 'کارگروه این جلسه در کتابخانه ماند';
/** What a session (its card, its report, its `session`, the close's answer) says of the working group it left: null when nothing. */
export function playbookKept(...sources: unknown[]): { ref: string | null } | null {
  for (const s of sources) {
    if (!s || typeof s !== 'object') continue;
    const o = s as Record<string, unknown>;
    for (const v of [o.playbook_kept, o.playbook]) {
      if (v === true) return { ref: null };
      if (typeof v === 'string' && v.trim()) return { ref: v.trim() };
      if (v && typeof v === 'object') {
        const r = (v as { ref?: unknown }).ref;
        return { ref: typeof r === 'string' && r.trim() ? r.trim() : null };
      }
    }
  }
  return null;
}
export const playbookHref = (k: { ref: string | null }) => (k.ref ? `/playbooks/${encodeURIComponent(k.ref)}` : '/playbooks');

// =================================================================================== §58.3 the group's day ==
const FREQ_FA: Record<string, string> = { DAILY: 'هر روز', WEEKLY: 'هر هفته', HOURLY: 'هر ساعت', MONTHLY: 'هر ماه' };
const DAY_FA: Record<string, string> = { SA: 'شنبه', SU: 'یکشنبه', MO: 'دوشنبه', TU: 'سه‌شنبه', WE: 'چهارشنبه', TH: 'پنجشنبه', FR: 'جمعه' };
const two = (n: number) => String(n).padStart(2, '0');
/** «هر روز» and «07:00» of a routine's schedule (an RRULE of the hub's); null when it cannot be read. A weekly one names its days. */
export function whenOfSchedule(schedule: string | null | undefined): { every_fa: string; hm: string | null } | null {
  if (!schedule) return null;
  const k = Object.fromEntries(schedule.replace(/^RRULE:/, '').split(';').map((x) => x.split('=') as [string, string]));
  const every = FREQ_FA[k.FREQ ?? ''];
  if (!every) return null;
  const days = k.FREQ === 'WEEKLY' ? (k.BYDAY ?? '').split(',').map((d) => DAY_FA[d]).filter(Boolean) : [];
  const h = Number(k.BYHOUR);
  const m = Number(k.BYMINUTE ?? 0);
  return { every_fa: days.length ? `هر ${days.join(' و ')}` : every, hm: k.FREQ === 'HOURLY' || !Number.isFinite(h) || k.BYHOUR == null ? null : `${two(h)}:${two(Number.isFinite(m) ? m : 0)}` };
}
/** The routine that makes the day's package: the daily one first, else the first that can be read. */
export const makingRoutine = (routines: PlaybookRoutine[] | undefined) =>
  (routines ?? []).find((r) => /FREQ=DAILY/.test(r.schedule)) ?? (routines ?? []).find((r) => whenOfSchedule(r.schedule)) ?? null;
export const ASK_FA = 'تأیید تو';
export const AUTO_FA = 'انتشار خودکار';
export const BUILD_FA = 'ساخت';
const CHANNEL_OF: Partial<Record<PlaybookPlatform, string>> = { instagram: 'اینستاگرام', any: 'اینستاگرام', youtube: 'یوتیوب', telegram: 'تلگرام', site: 'سایت' };
/** The steps of a member's day: build, then his tap or by itself, then the channel. Null when the routine's time cannot be read. */
export function dayFlow(routines: PlaybookRoutine[] | undefined, platform: PlaybookPlatform, publish: MemberPublish | undefined) {
  const r = makingRoutine(routines);
  const when = whenOfSchedule(r?.schedule);
  if (!when) return null;
  return { every_fa: when.every_fa, hm: when.hm, steps: [BUILD_FA, publish?.mode === 'auto' ? AUTO_FA : ASK_FA, CHANNEL_OF[platform] ?? 'اینستاگرام'] };
}

// ================================================================================== §58.4 what a publication keeps ==
/** «بایگانی شد · 12.4 MB آزاد شد»: whether the package was filed, and how much the sweep freed (null while not yet swept). */
export function sweptOf(...sources: unknown[]): { archived: boolean; freed: number | null } | null {
  let archived = false;
  let freed: number | null = null;
  for (const s of sources) {
    if (!s || typeof s !== 'object') continue;
    const o = s as Record<string, unknown>;
    if (o.archived === true || (typeof o.archived === 'string' && o.archived) || (o.archived && typeof o.archived === 'object')) archived = true;
    const f = typeof o.freed_bytes === 'string' ? Number(o.freed_bytes) : o.freed_bytes;
    if (freed == null && typeof f === 'number' && Number.isFinite(f) && f > 0) freed = f;
  }
  return archived || freed != null ? { archived, freed } : null;
}
export const ARCHIVED_FA = 'بایگانی شد';
export const freedFa = (size: string) => `${size} آزاد شد`;

// ===================================================================================== §58.5 the desk's channels ==
export const CHANNEL_FA: Record<string, string> = { instagram: 'اینستاگرام', youtube: 'یوتیوب', telegram: 'تلگرام', x: 'ایکس', site: 'سایت' };
export const channelOf = (c: { channel?: string | null }) => (c.channel && c.channel.trim() ? c.channel.trim() : 'instagram');
export const channelFa = (ch: string) => CHANNEL_FA[ch] ?? ch;
export const PUBLISH_FA = 'انتشار';
