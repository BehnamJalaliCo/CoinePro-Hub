'use client';

// ⟨1.13⟩ Contract §31.2 «شرکت آماده»: a kit gallery, the company's code and names, a preview of what will be created, the seal behind the
// passkey, and the result with what is still to be connected. Nothing is created before the seal.

import Link from 'next/link';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, Empty, ErrorState, Pill, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { platformFa } from '@/lib/api/v30';
import { previewKit, useCreateFromKit, useKits, type Kit, type KitPreview, type KitResult } from '@/lib/api/v31';
import { cx } from '@/lib/format';
import { FaPara, FaText } from '@/components/v29/text';

export const field = 'w-full rounded-[10px] border border-strong bg-tile px-3 text-[14px] text-ink outline-none focus:border-gold-ink';
export const errText = (e: unknown, fallback: string) => (e instanceof ApiError ? e.messageFa : fallback);
export const notYet = (icon: 'companies' | 'chart' | 'send' | 'globe' | 'task' | 'planner' | 'budget', title: string, body: string) => <Card><Empty icon={icon} title={title} body={body} /></Card>;

export function CompanyKit() {
  const q = useKits();
  const toast = useToast();
  const create = useCreateFromKit();
  const [kit, setKit] = useState<Kit | null>(null);
  const [code, setCode] = useState('');
  const [nameFa, setNameFa] = useState('');
  const [nameEn, setNameEn] = useState('');
  const [prev, setPrev] = useState<KitPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<KitResult | null>(null);
  const valid = /^[A-Z]{2,5}$/.test(code) && nameFa.trim() && nameEn.trim();
  const body = () => ({ kit: kit!.key, code, name_fa: nameFa.trim(), name_en: nameEn.trim() });
  const preview = async () => {
    setBusy(true);
    try { setPrev(await previewKit(body())); } catch (e) { toast({ tone: 'error', text: errText(e, 'پیش‌نمایش نیامد.') }); } finally { setBusy(false); }
  };
  const make = () => create.mutate(body(), { onSuccess: (r) => setDone(r), onError: (e) => toast({ tone: 'error', text: errText(e, 'ساخته نشد؛ دوباره بزن.') }) });

  if (done) {
    return (
      <Card as="section" className="tahrir hq-rise flex flex-col gap-4 p-5" aria-label="شرکت ساخته شد">
        <SectionTitle title={<>شرکت «{done.company.name_fa}» ساخته شد</>} note="تیم، کارگروه‌ها و خط‌های پیش‌نویس آماده‌اند" />
        <div className="flex flex-col gap-2" aria-label="چه چیزی هنوز باید وصل شود">
          <h3 className="text-[13px] font-semibold text-sec">چه چیزی هنوز باید وصل شود</h3>
          {done.todo_fa.length ? <ul className="flex flex-col gap-1.5">{done.todo_fa.map((t) => <li key={t} className="rounded-[10px] bg-warn-soft px-3 py-2 text-[13px] leading-6"><FaText text={t} /></li>)}</ul> : <p className="text-[13px] text-muted">چیزی نمانده.</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <Link href={`/companies/${done.company.code}?tab=connections`} className="inline-flex h-11 items-center rounded-[12px] bg-gold px-5 text-[14px] font-semibold text-on-gold">وصل کردن اتصال‌ها</Link>
          <Link href={`/companies/${done.company.code}?tab=lines`} className="inline-flex h-11 items-center rounded-[12px] border border-strong px-5 text-[14px] font-semibold">خط‌های تولید</Link>
        </div>
      </Card>
    );
  }
  if (q.isLoading) return <div className="grid gap-4 lg:grid-cols-2">{Array.from({ length: 2 }, (_, i) => <Skeleton key={i} className="h-40 rounded-[16px]" />)}</div>;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (q.data === null) return notYet('companies', 'شرکت آماده بعد از به‌روزرسانی ستاد میاید', 'یک الگو را انتخاب میکنی و شرکت با تیم، کارگروه و خط‌هایش ساخته میشود.');
  if (!kit) {
    return (
      <div className="grid items-start gap-4 lg:grid-cols-2" aria-label="الگوهای شرکت">
        {(q.data ?? []).map((k) => (
          <button key={k.key} type="button" onClick={() => setKit(k)} aria-label={`الگوی ${k.title_fa}`} className="hq-tile text-start">
            <Card className="flex h-full flex-col gap-3 p-5 transition-colors hover:bg-tile">
              <span className="text-[16px] font-semibold">{k.title_fa}</span>
              <FaPara text={k.purpose_fa} className="text-[13px] leading-6 text-sec" />
              <div className="flex flex-wrap gap-1.5 text-[12px] text-sec">
                <Pill tone="silver"><span className="fig">{k.lines.length}</span> خط تولید</Pill>
                <Pill tone="silver"><span className="fig">{k.groups.length}</span> کارگروه</Pill>
                <Pill tone="silver"><span className="fig">{k.connections.length}</span> اتصال</Pill>
              </div>
            </Card>
          </button>
        ))}
        {!q.data?.length ? <Card><Empty icon="companies" title="الگویی نیست" /></Card> : null}
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      <Card as="section" className="flex flex-col gap-4 p-5" aria-label="مشخصات شرکت">
        <SectionTitle title={kit.title_fa} note={kit.purpose_fa} action={<Button size="sm" onClick={() => { setKit(null); setPrev(null); }}>الگوی دیگر</Button>} />
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">کد شرکت (حروف بزرگ لاتین)</span>
            <input value={code} onChange={(e) => { setCode(e.target.value.toUpperCase()); setPrev(null); }} dir="ltr" maxLength={5} className={cx(field, 'h-11 text-left')} aria-label="کد شرکت" /></label>
          <label className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">نام فارسی</span>
            <input value={nameFa} onChange={(e) => { setNameFa(e.target.value); setPrev(null); }} className={cx(field, 'h-11')} aria-label="نام فارسی" /></label>
          <label className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">نام انگلیسی</span>
            <input value={nameEn} onChange={(e) => { setNameEn(e.target.value); setPrev(null); }} dir="ltr" className={cx(field, 'h-11 text-left')} aria-label="نام انگلیسی" /></label>
        </div>
        <div><Button icon="search" loading={busy} disabled={!valid} onClick={preview}>پیش‌نمایش</Button></div>
      </Card>
      {prev ? (
        <Card as="section" className="hq-rise flex flex-col gap-4 p-5" aria-label="پیش‌نمایش">
          <SectionTitle title="این‌ها ساخته میشود" note="تا مُهر نزنی چیزی ساخته نمیشود" />
          <div className="grid gap-4 md:grid-cols-2">
            <div className="flex flex-col gap-1.5"><h3 className="text-[13px] font-semibold text-sec">خط‌های تولید (پیش‌نویس)</h3>
              <ul className="flex flex-col gap-1 text-[13px]">{prev.lines.map((l, i) => <li key={i}><FaText text={l.title_fa} /> <span className="text-muted">· {platformFa(l.platform)}</span></li>)}</ul></div>
            <div className="flex flex-col gap-1.5"><h3 className="text-[13px] font-semibold text-sec">کارگروه‌ها، شاخص‌ها و اتصال‌ها</h3>
              <p className="text-[13px] leading-6">{prev.groups.length ? `کارگروه: ${prev.groups.join('، ')}` : ''}<br />{prev.kpis.length ? `شاخص: ${prev.kpis.join('، ')}` : ''}<br />{prev.connections.length ? `اتصال (هنوز وصل نیست): ${prev.connections.join('، ')}` : ''}</p></div>
          </div>
          {prev.todo_fa.length ? <ul className="flex flex-col gap-1.5" aria-label="بعد از ساخت باید وصل شود">{prev.todo_fa.map((t) => <li key={t} className="rounded-[10px] bg-tile px-3 py-2 text-[13px]"><FaText text={t} /></li>)}</ul> : null}
          <div><Button variant="primary" icon="seal" loading={create.isPending} onClick={make}>بساز و مُهر کن</Button></div>
        </Card>
      ) : null}
    </div>
  );
}
