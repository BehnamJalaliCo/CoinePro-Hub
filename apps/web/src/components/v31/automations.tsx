'use client';

// ⟨1.13⟩ Contract §31.7 «اتوماسیون از یک جمله»: one Persian sentence is compiled into a rule, shown back in plain words with what it will
// not do, sealed behind the passkey, and then listed with an on/off switch and its runs. Running is code, never a model.

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, Empty, ErrorState, Pill, SectionTitle, Skeleton, Switch } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { AUTOMATION_STATE, compileAutomation, useAutomation, useAutomationActions, useAutomations, type Automation, type Compiled } from '@/lib/api/v31';
import { useCompanies } from '@/lib/api/hooks';
import { jDateTime } from '@/lib/format';
import { FaPara, FaText } from '@/components/v29/text';
import { errText, field } from './kit';
import { cx } from '@/lib/format';

export function Automations() {
  const q = useAutomations();
  const act = useAutomationActions();
  const toast = useToast();
  const cs = useCompanies();
  const [sentence, setSentence] = useState('');
  const [company, setCompany] = useState<string | null>(null);
  const [out, setOut] = useState<Compiled | null>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const compile = async () => {
    setBusy(true);
    try { setOut(await compileAutomation(sentence.trim(), company)); } catch (e) { toast({ tone: 'error', text: errText(e, 'ساخته نشد؛ دوباره بزن.') }); } finally { setBusy(false); }
  };
  const register = () => out?.rule && act.register.mutate({ rule: out.rule, sentence_fa: sentence.trim(), company }, {
    onSuccess: () => { toast({ tone: 'ok', text: 'ثبت و مُهر شد؛ روشن است.' }); setOut(null); setSentence(''); },
    onError: (e) => toast({ tone: 'error', text: errText(e, 'ثبت نشد.') }),
  });
  const name = (c: string | null) => (c ? cs.data?.find((x) => x.code === c)?.name_fa ?? c : 'کل هلدینگ');
  return (
    <div className="flex flex-col gap-4">
      <Card as="section" className="flex flex-col gap-3 p-5" aria-label="یک جمله بنویس">
        <SectionTitle title="یک جمله بنویس" note="مثلاً: هر روز ساعت ۸ صبح اگر بازدید دیروز کم شد به من خبر بده" />
        <textarea value={sentence} onChange={(e) => { setSentence(e.target.value); setOut(null); }} rows={3} dir="auto" aria-label="جمله‌ی اتوماسیون" className={cx(field, 'py-2.5 leading-7')} />
        <div className="no-scrollbar flex gap-2 overflow-x-auto" role="radiogroup" aria-label="برای کدام شرکت">
          {[{ code: null as string | null, n: 'کل هلدینگ' }, ...(cs.data ?? []).filter((c) => c.code !== 'HQ').map((c) => ({ code: c.code as string | null, n: c.name_fa ?? c.code }))].map((c) => (
            <button key={c.code ?? 'all'} type="button" role="radio" aria-checked={company === c.code} onClick={() => { setCompany(c.code); setOut(null); }}
              className={cx('h-9 flex-none rounded-full px-3.5 text-[13px] font-semibold', company === c.code ? 'bg-gold text-on-gold' : 'bg-tile text-sec hover:bg-hover')}>{c.n}</button>
          ))}
        </div>
        <div><Button variant="primary" icon="send" loading={busy} disabled={sentence.trim().length < 6} onClick={compile}>بساز و نشانم بده</Button></div>
      </Card>

      {out ? (
        <Card as="section" className="tahrir hq-rise flex flex-col gap-3 p-5" aria-label="پیش‌نمایش اتوماسیون">
          <SectionTitle title={out.rule ? 'این کار انجام میشود' : 'این جمله قاعده نشد'} note={out.rule ? 'تا مُهر نزنی چیزی اجرا نمیشود' : 'جمله را ساده‌تر یا دقیق‌تر بنویس'} />
          {out.preview_fa ? <FaPara text={out.preview_fa} className="text-[14px] leading-7" /> : null}
          {out.refused_fa.length ? (
            <div className="flex flex-col gap-1.5" aria-label="این کارها انجام نمیشود">
              <h3 className="text-[13px] font-semibold text-sec">این‌ها را انجام نمیدهد</h3>
              <ul className="flex flex-col gap-1.5">{out.refused_fa.map((r) => <li key={r} className="rounded-[10px] bg-warn-soft px-3 py-2 text-[13px] leading-6"><FaText text={r} /></li>)}</ul>
            </div>
          ) : null}
          <div className="flex flex-wrap gap-2">
            {out.rule ? <Button variant="primary" icon="seal" loading={act.register.isPending} onClick={register}>ثبت و مُهر</Button> : null}
            <Button onClick={() => setOut(null)}>بی‌خیال</Button>
          </div>
        </Card>
      ) : null}

      {q.isLoading ? <Skeleton className="h-40 rounded-[16px]" /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.data === null ? (
        <Card><Empty icon="task" title="اتوماسیون بعد از به‌روزرسانی ستاد میاید" body="یک جمله مینویسی و ستاد قاعده‌اش را میسازد." /></Card>
      ) : (
        <Card as="section" className="flex flex-col gap-2 p-5" aria-label="اتوماسیون‌های من">
          <SectionTitle title="اتوماسیون‌های من" />
          {!q.data?.length ? <p className="py-2 text-[13px] text-muted">هنوز اتوماسیونی نیست.</p> : (
            <ul className="flex flex-col">{q.data.map((a) => <AutomationRow key={a.ref} a={a} open={open === a.ref} onOpen={() => setOpen(open === a.ref ? null : a.ref)} name={name(a.company)} />)}</ul>
          )}
        </Card>
      )}
    </div>
  );
}

const OUTCOME_FA: Record<string, string> = { ok: 'انجام شد', failed: 'ناموفق', skipped: 'اجرا نشد' };

function AutomationRow({ a, open, onOpen, name }: { a: Automation; open: boolean; onOpen: () => void; name: string }) {
  const act = useAutomationActions();
  const toast = useToast();
  const det = useAutomation(open ? a.ref : null);
  const st = AUTOMATION_STATE[a.state];
  // The detail's history is `run_log`; `runs` is only the count.
  const runs = det.data?.run_log ?? [];
  const count = a.runs;
  return (
    <li className="flex flex-col gap-2 border-t border-div py-3 first:border-0" aria-label={`اتوماسیون ${a.ref}`}>
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" onClick={onOpen} aria-expanded={open} className="flex min-w-0 flex-[1_1_14rem] flex-col text-start">
          <span className="text-[14px] font-semibold"><FaText text={a.sentence_fa} /></span>
          <span className="text-[11px] text-muted"><span className="fig">{a.ref}</span> · {name} · <span className="fig">{count}</span> اجرا{a.last_run_at ? ` · آخرین: ${jDateTime(a.last_run_at)}` : ''}</span>
        </button>
        <Pill tone={st.tone} dot>{st.fa}</Pill>
        {a.state === 'proposed' ? <Button size="sm" variant="primary" icon="seal" loading={act.seal.isPending} onClick={() => act.seal.mutate(a.ref, { onError: (e) => toast({ tone: 'error', text: errText(e, 'مُهر نشد.') }) })}>مُهر کن</Button>
          : <Switch checked={a.state === 'on'} label={`روشن بودن ${a.ref}`} onChange={(v) => act.state.mutate({ ref: a.ref, state: v ? 'on' : 'off' }, { onError: (e) => toast({ tone: 'error', text: errText(e, 'تغییر نکرد.') }) })} />}
      </div>
      {open ? (
        <div className="flex flex-col gap-2 rounded-[12px] bg-tile p-3" aria-label="اجراها">
          {det.data?.preview_fa ? <FaPara text={det.data.preview_fa} className="text-[13px] leading-6 text-sec" /> : null}
          {det.isLoading ? <Skeleton className="h-10" /> : !runs.length ? <p className="text-[12px] text-muted">هنوز اجرا نشده.</p> : (
            <ul className="flex flex-col gap-1">{runs.map((r) => <li key={r.key} className="flex flex-wrap gap-2 text-[12px]"><span>{jDateTime(r.at)}</span><Pill tone={r.outcome === 'failed' ? 'warn' : r.outcome === 'skipped' ? 'silver' : 'pos'} dot>{OUTCOME_FA[r.outcome] ?? r.outcome}</Pill>{r.error_fa ? <span className="text-sec"><FaText text={r.error_fa} /></span> : null}</li>)}</ul>
          )}
        </div>
      ) : null}
    </li>
  );
}
