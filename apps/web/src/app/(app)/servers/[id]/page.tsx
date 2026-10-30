'use client';

// ⟨1.8⟩ One company server (contract §26): its runner's state and its map, the jobs on it live, Claude Code sessions on it, the owner's
// terminal, its seals (Android: Server.kt).

import * as Menu from '@radix-ui/react-dropdown-menu';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { use, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { Button } from '@/components/ui/button';
import { Dialog } from '@/components/ui/overlay';
import { Card, Empty, ErrorState, FilterChip, Pill, Segmented, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { SessionRow } from '@/components/workshop/parts';
import { CallLines, Iso, LockedBanner, Notice, OriginPill, RunnerFacts, SealCards, ServerStatePill, TranscriptSheet, useServerName, useServerSeals } from '@/components/v26/bits';
import { MapView } from '@/components/v26/map';
import { ServerTaskSheet } from '@/components/v26/task';
import { useLive } from '@/lib/live';
import { useGrants, useSessions, useWorkspaces } from '@/lib/api/v13';
import {
  detachServer, isOnline, msFig, onServer, refreshMap, serverError, useLocked, useServerActivity, useServerMap, useServers,
  type HubServer, type ServerSession,
} from '@/lib/api/v26';
import { cx } from '@/lib/format';

type Tab = 'map' | 'activity' | 'sessions';

function Fact({ label, value }: { label: string; value: ReactNode }) {
  if (value == null || value === '') return null;
  return <span className="flex items-center gap-1.5"><span className="text-[11px] text-muted">{label}</span><span className="fig text-[12px] text-sec">{value}</span></span>;
}

function ActivityTab({ s, onTranscript }: { s: HubServer; onTranscript: (url: string) => void }) {
  const live = useLive();
  const [mine, setMine] = useState(false);
  const q = useServerActivity(s.id, mine ? 'owner' : null);
  const rows = q.data?.items;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <FilterChip selected={!mine} onClick={() => setMine(false)}>همه</FilterChip>
        <FilterChip selected={mine} onClick={() => setMine(true)}>فقط من</FilterChip>
        <span className="flex-1" />
        <Pill tone={live.state === 'live' ? 'pos' : 'warn'} live={live.state === 'live'}>{live.state === 'live' ? 'زنده' : 'در حال اتصال'}</Pill>
      </div>
      {q.error && !rows ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : !rows ? <Skeleton className="h-64 rounded-[16px]" />
        : !rows.length ? <Empty icon="agent" title="هنوز کاری روی این سرور ثبت نشده" body="هر کار روی سرور — فرمان، خواندن و نوشتن فایل، نقشه و جلسه‌ی Claude — با فرمان ماسک‌شده‌اش و وضعیتش اینجا میاید: در صف، در جریان، منتظر مُهر، تمام، ناموفق یا لغو." />
        : <CallLines rows={rows} onTranscript={onTranscript} />}
      <p className="text-[11px] text-muted">رمزها پیش از ثبت با نام و الگو ماسک میشوند؛ متن کامل هر کار برای تو میماند. کلید توقف شرکت کارهای در صف و در جریان را لغو میکند.</p>
    </div>
  );
}

function SessionsTab({ s, locked, onNew }: { s: HubServer; locked: boolean; onNew: () => void }) {
  const { data: sessions } = useSessions();
  const { data: workspaces } = useWorkspaces();
  const { data: grants } = useGrants();
  const list = (sessions?.items as ServerSession[] | undefined)?.filter((x) => onServer(x) && x.server === s.id);
  const open = (x: ServerSession) => !['done', 'failed', 'stopped'].includes(x.state);
  return (
    <div className="flex flex-col gap-3">
      <Button variant="primary" icon="code" className="self-start" disabled={!isOnline(s) || locked} onClick={onNew}>یک کار روی این سرور بسپار</Button>
      {!list ? <Skeleton className="h-28 rounded-[14px]" />
        : !list.length ? <p className="text-[12px] text-muted">هنوز جلسه‌ای روی این سرور نبوده.</p>
        : <div className="flex flex-col gap-2">{[...list].sort((a, b) => Number(open(b)) - Number(open(a)) || b.updated_at.localeCompare(a.updated_at)).map((x) => <SessionRow key={x.ref} s={x as never} workspaces={workspaces} grant={grants?.find((g) => g.ref === x.grant)} />)}</div>}
      <p className="text-[11px] text-muted"><Iso text="Claude Code خود سرور با login همان سرور کار میکند؛ مصرفش از پاکت شرکت و خزانه‌ی توکن کم میشود." /></p>
    </div>
  );
}

function DetachDialog({ s, open, onOpenChange }: { s: HubServer; open: boolean; onOpenChange: (v: boolean) => void }) {
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();
  const label = useServerName(s.company, s.name).text;
  const [busy, setBusy] = useState(false);
  const go = async () => {
    setBusy(true);
    try {
      await detachServer(s);
      void qc.invalidateQueries({ queryKey: ['servers'] });
      void qc.invalidateQueries({ queryKey: ['network'] });
      toast({ tone: 'ok', text: <>runner سرور {label} باطل شد.</> });
      onOpenChange(false);
      router.push('/servers');
    } catch (e) {
      toast({ tone: 'error', text: serverError(e) });
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={`جدا کردن سرور ${label} از هاب؟`} actions={<>
      <Button variant="danger" icon="close" loading={busy} onClick={go}>با گذرکلید جدا کن</Button>
      <Button variant="ghost" onClick={() => onOpenChange(false)}>نه</Button>
    </>}>
      <Iso text="اعتبار runner همین لحظه باطل میشود و runner در تماس بعدی‌اش میایستد؛ کارهای در صف لغو میشوند و دیگر هیچ ایجنتی کاری روی این سرور نمیکند. خود سرور دست نمیخورد: کاربر کاری، فایل‌ها و سرویس‌ها همان‌طور میمانند. تاریخچه‌ی کارها در Audit میماند." />
    </Dialog>
  );
}

const item = 'flex h-10 cursor-pointer items-center gap-2.5 rounded-[8px] px-2.5 text-[13px] text-ink outline-none data-[highlighted]:bg-hover';

export default function ServerPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();
  const q = useServers();
  const s = q.data?.find((x) => x.id === id);
  const locked = useLocked(s?.company);
  const name = useServerName(s?.company ?? '', s?.name);
  const map = useServerMap(id);
  const seals = useServerSeals().filter((x) => x.serverId === id || (!!s && x.company === s.company && x.serverName === s.name));
  const [tab, setTab] = useState<Tab>('map');
  const [task, setTask] = useState(false);
  const [detach, setDetach] = useState(false);
  const [transcript, setTranscript] = useState<string | null>(null);
  const [mapping, setMapping] = useState(false);

  const remap = async () => {
    if (!s) return;
    setMapping(true);
    try {
      const m = await refreshMap(s.id);
      if (m) qc.setQueryData(['servers', 'map', s.id], m);
      else toast({ tone: 'info', text: 'نقشه‌برداری شروع شد؛ چند لحظه بعد اینجا میاید.' });
      void qc.invalidateQueries({ queryKey: ['servers', 'list'] });
      void qc.invalidateQueries({ queryKey: ['servers', 'activity', s.id] });
    } catch (e) {
      toast({ tone: 'error', text: serverError(e) });
    } finally {
      setMapping(false);
    }
  };

  if (!s) {
    return q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
      : q.data ? <Empty icon="server" title="این سرور دیگر به هاب وصل نیست" action={<Link href="/servers" className="text-[13px] font-semibold text-gold-ink">همه‌ی سرورها</Link>} />
      : <div className="flex flex-col gap-4"><Skeleton className="h-48 rounded-[16px]" /><Skeleton className="h-80 rounded-[16px]" /></div>;
  }
  const on = isOnline(s) && !locked;
  const m = map.data;
  return (
    <>
      <Link href="/servers" className="inline-flex items-center gap-1 self-start text-[13px] text-sec hover:text-ink"><Icon name="back" size={16} mirror />همه‌ی سرورها</Link>
      <Card className="flex flex-col gap-3 p-4 md:p-5">
        <div className="flex items-start gap-3">
          <span className={cx('flex size-12 flex-none items-center justify-center rounded-[14px]', on ? 'bg-gold-soft text-gold-ink' : 'bg-tile text-sec')}><Icon name="server" size={24} /></span>
          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            {/* The owner's rule: the company is the server's name; the server's own name follows only when the company has several. */}
            <h1 className="flex items-center gap-2 text-h2 font-semibold text-ink"><span className="text-sec"><CompanyMark code={s.company} height={16} mono /></span><span className="truncate">{name.companyFa}</span></h1>
            {name.server ? <span className="fig text-[12px] text-sec">{name.server}</span> : null}
          </div>
          <Menu.Root dir="rtl">
            <Menu.Trigger aria-label="کارهای این سرور" className="inline-flex size-10 items-center justify-center rounded-full text-sec hover:bg-hover hover:text-ink"><Icon name="more" size={20} /></Menu.Trigger>
            <Menu.Portal>
              <Menu.Content align="end" sideOffset={6} className="z-50 w-[220px] rounded-[14px] bg-raised p-1.5 shadow-[0_16px_40px_rgba(0,0,0,.4)]">
                {isOnline(s) ? <Menu.Item className={item} onSelect={() => void remap()}><Icon name="refresh" size={18} />نقشه‌ی تازه بگیر</Menu.Item> : null}
                <Menu.Item className={item} onSelect={() => router.push('/server-policy')}><Icon name="seal" size={18} />قوانین سرورها</Menu.Item>
                {s.state !== 'revoked' ? <Menu.Item className={cx(item, 'text-neg')} onSelect={() => setDetach(true)}><Icon name="close" size={18} />جدا کردن از هاب</Menu.Item> : null}
              </Menu.Content>
            </Menu.Portal>
          </Menu.Root>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <ServerStatePill state={s.state} locked={locked} />
          <OriginPill origin={s.origin} />
          <RunnerFacts s={s} />
        </div>
        <div className="flex flex-wrap items-center gap-x-3.5 gap-y-1">
          <Fact label="میزبان" value={s.hostname} />
          <Fact label="کاربر کاری" value={s.user} />
          <Fact label="آدرس خصوصی" value={s.private_ip} />
          {/* §26.1a / §26.6: how the runner reached the hub on its last poll. */}
          {s.via ? <Fact label={s.via === 'public' ? 'به هاب از راه عمومی' : 'به هاب از شبکه‌ی خصوصی'} value={msFig(s.hub_rtt_ms) ?? '—'} /> : null}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" icon="code" disabled={!on} onClick={() => setTask(true)}>یک کار بسپار</Button>
          {on ? <Link href={`/servers/${s.id}/terminal`} className="inline-flex h-10 items-center gap-2 rounded-[10px] border border-strong px-4 text-[13px] font-semibold text-ink hover:bg-hover"><Icon name="command" size={18} />ترمینال</Link>
            : <Button variant="secondary" icon="command" disabled>ترمینال</Button>}
        </div>
      </Card>
      {locked ? <LockedBanner company={s.company} /> : null}
      {s.state === 'pending' ? <Notice icon="time" tone="gold" title="کد تأیید شد؛ منتظر runner"><Iso text="runner در تماس بعدی‌اش اعتبار خودش را میگیرد و سرور «آنلاین» میشود، معمولاً در چند ثانیه. اگر نشد، Claude همان سرور با hq-runner status وضعش را ببیند." /></Notice>
        : s.state === 'offline' ? <Notice icon="offline" tone="warn" title="runner این سرور تماس نمیگیرد"><Iso text="سرور خاموش است، سرویس hq-runner ایستاده یا سرور به اینترنت نمیرسد. تا runner برنگردد، هیچ کاری رویش اجرا نمیشود؛ Claude همان سرور با hq-runner status علتش را میبیند." /></Notice>
        : s.state === 'revoked' ? <Notice icon="close" tone="neutral" title="runner این سرور باطل شده"><Iso text="هاب دیگر هیچ کاری به این سرور نمیدهد. تاریخچه‌ی کارها در Audit میماند. برای وصل دوباره، روی سرور hq-runner pair را از نو اجرا کن و کد تازه را در «وصل کردن سرور» تأیید کن." /></Notice>
        : null}
      {seals.length ? <SealCards cards={seals} compact /> : null}
      <div className="max-w-md"><Segmented<Tab> label="بخش سرور" value={tab} onChange={setTab} options={[{ value: 'map', label: 'نقشه' }, { value: 'activity', label: 'فعالیت' }, { value: 'sessions', label: 'جلسه‌ها' }]} /></div>
      {tab === 'activity' ? <ActivityTab s={s} onTranscript={setTranscript} />
        : tab === 'sessions' ? <SessionsTab s={s} locked={locked} onNew={() => setTask(true)} />
        : m ? <MapView m={m} refreshing={mapping} onRefresh={isOnline(s) ? () => void remap() : undefined} />
        : map.isLoading ? <Skeleton className="h-80 rounded-[16px]" />
        : map.error ? <ErrorState error={map.error} onRetry={() => map.refetch()} />
        : <Empty icon="server" title="هنوز نقشه‌ای گرفته نشده" body={isOnline(s) ? <Iso text="با «نقشه‌ی تازه بگیر» runner سرور را میگردد: سیستم، دیسک، کانتینرها، سرویس‌ها، ریپوها و سایت‌ها." /> : <Iso text="وقتی runner آنلاین شد، اولین نقشه خودکار گرفته میشود." />}
            action={isOnline(s) ? <Button variant="secondary" icon="refresh" loading={mapping} onClick={() => void remap()}>نقشه‌ی تازه بگیر</Button> : undefined} />}
      <ServerTaskSheet open={task} onOpenChange={setTask} servers={[s]} initial={s} />
      <DetachDialog s={s} open={detach} onOpenChange={setDetach} />
      <TranscriptSheet url={transcript} onClose={() => setTranscript(null)} />
    </>
  );
}
