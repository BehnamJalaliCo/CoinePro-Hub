'use client';

import Link from 'next/link';
import { useState, type ReactNode } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Md, MdInline } from '@/components/ui/md';
import { FilterChip, Pill, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { CONFLICT_RULE, RefChip } from '@/components/v17/bits';
import type { IconName } from '@/generated/icons';
import { useDecisionDiffFile, useDecisionMemo, useRequestMemo, faError, type Decision18, type DecisionMemo, type DeployPayload, type DiffFile, type EvaluationPayload, type MemoMode, type Opinion, type ReviewFinding } from '@/lib/api/v18';
import { ago, cx, jDateTime, modelLabel, tokens, usd } from '@/lib/format';
import { Confidence, LEVEL3, MEMO_STATE, PlayerName, REC, RECOMMENDATION, REMINDER, Section, SubstituteNote, VERDICT3, hoursFa } from './bits';

function Fact({ label, children, mono }: { label: string; children: ReactNode; mono?: boolean }) {
  return (
    <div className="flex min-w-0 flex-col gap-1 rounded-[12px] bg-tile p-3">
      <span className="text-[11px] text-muted">{label}</span>
      <span className={cx('min-w-0 break-words text-[14px] font-semibold text-ink', mono && 'fig')}>{children}</span>
    </div>
  );
}

// ------------------------------------------------------------ the deploy card (§21.6) --
const FILE_STATUS: Record<string, { fa: string; icon: IconName; cls: string }> = {
  added: { fa: 'تازه', icon: 'add', cls: 'text-pos' }, modified: { fa: 'عوض‌شده', icon: 'edit', cls: 'text-warn' },
  removed: { fa: 'حذف‌شده', icon: 'reject', cls: 'text-neg' }, renamed: { fa: 'نام تازه', icon: 'share', cls: 'text-lapis' },
};
const UNAVAILABLE: Record<string, string> = {
  no_access: 'هاب به این ریپو دسترسی ندارد؛ diff نیامد، ولی کارت همچنان به همان commit بسته است.',
  too_large: 'diff از سقف (۳۰۰ فایل یا ۲۵۶ کیلوبایت) بزرگ‌تر است؛ فقط آمار آمده.',
  fetch_failed: 'گرفتن diff شکست خورد؛ کارت همچنان به همان commit بسته است.',
};
const SEVERITY: Record<string, { fa: string; tone: 'neutral' | 'warn' | 'neg' }> = { low: { fa: 'کم', tone: 'neutral' }, medium: { fa: 'متوسط', tone: 'warn' }, high: { fa: 'زیاد', tone: 'neg' }, critical: { fa: 'بحرانی', tone: 'neg' } };

/** Code lines, left to right, Latin figures; additions and removals by sign and colour (masked lines stay masked). */
export function CodeDiff({ text, className }: { text: string; className?: string }) {
  return (
    <div dir="ltr" className={cx('overflow-x-auto rounded-[10px] bg-page py-1.5 text-[12px] leading-6', className)} role="region" aria-label="patch">
      {text.split('\n').map((l, i) => {
        const head = l.startsWith('@@');
        const add = !head && l.startsWith('+');
        const del = !head && l.startsWith('-');
        return (
          <div key={i} className={cx('flex min-w-max gap-2 px-2', add && 'bg-pos-soft', del && 'bg-neg-soft', head && 'text-muted')}>
            <span aria-hidden className={cx('fig w-3 flex-none text-center', add ? 'text-pos' : del ? 'text-neg' : 'text-muted')}>{head ? '' : add ? '+' : del ? '−' : ''}</span>
            <span className={cx('fig whitespace-pre', head ? 'text-muted' : 'text-ink')}>{head ? l : l.slice(1) || ' '}</span>
          </div>
        );
      })}
    </div>
  );
}

function FileRow({ refId, f }: { refId: string; f: DiffFile }) {
  const [open, setOpen] = useState(false);
  const [full, setFull] = useState(false);
  const q = useDecisionDiffFile(refId, full ? f.path : null);
  const st = FILE_STATUS[f.status] ?? FILE_STATUS.modified!;
  const patch = full && q.data?.patch ? q.data.patch : f.patch;
  return (
    <li className="flex flex-col gap-1.5">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} className="flex w-full items-center gap-2 rounded-[10px] px-2 py-1.5 text-start hover:bg-hover">
        <span className={st.cls} title={st.fa}><Icon name={st.icon} size={15} /></span>
        <span dir="ltr" className="fig min-w-0 flex-1 truncate text-right text-[12px] text-ink" title={f.path}>{f.path}</span>
        {f.secret_masked ? <Pill tone="warn" icon="lock">ماسک</Pill> : null}
        {f.binary ? <span className="text-[11px] text-muted">باینری</span> : <span className="fig flex-none text-[11px]"><span className="text-pos">+{f.additions}</span> <span className="text-neg">−{f.deletions}</span></span>}
        <Icon name="chevron" size={14} className={cx('flex-none text-muted transition-transform', open && 'rotate-180')} />
      </button>
      {open ? (
        <div className="flex flex-col gap-1.5 ps-2">
          {f.binary || !patch ? <p className="text-[12px] text-muted">فایل باینری است؛ patch ندارد.</p> : <CodeDiff text={patch} className="max-h-80 overflow-y-auto" />}
          {f.secret_masked ? <p className="text-[11px] text-muted">خطی که اسکن رمز در آن چیزی پیدا کرد ماسک شده؛ نه اینجا و نه در هیچ لاگی نمیاید.</p> : null}
          {f.truncated && !full ? <Button size="sm" variant="text" icon="download" onClick={() => setFull(true)} className="self-start">patch کامل این فایل</Button> : null}
          {full && q.isLoading ? <Skeleton className="h-16" /> : null}
          {full && q.error ? <p className="text-[12px] text-neg">{faError(q.error)}</p> : null}
        </div>
      ) : null}
    </li>
  );
}

function SecondReview({ r }: { r: NonNullable<DeployPayload['second_review']> }) {
  const mark = (v: ReviewFinding['verified']) => (v === true ? { fa: 'تأیید مدیر فنی', tone: 'pos' as const } : v === false ? { fa: 'رد مدیر فنی', tone: 'neutral' as const } : { fa: 'در حال سنجش', tone: 'lapis' as const });
  return (
    <div className="flex flex-col gap-2 rounded-[12px] border border-div p-3">
      <div className="flex flex-wrap items-center gap-2 text-[12px]">
        <span className="font-semibold text-ink">بازبینی دوم</span><PlayerName player={r.player} model={r.model} size={13} />
        <span className="flex-1" /><SubstituteNote />
      </div>
      <ul className="flex flex-col gap-2">
        {r.findings.map((f, i) => {
          const v = mark(f.verified);
          return (
            <li key={i} className="flex flex-col gap-1 rounded-[10px] bg-tile p-2.5">
              <div className="flex flex-wrap items-center gap-2">
                <Pill tone={SEVERITY[f.severity]?.tone ?? 'neutral'} dot>{SEVERITY[f.severity]?.fa ?? f.severity}</Pill>
                <span className="min-w-0 flex-1 text-[13px] font-semibold text-ink">{f.title_fa}</span>
                <Pill tone={v.tone}>{v.fa}</Pill>
              </div>
              <span dir="ltr" className="fig self-end text-[11px] text-muted">{f.path}:{f.line}</span>
              <Md text={f.detail_md} className="text-[12px] leading-6 text-sec" />
            </li>
          );
        })}
      </ul>
      <p className="text-[11px] text-muted">هیچ یافته‌ای فقط با حرف بازیکن ذخیره وارد کارت نمیشود؛ مدیر فنی یا QC هر کدام را میسنجد و تأییدشده‌ها به یادداشت ریسک میروند. این بازبینی کارت را نه تأیید میکند نه مسدود.</p>
    </div>
  );
}

/** The one definition of the deploy payload (§21.6): bound to `head_sha`, with the real diff when the hub can read the repository. */
export function DeployPayloadBlock({ d }: { d: Decision18 }) {
  const p = (d.payload ?? {}) as Partial<DeployPayload>;
  const diff = p.diff ?? null;
  const conflicts = p.calendar_conflicts ?? [];
  return (
    <Section title="انتشار">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Fact label="ریپو" mono><span dir="ltr" title={p.repo ?? undefined}>{String(p.repo ?? '—').split('/').at(-1)}</span></Fact>
        <Fact label="تغییر" mono>{String(p.diff_stat ?? '—')}</Fact>
        <Fact label="CI"><span className={p.ci?.status === 'passed' ? 'text-pos' : 'text-neg'}>{p.ci?.status === 'passed' ? 'سبز' : String(p.ci?.status ?? '—')}</span></Fact>
        <Fact label="تست‌ها" mono>{String(p.tests?.passed ?? 0)} ✓ · {String(p.tests?.failed ?? 0)} ✗</Fact>
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-sec">
        {p.head_sha ? <span>commit <span className="fig text-ink" title={p.head_sha}>{p.head_sha.slice(0, 10)}</span></span> : null}
        {p.rollout ? <span>روش <span className="fig text-ink">{p.rollout}</span></span> : null}
        {p.window ? <span>پنجره {jDateTime(p.window.from)} تا {jDateTime(p.window.to)}</span> : null}
        {p.pr_url ? <a href={p.pr_url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-gold-ink hover:underline"><Icon name="share" size={13} />PR</a> : null}
      </div>
      {conflicts.length ? (
        <ul className="flex flex-col gap-1">{conflicts.map((c, i) => <li key={i} className="flex items-start gap-2 rounded-[10px] bg-warn-soft p-2 text-[12px] text-ink"><span className="text-warn"><Icon name="urgent" size={14} /></span>{CONFLICT_RULE[c.rule] ?? c.rule}: {c.note_fa}</li>)}</ul>
      ) : null}
      {p.diff_unavailable ? <p className="flex items-start gap-2 rounded-[12px] bg-tile p-3 text-[12px] leading-6 text-sec"><Icon name="info" size={16} />{UNAVAILABLE[p.diff_unavailable] ?? p.diff_unavailable}</p> : null}
      {diff ? (
        <div className="flex flex-col gap-1.5 rounded-[12px] border border-div p-2">
          <div className="flex flex-wrap items-center gap-2 px-2 pt-1 text-[12px] text-sec">
            <span className="font-semibold text-ink">diff واقعی</span>
            <span>{diff.total_files} فایل</span>
            <span className="fig"><span className="text-pos">+{diff.total_additions}</span> <span className="text-neg">−{diff.total_deletions}</span></span>
            <span className="flex-1" />
            <span className="fig text-[11px] text-muted" dir="ltr">{diff.base_sha.slice(0, 7)}…{diff.head_sha.slice(0, 7)}</span>
          </div>
          <ul className="flex flex-col">{diff.files.map((f) => <FileRow key={f.path} refId={d.ref} f={f} />)}</ul>
          <p className="px-2 pb-1 text-[11px] text-muted">با دسترسی git خود هاب، {ago(diff.fetched_at)}. هر فایل تا ۴۰۰ خط اینجاست؛ فایل بلندتر «patch کامل» دارد. push تازه روی شاخه این کارت را کنار میگذارد.{diff.truncated ? ' فهرست فایل‌ها هم بریده شده.' : ''}</p>
        </div>
      ) : null}
      {p.second_review ? <SecondReview r={p.second_review} /> : null}
    </Section>
  );
}

// ---------------------------------------------------------- evaluation v2 (§21.5) --
export function EvaluationBlock({ d }: { d: Decision18 }) {
  const p = (d.payload ?? {}) as Partial<EvaluationPayload>;
  const r = RECOMMENDATION[String(p.recommendation)] ?? { fa: String(p.recommendation ?? '—'), tone: 'neutral' as const, icon: 'rate' as const };
  const c = p.change ?? null;
  return (
    <Section title="ارزیابی ماهانه">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <Fact label="کارمند" mono>{p.employee ? <Link href={`/employees/${p.employee}`} className="hover:underline">{p.employee}</Link> : '—'}</Fact>
        <Fact label="پیشنهاد"><Pill tone={r.tone} icon={r.icon}>{r.fa}</Pill></Fact>
        <Fact label="دور ارزیابی" mono>{p.round ?? '—'}</Fact>
      </div>
      {c ? (
        <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {c.title_fa ? <Fact label="عنوان تازه">{c.title_fa}</Fact> : null}
          {c.model ? <Fact label="مدل" mono>{modelLabel(c.model)}</Fact> : null}
          {c.effort ? <Fact label="فکر" mono>{c.effort}</Fact> : null}
          {c.quota_estimate_month ? <Fact label="برآورد ماهانه" mono>{tokens(c.quota_estimate_month)} tok</Fact> : null}
        </dl>
      ) : null}
      {p.transfer_to ? <p className="text-[13px] text-sec">کارهای باز به <span className="fig text-ink">{p.transfer_to}</span> میرسد.</p> : null}
      {p.evidence?.length ? <div className="flex flex-wrap gap-1.5">{p.evidence.map((e, i) => <RefChip key={i} r={e.ref} note={e.note ?? null} tone="neutral" />)}</div> : null}
      {p.unflagged ? <p className="flex items-start gap-2 rounded-[12px] bg-warn-soft p-3 text-[13px] leading-6 text-ink"><span className="text-warn"><Icon name="urgent" size={16} /></span>این کارمند پرچم قاعده‌محور ندارد؛ ارزیاب با این دلیل پیشنهاد داده: {p.override_reason ?? '—'}</p> : null}
      <p className="text-[12px] text-muted">{p.recommendation === 'promote' || p.recommendation === 'demote' ? 'با مُهر، تغییر با همان بررسی‌های استخدام اعمال میشود: مدل باید در یک اتصال روشن باشد و تعهد ماهانه در پاکت شرکت جا شود، وگرنه هیچ چیز عوض نمیشود.' : p.recommendation === 'dismiss' ? 'با مُهر، برکناری مثل §3.3 انجام میشود و کارهای باز منتقل میشوند.' : 'با مُهر، دوره‌ی آزمایشی پایان میگیرد.'}</p>
    </Section>
  );
}

// ------------------------------------------------------- the premium advisor (§21.1) --
function OpinionCard({ o, title }: { o: Opinion; title: string }) {
  const rec = REC[o.recommendation] ?? REC.ask!;
  return (
    <div className="flex flex-col gap-2 rounded-[12px] border border-div p-3">
      <div className="flex flex-wrap items-center gap-2 text-[12px]">
        <span className="font-semibold text-ink">{title}</span><PlayerName player={o.player} model={o.model} size={13} />
        <span className="flex-1" />
        <Pill tone={o.agrees ? 'pos' : 'warn'} icon={o.agrees ? 'seal' : 'urgent'}>{o.agrees ? 'هم‌نظر با مشاور' : 'اختلاف با مشاور'}</Pill>
      </div>
      <div className="flex flex-wrap items-center gap-2"><Pill tone={rec.tone} dot>{rec.fa}</Pill><Confidence v={o.confidence} tone="silver" /></div>
      <p className="text-[13px] leading-6 text-sec"><MdInline text={o.summary_fa} /></p>
      {o.differences.length ? <ul className="flex list-disc flex-col gap-1 pr-5 text-[12px] leading-6 text-sec marker:text-muted">{o.differences.map((x) => <li key={x}><MdInline text={x} /></li>)}</ul> : null}
      <SubstituteNote />
    </div>
  );
}

function MemoView({ m }: { m: DecisionMemo }) {
  const rec = REC[m.recommendation] ?? REC.ask!;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted">
        <span className="fig">{m.ref}</span><span>{m.trigger === 'auto' ? 'خودکار' : 'به درخواست تو'}، {ago(m.created_at)}</span>
        <span className="flex-1" />
        <span className="fig">{tokens(m.usage.tokens)} · {usd(m.usage.usd)}</span>
      </div>
      <div className="flex flex-wrap items-center gap-2"><Pill tone={rec.tone} dot>توصیه: {rec.fa}</Pill><Confidence v={m.confidence} /></div>
      <p className="text-[14px] leading-7 text-ink"><MdInline text={m.summary_fa} /></p>
      <div className="flex flex-col gap-1 rounded-[12px] border-s-2 border-[var(--hq-neg-line)] bg-neg-soft p-3">
        <span className="text-[12px] font-semibold text-neg">{m.mode === 'devil' ? 'چرا نه' : 'قوی‌ترین استدلال مخالف'}</span>
        <Md text={m.against_md} className="flex flex-col gap-1 text-[13px] leading-6 text-ink" />
      </div>
      {m.options.length ? (
        <div className="grid gap-2 sm:grid-cols-2">
          {m.options.map((o, i) => (
            <div key={i} className="flex flex-col gap-1 rounded-[12px] bg-tile p-3 text-[12px] leading-6">
              <span className="text-[13px] font-semibold text-ink"><MdInline text={o.title_fa} /></span>
              <span className="text-pos">+ <span className="text-sec"><MdInline text={o.pros_md} /></span></span>
              <span className="text-neg">− <span className="text-sec"><MdInline text={o.cons_md} /></span></span>
            </div>
          ))}
        </div>
      ) : null}
      {m.risks.length ? (
        <ul className="flex flex-col gap-1.5">
          {m.risks.map((r, i) => (
            <li key={i} className="flex flex-wrap items-center gap-2 rounded-[10px] bg-tile px-3 py-2 text-[12px]">
              <span className="min-w-0 flex-1 text-[13px] text-ink"><MdInline text={r.title_fa} /></span>
              <span className="text-muted">احتمال {LEVEL3[r.likelihood]} · اثر {LEVEL3[r.impact]}</span>
              <span className="w-full text-sec">کاهش: <MdInline text={r.mitigation_fa} /></span>
            </li>
          ))}
        </ul>
      ) : null}
      {m.questions.length ? (
        <div className="flex flex-col gap-1"><span className="text-[12px] font-semibold text-sec">از پیشنهاددهنده بپرس</span>
          <ul className="flex list-disc flex-col gap-1 pr-5 text-[13px] leading-6 text-ink marker:text-gold-ink">{m.questions.map((x) => <li key={x}><MdInline text={x} /></li>)}</ul></div>
      ) : null}
      {m.citations.length ? <div className="flex flex-wrap gap-1.5">{m.citations.map((c) => <RefChip key={`${c.kind}${c.ref}`} r={c.ref} tone="neutral" />)}</div> : null}
      {m.second_opinion || m.third_opinion ? (
        <div className="grid gap-2 lg:grid-cols-2">
          {m.second_opinion ? <OpinionCard o={m.second_opinion} title="نظر دوم" /> : null}
          {m.third_opinion ? <OpinionCard o={m.third_opinion} title="نظر سوم" /> : null}
        </div>
      ) : m.mode === 'standard' ? <p className="text-[11px] text-muted">نظر دوم و سوم این یادداشت نیامد (بازیکن در دسترس نبود یا سقف روزش پر بود)؛ هیچ جابه‌جایی پنهانی نیست.</p> : null}
    </div>
  );
}

/** The decision memo (§21.1): standard or devil's advocate, bound to the card's version, with the substitutes' opinions beside it. */
export function MemoBlock({ d }: { d: Decision18 }) {
  const pending = d.status === 'pending';
  const [mode, setMode] = useState<MemoMode>('standard');
  const q = useDecisionMemo(d.ref, mode);
  const req = useRequestMemo();
  const toast = useToast();
  if (!pending && !d.memos?.length) return null;
  const m = q.data ?? null;
  const ask = async () => { try { await req.mutateAsync({ ref: d.ref, mode }); toast({ tone: 'info', text: 'مشاور شروع به نوشتن کرد.' }); } catch (e) { toast({ tone: 'error', text: faError(e) }); } };
  const st = m ? MEMO_STATE[m.state] ?? MEMO_STATE.ready! : null;
  return (
    <Section title="یادداشت مشاور" action={<div className="flex gap-1.5"><FilterChip selected={mode === 'standard'} onClick={() => setMode('standard')}>استاندارد</FilterChip><FilterChip selected={mode === 'devil'} onClick={() => setMode('devil')}>مخالف‌خوان</FilterChip></div>}>
      <div className="flex flex-col gap-3 rounded-[14px] bg-card p-3">
        {q.isLoading ? <Skeleton className="h-24" /> : !m ? (
          <div className="flex flex-wrap items-center gap-3">
            <p className="min-w-0 flex-[1_1_14rem] text-[13px] leading-6 text-sec">{mode === 'devil' ? 'یادداشت مخالف‌خوان میگوید چرا نه؛ قوی‌ترین استدلال‌ها علیه همین کارت.' : 'یادداشت رسمی: خلاصه، گزینه‌ها، قوی‌ترین استدلال مخالف، ریسک‌ها و پرسش‌ها، با نظر دوم و سوم بازیکن‌های ذخیره.'}</p>
            {pending ? <Button size="sm" variant="silver" icon="advisor" loading={req.isPending} onClick={ask}>یادداشت بخواه</Button> : null}
          </div>
        ) : (
          <>
            {st && m.state !== 'ready' ? <div className="flex items-center gap-2"><Pill tone={st.tone} live={st.live} dot={!st.live}>{st.fa}</Pill>{m.state === 'stale' && pending ? <Button size="sm" variant="text" icon="refresh" loading={req.isPending} onClick={ask}>یادداشت تازه</Button> : null}</div> : null}
            {m.state === 'writing' ? <div className="flex flex-col gap-2"><Skeleton className="h-4 w-2/3" /><Skeleton className="h-16" /><p className="text-[12px] text-muted">مشاور با بسته‌ی شاهد کارت مینویسد؛ هم‌زمان GPT و DeepSeek همان بسته را بی‌دیدن یادداشت میخوانند.</p></div> : <MemoView m={m} />}
          </>
        )}
      </div>
    </Section>
  );
}

// ---------------------------------------------------------- reminders (§21.8) --
export function WaitingLine({ d }: { d: Decision18 }) {
  if (d.status !== 'pending' || d.waiting_h == null || d.waiting_h < 1) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 text-[12px] text-sec">
      <span className="inline-flex items-center gap-1"><Icon name="time" size={14} />منتظر تو، {hoursFa(d.waiting_h)}</span>
      {(d.reminders ?? []).map((r) => <span key={r.kind} className="rounded-full bg-tile px-2 py-0.5 text-[11px] text-muted" title={jDateTime(r.at)}>یادآوری {REMINDER[r.kind] ?? r.kind}</span>)}
    </div>
  );
}

// ------------------------------------------------------- the digital CEO (§21.10) --
export function PredictionLine({ d }: { d: Decision18 }) {
  const p = d.digital_ceo_prediction;
  if (!p) return null;
  const v = VERDICT3[p.verdict] ?? VERDICT3.approve!;
  return (
    <Link href="/digital-ceo" className="flex flex-wrap items-center gap-2 rounded-[14px] bg-tile p-3 text-[12px] text-sec hover:bg-hover">
      <span className="flex size-8 flex-none items-center justify-center rounded-full bg-card text-gold-ink"><Icon name="holding" size={16} /></span>
      <span className="text-[13px] font-semibold text-ink">مدیر کل دیجیتال</span>
      <span>پیش از تصمیم تو پیش‌بینی کرده بود:</span>
      <Pill tone={v.tone} dot>{v.fa}</Pill><Confidence v={p.confidence} tone="silver" />
      <span className="text-muted">{p.method === 'model' ? 'با مدل' : 'روش پایه'}</span>
      <span className="flex-1" />
      {p.correct == null ? null : <Pill tone={p.correct ? 'pos' : 'neg'} icon={p.correct ? 'seal' : 'reject'}>{p.correct ? 'درست' : 'نادرست'}</Pill>}
    </Link>
  );
}
