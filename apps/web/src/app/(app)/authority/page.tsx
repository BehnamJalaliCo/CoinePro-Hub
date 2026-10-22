'use client';

import { useMemo, useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Dialog } from '@/components/ui/overlay';
import { Card, ErrorState, FilterChip, PageHeader, Pill, SectionTitle, Skeleton, Switch } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { Prose } from '@/components/v16/bits';
import { ACTOR_ROLE_FA, WEEKDAY_FA } from '@/components/v17/bits';
import { faError, limitNumber, useAuthority, useAuthorityAction, type AuthorityChange, type AuthorityRule, type Limit, type Weekday } from '@/lib/api/v17';
import { cx, tokens, usd } from '@/lib/format';

const UNIT: Record<string, string> = { tokens_month: 'توکن در ماه', usd: 'دلار', count_day: 'در روز', count_hour: 'در ساعت', items: 'کارت' };
const DAYS: Weekday[] = ['SA', 'SU', 'MO', 'TU', 'WE', 'TH', 'FR'];
const field = 'h-9 w-28 rounded-[10px] border border-strong bg-tile px-2 text-[13px] text-ink outline-none focus:border-gold-ink';
const limitFa = (l: Limit | null) => {
  const n = limitNumber(l);
  if (n) return n.key === 'usd' ? usd(n.value) : n.key === 'tokens_month' ? `${tokens(n.value)} ${UNIT[n.key]}` : `${n.value} ${UNIT[n.key]}`;
  if (l?.days) return l.days.map((d) => WEEKDAY_FA[d] ?? d).join('، ');
  return '—';
};
const CLASS_TONE: Record<string, 'neutral' | 'lapis' | 'warn' | 'neg' | 'gold'> = { A0: 'neutral', A1: 'lapis', A2: 'gold', A3: 'warn', A4: 'neg' };

function Row({ r, draft, onChange }: { r: AuthorityRule; draft: AuthorityChange | undefined; onChange: (c: AuthorityChange | null) => void }) {
  const limit = draft ? draft.limit : r.limit;
  const actor = draft?.actor ?? r.actor;
  const num = limitNumber(limit);
  const out = !!num && !!r.bounds && (num.value < r.bounds.min || num.value > r.bounds.max);
  const set = (p: Partial<AuthorityChange>) => {
    const next = { key: r.key, version: r.version, limit, ...(actor !== r.actor ? { actor } : {}), ...p };
    const same = JSON.stringify(next.limit) === JSON.stringify(r.limit) && (next.actor ?? r.actor) === r.actor;
    onChange(same ? null : next);
  };
  return (
    <li className={cx('grid grid-cols-1 gap-x-4 gap-y-2 border-t border-div py-3 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_minmax(0,1.6fr)_auto]', draft && 'bg-gold-soft/40')}>
      <span className="flex min-w-0 flex-col gap-0.5">
        <span className="text-[14px] font-semibold text-ink"><Prose text={r.title_fa} /></span>
        <span className="fig text-[11px] text-muted">{r.key} · {r.action}</span>
        {r.note_fa ? <span className="text-[12px] leading-5 text-sec"><Prose text={r.note_fa} /></span> : null}
      </span>
      <span className="flex flex-wrap items-center gap-2 text-[12px] text-sec">
        <span>{ACTOR_ROLE_FA[actor] ?? actor}</span><span className="text-muted">·</span><span>{r.scope === 'holding' ? 'هلدینگ' : 'شرکت خودش'}</span>
        {r.actor !== 'owner' ? <label className="flex items-center gap-1.5 text-[11px] text-muted"><Switch checked={actor === 'owner'} onChange={(v) => set({ actor: v ? 'owner' : r.actor })} label={`فقط با تو: ${r.title_fa}`} />فقط با تو</label> : null}
      </span>
      <span className="flex flex-wrap items-center gap-2">
        {num ? (
          <>
            <input inputMode="decimal" dir="ltr" value={String(num.value)} aria-label={`مقدار ${r.title_fa}`} aria-invalid={out}
              onChange={(e) => set({ limit: { ...limit, [num.key]: Number(e.target.value.replace(/[^\d.]/g, '') || 0) } })} className={cx(field, 'fig', out && 'border-[var(--hq-neg-line)]')} />
            <span className="text-[12px] text-muted">{UNIT[num.key]}</span>
            {r.bounds ? <span className={cx('text-[11px]', out ? 'text-neg' : 'text-muted')}>بین <span className="fig">{r.bounds.min.toLocaleString('en-US')}</span> و <span className="fig">{r.bounds.max.toLocaleString('en-US')}</span></span> : null}
          </>
        ) : limit?.days ? (
          <span className="flex flex-wrap gap-1.5">{DAYS.map((d) => { const on = limit.days!.includes(d); return <FilterChip key={d} selected={on} onClick={() => set({ limit: { ...limit, days: on ? limit.days!.filter((x) => x !== d) : [...limit.days!, d] } })}>{WEEKDAY_FA[d]}</FilterChip>; })}</span>
        ) : <span className="text-[12px] text-muted">بی‌سقف عددی</span>}
      </span>
      <span className="flex items-center gap-2">
        <Pill tone={CLASS_TONE[r.class] ?? 'neutral'} className="h-5 text-[11px]"><span className="fig">{r.class}</span></Pill>
        {r.step_up ? <span className="text-gold-ink" title="با اثر انگشت"><Icon name="seal" size={16} /></span> : null}
      </span>
    </li>
  );
}

/** ماتریس اختیار (contract §20.7): rows OPA reads as data; the locked invariants hold whatever the data says. */
export default function AuthorityPage() {
  const q = useAuthority();
  const save = useAuthorityAction();
  const toast = useToast();
  const [drafts, setDrafts] = useState<Record<string, AuthorityChange>>({});
  const [confirm, setConfirm] = useState(false);
  const rules = useMemo(() => q.data ?? [], [q.data]);
  const open = rules.filter((r) => !r.locked);
  const locked = rules.filter((r) => r.locked);
  const changes = Object.values(drafts);
  const bad = changes.some((c) => { const r = rules.find((x) => x.key === c.key); const n = limitNumber(c.limit); return !!r?.bounds && !!n && (n.value < r.bounds.min || n.value > r.bounds.max); });
  const run = () => save.mutateAsync(changes).then(() => { toast({ tone: 'ok', text: 'ماتریس اختیار مُهر و ذخیره شد؛ OPA از همین لحظه عدد تازه را اجرا میکند.' }); setDrafts({}); setConfirm(false); }).catch((e) => toast({ tone: 'error', text: faError(e) }));
  return (
    <>
      <PageHeader eyebrow="قاعده‌ها داده‌اند و OPA میخواندشان؛ ثابت‌های قفل مستقل از داده‌اند" title="ماتریس اختیار"
        actions={<Button variant="primary" icon="seal" disabled={!changes.length || bad} onClick={() => setConfirm(true)}>ذخیره{changes.length ? <span className="fig"> ({changes.length})</span> : null}</Button>}>
        <p className="max-w-3xl text-[13px] leading-6 text-sec">فقط ردیف‌های باز و فقط داخل محدوده‌ی هر ردیف عوض میشوند؛ ذخیره با اثر انگشت روی همین تغییرهای دقیق است. ایجنت‌ها ماتریس را نمیتوانند عوض کنند و فقط با کارت «تغییر ماتریس اختیار» پیشنهاد میدهند.</p>
      </PageHeader>
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !q.data ? <Skeleton className="h-96" /> : (
        <>
          <Card className="flex flex-col p-4 md:p-5">
            <SectionTitle title="ردیف‌های باز" note="سقف‌ها، سهمیه‌ها و این‌که چه کسی تأیید میکند" />
            <ul className="mt-2 flex flex-col">{open.map((r) => <Row key={r.key} r={r} draft={drafts[r.key]} onChange={(c) => setDrafts((d) => { const n = { ...d }; if (c) n[r.key] = c; else delete n[r.key]; return n; })} />)}</ul>
          </Card>
          <Card className="flex flex-col gap-2 p-4 md:p-5">
            <SectionTitle title="ثابت‌های قفل" note="در کد، مستقل از داده؛ هیچ ذخیره‌ای عوضشان نمیکند" />
            <ul className="grid gap-2 md:grid-cols-2">
              {locked.map((r) => (
                <li key={r.key} className="flex items-start gap-3 rounded-[12px] bg-tile p-3">
                  <span className="mt-0.5 text-neg"><Icon name="lock" size={16} /></span>
                  <span className="flex min-w-0 flex-1 flex-col gap-0.5"><span className="text-[13px] font-semibold text-ink"><Prose text={r.title_fa} /></span>{r.note_fa ? <span className="text-[12px] leading-5 text-sec"><Prose text={r.note_fa} /></span> : null}<span className="fig text-[11px] text-muted">{r.key}</span></span>
                  <Pill tone={CLASS_TONE[r.class] ?? 'neutral'} className="h-5 text-[11px]"><span className="fig">{r.class}</span></Pill>
                </li>
              ))}
            </ul>
          </Card>
        </>
      )}
      <Dialog open={confirm} onOpenChange={setConfirm} title="ذخیره‌ی ماتریس اختیار" actions={<>
        <Button variant="primary" icon="seal" loading={save.isPending} onClick={() => void run()}>مُهر با passkey</Button>
        <Button variant="secondary" onClick={() => setConfirm(false)}>انصراف</Button>
      </>}>
        <div className="flex flex-col gap-2">
          <span>این ردیف‌ها عوض میشوند:</span>
          <ul className="flex flex-col gap-1.5">
            {changes.map((c) => { const r = rules.find((x) => x.key === c.key); return <li key={c.key} className="flex flex-wrap items-center gap-2 text-[13px]"><span className="text-ink">{r?.title_fa}</span><span className="text-muted line-through">{limitFa(r?.limit ?? null)}</span><span className="font-semibold text-ink">{limitFa(c.limit)}</span>{c.actor ? <span className="text-gold-ink">فقط با تو</span> : null}</li>; })}
          </ul>
        </div>
      </Dialog>
    </>
  );
}
