'use client';

// ⟨1.12⟩ Contract §30 «خط تولید»: a company's lines and the template gallery that makes a draft, and one line's page — header (state,
// mode and «N از 7 اجرای خوب», caps), the steps as cards in order (prompt with {{variables}} as chips, settings, special editors for
// voice, cover and publish, a test of that step alone), the whole-line dry run, versions with revert, and a copy for another company.

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { rruleFa } from '@/components/v14/bits';
import { Button } from '@/components/ui/button';
import { Dialog, Sheet } from '@/components/ui/overlay';
import { Card, Empty, ErrorState, PageHeader, Pill, SectionTitle, Segmented, Skeleton, Switch } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { useCompanies } from '@/lib/api/hooks';
import {
  BASE_VARS, GATE_FA, platformFa, promptVars, stepKind, useCompanyLines, useCreateLine, useLibrary, useLine, useLineActions, useLineRuns, useLineVersions,
  useTemplates, useVoices, type Caps, type Gate, type Line, type StepDef, type StepRun, type Template,
} from '@/lib/api/v30';
import { fileUrl } from '@/lib/api/v13';
import { cx, jDate, jDateTime } from '@/lib/format';
import { LineInsights } from '@/components/v31/insights';
import { FaPara, FaText, KindIcon, LineStatePill, OutputView, RunStatePill, fig } from './bits';

const field = 'w-full rounded-[10px] border border-strong bg-tile px-3 text-[14px] text-ink outline-none focus:border-gold-ink';
const errText = (e: unknown, fallback: string) => (e instanceof ApiError ? e.messageFa : fallback);

function useName() {
  const { data } = useCompanies();
  return { name: (code: string) => data?.find((c) => c.code === code)?.name_fa ?? code, companies: data };
}
const channelKind = (platform: string) => platform.split('_')[0] === 'site' ? 'site' : platform.split('_')[0]!;

// ======================================================================================== the company's tab ==
export function CompanyLines({ code }: { code: string }) {
  const q = useCompanyLines(code);
  const [open, setOpen] = useState(false);
  if (q.isLoading) return <div className="grid gap-3 lg:grid-cols-2">{Array.from({ length: 2 }, (_, i) => <Skeleton key={i} className="h-36 rounded-[16px]" />)}</div>;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (q.data === null) return <Card><Empty icon="video" title="خط تولید بعد از به‌روزرسانی ستاد میاید" body="هر خط، قدم‌های ساخت و انتشار یک صفحه را دارد و خودش اجرا میشود." /></Card>;
  const lines = q.data ?? [];
  return (
    <div className="flex flex-col gap-3">
      <SectionTitle title="خط تولید" note="هر خط یک صفحه یا کانال دارد؛ قدم‌ها را یک بار میچینی و خودش اجرا میشود"
        action={<Button variant="primary" size="sm" icon="add" onClick={() => setOpen(true)}>خط تازه</Button>} />
      {!lines.length ? (
        <Card><Empty icon="video" title="هنوز خطی نیست" body="از روی یک الگو یک خط پیش‌نویس بساز؛ هر قدمش را میتوانی عوض کنی."
          action={<Button variant="primary" icon="add" onClick={() => setOpen(true)}>خط تازه</Button>} /></Card>
      ) : (
        <div className="grid items-start gap-3 lg:grid-cols-2">{lines.map((l) => <LineCard key={l.ref} line={l} />)}</div>
      )}
      <NewLineSheet code={code} open={open} onOpenChange={setOpen} />
    </div>
  );
}

function LineCard({ line }: { line: Line }) {
  return (
    <Link href={`/lines/${line.ref}`} className="group min-w-0" aria-label={`خط ${line.title_fa}`}>
      <Card className="hq-rise flex h-full flex-col gap-3 p-5 transition-colors group-hover:bg-tile">
        <div className="flex items-center gap-3">
          <KindIcon kind={line.steps.find((s) => s.kind === 'publish')?.kind ?? 'publish'} />
          <span className="flex min-w-0 flex-1 flex-col">
            <span className="text-[15px] font-semibold"><FaText text={line.title_fa} /></span>
            <span className="text-[12px] text-muted">{platformFa(line.platform)} · <FaText text={line.channel.subject} /></span>
          </span>
          <LineStatePill state={line.state} />
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-sec">
          <span>{line.mode === 'auto' ? 'خودکار' : 'پیش‌نویس'}</span>
          <span>اجرای بعدی: {line.next_run_at ? jDateTime(line.next_run_at) : line.schedule ? rruleFa(line.schedule) : '—'}</span>
          <span className="inline-flex items-center gap-1.5">آخرین اجرا: {line.last_run ? <><RunStatePill state={line.last_run.state} />{jDate(line.last_run.at)}</> : '—'}</span>
        </div>
      </Card>
    </Link>
  );
}

function NewLineSheet({ code, open, onOpenChange }: { code: string; open: boolean; onOpenChange: (v: boolean) => void }) {
  const router = useRouter();
  const toast = useToast();
  const tpl = useTemplates();
  const create = useCreateLine(code);
  const [pick, setPick] = useState<Template | null>(null);
  const [title, setTitle] = useState('');
  const [subject, setSubject] = useState('');
  const choose = (t: Template) => { setPick(t); setTitle(t.title_fa); setSubject(''); };
  const go = () => {
    if (!pick) return;
    create.mutate({ template: pick.key, platform: pick.platform, channel: { kind: channelKind(pick.platform), subject: subject.trim() }, title_fa: title.trim() }, {
      onSuccess: (l) => { onOpenChange(false); setPick(null); toast({ tone: 'ok', text: 'خط پیش‌نویس ساخته شد.' }); router.push(`/lines/${l.ref}`); },
      onError: (e) => toast({ tone: 'error', text: errText(e, 'خط ساخته نشد؛ دوباره بزن.') }),
    });
  };
  return (
    <Sheet open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) setPick(null); }} title={pick ? 'خط تازه' : 'الگوی خط را انتخاب کن'}
      description={pick ? pick.title_fa : 'هر الگو برنامه‌ی قدم‌هاست؛ بعد از ساختن هرچه خواستی عوض کن'}
      footer={pick ? <div className="flex gap-2"><Button variant="primary" loading={create.isPending} disabled={!title.trim() || !subject.trim()} onClick={go}>بساز</Button><Button onClick={() => setPick(null)}>الگوی دیگر</Button></div> : undefined}>
      {!pick ? (
        tpl.isLoading ? <Skeleton className="h-40 rounded-[16px]" /> : tpl.error ? <ErrorState error={tpl.error} onRetry={() => tpl.refetch()} /> : !tpl.data?.length ? <Empty icon="video" title="الگویی نیست" /> : (
          <ul className="flex flex-col gap-2" aria-label="الگوها">
            {tpl.data.map((t) => (
              <li key={t.key}>
                <button type="button" onClick={() => choose(t)} aria-label={`الگوی ${t.title_fa}`} className="hq-tile flex w-full flex-col gap-1.5 rounded-[14px] bg-tile p-4 text-start transition-colors hover:bg-hover">
                  <span className="flex items-center gap-2"><span className="flex-1 text-[14px] font-semibold">{t.title_fa}</span><Pill tone="silver">{platformFa(t.platform)}</Pill></span>
                  <FaPara text={t.outputs_fa} className="text-[12px] leading-5 text-sec" />
                  <span className="text-[11px] text-muted"><span className="fig">{t.steps.length}</span> قدم</span>
                </button>
              </li>
            ))}
          </ul>
        )
      ) : (
        <div className="flex flex-col gap-4">
          <label className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">نام خط</span><input value={title} onChange={(e) => setTitle(e.target.value)} className={cx(field, 'h-11')} aria-label="نام خط" /></label>
          <label className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">{platformFa(pick.platform)}: نام صفحه یا کانال</span><input value={subject} onChange={(e) => setSubject(e.target.value)} dir="auto" placeholder="مثلاً نام کاربری صفحه" className={cx(field, 'h-11')} aria-label="صفحه یا کانال" /></label>
          <p className="text-[12px] leading-6 text-muted">خط تازه پیش‌نویس است؛ انتشارش تا هفت اجرای خوب با مُهر خودت انجام میشود.</p>
        </div>
      )}
    </Sheet>
  );
}

// ================================================================================================ one line ==
type Draft = { title_fa: string; schedule: string | null; caps: Caps; steps: StepDef[] };
const draftOf = (l: Line): Draft => ({ title_fa: l.title_fa, schedule: l.schedule, caps: l.caps, steps: l.steps });
const SCHEDULES: Array<{ fa: string; rrule: string | null }> = [
  { fa: 'دستی', rrule: null }, { fa: 'هر روز ۰۹:۰۰', rrule: 'FREQ=DAILY;BYHOUR=9;BYMINUTE=0' }, { fa: 'هر روز ۱۸:۰۰', rrule: 'FREQ=DAILY;BYHOUR=18;BYMINUTE=0' },
  { fa: 'شنبه‌ها ۱۰:۰۰', rrule: 'FREQ=WEEKLY;BYDAY=SA;BYHOUR=10;BYMINUTE=0' },
];

export function LineView({ lineRef }: { lineRef: string }) {
  const q = useLine(lineRef);
  const { name } = useName();
  const line = q.data;
  const act = useLineActions(lineRef);
  const toast = useToast();
  const router = useRouter();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [note, setNote] = useState('');
  const [versions, setVersions] = useState(false);
  const [copy, setCopy] = useState(false);
  // The draft starts again from each saved version (adjusting state while rendering, not in an effect).
  const [seen, setSeen] = useState('');
  const key = line ? `${line.ref}:${line.version}` : '';
  if (line && key !== seen) { setSeen(key); setDraft(draftOf(line)); setNote(''); }

  if (q.isLoading || (line && !draft)) return <div className="flex flex-col gap-4"><Skeleton className="h-24 rounded-[16px]" /><Skeleton className="h-64 rounded-[16px]" /></div>;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!line || !draft) return <Card><Empty icon="video" title="این خط پیدا نشد" action={<Link href="/companies" className="text-[13px] font-semibold text-gold-ink">شرکت‌ها</Link>} /></Card>;

  const dirty = JSON.stringify(draft) !== JSON.stringify(draftOf(line));
  const setStep = (i: number, s: StepDef) => setDraft({ ...draft, steps: draft.steps.map((x, j) => (j === i ? s : x)) });
  const save = () => act.save.mutate({ title_fa: draft.title_fa, schedule: draft.schedule, caps: draft.caps, steps: draft.steps, note_fa: note.trim() || undefined }, {
    onSuccess: (l) => toast({ tone: 'ok', text: `نسخه‌ی ${fig(l.version)} ذخیره شد.` }),
    onError: (e) => toast({ tone: 'error', text: errText(e, 'ذخیره نشد؛ دوباره بزن.') }),
  });
  const run = (dry: boolean) => act.run.mutate({ dry }, {
    onSuccess: (r) => { toast({ tone: 'ok', text: dry ? 'آزمایش کامل شروع شد.' : 'اجرا شروع شد.' }); router.push(`/line-runs/${r.ref}`); },
    onError: (e) => toast({ tone: 'error', text: errText(e, 'اجرا شروع نشد.') }),
  });
  const ready = line.good_runs >= line.auto_after;
  const setMode = (m: 'draft' | 'auto') => act.mode.mutate(m, {
    onSuccess: () => toast({ tone: 'ok', text: m === 'auto' ? 'خط خودکار شد؛ بدون مُهر منتشر میکند.' : 'خط به پیش‌نویس برگشت؛ انتشارش دوباره مُهر میخواهد.' }),
    onError: (e) => toast({ tone: 'error', text: errText(e, 'تغییر نکرد.') }),
  });

  return (
    <div className="flex flex-col gap-4">
      <PageHeader eyebrow={<span className="inline-flex items-center gap-1.5"><CompanyMark code={line.company} height={12} mono />{name(line.company)} · {platformFa(line.platform)} · {line.ref}</span>} title={<FaText text={line.title_fa} />}
        actions={<>
          <LineStatePill state={line.state} />
          <Button size="sm" icon={line.state === 'on' ? 'pause' : 'resume'} loading={act.state.isPending} aria-label={line.state === 'on' ? 'توقف خط' : 'روشن کردن خط'}
            onClick={() => act.state.mutate(line.state === 'on' ? 'paused' : 'on', { onError: (e) => toast({ tone: 'error', text: errText(e, 'تغییر نکرد.') }) })}>{line.state === 'on' ? 'توقف' : 'روشن کن'}</Button>
        </>} />

      {/* header card: channel, schedule, mode, caps */}
      <Card as="section" className="hq-rise flex flex-col gap-4 p-5" aria-label="مشخصات خط">
        <div className="grid gap-4 md:grid-cols-2">
          <label className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">نام خط</span>
            <input value={draft.title_fa} onChange={(e) => setDraft({ ...draft, title_fa: e.target.value })} className={cx(field, 'h-11')} aria-label="نام خط" /></label>
          <div className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">کانال</span>
            <span className="flex h-11 items-center text-[14px]"><FaText text={`${line.channel.kind}: ${line.channel.subject}`} /></span></div>
        </div>
        <div className="flex flex-col gap-2">
          <span className="text-[12px] text-sec">زمان‌بندی{draft.schedule ? `: ${rruleFa(draft.schedule)}` : ''}</span>
          <div className="no-scrollbar flex gap-2 overflow-x-auto" role="group" aria-label="زمان‌بندی">
            {SCHEDULES.map((s) => (
              <button key={s.fa} type="button" aria-pressed={draft.schedule === s.rrule} onClick={() => setDraft({ ...draft, schedule: s.rrule })}
                className={cx('h-9 flex-none rounded-full px-3.5 text-[13px] font-semibold', draft.schedule === s.rrule ? 'bg-gold text-on-gold' : 'bg-tile text-sec hover:bg-hover')}>{s.fa}</button>
            ))}
            {draft.schedule && !SCHEDULES.some((s) => s.rrule === draft.schedule) ? <Pill tone="gold">{rruleFa(draft.schedule)}</Pill> : null}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3 rounded-[12px] bg-tile p-3" aria-label="حالت خط">
          <Pill tone={line.mode === 'auto' ? 'gold' : 'silver'} icon={line.mode === 'auto' ? 'send' : 'seal'}>{line.mode === 'auto' ? 'خودکار' : 'پیش‌نویس'}</Pill>
          <span className="min-w-0 flex-[1_1_14rem] text-[13px] text-sec">
            {line.mode === 'auto' ? 'بدون مُهر منتشر میکند.' : <><span className="fig">{line.good_runs}</span> از <span className="fig">{line.auto_after}</span> اجرای خوب؛ انتشار هر اجرا مُهر تو را میخواهد.</>}
          </span>
          {line.mode === 'draft' ? <Button size="sm" variant="primary" icon="seal" disabled={!ready} loading={act.mode.isPending} onClick={() => setMode('auto')}>خودکار کن</Button>
            : <Button size="sm" icon="back" loading={act.mode.isPending} onClick={() => setMode('draft')}>برگرد به پیش‌نویس</Button>}
        </div>
        <div className="grid gap-3 sm:grid-cols-3" role="group" aria-label="سقف‌ها">
          {([['runs_per_day', 'اجرا در روز'], ['tokens_per_run', 'توکن هر اجرا'], ['opus_per_day', 'ساخت نهایی در روز']] as const).map(([k, fa]) => (
            <label key={k} className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">{fa}</span>
              <input type="number" min={0} inputMode="numeric" value={draft.caps[k]} aria-label={fa} dir="ltr" onChange={(e) => setDraft({ ...draft, caps: { ...draft.caps, [k]: Math.max(0, Number(e.target.value) || 0) } })} className={cx(field, 'h-11 text-left')} /></label>
          ))}
        </div>
        <p className="text-[11px] text-muted">بالا بردن سقف مُهر میخواهد.</p>
      </Card>

      {/* actions */}
      <div className="flex flex-wrap items-center gap-2">
        <Button icon="refresh" loading={act.run.isPending && act.run.variables?.dry === true} disabled={dirty} onClick={() => run(true)}>آزمایش کامل</Button>
        <Button icon="send" loading={act.run.isPending && act.run.variables?.dry === false} disabled={dirty || line.state === 'paused'} onClick={() => run(false)}>اجرا کن</Button>
        <Button icon="time" onClick={() => setVersions(true)}>نسخه‌ها <span className="fig">{line.version}</span></Button>
        <Button icon="share" onClick={() => setCopy(true)}>کپی برای شرکت دیگر</Button>
        {dirty ? <span className="text-[12px] text-warn">تغییرها ذخیره نشده‌اند؛ آزمایش روی نسخه‌ی ذخیره‌شده انجام میشود.</span> : null}
      </div>

      <LineInsights lineRef={lineRef} />

      {/* steps */}
      <ol className="flex flex-col gap-3" aria-label="قدم‌ها">
        {draft.steps.map((s, i) => (
          <li key={s.key}><StepCard line={line} step={s} index={i} onChange={(x) => setStep(i, x)} dirty={dirty} test={act.test} /></li>
        ))}
      </ol>

      <RecentRuns lineRef={lineRef} />

      {dirty ? (
        <div className="sticky bottom-3 z-10 flex flex-wrap items-center gap-2 rounded-[16px] bg-raised p-3 shadow-[0_8px_32px_rgba(0,0,0,.35)]" role="region" aria-label="ذخیره">
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="یادداشت نسخه (اختیاری)" aria-label="یادداشت نسخه" className={cx(field, 'h-10 min-w-0 flex-[1_1_12rem]')} />
          <Button variant="primary" icon="seal" loading={act.save.isPending} onClick={save}>ذخیره، نسخه‌ی تازه</Button>
          <Button onClick={() => setDraft(draftOf(line))}>پس بگیر</Button>
        </div>
      ) : null}

      <VersionsSheet lineRef={lineRef} open={versions} onOpenChange={setVersions} current={line.version} />
      <CopyDialog line={line} open={copy} onOpenChange={setCopy} />
    </div>
  );
}

function RecentRuns({ lineRef }: { lineRef: string }) {
  const q = useLineRuns(lineRef);
  return (
    <Card as="section" className="flex flex-col gap-2 p-5" aria-label="اجراهای این خط">
      <SectionTitle title="اجراها" note="تازه‌ترین بالا" />
      {q.isLoading ? <Skeleton className="h-16" /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !q.data?.length ? <p className="py-2 text-[13px] text-muted">هنوز اجرایی نبوده؛ «آزمایش کامل» را بزن.</p> : (
        <ul className="flex flex-col">
          {q.data.slice(0, 8).map((r) => (
            <li key={r.ref}>
              <Link href={`/line-runs/${r.ref}`} className="flex flex-wrap items-center gap-3 border-t border-div py-3 first:border-0 hover:text-gold-ink">
                <span className="fig text-[13px] font-semibold">{r.ref}</span>
                <RunStatePill state={r.state} />
                {r.dry ? <Pill tone="silver">آزمایشی</Pill> : null}
                <span className="flex-1 text-[12px] text-muted">{jDateTime(r.at)}</span>
                <span className="text-[12px] text-sec"><span className="fig">{fig(r.cost.tokens)}</span> توکن</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

// ================================================================================================ a step ==
function StepCard({ line, step, index, onChange, dirty, test }: {
  line: Line; step: StepDef; index: number; onChange: (s: StepDef) => void; dirty: boolean; test: ReturnType<typeof useLineActions>['test'];
}) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [result, setResult] = useState<StepRun | null>(null);
  const area = useRef<HTMLTextAreaElement>(null);
  const k = stepKind(step.kind);
  const chips = useMemo(() => [...new Set([...BASE_VARS, ...step.inputs, ...promptVars(step.prompt_fa)])], [step.inputs, step.prompt_fa]);
  const insert = (v: string) => {
    const el = area.current;
    const text = step.prompt_fa ?? '';
    const a = el?.selectionStart ?? text.length;
    const b = el?.selectionEnd ?? a;
    const ins = `{{${v}}}`;
    onChange({ ...step, prompt_fa: text.slice(0, a) + ins + text.slice(b) });
    requestAnimationFrame(() => { el?.focus(); el?.setSelectionRange(a + ins.length, a + ins.length); });
  };
  const setSetting = (key: string, v: unknown) => onChange({ ...step, settings: { ...step.settings, [key]: v } });
  const runTest = () => test.mutate({ key: step.key }, {
    onSuccess: (r) => { setResult(r); setOpen(true); },
    onError: (e) => toast({ tone: 'error', text: errText(e, 'آزمایش این قدم انجام نشد.') }),
  });
  return (
    <Card as="article" className={cx('hq-rise flex flex-col gap-3 p-4', !step.enabled && 'opacity-70')} aria-label={`قدم ${index + 1}: ${step.title_fa}`}>
      <div className="flex flex-wrap items-center gap-3">
        <span className="fig w-5 text-center text-[12px] text-muted">{index + 1}</span>
        <KindIcon kind={step.kind} />
        <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex min-w-0 flex-[1_1_12rem] flex-col text-start">
          <span className="text-[14px] font-semibold"><FaText text={step.title_fa} /></span>
          <span className="text-[11px] text-muted">{k.fa} · {GATE_FA[step.gate]}{step.optional ? ' · اختیاری' : ''}</span>
        </button>
        {step.optional ? <Switch checked={step.enabled} onChange={(v) => onChange({ ...step, enabled: v })} label={`${step.title_fa} فعال باشد`} /> : null}
        <Button size="sm" icon="refresh" loading={test.isPending && test.variables?.key === step.key} disabled={dirty || !step.enabled} title={dirty ? 'اول ذخیره کن' : undefined} onClick={runTest}>آزمایش همین مرحله</Button>
        <button type="button" onClick={() => setOpen(!open)} aria-label={open ? 'بستن' : 'باز کردن'} className="flex size-9 items-center justify-center rounded-full text-sec hover:bg-hover"><Icon name="chevron" size={16} className={open ? 'rotate-180' : ''} /></button>
      </div>
      {open ? (
        <div className="flex flex-col gap-4 border-t border-div pt-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">عنوان</span>
              <input value={step.title_fa} onChange={(e) => onChange({ ...step, title_fa: e.target.value })} className={cx(field, 'h-10')} aria-label="عنوان قدم" /></label>
            <div className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">چه کسی تأیید میکند</span>
              <Segmented<Gate> label="تأیید" value={step.gate} onChange={(g) => onChange({ ...step, gate: g })} options={(['auto', 'owner', 'ceo'] as Gate[]).map((g) => ({ value: g, label: GATE_FA[g] }))} /></div>
          </div>
          {step.prompt_fa !== null ? (
            <div className="flex flex-col gap-2">
              <span className="text-[12px] text-sec">متن دستور</span>
              <textarea ref={area} value={step.prompt_fa} onChange={(e) => onChange({ ...step, prompt_fa: e.target.value })} rows={7} dir="auto" aria-label={`دستور ${step.title_fa}`}
                className={cx(field, 'py-2.5 leading-7')} />
              <div className="flex flex-wrap gap-1.5" role="group" aria-label="متغیرها">
                {chips.map((v) => <button key={v} type="button" onClick={() => insert(v)} aria-label={`درج ${v}`} className="inline-flex h-7 items-center rounded-full bg-gold-soft px-2.5 text-[12px] font-semibold text-gold-ink hover:bg-[var(--hq-gold-hover-soft)]"><span dir="ltr">{`{{${v}}}`}</span></button>)}
              </div>
            </div>
          ) : null}
          <SettingsEditor line={line} step={step} set={setSetting} />
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">حداکثر تلاش</span>
              <input type="number" min={1} max={3} value={step.max_attempts} dir="ltr" onChange={(e) => onChange({ ...step, max_attempts: Math.min(3, Math.max(1, Number(e.target.value) || 1)) })} className={cx(field, 'h-10 text-left')} aria-label="حداکثر تلاش" /></label>
            <label className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">مهلت (ثانیه)</span>
              <input type="number" min={1} value={step.timeout_s} dir="ltr" onChange={(e) => onChange({ ...step, timeout_s: Math.max(1, Number(e.target.value) || 1) })} className={cx(field, 'h-10 text-left')} aria-label="مهلت" /></label>
          </div>
        </div>
      ) : null}
      {result ? (
        <div className="hq-settle flex flex-col gap-2 rounded-[12px] bg-tile p-3" aria-label="نتیجه‌ی آزمایش">
          <div className="flex items-center gap-2 text-[12px] text-sec"><Pill tone={result.state === 'done' ? 'pos' : 'neg'} dot>{result.state === 'done' ? 'آزمایش شد' : 'ناموفق'}</Pill><span>فقط جواب این قدم؛ چیزی نگه داشته نشد</span>
            <button type="button" onClick={() => setResult(null)} className="ms-auto text-gold-ink hover:underline">بستن</button></div>
          {result.error_fa ? <FaPara text={result.error_fa} className="text-[13px] text-neg" /> : null}
          <OutputView out={result.output} kind={result.kind} />
        </div>
      ) : null}
    </Card>
  );
}

const SPECIAL: Record<string, string[]> = { tts: ['speaker', 'style'], cover: ['folder'], publish: ['when', 'time', 'where'] };

function SettingsEditor({ line, step, set }: { line: Line; step: StepDef; set: (k: string, v: unknown) => void }) {
  const s = step.settings ?? {};
  const hide = new Set(SPECIAL[step.kind] ?? []);
  const rest = Object.entries(s).filter(([k]) => !hide.has(k));
  return (
    <div className="flex flex-col gap-3">
      {step.kind === 'tts' ? <VoicePicker speaker={String(s.speaker ?? '')} style={String(s.style ?? '')} set={set} /> : null}
      {step.kind === 'cover' ? <CoverPicker company={line.company} folder={String(s.folder ?? '')} set={set} /> : null}
      {step.kind === 'publish' ? <PublishEditor s={s} set={set} /> : null}
      {rest.length ? (
        <div className="flex flex-col gap-2" role="group" aria-label="تنظیم‌ها">
          <span className="text-[12px] text-sec">تنظیم‌ها</span>
          {rest.map(([k, v]) => (
            <label key={k} className="flex flex-wrap items-center gap-2">
              <span dir="ltr" className="w-32 flex-none text-left text-[12px] text-muted">{k}</span>
              {typeof v === 'boolean' ? <Switch checked={v} onChange={(x) => set(k, x)} label={k} />
                : typeof v === 'number' ? <input type="number" value={v} dir="ltr" onChange={(e) => set(k, Number(e.target.value))} className={cx(field, 'h-10 min-w-0 flex-1 text-left')} aria-label={k} />
                : typeof v === 'object' && v !== null ? <code dir="ltr" className="min-w-0 flex-1 break-all text-[11px] text-sec">{JSON.stringify(v)}</code>
                : <input value={String(v ?? '')} dir="auto" onChange={(e) => set(k, e.target.value)} className={cx(field, 'h-10 min-w-0 flex-1')} aria-label={k} />}
            </label>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function VoicePicker({ speaker, style, set }: { speaker: string; style: string; set: (k: string, v: unknown) => void }) {
  const q = useVoices();
  const [playing, setPlaying] = useState<string | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const play = (name: string, file: string) => {
    audio.current?.pause();
    if (playing === name) { setPlaying(null); return; }
    const a = new Audio(fileUrl(file));
    audio.current = a;
    a.onended = () => setPlaying(null);
    setPlaying(name);
    void a.play().catch(() => setPlaying(null));
  };
  useEffect(() => () => audio.current?.pause(), []);
  return (
    <div className="flex flex-col gap-2" role="group" aria-label="گوینده">
      <span className="text-[12px] text-sec">گوینده</span>
      {q.isLoading ? <Skeleton className="h-20" /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !q.data?.length ? <p className="text-[12px] text-muted">فهرست گوینده‌ها هنوز نیامده؛ هاب باید به استودیوی هوش مصنوعی وصل باشد.</p> : (
        <ul className="grid gap-2 sm:grid-cols-2">
          {q.data.map((v) => (
            <li key={v.name} className={cx('flex items-center gap-2 rounded-[12px] p-2 pe-3', speaker === v.name ? 'bg-gold-soft' : 'bg-tile')}>
              <button type="button" aria-pressed={speaker === v.name} onClick={() => set('speaker', v.name)} className="flex min-w-0 flex-1 flex-col text-start">
                <span className="text-[13px] font-semibold">{v.title_fa}</span><span className="text-[11px] text-muted" dir="ltr">{v.name} · {v.gender}</span>
              </button>
              {v.sample_file ? <Button size="sm" icon={playing === v.name ? 'stop' : 'resume'} aria-label={`نمونه‌ی صدای ${v.title_fa}`} onClick={() => play(v.name, v.sample_file!)}>نمونه</Button> : null}
            </li>
          ))}
        </ul>
      )}
      <label className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">سبک خواندن</span>
        <input value={style} onChange={(e) => set('style', e.target.value)} dir="auto" placeholder="مثلاً آرام و گرم" className={cx(field, 'h-10')} aria-label="سبک خواندن" /></label>
    </div>
  );
}

function CoverPicker({ company, folder, set }: { company: string; folder: string; set: (k: string, v: unknown) => void }) {
  const q = useLibrary(company, 'cover_folder');
  const holding = useLibrary(null, 'cover_folder');
  const all = [...(q.data ?? []), ...(holding.data ?? []).filter((a) => !a.company)];
  return (
    <div className="flex flex-col gap-2" role="group" aria-label="پوشه‌ی کاور">
      <span className="text-[12px] text-sec">پوشه‌ی کاور</span>
      {q.isLoading ? <Skeleton className="h-12" /> : !all.length ? <p className="text-[12px] text-muted">پوشه‌ای نیست؛ در <Link href="/library" className="font-semibold text-gold-ink">کتابخانه‌ی تولید</Link> یکی بساز.</p> : (
        <div className="flex flex-wrap gap-2">
          {all.map((a) => (
            <button key={a.id} type="button" aria-pressed={folder === a.id} onClick={() => set('folder', a.id)}
              className={cx('inline-flex h-10 items-center gap-2 rounded-full px-4 text-[13px] font-semibold', folder === a.id ? 'bg-gold text-on-gold' : 'bg-tile text-sec hover:bg-hover')}>
              <Icon name="image" size={16} />{a.title_fa}<span className="fig text-[11px] opacity-70">{a.files.length}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

const WHEN: Array<{ value: string; fa: string }> = [{ value: 'schedule', fa: 'طبق زمان‌بندی خط' }, { value: 'asap', fa: 'همین که آماده شد' }, { value: 'time', fa: 'ساعت ثابت' }];
function PublishEditor({ s, set }: { s: Record<string, unknown>; set: (k: string, v: unknown) => void }) {
  const when = String(s.when ?? 'schedule');
  return (
    <div className="flex flex-col gap-2" role="group" aria-label="انتشار">
      <span className="text-[12px] text-sec">کی و کجا منتشر شود</span>
      <Segmented label="زمان انتشار" value={when} onChange={(v) => set('when', v)} options={WHEN.map((w) => ({ value: w.value, label: w.fa }))} />
      <div className="grid gap-3 sm:grid-cols-2">
        {when === 'time' ? <label className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">ساعت (به وقت تهران)</span>
          <input type="time" value={String(s.time ?? '18:00')} dir="ltr" onChange={(e) => set('time', e.target.value)} className={cx(field, 'h-10 text-left')} aria-label="ساعت انتشار" /></label> : null}
        <label className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">کجا (صفحه یا کانال)</span>
          <input value={String(s.where ?? '')} onChange={(e) => set('where', e.target.value)} dir="auto" placeholder="پیش‌فرض: کانال خط" className={cx(field, 'h-10')} aria-label="مقصد انتشار" /></label>
      </div>
    </div>
  );
}

// ============================================================================================== versions, copy ==
function VersionsSheet({ lineRef, open, onOpenChange, current }: { lineRef: string; open: boolean; onOpenChange: (v: boolean) => void; current: number }) {
  const q = useLineVersions(lineRef, open);
  const act = useLineActions(lineRef);
  const toast = useToast();
  return (
    <Sheet open={open} onOpenChange={onOpenChange} title="نسخه‌ها" description="هر ذخیره یک نسخه است؛ برگرداندن، نسخه‌ی تازه‌ای با متن قدیمی میسازد">
      {q.isLoading ? <Skeleton className="h-32" /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : (
        <ul className="flex flex-col" aria-label="نسخه‌ها">
          {[...(q.data ?? [])].sort((a, b) => b.version - a.version).map((v) => (
            <li key={v.version} className="flex flex-wrap items-center gap-3 border-t border-div py-3 first:border-0">
              <span className="flex min-w-0 flex-[1_1_10rem] flex-col">
                <span className="text-[14px] font-semibold">نسخه‌ی <span className="fig">{v.version}</span>{v.version === current ? <Pill tone="pos" className="ms-2">فعلی</Pill> : null}</span>
                <span className="text-[11px] text-muted">{jDateTime(v.at)} · {v.by.display_fa ?? v.by.code}</span>
                {v.note_fa ? <FaPara text={v.note_fa} className="text-[12px] text-sec" /> : null}
              </span>
              {v.version !== current ? (
                <Button size="sm" icon="back" loading={act.revert.isPending && act.revert.variables === v.version} aria-label={`برگرد به نسخه‌ی ${v.version}`}
                  onClick={() => act.revert.mutate(v.version, { onSuccess: () => { toast({ tone: 'ok', text: 'نسخه‌ی تازه از متن قدیمی ساخته شد.' }); onOpenChange(false); }, onError: (e) => toast({ tone: 'error', text: errText(e, 'برنگشت.') }) })}>برگردان</Button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </Sheet>
  );
}

function CopyDialog({ line, open, onOpenChange }: { line: Line; open: boolean; onOpenChange: (v: boolean) => void }) {
  const router = useRouter();
  const toast = useToast();
  const { companies, name } = useName();
  const act = useLineActions(line.ref);
  const others = (companies ?? []).filter((c) => c.code !== line.company && c.code !== 'HQ');
  const [to, setTo] = useState('');
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="کپی برای شرکت دیگر"
      actions={<>
        <Button variant="primary" loading={act.copy.isPending} disabled={!to} onClick={() => act.copy.mutate(to, {
          onSuccess: (l) => { onOpenChange(false); toast({ tone: 'ok', text: `پیش‌نویس برای ${name(to)} ساخته شد؛ صفحه و تنظیم‌هایش را بررسی کن.` }); router.push(`/lines/${l.ref}`); },
          onError: (e) => toast({ tone: 'error', text: errText(e, 'کپی نشد.') }),
        })}>کپی کن</Button>
        <Button onClick={() => onOpenChange(false)}>بی‌خیال</Button>
      </>}>
      <div className="flex flex-col gap-3">
        <p>کپی، پیش‌نویسی با همین قدم‌ها برای شرکت دیگر است؛ فقط صفحه و تنظیم‌هایش را باید عوض کنی.</p>
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="شرکت">
          {others.map((c) => (
            <button key={c.code} type="button" role="radio" aria-checked={to === c.code} onClick={() => setTo(c.code)}
              className={cx('inline-flex h-10 items-center gap-2 rounded-full px-4 text-[13px] font-semibold', to === c.code ? 'bg-gold text-on-gold' : 'bg-tile text-sec hover:bg-hover')}>
              <CompanyMark code={c.code} height={12} mono />{c.name_fa ?? c.code}
            </button>
          ))}
        </div>
      </div>
    </Dialog>
  );
}
