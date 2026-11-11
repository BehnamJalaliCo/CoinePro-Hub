'use client';

// ⟨1.14⟩ Contract §32.5–§32.6: the light of every voice engine, the secure key sheet, the live meter chip and its panel, and the voices of
// the personas. The key is typed or pasted only into the sheet; it is sent once, behind the passkey, and the field is cleared at once.

import { useEffect, useRef, useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Dialog, Sheet } from '@/components/ui/overlay';
import { Bar, Pill, Segmented, budgetTone } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { FaPara, FaText } from '@/components/v29/text';
import { errText, field } from '@/components/v31/kit';
import { useSettings18 } from '@/lib/api/v18';
import { fileUrl } from '@/lib/api/v13';
import {
  ENGINE_LIGHT, dollars, priceWarning, useEngines, useMeter, usePersonas, useSaveCap, useSavePersona, useVoiceActions, type VoiceEngine, type VoiceMeter,
} from '@/lib/api/v32';
import { cx } from '@/lib/format';

const PERSONA_FA: Record<string, string> = { secretary: 'منشی هلدینگ', overseer: 'ناظر کل', assistant: 'دستیار شخصی', advisor: 'مشاور کل', manager: 'مدیران شرکت‌ها' };
export const personaFa = (k: string) => PERSONA_FA[k] ?? k;

// ============================================================================================ the light of engines ==
/** One dot per engine: green works, yellow is being checked, red needs a key or failed (tap: the reason and the fix), amber hit the cap. */
export function EngineLights({ engines, onKey }: { engines: VoiceEngine[] | null | undefined; onKey: () => void }) {
  const [open, setOpen] = useState<string | null>(null);
  const act = useVoiceActions();
  const toast = useToast();
  if (!engines) return null;
  const sel = engines.find((e) => e.key === open) ?? null;
  return (
    <div className="flex flex-col gap-2" aria-label="چراغ موتورهای صدا" role="group">
      <div className="flex flex-wrap items-center gap-1.5">
        {engines.map((e) => {
          const l = ENGINE_LIGHT[e.state];
          return (
            <button key={e.key} type="button" onClick={() => setOpen(open === e.key ? null : e.key)} aria-expanded={open === e.key} data-state={e.state}
              aria-label={`${e.title_fa}: ${l.fa}`} title={e.reason_fa ?? l.fa}
              className={cx('inline-flex h-8 items-center gap-1.5 rounded-full px-2.5 text-[12px] font-semibold', open === e.key ? 'bg-hover text-ink' : 'bg-tile text-sec hover:bg-hover')}>
              <span className={cx('size-2.5 rounded-full', l.dot)} style={e.state === 'checking' ? { animation: 'hq-live 1.4s infinite' } : undefined} />
              <span className="max-w-[9rem] truncate">{shortTitle(e)}</span>
            </button>
          );
        })}
      </div>
      {sel ? (
        <div className="hq-rise flex flex-col gap-2 rounded-[12px] bg-tile p-3 text-[13px] leading-6" role="status">
          <div className="flex flex-wrap items-center gap-2">
            <b className="text-ink"><FaText text={sel.title_fa} /></b>
            <Pill tone={sel.state === 'ok' ? 'pos' : sel.state === 'capped' || sel.state === 'checking' ? 'warn' : 'neg'} dot>{ENGINE_LIGHT[sel.state].fa}</Pill>
          </div>
          {sel.reason_fa ? <FaPara text={sel.reason_fa} className="text-sec" /> : null}
          {sel.state === 'missing' || sel.state === 'failing' ? (
            <p className="text-sec">{sel.state === 'missing' ? 'برای شنیدن صدای خوب، کلید را بده.' : 'کلید را دوباره بده یا بسنج.'} تا آن وقت صدا با پایپر روی خود ستاد پخش میشود.</p>
          ) : null}
          <div className="flex flex-wrap gap-2">
            {sel.provider !== 'local' ? <Button size="sm" icon="lock" onClick={onKey}>کلید بده</Button> : null}
            {sel.provider !== 'local' && sel.state !== 'missing' ? (
              <Button size="sm" icon="refresh" loading={act.check.isPending} onClick={() => act.check.mutate(sel.key, { onError: (e) => toast({ tone: 'error', text: errText(e, 'سنجیده نشد.') }) })}>دوباره بسنج</Button>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
const shortTitle = (e: VoiceEngine) => e.title_fa.replace(/\s*\(.*\)\s*$/, '');

// ============================================================================================== the key, secure ==
/**
 * The sheet that takes a provider's key (masked, no suggestions, no spell-check). It is saved behind the passkey, checked at once, and the
 * result is shown as the light. The first key also asks for the month cap: nobody else sets one.
 */
export function KeyDialog({ open, onOpenChange, initialKey }: { open: boolean; onOpenChange: (v: boolean) => void; initialKey?: string }) {
  const engines = useEngines();
  const act = useVoiceActions();
  const save = useSaveCap();
  const settings = useSettings18();
  const toast = useToast();
  const meter = useMeter('month');
  const providers = [...new Set((engines.data ?? []).filter((e) => e.key_pattern).map((e) => e.provider))];
  const provider = providers[0] ?? 'google';
  const mine = (engines.data ?? []).filter((e) => e.provider === provider);
  const hasKey = mine.some((e) => e.state !== 'missing');
  const [secret, setSecret] = useState(initialKey ?? '');
  const [cap, setCap] = useState('');
  const [noCap, setNoCap] = useState(false);
  const [sent, setSent] = useState(false);
  const askCap = !hasKey && meter.data?.cap_usd == null;
  const capOk = !askCap || noCap || (cap !== '' && Number(cap) > 0);
  const result = sent ? mine[0] : null;

  const submit = () => {
    const k = secret.trim();
    act.setSecret.mutate({ provider, secret: k }, {
      onSuccess: () => {
        setSecret(''); setSent(true);
        if (askCap && !noCap && settings.data) save.mutate({ version: settings.data.version, month_cap_usd: Number(cap) }, { onError: (e) => toast({ tone: 'error', text: errText(e, 'سقف ثبت نشد؛ از پنل هزینه دوباره بزن.') }) });
      },
      onError: (e) => toast({ tone: 'error', text: errText(e, 'کلید ذخیره نشد.') }),
    });
  };
  const close = (v: boolean) => { if (!v) { setSecret(''); setSent(false); } onOpenChange(v); };
  const state = result?.state;

  return (
    <Dialog open={open} onOpenChange={close} title="کلید صدا"
      actions={sent ? <Button variant="primary" onClick={() => close(false)}>بستن</Button> : (
        <>
          <Button variant="primary" icon="seal" loading={act.setSecret.isPending} disabled={secret.trim().length < 20 || !capOk} onClick={submit}>ذخیره و بسنج</Button>
          <Button onClick={() => close(false)}>بی‌خیال</Button>
        </>
      )}>
      {sent ? (
        <div className="flex flex-col gap-2" role="status" aria-live="polite" aria-label="نتیجه‌ی بررسی کلید">
          {state === 'ok' ? <Pill tone="pos" icon="seal">کلید درست است؛ صدا فعال شد</Pill> : state === 'failing' || state === 'capped' ? <Pill tone="neg" dot>کلید کار نکرد</Pill> : <Pill tone="warn" live>در حال بررسی…</Pill>}
          {result?.reason_fa && state !== 'ok' ? <FaPara text={result.reason_fa} className="text-[13px] leading-6" /> : null}
          <p className="text-[12px] leading-5 text-muted">کلید فقط در گاوصندوق ستاد میماند و هیچ‌جا در گفتگو یا گزارش نمیآید.</p>
        </div>
      ) : (
        <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); if (secret.trim().length >= 20 && capOk) submit(); }} autoComplete="off">
          <label className="flex flex-col gap-1.5 text-[13px] text-sec">کلید API گوگل (برای صدای جمنای)
            <input type="password" name="hq-voice-key" autoComplete="off" spellCheck={false} autoCapitalize="off" autoCorrect="off" data-lpignore="true" data-1p-ignore="true" dir="ltr"
              value={secret} onChange={(e) => setSecret(e.target.value)} aria-label="کلید" className={cx(field, 'h-11 font-mono')} />
          </label>
          {askCap ? (
            <fieldset className="flex flex-col gap-2 rounded-[12px] bg-tile p-3">
              <legend className="px-1 text-[12px] font-semibold text-sec">سقف هزینه‌ی ماهانه‌ی صدا</legend>
              <p className="text-[12px] leading-5 text-muted">کلید اول است، پس سقف را خودت تعیین کن؛ کسی جز تو آن را نمیگذارد و نمیبرد بالا.</p>
              <label className="flex items-center gap-2 text-[13px] text-sec">دلار
                <input type="number" min={1} step={1} inputMode="decimal" value={cap} disabled={noCap} onChange={(e) => setCap(e.target.value)} aria-label="سقف ماهانه به دلار" className={cx(field, 'fig h-10 w-28')} />
              </label>
              <label className="flex items-center gap-2 text-[13px] text-sec"><input type="checkbox" checked={noCap} onChange={(e) => setNoCap(e.target.checked)} />بدون سقف (هشدار هم نمیدهد)</label>
            </fieldset>
          ) : null}
        </form>
      )}
    </Dialog>
  );
}

// ================================================================================================== the meter ==
/** The counter in the header: today's voice spend; it moves (a short lift) whenever the sum changes, at the end of every turn. */
export function MeterChip({ onOpen, pulse }: { onOpen: () => void; pulse: number }) {
  const q = useMeter('today');
  const v = q.data?.voice_usd ?? null;
  const prev = useRef<number | null>(null);
  const [bump, setBump] = useState(0);
  useEffect(() => { if (v != null && prev.current != null && v !== prev.current) setBump((n) => n + 1); if (v != null) prev.current = v; }, [v, pulse]);
  if (q.data === null) return null;
  return (
    <button type="button" onClick={onOpen} aria-label="شمارنده‌ی هزینه‌ی صدا" title="هزینه‌ی صدای امروز؛ بزن تا جزئیات را ببینی"
      className="inline-flex h-9 items-center gap-1.5 rounded-full bg-tile px-3 text-[13px] font-semibold text-ink hover:bg-hover">
      <Icon name="budget" size={16} />
      <span key={bump} className={cx('fig', bump > 0 && 'hq-rise')} data-testid="meter-today">{dollars(v)}</span>
    </button>
  );
}

export function MeterPanel({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const [period, setPeriod] = useState<'today' | 'month'>('month');
  const q = useMeter(period);
  const engines = useEngines();
  const settings = useSettings18();
  const save = useSaveCap();
  const act = useVoiceActions();
  const toast = useToast();
  const [cap, setCap] = useState<string | null>(null);
  const m: VoiceMeter | null | undefined = q.data;
  const capNow = m?.cap_usd ?? null;
  const shown = cap ?? (capNow != null ? String(capNow) : '');
  const saveCap = (v: number | null) => {
    if (!settings.data) return;
    save.mutate({ version: settings.data.version, month_cap_usd: v }, { onSuccess: () => { setCap(null); toast({ tone: 'ok', text: v == null ? 'سقف برداشته شد.' : 'سقف ثبت شد.' }); }, onError: (e) => toast({ tone: 'error', text: errText(e, 'سقف ثبت نشد.') }) });
  };
  const warns = (engines.data ?? []).map((e) => ({ e, w: priceWarning(e) })).filter((x) => x.w);
  const pctCap = capNow && m ? (m.voice_usd / capNow) * 100 : null;
  return (
    <Sheet open={open} onOpenChange={onOpenChange} title="هزینه‌ی صدا" description="هر جمله با شمار توکن خود گوگل حساب میشود" width={520}>
      <div className="flex flex-col gap-4" aria-label="جزئیات هزینه">
        <Segmented<'today' | 'month'> label="بازه" value={period} onChange={setPeriod} options={[{ value: 'today', label: 'امروز' }, { value: 'month', label: 'این ماه' }]} />
        {warns.map(({ e, w }) => (
          <p key={e.key} role="alert" className="rounded-[10px] bg-warn-soft px-3 py-2 text-[13px] leading-6">
            <FaText text={`${w!.days === 0 ? 'امروز' : `تا ${w!.days} روز دیگر`} قیمت ${shortTitle(e)} عوض میشود: خروجی صدا از ${e.price.audio_out_per_m}$ به ${w!.audio_out_per_m}$ برای هر میلیون توکن.`} />
          </p>
        ))}
        {!m ? <p className="text-[13px] text-muted">{q.isLoading ? 'در حال خواندن…' : 'شمارنده بعد از به‌روزرسانی ستاد میاید.'}</p> : (
          <>
            <div className="grid grid-cols-3 gap-2">
              <Stat label={period === 'today' ? 'امروز' : 'این ماه'} v={dollars(m.voice_usd)} />
              <Stat label="پیش‌بینی ماه" v={dollars(m.projected_usd)} />
              <Stat label="سقف" v={m.cap_usd == null ? 'ندارد' : dollars(m.cap_usd)} />
            </div>
            {pctCap != null ? <Bar pct={Math.min(100, pctCap)} tone={budgetTone(pctCap)} label="مصرف نسبت به سقف" /> : null}
            <section aria-label="سقف ماهانه" className="flex flex-wrap items-end gap-2">
              <label className="flex flex-col gap-1 text-[12px] text-sec">سقف ماهانه (دلار)
                <input type="number" min={1} inputMode="decimal" value={shown} onChange={(e) => setCap(e.target.value)} aria-label="ویرایش سقف ماهانه" className={cx(field, 'fig h-10 w-32')} />
              </label>
              <Button size="sm" variant="primary" loading={save.isPending} disabled={!(Number(shown) > 0) || Number(shown) === capNow} onClick={() => saveCap(Number(shown))}>ثبت سقف</Button>
              {capNow != null ? <Button size="sm" onClick={() => saveCap(null)}>بدون سقف</Button> : null}
            </section>
            <Table title="به تفکیک موتور" head={['موتور', 'هزینه', 'ثانیه']} rows={m.by_engine.map((x) => [x.engine, dollars(x.usd), String(Math.round(x.seconds))])} />
            <Table title="به تفکیک چهره" head={['چهره', 'هزینه', 'ثانیه']} rows={m.by_persona.map((x) => [personaFa(x.persona), dollars(x.usd), String(Math.round(x.seconds))])} />
            <p className="text-[13px] leading-6 text-sec"><FaText text={`فکر و جواب‌ها: ${m.talk_tokens.toLocaleString('en-US')} توکن، معادل ${dollars(m.talk_usd_equiv)}؛ این از سهمیه‌ی اشتراک میرود، نه از صورتحساب صدا.`} /></p>
            <details className="rounded-[10px] bg-tile p-3 text-[13px] leading-6 text-sec">
              <summary className="cursor-pointer font-semibold text-ink">جزئیات</summary>
              <p className="pt-2">{m.price_note_fa ?? 'این شمارنده توکن‌هایی است که خود گوگل برمیگرداند ضرب در جدول قیمت؛ صورتحساب گوگل (مالیات و ارز) ممکن است کمی فرق کند.'}</p>
            </details>
          </>
        )}
        <section aria-label="جدول قیمت" className="flex flex-col gap-2">
          <h3 className="text-[13px] font-semibold text-sec">قیمت‌ها (برای هر میلیون توکن)</h3>
          {(engines.data ?? []).filter((e) => e.provider !== 'local').map((e) => (
            <PriceRow key={e.key} e={e} onSave={(p) => act.price.mutate({ key: e.key, price: p }, { onSuccess: () => toast({ tone: 'ok', text: 'قیمت ثبت شد.' }), onError: (er) => toast({ tone: 'error', text: errText(er, 'قیمت ثبت نشد.') }) })} />
          ))}
        </section>
      </div>
    </Sheet>
  );
}
const Stat = ({ label, v }: { label: string; v: string }) => (
  <div className="flex flex-col gap-0.5 rounded-[12px] bg-tile p-3"><span className="text-[11px] text-muted">{label}</span><span className="fig text-[16px] font-semibold text-ink">{v}</span></div>
);
function Table({ title, head, rows }: { title: string; head: string[]; rows: string[][] }) {
  return (
    <section aria-label={title} className="flex flex-col gap-1.5">
      <h3 className="text-[13px] font-semibold text-sec">{title}</h3>
      <table aria-label={title} className="w-full text-[13px]">
        <thead><tr className="text-muted">{head.map((h) => <th key={h} className="pb-1 text-start font-normal">{h}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i} className="border-t border-div">{r.map((c, j) => <td key={j} className={cx('py-1.5', j > 0 && 'fig')}>{c}</td>)}</tr>)}</tbody>
      </table>
    </section>
  );
}
function PriceRow({ e, onSave }: { e: VoiceEngine; onSave: (p: { text_in_per_m: number; audio_out_per_m: number }) => void }) {
  const [edit, setEdit] = useState(false);
  const [t, setT] = useState(String(e.price.text_in_per_m));
  const [a, setA] = useState(String(e.price.audio_out_per_m));
  return (
    <div className="flex flex-col gap-2 rounded-[10px] bg-tile p-3 text-[13px]">
      <div className="flex flex-wrap items-center gap-2">
        <span className="min-w-0 flex-1 truncate text-ink"><FaText text={e.title_fa} /></span>
        {edit ? null : <span className="fig text-sec">{`ورودی ${e.price.text_in_per_m}$ · صدا ${e.price.audio_out_per_m}$`}</span>}
        <button type="button" className="font-semibold text-gold-ink hover:underline" onClick={() => setEdit(!edit)}>{edit ? 'بستن' : 'ویرایش'}</button>
      </div>
      {edit ? (
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1 text-[12px] text-sec">متن ورودی<input type="number" step="0.01" value={t} onChange={(x) => setT(x.target.value)} aria-label={`قیمت ورودی ${shortTitle(e)}`} className={cx(field, 'fig h-9 w-24')} /></label>
          <label className="flex flex-col gap-1 text-[12px] text-sec">خروجی صدا<input type="number" step="0.01" value={a} onChange={(x) => setA(x.target.value)} aria-label={`قیمت صدا ${shortTitle(e)}`} className={cx(field, 'fig h-9 w-24')} /></label>
          <Button size="sm" variant="primary" onClick={() => { onSave({ text_in_per_m: Number(t), audio_out_per_m: Number(a) }); setEdit(false); }}>ثبت</Button>
        </div>
      ) : null}
      {e.price.next ? <span className="text-[12px] text-muted"><FaText text={`از ${e.price.next.from}: صدا ${e.price.next.audio_out_per_m}$`} /></span> : null}
    </div>
  );
}

// ==================================================================================== voices of the personas ==
/** Per persona: the engine and the voice, and «بشنو» (a short sample whose cost is on the meter). */
export function VoicesPanel({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const personas = usePersonas();
  const engines = useEngines();
  const save = useSavePersona();
  const act = useVoiceActions();
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const hear = (key: string, engine: string, voice: string) => {
    setBusy(key);
    act.sample.mutate({ engine, voice }, {
      onSuccess: (r) => { const a = new Audio(fileUrl(r.file_id)); a.play().catch(() => toast({ tone: 'info', text: 'مرورگر پخش را نگذاشت؛ یک بار روی صفحه بزن و دوباره امتحان کن.' })); },
      onError: (e) => toast({ tone: 'error', text: errText(e, 'نمونه ساخته نشد.') }),
      onSettled: () => setBusy(null),
    });
  };
  return (
    <Sheet open={open} onOpenChange={onOpenChange} title="صدای هر چهره" description="هر چهره صدای خودش را دارد؛ با گوش خودت انتخاب کن" width={520}>
      <div className="flex flex-col gap-3" aria-label="صدا‌ها">
        {personas.data === null ? <p className="text-[13px] text-muted">این بخش بعد از به‌روزرسانی ستاد میاید.</p> : (personas.data ?? []).map((p) => {
          const eng = (engines.data ?? []).find((e) => e.key === p.voice.engine) ?? engines.data?.[0];
          const voices = eng?.voices ?? [];
          return (
            <div key={p.key} className="flex flex-col gap-2 rounded-[12px] bg-tile p-3" role="group" aria-label={`صدای ${p.title_fa}`}>
              <b className="text-[14px] text-ink">{p.title_fa}</b>
              <div className="flex flex-wrap items-center gap-2">
                <select aria-label={`موتور ${p.title_fa}`} value={p.voice.engine} onChange={(e) => save.mutate({ key: p.key, engine: e.target.value })} className={cx(field, 'h-9 w-auto min-w-0 flex-1')}>
                  {(engines.data ?? []).map((e) => <option key={e.key} value={e.key}>{e.title_fa}</option>)}
                </select>
                <select aria-label={`صدای ${p.title_fa}`} value={p.voice.voice} onChange={(e) => save.mutate({ key: p.key, voice: e.target.value })} className={cx(field, 'h-9 w-auto min-w-0 flex-1')}>
                  {voices.map((v) => <option key={v.name} value={v.name}>{`${v.name} · ${v.gender_fa}`}</option>)}
                  {voices.length && !voices.some((v) => v.name === p.voice.voice) ? <option value={p.voice.voice}>{p.voice.voice}</option> : null}
                </select>
                <Button size="sm" icon="resume" loading={busy === p.key} onClick={() => hear(p.key, p.voice.engine, p.voice.voice)}>بشنو</Button>
              </div>
            </div>
          );
        })}
      </div>
    </Sheet>
  );
}
