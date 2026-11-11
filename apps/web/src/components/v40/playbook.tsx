'use client';

// ⟨1.22⟩ Contract §40 «یک جلسه میشود کارگروهی که به هر شرکت و پلتفرم میدهی»: the session's memory («تا اینجا») and the button that drafts a playbook
// from it, the playbook card in the chat, the playbook's own page (edit the draft lightly, seal, give it to another company or platform,
// retire it) and the library of every playbook. The owner never reads a ref: a playbook is its title, a session is a link.
//
// ⟨1.0.1⟩ Part C (C3.4), the page in the app's look. A sealed working group opens with its member companies as tiles (state, last run,
// next run, a silver work line only while something of it runs; one that stands still says why in one line and has a quiet
// «راه بینداز»), then each routine with its last seven runs as dots; what it is (goal, seats, rules, connections) folds under
// «تعریف کارگروه». Each member's settings are one grouped block: «انتشار خودکار» (a silver switch, with «بهترین ساعت، خودکار» and the
// fixed hour), «گوینده‌ی محتوا», «دفتر موضوع‌ها». A draft's «مُهر کارگروه» lives in the decision bar with a one-line summary: one tap,
// no fingerprint. The header folds to its title once the page has scrolled under it (M18).

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import { Icon } from '@/components/icon';
import { DecisionBar } from '@/components/look/decision-bar';
import { GroupHeader, MemberHead, QUIET_ACTION, QuietLink, RunDots, SETTING_ROW, SealSummary, StateWord, WhenAt, nextRun } from '@/components/look/group';
import { SpringSheet } from '@/components/look/spring-sheet';
import { stagger } from '@/components/look/stagger';
import { Facts, Ltr, faCount } from '@/components/look/text';
import { Button, IconButton } from '@/components/ui/button';
import { Md } from '@/components/ui/md';
import { Dialog } from '@/components/ui/overlay';
import { Card, Empty, ErrorState, FilterChip, PageHeader, SectionTitle, Skeleton, Switch } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { FaPara, FaText } from '@/components/v29/text';
import { errText, field } from '@/components/v31/kit';
import { useCompanies } from '@/lib/api/hooks';
import {
  HELPER_FA, PB_STATE_FA, PLATFORMS, PLATFORM_FA, publishes, useDraftPlaybook, usePlaybook, usePlaybookActions, usePlaybooks,
  type Playbook, type PlaybookPatch, type PlaybookPlatform, type PlaybookRoutine, type PlaybookSeat, type PlaybookState,
} from '@/lib/api/v40';
import { CONNECTION_FA, useGroupActions } from '@/lib/api/v29';
import { accountsNamed, clockOf, publishRule, useMemberPublish, type MemberPublish } from '@/lib/api/v44';
import { bestHourOf, useBestHour } from '@/lib/api/v47';
import { useGroupRunsLook } from '@/lib/api/v55';
import { BestHourChoice } from '@/components/v47/best-hour';
import { LedgerRow } from '@/components/v47/ledger';
import { NarratorRow } from '@/components/v47/narrator';
import { ApiError } from '@/lib/api/client';
import { cx, jDate } from '@/lib/format';

// One look for every text field of these pages (the focus ring is silver: a field is not the owner's act).
const INPUT = cx(field, 'focus:border-[var(--hq-silver-ink)]');
const LINK = 'font-semibold text-silver-ink hover:text-ink hover:underline';
const STATE_KIND: Record<PlaybookState, 'on' | 'wait' | 'off'> = { draft: 'wait', sealed: 'on', retired: 'off' };

const DAY_FA: Record<string, string> = { SA: 'شنبه', SU: 'یکشنبه', MO: 'دوشنبه', TU: 'سه‌شنبه', WE: 'چهارشنبه', TH: 'پنجشنبه', FR: 'جمعه' };

/** An RRULE in the words the owner says it in: «هر روز ۰۹:۰۰»; the times stay Latin figures. */
export function whenFa(schedule: string): string {
  const k = Object.fromEntries(schedule.replace(/^RRULE:/, '').split(';').map((x) => x.split('=') as [string, string]));
  const hm = k.BYHOUR ? ` ${k.BYHOUR.padStart(2, '0')}:${(k.BYMINUTE ?? '0').padStart(2, '0')}` : '';
  if (k.FREQ === 'HOURLY') return 'هر ساعت';
  if (k.FREQ === 'DAILY') return `هر روز${hm}`;
  if (k.FREQ === 'WEEKLY') {
    const days = (k.BYDAY ?? '').split(',').map((d) => DAY_FA[d]).filter(Boolean);
    if (!days.length) return `هر هفته${hm}`;
    return `هر ${days.length === 1 ? days[0] : `${days.slice(0, -1).join('، ')} و ${days.at(-1)}`}${hm}`;
  }
  if (k.FREQ === 'MONTHLY') return `ماهانه، روز ${k.BYMONTHDAY ?? '1'}${hm}`;
  return schedule;
}

const seatTitle = (pb: Pick<Playbook, 'seats'>, key: string) => pb.seats?.find((s) => s.seat === key)?.title_fa ?? key;

// ===================================================================================== what a playbook says ==
function HelperChips({ helpers }: { helpers?: string[] }) {
  if (!helpers?.length) return null;
  return <span className="flex flex-wrap gap-1" aria-label="کمک‌ها">{helpers.map((h) => <span key={h} className="inline-flex h-5 items-center rounded-full border border-div px-2 text-[11px] font-semibold text-sec">{HELPER_FA[h] ?? h}</span>)}</span>;
}

/** Every field of a playbook, read-only: its purpose, seats with their helpers, routines in plain times, KPIs, connections and rules. */
export function PlaybookBody({ pb, compact }: { pb: Playbook; compact?: boolean }) {
  const seats = pb.seats ?? [];
  const routines = pb.routines ?? [];
  const rules = pb.rules_fa ?? [];
  const kpis = pb.kpis ?? [];
  return (
    <div className="flex flex-col gap-3">
      {pb.purpose_fa ? <FaPara text={pb.purpose_fa} className="text-[13px] leading-6 text-sec" /> : null}
      {seats.length ? (
        <section aria-label="جایگاه‌ها" className="flex flex-col gap-1.5">
          <h3 className="text-[12px] font-semibold text-muted">چه کسانی</h3>
          <ul className="flex flex-col gap-1.5">
            {seats.map((s) => (
              <li key={s.seat} className="flex flex-wrap items-center gap-x-2.5 gap-y-1 rounded-[10px] bg-tile px-3 py-2" data-seat={s.seat}>
                <span className="text-[13px] font-semibold"><FaText text={s.title_fa} /></span>
                <HelperChips helpers={s.helpers} />
                {!compact && s.duties_fa ? <span className="basis-full text-[12px] leading-5 text-sec"><FaText text={s.duties_fa} /></span> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {routines.length ? (
        <section aria-label="روال‌ها" className="flex flex-col gap-1.5">
          <h3 className="text-[12px] font-semibold text-muted">چه کاری، کِی</h3>
          <ul className="flex flex-col gap-1.5">
            {routines.map((r) => (
              <li key={r.key} className="flex flex-col gap-0.5 rounded-[10px] bg-tile px-3 py-2" data-routine={r.key}>
                <b className="text-[13px] font-semibold"><FaText text={r.title_fa} /></b>
                <span className="text-[12px] text-sec"><Facts><span className="fig">{whenFa(r.schedule)}</span>{seatTitle(pb, r.seat)}</Facts></span>
                {!compact && r.brief_md ? <Md text={r.brief_md} className="flex flex-col gap-1 text-[12px] leading-6 text-sec" /> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {!compact && kpis.length ? (
        <section aria-label="شاخص‌ها" className="flex flex-col gap-1.5">
          <h3 className="text-[12px] font-semibold text-muted">با چه عددی میسنجیم</h3>
          <ul className="flex flex-wrap gap-1.5">{kpis.map((k) => <li key={k.key} className="inline-flex h-7 items-center rounded-full bg-tile px-3 text-[12px]"><FaText text={k.title_fa} />{k.unit ? <span className="ms-1 text-muted">({k.unit})</span> : null}</li>)}</ul>
        </section>
      ) : null}
      {!compact && pb.connections?.length ? (
        <section aria-label="اتصال‌ها" className="flex flex-wrap items-center gap-1.5 text-[12px] text-sec"><span className="text-muted">اتصال‌ها:</span>{pb.connections.map((c) => <span key={c} className="inline-flex h-6 items-center rounded-full bg-tile px-2.5"><FaText text={(CONNECTION_FA as Record<string, string>)[c] ?? c} /></span>)}</section>
      ) : null}
      {rules.length ? (
        <section aria-label="قانون‌ها" className="flex flex-col gap-1.5">
          <h3 className="text-[12px] font-semibold text-muted">قانون‌ها</h3>
          <ul className="flex flex-col gap-1 ps-4 text-[13px] leading-6 text-sec" style={{ listStyle: 'disc' }}>{rules.map((t, i) => <li key={i}><FaText text={t} /></li>)}</ul>
        </section>
      ) : null}
    </div>
  );
}

// ======================================================================================== the session side ==
/** «تا اینجا»: what the session remembers (§40.1), Markdown, folded away until he wants it. */
export function MemoryCard({ md }: { md: string | null | undefined }) {
  const [open, setOpen] = useState(false);
  const text = (md ?? '').trim();
  return (
    <Card className="flex flex-col gap-2 p-4" aria-label="تا اینجا">
      <button type="button" aria-expanded={open} aria-controls="session-memory" onClick={() => setOpen(!open)} disabled={!text} className="flex items-center gap-2 text-start disabled:cursor-default">
        <Icon name="report" size={16} className="flex-none text-silver-ink" />
        <span className="flex-1 text-[14px] font-semibold">تا اینجا</span>
        {text ? <span className="text-[12px] text-muted">{open ? 'ببند' : 'بخوان'}</span> : null}
      </button>
      {text ? (
        open
          ? <div id="session-memory" className="tahrir"><Md text={text} className="flex flex-col gap-2 text-[13px] leading-6 text-sec" /></div>
          : <p id="session-memory" className="line-clamp-2 text-[12px] leading-5 text-muted">{text.replace(/[#*`>-]/g, '').replace(/\s+/g, ' ')}</p>
      ) : <p className="text-[12px] leading-5 text-muted">هنوز چیزی برای یادآوری نیست؛ با ادامه‌ی گفتگو جلسه خودش خلاصه‌اش را نگه میدارد.</p>}
    </Card>
  );
}

/** «کارگروه از این جلسه بساز» (§40.2): the holder drafts a playbook from the memory, the plan and what was done; its card lands in the chat. */
export function MakePlaybook({ order, onDone }: { order: string; onDone?: () => void }) {
  const draft = useDraftPlaybook(order);
  const toast = useToast();
  return (
    <Card className="flex flex-col gap-2 p-4" aria-label="کارگروه از این جلسه">
      <SectionTitle title="کارگروه" note="نتیجه‌ی این جلسه را به یک کارگروه تبدیل کن تا به شرکت‌ها و پلتفرم‌های دیگر هم بدهی" />
      <div>
        <Button variant="secondary" icon="companies" loading={draft.isPending}
          onClick={() => draft.mutate(undefined, {
            onSuccess: () => { toast({ tone: 'ok', text: 'پیش‌نویس کارگروه ساخته شد؛ کارتش در گفتگو آمد.' }); onDone?.(); },
            onError: (e) => toast({ tone: 'error', text: errText(e, 'ساخته نشد؛ دوباره بزن.') }),
          })}>کارگروه از این جلسه بساز</Button>
      </div>
    </Card>
  );
}

/** «از کارگروه …» in a session's header when it was opened from a playbook (§40.3 `source`). */
export function FromPlaybook({ refId }: { refId: string }) {
  const q = usePlaybook(refId);
  return (
    <Link href={`/playbooks/${encodeURIComponent(refId)}`} data-from-playbook className="inline-flex h-6 max-w-[16rem] flex-none items-center gap-1.5 rounded-full bg-[var(--hq-silver-soft)] px-2.5 text-[12px] font-semibold text-silver-ink hover:underline">
      <Icon name="companies" size={13} className="flex-none" /><span className="truncate">از کارگروه{q.data ? ` «${q.data.title_fa}»` : ''}</span>
    </Link>
  );
}

// ============================================================================================ the chat card ==
/** The `playbook` card in a talk (§40.2): the draft's title, platform, seats with their helpers, routines in plain times and rules; open it, seal it. */
export function PlaybookCard({ refId, fallback }: { refId: string; fallback: { title_fa: string; body_fa: string } }) {
  const q = usePlaybook(refId);
  const act = usePlaybookActions(refId);
  const toast = useToast();
  const pb = q.data;
  return (
    <section aria-label={`کارگروه: ${pb?.title_fa ?? fallback.title_fa}`} data-kind="playbook" data-state={pb?.state ?? 'offered'} className="flex flex-col gap-3 rounded-[14px] border border-div bg-tile p-3.5">
      <header className="flex flex-col gap-1">
        <span className="flex items-center gap-2 text-[12px] text-sec">
          <span className="flex-none text-silver-ink"><Icon name="companies" size={16} /></span>
          <span className="min-w-0 flex-1"><Facts>{'کارگروه از این جلسه'}{pb ? PLATFORM_FA[pb.platform] : null}</Facts></span>
          {pb ? <StateWord kind={STATE_KIND[pb.state]}>{PB_STATE_FA[pb.state].fa}</StateWord> : null}
        </span>
        <b className="text-[14px] leading-6 text-ink"><FaText text={pb?.title_fa ?? fallback.title_fa} /></b>
      </header>
      {pb ? <PlaybookBody pb={pb} compact /> : q.isLoading ? <Skeleton className="h-16 rounded-[10px]" /> : <FaPara text={fallback.body_fa} className="text-[13px] leading-6 text-sec" />}
      <footer className="flex flex-wrap gap-2">
        <Link href={`/playbooks/${encodeURIComponent(refId)}`} className="inline-flex h-8 items-center gap-1.5 rounded-[8px] border border-strong px-3 text-[12px] font-semibold text-ink hover:bg-hover"><Icon name="next" size={16} />باز کن</Link>
        {pb?.state === 'draft' ? (
          <Button size="sm" variant="secondary" icon="seal" loading={act.seal.isPending}
            onClick={() => act.seal.mutate(publishes(pb) ? { mode: 'auto' } : undefined, { onSuccess: (out) => toast({ tone: 'ok', text: sealedFa(out, publishes(pb)) }), onError: (e) => toast({ tone: 'error', text: errText(e, 'مُهر نشد.') }) })}>مُهر کن</Button>
        ) : null}
      </footer>
      {pb?.state === 'draft' && publishes(pb) ? <p className="text-[11px] leading-5 text-muted">با مُهر، از نوبت بعد خروجی هر روز خودکار منتشر میشود؛ در صفحه‌ی کارگروه میشود خاموشش کرد.</p> : null}
    </section>
  );
}

/** What the seal's toast says: the routines start, and whether each day's output goes out by itself (a hub before §45 does not know the word). */
const sealedFa = (out: Playbook, auto: boolean) => (!auto ? 'کارگروه مُهر شد.'
  : out.members?.some((m) => m.publish?.mode === 'auto') ? 'مُهر شد؛ از نوبت بعد خودش میسازد و خودکار منتشر میکند.'
  : 'مُهر شد. انتشار خودکار بعد از به‌روز شدن هاب روشن میشود؛ تا آن وقت هر خروجی منتظر تأیید تو است.');

// ====================================================================================== the standing word ==
/**
 * ⟨0.19.9⟩ §45 The owner's standing word, asked where he seals a working group or gives it to a company (his words, 2026-11-10:
 * «به صورت خودکار از روز دوم انجام بشه … نه اینکه هر بار من تایید کنم»). On: each day's package goes out by itself.
 */
export function StandingChoice({ value, onChange, company }: { value: MemberPublish; onChange: (v: MemberPublish) => void; company?: string | null }) {
  const auto = value.mode === 'auto';
  return (
    <div className="flex flex-col gap-2.5 rounded-[12px] bg-tile p-3" data-testid="standing">
      <div className="flex items-center gap-3">
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <b className="text-[14px] text-ink">انتشار خودکار</b>
          <span className="text-[11px] leading-5 text-muted">{auto ? 'خروجی هر روز بی تأیید تو منتشر میشود. هر وقت خواستی خاموشش کن.' : 'هر خروجی منتظر «تأیید و انتشار» تو میماند.'}</span>
        </span>
        <Switch checked={auto} onChange={(v) => onChange({ ...value, mode: v ? 'auto' : 'ask' })} label="انتشار خودکار" />
      </div>
      {auto ? (
        <div className="flex flex-wrap items-center gap-2">
          <FilterChip selected={!!value.story} onClick={() => onChange({ ...value, story: !value.story })}>استوری هم بشود</FilterChip>
          {/* ⟨0.20.0⟩ §46 the hour each day's package goes out at; empty: as soon as it is ready */}
          <input
            value={value.at ?? ''} onChange={(e) => onChange({ ...value, at: e.target.value.slice(0, 5) || null })} dir="ltr" inputMode="numeric" placeholder="ساعت انتشار، مثل 18:30" aria-label="ساعت انتشار"
            className="fig h-9 min-w-0 flex-1 rounded-[10px] border border-strong bg-tile px-3 text-center text-[13px] text-ink outline-none transition-colors placeholder:text-muted focus:border-[var(--hq-silver-ink)]"
          />
        </div>
      ) : null}
      {/* ⟨1.0.1⟩ §49 the account's best hour instead of a fixed one; the fixed hour above stays for until the hub knows it */}
      {auto ? <BestHourChoice company={company} value={value} onChange={onChange} /> : null}
    </div>
  );
}

/** The standing word in words: «خودکار | بهترین ساعت 19:00 | @account | استوری هم», or «هر بار بپرس». Every hour a Latin figure. */
function StandingLine({ p, hour }: { p: MemberPublish; hour: string | null }) {
  if (p.mode !== 'auto') return <>هر بار بپرس</>;
  const at = clockOf(p.at);
  return (
    <Facts>
      خودکار
      {p.best ? (hour ? <>بهترین ساعت <Ltr>{hour}</Ltr></> : 'بهترین ساعت') : null}
      {at && !(p.best && hour) ? <>{p.best ? 'تا آن وقت ساعت' : 'ساعت'} <Ltr>{at}</Ltr></> : null}
      {p.account ? <Ltr tabular={false}>@{p.account}</Ltr> : null}
      {p.story ? 'استوری هم' : null}
    </Facts>
  );
}

/** One member's standing word: a switch, his tap, no passkey. A company with several accounts is asked which one. */
function StandingRow({ group, company, value }: { group: string; company: string; value: MemberPublish | undefined }) {
  const toast = useToast();
  const set = useMemberPublish(group);
  const [picking, setPicking] = useState<string[]>([]);
  // ⟨0.20.0⟩ §46 its hour and «استوری هم», changed in place
  const [editing, setEditing] = useState<MemberPublish | null>(null);
  const cur: MemberPublish = value ?? { mode: 'ask' };
  // ⟨1.0.1⟩ §49 with «بهترین ساعت», the row says the hour once the hub knows it
  const best = useBestHour(company, cur.account, cur.mode === 'auto' && !!cur.best);
  const say = (next: MemberPublish) => set.mutate({ company, publish: next }, {
    onSuccess: (m) => { setPicking([]); setEditing(null); toast({ tone: 'ok', text: m.publish.mode === 'auto' ? 'از نوبت بعد خودکار منتشر میشود.' : 'از این به بعد هر خروجی منتظر تأیید تو است.' }); },
    onError: (e) => {
      const named = e instanceof ApiError && e.status === 422 ? accountsNamed(e.fields?.account) : [];
      if (named.length) setPicking(named);
      else toast({ tone: 'error', text: errText(e, 'انجام نشد؛ دوباره بزن.') });
    },
  });
  const badHour = !!editing && editing.mode === 'auto' && !!editing.at && !clockOf(editing.at);
  return (
    <div className={SETTING_ROW} data-standing={company}>
      <div className="flex items-center gap-3">
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="text-[13px] text-ink">انتشار خودکار</span>
          <span className={cx('text-[12px] leading-5', cur.mode === 'auto' ? 'text-sec' : 'text-muted')} data-standing-line><StandingLine p={cur} hour={bestHourOf(best.data)} /></span>
        </span>
        {cur.mode === 'auto' ? <button type="button" aria-expanded={!!editing} onClick={() => setEditing(editing ? null : cur)} className={QUIET_ACTION}>تنظیم</button> : null}
        <Switch checked={cur.mode === 'auto'} disabled={set.isPending} label={`انتشار خودکار ${company}`} onChange={(v) => say({ ...cur, mode: v ? 'auto' : 'ask' })} />
      </div>
      {editing ? (
        <div className="flex flex-col gap-2">
          <StandingChoice value={editing} onChange={setEditing} company={company} />
          {badHour ? <p className="text-[11px] text-muted">ساعت را به شکل ۱۸:۳۰ بنویسید.</p> : null}
          <Button variant="secondary" size="sm" className="self-start" disabled={badHour} loading={set.isPending} onClick={() => say(editing)}>ذخیره</Button>
        </div>
      ) : null}
      {picking.length ? (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[12px] text-sec">کدام حساب؟</span>
          {picking.map((a) => <FilterChip key={a} selected={false} onClick={() => say({ ...cur, mode: 'auto', account: a })}><Ltr tabular={false}>@{a}</Ltr></FilterChip>)}
        </div>
      ) : null}
    </div>
  );
}

// ================================================================================== give it to someone else ==
function ApplyDialog({ pb, open, onOpenChange }: { pb: Playbook; open: boolean; onOpenChange: (v: boolean) => void }) {
  const router = useRouter();
  const toast = useToast();
  const act = usePlaybookActions(pb.ref);
  const companies = useCompanies();
  const list = (companies.data ?? []).filter((c) => c.kind !== 'holding' && c.code !== 'HQ');
  const [company, setCompany] = useState('');
  const [platform, setPlatform] = useState<PlaybookPlatform>(pb.platform);
  const [note, setNote] = useState('');
  const [asIs, setAsIs] = useState(false);
  const sealed = pb.state === 'sealed';
  // ⟨0.19.9⟩ §45 with «بدون تغییر», his standing word for that company (as the group's first member has it)
  const [word, setWord] = useState<MemberPublish>({ mode: pb.members?.some((m) => m.publish?.mode === 'auto') ? 'auto' : 'ask', story: pb.members?.some((m) => m.publish?.story) });
  const standing = sealed && asIs && publishes(pb);
  const go = () => act.apply.mutate(
    { company, platform, note_fa: note.trim() || undefined, ...(sealed && asIs ? { as_is: true } : {}), ...(standing ? { publish: publishRule(word) } : {}) },
    {
      onSuccess: (r) => {
        onOpenChange(false);
        if (r.order) router.push(`/s/${encodeURIComponent(r.order)}`);
        else toast({ tone: 'ok', text: `${r.member?.name_fa ?? 'شرکت'} عضو کارگروه شد.` });
      },
      onError: (e) => toast({ tone: 'error', text: errText(e, 'داده نشد؛ دوباره بزن.') }),
    },
  );
  return (
    <SpringSheet open={open} onOpenChange={onOpenChange} title="به شرکت دیگر بده" width={480} testid="apply-sheet"
      bar={(
        <DecisionBar label="دادن کارگروه" context={asIs && sealed ? 'همین کارگروه، همان‌طور که هست، عضوی تازه میگیرد.' : 'مسئول آن شرکت جلسه‌ای تازه باز میکند و کارگروه را تطبیق میدهد.'}
          primary={{ label: asIs && sealed ? 'عضوش کن' : 'بده', onClick: go, disabled: !company }} quiet={[{ label: 'بعداً', onClick: () => onOpenChange(false) }]} state={act.apply.isPending ? 'working' : 'idle'} />
      )}>
      <div className="flex flex-col gap-3 pb-1">
        <label className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">شرکت</span>
          <select value={company} onChange={(e) => setCompany(e.target.value)} aria-label="شرکت" className={cx(INPUT, 'h-11')}>
            <option value="">انتخاب کن…</option>
            {list.map((c) => <option key={c.code} value={c.code}>{c.name_fa}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">پلتفرم</span>
          <select value={platform} onChange={(e) => setPlatform(e.target.value as PlaybookPlatform)} aria-label="پلتفرم" className={cx(INPUT, 'h-11')}>
            {PLATFORMS.map((p) => <option key={p} value={p}>{PLATFORM_FA[p]}</option>)}
          </select>
        </label>
        {sealed ? (
          <div className="flex items-center gap-3 text-[13px] text-ink"><span className="min-w-0 flex-1">بدون تغییر</span><Switch checked={asIs} onChange={setAsIs} label="بدون تغییر" /></div>
        ) : null}
        {standing ? <StandingChoice value={word} onChange={setWord} company={company || null} /> : null}
        {asIs && sealed
          ? <p className="text-[12px] leading-5 text-muted">جلسه‌ی تازه‌ای باز نمیشود.</p>
          : (
            <label className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">یادداشت برای مسئول (اختیاری)</span>
              <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} dir="auto" aria-label="یادداشت" placeholder="لحن، حساب‌ها، چیزی که باید فرق کند…" className={cx(INPUT, 'py-2 leading-6')} />
            </label>
          )}
      </div>
    </SpringSheet>
  );
}

// =============================================================================================== the page ==
function useCompanyName() {
  const { data } = useCompanies();
  return (code: string | null | undefined) => (code ? data?.find((c) => c.code === code)?.name_fa ?? code : null);
}

/** When the group's next routine runs (the soonest of its schedules). */
const soonest = (pb: Pick<Playbook, 'routines'>): string | null =>
  (pb.routines ?? []).map((r) => nextRun(r.schedule)).filter((x): x is string => !!x).sort()[0] ?? null;

/** The member companies as tiles: state, last run, next run, the work line, and each one's settings as one grouped block. */
function Members({ pb }: { pb: Playbook }) {
  const toast = useToast();
  const qc = useQueryClient();
  const members = pb.members ?? [];
  const sealed = pb.state === 'sealed' && !!pb.group;
  const runs = useGroupRunsLook(sealed ? pb.group : null);
  const act = useGroupActions(pb.group ?? '');
  const next = sealed ? soonest(pb) : null;
  const start = (company: string, nameFa: string) => act.member.mutate({ company, state: 'on' }, {
    // the working group's own page reads its members from the playbook: it is read again with the group
    onSuccess: () => { toast({ tone: 'ok', text: `کارگروه در ${nameFa} دوباره راه افتاد.` }); void qc.invalidateQueries({ queryKey: ['playbooks'] }); },
    onError: (e) => toast({ tone: 'error', text: errText(e, 'راه نیفتاد؛ دوباره بزن.') }),
  });
  return (
    <section className="flex flex-col gap-2.5" aria-label="شرکت‌های عضو">
      <SectionTitle title="شرکت‌های عضو" note={members.length ? undefined : 'هنوز شرکتی عضو نیست'} />
      {members.length ? (
        <ul className="grid items-start gap-3 lg:grid-cols-2">
          {members.map((m, i) => {
            const item = stagger(i);
            return (
              <li key={m.company} {...item} data-member={m.company} className={cx('flex min-w-0 flex-col gap-3 rounded-[16px] bg-card p-4', item.className)}>
                <MemberHead m={m} runs={sealed ? runs.data : undefined} next={m.state === 'on' ? next : null}
                  onStart={sealed ? () => start(m.company, m.name_fa) : undefined} starting={act.member.isPending && act.member.variables?.company === m.company}
                  action={m.order ? <QuietLink href={`/s/${encodeURIComponent(m.order)}`}>جلسه‌اش</QuietLink> : null} />
                {sealed ? (
                  // §45 his standing word, §48 who speaks for it, §47 what it already said: one block, each a row (nothing of a row the hub does not serve).
                  <div className="flex flex-col divide-y divide-[var(--hq-line-divider)] rounded-[12px] bg-tile px-3 empty:hidden" data-member-settings>
                    {publishes(pb) ? <StandingRow group={pb.group!} company={m.company} value={m.publish} /> : null}
                    <NarratorRow company={m.company} nameFa={m.name_fa} />
                    <LedgerRow group={pb.group!} company={m.company} nameFa={m.name_fa} />
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}

/** Each routine with when it runs, who does it, its last seven runs as dots and its next turn. */
function RoutineRuns({ pb }: { pb: Playbook }) {
  const routines = pb.routines ?? [];
  const runs = useGroupRunsLook(pb.state === 'sealed' ? pb.group : null);
  const live = pb.state === 'sealed' && (pb.members ?? []).some((m) => m.state === 'on');
  if (!routines.length) return null;
  return (
    <section className="flex flex-col gap-2.5" aria-label="روال‌ها و نوبت‌ها" data-testid="routine-runs">
      <SectionTitle title="روال‌ها" note={runs.data ? 'هفت نوبت آخر هر روال' : undefined} />
      <ul className="flex flex-col divide-y divide-[var(--hq-line-divider)] rounded-[16px] bg-card px-4">
        {routines.map((r) => {
          const next = live ? nextRun(r.schedule) : null;
          return (
            <li key={r.key} className="flex flex-col gap-1 py-3" data-routine-run={r.key}>
              <div className="flex items-center gap-3">
                <b className="min-w-0 flex-1 text-[14px] font-semibold leading-6 text-ink"><FaText text={r.title_fa} /></b>
                {runs.data ? <RunDots runs={runs.data.filter((x) => x.routine === r.key)} label={r.title_fa} /> : null}
              </div>
              <span className="text-[12px] leading-5 text-sec">
                <Facts><span className="fig">{whenFa(r.schedule)}</span>{seatTitle(pb, r.seat)}{next ? <>نوبت بعد <WhenAt iso={next} /></> : null}</Facts>
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** One playbook: every field; a draft can be edited lightly and sealed; a sealed one is given on and retired. */
export function PlaybookPage({ refId }: { refId: string }) {
  const q = usePlaybook(refId);
  if (q.isLoading) return <><Skeleton className="h-16 w-2/3" /><Skeleton className="mt-3 h-64 rounded-[16px]" /></>;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) {
    return (
      <>
        <PageHeader eyebrow={<Link href="/playbooks" className="hover:text-ink">کارگروه‌های آماده</Link>} title="کارگروه" />
        <Card><Empty icon="companies" title="این کارگروه پیدا نشد" body="یا هنوز ستاد به‌روز نشده، یا کارگروه دیگر نیست." action={<Link href="/playbooks" className={cx('text-[13px]', LINK)}>کتابخانه‌ی کارگروه‌ها</Link>} /></Card>
      </>
    );
  }
  // The page itself stays mounted across a save (its mutation callbacks must outlive the refetch); only the editor starts over from the new version.
  return <PlaybookView key={q.data.ref} pb={q.data} />;
}

function PlaybookView({ pb }: { pb: Playbook }) {
  const toast = useToast();
  const act = usePlaybookActions(pb.ref);
  const name = useCompanyName();
  const parent = usePlaybook(pb.parent);
  const [giving, setGiving] = useState(false);
  const [retiring, setRetiring] = useState(false);
  const draft = pb.state === 'draft';
  const st = PB_STATE_FA[pb.state];
  const [sealingNow, setSealingNow] = useState(false);
  const save = (diff: PlaybookPatch) => act.patch.mutate(diff, { onSuccess: () => toast({ tone: 'ok', text: 'ذخیره شد.' }), onError: (e) => toast({ tone: 'error', text: errText(e, 'ذخیره نشد.') }) });
  // ⟨0.19.9⟩ §45 his standing word, given with the seal: on, as he asked («به صورت خودکار از روز دوم انجام بشه»)
  const [word, setWord] = useState<MemberPublish>({ mode: 'auto' });
  const seal = (before?: PlaybookPatch) => {
    setSealingNow(true);
    const said = publishes(pb) ? word : undefined;
    const run = () => act.seal.mutate(said, { onSuccess: (out) => toast({ tone: 'ok', text: sealedFa(out, said?.mode === 'auto') }), onError: (e) => toast({ tone: 'error', text: errText(e, 'مُهر نشد.') }), onSettled: () => setSealingNow(false) });
    if (before) act.patch.mutate(before, { onSuccess: run, onError: (e) => { setSealingNow(false); toast({ tone: 'error', text: errText(e, 'ذخیره نشد.') }); } });
    else run();
  };
  return (
    <div className="mx-auto flex w-full max-w-[58rem] flex-col gap-4">
      <GroupHeader
        eyebrow={<Link href="/playbooks" className="hover:text-ink">کارگروه‌های آماده</Link>}
        title={<FaText text={pb.title_fa} />}
        state={<StateWord kind={STATE_KIND[pb.state]}>{st.fa}</StateWord>}
        facts={(
          <Facts>
            {PLATFORM_FA[pb.platform]}
            <Link href={`/s/${encodeURIComponent(pb.source.order)}`} className={LINK}>جلسه‌ای که از آن ساخته شد</Link>
            {pb.source.company ? `شرکت: ${name(pb.source.company)}` : null}
            {parent.data ? <Link href={`/playbooks/${encodeURIComponent(parent.data.ref)}`} className="hover:text-ink">نسخه‌ای از «{parent.data.title_fa}»</Link> : null}
            {`ساخته شد ${jDate(pb.created_at)}`}
            {pb.sealed_at ? `مُهر شد ${jDate(pb.sealed_at)}` : null}
            {pb.retired_at ? `بازنشسته شد ${jDate(pb.retired_at)}` : null}
          </Facts>
        )}
        actions={pb.state === 'sealed' ? (
          <>
            <Button variant="secondary" size="sm" icon="send" onClick={() => setGiving(true)}>به شرکت دیگر بده</Button>
            <Button variant="text" size="sm" onClick={() => setRetiring(true)}>بازنشسته کن</Button>
          </>
        ) : null}
      />
      {pb.note_fa ? <Card className="p-4" aria-label="یادداشت پیش‌نویس"><p className="text-[12px] leading-6 text-sec"><span className="font-semibold text-ink">چیزهایی که پیش‌نویس‌کننده کنار گذاشت: </span><FaText text={pb.note_fa} /></p></Card> : null}

      {draft ? (
        <DraftEditor key={pb.version} pb={pb} saving={act.patch.isPending && !sealingNow} sealing={sealingNow} onSave={save} onSeal={seal}
          standing={publishes(pb) ? <StandingChoice value={word} onChange={setWord} company={pb.source.company} /> : null} />
      ) : (
        <>
          <Members pb={pb} />
          <RoutineRuns pb={pb} />
          {/* What the working group is: read when he wants it, folded until then. */}
          <details className="group rounded-[16px] bg-card" data-testid="group-definition">
            <summary className="flex cursor-pointer select-none list-none items-center gap-2 px-4 py-3.5 text-[14px] font-semibold text-ink [&::-webkit-details-marker]:hidden">
              <span className="min-w-0 flex-1">تعریف کارگروه</span>
              <span className="text-[12px] font-normal text-muted"><SealSummary seats={pb.seats?.length ?? 0} routines={pb.routines?.length ?? 0} connections={pb.connections?.length ?? 0} /></span>
              <Icon name="next" size={16} className="flex-none -rotate-90 text-muted transition-transform group-open:rotate-90" />
            </summary>
            <div className="px-4 pb-4" aria-label="کارگروه"><PlaybookBody pb={pb} /></div>
          </details>
          {pb.group ? <Link href={`/groups/${encodeURIComponent(pb.group)}`} className={cx('self-start text-[12px]', LINK)}>شاخص‌ها و آزمایش هفته در «کارگروه‌ها»</Link> : null}
        </>
      )}

      <ApplyDialog pb={pb} open={giving} onOpenChange={setGiving} />
      <Dialog open={retiring} onOpenChange={setRetiring} title="این کارگروه بازنشسته شود؟"
        actions={(
          <>
            <Button variant="danger" icon="seal" loading={act.retire.isPending}
              onClick={() => act.retire.mutate(undefined, { onSuccess: () => { setRetiring(false); toast({ tone: 'info', text: 'کارگروه بازنشسته شد؛ روال‌هایش برای همه‌ی اعضا ایستاد.' }); }, onError: (e) => toast({ tone: 'error', text: errText(e, 'انجام نشد.') }) })}>بازنشسته کن</Button>
            <Button variant="ghost" onClick={() => setRetiring(false)}>نه</Button>
          </>
        )}>
        روال‌های این کارگروه برای همه‌ی شرکت‌های عضو میایستد. چیزی پاک نمیشود و دیگر نمیشود آن را به شرکت دیگری داد.
      </Dialog>
    </div>
  );
}

// ================================================================================================ the draft ==
function Area({ label, children }: { label: string; children: ReactNode }) {
  return <label className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">{label}</span>{children}</label>;
}

function DraftEditor({ pb, saving, sealing, onSave, onSeal, standing }: {
  pb: Playbook; saving: boolean; sealing: boolean; onSave: (diff: PlaybookPatch) => void; onSeal: (before?: PlaybookPatch) => void; standing?: ReactNode;
}) {
  const [title, setTitle] = useState(pb.title_fa);
  const [purpose, setPurpose] = useState(pb.purpose_fa);
  const [platform, setPlatform] = useState<PlaybookPlatform>(pb.platform);
  const [seats, setSeats] = useState<PlaybookSeat[]>(pb.seats ?? []);
  const [routines, setRoutines] = useState<PlaybookRoutine[]>(pb.routines ?? []);
  const [rules, setRules] = useState<string[]>(pb.rules_fa ?? []);

  const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
  const changes = (): PlaybookPatch => ({
    ...(title.trim() !== pb.title_fa ? { title_fa: title.trim() } : {}),
    ...(purpose !== pb.purpose_fa ? { purpose_fa: purpose } : {}),
    ...(platform !== pb.platform ? { platform } : {}),
    ...(!same(seats, pb.seats ?? []) ? { seats } : {}),
    ...(!same(routines, pb.routines ?? []) ? { routines } : {}),
    ...(!same(rules.map((r) => r.trim()).filter(Boolean), pb.rules_fa ?? []) ? { rules_fa: rules.map((r) => r.trim()).filter(Boolean) } : {}),
  });
  const diff = changes();
  const dirty = Object.keys(diff).length > 0;
  const bad = !title.trim();
  const dropSeat = (key: string) => {
    setSeats((x) => x.filter((s) => s.seat !== key));
    setRoutines((x) => x.filter((r) => r.seat !== key));
  };

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-3 p-5" aria-label="عنوان و هدف">
        <Area label="عنوان"><input value={title} onChange={(e) => setTitle(e.target.value)} dir="auto" aria-label="عنوان" maxLength={200} className={cx(INPUT, 'h-11')} /></Area>
        <Area label="هدف"><textarea value={purpose} onChange={(e) => setPurpose(e.target.value)} rows={3} dir="auto" aria-label="هدف" maxLength={2000} className={cx(INPUT, 'py-2 leading-6')} /></Area>
        <div className="flex flex-col gap-1.5" role="radiogroup" aria-label="پلتفرم">
          <span className="text-[12px] text-sec">پلتفرم</span>
          <div className="flex flex-wrap gap-1.5">{PLATFORMS.map((p) => <FilterChip key={p} selected={platform === p} onClick={() => setPlatform(p)}>{PLATFORM_FA[p]}</FilterChip>)}</div>
        </div>
      </Card>

      <Card className="flex flex-col gap-2 p-5" aria-label="جایگاه‌ها">
        <SectionTitle title="چه کسانی" note={seats.length ? 'هر کدام را که نمیخواهی بردار' : 'جایگاهی نمانده'} />
        <ul className="flex flex-col gap-1.5">
          {seats.map((s) => (
            <li key={s.seat} className="flex flex-wrap items-center gap-x-2.5 gap-y-1 rounded-[10px] bg-tile px-3 py-2" data-seat={s.seat}>
              <span className="min-w-0 flex-1"><span className="text-[13px] font-semibold"><FaText text={s.title_fa} /></span>{s.duties_fa ? <span className="block text-[12px] leading-5 text-sec"><FaText text={s.duties_fa} /></span> : null}</span>
              <HelperChips helpers={s.helpers} />
              <IconButton icon="close" size={32} label={`${s.title_fa} را بردار`} onClick={() => dropSeat(s.seat)} />
            </li>
          ))}
        </ul>
      </Card>

      <Card className="flex flex-col gap-2 p-5" aria-label="روال‌ها">
        <SectionTitle title="چه کاری، کِی" note={routines.length ? 'شرح هر کار را میتوانی عوض کنی' : 'روالی نمانده'} />
        <ul className="flex flex-col gap-2">
          {routines.map((r, i) => (
            <li key={r.key} className="flex flex-col gap-1.5 rounded-[10px] bg-tile p-3" data-routine={r.key}>
              <div className="flex items-start gap-2 text-[13px]">
                <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <b className="font-semibold"><FaText text={r.title_fa} /></b>
                  <span className="text-[12px] text-sec"><Facts><span className="fig">{whenFa(r.schedule)}</span>{seatTitle({ seats }, r.seat)}</Facts></span>
                </span>
                <IconButton icon="close" size={32} label={`${r.title_fa} را بردار`} onClick={() => setRoutines((x) => x.filter((y) => y.key !== r.key))} />
              </div>
              <textarea value={r.brief_md} onChange={(e) => setRoutines((x) => x.map((y, j) => (j === i ? { ...y, brief_md: e.target.value } : y)))} rows={3} dir="auto" aria-label={`شرح ${r.title_fa}`} className={cx(INPUT, 'bg-page py-2 text-[13px] leading-6')} />
            </li>
          ))}
        </ul>
      </Card>

      <Card className="flex flex-col gap-2 p-5" aria-label="قانون‌ها">
        <SectionTitle title="قانون‌ها" action={<Button size="sm" icon="add" onClick={() => setRules((x) => [...x, ''])}>قانون تازه</Button>} />
        <ul className="flex flex-col gap-1.5">
          {rules.map((t, i) => (
            <li key={i} className="flex items-center gap-2">
              <input value={t} onChange={(e) => setRules((x) => x.map((y, j) => (j === i ? e.target.value : y)))} dir="auto" aria-label={`قانون ${i + 1}`} className={cx(INPUT, 'h-11 min-w-0 flex-1')} />
              <IconButton icon="close" size={32} label={`قانون ${i + 1} را بردار`} onClick={() => setRules((x) => x.filter((_, j) => j !== i))} />
            </li>
          ))}
        </ul>
        {!rules.length ? <p className="text-[12px] text-muted">قانونی نیست.</p> : null}
      </Card>

      {pb.kpis?.length || pb.connections?.length ? (
        <Card className="p-5" aria-label="شاخص‌ها و اتصال‌ها"><PlaybookBody pb={{ ...pb, purpose_fa: '', seats: [], routines: [], rules_fa: [] }} /></Card>
      ) : null}

      {standing}

      {/* «مُهر کارگروه»: the page's one act, in its decision bar with what the seal starts in one line. One tap, no fingerprint. */}
      <DecisionBar place="page" label="مُهر کارگروه"
        context={<Facts><SealSummary seats={seats.length} routines={routines.length} connections={pb.connections?.length ?? 0} />{dirty ? 'مُهر اول تغییرهایت را ذخیره میکند' : 'با مُهر، روال‌ها شروع میشوند'}</Facts>}
        primary={{ label: 'مُهر کارگروه', onClick: () => onSeal(dirty ? diff : undefined), disabled: bad || saving }} state={sealing ? 'working' : 'idle'}
        quiet={[{ label: 'ذخیره', onClick: () => onSave(diff), disabled: !dirty || bad || saving }]} />
    </div>
  );
}

// ============================================================================================= the library ==
const GROUPS: Array<{ state: PlaybookState; title: string }> = [
  { state: 'draft', title: 'پیش‌نویس، منتظر مُهر تو' }, { state: 'sealed', title: 'مُهر شده' }, { state: 'retired', title: 'بازنشسته' },
];

/** Every playbook, grouped by state: title, platform, how many companies use it, and the company it came from. */
export function PlaybookLibrary() {
  const q = usePlaybooks();
  const name = useCompanyName();
  if (q.isLoading) return <div className="flex flex-col gap-3">{Array.from({ length: 3 }, (_, i) => <Skeleton key={i} className="h-16 rounded-[14px]" />)}</div>;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (q.data === null) return <Card><Empty icon="companies" title="کارگروه‌های آماده بعد از به‌روزرسانی ستاد میایند" /></Card>;
  const all = q.data ?? [];
  if (!all.length) return <Card><Empty icon="companies" title="هنوز کارگروهی ساخته نشده" body="از داخل یک جلسه‌ی کامل، «کارگروه از این جلسه بساز» را بزن تا نتیجه‌اش به کارگروهی تبدیل شود که به هر شرکت و پلتفرم میدهی." /></Card>;
  return (
    <div className="flex flex-col gap-6">
      {GROUPS.map((g) => {
        const rows = all.filter((p) => p.state === g.state);
        if (!rows.length) return null;
        return (
          <section key={g.state} className="flex flex-col gap-2" aria-label={g.title} data-state={g.state}>
            <SectionTitle title={g.title} note={`${faCount(rows.length)} کارگروه`} />
            <ul className="flex flex-col gap-2">
              {rows.map((p, i) => {
                const item = stagger(i);
                return (
                  <li key={p.ref} {...item}>
                    <Link href={`/playbooks/${encodeURIComponent(p.ref)}`} data-playbook className={cx('flex items-center gap-3 rounded-[14px] bg-card px-4 py-3 hover:bg-hover', g.state === 'draft' && 'hq-edge')}>
                      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                        <span className="text-[14px] font-semibold leading-6 text-ink"><FaText text={p.title_fa} /></span>
                        <span className="text-[12px] leading-5 text-sec"><Facts>{PLATFORM_FA[p.platform]}{`${faCount(p.members?.length ?? 0)} شرکت عضو`}{p.source.company ? `از ${name(p.source.company)}` : null}</Facts></span>
                      </span>
                      <Icon name="next" size={16} mirror className="flex-none text-muted" />
                    </Link>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
