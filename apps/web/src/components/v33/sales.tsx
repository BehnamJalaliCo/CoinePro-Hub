'use client';

// ⟨1.15⟩ Contract §33.4–§33.5 «فروش»: a small CRM per company — the pipeline by stage, the leads, one lead with its events and the follow-up
// draft (shown only; nothing is sent from here), and the affiliate commission due against received.

import { Fit } from '@/components/look/text';
import Link from 'next/link';
import { useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Sheet } from '@/components/ui/overlay';
import { Card, Empty, ErrorState, FilterChip, Pill, SectionTitle, Skeleton, StatTile } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { FaPara, FaText, fig } from '@/components/v29/text';
import { errText, field, notYet } from '@/components/v31/kit';
import {
  CONTACT_RE, LEAD_SOURCE_FA, dec0, stageFa, useAffiliateGaps, useLead, useLeadActions, useLeads, usePipeline,
  type GapState, type Lead, type LeadDraft, type LeadPatch, type PipelineStage,
} from '@/lib/api/v33';
import { cx, jDate, jDateTime, numText, parseNum } from '@/lib/format';
import { useNow } from '@/lib/store';
import { Loading, Txt, pctOf, usdt } from './bits';

// ============================================================================================== the pipeline ==
function PipelineCard({ code }: { code: string }) {
  const q = usePipeline(code);
  if (q.isLoading) return <Loading h="h-44" />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return null;
  const p = q.data;
  const max = Math.max(1, ...p.stages.map((s) => s.count));
  const win = p.win_rate == null ? null : p.win_rate * 100;
  return (
    <Card as="section" className="flex flex-col gap-4 p-5" aria-label="مسیر فروش">
      <SectionTitle title="مسیر فروش" note="تعداد و ارزش هر مرحله و چند روز معمولاً در آن می‌مانند" />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="سرنخ باز" value={<span className="fig">{fig(p.open_count)}</span>} sub={<>از <span className="fig">{fig(p.total)}</span> سرنخ</>} />
        <StatTile label="ارزش باز" value={<span className="fig">{usdt(p.open_value_usdt)}</span>} sub="جمع ارزش برآوردشده" />
        <StatTile label="نرخ موفقیت" value={<span className="fig">{pctOf(win, 0)}</span>} sub={<>پرداخت <span className="fig">{fig(p.won_count)}</span>، رفته <span className="fig">{fig(p.lost_count)}</span></>} />
        <StatTile label="پرداخت کرده" value={<span className="fig">{fig(p.won_count)}</span>} tone="pos" />
      </div>
      <ol className="flex flex-col gap-2.5" aria-label="مرحله‌ها">
        {p.stages.map((s) => (
          <li key={s.stage} className="flex flex-col gap-1.5">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-[13px]">
              <span className="min-w-0 flex-1 font-semibold">{stageFa(s.stage, s.title_fa)}</span>
              <span className="fig text-sec">{fig(s.count)} سرنخ</span>
              <span className="fig text-sec">{usdt(s.value_usdt)}</span>
              <span className="text-[11px] text-muted">{s.median_days == null ? '—' : <>معمولاً <span className="fig">{fig(s.median_days, 1)}</span> روز</>}</span>
            </div>
            <div className="h-2.5 rounded-full bg-tile"><span className={cx('block h-full rounded-full', s.kind === 'lost' ? 'bg-neg' : s.kind === 'won' ? 'bg-pos' : 'bg-[var(--hq-gold-bright)]')} style={{ width: `${Math.max(s.count ? 3 : 0, (s.count / max) * 100)}%` }} /></div>
          </li>
        ))}
      </ol>
    </Card>
  );
}

// ================================================================================================= lead sheet ==
function LeadSheet({ code, leadRef, onClose, stages }: { code: string; leadRef: string; onClose: () => void; stages: PipelineStage[] }) {
  const q = useLead(leadRef);
  const act = useLeadActions(code);
  const toast = useToast();
  const [draft, setDraft] = useState<LeadDraft | null>(null);
  const d = q.data;
  const [next, setNext] = useState<{ next_fa: string; next_at: string } | null>(null);
  const [lost, setLost] = useState<string | null>(null);
  const [value, setValue] = useState<string | null>(null);
  const titleOf = (k: string) => stageFa(k, stages.find((s) => s.stage === k)?.title_fa);
  const patch = (body: LeadPatch, ok: string, after?: () => void) => {
    if (!d) return;
    act.edit.mutate({ ref: leadRef, version: d.version, body }, { onSuccess: () => { toast({ tone: 'ok', text: ok }); after?.(); }, onError: (e) => { toast({ tone: 'error', text: errText(e, 'ذخیره نشد.') }); void q.refetch(); } });
  };
  const lostKey = stages.find((s) => s.kind === 'lost')?.stage ?? 'lost';
  return (
    <Sheet open onOpenChange={(v) => !v && onClose()} title={d ? <span>{d.name_fa ?? d.contact} <span className="fig text-[12px] font-normal text-muted">{d.ref}</span></span> : 'سرنخ'} width={520}>
      {q.isLoading || !d ? (q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : <Skeleton className="h-64" />) : (
        <div className="flex flex-col gap-5" aria-label={`سرنخ ${d.ref}`}>
          <dl className="grid grid-cols-2 gap-2">
            {([['منبع', LEAD_SOURCE_FA[d.source] ?? d.source], ['ارزش', usdt(d.value_usdt)], ['شناسه', d.contact], ['مسئول', d.assignee?.display_fa ?? d.assignee?.code ?? 'بدون مسئول']] as const).map(([k, v]) => (
              <div key={k} className="rounded-[12px] bg-tile p-3"><dt className="text-[11px] text-muted">{k}</dt><dd className="pt-1 text-[14px] font-semibold"><Fit><span className="fig" dir="auto">{v}</span></Fit></dd></div>
            ))}
          </dl>
          <label className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">مرحله</span>
            <select value={d.stage} aria-label="مرحله‌ی سرنخ" disabled={act.edit.isPending} onChange={(e) => (e.target.value === lostKey ? setLost('') : patch({ stage: e.target.value }, 'مرحله عوض شد.'))} className={cx(field, 'h-10')}>
              {[...new Set([...stages.map((s) => s.stage), d.stage])].map((s) => <option key={s} value={s}>{titleOf(s)}</option>)}
            </select></label>
          {lost != null ? (
            <div className="hq-rise flex flex-col gap-2 rounded-[12px] bg-tile p-3" aria-label="دلیل از دست رفتن">
              <Txt label="چرا از دست رفت؟ (اختیاری)" value={lost} set={setLost} />
              <div className="flex gap-2"><Button variant="primary" size="sm" loading={act.edit.isPending} onClick={() => patch({ stage: lostKey, lost_reason_fa: lost.trim() || null }, 'مرحله عوض شد.', () => setLost(null))}>ثبت</Button><Button size="sm" onClick={() => setLost(null)}>بی‌خیال</Button></div>
            </div>
          ) : null}
          {value != null ? (
            <div className="hq-rise flex flex-col gap-2 rounded-[12px] bg-tile p-3" aria-label="ارزش سرنخ">
              <Txt label="ارزش برآوردی (USDT)" value={value} set={(v) => setValue(numText(v))} ltr />
              {/* Empty clears the value; anything typed must read as a number (Persian digits included), never a silent null. */}
              <div className="flex gap-2"><Button variant="primary" size="sm" loading={act.edit.isPending} disabled={value.trim() !== '' && parseNum(value) == null} onClick={() => patch({ value_usdt: value.trim() ? parseNum(value) : null }, 'ارزش ثبت شد.', () => setValue(null))}>ثبت</Button><Button size="sm" onClick={() => setValue(null)}>بی‌خیال</Button></div>
            </div>
          ) : <Button size="sm" className="self-start" onClick={() => setValue(d.value_usdt == null ? '' : String(dec0(d.value_usdt)))}>تغییر ارزش</Button>}
          {d.stage === 'lost' && d.lost_reason_fa ? <p className="rounded-[10px] bg-neg-soft px-3 py-2 text-[13px] leading-6">دلیل از دست رفتن: <FaText text={d.lost_reason_fa} /></p> : null}
          <section className="flex flex-col gap-2" aria-label="پیگیری بعدی">
            <h3 className="text-[13px] font-semibold text-sec">پیگیری بعدی</h3>
            <p className="text-[13px] leading-6">{d.next_fa ? <FaText text={d.next_fa} /> : <span className="text-muted">هنوز تعیین نشده.</span>}{d.next_at ? <span className="text-muted"> · {jDateTime(d.next_at)}</span> : null}</p>
            {next ? (
              <div className="flex flex-col gap-2 rounded-[12px] bg-tile p-3">
                <Txt label="چه بگوییم" value={next.next_fa} set={(v) => setNext({ ...next, next_fa: v })} />
                <Txt label="چه زمانی" value={next.next_at} set={(v) => setNext({ ...next, next_at: v })} type="datetime-local" ltr />
                <div className="flex gap-2"><Button variant="primary" size="sm" disabled={!next.next_fa.trim()} loading={act.edit.isPending} onClick={() => patch({ next_fa: next.next_fa.trim(), next_at: next.next_at ? new Date(next.next_at).toISOString() : null }, 'پیگیری ثبت شد.', () => setNext(null))}>ثبت</Button><Button size="sm" onClick={() => setNext(null)}>بی‌خیال</Button></div>
              </div>
            ) : <Button size="sm" className="self-start" onClick={() => setNext({ next_fa: d.next_fa ?? '', next_at: '' })}>تعیین پیگیری</Button>}
          </section>
          <section className="flex flex-col gap-2" aria-label="پیش‌نویس پیگیری">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="flex-1 text-[13px] font-semibold text-sec">پیش‌نویس پیگیری</h3>
              <Button size="sm" icon="edit" loading={act.draft.isPending} onClick={() => act.draft.mutate(leadRef, { onSuccess: (t) => setDraft(t), onError: (e) => toast({ tone: 'error', text: errText(e, 'پیش‌نویس نیامد.') }) })}>پیش‌نویس پیگیری</Button>
            </div>
            {draft != null ? (
              <figure className="hq-rise flex flex-col gap-2 rounded-[12px] bg-tile p-3" aria-label="متن پیش‌نویس">
                <FaPara text={draft.draft_fa} className="text-[14px] leading-7" />
                {!draft.guard_ok ? <p className="rounded-[10px] bg-warn-soft px-3 py-2 text-[12px] leading-6" role="alert">این متن از بازبینی پیام‌های بیرونی رد نمیشود؛ پیش از فرستادن باید اصلاح شود.</p> : null}
                <figcaption className="text-[11px] text-muted">فقط پیش‌نویس است و فرستاده نمیشود؛ فرستادن از همان مسیر همیشگی بازبینی و مُهر میگذرد.</figcaption>
              </figure>
            ) : <p className="text-[12px] text-muted">با صدای همین شرکت نوشته میشود و هیچ‌جا نمی‌رود.</p>}
          </section>
          <section className="flex flex-col gap-2" aria-label="رویدادها">
            <h3 className="text-[13px] font-semibold text-sec">رویدادها</h3>
            {d.events.length ? (
              <ol className="flex flex-col">{[...d.events].sort((a, b) => b.at.localeCompare(a.at)).map((e, i) => (
                <li key={i} className="flex items-start gap-2 border-t border-div py-2 text-[13px] first:border-0"><span className="fig w-24 flex-none text-[11px] text-muted">{jDate(e.at)}</span><span className="min-w-0 flex-1 leading-6"><FaText text={e.note_fa} /></span></li>
              ))}</ol>
            ) : <p className="text-[13px] text-muted">رویدادی نیست.</p>}
          </section>
        </div>
      )}
    </Sheet>
  );
}

// ==================================================================================================== leads ==
export function LeadsCard({ code }: { code: string }) {
  const q = useLeads(code);
  const pipe = usePipeline(code);
  const act = useLeadActions(code);
  const toast = useToast();
  const [stage, setStage] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [form, setForm] = useState<{ name_fa: string; contact: string; value: string } | null>(null);
  const stages = useMemo(() => pipe.data?.stages ?? [], [pipe.data]);
  const all = q.data ?? [];
  const rows = all.filter((l) => !stage || l.stage === stage);
  if (q.isLoading) return <Loading h="h-52" />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return notYet('companies', 'فروش بعد از به‌روزرسانی ستاد میاید', 'سرنخ‌ها از پشتیبانی، تلگرام و پرداخت‌ها این‌جا جمع میشود.');
  const keys = stages.length ? stages.map((s) => s.stage) : [...new Set(all.map((l) => l.stage))];
  const titleOf = (k: string) => stageFa(k, stages.find((s) => s.stage === k)?.title_fa);
  const contact = form?.contact.trim() ?? '';
  const contactOk = !contact || CONTACT_RE.test(contact);
  return (
    <Card as="section" className="flex flex-col gap-3 p-5" aria-label="سرنخ‌ها">
      <SectionTitle title="سرنخ‌ها" note="فقط نام نمایشی و یک شناسه؛ شماره و نشانی تماس در سامانه‌ی خود شرکت می‌ماند"
        action={<Button size="sm" variant="primary" icon="add" onClick={() => setForm({ name_fa: '', contact: '', value: '' })}>سرنخ تازه</Button>} />
      {form ? (
        <div className="hq-rise flex flex-col gap-3 rounded-[12px] bg-tile p-4" aria-label="سرنخ تازه">
          <div className="grid gap-3 sm:grid-cols-3">
            <Txt label="نام" value={form.name_fa} set={(v) => setForm({ ...form, name_fa: v })} />
            <Txt label="شناسه (اختیاری)" value={form.contact} set={(v) => setForm({ ...form, contact: v })} ltr placeholder="cu_…" />
            <Txt label="ارزش برآوردی (USDT)" value={form.value} set={(v) => setForm({ ...form, value: v.replace(/[^\d.]/g, '') })} ltr />
          </div>
          {!contactOk ? <p className="text-[12px] text-neg" role="alert">شناسه دست‌کم ۸ حرف لاتین یا عدد است؛ شماره یا نشانی تماس پذیرفته نمیشود.</p> : <p className="text-[11px] text-muted">اگر شناسه ننویسی، ستاد خودش یکی میسازد.</p>}
          <div className="flex gap-2">
            <Button variant="primary" loading={act.add.isPending} disabled={!contactOk || !(form.name_fa.trim() || contact)} onClick={() => act.add.mutate({ name_fa: form.name_fa.trim() || null, contact: contact || null, source: 'manual', value_usdt: form.value ? Number(form.value) : null }, { onSuccess: () => { toast({ tone: 'ok', text: 'سرنخ ثبت شد.' }); setForm(null); }, onError: (e) => toast({ tone: 'error', text: errText(e, 'ثبت نشد.') }) })}>ذخیره</Button>
            <Button onClick={() => setForm(null)}>بی‌خیال</Button>
          </div>
        </div>
      ) : null}
      <div className="flex flex-wrap gap-2" role="group" aria-label="مرحله">
        <FilterChip selected={stage === null} onClick={() => setStage(null)} count={all.length}>همه</FilterChip>
        {keys.map((k) => <FilterChip key={k} selected={stage === k} onClick={() => setStage(stage === k ? null : k)} count={all.filter((l) => l.stage === k).length}>{titleOf(k)}</FilterChip>)}
      </div>
      {!rows.length ? <Empty icon="companies" title="سرنخی نیست" body="سرنخ از پشتیبانی، تلگرام یا پرداخت بدون مشتری خودکار ساخته میشود؛ دستی هم می‌توانی اضافه کنی." /> : (
        <ul className="flex flex-col">{rows.map((l) => <LeadRow key={l.ref} l={l} stage={stages.find((s) => s.stage === l.stage)} onOpen={() => setOpen(l.ref)} />)}</ul>
      )}
      {open ? <LeadSheet code={code} leadRef={open} stages={stages} onClose={() => setOpen(null)} /> : null}
    </Card>
  );
}

function LeadRow({ l, stage, onOpen }: { l: Lead; stage?: PipelineStage; onOpen: () => void }) {
  const now = useNow();
  const kind = stage?.kind ?? (l.stage === 'paid' ? 'won' : l.stage === 'lost' ? 'lost' : 'open');
  const late = !!now && !!l.next_at && new Date(l.next_at).getTime() < now && kind === 'open';
  return (
    <li className="border-t border-div first:border-0" aria-label={`سرنخ ${l.ref}`}>
      <button type="button" onClick={onOpen} className="flex w-full flex-wrap items-center gap-x-4 gap-y-1.5 py-3 text-start hover:bg-hover/40">
        <span className="flex min-w-0 flex-[1_1_13rem] flex-col">
          <span className="truncate text-[14px] font-semibold">{l.name_fa ?? <span className="fig" dir="ltr">{l.contact}</span>}</span>
          <span className="text-[11px] text-muted"><span className="fig">{l.ref}</span> · {LEAD_SOURCE_FA[l.source] ?? l.source}{l.next_fa ? <> · <FaText text={l.next_fa} /></> : ''}</span>
        </span>
        {l.value_usdt != null ? <span className="fig text-[13px] text-sec">{usdt(l.value_usdt)}</span> : null}
        {late ? <Pill tone="warn" icon="time">پیگیری عقب افتاده</Pill> : null}
        <Pill tone={kind === 'won' ? 'pos' : kind === 'lost' ? 'neg' : 'silver'} dot>{stageFa(l.stage, stage?.title_fa)}</Pill>
      </button>
    </li>
  );
}

export function CompanySales({ code }: { code: string }) {
  return (<><PipelineCard code={code} /><LeadsCard code={code} /></>);
}

// ======================================================================================== affiliate follow-up ==
const GAP_STATE: Record<GapState, { fa: string; tone: 'warn' | 'pos' | 'silver' }> = { open: { fa: 'باز', tone: 'warn' }, closed: { fa: 'بسته شد', tone: 'pos' }, ok: { fa: 'درست رسید', tone: 'pos' }, waiting: { fa: 'در مهلت تسویه', tone: 'silver' } };
/** `/revenue/affiliate-gaps`: commission due against received per account and month. */
export function AffiliateGaps({ company }: { company: string | null }) {
  const q = useAffiliateGaps(company);
  if (q.isLoading) return <Loading h="h-52" />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return notYet('budget', 'پیگیری افیلیت بعد از به‌روزرسانی ستاد میاید', 'کمیسیون طلب‌شده در برابر دریافت‌شده هر حساب این‌جا میاید.');
  const rows = [...q.data].sort((a, b) => (a.state === 'open' ? 0 : 1) - (b.state === 'open' ? 0 : 1) || b.month.localeCompare(a.month));
  if (!rows.length) return <Card><Empty icon="budget" title="شکافی نیست" body="کمیسیون همه‌ی حساب‌ها با آنچه رسیده یکی است." /></Card>;
  return (
    <Card as="section" className="flex flex-col gap-1 p-5" aria-label="شکاف کمیسیون">
      <SectionTitle title="طلب و دریافت" note="اگر بعد از مهلت تسویه بیش از ۵٪ کم برسد، برای مدیر مالی یک پیگیری باز میشود؛ با رسیدن پول بسته میشود" />
      <ul className="flex flex-col">
        {rows.map((g) => {
          const s = GAP_STATE[g.state];
          return (
            <li key={`${g.company}-${g.account}-${g.month}`} aria-label={`شکاف ${g.account} ${g.month}`} className="flex flex-col gap-2 border-t border-div py-3 first:border-0">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                <span className="flex min-w-0 flex-[1_1_12rem] flex-col"><span className="fig text-[14px] font-semibold" dir="ltr">{g.account}</span><span className="text-[11px] text-muted"><span className="fig">{g.exchange}</span> · <span className="fig">{g.company}</span> · <span className="fig">{g.month.slice(0, 7)}</span></span></span>
                <span className="text-[12px] text-sec">طلب <span className="fig font-semibold text-ink">{usdt(g.due_usdt, 2)}</span></span>
                <span className="text-[12px] text-sec">رسیده <span className="fig font-semibold text-ink">{usdt(g.received_usdt, 2)}</span></span>
                <span className={cx('text-[12px]', g.state === 'open' ? 'text-neg' : 'text-sec')}>کم <span className="fig font-semibold">{usdt(g.gap_usdt, 2)} ({fig(g.gap_pct, 1)}%)</span></span>
                <Pill tone={s.tone} dot>{s.fa}</Pill>
              </div>
              {g.state === 'waiting' ? <span className="text-[11px] text-muted">مهلت تسویه تا {jDate(g.settles_on)}</span> : null}
              {g.work_ref ? <Link href={`/work/${g.work_ref}`} className="self-start text-[12px] text-gold-ink hover:underline">پیگیری مدیر مالی <span className="fig">{g.work_ref}</span></Link> : null}
              {g.draft_fa ? <FaPara text={g.draft_fa} className="rounded-[10px] bg-tile px-3 py-2 text-[13px] leading-6 text-sec" /> : null}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

