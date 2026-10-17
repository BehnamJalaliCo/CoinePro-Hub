'use client';

import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { Button } from '@/components/ui/button';
import { Dialog } from '@/components/ui/overlay';
import { Card, Empty, ErrorState, PageHeader, Pill, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ACTION_FA, SessionRow, companyOfWorkspace, isOpen } from '@/components/workshop/parts';
import { GrantSheet, NewSessionSheet } from '@/components/workshop/sheets';
import { ApiError } from '@/lib/api/client';
import { revokeGrant, useGrants, useSessions, useWorkshopMeta, useWorkspaces, type Grant } from '@/lib/api/v13';
import { ACTOR_FA } from '@/lib/labels';
import { until } from '@/lib/format';

function Runtime() {
  const { data } = useWorkshopMeta();
  if (!data || data.runtime) return null;
  return (
    <Card className="flex flex-wrap items-center gap-3 p-4">
      <span className="flex size-9 flex-none items-center justify-center rounded-full bg-gold-soft text-gold-ink"><Icon name="code" size={18} /></span>
      <div className="flex min-w-0 flex-[1_1_16rem] flex-col gap-0.5">
        <span className="text-[14px] font-semibold">جلسه‌های Claude Code تو در اپ Claude هستند</span>
        <span className="text-caption text-sec">همین گفت‌وگوها و نشست سرور، با همان اشتراک. اجرای کارگاه داخل هاب کنار گذاشته شد (تصمیم تو)؛ مجوزها و تاریخچه اینجا میمانند.</span>
      </div>
      {/* The owner's own Claude Code sessions live in claude.ai/code and the Claude app; there is no official API to show them here. */}
      <a href="https://claude.ai/code" target="_blank" rel="noopener noreferrer" className="inline-flex h-10 items-center gap-2 rounded-[10px] bg-gold px-4 text-[13px] font-bold text-on-gold">باز کردن Claude Code<Icon name="share" size={16} /></a>
    </Card>
  );
}

function Grants({ onNew }: { onNew: () => void }) {
  const q = useGrants();
  const { data: workspaces } = useWorkspaces();
  const { data: sessions } = useSessions();
  const qc = useQueryClient();
  const toast = useToast();
  const [revoke, setRevoke] = useState<Grant | null>(null);
  const [busy, setBusy] = useState(false);
  const spent = (ref: string) => (sessions?.items ?? []).filter((s) => s.grant === ref).reduce((n, s) => n + s.usage.usd, 0);
  const doRevoke = async () => {
    if (!revoke) return;
    setBusy(true);
    try {
      await revokeGrant(revoke.ref);
      await qc.invalidateQueries({ queryKey: ['workshop'] });
      toast({ tone: 'ok', text: <>مجوز <span className="fig">{revoke.ref}</span> لغو شد.</> });
      setRevoke(null);
    } catch (e) {
      toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'لغو نشد.' });
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card className="flex flex-col gap-3 p-4">
      <SectionTitle title="مجوزهای تو" note="هر جلسه زیر یک مجوز؛ لغو، جلسه‌هایش را همان لحظه متوقف میکند" action={<Button variant="text" size="sm" icon="add" onClick={onNew}>مجوز تازه</Button>} />
      {q.isLoading ? <Skeleton className="h-24" /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !q.data?.length ? (
        <p className="py-4 text-center text-caption text-muted">مجوز فعالی نیست.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {q.data.map((g) => {
            const ws = workspaces?.find((w) => w.code === g.workspace);
            const used = spent(g.ref);
            return (
              <li key={g.ref} className="flex flex-col gap-2 rounded-[12px] bg-tile px-3 py-3">
                <div className="flex items-center gap-2">
                  <span className="text-sec"><CompanyMark code={companyOfWorkspace(workspaces, g.workspace)} height={14} mono /></span>
                  <span className="min-w-0 flex-1 truncate text-[13px] font-semibold">{ws?.title_fa ?? g.workspace}</span>
                  <span className="fig text-[11px] text-muted">{g.ref}</span>
                </div>
                <div className="flex flex-wrap gap-1">
                  {g.actions.map((a) => <span key={a} className="rounded-full bg-card px-2 py-0.5 text-[11px] text-sec">{ACTION_FA[a] ?? a}</span>)}
                </div>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-sec">
                  <span>{g.driver ? ACTOR_FA(g.driver) : 'خودت'}</span>
                  <span className="fig">${used.toFixed(2)} / ${g.budget_usd}</span>
                  <span className="text-muted">{until(g.expires_at)}</span>
                  <span className="flex-1" />
                  {g.decision_ref ? <span className="fig text-[11px] text-muted">{g.decision_ref}</span> : null}
                  <button type="button" onClick={() => setRevoke(g)} className="text-[12px] font-semibold text-neg hover:underline">لغو</button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <Dialog open={!!revoke} onOpenChange={(v) => !v && setRevoke(null)} title={<>لغو مجوز <span className="fig">{revoke?.ref}</span>؟</>}
        actions={<><Button variant="danger" loading={busy} onClick={doRevoke}>لغو کن</Button><Button variant="ghost" onClick={() => setRevoke(null)}>نه</Button></>}>
        جلسه‌های در جریان زیر این مجوز همین حالا متوقف میشوند. شاخه‌ها و تاریخچه میمانند.
      </Dialog>
    </Card>
  );
}

function Workspaces({ onGrant }: { onGrant: (code: string) => void }) {
  const { data } = useWorkspaces();
  return (
    <Card className="flex flex-col gap-3 p-4">
      <SectionTitle title="ریپوها" note={<>فقط شاخه‌ی <span className="fig">hq/</span> و PR؛ ادغام و انتشار با مُهر تو</>} />
      {!data ? <Skeleton className="h-28" /> : (
        <ul className="flex flex-col">
          {data.map((w) => (
            <li key={w.code} className="flex items-center gap-3 border-b border-div py-2.5 last:border-0">
              <span className="text-sec"><CompanyMark code={w.company} height={14} mono /></span>
              <span className="flex min-w-0 flex-1 flex-col"><span className="truncate text-[13px]">{w.title_fa}</span><span className="fig truncate text-[11px] text-muted">{w.repo}</span></span>
              {w.status === 'paused' ? <Pill tone="warn" dot>متوقف</Pill> : <Button variant="ghost" size="sm" onClick={() => onGrant(w.code)}>مجوز</Button>}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/** The owner's own Claude sessions stay in the owner's Claude account (contract §17.5): linked, never stored. */
function Personal() {
  return (
    <Card className="flex flex-col gap-3 p-4">
      <div className="flex items-center gap-3">
        <span className="flex size-10 items-center justify-center rounded-full bg-gold-soft text-gold-ink"><Icon name="code" size={20} /></span>
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="text-[14px] font-semibold">سشن‌های خودت در Claude Code</span>
          <span className="text-caption text-muted">با حساب Claude خودت</span>
        </div>
      </div>
      <p className="text-[13px] leading-6 text-sec">گفت‌وگوهای شخصی تو با Claude، مثل همانی که این اپ را ساخت، در حساب خودت میمانند. هاب آن‌ها را نگه نمیدارد و نمیخواند؛ با ورود خودت باز میشوند.</p>
      <a href="https://claude.ai/code" target="_blank" rel="noopener noreferrer" className="inline-flex h-10 items-center justify-center gap-2 rounded-[10px] border border-strong px-4 text-[13px] font-semibold text-ink hover:bg-hover">
        <span className="fig">claude.ai/code</span><Icon name="share" size={16} />
      </a>
    </Card>
  );
}

export default function WorkshopPage() {
  const q = useSessions();
  const { data: grants } = useGrants();
  const { data: workspaces } = useWorkspaces();
  const [grantFor, setGrantFor] = useState<string | null | undefined>(undefined);
  const [start, setStart] = useState(false);
  const runtime = useWorkshopMeta().data?.runtime ?? null;
  const items = q.data?.items ?? [];
  const open = items.filter((s) => isOpen(s.state)).sort((a, b) => Number(b.state === 'waiting_approval') - Number(a.state === 'waiting_approval'));
  const past = items.filter((s) => !isOpen(s.state));
  const grantOf = (ref: string) => grants?.find((g) => g.ref === ref);
  return (
    <>
      <PageHeader eyebrow="کارگاه کد" title="Claude Code برای شرکت‌ها" actions={runtime ? <Button variant="primary" icon="add" onClick={() => setStart(true)}>جلسه‌ی تازه</Button> : undefined}>
        <p className="max-w-3xl text-[13px] leading-6 text-sec">{runtime ? 'مدیرها و مشاور کل با مجوز تو روی ریپوی هر شرکت کد میزنند. تو فقط مجوز میدهی، زنده تماشا میکنی و هر لحظه میتوانی متوقف کنی؛ هر push و PR اجازه‌ی تو را میخواهد و هیچ چیزی به production نمیرسد.' : 'جلسه‌های Claude Code در اپ Claude اجرا میشوند. مجوزها و تاریخچه‌ی کارگاه اینجا میمانند.'}</p>
      </PageHeader>
      <Runtime />
      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          <Card className="flex flex-col gap-3 p-4">
            <SectionTitle title="در جریان" note="منتظرِ اجازه‌ها بالاتر" />
            {q.isLoading ? <div className="flex flex-col gap-2">{Array.from({ length: 2 }, (_, i) => <Skeleton key={i} className="h-24 rounded-[14px]" />)}</div>
              : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
              : !open.length ? <Empty icon="code" title="جلسه‌ای در جریان نیست" body="یک جلسه باز کن، یا با فرمان صوتی بگو؛ کار خودش به کارگاه میرسد." />
              : <div className="flex flex-col gap-2">{open.map((s) => <SessionRow key={s.ref} s={s} workspaces={workspaces} grant={grantOf(s.grant)} />)}</div>}
          </Card>
          {past.length ? (
            <Card className="flex flex-col gap-3 p-4">
              <SectionTitle title="گذشته" note="تاریخچه و transcript کامل میماند" />
              <div className="flex flex-col gap-2">{past.map((s) => <SessionRow key={s.ref} s={s} workspaces={workspaces} grant={grantOf(s.grant)} />)}</div>
            </Card>
          ) : null}
        </div>
        <div className="flex min-w-0 flex-col gap-4">
          <Grants onNew={() => setGrantFor(null)} />
          <Workspaces onGrant={(c) => setGrantFor(c)} />
          <Personal />
        </div>
      </div>
      <NewSessionSheet open={start} onOpenChange={setStart} />
      {grantFor !== undefined ? <GrantSheet open onOpenChange={(v) => !v && setGrantFor(undefined)} workspace={grantFor} /> : null}
    </>
  );
}
