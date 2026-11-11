'use client';

// ⟨1.0.1⟩ Part C, the limits of the treasury (C3.6, contract §55.3; features 111 and 112). The owner's Claude accounts, each one ring:
// the share of its window that is used in the middle, its name under it and one line of where it stands; the one the hub is on has
// the turning arc only while a call is in flight. When every account is full, one amber line says until when the work waits. Then
// today's meter: what the agents spent today against their daily cap, with marks at 70, 90 and 100 percent, coloured by its state.
// Every figure says when it was read. A hub before §55 does not serve the block: nothing is shown and the older quota card stays.

import { Icon } from '@/components/icon';
import { useTick } from '@/components/live/motion';
import { bidi } from '@/components/ui/bidi';
import { Card, SectionTitle } from '@/components/ui/primitives';
import { inFa, num, queueOpensAt, type AccountState, type ClaudeAccount, type Limits, type MeterState, type TodayMeter } from '@/lib/api/v55';
import { cx, tokens } from '@/lib/format';
import { inFlight } from '@/lib/live/model';
import { useLiveState } from '@/lib/live/store';
import { Ring, ringColor, type RingTone } from './ring';
import { Facts, Ltr, clock } from './text';

// A full account is red-amber, never plain amber: beside the gold of the page it must not read as gold.
const ACCOUNT_TONE: Record<AccountState, RingTone> = { working: 'silver', ready: 'silver', full: 'near', off: 'muted' };

/** One line of where an account stands; a full one says when it opens, on the owner's clock and as a countdown. */
function AccountLine({ a, now }: { a: ClaudeAccount; now: number }) {
  if (a.state === 'working') return <>الان همین کار میکند</>;
  if (a.state === 'ready') return <>آماده</>;
  if (a.state === 'off') return <>خاموش</>;
  const left = inFa(a.resets_at, now);
  return a.resets_at ? <>پر است؛ <Ltr>{clock(a.resets_at)}</Ltr> خالی میشود{left ? <span className="block text-muted">{left}</span> : null}</> : <>پر است</>;
}

function Account({ a, live, now }: { a: ClaudeAccount; live: boolean; now: number }) {
  const u = num(a.utilization);
  const share = a.state === 'full' ? Math.max(u ?? 1, 1) : u;
  return (
    <li className="flex min-w-[8.5rem] flex-1 flex-col items-center gap-1.5 text-center" data-account={a.key} data-state={a.state}>
      <Ring value={a.state === 'off' ? null : share} size={84} stroke={6} tone={ACCOUNT_TONE[a.state]} live={live} broken={a.state === 'off'}
        label={`${a.name_fa}: ${u == null ? 'نامعلوم' : `${Math.round(u * 100)} درصد پر`}`}>
        <Ltr className={cx('text-[19px] font-bold leading-6', a.state === 'off' ? 'text-muted' : 'text-ink')}>{u == null ? '—' : `${Math.round(Math.min(1, u) * 100)}%`}</Ltr>
      </Ring>
      <span className="text-[13px] font-semibold text-ink">{bidi(a.name_fa)}</span>
      <span className={cx('text-[12px] leading-5', a.state === 'full' ? 'text-warn' : 'text-sec')} data-account-line>
        {a.state === 'full' ? <span className="me-1 inline-flex align-[-2px]"><Icon name="time" size={13} /></span> : null}
        <AccountLine a={a} now={now} />
      </span>
    </li>
  );
}

const METER: Record<MeterState, { fa: string; fill: string; ink: string; icon: 'seal' | 'urgent' | 'time' }> = {
  calm: { fa: 'آرام', fill: ringColor('silver'), ink: 'text-sec', icon: 'seal' },
  warm: { fa: 'از ۷۰٪ گذشت', fill: ringColor('warn'), ink: 'text-warn', icon: 'time' },
  near: { fa: 'نزدیک سقف', fill: ringColor('near'), ink: 'text-warn', icon: 'urgent' },
  full: { fa: 'سقف پر شد', fill: ringColor('neg'), ink: 'text-neg', icon: 'urgent' },
};
const MARKS = [70, 90, 100] as const;
const stateOf = (share: number): MeterState => (share >= 1 ? 'full' : share >= 0.9 ? 'near' : share >= 0.7 ? 'warm' : 'calm');

/** Today's meter: the agents' spend of today against their daily cap. */
export function TodayMeterBar({ t, now }: { t: TodayMeter; now: number }) {
  const spent = t.spent ?? 0;
  const cap = t.cap ?? 0;
  const share = num(t.share) ?? (cap ? spent / cap : 0);
  const state = t.state && METER[t.state] ? t.state : stateOf(share);
  const m = METER[state];
  const pct = Math.max(0, Math.min(100, share * 100));
  const left = inFa(t.resets_at, now);
  return (
    <div className="flex flex-col gap-2" data-testid="today-meter" data-state={state}>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-[13px] font-semibold text-ink">کنتور امروز</span>
        <span className={cx('inline-flex items-center gap-1 text-[12px] font-semibold', m.ink)} data-meter-word><Icon name={m.icon} size={13} />{m.fa}</span>
        <span className="ms-auto text-[13px] text-sec" data-meter-figure><Ltr className="text-[15px] font-bold text-ink">{tokens(spent)}</Ltr> از <Ltr>{cap ? tokens(cap) : '—'}</Ltr></span>
      </div>
      <div className="relative mb-5 mt-1 h-3 rounded-full bg-tile" role="meter" aria-label="مصرف امروز از سقف روزانه" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)}>
        <span className="hq-m12 absolute inset-y-0 start-0 block rounded-full" style={{ width: `${pct}%`, background: m.fill }} />
        {MARKS.map((x) => (
          <span key={x} data-mark={x} className="absolute -bottom-1 -top-1 w-0 border-s-[1.5px]" style={{ insetInlineStart: x === 100 ? 'calc(100% - 1.5px)' : `${x}%`, borderColor: pct >= x ? m.fill : 'var(--hq-line-strong)' }}>
            <Ltr className={cx('absolute top-[18px] translate-x-1/2 whitespace-nowrap text-[10.5px]', pct >= x ? m.ink : 'text-muted')}>{x}%</Ltr>
          </span>
        ))}
      </div>
      {t.note_fa ? <p className="text-[12px] leading-5 text-sec" data-meter-note>{bidi(t.note_fa)}</p> : null}
      <p className="text-[11px] text-muted" data-meter-reset>ساعت <Ltr>{clock(t.resets_at)}</Ltr> از نو شروع میشود{left ? `، ${left}` : ''}.</p>
    </div>
  );
}

/** The limits block of the treasury. Nothing when the hub does not serve it. */
export function LimitsBlock({ limits, className }: { limits: Limits | null | undefined; className?: string }) {
  const now = useTick(30_000);
  const flying = useLiveState((s) => inFlight(s)) > 0;
  if (!limits) return null;
  const accounts = limits.accounts ?? [];
  const opens = limits.waiting ? queueOpensAt(limits) : null;
  const read = accounts.map((a) => a.observed_at).filter((x): x is string => !!x).sort().pop() ?? null;
  return (
    <Card as="section" aria-label="لیمیت اکانت‌ها" data-testid="limits" className={cx('flex flex-col gap-4 p-4 sm:p-5', className)}>
      <SectionTitle title="اکانت‌های Claude" note={<Facts>{accounts[0]?.window_fa ? bidi(accounts[0].window_fa) : null}{read ? <span data-read-at>خوانده‌شده در <Ltr>{clock(read)}</Ltr></span> : 'هنوز خوانده نشده'}</Facts>} />
      {limits.waiting ? (
        <p role="status" data-testid="limits-waiting" className="flex items-start gap-2 rounded-[12px] bg-warn-soft px-3 py-2.5 text-[13px] font-semibold leading-6 text-warn">
          <span className="mt-0.5 flex-none"><Icon name="time" size={16} /></span>
          <span>{accounts.length === 2 ? 'هر دو اکانت پر است' : 'همه‌ی اکانت‌ها پر است'}؛ کارها {opens ? <>تا <Ltr>{clock(opens)}</Ltr> </> : null}در صف میمانند.</span>
        </p>
      ) : null}
      {accounts.length ? (
        <ul className="flex flex-wrap items-start justify-around gap-x-4 gap-y-5">
          {accounts.map((a) => <Account key={a.key} a={a} now={now} live={a.state === 'working' && flying} />)}
        </ul>
      ) : null}
      <div className="h-px bg-div" aria-hidden />
      <TodayMeterBar t={limits.today} now={now} />
    </Card>
  );
}
