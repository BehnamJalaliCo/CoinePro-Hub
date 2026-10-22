'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Icon } from '@/components/icon';
import { ModelMark, ModelName } from '@/components/brand/model-mark';
import { Button } from '@/components/ui/button';
import { Sheet } from '@/components/ui/overlay';
import { Card, FilterChip, Pill, SectionTitle, Segmented, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { useConnections } from '@/lib/api/hooks';
import { useTreasuryAction } from '@/lib/api/v15';
import { ROUTER_PROVIDERS, faError, publicHttps, useCreateConnection, type Connection18, type ConnectionIn } from '@/lib/api/v18';
import { cx } from '@/lib/format';
import { CONN } from './bits';

const field = 'h-10 w-full rounded-[10px] border border-strong bg-card px-3 text-[14px] text-ink outline-none focus:border-gold-ink';
const PROVIDER_FA: Record<string, string> = { anthropic: 'Anthropic', openai: 'OpenAI', google: 'Google', deepseek: 'DeepSeek', mistral: 'Mistral', openai_compatible: 'سازگار با OpenAI' };
const STEPS = ['ارائه‌دهنده', 'مدل‌ها و قیمت', 'مرور و مُهر', 'کلید'];
const KEY_RE = /^[a-z0-9][a-z0-9-]{2,39}$/;
const dec = (s: string) => s.trim() !== '' && Number.isFinite(Number(s)) && Number(s) >= 0;

type Draft = {
  provider: string; kind: 'api_key' | 'subscription'; key: string; display_name: string; base_url: string; models: string; default_model: string;
  price: Record<string, { in: string; out: string }>; rpm: string; tpm: string; daily_usd: string; fallback: string;
};
const EMPTY: Draft = { provider: 'openai', kind: 'api_key', key: '', display_name: '', base_url: '', models: '', default_model: '', price: {}, rpm: '', tpm: '', daily_usd: '', fallback: '' };
const modelsOf = (d: Draft) => [...new Set(d.models.split(/[\s,،]+/).map((x) => x.trim()).filter(Boolean))];

function bodyOf(d: Draft): ConnectionIn {
  const models = modelsOf(d);
  const limits: ConnectionIn['limits'] = {};
  if (d.rpm.trim()) limits.rpm = Number(d.rpm);
  if (d.tpm.trim()) limits.tpm = Number(d.tpm);
  if (d.daily_usd.trim()) limits.daily_usd = Number(d.daily_usd).toFixed(2);
  return {
    key: d.key.trim(), provider: d.provider, kind: d.kind, display_name: d.display_name.trim(),
    ...(d.provider === 'openai_compatible' && d.base_url.trim() ? { base_url: d.base_url.trim() } : {}),
    models, ...(d.default_model && models.includes(d.default_model) ? { default_model: d.default_model } : {}),
    pricing: Object.fromEntries(models.filter((m) => d.price[m] && dec(d.price[m]!.in) && dec(d.price[m]!.out)).map((m) => [m, { input_per_mtok: Number(d.price[m]!.in).toFixed(2), output_per_mtok: Number(d.price[m]!.out).toFixed(2) }])),
    limits, ...(d.fallback.trim() ? { fallback_priority: Number(d.fallback) } : {}),
  };
}

/** The secret step: the existing write-only route with a passkey, or the owner's own terminal; then a no-cost check by the router. */
function SecretStep({ c, onDone }: { c: Connection18; onDone: () => void }) {
  const conns = useConnections();
  const act = useTreasuryAction();
  const toast = useToast();
  const [secret, setSecret] = useState('');
  const live = ((conns.data ?? []) as unknown as Connection18[]).find((x) => x.id === c.id) ?? c;
  const st = CONN[live.status] ?? { fa: live.status, tone: 'neutral' as const };
  const { refetch } = conns;
  useEffect(() => {
    if (live.status !== 'verifying' && live.status !== 'pending_secret') return;
    const t = setInterval(() => void refetch(), 2_000);
    return () => clearInterval(t);
  }, [live.status, refetch]);
  const cmd = `make connection-secret KEY=${live.key}`;
  if (live.kind === 'subscription') {
    return (
      <div className="flex flex-col gap-3 text-[13px] leading-6 text-sec">
        <p>اشتراک کلید API ندارد؛ با ورود خود CLI وصل میشود (کد دستگاه از اپ، یا ترمینال خودت).</p>
        <Link href="/substitutes" className="inline-flex items-center gap-1.5 self-start text-gold-ink hover:underline"><Icon name="agent" size={16} />بازیکن‌های ذخیره و ورودشان</Link>
        <Button variant="secondary" onClick={onDone} className="self-start">بستن</Button>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-4 text-[13px]">
      <div className="flex items-center gap-2"><ModelMark provider={live.provider} model={live.default_model ?? live.models[0]} size={20} /><span className="font-semibold text-ink">{live.display_name}</span><span className="fig text-[11px] text-muted">{live.key}</span><span className="flex-1" /><Pill tone={st.tone} dot live={live.status === 'verifying'}>{st.fa}</Pill></div>
      {live.status === 'ready' || live.status === 'enabled' ? (
        <p className="flex items-start gap-2 rounded-[12px] bg-pos-soft p-3 leading-6 text-ink"><Icon name="seal" size={16} className="mt-1 text-pos" />مسیریاب کلید را با یک فراخوانی بی‌هزینه سنجید. استفاده از این اتصال فقط با تخصیص (PUT /assignments) و مُهر توست.</p>
      ) : live.status === 'error' ? (
        <p className="rounded-[12px] bg-neg-soft p-3 leading-6 text-ink">سنجش نشد: {live.status_reason ?? '—'}. کلید تازه بده.</p>
      ) : live.status === 'verifying' ? (
        <p className="rounded-[12px] bg-lapis-soft p-3 leading-6 text-ink">کلید رسید؛ مسیریاب با فهرست مدل‌ها (بی‌هزینه، از درگاه خروجی) آن را میسنجد…</p>
      ) : null}
      {live.status === 'pending_secret' || live.status === 'error' ? (
        <>
          <label className="flex flex-col gap-1.5 font-semibold text-sec">کلید، همین‌جا
            <input type="password" autoComplete="off" value={secret} onChange={(e) => setSecret(e.target.value)} dir="ltr" placeholder="sk-…" className={cx(field, 'fig')} />
            <span className="text-[11px] font-normal text-muted">فقط‌نوشتنی: مستقیم به خزانه‌ی رمزها میرود و نه این‌جا، نه در پاسخ، نه در لاگ و نه در Audit برنمیگردد.</span>
          </label>
          <Button variant="primary" icon="seal" disabled={!secret.trim()} loading={act.secret.isPending} className="self-start"
            onClick={async () => { try { await act.secret.mutateAsync({ id: live.id, secret: secret.trim() }); setSecret(''); toast({ tone: 'ok', text: 'کلید رفت؛ در حال سنجش.' }); void refetch(); } catch (e) { toast({ tone: 'error', text: faError(e) }); } }}>ذخیره با passkey</Button>
          <div className="flex flex-col gap-1.5 rounded-[12px] bg-tile p-3">
            <span className="text-[12px] font-semibold text-sec">یا در ترمینال خودت (ورودی پنهان، مستقیم به OpenBao)</span>
            <div className="flex items-center gap-2"><code dir="ltr" className="fig min-w-0 flex-1 truncate rounded-[8px] bg-page px-2 py-1.5 text-[12px] text-ink">{cmd}</code>
              <Button size="sm" variant="ghost" icon="share" onClick={() => void navigator.clipboard?.writeText(cmd).then(() => toast({ tone: 'info', text: 'کپی شد.' }), () => undefined)}>کپی</Button></div>
          </div>
        </>
      ) : null}
      <Button variant="secondary" onClick={onDone} className="self-start">{live.status === 'ready' || live.status === 'enabled' ? 'تمام' : 'بعداً'}</Button>
    </div>
  );
}

/** «افزودن اتصال» (§21.7): provider, models and prices, sealed on the exact body; then the secret, by the app or the terminal. */
export function ConnectionWizard({ onClose, resume }: { onClose: () => void; resume?: Connection18 | null }) {
  const [step, setStep] = useState(resume ? 3 : 0);
  const [d, setD] = useState<Draft>(EMPTY);
  const [made, setMade] = useState<Connection18 | null>(resume ?? null);
  const [idem] = useState(() => crypto.randomUUID());
  const create = useCreateConnection();
  const toast = useToast();
  const set = (p: Partial<Draft>) => setD((x) => ({ ...x, ...p }));
  const models = modelsOf(d);
  const baseOk = d.provider !== 'openai_compatible' || (d.base_url.trim() !== '' && publicHttps(d.base_url.trim()));
  const ok0 = KEY_RE.test(d.key.trim()) && d.display_name.trim().length >= 2 && baseOk;
  const ok1 = models.length > 0 && Object.values(d.price).every((p) => (p.in === '' || dec(p.in)) && (p.out === '' || dec(p.out)));
  const seal = async () => {
    try { const c = await create.mutateAsync({ body: bodyOf(d), key: idem }); setMade(c); setStep(3); toast({ tone: 'ok', text: <>اتصال <span className="fig">{c.key}</span> ساخته شد؛ منتظر کلید است.</> }); } catch (e) { toast({ tone: 'error', text: faError(e) }); }
  };
  return (
    <Sheet open onOpenChange={(v) => !v && onClose()} width={600} title="اتصال تازه‌ی مدل" description="فقط ارائه‌دهنده‌ای که مسیریاب میشناسد؛ نشانی پایه فقط برای سازگار با OpenAI و از محافظ خروجی. استفاده‌اش بعداً فقط با تخصیص و مُهر تو."
      footer={step < 3 ? (
        <div className="flex flex-wrap items-center gap-2">
          {step > 0 ? <Button variant="ghost" icon="back" onClick={() => setStep(step - 1)}>قبلی</Button> : null}
          <span className="flex-1" />
          {step < 2 ? <Button variant="primary" iconEnd="next" disabled={step === 0 ? !ok0 : !ok1} onClick={() => setStep(step + 1)}>بعدی</Button>
            : <Button variant="primary" icon="seal" loading={create.isPending} onClick={seal}>ساختن با passkey</Button>}
        </div>
      ) : undefined}>
      <ol className="mb-4 flex flex-wrap items-center gap-1.5 text-[12px]" aria-label="گام‌ها">
        {STEPS.map((s, i) => <li key={s} className={cx('flex items-center gap-1.5 rounded-full px-2.5 py-1', i === step ? 'bg-gold-soft font-semibold text-gold-ink' : i < step ? 'text-sec' : 'text-muted')}><span>{i + 1}</span>{s}</li>)}
      </ol>
      {step === 0 ? (
        <div className="flex flex-col gap-4 text-[13px]">
          <div className="flex flex-wrap gap-2">{ROUTER_PROVIDERS.map((p) => <FilterChip key={p} selected={d.provider === p} onClick={() => set({ provider: p })}><span className="flex items-center gap-1.5">{p !== 'openai_compatible' ? <ModelMark provider={p} size={14} /> : <Icon name="model" size={14} />}{PROVIDER_FA[p]}</span></FilterChip>)}</div>
          <Segmented label="نوع" value={d.kind} onChange={(kind) => set({ kind })} options={[{ value: 'api_key', label: 'کلید API (پولی)' }, { value: 'subscription', label: 'اشتراک' }]} />
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1.5 font-semibold text-sec">کلید اتصال<input value={d.key} onChange={(e) => set({ key: e.target.value.toLowerCase() })} dir="ltr" placeholder="mistral-api" className={cx(field, 'fig', d.key && !KEY_RE.test(d.key) && 'border-neg')} /><span className="text-[11px] font-normal text-muted">حروف کوچک لاتین، عدد و خط تیره؛ یکتا</span></label>
            <label className="flex flex-col gap-1.5 font-semibold text-sec">نام<input value={d.display_name} onChange={(e) => set({ display_name: e.target.value })} maxLength={120} placeholder="API میسترال (پشتیبان)" className={field} /></label>
          </div>
          {d.provider === 'openai_compatible' ? (
            <label className="flex flex-col gap-1.5 font-semibold text-sec">نشانی پایه
              <input value={d.base_url} onChange={(e) => set({ base_url: e.target.value })} dir="ltr" placeholder="https://api.example.com/v1" className={cx(field, 'fig', d.base_url && !publicHttps(d.base_url) && 'border-neg')} />
              <span className={cx('text-[11px] font-normal', d.base_url && !publicHttps(d.base_url) ? 'text-neg' : 'text-muted')}>فقط https و هرگز نشانی خصوصی (شبکه‌ی هتزنر، localhost)؛ از محافظ خروجی رد میشود.</span>
            </label>
          ) : null}
        </div>
      ) : step === 1 ? (
        <div className="flex flex-col gap-4 text-[13px]">
          <label className="flex flex-col gap-1.5 font-semibold text-sec">مدل‌ها<textarea value={d.models} onChange={(e) => set({ models: e.target.value })} rows={2} dir="ltr" placeholder="mistral-large-3, mistral-small-3" className="fig w-full rounded-[10px] border border-strong bg-card p-3 text-[13px] text-ink outline-none focus:border-gold-ink" /><span className="text-[11px] font-normal text-muted">با ویرگول یا فاصله؛ شناسه‌ی هر مدل همان‌طور که ارائه‌دهنده میگوید</span></label>
          {models.length ? (
            <div className="flex flex-col gap-2">
              <span className="font-semibold text-sec">پیش‌فرض و قیمت (دلار برای هر میلیون توکن)</span>
              {models.map((m) => (
                <div key={m} className="grid grid-cols-[auto_minmax(0,1fr)_5.5rem_5.5rem] items-center gap-2 rounded-[12px] bg-tile p-2">
                  <input type="radio" name="default-model" checked={d.default_model === m} onChange={() => set({ default_model: m })} aria-label={`پیش‌فرض: ${m}`} className="accent-[var(--hq-gold-fill)]" />
                  <ModelName model={m} provider={d.provider} size={13} className="min-w-0 truncate text-[12px]" />
                  <input value={d.price[m]?.in ?? ''} onChange={(e) => set({ price: { ...d.price, [m]: { in: e.target.value, out: d.price[m]?.out ?? '' } } })} inputMode="decimal" dir="ltr" placeholder="ورودی" aria-label={`${m}: قیمت ورودی`} className={cx(field, 'fig h-9 px-2 text-center text-[12px]')} />
                  <input value={d.price[m]?.out ?? ''} onChange={(e) => set({ price: { ...d.price, [m]: { in: d.price[m]?.in ?? '', out: e.target.value } } })} inputMode="decimal" dir="ltr" placeholder="خروجی" aria-label={`${m}: قیمت خروجی`} className={cx(field, 'fig h-9 px-2 text-center text-[12px]')} />
                </div>
              ))}
            </div>
          ) : null}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <label className="flex flex-col gap-1.5 text-[12px] font-semibold text-sec">در دقیقه<input value={d.rpm} onChange={(e) => set({ rpm: e.target.value.replace(/\D/g, '') })} inputMode="numeric" dir="ltr" placeholder="rpm" className={cx(field, 'fig text-center')} /></label>
            <label className="flex flex-col gap-1.5 text-[12px] font-semibold text-sec">توکن در دقیقه<input value={d.tpm} onChange={(e) => set({ tpm: e.target.value.replace(/\D/g, '') })} inputMode="numeric" dir="ltr" placeholder="tpm" className={cx(field, 'fig text-center')} /></label>
            <label className="flex flex-col gap-1.5 text-[12px] font-semibold text-sec">سقف روزانه ($)<input value={d.daily_usd} onChange={(e) => set({ daily_usd: e.target.value })} inputMode="decimal" dir="ltr" placeholder="10.00" className={cx(field, 'fig text-center')} /></label>
            <label className="flex flex-col gap-1.5 text-[12px] font-semibold text-sec">اولویت پشتیبان<input value={d.fallback} onChange={(e) => set({ fallback: e.target.value.replace(/\D/g, '') })} inputMode="numeric" dir="ltr" placeholder="6" className={cx(field, 'fig text-center')} /></label>
          </div>
        </div>
      ) : step === 2 ? (
        <div className="flex flex-col gap-3 text-[13px]">
          <div className="flex items-center gap-2"><ModelMark provider={d.provider} size={20} /><span className="font-semibold text-ink">{d.display_name}</span><span className="fig text-[11px] text-muted">{d.key}</span><Pill tone="neutral">{d.kind === 'api_key' ? 'کلید API' : 'اشتراک'}</Pill></div>
          <p className="leading-6 text-sec">passkey به SHA-256 همین بدنه بسته است؛ اگر چیزی عوض شود، مُهر دیگر نمیخورد. نتیجه اتصالی «منتظر کلید» است که هنوز هیچ کاری از آن نمیگذرد.</p>
          <pre dir="ltr" className="fig max-h-72 overflow-auto rounded-[12px] bg-page p-3 text-[11px] leading-5 text-ink">{JSON.stringify(bodyOf(d), null, 2)}</pre>
        </div>
      ) : made ? <SecretStep c={made} onDone={onClose} /> : <Skeleton className="h-32" />}
    </Sheet>
  );
}

/** The model connections on the tools page, with the wizard (§21.7) and the secret step for one waiting for its key. */
export function ConnectionsCard() {
  const q = useConnections();
  const [wizard, setWizard] = useState<Connection18 | 'new' | null>(null);
  const xs = (q.data ?? []) as unknown as Connection18[];
  return (
    <Card className="flex flex-col gap-3 p-4">
      <SectionTitle title="اتصال‌های مدل" note="کلیدها هرگز نمایش داده نمیشوند؛ تخصیص هر نقش در خزانه" action={<Button size="sm" variant="primary" icon="add" onClick={() => setWizard('new')}>اتصال تازه</Button>} />
      {q.isLoading ? <Skeleton className="h-32" /> : (
        <ul className="flex flex-col gap-1.5">
          {xs.map((c) => {
            const st = CONN[c.status] ?? { fa: c.status, tone: 'neutral' as const };
            const waiting = c.status === 'pending_secret' || c.status === 'verifying' || c.status === 'error';
            return (
              <li key={c.id} className={cx('flex items-center gap-3 rounded-[12px] p-2.5', waiting ? 'bg-gold-soft' : 'bg-tile')}>
                <ModelMark model={c.default_model ?? c.models[0]} provider={c.provider} size={20} />
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-[13px] font-semibold">{c.display_name}</span>
                  <span className="flex flex-wrap items-center gap-x-2 text-[11px] text-muted"><span className="fig">{c.key}</span><span>{c.kind === 'subscription' ? 'اشتراک' : c.kind === 'claude_subscription' ? 'اشتراک Claude' : 'کلید API'}</span></span>
                </span>
                {waiting ? <Button size="sm" variant="text" icon="lock" onClick={() => setWizard(c)}>کلید</Button> : null}
                <Pill tone={st.tone} dot live={c.status === 'verifying'}>{st.fa}</Pill>
              </li>
            );
          })}
        </ul>
      )}
      {wizard ? <ConnectionWizard onClose={() => setWizard(null)} resume={wizard === 'new' ? null : wizard} /> : null}
    </Card>
  );
}

