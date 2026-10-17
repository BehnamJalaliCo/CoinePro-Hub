'use client';

import { useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { useMemo, useRef, useState } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { AttachmentTray, PICKER_ACCEPT, useAttachments } from '@/components/media/attachments';
import { Waveform, useVoiceInput } from '@/components/media/composer';
import { Button, IconButton, Spinner } from '@/components/ui/button';
import { Sheet } from '@/components/ui/overlay';
import { FilterChip, Segmented } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { useEmployees } from '@/lib/api/hooks';
import { createGrant, createSession, useGrants, useWorkspaces, type Grant } from '@/lib/api/v13';
import { bodyTarget, stepUp } from '@/lib/auth';
import { clock } from '@/lib/recorder';
import { cx, until } from '@/lib/format';
import { ACTION_FA, companyOfWorkspace } from './parts';

const field = 'w-full rounded-[10px] border border-strong bg-tile px-3 text-[15px] text-ink outline-none focus:border-gold-ink';

/** A text field the owner can also speak into: the exact text is appended for them to read and fix. */
function SpokenField({ value, onChange, rows, placeholder, label }: { value: string; onChange: (v: string) => void; rows: number; placeholder?: string; label: string }) {
  const v = useVoiceInput({ purpose: 'note', onText: (r) => onChange(value.trim() ? `${value.trimEnd()} ${r.text}` : r.text) });
  const recording = v.state === 'recording' || v.state === 'asking';
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        <span className="flex-1 text-[13px] text-sec">{label}</span>
        {recording ? (
          <span className="flex items-center gap-2">
            <Waveform levels={v.levels.slice(-18)} className="h-5 w-20" />
            <span className="fig text-[12px] text-sec">{clock(v.elapsed)}</span>
            <IconButton icon="close" label="لغو ضبط" size={32} onClick={v.cancel} />
            <button type="button" onClick={v.finish} className="flex h-8 items-center gap-1.5 rounded-full bg-gold px-3 text-[12px] font-semibold text-on-gold"><Icon name="stop" size={14} />تمام</button>
          </span>
        ) : v.transcribing ? (
          <span className="flex items-center gap-1.5 text-[12px] text-sec"><Spinner size={14} />در حال نوشتن…</span>
        ) : (
          <button type="button" onClick={() => void v.start()} className="flex h-8 items-center gap-1.5 rounded-full px-2.5 text-[12px] font-semibold text-gold-ink hover:bg-gold-soft"><Icon name="mic" size={16} />بگو</button>
        )}
      </div>
      <textarea value={value} onChange={(e) => onChange(e.target.value)} rows={rows} maxLength={10000} placeholder={placeholder} aria-label={label} className={cx(field, 'py-3 leading-7')} />
    </div>
  );
}

/** The owner's grant (contract §17.3): which repository, which actions, who drives, how much, until when. 🔏 */
export function GrantSheet({ open, onOpenChange, workspace: initial }: { open: boolean; onOpenChange: (v: boolean) => void; workspace?: string | null }) {
  const qc = useQueryClient();
  const toast = useToast();
  const { data: workspaces } = useWorkspaces();
  const { data: employees } = useEmployees({});
  const [ws, setWs] = useState<string | null>(initial ?? null);
  const [actions, setActions] = useState<string[]>(['read', 'edit', 'run', 'push_branch', 'open_pr']);
  const [driver, setDriver] = useState<string | null>(null);
  const [budget, setBudget] = useState('10');
  const [days, setDays] = useState('3');
  const [busy, setBusy] = useState(false);
  const company = ws ? companyOfWorkspace(workspaces, ws) : null;
  // Managers and the chief advisor drive sessions (owner, 2026-10-17); the owner only grants.
  const drivers = useMemo(() => (employees?.items ?? []).filter((e) => e.status === 'active' && ((e.company === company && (e.kind === 'manager' || e.kind === 'ceo')) || e.kind === 'advisor')), [employees, company]);
  const toggle = (a: string) => setActions((xs) => (xs.includes(a) ? xs.filter((x) => x !== a) : [...xs, a]));

  const submit = async () => {
    if (!ws) return;
    setBusy(true);
    try {
      const body = { workspace: ws, actions, driver, budget_usd: Number(budget), expires_at: new Date(Date.now() + Number(days) * 86_400_000).toISOString() };
      const token = await stepUp('workshop.grant', await bodyTarget(JSON.stringify(body)));
      const g = await createGrant(body, token);
      await qc.invalidateQueries({ queryKey: ['workshop'] });
      toast({ tone: 'ok', text: <>مجوز <span className="fig">{g.ref}</span> صادر شد.</> });
      onOpenChange(false);
    } catch (e) {
      toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : e instanceof Error ? e.message : 'صادر نشد.' });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange} title="مجوز تازه برای کارگاه" description="تو فقط اجازه میدهی؛ مدیرها و مشاور کل کار را میبرند. ادغام و انتشار همیشه با مُهر خودت." width={560}
      footer={<Button variant="primary" icon="seal" className="w-full" disabled={!ws || !actions.includes('read')} loading={busy} onClick={submit}>با گذرکلید مجوز بده</Button>}>
      <div className="flex flex-col gap-5">
        <fieldset className="flex flex-col gap-2">
          <legend className="pb-2 text-[13px] text-sec">کدام ریپو</legend>
          <div className="flex flex-col gap-1.5">
            {(workspaces ?? []).filter((w) => w.status === 'active').map((w) => (
              <button key={w.code} type="button" aria-pressed={ws === w.code} onClick={() => { setWs(w.code); setDriver(null); }}
                className={cx('flex items-center gap-3 rounded-[12px] px-3 py-2.5 text-start transition-colors', ws === w.code ? 'bg-gold-soft ring-1 ring-[var(--hq-gold-ink)]' : 'bg-tile hover:bg-hover')}>
                <span className="text-sec"><CompanyMark code={w.company} height={16} mono /></span>
                <span className="flex min-w-0 flex-1 flex-col"><span className="text-[14px] text-ink">{w.title_fa}</span><span className="fig truncate text-[11px] text-muted">{w.repo}</span></span>
              </button>
            ))}
          </div>
        </fieldset>
        <fieldset className="flex flex-col gap-2">
          <legend className="pb-2 text-[13px] text-sec">چه کارهایی</legend>
          <div className="flex flex-wrap gap-2">
            {Object.entries(ACTION_FA).map(([a, fa]) => <FilterChip key={a} selected={actions.includes(a)} onClick={() => a !== 'read' && toggle(a)}>{fa}</FilterChip>)}
          </div>
          <p className="text-[12px] text-muted">push فقط به شاخه‌های <span className="fig">hq/</span>؛ هر push و PR باز هم اجازه‌ی جدای تو را میخواهد.</p>
        </fieldset>
        {ws ? (
          <fieldset className="flex flex-col gap-2">
            <legend className="pb-2 text-[13px] text-sec">چه کسی کار را ببرد</legend>
            <div className="flex flex-wrap gap-2">
              <FilterChip selected={!driver} onClick={() => setDriver(null)}>خودم، از همین‌جا</FilterChip>
              {drivers.map((e) => <FilterChip key={e.code} selected={driver === e.code} onClick={() => setDriver(e.code)}>{e.title_fa}{e.company !== company ? ` (${e.company})` : ''}</FilterChip>)}
            </div>
          </fieldset>
        ) : null}
        <div className="flex flex-wrap gap-5">
          <div className="flex flex-col gap-2">
            <span className="text-[13px] text-sec">سقف هزینه</span>
            <Segmented label="سقف هزینه" value={budget} onChange={setBudget} options={['5', '10', '25', '50'].map((v) => ({ value: v, label: <span className="fig">${v}</span> }))} />
          </div>
          <div className="flex flex-col gap-2">
            <span className="text-[13px] text-sec">تا کی</span>
            <Segmented label="مدت مجوز" value={days} onChange={setDays} options={[{ value: '1', label: '۱ روز' }, { value: '3', label: '۳ روز' }, { value: '7', label: '۱ هفته' }, { value: '30', label: '۱ ماه' }]} />
          </div>
        </div>
      </div>
    </Sheet>
  );
}

/** Open a session under an active grant. The brief can be spoken; photos and films help explain it. */
export function NewSessionSheet({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();
  const { data: grants } = useGrants();
  const { data: workspaces } = useWorkspaces();
  const [grant, setGrant] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [brief, setBrief] = useState('');
  const [busy, setBusy] = useState(false);
  const files = useAttachments(10);
  const pick = useRef<HTMLInputElement>(null);
  const active = (grants ?? []).filter((g) => !g.revoked_at);
  const chosen = active.find((g) => g.ref === grant) ?? (active.length === 1 ? active[0] : undefined);
  const ok = !!chosen && title.trim().length >= 3 && brief.trim().length >= 3 && !files.uploading;

  const submit = async () => {
    if (!chosen) return;
    setBusy(true);
    try {
      const s = await createSession({ grant: chosen.ref, title: title.trim(), brief: brief.trim(), attachments: files.ids });
      await qc.invalidateQueries({ queryKey: ['workshop'] });
      onOpenChange(false);
      setTitle(''); setBrief(''); files.clear();
      router.push(`/workshop/${s.ref}`);
    } catch (e) {
      toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'جلسه باز نشد.' });
    } finally {
      setBusy(false);
    }
  };

  const label = (g: Grant) => workspaces?.find((w) => w.code === g.workspace)?.title_fa ?? g.workspace;
  return (
    <Sheet open={open} onOpenChange={onOpenChange} title="جلسه‌ی تازه در کارگاه" description="زیر یکی از مجوزهای فعال؛ راننده‌ی همان مجوز کار را میبرد." width={560}
      footer={<Button variant="primary" icon="code" className="w-full" disabled={!ok} loading={busy} onClick={submit}>شروع کن</Button>}>
      <div className="flex flex-col gap-5">
        <fieldset className="flex flex-col gap-2">
          <legend className="pb-2 text-[13px] text-sec">زیر کدام مجوز</legend>
          {!active.length ? <p className="rounded-[12px] bg-tile px-3 py-3 text-[13px] text-muted">مجوز فعالی نیست؛ اول از «مجوز تازه» یکی بده.</p> : (
            <div className="flex flex-col gap-1.5">
              {active.map((g) => (
                <button key={g.ref} type="button" aria-pressed={chosen?.ref === g.ref} onClick={() => setGrant(g.ref)}
                  className={cx('flex items-center gap-3 rounded-[12px] px-3 py-2.5 text-start transition-colors', chosen?.ref === g.ref ? 'bg-gold-soft ring-1 ring-[var(--hq-gold-ink)]' : 'bg-tile hover:bg-hover')}>
                  <span className="text-sec"><CompanyMark code={companyOfWorkspace(workspaces, g.workspace)} height={16} mono /></span>
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="text-[14px] text-ink">{label(g)}</span>
                    <span className="text-[11px] text-muted">{g.driver?.display_fa ?? 'خودت'} · <span className="fig">${g.budget_usd}</span> · {until(g.expires_at)}</span>
                  </span>
                  <span className="fig text-[11px] text-muted">{g.ref}</span>
                </button>
              ))}
            </div>
          )}
        </fieldset>
        <label className="flex flex-col gap-1.5"><span className="text-[13px] text-sec">عنوان</span><input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} className={cx(field, 'h-12')} placeholder="مثلاً: کندی صفحه‌ی ثبت‌نام" /></label>
        <SpokenField label="چه باید بشود و کی تمام است" value={brief} onChange={setBrief} rows={5} placeholder="هدف، محدودیت‌ها و معیار تمام شدن" />
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <span className="flex-1 text-[13px] text-sec">عکس، فیلم یا PDF برای روشن‌تر شدن (اختیاری)</span>
            <input ref={pick} type="file" multiple accept={PICKER_ACCEPT} hidden onChange={(e) => { if (e.target.files) void files.add(e.target.files); e.target.value = ''; }} />
            <Button variant="text" size="sm" icon="attach" onClick={() => pick.current?.click()}>پیوست</Button>
          </div>
          <AttachmentTray items={files.items} onRemove={files.remove} onRetry={files.retry} />
        </div>
      </div>
    </Sheet>
  );
}
