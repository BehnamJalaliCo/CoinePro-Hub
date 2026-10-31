'use client';

// ⟨1.10⟩ §28.3 دیده‌بان: an intelligence beyond the CEOs watching the apps, the hub and every company. The overseer's daily security
// sweep and app-health check and its weekly code review, the advisor's weekly growth memo and the digital CEO's monthly «پیشنهاد هلدینگ»
// arrive as findings on the same `/oversight/findings`, grouped by what they watch, each with its severity and the proposed fix.
// «تأیید اصلاح» opens the card or the Code Workshop session that waits for the owner's seal, or, when the fix is only words, gives it to
// the company as a work item at the finding's priority (the Android app does the same).

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useMemo, useState } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { Sentinel } from '@/components/brand/avatar';
import { Button } from '@/components/ui/button';
import { Md } from '@/components/ui/md';
import { Card, Empty, ErrorState, FilterChip, Pill, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { SEVERITY, SeverityPill } from '@/components/v14/bits';
import { ScopeChips } from '@/components/v17/bits';
import { ApiError } from '@/lib/api/client';
import { useCompanies } from '@/lib/api/hooks';
import { WATCH_GROUPS, bySeverity, fixText, isOpenFinding, useApproveFix, useWatch, type WatchGroup, type WatchItem } from '@/lib/api/v28';
import { ACTOR_FA } from '@/lib/labels';
import { ago, cx } from '@/lib/format';

const fa = (n: number) => n.toLocaleString('fa-IR');
const STATUS_FA: Record<string, { fa: string; tone: 'neutral' | 'gold' | 'pos' | 'neg' | 'lapis' }> = {
  open: { fa: 'باز', tone: 'neg' }, acknowledged: { fa: 'پذیرفته', tone: 'lapis' }, fixing: { fa: 'در حال اصلاح', tone: 'gold' }, fixed: { fa: 'اصلاح شد، منتظر تأیید', tone: 'pos' },
  verified: { fa: 'تأیید رفع', tone: 'pos' }, disputed: { fa: 'مورد اختلاف', tone: 'neutral' }, closed: { fa: 'بسته', tone: 'neutral' },
};
const FIX_KIND = { work: 'کار', workshop: 'جلسه‌ی کارگاه کد', decision: 'کارت تصمیم' } as const;

function FixBox({ f }: { f: WatchItem }) {
  const approve = useApproveFix();
  const router = useRouter();
  const toast = useToast();
  const words = fixText(f);
  if (!words && !f.fix?.ref) return null;
  const advice = f.group === 'growth' || f.group === 'holding';
  const live = isOpenFinding(f);
  const go = async () => {
    try {
      const out = await approve.mutateAsync(f);
      if (out.made) toast({ tone: 'ok', text: <>اصلاح به <span className="fig">{out.made}</span> سپرده شد؛ مرحله‌به‌مرحله در «فرمان‌های من».</> });
      router.push(out.route);
    } catch (e) {
      toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'ثبت نشد.' });
    }
  };
  return (
    <div className="flex flex-col gap-2 rounded-[12px] bg-gold-soft p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Icon name="edit" size={14} className="text-gold-ink" />
        <span className="flex-1 text-[12px] font-semibold text-gold-ink">{advice ? 'پیشنهاد' : 'اصلاح پیشنهادی'}</span>
        {f.fix ? <Pill tone="neutral" icon={f.fix.kind === 'workshop' ? 'code' : f.fix.kind === 'decision' ? 'decision' : 'task'}>{FIX_KIND[f.fix.kind] ?? f.fix.kind}</Pill> : null}
        {f.fix?.ref ? <span className="fig text-[11px] text-gold-ink">{f.fix.ref}</span> : null}
      </div>
      {words ? <Md text={words} className="flex flex-col gap-1 text-[13px] leading-6 text-ink" /> : null}
      {live ? (
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="primary" size="sm" icon="seal" loading={approve.isPending} onClick={go}>تأیید اصلاح</Button>
          <span className="text-[11px] text-muted">{f.fix?.ref ? 'کارت یا جلسه‌اش باز میشود تا همان‌جا مُهر کنی' : 'به‌صورت کار به شرکت سپرده میشود'}</span>
        </div>
      ) : null}
    </div>
  );
}

function FindingCard({ f, companyFa }: { f: WatchItem; companyFa: string }) {
  const [more, setMore] = useState(false);
  const st = STATUS_FA[f.status] ?? { fa: f.status, tone: 'neutral' as const };
  const long = f.body_md.length > 220;
  return (
    <article className={cx('flex flex-col gap-2.5 rounded-[14px] border p-3.5', f.severity === 'critical' && isOpenFinding(f) ? 'border-[var(--hq-neg-line)]' : 'border-div')} aria-label={f.title_fa}>
      <div className="flex flex-wrap items-center gap-2">
        <SeverityPill s={f.severity} />
        <span className="inline-flex items-center gap-1.5 text-[12px] text-sec"><CompanyMark code={f.company} height={12} mono />{companyFa}</span>
        <Pill tone={st.tone} dot>{st.fa}</Pill>
        <span className="flex-1" />
        <span className="fig text-[11px] text-muted">{f.ref}</span>
      </div>
      <h4 className="text-[14px] font-semibold leading-6 text-ink">{f.title_fa}</h4>
      {f.body_md ? (
        <>
          <div className={cx('relative', !more && long && 'max-h-[4.5rem] overflow-hidden')}>
            <Md text={f.body_md} className="flex flex-col gap-1 text-[13px] leading-6 text-sec" />
            {!more && long ? <span className="pointer-events-none absolute inset-x-0 bottom-0 h-6" style={{ background: 'linear-gradient(to top, var(--hq-surface-card), transparent)' }} /> : null}
          </div>
          {long ? <button type="button" onClick={() => setMore(!more)} className="self-start text-[12px] font-semibold text-gold-ink hover:underline">{more ? 'کمتر' : 'بیشتر'}</button> : null}
        </>
      ) : null}
      <FixBox f={f} />
      <span className="text-[11px] text-muted">{ago(f.opened_at)}{f.protocol ? <> · <span className="fig">{f.protocol}</span></> : null}{f.answerable ? <> · پاسخگو: {ACTOR_FA(f.answerable)}</> : null}</span>
    </article>
  );
}

export function WatchBoard() {
  const q = useWatch();
  const { data: companies } = useCompanies();
  const [group, setGroup] = useState<WatchGroup | null>(null);
  const [open, setOpen] = useState(true);
  const [company, setCompany] = useState<string | null>(null);
  const companyFa = (code: string) => companies?.find((c) => c.code === code)?.name_fa ?? code;
  const items = useMemo(() => (q.data ?? []).filter((f) => (!open || isOpenFinding(f)) && (!company || f.company === company)).sort(bySeverity), [q.data, open, company]);
  if (q.isLoading) return <div className="flex flex-col gap-4"><Skeleton className="h-28 rounded-[16px]" /><Skeleton className="h-72 rounded-[16px]" /></div>;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const groups = WATCH_GROUPS.map((g) => ({ ...g, list: items.filter((f) => f.group === g.key) }));
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5" role="group" aria-label="گروه‌های دیده‌بان">
        {groups.map((g) => {
          const worst = g.list[0]?.severity;
          const on = group === g.key;
          return (
            <button key={g.key} type="button" aria-pressed={on} onClick={() => setGroup(on ? null : g.key)} className="min-w-0 rounded-[16px] text-start">
              <Card className={cx('flex h-full flex-col gap-1.5 p-3.5 transition-colors hover:bg-hover', on && 'ring-1 ring-[var(--hq-gold-ink)]')}>
                <span className="flex items-center gap-2">
                  <span className={cx('flex size-8 flex-none items-center justify-center rounded-[10px]', worst === 'critical' || worst === 'high' ? 'bg-neg-soft text-neg' : 'bg-tile text-silver-ink')}><Icon name={g.icon} size={16} /></span>
                  <span className="min-w-0 flex-1 truncate text-[13px] font-semibold">{g.fa}</span>
                  <span className="text-[18px] font-semibold">{fa(g.list.length)}</span>
                </span>
                <span className="line-clamp-2 text-[11px] text-muted">{worst ? `بدترین: ${SEVERITY[worst].fa}` : 'چیزی باز نیست'} · {g.who}</span>
              </Card>
            </button>
          );
        })}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <FilterChip selected={open} onClick={() => setOpen(true)}>باز</FilterChip>
        <FilterChip selected={!open} onClick={() => setOpen(false)}>همه</FilterChip>
        <span className="mx-1 h-5 w-px bg-div" />
        <ScopeChips value={company} onChange={setCompany} />
      </div>
      {!items.length && !group ? (
        <Card className="p-5"><Empty icon="seal" title={open ? 'یافته‌ی بازی نیست' : 'هنوز یافته‌ای نیست'} body="پایش امنیت و سلامت اپ هر روز، بازبینی کد و یادداشت رشد هر هفته، و پیشنهاد هلدینگ هر ماه این‌جا میایند." /></Card>
      ) : groups.filter((g) => (group ? g.key === group : g.list.length > 0)).map((g) => (
        <Card key={g.key} as="section" className="flex flex-col gap-3 p-4" aria-label={g.fa}>
          <SectionTitle title={<span className="inline-flex items-center gap-2"><Icon name={g.icon} size={18} />{g.fa}</span>} note={g.rhythm} />
          {g.list.length ? <div className="flex flex-col gap-3">{g.list.map((f) => <FindingCard key={f.ref} f={f} companyFa={companyFa(f.company)} />)}</div>
            : <p className="py-2 text-[13px] text-muted">{open ? 'یافته‌ی بازی نیست.' : 'یافته‌ای نیست.'}</p>}
        </Card>
      ))}
    </div>
  );
}

/** The home page's card, shown only while something is open: the count by group and the most serious finding. */
export function HomeWatchCard() {
  const q = useWatch();
  const open = (q.data ?? []).filter(isOpenFinding).sort(bySeverity);
  if (!open.length) return null;
  const top = open[0]!;
  const serious = open.filter((f) => f.severity === 'critical' || f.severity === 'high').length;
  return (
    <Card className={cx('flex flex-col gap-3 p-4', serious > 0 && 'ring-1 ring-[var(--hq-neg-line)]')}>
      <SectionTitle title={<span className="inline-flex items-center gap-2"><Sentinel size={24} state="working" />دیده‌بان</span>}
        note={serious ? <span className="text-neg">{fa(serious)} یافته‌ی جدی</span> : `${fa(open.length)} یافته‌ی باز`}
        action={<Link href="/watch" className="inline-flex h-8 items-center gap-1 rounded-[8px] px-3 text-[12px] font-semibold text-gold-ink hover:bg-gold-soft">همه<Icon name="next" size={16} /></Link>} />
      <div className="flex flex-wrap gap-2">
        {WATCH_GROUPS.map((g) => {
          const list = open.filter((f) => f.group === g.key);
          if (!list.length) return null;
          const bad = list.some((f) => f.severity === 'critical' || f.severity === 'high');
          return <Pill key={g.key} tone={bad ? 'neg' : 'neutral'} icon={g.icon}>{g.fa} {fa(list.length)}</Pill>;
        })}
      </div>
      <Link href="/watch" className="flex items-start gap-2 rounded-[12px] bg-tile p-3 hover:bg-hover">
        <SeverityPill s={top.severity} />
        <span className="min-w-0 flex-1 text-[13px] leading-6 text-ink">{top.title_fa}</span>
        <CompanyMark code={top.company} height={12} mono />
      </Link>
    </Card>
  );
}
