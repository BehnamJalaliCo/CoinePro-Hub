'use client';

// ⟨1.8⟩ «یک کار روی این سرور بسپار» (§26.2 `server.claude`, §26.5): Claude Code on the server itself, in a repository there, driven by an
// agent of the company or by the owner (Android: Task.kt).

import { useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { useRef, useState } from 'react';
import { Icon } from '@/components/icon';
import { AttachmentTray, PICKER_ACCEPT, useAttachments } from '@/components/media/attachments';
import { Button } from '@/components/ui/button';
import { Sheet } from '@/components/ui/overlay';
import { FilterChip, Pill } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { SpokenField } from '@/components/workshop/sheets';
import { useEmployees } from '@/lib/api/hooks';
import { defaultRepo, serverError, startServerSession, useServerMap, type HubServer } from '@/lib/api/v26';
import { cx } from '@/lib/format';
import { ServerTitle, useServerName } from './bits';

/** The roles that may drive Claude Code on a company's server by default (§26.2: the CEO, CTO / Lead Developer, DevOps and SRE). */
const canDrive = (kind: string, company: string, employeeCompany: string) => employeeCompany === company && (kind === 'ceo' || kind === 'manager');

function ServerChoice({ s, on, onPick }: { s: HubServer; on: boolean; onPick: () => void }) {
  const name = useServerName(s.company, s.name);
  return (
    <button type="button" role="radio" aria-checked={on} onClick={onPick} className={cx('flex items-center gap-3 rounded-[12px] px-3 py-2.5 text-start text-[13px] transition-colors', on ? 'bg-gold-soft ring-1 ring-[var(--hq-gold-ink)]' : 'bg-tile hover:bg-hover')}>
      <ServerTitle name={name} className="flex-1" />
    </button>
  );
}

export function ServerTaskSheet({ open, onOpenChange, servers, initial }: { open: boolean; onOpenChange: (v: boolean) => void; servers: HubServer[]; initial: HubServer | null }) {
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();
  const { data: emps } = useEmployees({});
  const [chosen, setChosen] = useState<string | null>(initial?.id ?? null);
  const [driver, setDriver] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [brief, setBrief] = useState('');
  const [picked, setPicked] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const files = useAttachments(10);
  const pick = useRef<HTMLInputElement>(null);
  const server = servers.find((s) => s.id === chosen) ?? (servers.length === 1 ? servers[0]! : null) ?? initial;
  // §26.5: the repository folder the session runs in, from the server's own map; the only one is taken unless the owner says otherwise.
  const repos = useServerMap(server?.id ?? null).data?.repos ?? [];
  const cwd = defaultRepo(repos.map((r) => r.path), picked);
  const drivers = (emps?.items ?? []).filter((e) => e.status === 'active' && !!server && canDrive(e.kind, server.company, e.company));
  const ok = !!server && title.trim().length >= 3 && brief.trim().length >= 3 && !files.uploading;
  const driverName = drivers.find((e) => e.code === driver);

  const submit = async () => {
    if (!server) return;
    setBusy(true);
    try {
      const s = await startServerSession(server, { driver, title: title.trim(), brief: brief.trim(), attachments: files.ids, cwd });
      void qc.invalidateQueries({ queryKey: ['workshop'] });
      void qc.invalidateQueries({ queryKey: ['servers'] });
      onOpenChange(false);
      setTitle(''); setBrief(''); files.clear();
      router.push(`/workshop/${s.ref}`);
    } catch (e) {
      toast({ tone: 'error', text: serverError(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange} title="یک کار روی این سرور بسپار" description="Claude Code خود سرور، در ریپوی همان‌جا؛ زنده تماشا کن، راهنمایی کن یا متوقفش کن." width={560}
      footer={<Button variant="primary" size="lg" icon="code" className="w-full" disabled={!ok} loading={busy} onClick={submit}>شروع کن</Button>}>
      <div className="flex flex-col gap-5">
        {!initial && servers.length > 1 ? (
          <div role="radiogroup" aria-label="کدام سرور" className="flex flex-col gap-1.5">
            <span className="pb-1 text-[13px] text-sec">کدام سرور</span>
            {servers.map((s) => <ServerChoice key={s.id} s={s} on={server?.id === s.id} onPick={() => { setChosen(s.id); setDriver(null); setPicked(null); }} />)}
          </div>
        ) : server ? <ServerChoice s={server} on={false} onPick={() => {}} /> : null}
        {server ? (
          <div className="flex flex-col gap-2">
            <span className="text-[13px] text-sec">چه کسی کار را ببرد</span>
            <div className="flex flex-wrap gap-2">
              <FilterChip selected={driver == null} onClick={() => setDriver(null)}>خودم</FilterChip>
              {drivers.map((e) => <FilterChip key={e.code} selected={driver === e.code} onClick={() => setDriver(e.code)}>{e.display_name ?? e.title_fa}</FilterChip>)}
            </div>
            <span className="text-[11px] text-muted">{driver == null ? 'Claude را خودت راهنمایی میکنی؛ پیام‌هایت با همان نشست به Claude سرور میرسد.' : `${driverName?.display_name ?? driverName?.title_fa ?? ''} کار را میبرد و از پاکت همین شرکت خرج میکند؛ تو زنده میبینی و هر لحظه میتوانی بایستانی.`}</span>
          </div>
        ) : null}
        {server && repos.length ? (
          <div role="radiogroup" aria-label="در کدام ریپو" className="flex flex-col gap-1.5">
            <span className="pb-1 text-[13px] text-sec">در کدام ریپو</span>
            {repos.map((r) => {
              const on = cwd === r.path;
              return (
                <button key={r.path} type="button" role="radio" aria-checked={on} aria-label={r.path} onClick={() => setPicked(r.path)}
                  className={cx('flex items-center gap-2.5 rounded-[12px] px-3 py-2 text-start transition-colors', on ? 'bg-gold-soft ring-1 ring-[var(--hq-gold-ink)]' : 'bg-tile hover:bg-hover')}>
                  <span className={on ? 'text-gold-ink' : 'text-sec'}><Icon name="code" size={16} /></span>
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="fig truncate text-[12px] font-semibold text-ink">{r.path}</span>
                    {r.branch ? <span className="fig text-[11px] text-muted">{r.branch}</span> : null}
                  </span>
                  {r.dirty ? <Pill tone="warn">تغییر ثبت‌نشده</Pill> : null}
                </button>
              );
            })}
            <span className="text-[11px] text-muted">Claude در همین پوشه و زیر <span className="fig">CLAUDE.md</span> همان ریپو کار میکند.</span>
          </div>
        ) : null}
        <label className="flex flex-col gap-1.5"><span className="text-[13px] text-sec">عنوان</span>
          <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} placeholder="عنوان؛ مثلاً: انتشار نسخه‌ی تازه‌ی API" className="h-12 w-full rounded-[10px] border border-strong bg-tile px-3 text-[15px] text-ink outline-none focus:border-gold-ink" />
        </label>
        <SpokenField label="چه باید بشود و کی تمام است" value={brief} onChange={setBrief} rows={5} placeholder="هدف، محدودیت‌ها، معیار تمام شدن؛ مثلاً «تست‌ها سبز، deploy، سلامت سایت را بسنج»" />
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <span className="flex-1 text-[13px] text-sec">عکس، فیلم یا PDF (اختیاری)</span>
            <input ref={pick} type="file" multiple accept={PICKER_ACCEPT} hidden onChange={(e) => { if (e.target.files) void files.add(e.target.files); e.target.value = ''; }} />
            <Button variant="text" size="sm" icon="attach" onClick={() => pick.current?.click()}>پیوست</Button>
          </div>
          <AttachmentTray items={files.items} onRemove={files.remove} onRetry={files.retry} />
        </div>
        <p className="text-[11px] text-muted">کد، commit، push، deploy و ریستارت آزاد است؛ اگر به یکی از شش کار ویرانگر برسد، همان‌جا میایستد و کارتش به کارتابل تو میاید.</p>
      </div>
    </Sheet>
  );
}
