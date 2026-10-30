'use client';

// ⟨1.8⟩ «وصل کردن سرور» (§26.1, device-authorisation pairing): on the server, its own Claude installs `hq-runner` and runs `hq-runner
// pair`, which prints a short code; the owner types that code here and approves it with the passkey (`POST /runners/approve {user_code}`,
// 🔏 `server.attach` on `company:<CODE>`). Then the new server, waiting until its runner takes its token and turns `online`. Nothing
// secret is shown: no key, no token, no address to open (Android: Attach.kt).

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { Suspense, useEffect, useState, type ReactNode } from 'react';
import { Icon } from '@/components/icon';
import { Button, Spinner } from '@/components/ui/button';
import { Card, FilterChip, PageHeader } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { CodeBlock, Iso, ServerCard, useServerName } from '@/components/v26/bits';
import { ApiError } from '@/lib/api/client';
import { useCompanies } from '@/lib/api/hooks';
import { approveRunner, isOnline, PairCode, serverError, useLocked, useServers, type HubServer } from '@/lib/api/v26';
import { cx } from '@/lib/format';

/** One numbered step of the three: done ones gold. */
function Step({ n, done, children }: { n: number; done: boolean; children: ReactNode }) {
  return (
    <li className="flex items-start gap-2.5">
      <span className={cx('mt-0.5 flex size-[22px] flex-none items-center justify-center rounded-full text-[11px] font-bold', done ? 'bg-gold text-on-gold' : 'bg-tile text-muted')}>{n}</span>
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">{children}</div>
    </li>
  );
}

/** Text the owner copies to hand on: left to right, monospace, wrapped, one click copies it. */
function CopyBox({ text, prefix }: { text: string; prefix?: string }) {
  const toast = useToast();
  return (
    <div className="flex flex-col items-start gap-1">
      <CodeBlock text={text} prefix={prefix} wrap className="w-full" />
      <Button variant="text" size="sm" icon="deliverable" onClick={() => { void navigator.clipboard?.writeText(text).then(() => toast({ tone: 'ok', text: 'کپی شد.' }), () => toast({ tone: 'error', text: 'کپی نشد.' })); }}>کپی</Button>
    </div>
  );
}

function PairForm({ company0, onDone }: { company0: string | null; onDone: (s: HubServer) => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const { data: all } = useCompanies();
  const companies = (all ?? []).filter((c) => c.kind !== 'holding' && c.status !== 'archived');
  const [company, setCompany] = useState<string | null>(company0);
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const cmd = PairCode.pairCommand(company);
  const ready = !!company && PairCode.valid(code);
  const brief = `طبق COMPANY_SERVER_ACCESS_SETUP.md از ریپوی ستاد، hq-runner را با کاربر کاری همین سرور نصب کن و بعد این را اجرا کن؛ کدی را که نشان میدهد به من بگو:\n\n${cmd}`;

  const approve = async () => {
    if (!company) return;
    setBusy(true);
    try {
      const s = await approveRunner(company, code);
      void qc.invalidateQueries({ queryKey: ['servers'] });
      onDone(s);
    } catch (e) {
      const why = e instanceof ApiError ? PairCode.refusal(e) : null;
      if (why) setError(why); else toast({ tone: 'error', text: serverError(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex max-w-2xl flex-col gap-3">
      <Card className="flex flex-col gap-4 p-5">
        <div className="flex flex-col gap-2">
          <span className="text-[13px] text-sec">کدام شرکت</span>
          <div className="flex flex-wrap gap-2">{companies.map((c) => <FilterChip key={c.code} selected={company === c.code} onClick={() => { setCompany(c.code); setError(null); }}>{c.name_fa ?? c.code}</FilterChip>)}</div>
        </div>
        <ol className="flex flex-col gap-4">
          <Step n={1} done>
            <span className="text-[13px] text-ink"><Iso text="روی سرور: Claude همان سرور hq-runner را طبق COMPANY_SERVER_ACCESS_SETUP.md با کاربر کاری‌اش نصب میکند." /></span>
            <span className="text-[12px] text-muted">این را به Claude همان سرور بده:</span>
            <CopyBox text={brief} />
          </Step>
          <Step n={2} done>
            <span className="text-[13px] text-ink">همان‌جا جفت میکند و یک کد کوتاه نشان میدهد:</span>
            <CodeBlock text={cmd} prefix="$ " wrap />
          </Step>
          <Step n={3} done={ready}>
            <label htmlFor="pair-code" className="text-[13px] text-ink">کد را اینجا بنویس و با گذرکلید تأیید کن.</label>
            <input id="pair-code" dir="ltr" value={code} aria-label="کد جفت‌سازی" aria-invalid={!!error} placeholder="ABCD-1234" autoComplete="off" autoCapitalize="characters" spellCheck={false}
              onChange={(e) => { setCode(PairCode.format(e.target.value)); setError(null); }}
              onKeyDown={(e) => { if (e.key === 'Enter' && ready && !busy) void approve(); }}
              className={cx('fig h-14 w-full rounded-[12px] border bg-tile px-3 text-center text-[22px] font-semibold tracking-[3px] text-ink outline-none placeholder:text-muted focus:border-gold-ink', error ? 'border-neg' : 'border-strong')} />
            {error ? <span role="alert" className="text-[12px] text-neg"><Iso text={error} /></span>
              : code && !PairCode.valid(code) ? <span className="text-[12px] text-muted">هشت حرف و رقم لاتین، مثل <span className="fig">ABCD-1234</span></span>
              : !company && code ? <span className="text-[12px] text-muted">شرکتی را که کد برایش ساخته شده انتخاب کن.</span> : null}
          </Step>
        </ol>
      </Card>
      <Button variant="primary" size="lg" icon="seal" disabled={!ready} loading={busy} onClick={approve}>تأیید با گذرکلید</Button>
      <p className="text-[11px] text-muted"><Iso text="runner خودش با HTTPS به هاب وصل میشود؛ هاب به سرور وارد نمیشود، پورتی باز نمیشود و هیچ رمز یا کلیدی از اینجا رد نمیشود. هر کد ۱۵ دقیقه اعتبار دارد." /></p>
    </div>
  );
}

/** After the approval: the new server as the hub now lists it, and the wait until its runner polls and turns `online`. */
function WaitStep({ o }: { o: HubServer }) {
  const qc = useQueryClient();
  const { data } = useServers();
  const now = data?.find((x) => x.id === o.id) ?? o;
  const online = isOnline(now);
  const name = useServerName(now.company, now.name);
  const locked = useLocked(now.company);
  // The runner takes its token on its next poll (every few seconds); the page asks again until the server is online.
  useEffect(() => {
    if (online) return;
    const t = setInterval(() => void qc.invalidateQueries({ queryKey: ['servers', 'list'] }), 3_000);
    return () => clearInterval(t);
  }, [online, qc]);
  return (
    <div className="flex max-w-2xl flex-col gap-3">
      <Card className="flex items-center gap-2.5 bg-pos-soft p-4">
        <span className="text-pos"><Icon name="seal" size={20} /></span>
        <span className="text-[13px] font-semibold text-ink">کد تأیید شد؛ سرور {name.text} به ستاد پیوست.</span>
      </Card>
      <ServerCard s={now} locked={locked} />
      <Card role="status" className={cx('flex flex-col gap-3 p-4', online && 'bg-pos-soft')}>
        <div className="flex items-center gap-3">
          {online ? <span className="text-pos"><Icon name="seal" size={22} /></span> : <span className="text-gold-ink"><span className="motion-reduce:hidden"><Spinner size={20} /></span><span className="hidden motion-reduce:inline"><Icon name="time" size={20} /></span></span>}
          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            <span className="text-[13px] font-semibold text-ink">{online ? 'آنلاین شد' : <Iso text="منتظرم runner تماس بگیرد…" />}</span>
            <span className="text-[12px] text-sec"><Iso text={online ? 'runner کار میگیرد و اولین نقشه گرفته میشود؛ ایجنت‌ها از همین حالا میتوانند رویش کار کنند.' : 'runner در تماس بعدی‌اش اعتبار خودش را میگیرد و سرور «آنلاین» میشود، معمولاً در چند ثانیه. لازم نیست صفحه باز بماند.'} /></span>
          </div>
        </div>
        {online ? <Link href={`/servers/${now.id}`} className="inline-flex h-10 items-center justify-center gap-2 rounded-[10px] bg-gold px-4 text-[13px] font-bold text-on-gold"><Icon name="server" size={18} />باز کردن سرور</Link> : null}
      </Card>
    </div>
  );
}

function AttachInner() {
  const params = useSearchParams();
  const [out, setOut] = useState<HubServer | null>(null);
  return (
    <>
      <PageHeader eyebrow="سرور یک شرکت، زیر کنترل ستاد" title="وصل کردن سرور" />
      {out ? <WaitStep o={out} /> : <PairForm company0={params.get('company')} onDone={setOut} />}
    </>
  );
}

export default function AttachPage() {
  return <Suspense><AttachInner /></Suspense>;
}
