'use client';

// ⟨1.0.1⟩ Part C, «نوار فرمان همه‌جا» (C2.1): one round button on every top-level screen (the HQ mark inside a thin gold ring, not a
// filled gold), and the one spring sheet it opens, «چه میخواهی؟»: the words, the template chips that only fill the starting text, the
// companies as their own marks (any number; none picked = the holding decides), the pace, and «باز کن» in the decision bar. The path
// is the one path: the existing new-order call, and the owner lands in the session it opens. «کارمند ۲۴ ساعته» turns the same sheet
// into the routine form: one sentence, one company, «بساز» (`POST /routines`; no card, no fingerprint).

import { useRouter } from 'next/navigation';
import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { CompanyMark, Monogram } from '@/components/brand/marks';
import { Icon } from '@/components/icon';
import { bidi } from '@/components/ui/bidi';
import { Segmented } from '@/components/ui/primitives';
import { ApiError } from '@/lib/api/client';
import { useCompanies } from '@/lib/api/hooks';
import { PACE_FA, type Pace } from '@/lib/api/v34';
import { SENTENCE_MAX, useAbsent, type SessionRoutine } from '@/lib/api/v47';
import { TEMPLATES, namesFa, sendCommand, templateText, useAbsent55, useMakeCompanyRoutine, type TemplateKey } from '@/lib/api/v55';
import { cx, jDateTime } from '@/lib/format';
import { DecisionBar } from './decision-bar';
import { haptic } from './haptics';
import { DrawnTick } from './ring';
import { SpringSheet } from './spring-sheet';
import { Facts } from './text';
import { viewTransition } from './transition';

export type CommandOpen = { text?: string; mode?: 'order' | 'routine' };
/** Opens the command sheet from anywhere under the shell. */
export const CommandContext = createContext<(o?: CommandOpen) => void>(() => {});
export const useCommand = () => useContext(CommandContext);

export const COMMAND_FA = 'چه میخواهی؟';
const PLACEHOLDER = 'بنویس چه میخواهی؛ درباره‌ی هر چیزی';
const ROUTINE_PLACEHOLDER = 'مثلاً: هر روز ساعت ۹ رتبه‌های سئوی سایت را ببین و خلاصه بده';
const PACE_ASK = 'این جلسه چطور جلو برود؟';
const PACE_HINT: Record<Pace, string> = { step: 'مسئول یک قدم برمیدارد و بعد از تو میپرسد.', auto: 'مسئول تا آخر میرود؛ فقط برای تأیید تو می‌ایستد.' };
const fieldCls = 'w-full resize-none rounded-[12px] border border-strong bg-tile px-3.5 py-3 text-[15px] leading-7 text-ink outline-none placeholder:text-muted focus:border-[var(--hq-silver-ink)]';

/** The HQ mark inside a thin gold ring: the command, never a filled gold. */
export function CommandMark({ size = 56 }: { size?: number }) {
  return (
    <span className="flex flex-none items-center justify-center rounded-full bg-raised shadow-[0_0_0_1.5px_var(--hq-gold-ink)]" style={{ width: size, height: size }}>
      <Monogram size={Math.round(size * 0.46)} />
    </span>
  );
}

/** The round command button: the same corner on every top-level screen, above the navigation. */
export function CommandButton({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" data-command-button aria-label={COMMAND_FA} title={COMMAND_FA} onClick={onClick}
      className="fixed bottom-[calc(88px+env(safe-area-inset-bottom))] end-4 z-30 rounded-full shadow-[0_10px_28px_rgba(0,0,0,.38)] lg:bottom-6 lg:end-6">
      <CommandMark />
    </button>
  );
}

/** The home's command entry: one row that opens the sheet. */
export function CommandRow() {
  const open = useCommand();
  return (
    <button type="button" data-testid="command-row" onClick={() => open()} className="flex min-h-14 w-full items-center gap-3 rounded-[16px] bg-card px-3.5 py-2.5 text-start hover:bg-hover">
      <CommandMark size={36} />
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="text-[15px] font-semibold text-ink">{COMMAND_FA}</span>
        <span className="truncate text-[12px] text-muted">بنویس؛ برایش یک جلسه باز میشود</span>
      </span>
      <span className="text-muted"><Icon name="next" size={18} mirror /></span>
    </button>
  );
}

const initials = (name: string) => name.replace(/[\s‌-]+/g, ' ').trim().split(' ').slice(0, 2).map((w) => w[0]).join('‌');

/** The companies as their own marks, in the hub's order; one tile each, a horizontal row that scrolls. */
function CompanyMarks({ picked, onToggle, label }: { picked: string[]; onToggle: (code: string) => void; label: string }) {
  const { data } = useCompanies();
  const list = (data ?? []).filter((c) => c.kind !== 'holding');
  if (!list.length) return null;
  return (
    <div className="flex flex-col gap-2">
      <span className="text-[13px] font-semibold text-ink">{label}</span>
      <div role="group" aria-label={label} className="no-scrollbar -mx-5 flex gap-2 overflow-x-auto px-5 pb-1 pt-0.5">
        {list.map((c) => {
          const on = picked.includes(c.code);
          return (
            <button key={c.code} type="button" aria-pressed={on} data-company={c.code} onClick={() => onToggle(c.code)}
              className="flex w-[76px] flex-none flex-col items-center gap-1.5 rounded-[14px] px-1 py-1.5">
              <span className={cx('flex size-[52px] items-center justify-center rounded-[16px] bg-tile text-ink', on ? 'shadow-[0_0_0_2px_var(--hq-silver-ink)]' : 'shadow-[inset_0_0_0_1px_var(--hq-line-divider)]')}>
                <CompanyMark code={c.code} height={24} title={c.name_fa ?? c.code} fallback={<span className="text-[15px] font-bold text-sec">{initials(c.name_fa ?? c.code)}</span>} />
              </span>
              <span className={cx('line-clamp-2 w-full text-center text-[11px] leading-4', on ? 'font-semibold text-ink' : 'text-sec')}>{c.name_fa ?? c.code}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

type Mode = 'order' | 'routine' | 'made';

/** «چه میخواهی؟»: the order form, the routine form, and the routine's quiet confirmation, in the one sheet. */
export function CommandSheet({ open, onOpenChange, initial }: { open: boolean; onOpenChange: (v: boolean) => void; initial?: CommandOpen | null }) {
  const router = useRouter();
  const qc = useQueryClient();
  const { data: companies } = useCompanies();
  const field = useRef<HTMLTextAreaElement>(null);
  const [mode, setMode] = useState<Mode>(initial?.mode === 'routine' ? 'routine' : 'order');
  const [text, setText] = useState(initial?.text ?? '');
  const [sentence, setSentence] = useState('');
  const [picked, setPicked] = useState<string[]>([]);
  const [one, setOne] = useState<string | null>(null);
  const [pace, setPace] = useState<Pace | null>(null);
  const [template, setTemplate] = useState<TemplateKey | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [made, setMade] = useState<SessionRoutine | null>(null);
  const routineKey = useRef<string>('');
  const make = useMakeCompanyRoutine();
  const noRoutine = useAbsent55('routine');
  const noRoutineA = useAbsent('routine');

  const nameOf = useCallback((code: string) => companies?.find((c) => c.code === code)?.name_fa ?? code, [companies]);
  const names = useMemo(() => picked.map(nameOf), [picked, nameOf]);

  const toggle = (code: string) => {
    haptic('tick');
    setPicked((p) => {
      const next = p.includes(code) ? p.filter((x) => x !== code) : [...p, code];
      // The template's own words follow the companies while the owner has not written past them.
      if (template && text === templateText(template, p.map(nameOf))) setText(templateText(template, next.map(nameOf)));
      return next;
    });
  };
  const fill = (key: TemplateKey) => {
    haptic('tick');
    setTemplate(key);
    setText(templateText(key, names));
    setError(null);
    requestAnimationFrame(() => { const el = field.current; if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length); } });
  };

  const ready = text.trim().length >= 3;
  const send = async () => {
    if (!ready || !pace || busy) return;
    setBusy(true);
    setError(null);
    try {
      const o = await sendCommand({ text, companies: picked.map((code) => ({ code, name_fa: nameOf(code) })), pace });
      haptic('seal');
      for (const k of ['orders', 'office', 'home', 'work', 'planner', 'inbox']) void qc.invalidateQueries({ queryKey: [k] });
      // The sheet becomes the session (M14): it carries the shared name while the session's page takes its place.
      const from = document.querySelector<HTMLElement>('[data-testid="command-sheet"]');
      viewTransition(() => { onOpenChange(false); router.push(`/s/${encodeURIComponent(o.ref)}`); }, from, { route: true });
    } catch (e) {
      haptic('error');
      setError(e instanceof ApiError ? e.messageFa : 'فرمان نرسید؛ دوباره بزن.');
    } finally {
      setBusy(false);
    }
  };
  const build = () => {
    const s = sentence.replace(/\s+/g, ' ').trim();
    if (s.length < 3 || make.isPending) return;
    setError(null);
    routineKey.current ||= crypto.randomUUID();
    make.mutate({ sentence_fa: s, company: one, key: routineKey.current }, {
      onSuccess: (r) => {
        routineKey.current = '';
        if (!r) { setMode('order'); return; } // a hub before the routine route: the form goes back to the order
        if (!r.ref) { haptic('error'); setError('ساخته نشد؛ دوباره بزن.'); return; } // an answer that is no routine
        haptic('seal');
        setMade(r);
        setMode('made');
      },
      onError: (e) => { haptic('error'); setError(e instanceof ApiError ? e.messageFa : 'ساخته نشد؛ دوباره بزن.'); },
    });
  };

  const bar = mode === 'order' ? (
    <DecisionBar label="باز کردن جلسه" error={error}
      context={!ready ? null : !pace ? `اول «${PACE_FA.step}» یا «${PACE_FA.auto}» را انتخاب کن؛ بعد جلسه باز میشود.` : <Facts>{names.length ? namesFa(names) : 'هلدینگ خودش میسپارد'}{PACE_FA[pace]}</Facts>}
      primary={{ label: 'باز کن', onClick: () => void send(), disabled: !ready || !pace }} state={busy ? 'working' : 'idle'} />
  ) : mode === 'routine' ? (
    <DecisionBar label="ساخت کارمند ۲۴ ساعته" error={error} context={one ? `برای ${nameOf(one)}، بی کارت و بی اثر انگشت.` : 'بی کارت و بی اثر انگشت؛ همین حالا روشن میشود.'}
      primary={{ label: 'بساز', onClick: build, disabled: sentence.trim().length < 3 }} state={make.isPending ? 'working' : 'idle'}
      quiet={[{ label: 'برگرد', onClick: () => { setMode('order'); setError(null); } }]} />
  ) : (
    <DecisionBar label="کارمند ۲۴ ساعته ساخته شد" primary={{ label: 'باشه', onClick: () => onOpenChange(false) }} />
  );

  return (
    <SpringSheet open={open} onOpenChange={onOpenChange} testid="command-sheet" bar={bar}
      title={mode === 'order' ? COMMAND_FA : 'کارمند ۲۴ ساعته'}
      description={mode === 'routine' ? 'یک جمله بنویس که چه کاری، هر چند وقت یک بار.' : undefined}
      onOpened={(e) => { e.preventDefault(); field.current?.focus(); }}>
      {mode === 'order' ? (
        <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); void send(); }}>
          <textarea ref={field} value={text} rows={3} dir="auto" aria-label="فرمان" placeholder={PLACEHOLDER} maxLength={10_000} className={fieldCls}
            onChange={(e) => { setText(e.target.value); if (error) setError(null); }}
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); void send(); } }} />
          <div role="group" aria-label="الگوهای آماده" className="no-scrollbar -mx-5 flex gap-2 overflow-x-auto px-5">
            {TEMPLATES.map((t) => (
              <button key={t.key} type="button" data-template={t.key} onClick={() => fill(t.key)}
                className="inline-flex h-9 flex-none items-center rounded-full border border-strong px-3.5 text-[13px] text-sec hover:bg-hover hover:text-ink">{t.label}</button>
            ))}
            {noRoutine || noRoutineA ? null : (
              <button type="button" data-template="routine" onClick={() => { haptic('tick'); setMode('routine'); setError(null); if (picked.length === 1) setOne(picked[0]!); }}
                className="inline-flex h-9 flex-none items-center rounded-full border border-strong px-3.5 text-[13px] text-sec hover:bg-hover hover:text-ink">کارمند ۲۴ ساعته</button>
            )}
          </div>
          <CompanyMarks label="برای کدام شرکت؟" picked={picked} onToggle={toggle} />
          <div className="flex flex-col gap-1.5" data-testid="command-pace">
            <span className="text-[13px] font-semibold text-ink">{PACE_ASK}</span>
            <Segmented<Pace | ''> label={PACE_ASK} value={pace ?? ''} onChange={(v) => { if (v) { haptic('tick'); setPace(v); } }}
              options={[{ value: 'step', label: PACE_FA.step }, { value: 'auto', label: PACE_FA.auto }]} />
            {pace ? <span className="text-[12px] text-muted">{PACE_HINT[pace]}</span> : null}
          </div>
        </form>
      ) : mode === 'routine' ? (
        <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); build(); }}>
          <textarea ref={field} autoFocus value={sentence} rows={3} dir="auto" aria-label="جمله‌ی کارمند ۲۴ ساعته" placeholder={ROUTINE_PLACEHOLDER} maxLength={SENTENCE_MAX} className={fieldCls}
            onChange={(e) => { setSentence(e.target.value); if (error) setError(null); }} />
          <CompanyMarks label="برای کدام شرکت؟" picked={one ? [one] : []} onToggle={(code) => { haptic('tick'); setOne((c) => (c === code ? null : code)); }} />
        </form>
      ) : made ? (
        <div role="status" data-testid="routine-made" className="flex flex-col gap-3 pb-1">
          <div className="flex items-start gap-3 rounded-[14px] bg-card p-3.5">
            <span className="mt-0.5 flex size-8 flex-none items-center justify-center rounded-full bg-pos-soft text-pos"><DrawnTick size={18} /></span>
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <span className="text-[14px] font-semibold leading-6 text-ink">{bidi(made.sentence_fa)}</span>
              <span className="text-[12px] leading-5 text-sec">
                <Facts>
                  {made.when_fa ? <span data-when>{bidi(made.when_fa)}</span> : null}
                  {made.next_at ? <span data-next>نوبت بعد: {jDateTime(made.next_at)}</span> : null}
                </Facts>
              </span>
              {made.preview_fa ? <span className="text-[12px] leading-5 text-muted">{bidi(made.preview_fa)}</span> : null}
            </div>
          </div>
        </div>
      ) : null}
    </SpringSheet>
  );
}
