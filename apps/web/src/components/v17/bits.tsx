'use client';

import Link from 'next/link';
import { type ComponentProps, type ReactNode } from 'react';
import { Avatar } from '@/components/brand/avatar';
import { CompanyMark, Monogram } from '@/components/brand/marks';
import { FilterChip, Pill } from '@/components/ui/primitives';
import type { IconName } from '@/generated/icons';
import { useCompanies } from '@/lib/api/hooks';
import type { Actor } from '@/lib/api/v13';
import { cx, tokens, usd } from '@/lib/format';

type Tone = ComponentProps<typeof Pill>['tone'];
type Label = { fa: string; tone: Tone };

// ------------------------------------------------------------------ labels (§20) --
export const MEETING_TYPE: Record<string, { fa: string; icon: IconName }> = {
  board: { fa: 'هیئت‌مدیره', icon: 'holding' }, company: { fa: 'مدیریت شرکت', icon: 'companies' }, standup: { fa: 'استندآپ', icon: 'time' },
  war_room: { fa: 'اتاق جنگ', icon: 'urgent' }, postmortem: { fa: 'کالبدشکافی', icon: 'search' }, strategy: { fa: 'استراتژی', icon: 'chart' },
};
export const MEETING_STATE: Record<string, Label & { live?: boolean }> = {
  scheduled: { fa: 'زمان‌بندی‌شده', tone: 'neutral' }, prep: { fa: 'دستور آماده', tone: 'lapis' }, live: { fa: 'زنده', tone: 'pos', live: true },
  closing: { fa: 'جمع‌بندی', tone: 'warn', live: true }, ended: { fa: 'تمام شد', tone: 'neutral' }, cancelled: { fa: 'لغو شد', tone: 'neutral' },
};
export const ITEM_STATE: Record<string, string> = { waiting: 'منتظر', round_1: 'دور ۱', round_2: 'دور ۲', done: 'تمام شد', skipped: 'رد شد' };
export const CLAIM_STATUS: Record<string, Label & { icon: IconName }> = {
  sourced: { fa: 'با منبع', tone: 'pos', icon: 'seal' }, unsourced: { fa: 'بی‌منبع؛ بیرون از مصوبه', tone: 'neg', icon: 'urgent' },
  challenged: { fa: 'به چالش کشیده شد', tone: 'warn', icon: 'search' }, withdrawn: { fa: 'پس گرفته شد', tone: 'neutral', icon: 'close' },
};
export const VOTE_FA: Record<string, Label> = { support: { fa: 'موافق', tone: 'pos' }, oppose: { fa: 'مخالف', tone: 'neg' }, abstain: { fa: 'ممتنع', tone: 'neutral' } };
export const PRESENCE_FA: Record<string, { fa: string; note: string }> = {
  live: { fa: 'زنده', note: 'استریم و ورود صوتی' }, summary: { fa: 'خلاصه', note: 'فقط خلاصه بعد از جلسه' }, audio: { fa: 'نسخه‌ی صوتی', note: 'تا text-to-speech بیاید مثل خلاصه' },
};
export const CHARTER_STATUS: Record<string, Label> = { proposed: { fa: 'پیشنهادی، منتظر مُهر', tone: 'gold' }, sealed: { fa: 'مُهرشده', tone: 'pos' }, superseded: { fa: 'جایگزین شد', tone: 'neutral' } };
export const LAYER_FA: Record<string, { fa: string; icon: IconName }> = {
  holding: { fa: 'هلدینگ', icon: 'holding' }, company: { fa: 'شرکت', icon: 'companies' }, department: { fa: 'دپارتمان', icon: 'department' }, employee: { fa: 'کارمند', icon: 'memory' },
};
export const KNOWLEDGE_KIND: Record<string, string> = { principle: 'اصل', policy: 'سیاست', fact: 'واقعیت', faq: 'پرسش رایج', playbook: 'روش کار (Playbook)', support: 'مقاله‌ی پشتیبانی' };
export const KNOWLEDGE_STATUS: Record<string, Label> = {
  draft: { fa: 'پیش‌نویس', tone: 'neutral' }, in_review: { fa: 'در بازبینی', tone: 'lapis' }, approved: { fa: 'تأییدشده', tone: 'pos' }, expired: { fa: 'منقضی', tone: 'warn' }, retired: { fa: 'بازنشسته', tone: 'neutral' },
};
export const REVIEW_VERDICT: Record<string, Label> = { pass: { fa: 'قبول', tone: 'pos' }, changes: { fa: 'اصلاح لازم', tone: 'warn' }, reject: { fa: 'رد', tone: 'neg' } };
export const REVIEW_CHECK: Record<string, string> = { injection: 'تزریق دستور', secrets: 'رمز و کلید', conflicts: 'تناقض با اساسنامه', policy: 'اختیار و سیاست' };
export const CARD_FA: Record<string, { fa: string; icon: IconName; note: string }> = {
  stability: { fa: 'پایداری', icon: 'server', note: 'سلامت سرویس‌ها و حادثه‌ها' },
  growth: { fa: 'رشد', icon: 'chart', note: 'درآمد، کاربر و قیف' },
  safety_cost: { fa: 'ایمنی و هزینه', icon: 'treasury', note: 'توکن، بودجه و نظارت' },
};
export const KPI_STATE: Record<string, Label> = { ok: { fa: 'تازه', tone: 'pos' }, stale: { fa: 'قدیمی', tone: 'warn' }, no_source: { fa: 'منبع وصل نیست', tone: 'neutral' } };
export const OBJECTIVE_STATUS: Record<string, Label> = { draft: { fa: 'پیش‌نویس', tone: 'neutral' }, proposed: { fa: 'منتظر مُهر', tone: 'gold' }, active: { fa: 'فعال', tone: 'pos' }, closed: { fa: 'بسته', tone: 'neutral' } };
export const VERDICT: Record<string, Label> = {
  pending: { fa: 'منتظر سنجش', tone: 'neutral' }, met: { fa: 'رسید', tone: 'pos' }, partly: { fa: 'نیمه‌راه', tone: 'warn' }, missed: { fa: 'نرسید', tone: 'neg' }, unmeasurable: { fa: 'سنجش‌ناپذیر', tone: 'lapis' },
};
export const OUTCOME_STATUS: Record<string, string> = { due: 'موعد سنجش', answered: 'یادداشت پیشنهاددهنده رسید', verified: 'تأییدشده' };
export const RISK_CATEGORY: Record<string, string> = { product: 'محصول', security: 'امنیت', data: 'داده', money: 'پول', people: 'آدم‌ها', vendor: 'تأمین‌کننده', ops: 'عملیات', reputation: 'اعتبار' };
export const RISK_STATUS: Record<string, Label> = { open: { fa: 'باز', tone: 'neg' }, mitigating: { fa: 'در حال کاهش', tone: 'lapis' }, accepted: { fa: 'پذیرفته‌شده', tone: 'gold' }, closed: { fa: 'بسته', tone: 'neutral' } };
export const CAL_KIND: Record<string, { fa: string; icon: IconName; color: string }> = {
  deploy: { fa: 'انتشار', icon: 'server', color: 'var(--hq-chart-1)' }, campaign: { fa: 'کمپین', icon: 'send', color: 'var(--hq-chart-3)' }, event: { fa: 'رویداد', icon: 'star', color: 'var(--hq-chart-2)' },
  maintenance: { fa: 'نگه‌داری', icon: 'settings', color: 'var(--hq-chart-4)' }, meeting: { fa: 'جلسه', icon: 'meeting', color: 'var(--hq-silver-ink)' },
  freeze: { fa: 'فریز', icon: 'pause', color: 'var(--hq-warning)' }, holiday: { fa: 'تعطیل', icon: 'sleeping', color: 'var(--hq-text-muted)' },
};
export const CAL_STATUS: Record<string, string> = { planned: 'برنامه', done: 'انجام شد', cancelled: 'لغو شد' };
export const CAL_RISK: Record<string, Label> = { low: { fa: 'ریسک کم', tone: 'pos' }, medium: { fa: 'ریسک متوسط', tone: 'warn' }, high: { fa: 'ریسک بالا', tone: 'neg' } };
export const CONFLICT_RULE: Record<string, string> = {
  deploy_in_freeze: 'انتشار داخل فریز', deploy_in_campaign: 'انتشار هم‌زمان با کمپین یا رویداد', two_deploys: 'دو انتشار هم‌زمان',
  deploy_on_blackout_day: 'انتشار در روز ممنوع', deploy_on_holiday: 'انتشار در تعطیلی', maintenance_during_deploy: 'نگه‌داری هم‌زمان با انتشار',
};
export const WEEKDAY_FA: Record<string, string> = { SA: 'شنبه', SU: 'یکشنبه', MO: 'دوشنبه', TU: 'سه‌شنبه', WE: 'چهارشنبه', TH: 'پنجشنبه', FR: 'جمعه' };
export const ACTOR_ROLE_FA: Record<string, string> = { ceo: 'مدیرعامل', manager: 'مدیر', agent: 'ایجنت', owner: 'مدیر کل', sre: 'SRE', inspector: 'بازرس', advisor: 'مشاور کل', '*': 'هر کس' };

// ------------------------------------------------------------------ actors and refs --
/** The medallion an actor gets (owner, advisor orb, overseer sentinel, CEO, manager, employee, system). */
export function avatarKind(a: Actor | null | undefined): string {
  if (!a) return 'system';
  if (a.kind === 'owner') return 'owner';
  if (a.kind === 'system' || a.kind === 'service') return 'system';
  if (a.kind === 'overseer' || a.code === 'HQ-OVR') return 'overseer';
  if (a.code === 'HQ-ADV' || a.kind === 'advisor') return 'advisor';
  if (a.code === 'HQ-OVS-MGR' || a.kind === 'inspector') return 'inspector';
  if (a.code.endsWith('-CEO')) return 'ceo';
  if (a.code.endsWith('-MGR')) return 'manager';
  return 'employee';
}
export function ActorAvatar({ a, size = 32 }: { a: Actor | null | undefined; size?: number }) {
  const k = avatarKind(a);
  if (k === 'system') return <span className="flex flex-none items-center justify-center rounded-full bg-tile text-sec" style={{ width: size, height: size }}><Monogram size={Math.round(size * 0.5)} /></span>;
  return <Avatar kind={k} dept={a?.code.split('-')[1]} size={size} label={a?.display_fa ?? a?.code} />;
}

/** Where a reference opens in the panel, when it has a page. */
export function refHref(ref: string): string | null {
  if (/^D-\d+$/.test(ref)) return `/cartable?ref=${ref}`;
  if (/^O-\d+$/.test(ref)) return `/outputs?ref=${ref}`;
  if (/^W-\d+$/.test(ref)) return `/work/${ref}`;
  if (/^S-\d+$/.test(ref)) return `/workshop/${ref}`;
  if (/^SC-\d+$/.test(ref)) return `/support/${ref}`;
  if (/^MT-\d+$/.test(ref)) return `/meetings/${ref}`;
  if (/^(?:K|KB)-\d+$/.test(ref)) return `/knowledge?ref=${ref}`;
  if (/^(?:OB|KR)-\d+$/.test(ref)) return '/okr';
  if (/^RK-\d+$/.test(ref)) return `/risks?ref=${ref}`;
  if (/^CE-\d+$/.test(ref)) return '/calendar';
  if (/^M-\d+$/.test(ref)) return '/resolutions';
  if (/^(?:TY|FX|PC|HQ)@\d+$|^holding@\d+$/.test(ref)) return '/charter';
  return null;
}

/** A source or reference as a small Latin chip; a ref with a page is a link. */
export function RefChip({ r, note, tone = 'gold', className }: { r: string; note?: string | null; tone?: 'gold' | 'neutral' | 'neg'; className?: string }) {
  const href = refHref(r);
  const cls = cx('inline-flex min-w-0 max-w-full items-center gap-1 rounded-full px-2 py-0.5 text-[11px]', tone === 'gold' ? 'bg-gold-soft text-gold-ink' : tone === 'neg' ? 'bg-neg-soft text-neg' : 'bg-tile text-sec', href && 'hover:underline', className);
  const body = <><span className="fig">{r}</span>{note ? <span className="truncate text-muted">· {note}</span> : null}</>;
  return href ? <Link href={href} className={cls} title={note ?? undefined}>{body}</Link> : <span className={cls} title={note ?? undefined}>{body}</span>;
}

// ------------------------------------------------------------------ figures --
/** A KPI value with its unit, always a Latin figure. */
export function kpiFig(v: number | null | undefined, unit: string): string {
  if (v == null || !Number.isFinite(v)) return '—';
  if (unit === 'USD') return usd(v);
  const n = Math.abs(v) >= 1000 ? v.toLocaleString('en-US', { maximumFractionDigits: 0 }) : v.toLocaleString('en-US', { maximumFractionDigits: 2 });
  if (unit === '%') return `${n}%`;
  return unit ? `${n} ${unit}` : n;
}
/** Is a KPI at or beyond its target, given its direction? */
export const onTarget = (v: number | null, target: number | null, direction: 'up' | 'down' = 'up') => (v == null || target == null ? null : direction === 'down' ? v <= target : v >= target);
/** Tokens of a budget: "61K / 120K", a missing cap reads «بی‌سقف». */
export const budgetFig = (used: number, cap: number | null) => (cap == null ? `${tokens(used)}` : `${tokens(used)} / ${tokens(cap)}`);
export const pctOf = (used: number, cap: number | null) => (cap ? Math.min(100, (used / cap) * 100) : 0);
/** A 0..1 as a Latin percentage. */
export const pct01 = (v: number | null | undefined) => (v == null ? '—' : `${Math.round(v * 100)}%`);
/** Risk score tone: ≥ 15 high, ≥ 8 medium. */
export const scoreTone = (s: number): 'neg' | 'warn' | 'neutral' => (s >= 15 ? 'neg' : s >= 8 ? 'warn' : 'neutral');
/** Days from now (negative = past), whole days. */
export const daysFrom = (iso: string, now: number) => Math.round((Date.parse(iso) - now) / 86_400_000);

// ------------------------------------------------------------------ pieces --
/** The holding and every company from the API (any number), for pages where the holding is a scope of its own. */
export function ScopeChips({ value, onChange, all = true, holding = true, allLabel = 'همه' }: { value: string | null; onChange: (c: string | null) => void; all?: boolean; holding?: boolean; allLabel?: string }) {
  const { data } = useCompanies();
  const list = (data ?? []).filter((c) => holding || c.kind !== 'holding');
  return (
    <div className="flex flex-wrap gap-2">
      {all ? <FilterChip selected={!value} onClick={() => onChange(null)}>{allLabel}</FilterChip> : null}
      {list.map((c) => (
        <FilterChip key={c.code} selected={value === c.code} onClick={() => onChange(c.code)}>
          <span className="flex items-center gap-1.5">{c.kind === 'holding' ? <Monogram size={12} /> : <CompanyMark code={c.code} height={12} mono />}{c.name_fa}</span>
        </FilterChip>
      ))}
    </div>
  );
}

/** A company's mark; the holding's is the monogram. */
export function CoMark({ code, height = 12 }: { code: string; height?: number }) {
  const { data } = useCompanies();
  return data?.find((c) => c.code === code)?.kind === 'holding' ? <Monogram size={height} /> : <CompanyMark code={code} height={height} mono />;
}

/** A labelled number in a tile. */
export function Stat({ label, children, sub, tone }: { label: ReactNode; children: ReactNode; sub?: ReactNode; tone?: 'pos' | 'neg' | 'warn' }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5 rounded-[12px] bg-tile p-3">
      <span className="text-[11px] text-muted">{label}</span>
      <span className={cx('fig text-[18px] font-semibold leading-7', tone === 'pos' ? 'text-pos' : tone === 'neg' ? 'text-neg' : tone === 'warn' ? 'text-warn' : 'text-ink')}>{children}</span>
      {sub ? <span className="text-[11px] text-sec">{sub}</span> : null}
    </div>
  );
}

/** A KPI's 30 days as one recessive silver line (a gap where a day has no value, never a zero); the last point says whether the
 *  KPI is at its target (positive), short of it (warning), or carries no judgement (silver). Up is not "good" for every KPI. */
export function Trend({ values, hit, width = 68, height = 24 }: { values: Array<number | null>; hit?: boolean | null; width?: number; height?: number }) {
  const xs = values.map((v, i) => [i, v] as const).filter((p): p is readonly [number, number] => p[1] != null);
  if (xs.length < 2) return null;
  const hi = Math.max(...xs.map((p) => p[1])), lo = Math.min(...xs.map((p) => p[1]));
  const span = hi - lo || 1;
  const x = (i: number) => (i / Math.max(values.length - 1, 1)) * (width - 4) + 2;
  const y = (v: number) => height - 2 - ((v - lo) / span) * (height - 4);
  let d = '';
  values.forEach((v, i) => { if (v == null) return; d += `${d && values[i - 1] != null ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`; });
  const last = xs.at(-1)!;
  const dot = hit == null ? 'var(--hq-silver-ink)' : hit ? 'var(--hq-positive)' : 'var(--hq-warning)';
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden className="flex-none" style={{ direction: 'ltr' }}>
      <path d={d} fill="none" stroke="var(--hq-silver-ink)" strokeOpacity={0.7} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={x(last[0])} cy={y(last[1])} r={3} fill={dot} stroke="var(--hq-surface-card)" strokeWidth={1.5} />
    </svg>
  );
}

/** A unified diff, line by line: additions and removals marked by sign and colour, each line in its own direction. */
export function Diff({ text, className }: { text: string; className?: string }) {
  const lines = text.split('\n');
  return (
    <div className={cx('overflow-x-auto rounded-[12px] bg-page p-2 text-[12px] leading-6', className)} role="region" aria-label="تفاوت دو نسخه">
      {lines.map((l, i) => {
        const head = l.startsWith('@@') || l.startsWith('---') || l.startsWith('+++');
        const add = !head && l.startsWith('+');
        const del = !head && l.startsWith('-');
        return (
          <div key={i} className={cx('flex gap-2 rounded-[4px] px-2', add && 'bg-pos-soft', del && 'bg-neg-soft', head && 'text-muted')}>
            <span aria-hidden className={cx('fig w-3 flex-none text-center', add ? 'text-pos' : del ? 'text-neg' : 'text-muted')}>{head ? '' : add ? '+' : del ? '−' : ''}</span>
            <span dir={head ? 'ltr' : 'auto'} className={cx('min-w-0 flex-1 whitespace-pre-wrap break-words', head ? 'fig' : 'text-ink', del && 'line-through decoration-[var(--hq-neg-line)]')}>{head ? l : l.slice(1) || ' '}</span>
          </div>
        );
      })}
    </div>
  );
}
