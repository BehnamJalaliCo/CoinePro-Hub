'use client';

import { useMemo, useState, type ReactNode } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { SealButton } from '@/components/cartable/seal-button';
import { Button } from '@/components/ui/button';
import { Md } from '@/components/ui/md';
import { Sheet } from '@/components/ui/overlay';
import { Empty, Pill, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { useCompanies } from '@/lib/api/hooks';
import {
  batchReasons, faError, useAuthority, useBatchSeal, useBatchable, useObjective, useOutcomes,
  type Claim, type Decision, type Expected, type RedLine,
} from '@/lib/api/v17';
import { DECISION_KIND } from '@/lib/labels';
import { cx, jDate, tokens, usd } from '@/lib/format';
import { Diff, KNOWLEDGE_KIND, LAYER_FA, RefChip, VERDICT, VOTE_FA, kpiFig } from './bits';

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-1.5">
      <h3 className="text-[12px] font-semibold text-gold-ink">{title}</h3>
      {children}
    </section>
  );
}
function Fact({ label, children, mono }: { label: string; children: ReactNode; mono?: boolean }) {
  return (
    <div className="flex min-w-0 flex-col gap-1 rounded-[12px] bg-tile p-3">
      <span className="text-[11px] text-muted">{label}</span>
      <span className={cx('min-w-0 break-words text-[14px] font-semibold text-ink', mono && 'fig')}>{children}</span>
    </div>
  );
}

const BATCH_REASON: Record<string, string> = {
  changed: 'کارت بعد از انتخاب عوض شد', not_pending: 'دیگر منتظر مُهر نیست', kind: 'این نوع کارت گروهی مُهر نمیشود', action_class: 'کلاس اقدامش A1 نیست', risk: 'ریسکش کم نیست',
  irreversible: 'برگشت‌ناپذیر است', amended: 'اصلاحیه دارد', over_max_usd: 'از سقف دلاری مُهر گروهی بیشتر است', over_max_items: 'از سقف تعداد مُهر گروهی بیشتر است', held: 'ناظر نگهش داشته', not_found: 'پیدا نشد',
};

// ----------------------------------------------------------------- batch seal (§20.10) --
/** «مُهر گروهی»: several low-risk A1 cards, one passkey bound to the exact set; all or nothing. */
export function BatchSeal() {
  const q = useBatchable();
  const [open, setOpen] = useState(false);
  const n = q.data?.length ?? 0;
  if (!n) return null;
  return (
    <>
      <Button variant="silver" size="sm" icon="seal" onClick={() => setOpen(true)}>مُهر گروهی ({n.toLocaleString('fa-IR')})</Button>
      {open ? <BatchSheet onClose={() => setOpen(false)} /> : null}
    </>
  );
}

function BatchSheet({ onClose }: { onClose: () => void }) {
  const q = useBatchable();
  const auth = useAuthority();
  const seal = useBatchSeal();
  const toast = useToast();
  const { data: companies } = useCompanies();
  const holding = companies?.find((c) => c.kind === 'holding');
  const list = useMemo(() => q.data ?? [], [q.data]);
  const [off, setOff] = useState<Set<string>>(new Set());
  const [reasons, setReasons] = useState<Array<{ ref: string; reason: string }>>([]);
  // One key per set: pressing again for the same cards is a retry; a different set is a new action.
  const [keyFor, setKeyFor] = useState<{ set: string; key: string } | null>(null);
  const chosen = list.filter((x) => !off.has(x.ref));
  const maxItems = auth.data?.find((r) => r.key === 'batch.max_items')?.limit?.items ?? 20;
  const maxUsd = auth.data?.find((r) => r.key === 'batch.max_usd')?.limit?.usd ?? 2;
  const total = chosen.reduce((a, x) => a + Number(x.quota_estimate.usd), 0);
  const toggle = (ref: string) => setOff((s) => { const n = new Set(s); if (n.has(ref)) n.delete(ref); else n.add(ref); return n; });
  const run = async () => {
    const set = chosen.map((x) => `${x.ref}@${x.version}`).sort().join(',');
    const key = keyFor?.set === set ? keyFor.key : crypto.randomUUID();
    setKeyFor({ set, key });
    setReasons([]);
    try {
      const out = await seal.mutateAsync({ items: chosen.map((x) => ({ ref: x.ref, version: x.version })), key });
      toast({ tone: 'ok', text: <>{out.items.length} کارت با یک مُهر تأیید شد <span className="fig">({out.batch})</span>؛ هر کدام مصوبه‌ی خودش را دارد.</> });
      onClose();
    } catch (e) {
      setReasons(batchReasons(e));
      toast({ tone: 'error', text: faError(e) });
    }
  };
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title="مُهر گروهی" description="کارت‌های کم‌ریسک و برگشت‌پذیر A1؛ یک اثر انگشت برای دقیقاً همین مجموعه." width={560}
      footer={(
        <div className="flex flex-col items-center gap-2">
          <SealButton code={holding?.code ?? 'HQ'} nameFa={holding?.name_fa ?? 'هلدینگ'} nameEn={holding?.name_en ?? 'Holding'} holding size={84} busy={seal.isPending} disabled={!chosen.length || chosen.length > maxItems} onSealed={run} />
          <span className="text-center text-[12px] text-muted">{chosen.length ? <>مُهر {chosen.length.toLocaleString('fa-IR')} کارت، روی هم <span className="fig">{usd(total)}</span>. اگر یکی عوض شده باشد هیچ‌کدام مُهر نمیشود.</> : 'کارتی انتخاب نشده.'}</span>
        </div>
      )}>
      <div className="flex flex-col gap-3">
        <p className="rounded-[12px] bg-tile p-3 text-[12px] leading-6 text-sec">
          فقط پیشنهاد، مصوبه‌ی جلسه و ورودی دانشنامه؛ هر کدام حداکثر <span className="fig">{usd(maxUsd)}</span> و حداکثر {maxItems.toLocaleString('fa-IR')} کارت در یک مُهر (ماتریس اختیار). هر کارت مصوبه، ردیف Audit و ثبت تعامل خودش را دارد.
        </p>
        {q.isLoading ? <Skeleton className="h-40" /> : !list.length ? <Empty icon="seal" title="کارت شایسته‌ای نیست" /> : (
          <ul className="flex flex-col gap-2">
            {list.map((x) => {
              const k = DECISION_KIND[x.kind] ?? { fa: x.kind, icon: 'decision' as const };
              const bad = reasons.find((r) => r.ref === x.ref);
              const on = !off.has(x.ref);
              return (
                <li key={x.ref}>
                  <label className={cx('flex cursor-pointer items-start gap-3 rounded-[12px] border p-3 transition-colors', on ? 'border-gold-ink bg-gold-soft' : 'border-div', bad && 'border-[var(--hq-neg-line)] bg-neg-soft')}>
                    <input type="checkbox" checked={on} onChange={() => toggle(x.ref)} className="mt-1 size-4 flex-none accent-[var(--hq-gold-ink)]" aria-label={`انتخاب ${x.ref}`} />
                    <span className="flex min-w-0 flex-1 flex-col gap-1">
                      <span className="text-[14px] font-semibold text-ink">{x.title}</span>
                      <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] text-muted">
                        <CompanyMark code={x.company} height={12} mono /><span>{k.fa}</span><span>، {x.proposer.display_fa ?? x.proposer.code}</span><span className="fig">{x.ref}</span>
                      </span>
                      {bad ? <span className="text-[12px] font-semibold text-neg">{BATCH_REASON[bad.reason] ?? bad.reason}</span> : null}
                    </span>
                    <span className="flex flex-none flex-col items-end gap-0.5"><span className="fig text-[13px] font-semibold text-ink">{usd(x.quota_estimate.usd)}</span><span className="fig text-[11px] text-muted">{tokens(x.quota_estimate.tokens)} tok</span></span>
                  </label>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Sheet>
  );
}

// ------------------------------------------------------- payloads of the §20 kinds --
const asObj = (v: unknown) => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {});
const asArr = (v: unknown) => (Array.isArray(v) ? (v as unknown[]) : []);

function Votes({ v }: { v: Record<string, unknown> }) {
  return (
    <div className="flex flex-wrap gap-2">
      {(['support', 'oppose', 'abstain'] as const).map((k) => <Pill key={k} tone={VOTE_FA[k]!.tone} dot>{VOTE_FA[k]!.fa} <span className="fig">{Number(v[k] ?? 0)}</span></Pill>)}
    </div>
  );
}

function ObjectiveKrs({ refOrObj }: { refOrObj: unknown }) {
  const ref = typeof refOrObj === 'string' ? refOrObj : null;
  const q = useObjective(ref);
  const o = ref ? q.data : (refOrObj as { key_results?: unknown[]; title_fa?: string } | null);
  const krs = asArr((o as { key_results?: unknown } | undefined)?.key_results).map(asObj);
  if (ref && q.isLoading) return <Skeleton className="h-24" />;
  if (!krs.length) return ref ? <RefChip r={ref} /> : null;
  return (
    <ul className="flex flex-col gap-1.5">
      {krs.map((k) => (
        <li key={String(k.ref)} className="flex flex-wrap items-center gap-2 rounded-[10px] bg-tile px-3 py-2 text-[13px]">
          <span className="fig text-[11px] text-muted">{String(k.ref)}</span>
          <span className="min-w-0 flex-1 text-ink">{String(k.title_fa ?? '')}</span>
          <span className="fig text-[12px] text-sec">{String(k.start)} → {String(k.target)}</span>
          <span className="fig text-[11px] text-muted">w {String(k.weight)}</span>
        </li>
      ))}
    </ul>
  );
}

/** The payload of a governance card (§20.11), read tolerantly: every field the card carries, nothing assumed beyond it. */
export function GovernancePayload({ d }: { d: Decision }) {
  const p = asObj(d.payload);
  if (d.kind === 'meeting_resolution') {
    const claims = asArr(p.claims) as Claim[];
    return (
      <Section title="مصوبه‌ی جلسه">
        <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted">{p.meeting ? <RefChip r={String(p.meeting)} note="جلسه" /> : null}</div>
        {p.text_md ? <div className="rounded-[12px] bg-tile p-3"><Md text={String(p.text_md)} className="text-[14px] leading-7 text-ink" /></div> : null}
        {p.votes ? <Votes v={asObj(p.votes)} /> : null}
        {claims.length ? (
          <ul className="flex flex-col gap-1.5 pt-1">
            {claims.map((c) => <li key={c.id} className="flex flex-wrap items-center gap-2 text-[13px] text-sec"><Icon name="seal" size={14} />{c.text_fa}{c.source ? <RefChip r={c.source.ref} /> : null}</li>)}
          </ul>
        ) : null}
        <p className="text-[12px] text-muted">فقط ادعاهای منبع‌دار همراه این کارت‌اند. رأی مدیرها جای مُهر تو را نمیگیرد؛ با مُهر، مصوبه و کار پیگیری ساخته میشود.</p>
      </Section>
    );
  }
  if (d.kind === 'charter_amendment') {
    const reds = asArr(p.red_lines) as RedLine[];
    const sha = String(p.body_sha256 ?? '');
    return (
      <Section title="اصلاحیه‌ی اساسنامه">
        <div className="grid grid-cols-2 gap-2">
          <Fact label="دامنه" mono>{String(p.scope ?? '—') === 'holding' ? 'holding' : String(p.scope ?? '—')}</Fact>
          <Fact label="بر پایه‌ی نسخه" mono>{String(p.base_version ?? '—')}</Fact>
        </div>
        {p.diff_md ? <Diff text={String(p.diff_md)} className="max-h-80 overflow-y-auto" /> : p.body_md ? <div className="max-h-80 overflow-y-auto rounded-[12px] bg-tile p-3"><Md text={String(p.body_md)} /></div> : null}
        {reds.length ? (
          <ul className="flex flex-col gap-1">{reds.map((r) => <li key={r.key} className="flex items-start gap-2 text-[13px] text-ink"><span className="mt-0.5 text-neg"><Icon name="lock" size={14} /></span><span className="min-w-0 flex-1">{r.text_fa}</span><span className="fig text-[11px] text-muted">{r.check}</span></li>)}</ul>
        ) : null}
        <p className="text-[12px] text-muted">{sha ? <>مُهر به همین متن و همین خطوط قرمز بسته است (<span className="fig">sha256 {sha.slice(0, 12)}…</span>). </> : null}اگر نسخه‌ی پایه دیگر جاری نباشد، این کارت کنار میرود و کارت تازه میاید.</p>
      </Section>
    );
  }
  if (d.kind === 'okr') {
    return (
      <Section title="OKR">
        <div className="flex flex-wrap items-center gap-2">{typeof p.objective === 'string' ? <RefChip r={p.objective} /> : null}{p.quarter ? <span className="fig text-[12px] text-sec">{String(p.quarter)}</span> : null}</div>
        <ObjectiveKrs refOrObj={p.objective} />
        <p className="text-[12px] text-muted">فقط مُهر تو OKR را فعال میکند؛ بی‌مُهر، فصل بی‌OKR میماند.</p>
      </Section>
    );
  }
  if (d.kind === 'knowledge_entry') {
    const e = asObj(p.entry ?? p);
    return (
      <Section title="ورودی دانشنامه‌ی هلدینگ">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <Fact label="لایه">{LAYER_FA[String(e.layer)]?.fa ?? String(e.layer ?? '—')}</Fact>
          <Fact label="نوع">{KNOWLEDGE_KIND[String(e.kind)] ?? String(e.kind ?? '—')}</Fact>
          <Fact label="معتبر تا">{e.valid_until ? jDate(`${String(e.valid_until)}T12:00:00Z`, true) : '—'}</Fact>
        </div>
        {e.body_md ? <div className="rounded-[12px] bg-tile p-3"><Md text={String(e.body_md)} /></div> : null}
        <div className="flex flex-wrap gap-1.5">{asArr(e.sources).map(asObj).map((s, i) => <RefChip key={i} r={String(s.ref)} note={s.note ? String(s.note) : null} tone="neutral" />)}</div>
      </Section>
    );
  }
  if (d.kind === 'risk_acceptance') {
    return (
      <Section title="پذیرش ریسک">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <Fact label="ریسک">{p.risk ? <RefChip r={String(p.risk)} /> : '—'}</Fact>
          <Fact label="تا">{p.until ? jDate(String(p.until), true) : '—'}</Fact>
          {p.score != null ? <Fact label="امتیاز" mono>{String(p.score)}</Fact> : null}
        </div>
        <p className="text-[12px] text-muted">پذیرش حداکثر ۹۰ روز است؛ بعد از آن ریسک دوباره راه کاهش یا مُهر تازه میخواهد.</p>
      </Section>
    );
  }
  if (d.kind === 'authority_change') {
    const rows = asArr(p.changes ?? p.rules).map(asObj);
    return (
      <Section title="تغییر ماتریس اختیار">
        <ul className="flex flex-col gap-1.5">
          {rows.map((r, i) => (
            <li key={i} className="flex flex-wrap items-center gap-2 rounded-[10px] bg-tile px-3 py-2 text-[13px]">
              <span className="fig text-ink">{String(r.key)}</span>
              {r.from !== undefined ? <span className="fig text-muted line-through">{JSON.stringify(r.from).replace(/["{}]/g, '')}</span> : null}
              <span className="fig text-ink">{JSON.stringify(r.to ?? r.limit ?? '').replace(/["{}]/g, '')}</span>
            </li>
          ))}
        </ul>
        <p className="text-[12px] text-muted">ثابت‌های قفل با هیچ کارتی عوض نمیشوند.</p>
      </Section>
    );
  }
  return null;
}

// ------------------------------------------------------- expected outcome (§20.6) --
const fig = (v: number, metric: string) => kpiFig(v, /٪|%/.test(metric) ? '%' : '');
export function ExpectedBlock({ d }: { d: Decision }) {
  const e: Expected | null | undefined = d.expected;
  const missing = (d.warnings ?? []).includes('expected_missing');
  if (!e && !missing) return null;
  return (
    <Section title="قول قابل سنجش">
      {missing ? <p className="flex items-start gap-2 rounded-[12px] bg-warn-soft p-3 text-[13px] leading-6 text-ink"><span className="text-warn"><Icon name="urgent" size={18} /></span>این پیشنهاد نتیجه‌ی مورد انتظار ندارد؛ بی‌آن در ۳۰، ۶۰ و ۹۰ روز سنجیده نمیشود. از پیشنهاددهنده بخواه آن را اضافه کند.</p> : null}
      {e ? (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div className="col-span-2 flex min-w-0 flex-col gap-1 rounded-[12px] bg-tile p-3"><span className="text-[11px] text-muted">سنجه</span><span className="text-[14px] font-semibold text-ink">{e.metric_fa}</span>{e.kpi ? <span className="fig text-[11px] text-sec">KPI {e.kpi}</span> : <span className="text-[11px] text-sec">بی‌KPI: پیشنهاددهنده یادداشت میدهد و ناظر حکم میکند</span>}</div>
          <Fact label="از → به" mono>{fig(e.baseline, e.metric_fa)} → {fig(e.target, e.metric_fa)}</Fact>
          <Fact label="تا">{e.by_days} روز</Fact>
        </div>
      ) : null}
    </Section>
  );
}

/** The 30/60/90-day reviews of a sealed decision. */
export function DecisionOutcomes({ d }: { d: Decision }) {
  const q = useOutcomes({ decision: d.ref });
  const rows = (q.data?.pages.flatMap((p) => p.items) ?? []).sort((a, b) => a.day - b.day);
  if (d.status !== 'approved' || !d.expected) return null;
  return (
    <Section title="بازبینی نتیجه">
      {q.isLoading ? <Skeleton className="h-16" /> : !rows.length ? <p className="text-[13px] text-muted">بازبینی‌ها با مُهر ساخته میشوند؛ هنوز ردیفی نیامده.</p> : (
        <ol className="grid gap-2 sm:grid-cols-3">
          {rows.map((r) => (
            <li key={r.ref} className="flex flex-col gap-1 rounded-[12px] bg-tile p-3">
              <span className="flex items-center gap-2 text-[12px] text-muted"><span>روز {r.day}</span><span className="fig">{r.ref}</span></span>
              <Pill tone={VERDICT[r.verdict]?.tone ?? 'neutral'} dot>{VERDICT[r.verdict]?.fa ?? r.verdict}</Pill>
              <span className="text-[12px] text-sec">{r.measured ? <>اندازه <span className="fig text-ink">{fig(r.measured.value, r.expected.metric_fa)}</span></> : `موعد ${jDate(r.due_at)}`}</span>
            </li>
          ))}
        </ol>
      )}
    </Section>
  );
}

