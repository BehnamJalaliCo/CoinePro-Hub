'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { Waveform } from '@/components/media/composer';
import { Button, Spinner } from '@/components/ui/button';
import { Sheet } from '@/components/ui/overlay';
import { MdInline } from '@/components/ui/md';
import { Bar, FilterChip, Segmented, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { useCompanies, useDepartments, useEmployees } from '@/lib/api/hooks';
import { useOrders, type OrderOut, type OrderRoute } from '@/lib/api/v13';
import {
  OUTPUT_KIND_FA, appliesFa, previewOrder, sendOrder29, unitsFa, useRuleActions, useRules, type OrderOut29, type OutputKind, type Route as SecretaryRoute, type Rule,
} from '@/lib/api/v29';
import { DEPT_FA } from '@/lib/labels';
import { LONG_VOICE_ERROR, useLongVoice } from '@/lib/long-voice';
import { clock } from '@/lib/recorder';
import { applyPlayer, optionOf, optionOfWork, recogniseOption, type PlayerOption } from '@/lib/players';
import { PlayerPicker } from '@/components/work/player';
import { PaceAsk } from '@/components/session/pace-ask';
import type { Pace } from '@/lib/api/v34';
import { FaText } from '@/components/v29/text';
import { RouteLine } from '@/components/v29/report';
import { ago, cx } from '@/lib/format';

// The golden button (contract §17.4, ⟨1.11⟩ §29.3–§29.5): the owner speaks or writes an order, or a new rule for the holding. Long voice:
// the browser's recogniser writes as he speaks and starts again at every pause; past a minute the audio goes to the hub in pieces. The whole
// text is shown and can be corrected before anything goes. An order gets the secretary's one line first («→ تریدیار/رسانه؛ خروجی: ۳ ریلز؛
// بودجه: …»), which the owner may change (company, department, collaborators, output, mode, player) before «بفرست»; a rule is cleaned into
// one imperative and sealed with one tap.

const KIND: Record<OrderRoute['kind'], { fa: string; icon: 'task' | 'code' | 'meeting' | 'advisor' }> = {
  work: { fa: 'کار', icon: 'task' },
  code: { fa: 'کارگاه کد', icon: 'code' },
  meeting: { fa: 'جلسه', icon: 'meeting' },
  question: { fa: 'پرسش', icon: 'advisor' },
};

function routeHref(r: OrderRoute): string | null {
  if (r.session_ref) return `/workshop/${r.session_ref}`;
  if (r.decision_ref) return `/cartable?ref=${r.decision_ref}`;
  if (r.work_ref) return `/work/${r.work_ref}`;
  if (r.kind === 'question') return '/advisor';
  return null;
}

/** Where an order went: company, who, what kind — and a way in. */
function Route({ r, onGo }: { r: OrderRoute; onGo?: () => void }) {
  const { data: employees } = useEmployees({});
  const who = employees?.items.find((e) => e.code === r.to)?.title_fa ?? r.to;
  const href = routeHref(r);
  const body = (
    <>
      <span className="text-sec"><CompanyMark code={r.company} height={13} mono /></span>
      <span className="text-sec"><Icon name={KIND[r.kind].icon} size={15} /></span>
      <span className="text-ink">{KIND[r.kind].fa}</span>
      <span className="text-muted">←</span>
      <span className="truncate text-ink">{who}</span>
    </>
  );
  const cls = 'inline-flex h-8 max-w-full items-center gap-1.5 rounded-full bg-tile px-3 text-[12px]';
  return href ? <Link href={href} onClick={onGo} className={cx(cls, 'hover:bg-hover')}>{body}</Link> : <span className={cls}>{body}</span>;
}

type Phase = 'ready' | 'review' | 'sent';
export type VoiceMode = 'order' | 'rule';
export type VoiceOpen = { mode?: VoiceMode; text?: string };

/** Opens the golden button from anywhere (top bar, home, palette, a council's plan), as an order or a rule, optionally with words. */
export const VoiceOrderContext = createContext<(o?: VoiceOpen) => void>(() => {});
export const useVoiceOrder = () => useContext(VoiceOrderContext);

type Edits = Partial<Pick<SecretaryRoute, 'companies' | 'department' | 'collaborators' | 'output_kind' | 'count'>>;

/** The secretary's reading of the words, asked again a moment after the owner stops typing. null: a hub without the secretary. */
function useSecretary(text: string, source: 'voice' | 'text', on: boolean) {
  const [settled, setSettled] = useState(text.trim());
  useEffect(() => { const t = setTimeout(() => setSettled(text.trim()), 600); return () => clearTimeout(t); }, [text]);
  return useQuery({
    queryKey: ['orders', 'preview', settled, source], enabled: on && settled.length >= 3, staleTime: 60_000, retry: false,
    queryFn: () => previewOrder(settled, source),
  });
}

/** The one line and, behind «تغییر», the company, department, collaborators, output and count. Mode and player are the picker's. */
function SecretaryLine({ preview, loading, edits, onEdits, option }: { preview: SecretaryRoute | null | undefined; loading: boolean; edits: Edits; onEdits: (e: Edits) => void; option: PlayerOption }) {
  const [open, setOpen] = useState(false);
  const { data: companies } = useCompanies();
  const r = preview ? { ...preview, ...edits, mode: option.mode, player: option.player } : null;
  const lead = r?.companies[0] ?? null;
  const deps = useDepartments(open ? lead : null);
  if (loading && !preview) return <div className="flex items-center gap-2 rounded-[12px] bg-tile px-3 py-2.5 text-[12px] text-sec"><Spinner size={14} />منشی فرمان را میخواند…</div>;
  if (!r) return null;
  const changed = Object.keys(edits).length > 0 || option.mode !== preview!.mode || option.player !== preview!.player;
  const unsure = preview!.confidence < 0.6;
  return (
    <section aria-label="پیش‌نمایش منشی" className={cx('flex flex-col gap-2 rounded-[12px] p-3', unsure ? 'bg-warn-soft' : 'bg-lapis-soft')}>
      <div className="flex items-start gap-2">
        <span className={cx('mt-0.5 flex-none', unsure ? 'text-warn' : 'text-lapis')}><Icon name="assistant" size={16} /></span>
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="text-[11px] font-semibold text-sec">منشی هلدینگ{unsure ? '؛ مطمئن نیست، مسیر را ببین' : ''}</span>
          {changed ? <RouteLine r={r} count={r.count} /> : <span className="text-[13px] leading-6 text-ink" data-testid="secretary-line"><FaText text={preview!.preview_fa} /></span>}
          {preview!.why_fa ? <span className="text-[11px] leading-5 text-muted"><FaText text={preview!.why_fa} /></span> : null}
        </div>
        <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className="flex-none text-[12px] font-semibold text-gold-ink hover:underline">{open ? 'بستن' : 'تغییر'}</button>
      </div>
      {open ? (
        <div className="flex flex-col gap-3 border-t border-div pt-3">
          <fieldset className="flex flex-col gap-1.5">
            <legend className="pb-1 text-[12px] text-sec">شرکت</legend>
            <div className="flex flex-wrap gap-1.5">
              {(companies ?? []).map((c) => (
                <FilterChip key={c.code} selected={lead === c.code} onClick={() => onEdits({ ...edits, companies: [c.code], department: null, collaborators: (r.collaborators ?? []).filter((x) => x !== c.code) })}>
                  <span className="flex items-center gap-1.5"><CompanyMark code={c.code} height={12} mono />{c.name_fa}</span>
                </FilterChip>
              ))}
            </div>
          </fieldset>
          <fieldset className="flex flex-col gap-1.5">
            <legend className="pb-1 text-[12px] text-sec">دپارتمان</legend>
            <div className="flex flex-wrap gap-1.5">
              <FilterChip selected={!r.department} onClick={() => onEdits({ ...edits, department: null })}>مدیرعامل تصمیم بگیرد</FilterChip>
              {(deps.data ?? []).map((d) => <FilterChip key={d.code} selected={r.department === d.code} onClick={() => onEdits({ ...edits, department: d.code })}>{d.name_fa}</FilterChip>)}
              {r.department && !(deps.data ?? []).some((d) => d.code === r.department) ? <FilterChip selected>{DEPT_FA[r.department] ?? r.department}</FilterChip> : null}
            </div>
          </fieldset>
          <fieldset className="flex flex-col gap-1.5">
            <legend className="pb-1 text-[12px] text-sec">شرکت‌های همکار</legend>
            <div className="flex flex-wrap gap-1.5">
              {(companies ?? []).filter((c) => c.code !== lead).map((c) => {
                const on = (r.collaborators ?? []).includes(c.code);
                return <FilterChip key={c.code} selected={on} onClick={() => onEdits({ ...edits, collaborators: on ? r.collaborators.filter((x) => x !== c.code) : [...r.collaborators, c.code] })}>{c.name_fa}</FilterChip>;
              })}
            </div>
          </fieldset>
          <fieldset className="flex flex-col gap-1.5">
            <legend className="pb-1 text-[12px] text-sec">خروجی</legend>
            <div className="flex flex-wrap items-center gap-1.5">
              {(Object.keys(OUTPUT_KIND_FA) as OutputKind[]).map((k) => <FilterChip key={k} selected={r.output_kind === k} onClick={() => onEdits({ ...edits, output_kind: k })}>{OUTPUT_KIND_FA[k]}</FilterChip>)}
              <label className="flex items-center gap-1.5 text-[12px] text-sec">تعداد
                <input type="number" min={1} max={99} value={r.count ?? ''} onChange={(e) => onEdits({ ...edits, count: e.target.value ? Math.max(1, Math.min(99, Number(e.target.value))) : null })}
                  className="fig h-8 w-16 rounded-[8px] border border-strong bg-tile px-2 text-[13px] text-ink outline-none focus:border-gold-ink" />
              </label>
            </div>
          </fieldset>
          <span className="text-[11px] text-muted">بودجه: <FaText text={`${unitsFa(r.budget_tokens)} واحد`} />، از جدول نوع خروجی؛ هرگز کمتر از کف دپارتمان. حالت و بازیکن از «با کدام مدل؟».</span>
        </div>
      ) : null}
    </section>
  );
}

/**
 * The owner speaks an order (or a rule); the hub routes it (contract §17.4, §29.4): rules first, then the light model. The owner reads the
 * exact text and the secretary's line before it goes, and sees where it went.
 */
export function VoiceOrder({ open, onOpenChange, initial }: { open: boolean; onOpenChange: (v: boolean) => void; initial?: VoiceOpen | null }) {
  const qc = useQueryClient();
  const router = useRouter();
  const toast = useToast();
  const orders = useOrders();
  const rules = useRules();
  const ruleAct = useRuleActions();
  const { data: companies } = useCompanies();
  // Opened with a mode or words (the home's «قانون تازه», a council's plan): it starts from them (the shell mounts it afresh each time).
  const [mode, setMode] = useState<VoiceMode>(initial?.mode ?? 'order');
  const [phase, setPhase] = useState<Phase>(initial?.text ? 'review' : 'ready');
  const [text, setText] = useState(initial?.text ?? '');
  const [voice, setVoice] = useState<{ seconds: number; via: 'phone' | 'hub' } | null>(null);
  const [out, setOut] = useState<OrderOut29 | null>(null);
  const [rule, setRule] = useState<Rule | null>(null);
  const [busy, setBusy] = useState(false);
  const [edits, setEdits] = useState<Edits>({});
  // ⟨1.9⟩ §27.1: «با جمنای / با جی‌پی‌تی / شورا» in the words picks the player; the owner sees what was heard and can change it.
  const heard = useMemo(() => recogniseOption(text), [text]);
  const [chosen, setChosen] = useState<PlayerOption | null>(null);
  // ⟨2026-11-09⟩ «با من یا خودکار؟» before the order goes (every order is a session); nothing is chosen for the owner
  const [pace, setPace] = useState<Pace | null>(null);
  const source = voice ? 'voice' : 'text';
  const sec = useSecretary(text, source, open && mode === 'order' && phase === 'review');
  const preview = sec.data;
  const option = chosen ?? heard?.option ?? (preview ? optionOfWork(preview.player, preview.mode) : optionOf('auto'));
  const lv = useLongVoice({
    purpose: mode === 'rule' ? 'rule' : 'order',
    onText: (r) => { setText((t) => (t.trim() ? `${t.trimEnd()} ${r.text}` : r.text)); setVoice({ seconds: r.seconds, via: r.via }); setPhase('review'); },
    onError: (f, detail) => toast({ tone: f === 'empty' ? 'info' : 'error', text: detail ?? LONG_VOICE_ERROR[f] }),
  });
  const listening = lv.phase === 'listening' || lv.phase === 'asking';

  const reset = () => { setPhase('ready'); setText(''); setVoice(null); setOut(null); setRule(null); setChosen(null); setPace(null); setEdits({}); };
  const close = (x: boolean) => { if (!x) { lv.cancel(); reset(); } onOpenChange(x); };
  const name = (code: string) => companies?.find((c) => c.code === code)?.name_fa ?? code;

  const sendOrder = async () => {
    setBusy(true);
    try {
      const route = preview ? {
        companies: edits.companies ?? preview.companies, department: edits.department !== undefined ? edits.department : preview.department,
        collaborators: edits.collaborators ?? preview.collaborators, output_kind: edits.output_kind ?? preview.output_kind,
        count: edits.count !== undefined ? edits.count : preview.count, budget_tokens: preview.budget_tokens, mode: option.mode, player: option.player,
      } : null;
      const o = await sendOrder29({ text: text.trim(), source, route, pace });
      // A hub without the secretary read the words itself; where the owner chose otherwise, the works it made follow the owner's choice.
      if (!route) {
        const changed = await applyPlayer(o as OrderOut, option);
        if (changed) toast({ tone: 'info', text: `بازیکن ${changed.toLocaleString('fa-IR')} کار به «${option.fa}» تغییر کرد.` });
      }
      for (const k of ['orders', 'work', 'planner', 'workshop', 'decisions', 'inbox', 'home', 'office']) void qc.invalidateQueries({ queryKey: [k] });
      // ⟨1.17⟩ §35.1: the order is a session at once; the owner lands in it.
      toast({ tone: 'ok', text: 'فرمان رسید؛ جلسه‌اش باز شد.' });
      close(false);
      router.push(`/s/${encodeURIComponent(o.ref)}`);
    } catch (e) {
      toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'فرمان نرسید.' });
    } finally {
      setBusy(false);
    }
  };
  const sendRule = () => ruleAct.create.mutate({ text: text.trim(), source }, {
    onSuccess: (r) => { setRule(r); setPhase('sent'); },
    onError: (e) => toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'قانون نرسید.' }),
  });
  const seal = () => rule && ruleAct.seal.mutate(rule.ref, {
    onSuccess: (r) => { setRule(r); toast({ tone: 'ok', text: 'قانون مُهر شد؛ از همین حالا در کار نقش‌ها می‌نشیند و ناظر آن را میپاید.' }); },
    onError: (e) => toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'مُهر نشد.' }),
  });

  const footer = phase === 'review'
    ? mode === 'rule'
      ? <Button variant="primary" icon="seal" className="w-full" disabled={text.trim().length < 3} loading={ruleAct.create.isPending} onClick={sendRule}>بفرست به‌عنوان قانون</Button>
      : <Button variant="primary" icon="send" className="w-full" disabled={text.trim().length < 3 || !pace} loading={busy} onClick={sendOrder}>بفرست</Button>
    : phase === 'sent'
      ? <Button variant="secondary" icon="mic" className="w-full" onClick={reset}>{mode === 'rule' ? 'قانون بعدی' : 'فرمان بعدی'}</Button>
      : undefined;

  return (
    <Sheet open={open} onOpenChange={close} title={mode === 'rule' ? 'قانون تازه برای هلدینگ' : 'فرمان صوتی'}
      description={mode === 'rule' ? 'بگو چه چیزی دیگر نباید تکرار شود؛ منشی آن را یک دستور روشن میکند و با یک ضربه مُهر میشود.' : 'بگو چه میخواهی؛ خودشان میدانند کجا و به دست چه کسی انجام شود.'} width={560} footer={footer}>
      <div className="flex flex-col gap-6">
        {phase !== 'sent' && !listening && lv.phase !== 'sending' ? (
          <Segmented label="فرمان یا قانون" value={mode} onChange={(m) => { setMode(m); setOut(null); setRule(null); }}
            options={[{ value: 'order', label: 'فرمان', icon: 'command' }, { value: 'rule', label: 'قانون تازه برای هلدینگ', icon: 'seal' }]} />
        ) : null}
        {phase === 'ready' ? (
          <div className="flex flex-col items-center gap-4 py-2">
            <button
              type="button"
              onClick={() => (listening ? lv.finish() : void lv.start())}
              disabled={lv.phase === 'sending' || lv.phase === 'asking'}
              aria-label={listening ? 'تمام؛ متن را ببینم' : mode === 'rule' ? 'شروع گفتن قانون' : 'شروع ضبط فرمان'}
              className="relative flex size-28 items-center justify-center rounded-full bg-gold text-on-gold shadow-[0_8px_32px_rgba(216,168,72,.35)] transition-transform active:scale-95 disabled:opacity-70"
            >
              {listening ? <span aria-hidden className="absolute inset-0 rounded-full bg-gold" style={{ animation: 'hq-ring 1.6s ease-out infinite' }} /> : null}
              <span className="relative">{lv.phase === 'sending' ? <Spinner size={34} /> : <Icon name={listening ? 'stop' : 'mic'} size={40} />}</span>
            </button>
            {listening ? (
              <div className="flex w-full flex-col items-center gap-3">
                <Waveform levels={lv.levels} className="h-10 w-full max-w-sm justify-center" />
                <div className="flex items-center gap-3 text-[13px] text-sec">
                  <span className="fig">{clock(lv.elapsed)}</span>
                  <button type="button" onClick={lv.cancel} className="text-muted hover:text-ink">لغو</button>
                </div>
                <div role="status" aria-live="polite" aria-label="متن تا این‌جا" className="max-h-40 w-full overflow-y-auto rounded-[12px] bg-tile px-3 py-2.5 text-[14px] leading-7 text-ink">
                  {lv.live ? <FaText text={lv.live} /> : <span className="text-muted">بگو؛ متن همین‌جا میاید. مکث کن، ادامه بده؛ دوباره بزن تا تمام شود.</span>}
                </div>
                {lv.hub ? (
                  <span className="flex items-center gap-1.5 text-[12px] text-lapis"><Icon name="info" size={14} />بیش از یک دقیقه شد؛ صدا تکه‌تکه به ستاد میرود تا متن کامل و دقیق شود (<span className="fig">{lv.sent}</span> تکه رسید).</span>
                ) : null}
              </div>
            ) : lv.phase === 'sending' ? (
              <div role="status" className="flex w-full max-w-sm flex-col items-center gap-2">
                <p className="text-[14px] text-sec">ستاد صدا را به متن فارسی تبدیل میکند…</p>
                <span className="text-[12px] text-muted"><span className="fig">{lv.sent}</span> از <span className="fig">{Math.max(lv.total, lv.sent)}</span> تکه رسید</span>
                <div className="w-full"><Bar pct={lv.total ? (lv.sent / lv.total) * 100 : 10} tone="gold" label="پیشرفت فرستادن صدا" /></div>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-1 text-center">
                <p className="text-[15px] font-semibold text-ink">بزن و بگو، هر قدر لازم است؛ دوباره بزن تا تمام شود</p>
                <p className="max-w-sm text-[13px] leading-6 text-sec">{mode === 'rule'
                  ? 'مثلاً «هیچ پستی بیرون از سری مُهرشده منتشر نشود». قانون به همه‌ی نقش‌هایی میرسد که به آن‌ها مربوط است.'
                  : 'مثلاً «برای تریدیار سه ریلز آموزشی بساز و منظم منتشر کن». پیش از رفتن، متن کامل و مسیرش را میبینی.'}</p>
                <button type="button" onClick={() => setPhase('review')} className="pt-2 text-[13px] font-semibold text-gold-ink hover:underline">به‌جایش مینویسم</button>
              </div>
            )}
          </div>
        ) : phase === 'review' ? (
          <div className="flex flex-col gap-3">
            <label className="flex flex-col gap-1.5">
              <span className="text-[13px] text-sec">{voice ? 'متن کامل آنچه گفتی؛ اگر لازم است اصلاح کن' : mode === 'rule' ? 'قانون، به زبان خودت' : 'فرمان'}</span>
              <textarea value={text} onChange={(e) => setText(e.target.value)} rows={5} maxLength={20000} autoFocus={!voice}
                className="w-full rounded-[12px] border border-strong bg-tile px-3 py-3 text-[15px] leading-7 text-ink outline-none focus:border-gold-ink" />
            </label>
            {mode === 'order' ? (
              <>
                <PlayerPicker value={option} onChange={setChosen} heard={heard} />
                {text.trim().length >= 3 ? <PaceAsk pace={pace} onChange={setPace} /> : null}
                <SecretaryLine preview={preview} loading={sec.isFetching} edits={edits} onEdits={setEdits} option={option} />
              </>
            ) : null}
            <div className="flex flex-wrap items-center gap-3 text-[12px] text-sec">
              {voice ? <span className="flex items-center gap-1.5"><Icon name="mic" size={14} /><span className="fig">{clock(voice.seconds)}</span> گفتار{voice.via === 'hub' ? '؛ متن از ستاد' : ''}</span> : null}
              <span className="flex-1" />
              <button type="button" onClick={() => { setPhase('ready'); void lv.start(); }} className="flex items-center gap-1 font-semibold text-gold-ink hover:underline"><Icon name="mic" size={14} />{text.trim() ? 'ادامه بده' : 'بگو'}</button>
            </div>
          </div>
        ) : mode === 'rule' && rule ? (
          <div className="flex flex-col gap-3 rounded-[14px] bg-tile p-4" aria-label="قانون پیشنهادی">
            <div className="flex items-center gap-2">
              <span className="text-gold-ink"><Icon name="seal" size={20} active={rule.status === 'sealed'} /></span>
              <span className="flex-1 text-[14px] font-semibold">{rule.status === 'sealed' ? 'قانون مُهر شد' : 'قانون آماده‌ی مُهر'}</span>
            </div>
            <p className="text-justify text-[15px] font-semibold leading-7 [text-align-last:start]"><FaText text={rule.text_md} /></p>
            <span className="text-[12px] text-sec">برای: {appliesFa(rule.applies_to, name)}</span>
            {rule.status === 'proposed' ? (
              <Button variant="primary" icon="seal" loading={ruleAct.seal.isPending} onClick={seal} className="self-start">مُهر کن</Button>
            ) : <span className="text-[12px] text-muted">گزارش اول اجرا ۲۴ ساعت بعد میاید: چند بار به کار رفت، چند تخلف و چند اصلاح.</span>}
            <Link href="/rules" onClick={() => close(false)} className="text-[12px] font-semibold text-gold-ink hover:underline">همه‌ی قانون‌ها</Link>
          </div>
        ) : out ? (
          <div className="flex flex-col gap-3 rounded-[14px] bg-tile p-4">
            <div className="flex items-center gap-2">
              <span className="text-gold-ink"><Icon name="seal" size={20} active /></span>
              <span className="flex-1 text-[14px] font-semibold">فرمان رسید</span>
              <Link href={`/s/${out.ref}`} onClick={() => close(false)} className="text-[12px] font-semibold text-gold-ink hover:underline">برو به جلسه</Link>
            </div>
            <p className="text-[13px] leading-6 text-sec"><MdInline text={out.summary_fa} /></p>
            <div className="flex flex-col items-start gap-1.5">{out.routes.map((r, i) => <Route key={i} r={r} onGo={() => close(false)} />)}</div>
          </div>
        ) : null}

        {mode === 'rule' ? (
          <section className="flex flex-col gap-2 border-t border-div pt-4" aria-label="قانون‌های اخیر">
            <div className="flex items-center"><h3 className="flex-1 text-[13px] font-semibold text-sec">قانون‌های اخیر</h3><Link href="/rules" onClick={() => close(false)} className="text-[12px] font-semibold text-gold-ink hover:underline">همه</Link></div>
            {rules.isLoading ? <Skeleton className="h-16" /> : !rules.data?.length ? <p className="text-[12px] text-muted">هنوز قانونی نگذاشته‌ای.</p> : (
              <ul className="flex flex-col gap-2">{rules.data.filter((r) => r.status !== 'retired').slice(0, 3).map((r) => <li key={r.ref} className="line-clamp-2 text-[13px] leading-6"><FaText text={r.text_md} /></li>)}</ul>
            )}
          </section>
        ) : (
          <section className="flex flex-col gap-2 border-t border-div pt-4" aria-label="فرمان‌های اخیر">
            <h3 className="text-[13px] font-semibold text-sec">فرمان‌های اخیر</h3>
            {orders.isLoading ? <Skeleton className="h-20" /> : !orders.data?.items.length ? <p className="text-[12px] text-muted">هنوز فرمانی نداده‌ای.</p> : (
              <ul className="flex flex-col gap-3">
                {orders.data.items.slice(0, 5).map((o) => (
                  <li key={o.ref} className="flex flex-col gap-1.5">
                    <div className="flex items-start gap-2">
                      <span className="mt-0.5 text-muted"><Icon name={o.source === 'voice' ? 'mic' : 'edit'} size={14} /></span>
                      <Link href={`/s/${o.ref}`} onClick={() => close(false)} className="line-clamp-2 min-w-0 flex-1 text-[13px] leading-6 text-ink hover:text-gold-ink"><MdInline text={o.text} links={false} /></Link>
                      <span className="flex-none text-[11px] text-muted">{ago(o.created_at)}</span>
                    </div>
                    {o.routes?.length ? <div className="flex flex-wrap gap-1.5 ps-6">{o.routes.map((r, i) => <Route key={i} r={r} onGo={() => close(false)} />)}</div> : null}
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}
      </div>
    </Sheet>
  );
}
