'use client';

// ⟨1.8⟩ Contract §26: the companies' servers under the holding's control, each through its own `hq-runner`. The pieces every server page
// shares, as the Android app draws them (ui/servers/Bits.kt).

import Link from 'next/link';
import { useQueryClient } from '@tanstack/react-query';
import { Fragment, useState, type ComponentProps, type ReactNode } from 'react';
import { Icon } from '@/components/icon';
import { Avatar } from '@/components/brand/avatar';
import { CompanyMark } from '@/components/brand/marks';
import { Button } from '@/components/ui/button';
import { MdInline } from '@/components/ui/md';
import { Dialog, Sheet } from '@/components/ui/overlay';
import { Bar, Card, ErrorState, Pill, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import type { IconName } from '@/generated/icons';
import { useCompanies, useDecide, useDecisions } from '@/lib/api/hooks';
import {
  callRow, isOnline, mapEmpty, runningContainers, sealCardOf, serverError, serverNameOf, size, useLocked, useServerMap, useServers, useTranscript,
  SERVER_DESTRUCTIVE, type CallOutcome, type DiskUsage, type HubServer, type SealCard, type ServerCall, type ServerCallRow, type ServerName,
} from '@/lib/api/v26';
import { stepUp } from '@/lib/auth';
import { companyOf } from '@/lib/company';
import { ACTOR_FA } from '@/lib/labels';
import { ago, cx, jTime } from '@/lib/format';

type Tone = NonNullable<ComponentProps<typeof Pill>['tone']>;

/** §26.4's runner states. */
export const SERVER_STATE: Record<string, { fa: string; tone: Tone; icon?: IconName; live?: boolean }> = {
  pending: { fa: 'منتظر runner', tone: 'gold', icon: 'time' },
  online: { fa: 'آنلاین', tone: 'pos', live: true },
  offline: { fa: 'آفلاین', tone: 'neg', icon: 'offline' },
  revoked: { fa: 'باطل‌شده', tone: 'neutral', icon: 'close' },
};

// ------------------------------------------------------------------ text --
const LATIN_RUN = /[A-Za-z0-9](?:[A-Za-z0-9.:/_\-–]*[A-Za-z0-9])?(?: [A-Za-z0-9](?:[A-Za-z0-9.:/_\-–]*[A-Za-z0-9])?)*/g;

/** A Persian sentence with commands and file names in it ("hq-runner status", "SETUP.md"): each Latin run set Latin and isolated left to
 *  right, so the bidi algorithm never reorders it. */
export function Iso({ text }: { text: string }) {
  const out: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(LATIN_RUN)) {
    out.push(text.slice(last, m.index));
    out.push(<span key={m.index} className="fig">{m[0]}</span>);
    last = m.index! + m[0].length;
  }
  out.push(text.slice(last));
  return <>{out.map((x, i) => <Fragment key={i}>{x}</Fragment>)}</>;
}

/** A line of a server's own text — a command, a path, a key — left to right in monospace; it scrolls sideways unless [wrap]. */
export function CodeBlock({ text, prefix, wrap, tone, className }: { text: string; prefix?: string | null; wrap?: boolean; tone?: 'neg'; className?: string }) {
  return (
    <code dir="ltr" className={cx('block rounded-[10px] px-3 py-2 text-left font-mono text-[12.5px] leading-[18px] text-ink', tone === 'neg' ? 'bg-neg-soft' : 'bg-page', wrap ? 'whitespace-pre-wrap break-all' : 'overflow-x-auto whitespace-pre', className)}>
      {prefix ? <span className="text-muted">{prefix}</span> : null}{text}
    </code>
  );
}

export function Notice({ icon, tone, title, children }: { icon: IconName; tone: 'gold' | 'warn' | 'neutral' | 'neg'; title: ReactNode; children?: ReactNode }) {
  const bg = { gold: 'bg-gold-soft', warn: 'bg-warn-soft', neutral: 'bg-tile', neg: 'bg-neg-soft' }[tone];
  const fg = { gold: 'text-gold-ink', warn: 'text-warn', neutral: 'text-sec', neg: 'text-neg' }[tone];
  return (
    <div className={cx('flex items-start gap-3 rounded-[14px] p-3.5', bg)}>
      <span className={cx('mt-0.5', fg)}><Icon name={icon} size={20} /></span>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="text-[13px] font-semibold text-ink">{title}</span>
        {children ? <span className="text-[12px] leading-6 text-sec">{children}</span> : null}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ names --
/** The name of [company]'s server [server], from the companies and the servers the panel already reads (the owner's rule). */
export function useServerName(company: string, server: string | null | undefined): ServerName {
  const { data: companies } = useCompanies();
  const { data: list } = useServers();
  return serverNameOf(company, companyOf(companies, company).nameFa, server, list?.filter((s) => s.company === company).length ?? 1);
}

/** A server's name as a title: its company's mark and name, the server's own name after it, small, when the company has several. */
export function ServerTitle({ name, className, mark = true, markHeight = 14, big }: { name: ServerName; className?: string; mark?: boolean; markHeight?: number; big?: boolean }) {
  return (
    <span className={cx('flex min-w-0 items-center gap-1.5', className)}>
      {mark ? <span className="text-sec"><CompanyMark code={name.company} height={markHeight} mono /></span> : null}
      <span className={cx('truncate text-ink', big ? 'text-h2 font-semibold' : 'font-semibold')}>{name.companyFa}</span>
      {name.server ? <><span className="text-muted">·</span><span className="fig text-[12px] text-muted">{name.server}</span></> : null}
    </span>
  );
}

export function ServerStatePill({ state, locked }: { state: string; locked?: boolean }) {
  if (locked) return <Pill tone="warn" icon="lock">قفل؛ شرکت متوقف است</Pill>;
  const s = SERVER_STATE[state] ?? { fa: state, tone: 'neutral' as Tone };
  return <Pill tone={s.tone} icon={s.icon} live={s.live} dot={!s.icon && !s.live}>{s.fa}</Pill>;
}

export const OriginPill = ({ origin }: { origin: string }) => <Pill tone="silver">{origin === 'provisioned' ? 'ساخته‌ی هاب' : 'وصل‌شده'}</Pill>;

/** The runner's version and its last poll ("آخرین تماس ۲ دقیقه پیش"). */
export function RunnerFacts({ s }: { s: HubServer }) {
  return (
    <>
      {s.runner_version ? <span className="fig text-[12px] text-sec">runner {s.runner_version}</span> : null}
      <span className="text-[11px] text-muted">{s.last_seen_at ? `آخرین تماس ${ago(s.last_seen_at)}` : <Iso text="runner هنوز تماس نگرفته" />}</span>
    </>
  );
}

/** A company stopped by its own switch or the holding's: everything on its servers stands, every new call is refused. */
export function LockedBanner({ company }: { company: string }) {
  const { data: companies } = useCompanies();
  return (
    <Notice icon="lock" tone="warn" title={`سرورهای ${companyOf(companies, company).nameFa} قفل‌اند`}>
      <Iso text="کلید توقف این شرکت زده شده؛ جلسه‌های Claude روی سرورهایش همان لحظه ایستادند و هر فرمان تازه، حتی از ترمینال تو، رد میشود. با ادامه‌ی کار شرکت باز میشوند." />
    </Notice>
  );
}

/** Used against total, with its label and figures. */
export function UsageBar({ u, label }: { u: DiskUsage; label?: string }) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2 text-[12px]">
        <span className="flex-1 text-sec">{label ?? u.label}</span>
        <span className="fig text-ink">{size(u.usedBytes)} / {size(u.totalBytes)}</span>
      </div>
      <Bar pct={u.pct} tone={u.pct >= 90 ? 'neg' : u.pct >= 75 ? 'warn' : 'silver'} height={5} label={label ?? u.label} />
    </div>
  );
}

const Count = ({ label, value }: { label: string; value: string }) => (
  <span className="flex items-center gap-1"><span className="fig text-[12px] font-semibold text-ink">{value}</span><span className="text-[11px] text-muted">{label}</span></span>
);

/** One server at a glance: its company (the server's own name too when the company has several), its runner's state, version and last
 *  poll, a road to the hub over the public address, and from its map disk, memory and what runs on it. */
export function ServerCard({ s, locked }: { s: HubServer; locked: boolean }) {
  const map = useServerMap(s.id, !!s.map_at).data;
  const name = useServerName(s.company, s.name);
  const on = isOnline(s) && !locked;
  return (
    <Link href={`/servers/${s.id}`} aria-label={`باز کردن سرور ${name.text}`} className="group block">
      <Card className="flex flex-col gap-3 p-4 transition-colors group-hover:bg-tile">
        <div className="flex items-center gap-3">
          <span className={cx('flex size-[42px] flex-none items-center justify-center rounded-[12px]', on ? 'bg-gold-soft text-gold-ink' : 'bg-tile text-sec')}><Icon name="server" size={21} /></span>
          <ServerTitle name={name} className="flex-1 text-[15px]" />
          <span className="text-muted"><Icon name="next" size={16} mirror /></span>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <ServerStatePill state={s.state} locked={locked} />
          <OriginPill origin={s.origin} />
          {s.via === 'public' && isOnline(s) ? <Pill tone="warn" icon="globe">از راه عمومی</Pill> : null}
          <RunnerFacts s={s} />
        </div>
        {map && !mapEmpty(map) ? (
          <div className="flex flex-col gap-2">
            {map.disks[0] ? <UsageBar u={map.disks[0]} label="دیسک" /> : null}
            {map.memory ? <UsageBar u={map.memory} label="رم" /> : null}
            <div className="flex flex-wrap gap-x-3.5 gap-y-1">
              <Count label="کانتینر" value={`${runningContainers(map)}/${map.containers.length}`} />
              <Count label="سایت" value={String(map.sites.length)} />
              <Count label="ریپو" value={String(map.repos.length)} />
              <Count label="اتوماسیون" value={String(map.automations.length)} />
            </div>
          </div>
        ) : null}
      </Card>
    </Link>
  );
}

/** The owner's own words on what the holding may do on a server, shown above every server list. */
export function ServersIntro() {
  return (
    <div className="flex flex-col items-start gap-1.5">
      <p className="text-[13px] leading-6 text-sec"><Iso text="ایجنت‌ها روی این سرورها کد میزنند، commit و push و deploy میکنند و هر کاری را که از شرکت بخواهی انجام میدهند؛ هر فراخوانی با فرمانش در Audit ثبت میشود. فقط شش کار ویرانگر منتظر مُهر تو میمانند." /></p>
      <Link href="/server-policy" className="inline-flex h-8 items-center gap-1.5 rounded-[8px] px-2 text-[12px] font-semibold text-gold-ink hover:bg-gold-soft"><Icon name="lock" size={16} />قوانین سرورها</Link>
    </div>
  );
}

// ------------------------------------------------------------------ activity --
const agentKind = (a: { kind: string; code: string }) => (a.kind === 'owner' ? 'owner' : a.kind === 'system' ? 'system' : a.code.endsWith('-CEO') ? 'ceo' : a.code.endsWith('-MGR') ? 'manager' : 'employee');

/** A job's state (§26.2) as a pill: in the queue, running, held for the seal, done (with its exit), failed, cancelled; or refused. */
export function outcomePill(o: CallOutcome, exit: number | null): { fa: string; tone: Tone; fig?: boolean } {
  switch (o) {
    case 'queued': return { fa: 'در صف', tone: 'silver' };
    case 'running': return { fa: 'در جریان', tone: 'lapis' };
    case 'awaiting_seal': return { fa: 'منتظر مُهر', tone: 'gold' };
    case 'ok': return exit != null ? { fa: `exit ${exit}`, tone: 'pos', fig: true } : { fa: 'انجام شد', tone: 'pos' };
    case 'failed': return exit != null ? { fa: `exit ${exit}`, tone: 'neg', fig: true } : { fa: 'ناموفق', tone: 'neg' };
    case 'cancelled': return { fa: 'لغو شد', tone: 'neutral' };
    default: return { fa: 'رد شد', tone: 'warn' };
  }
}

/** One job (or command) on a server: who, with which tool, what (the masked command, in its folder), its state and how long it took;
 *  its Claude session and its full transcript a click away. */
export function CallLine({ r, serverName, onTranscript }: { r: ServerCallRow; serverName?: string; onTranscript?: (url: string) => void }) {
  const p = outcomePill(r.outcome, r.exitCode);
  return (
    <div className="flex flex-col gap-2 py-3">
      <div className="flex items-center gap-2.5">
        <Avatar kind={agentKind(r.actor)} dept={r.actor.code.split('-')[1]} size={30} state={r.outcome === 'running' ? 'working' : 'idle'} />
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="truncate text-[13px] font-semibold text-ink">{r.byOwner ? 'تو' : ACTOR_FA(r.actor)} · {r.toolFa}{serverName ? <> · {serverName}</> : null}</span>
          {r.summaryFa ? <span className="line-clamp-2 text-[12px] text-sec"><MdInline text={r.summaryFa} /></span> : null}
        </div>
        <span className="text-[11px] text-muted">{jTime(r.at)}</span>
      </div>
      {r.cmd ? <CodeBlock text={r.cmd} prefix={`${r.cwd ? `${r.cwd} ` : ''}$ `} /> : r.cwd ? <span className="flex items-center gap-1.5 text-muted"><Icon name="code" size={14} /><span className="fig text-[12px] text-sec">{r.cwd}</span></span> : null}
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={p.tone} dot={r.outcome !== 'running'} live={r.outcome === 'running'}>{p.fig ? <span className="fig">{p.fa}</span> : p.fa}</Pill>
        {r.duration ? <span className="fig text-[12px] text-muted">{r.duration}</span> : null}
        <span className="flex-1" />
        {r.sessionRef ? <Link href={`/workshop/${r.sessionRef}`} className="inline-flex h-8 items-center gap-1.5 rounded-[8px] px-2 text-[12px] font-semibold text-gold-ink hover:bg-gold-soft"><Icon name="code" size={16} />جلسه <span className="fig">{r.sessionRef}</span></Link> : null}
        {r.transcriptUrl && onTranscript ? <Button variant="ghost" size="sm" icon="report" onClick={() => onTranscript(r.transcriptUrl!)}>متن کامل</Button> : null}
      </div>
    </div>
  );
}

export const CallLines = ({ rows, onTranscript }: { rows: ServerCall[]; onTranscript?: (url: string) => void }) => (
  <Card className="flex flex-col divide-y divide-[var(--hq-line-divider)] px-4 py-1">{rows.map((x, i) => <CallLine key={x.id ?? i} r={callRow(x)} onTranscript={onTranscript} />)}</Card>
);

/** A full transcript as the hub keeps it (§26.3), in monospace. */
export function TranscriptSheet({ url, onClose }: { url: string | null; onClose: () => void }) {
  const q = useTranscript(url);
  return (
    <Sheet open={!!url} onOpenChange={(v) => !v && onClose()} title="متن کامل" description="خروجی همان‌طور که روی سرور آمد؛ رمزها پیش از ذخیره ماسک شده‌اند." width={640}>
      {q.isLoading ? <Skeleton className="h-48" /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : <CodeBlock text={(q.data ?? '').trimEnd()} wrap />}
    </Sheet>
  );
}

// ------------------------------------------------------------------ the seal (§26.3) --
/** The pending cards of destructive commands, from the cartable's own query; [company] narrows to one company. */
export function useServerSeals(company?: string | null): SealCard[] {
  const { data } = useDecisions({ status: 'pending' });
  return (data?.items ?? []).filter((d) => d.kind === SERVER_DESTRUCTIVE && (!company || d.company === company)).map((d) => sealCardOf(d)).filter((x): x is SealCard => !!x);
}

export const SealCards = ({ cards, compact }: { cards: SealCard[]; compact?: boolean }) => (
  <div className="flex flex-col gap-3">{cards.map((c) => <ServerSealCard key={c.ref} card={c} compact={compact} />)}</div>
);

/**
 * «کار ویرانگر منتظر مُهر تو»: what exactly would run, where, what kind of loss it is, who asked from which session. The seal is the
 * passkey on `server.destructive` (`<CODE>:<server>`); a no needs none (like engaging a kill switch).
 */
export function ServerSealCard({ card, compact }: { card: SealCard; compact?: boolean }) {
  const toast = useToast();
  const qc = useQueryClient();
  const decide = useDecide();
  const where = useServerName(card.company, card.serverName);
  const [busy, setBusy] = useState(false);
  const [reject, setReject] = useState(false);
  const [done, setDone] = useState<boolean | null>(null);
  const seal = async () => {
    setBusy(true);
    try {
      const token = await stepUp('server.destructive', card.target);
      await decide.mutateAsync({ ref: card.ref, verdict: 'approve', stepUpToken: token });
      void qc.invalidateQueries({ queryKey: ['servers'] });
      setDone(true);
      toast({ tone: 'ok', text: `مُهر خورد؛ فرمان روی سرور ${where.text} اجرا میشود.` });
    } catch (e) {
      toast({ tone: 'error', text: serverError(e) });
    } finally {
      setBusy(false);
    }
  };
  const no = async () => {
    try {
      await decide.mutateAsync({ ref: card.ref, verdict: 'reject', note: 'مدیر کل اجازه‌ی این کار ویرانگر را نداد.', reasonCode: 'risk' });
      void qc.invalidateQueries({ queryKey: ['servers'] });
      setDone(false);
      setReject(false);
    } catch (e) {
      toast({ tone: 'error', text: serverError(e) });
    }
  };
  const byOwner = card.actor.kind === 'owner';
  return (
    <article aria-label={`کار ویرانگر ${card.ref}`} className="flex flex-col gap-2.5 rounded-[16px] bg-card p-4 ring-1 ring-[color-mix(in_srgb,var(--hq-negative)_55%,transparent)]">
      <div className="flex items-center gap-2.5">
        <span className="flex size-[34px] flex-none items-center justify-center rounded-full bg-neg-soft text-neg"><Icon name="urgent" size={18} /></span>
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="text-[14px] font-semibold text-ink">کار ویرانگر منتظر مُهر تو</span>
          <span className="truncate text-[12px] text-muted">{where.text} · {card.category?.titleFa ?? 'دسته‌ی ویرانگر'} · <span className="fig">{card.ref}</span></span>
        </div>
        <span className="text-sec"><CompanyMark code={card.company} height={14} mono /></span>
      </div>
      {/* The whole command, wrapped: the owner seals exactly what will run, so nothing of it may hide off screen. */}
      <CodeBlock text={card.cmd || '—'} prefix={`${card.cwd ? `${card.cwd} ` : ''}$ `} tone="neg" wrap />
      <p className="text-[12px] leading-6 text-sec">
        {byOwner ? 'از ترمینال تو' : ACTOR_FA(card.actor)}{card.sessionRef ? <> در جلسه‌ی <span className="fig">{card.sessionRef}</span></> : null}، {ago(card.createdAt)}. {card.category?.whyFa ?? ''}
      </p>
      {!compact && card.detectedBy ? <p className="text-[11px] text-muted">{card.detectedBy === 'tool' ? 'دروازه از روی ابزار گرفت' : 'دروازه از روی الگو گرفت'}{card.pattern ? <>: <span className="fig">{card.pattern}</span></> : null}</p> : null}
      {done === true ? <span className="self-start"><Pill tone="gold" icon="seal">مُهر خورد؛ اجرا میشود</Pill></span>
        : done === false ? <span className="self-start"><Pill tone="neutral" icon="reject">اجازه ندادی؛ اجرا نمیشود</Pill></span>
        : !card.pending ? <span className="self-start"><Pill tone="neutral">تصمیم گرفته شد</Pill></span>
        : (
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="primary" icon="seal" loading={busy} onClick={seal}>مُهر بزن</Button>
            <Button variant="danger" icon="reject" disabled={busy} onClick={() => setReject(true)}>نه</Button>
            <span className="flex-1" />
            {!compact ? <Link href={`/cartable?ref=${card.ref}`} className="inline-flex h-8 items-center gap-1 rounded-[8px] px-2 text-[12px] text-sec hover:bg-hover">باز کردن کارت<Icon name="next" size={16} mirror /></Link> : null}
          </div>
        )}
      {card.pending && done == null ? <p className="text-[11px] text-muted">مُهر با اثر انگشت یا چهره؛ «نه» بی‌گذرکلید است.</p> : null}
      <Dialog open={reject} onOpenChange={setReject} title="اجرا نشود؟" actions={<>
        <Button variant="danger" loading={decide.isPending} onClick={no}>اجرا نشود</Button>
        <Button variant="ghost" onClick={() => setReject(false)}>برگشت</Button>
      </>}>
        فرمان روی سرور {where.text} اجرا نمیشود و {byOwner ? '' : `${ACTOR_FA(card.actor)} `}خبردار میشود؛ میتواند راه دیگری پیشنهاد بدهد.
      </Dialog>
    </article>
  );
}

/** The decision page's payload of a `server_destructive` card: the same facts, without its own buttons (the page has the seal). */
export function SealPayload({ d }: { d: Parameters<typeof sealCardOf>[0] }) {
  const card = sealCardOf(d);
  const where = useServerName(card?.company ?? d.company, card?.serverName);
  if (!card) return null;
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-[12px] font-semibold text-gold-ink">فرمانی که اجرا میشود</h3>
      <CodeBlock text={card.cmd || '—'} prefix={`${card.cwd ? `${card.cwd} ` : ''}$ `} tone="neg" wrap />
      <p className="text-[13px] text-sec">سرور {where.text} · {card.category?.titleFa ?? 'ویرانگر'}{card.sessionRef ? <> · جلسه‌ی <span className="fig">{card.sessionRef}</span></> : null}</p>
      {card.category ? <p className="text-[12px] text-muted">{card.category.whyFa} با مُهر، همین فرمان یک بار اجرا میشود؛ هر تغییری کارت تازه میخواهد.</p> : null}
    </section>
  );
}

/** Whether a company's servers are locked, for a list of servers of several companies. */
export function ServerCardFor({ s }: { s: HubServer }) {
  return <ServerCard s={s} locked={useLocked(s.company)} />;
}
