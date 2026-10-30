'use client';

import { useRouter } from 'next/navigation';
import { useMemo, useRef, useState, type ReactNode } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Card, PageHeader } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { inputCls } from '@/components/v21/bits';
import type { IconName } from '@/generated/icons';
import { ApiError } from '@/lib/api/client';
import { useCompanies } from '@/lib/api/hooks';
import { uploadFile } from '@/lib/api/v13';
import { useFoundings } from '@/lib/api/v14';
import { useStartFounding } from '@/lib/api/v21';
import { EMPTY_DRAFT, STEPS, cleanCode, firstIncomplete, foundingIn, repoOf, stepErrors, type FoundingDraft, type FoundingPath } from '@/lib/founding';
import { cx } from '@/lib/format';

// «تأسیس شرکت» (0.5.0; the Android app's ui/founding/Wizard.kt): the one way to make a company, in four short steps — who it is (Persian name,
// a 2–4 letter code, one line), how it starts (an idea, a GitHub repository, or only registered for now), its brand (a logo seen in its
// circle and a colour, optional), and a review that says exactly what happens next. Nothing reaches the hub before the last step.

const STEP_FA = ['کیست', 'شروع', 'نشان', 'تأیید'];
type Way = { path: FoundingPath; title: string; icon: IconName; what: string; next: string };
const WAYS: Way[] = [
  { path: 'idea', title: 'از یک ایده', icon: 'learning', what: 'بگو چه میخواهی بسازی؛ مشتری، کار اصلی و درآمد.', next: 'مدیر AI Ops پیشنهاد کامل مینویسد (ساختار، تیم، بودجه، نقشه‌ی ۹۰ روزه) و برای مُهر به کارتابلت میاید.' },
  { path: 'repo', title: 'از یک ریپوی GitHub', icon: 'code', what: 'کدی که داری؛ آدرس ریپو را بده.', next: 'اول ممیزی فقط‌خواندنی کد (معماری، کیفیت، امنیت، تست، بدهی فنی)، بعد پیشنهاد کامل؛ هر دو به کارتابلت میاید.' },
  { path: 'blank', title: 'فقط ثبت کن، بعداً کامل میکنم', icon: 'companies', what: 'شرکت همین حالا با نام و کدش ثبت میشود.', next: 'با دپارتمان‌های الگوی استاندارد و بی‌کارمند و بی‌سرور ساخته میشود؛ استخدام، نشان و سرور را بعداً از صفحه‌ی شرکت کامل میکنی.' },
];

const Err = ({ text }: { text?: string }) => (text ? <span className="text-[12px] text-neg">{text}</span> : null);
const Label = ({ text, note }: { text: string; note?: string }) => (
  <span className="flex flex-wrap items-baseline gap-x-2"><span className="text-[12px] font-semibold text-sec">{text}</span>{note ? <span className="text-[11px] text-muted">{note}</span> : null}</span>
);

/** Four numbered steps; a done one is ticked and goes back when touched. */
function Steps({ at, onBack }: { at: number; onBack: (n: number) => void }) {
  return (
    <ol className="flex gap-1.5">
      {STEP_FA.map((fa, i) => {
        const n = i + 1;
        const cls = n < at ? 'bg-pos-soft text-pos' : n === at ? 'bg-gold-soft text-gold-ink' : 'bg-tile text-muted';
        return (
          <li key={fa} className="flex-1">
            <button type="button" disabled={n >= at} onClick={() => onBack(n)} aria-label={n < at ? `برگرد به ${fa}` : fa} aria-current={n === at ? 'step' : undefined}
              className={cx('flex h-8 w-full items-center justify-center gap-1.5 rounded-full px-2 text-[12px] transition-colors', cls, n === at && 'font-semibold', n < at && 'hover:brightness-110')}>
              {n < at ? <Icon name="seal" size={12} active /> : <span className="text-[11px] font-semibold">{n}</span>}
              <span className="truncate">{fa}</span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

function Who({ d, set, errors }: { d: FoundingDraft; set: (p: Partial<FoundingDraft>) => void; errors: Record<string, string> }) {
  return (
    <Card className="flex flex-col gap-4 p-5">
      <h2 className="text-h3 font-semibold">شرکت تازه چیست؟</h2>
      <label className="flex flex-col gap-1.5"><Label text="نام شرکت" /><input value={d.nameFa} onChange={(e) => set({ nameFa: e.target.value })} maxLength={60} placeholder="مثلاً دایرکت هوشمند" className={inputCls} /><Err text={errors.name} /></label>
      <label className="flex flex-col gap-1.5"><Label text="کد" note="۲ تا ۴ حرف لاتین؛ یک بار داده میشود و عوض نمیشود" />
        <input dir="ltr" value={d.code} onChange={(e) => set({ code: cleanCode(e.target.value) })} maxLength={4} placeholder="IG" autoComplete="off" className={cx(inputCls, 'fig text-left')} /><Err text={errors.code} /></label>
      <label className="flex flex-col gap-1.5"><Label text="در یک خط چه میکند" /><input value={d.tagline} onChange={(e) => set({ tagline: e.target.value.replace(/\n/g, ' ') })} maxLength={140} placeholder="مثلاً پاسخ خودکار و فروش در دایرکت اینستاگرام" className={inputCls} /><Err text={errors.tagline} /></label>
      <span className="text-[12px] text-muted">کد روی کارت‌ها، کارمندها (مثل <span className="fig">IG-CEO</span>) و گزارش‌ها میاید.</span>
    </Card>
  );
}

function How({ d, set, errors }: { d: FoundingDraft; set: (p: Partial<FoundingDraft>) => void; errors: Record<string, string> }) {
  return (
    <div className="flex flex-col gap-3" role="radiogroup" aria-label="از کجا شروع کنیم؟">
      <h2 className="text-h3 font-semibold">از کجا شروع کنیم؟</h2>
      {WAYS.map((w) => {
        const on = d.path === w.path;
        return (
          <div key={w.path} className={cx('flex flex-col gap-2 rounded-[16px] p-4 transition-colors duration-200', on ? 'tahrir bg-gold-soft' : 'bg-card hover:bg-hover')}>
            <button type="button" role="radio" aria-checked={on} onClick={() => set({ path: w.path })} className="flex items-center gap-3 text-start">
              <span className={cx('flex size-10 flex-none items-center justify-center rounded-full', on ? 'bg-gold text-on-gold' : 'bg-tile text-sec')}><Icon name={w.icon} size={20} /></span>
              <span className="flex min-w-0 flex-1 flex-col"><span className="text-[15px] font-semibold">{w.title}</span><span className="text-[12px] text-sec">{w.what}</span></span>
              <span className={cx('flex size-5 flex-none items-center justify-center rounded-full border-2', on ? 'border-gold-ink' : 'border-strong')}>{on ? <span className="size-2.5 rounded-full bg-gold-ink" /> : null}</span>
            </button>
            <span className="flex gap-1.5 text-[12px] text-muted"><span className="font-semibold">بعدش:</span><span className="flex-1">{w.next}</span></span>
            {on && w.path === 'idea' ? (
              <label className="flex flex-col gap-1.5 pt-1"><Label text="ایده" />
                <textarea value={d.idea} onChange={(e) => set({ idea: e.target.value })} rows={4} maxLength={4000} placeholder="چه میسازد، برای چه کسی، از کجا درآمد دارد، چه محدودیتی هست" className={cx(inputCls, 'h-auto py-3 leading-7')} /><Err text={errors.path} /></label>
            ) : on && w.path === 'repo' ? (
              <label className="flex flex-col gap-1.5 pt-1"><Label text="ریپو" />
                <input dir="ltr" value={d.repo} onChange={(e) => set({ repo: e.target.value.trim() })} maxLength={220} placeholder="github.com/owner/name" className={cx(inputCls, 'fig text-left')} /><Err text={errors.path} /></label>
            ) : null}
          </div>
        );
      })}
      {!d.path ? <Err text={errors.path} /> : null}
    </div>
  );
}

/** Step 3 (optional): the logo, seen in its circle as the company's mark will be, and a colour from the companies' palette. */
function Brand({ d, set, used, preview, setPreview }: { d: FoundingDraft; set: (p: Partial<FoundingDraft>) => void; used: Set<number>; preview: string | null; setPreview: (u: string | null) => void }) {
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [state, setState] = useState<{ pct: number; error: string | null } | null>(null);
  const pick = async (f: File | undefined) => {
    if (!f) return;
    if (!['image/png', 'image/webp', 'image/jpeg'].includes(f.type)) { toast({ tone: 'error', text: 'لوگو باید PNG (بهتر با زمینه‌ی شفاف)، WebP یا JPEG باشد.' }); return; }
    setPreview(URL.createObjectURL(f));
    setState({ pct: 0, error: null });
    try {
      const ref = await uploadFile(f, f.name, (pct) => setState({ pct, error: null }));
      set({ logoFileId: ref.id });
      setState(null);
    } catch (e) { setState({ pct: 0, error: e instanceof ApiError ? e.messageFa : 'بارگذاری نشد.' }); }
  };
  const ring = d.colorIndex ? `var(--hq-chart-${d.colorIndex})` : 'var(--hq-line-strong)';
  return (
    <Card className="flex flex-col gap-5 p-5">
      <div className="flex flex-col gap-0.5"><h2 className="text-h3 font-semibold">نشان و رنگ</h2><span className="text-[12px] text-muted">اختیاری؛ میتوانی بعداً از صفحه‌ی شرکت بدهی. تا آن موقع کد جای نشان را میگیرد.</span></div>
      <div className="flex flex-wrap items-center gap-5">
        <span className="flex size-28 flex-none items-center justify-center overflow-hidden rounded-full border-[3px] bg-tile transition-colors" style={{ borderColor: ring }}>
          {preview
            // eslint-disable-next-line @next/next/no-img-element
            ? <img src={preview} alt="لوگو در دایره" className="size-full object-cover" />
            : <span className="fig text-[28px] font-semibold" style={{ color: d.colorIndex ? ring : 'var(--hq-text-secondary)' }}>{d.code || 'IG'}</span>}
        </span>
        <div className="flex min-w-0 flex-[1_1_14rem] flex-col gap-2">
          <span className="text-[13px] text-ink">{preview ? 'این‌طور در دایره دیده میشود' : 'هنوز لوگو نداده‌ای'}</span>
          {state?.error ? <span className="text-[12px] text-neg">{state.error}</span> : state ? <span className="fig text-[12px] text-muted">{state.pct}%</span>
            : <span className="text-[12px] text-muted">PNG با زمینه‌ی شفاف بهترین است؛ نشان نهایی از آن ساخته میشود و پیش از مُهر می‌بینی‌اش.</span>}
          <div className="flex flex-wrap gap-2">
            <Button size="sm" icon="image" onClick={() => input.current?.click()}>{preview ? 'عوض کن' : 'انتخاب لوگو'}</Button>
            {preview ? <Button size="sm" variant="text" icon="close" onClick={() => { setPreview(null); set({ logoFileId: null }); setState(null); }}>بردار</Button> : null}
          </div>
          <input ref={input} type="file" accept="image/png,image/webp,image/jpeg" className="hidden" onChange={(e) => { void pick(e.target.files?.[0]); e.target.value = ''; }} />
        </div>
      </div>
      <div className="flex flex-col gap-2">
        <Label text="رنگ شرکت" note="در نمودارها و کارت‌ها؛ رنگ‌های گرفته‌شده کم‌رنگ‌اند" />
        <div className="flex flex-wrap gap-2.5" role="radiogroup" aria-label="رنگ شرکت">
          <button type="button" role="radio" aria-checked={d.colorIndex == null} onClick={() => set({ colorIndex: null })}
            className={cx('flex size-9 items-center justify-center rounded-full bg-tile text-[10px] text-sec', d.colorIndex == null ? 'ring-[3px] ring-[var(--hq-gold-ink)]' : 'ring-1 ring-[var(--hq-line-strong)]')}>خودکار</button>
          {Array.from({ length: 8 }, (_, i) => i + 1).map((n) => {
            const taken = used.has(n) && d.colorIndex !== n;
            return (
              <button key={n} type="button" role="radio" aria-checked={d.colorIndex === n} disabled={taken} onClick={() => set({ colorIndex: n })} aria-label={taken ? 'این رنگ را شرکت دیگری دارد' : 'رنگ شرکت'}
                className={cx('flex size-9 items-center justify-center rounded-full text-white transition-transform enabled:hover:scale-105 disabled:opacity-35', d.colorIndex === n ? 'ring-[3px] ring-[var(--hq-gold-ink)] ring-offset-2 ring-offset-[var(--hq-surface-card)]' : 'ring-1 ring-[var(--hq-line-strong)]')}
                style={{ background: `var(--hq-chart-${n})` }}>{d.colorIndex === n ? <Icon name="seal" size={14} active /> : null}</button>
            );
          })}
        </div>
      </div>
      {d.path !== 'blank' ? <span className="text-[12px] text-muted">شرکت بعد از مُهر پیشنهاد ساخته میشود؛ لوگو و رنگ همراه تأسیس میروند و در قدم «مُهر شرکت» به کار میروند.</span> : null}
    </Card>
  );
}

/** Step 4: everything on one card, each part with «ویرایش», and what happens the moment the owner confirms. */
function Review({ d, preview, edit }: { d: FoundingDraft; preview: string | null; edit: (n: number) => void }) {
  const way = WAYS.find((w) => w.path === d.path);
  const ring = d.colorIndex ? `var(--hq-chart-${d.colorIndex})` : 'var(--hq-line-strong)';
  const lines = d.path === 'blank' ? [
    'شرکت همین حالا ثبت میشود؛ با دپارتمان‌های الگوی استاندارد، بی‌کارمند و بی‌سرور.',
    d.logoFileId ? 'نشانش از لوگو ساخته میشود و در صفحه‌ی شرکت منتظر مُهر تو میماند.' : 'تا نشان بدهی، کد جای نشان را میگیرد.',
    'استخدام، نشان و سرور را هر وقت خواستی از صفحه‌ی شرکت کامل کن.',
  ] : d.path === 'repo' ? [
    'ممیزی فقط‌خواندنی ریپو شروع میشود؛ هیچ چیز اجرا یا push نمیشود.',
    'بعد پیشنهاد کامل (نام، تیم، بودجه، نقشه‌ی راه) و طرح سرور به کارتابلت میاید.',
    'شرکت فقط با مُهر تو ساخته میشود و سرور با مُهر جدا (هزینه‌ی واقعی).',
  ] : [
    'پیشنهاد کامل (ساختار، تیم، بودجه، نقشه‌ی ۹۰ روزه) نوشته میشود و به کارتابلت میاید.',
    'شرکت فقط با مُهر تو ساخته میشود و سرور با مُهر جدا (هزینه‌ی واقعی).',
    'هر قدم را در صفحه‌ی تأسیس می‌بینی؛ تا پیش از ساخت سرور میتوانی لغوش کنی.',
  ];
  const row = (n: number, body: ReactNode) => (
    <div className="flex items-center gap-3 border-t border-div py-3 first:border-0 first:pt-0 last:pb-0">{body}<Button variant="text" size="sm" onClick={() => edit(n)}>ویرایش</Button></div>
  );
  return (
    <div className="flex flex-col gap-3">
      <Card className="flex flex-col p-5">
        {row(1, <>
          <span className="flex size-14 flex-none items-center justify-center overflow-hidden rounded-full border-2 bg-tile" style={{ borderColor: ring }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            {preview ? <img src={preview} alt="" className="size-full object-cover" /> : <span className="fig text-[16px] font-semibold" style={{ color: d.colorIndex ? ring : undefined }}>{d.code}</span>}
          </span>
          <span className="flex min-w-0 flex-1 flex-col"><span className="text-h2 font-semibold">{d.nameFa.trim()}</span><span className="line-clamp-2 text-[12px] text-sec"><span className="fig text-muted">{d.code}</span>  ·  {d.tagline.trim()}</span></span>
        </>)}
        {row(2, <>
          {way ? <span className="text-gold-ink"><Icon name={way.icon} size={18} /></span> : null}
          <span className="flex min-w-0 flex-1 flex-col"><span className="text-[14px] font-semibold">{way?.title ?? '—'}</span>
            {d.path === 'repo' ? <span className="fig text-[12px] text-muted">{repoOf(d.repo) ?? d.repo}</span> : d.path === 'idea' ? <span className="line-clamp-3 text-[12px] text-muted">{d.idea.trim()}</span> : null}</span>
        </>)}
        {row(3, <>
          <span className="text-sec"><Icon name="image" size={18} /></span>
          <span className="flex-1 text-[13px] text-sec">{[d.logoFileId ? 'لوگو داده شد' : 'بی‌لوگو (بعداً)', d.colorIndex ? 'رنگ انتخاب شد' : 'رنگ خودکار'].join('، ')}</span>
        </>)}
      </Card>
      <Card className="flex flex-col gap-2 bg-gold-soft p-5">
        <span className="text-[14px] font-semibold text-gold-ink">با تأیید تو</span>
        <ol className="flex flex-col gap-1.5">{lines.map((l, i) => <li key={i} className="flex gap-2 text-[13px] leading-6 text-ink"><span className="w-4 flex-none font-semibold text-gold-ink">{i + 1}.</span><span>{l}</span></li>)}</ol>
      </Card>
    </div>
  );
}

export default function FoundingWizardPage() {
  const router = useRouter();
  const toast = useToast();
  const start = useStartFounding();
  const companies = useCompanies();
  const foundings = useFoundings();
  const [step, setStep] = useState(1);
  const [d, setD] = useState<FoundingDraft>(EMPTY_DRAFT);
  // Errors show once the owner tried to go on, never on an empty form at first sight.
  const [tried, setTried] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);
  const taken = useMemo(() => new Set([
    ...(companies.data ?? []).map((c) => c.code),
    ...(foundings.data?.pages.flatMap((p) => p.items) ?? []).filter((f) => f.state !== 'cancelled').map((f) => f.code).filter((c): c is string => !!c),
  ]), [companies.data, foundings.data]);
  const used = useMemo(() => new Set((companies.data ?? []).filter((c) => c.code !== d.code).map((c) => c.color_index).filter((x): x is number => !!x)), [companies.data, d.code]);
  const errors = stepErrors(step, d, taken);
  const set = (p: Partial<FoundingDraft>) => setD((x) => ({ ...x, ...p }));

  const submit = async () => {
    const bad = firstIncomplete(d, taken);
    if (bad) { setTried(true); setStep(bad); return; }
    try {
      const f = await start.mutateAsync(foundingIn(d));
      if (d.path === 'blank') {
        toast({ tone: 'ok', text: d.logoFileId ? `${d.nameFa.trim()} ثبت شد؛ نشانش در صفحه‌ی شرکت منتظر مُهر توست.` : `${d.nameFa.trim()} ثبت شد.` });
        router.replace(`/companies/${f.company ?? d.code}`);
      } else {
        toast({ tone: 'ok', text: d.path === 'repo' ? 'تأسیس شروع شد؛ ممیزی ریپو در جریان است.' : 'تأسیس شروع شد؛ پیشنهاد در حال نوشتن است.' });
        router.replace(`/founding/${f.ref}`);
      }
    } catch (e) {
      if (e instanceof ApiError && e.code === 'code_taken') { setTried(true); setStep(1); }
      toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'شروع نشد.' });
    }
  };

  return (
    <>
      <PageHeader eyebrow="چهار قدم کوتاه؛ تا قدم آخر چیزی ساخته نمیشود" title="تأسیس شرکت" />
      <div className="flex max-w-2xl flex-col gap-4">
        <Steps at={step} onBack={(n) => { setStep(n); setTried(false); }} />
        <div key={step} className="hq-rise">
          {step === 1 ? <Who d={d} set={set} errors={tried ? errors : {}} />
            : step === 2 ? <How d={d} set={set} errors={tried ? errors : {}} />
            : step === 3 ? <Brand d={d} set={set} used={used} preview={preview} setPreview={setPreview} />
            : <Review d={d} preview={preview} edit={(n) => setStep(n)} />}
        </div>
        <div className="flex gap-2">
          {step > 1 ? <Button variant="ghost" icon="back" className="flex-1" onClick={() => { setStep(step - 1); setTried(false); }}>قبلی</Button> : null}
          {step < STEPS ? (
            <Button variant="primary" iconEnd="next" className="flex-1" onClick={() => { if (!Object.keys(errors).length) { setStep(step + 1); setTried(false); } else setTried(true); }}>
              {step === 3 && !d.logoFileId && !d.colorIndex ? 'بعداً؛ بعدی' : 'بعدی'}
            </Button>
          ) : d.path === 'blank'
            ? <Button variant="primary" icon="seal" className="flex-[1.4]" loading={start.isPending} onClick={submit}>ثبت کن</Button>
            : <Button variant="primary" icon="found" className="flex-[1.4]" loading={start.isPending} onClick={submit}>شروع تأسیس</Button>}
        </div>
      </div>
    </>
  );
}
