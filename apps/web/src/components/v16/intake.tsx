'use client';

import { useState } from 'react';
import { CompanyMark } from '@/components/brand/marks';
import { Button } from '@/components/ui/button';
import { Sheet } from '@/components/ui/overlay';
import { Card, ErrorState, FilterChip, Pill, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { PRODUCT_EVENTS, faError, useIntakeAction, useIntakeSources, type IntakeKind } from '@/lib/api/v16';
import { ago, cx } from '@/lib/format';
import { CompanyChips, INTAKE_KIND, TerminalCommand } from './bits';

const KINDS: IntakeKind[] = ['telegram', 'chatwoot', 'product'];
const IP = /^(?:\d{1,3}(?:\.\d{1,3}){3}|[0-9a-f:]+:[0-9a-f:]*)(?:\/\d{1,3})?$/i;

function RegisterSheet({ onClose }: { onClose: () => void }) {
  const act = useIntakeAction();
  const toast = useToast();
  const [company, setCompany] = useState<string | null>(null);
  const [kind, setKind] = useState<IntakeKind>('product');
  const [ips, setIps] = useState('');
  const [events, setEvents] = useState<string[]>([...PRODUCT_EVENTS]);
  const list = ips.split(/[\s,]+/).map((x) => x.trim()).filter(Boolean);
  // Telegram is accepted only from its own published ranges; the others need their sources' addresses.
  const valid = !!company && list.every((x) => IP.test(x)) && (kind === 'telegram' || list.length > 0) && (kind !== 'product' || events.length > 0);
  const save = () => act.mutateAsync({ company: company!, kind, allowed_ips: list, kinds: kind === 'product' ? events : [] })
    .then(() => { toast({ tone: 'ok', text: 'منبع ثبت شد؛ رمزش را در ترمینال خودت بگذار.' }); onClose(); })
    .catch((e) => toast({ tone: 'error', text: faError(e) }));
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title="ثبت منبع ورودی" description="ثبت با passkey و روی همین متن؛ رمز منبع هرگز از API نمیگذرد." width={520}
      footer={<Button variant="primary" icon="seal" className="w-full" disabled={!valid} loading={act.isPending} onClick={save}>ثبت با passkey</Button>}>
      <div className="flex flex-col gap-4 text-[13px]">
        <div className="flex flex-col gap-1.5"><span className="font-semibold text-sec">شرکت</span><CompanyChips value={company} onChange={setCompany} all={false} /></div>
        <div className="flex flex-col gap-1.5"><span className="font-semibold text-sec">نوع</span><div className="flex flex-wrap gap-2">{KINDS.map((k) => <FilterChip key={k} selected={kind === k} onClick={() => setKind(k)}>{INTAKE_KIND[k]}</FilterChip>)}</div></div>
        <label className="flex flex-col gap-1.5 font-semibold text-sec">IPهای مجاز (هر خط یکی، CIDR هم میشود)
          <textarea value={ips} onChange={(e) => setIps(e.target.value)} rows={3} dir="ltr" placeholder={kind === 'telegram' ? 'Telegram: published ranges only' : '203.0.113.10'} className="fig rounded-[10px] border border-strong bg-card px-3 py-2 text-left text-[13px] text-ink outline-none focus:border-gold-ink" />
          {kind === 'telegram' ? <span className="text-[11px] font-normal text-muted">تلگرام فقط از بازه‌های IP منتشرشده‌ی خودش پذیرفته میشود؛ خالی بگذار مگر محدودتر بخواهی.</span> : null}
        </label>
        {kind === 'product' ? (
          <div className="flex flex-col gap-1.5"><span className="font-semibold text-sec">رویدادهای پذیرفته</span>
            <div className="flex flex-wrap gap-2">{PRODUCT_EVENTS.map((e) => <FilterChip key={e} selected={events.includes(e)} onClick={() => setEvents((xs) => (xs.includes(e) ? xs.filter((x) => x !== e) : [...xs, e]))}><span className="fig">{e}</span></FilterChip>)}</div>
          </div>
        ) : null}
        <div className="flex flex-col gap-2 rounded-[12px] bg-tile p-3 leading-6 text-sec">
          <span>بعد از ثبت، در ترمینال خودت روی سرور:</span>
          <TerminalCommand text={`make intake-secret COMPANY=${company ?? '…'} SOURCE=${kind}`} />
          <span className="text-[11px] text-muted">امضای بد یا timestamp کهنه بی‌هیچ جزئیاتی ۴۰۱ میگیرد و هیچ ردیفی نمیسازد.</span>
        </div>
      </div>
    </Sheet>
  );
}

/** ورودی‌ها از بیرون (contract §19.8): the only new public routes — Telegram webhooks, Chatwoot and product events — each signed. */
export function IntakeCard() {
  const q = useIntakeSources();
  const [neu, setNew] = useState(false);
  return (
    <Card className="flex flex-col gap-3 p-4">
      <SectionTitle title="ورودی‌ها از بیرون" note="تلگرام، Chatwoot و رویداد محصول؛ هر کدام با امضا، رمزش فقط در ترمینال تو" action={<Button variant="text" size="sm" icon="add" onClick={() => setNew(true)}>ثبت منبع</Button>} />
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !q.data ? <Skeleton className="h-32" /> : q.data.map((s) => (
        <div key={`${s.company}-${s.kind}`} className="flex flex-col gap-1.5 border-b border-div pb-2.5 last:border-0 last:pb-0">
          <div className="flex items-center gap-2 text-[13px]">
            <CompanyMark code={s.company} height={12} mono />
            <span className="min-w-0 flex-1">{INTAKE_KIND[s.kind] ?? s.kind}</span>
            <Pill tone={s.configured ? 'pos' : 'neutral'} dot>{s.configured ? 'پیکربندی‌شده' : 'بی‌رمز'}</Pill>
          </div>
          <div className="flex flex-wrap gap-x-3 text-[11px] text-muted">
            <span>{s.last_event_at ? <>آخرین رویداد {ago(s.last_event_at)}</> : 'هنوز رویدادی نرسیده'}</span>
            <span>۲۴ ساعت: <span className="fig text-sec">{s.events_24h}</span> رویداد</span>
            <span className={cx(s.rejected_24h ? 'text-neg' : undefined)}>رد: <span className="fig">{s.rejected_24h}</span></span>
          </div>
          {!s.configured ? <TerminalCommand text={`make intake-secret COMPANY=${s.company} SOURCE=${s.kind}`} /> : null}
        </div>
      ))}
      {neu ? <RegisterSheet onClose={() => setNew(false)} /> : null}
    </Card>
  );
}
