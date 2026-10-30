'use client';

// ⟨1.8⟩ «ترمینال»: the owner's own command on a company server (§26.4 `POST /infra/servers/{id}/exec`, 🔏 `server.exec` per command), its
// output streaming into a monospace, left-to-right panel inside the right-to-left page; the last commands a click away. A destructive one
// waits for the seal like any agent's; a stopped company refuses it (`423 company_locked`) (Android: Terminal.kt).

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { use, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Icon } from '@/components/icon';
import { Button, Spinner } from '@/components/ui/button';
import { ErrorState, FilterChip, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { LockedBanner, ServerStatePill, ServerTitle, useServerName } from '@/components/v26/bits';
import { ApiError } from '@/lib/api/client';
import {
  execOnServer, isOnline, loginOf, serverError, TermHistory, TerminalBuffer, useLocked, useServerActivity, useServers,
  type HubServer, type TermKind,
} from '@/lib/api/v26';
import { cx } from '@/lib/format';

/** One server's terminal as it stays while the panel is open: its lines (memory only) and the command that may be running. */
type TermUi = { buffer: TerminalBuffer; history: TermHistory; ctrl: AbortController | null };
const TERMS = new Map<string, TermUi>();
const termOf = (id: string) => { let t = TERMS.get(id); if (!t) { t = { buffer: new TerminalBuffer(), history: new TermHistory(), ctrl: null }; TERMS.set(id, t); } return t; };
const setCtrl = (id: string, c: AbortController | null) => { termOf(id).ctrl = c; };
const abortTerm = (id: string) => termOf(id).ctrl?.abort();

/** The lines the panel draws at most (the buffer keeps more). */
const SHOWN = 800;
/** A few starting points for the owner, all harmless (read-only). */
const SUGGESTED = ['docker ps', 'df -h', 'free -h', 'systemctl list-timers --no-pager', 'git -C ~ status', 'tail -n 50 /var/log/syslog'];
const COLOR: Record<TermKind, string> = { cmd: 'text-gold-ink font-bold', out: 'text-ink', err: 'text-neg', info: 'text-muted', ok: 'text-pos', fail: 'text-neg' };

function Terminal({ s }: { s: HubServer }) {
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();
  const term = termOf(s.id);
  const locked = useLocked(s.company);
  const name = useServerName(s.company, s.name);
  const mine = useServerActivity(s.id, 'owner', 20);
  const [, setVersion] = useState(0);
  const bump = () => setVersion((v) => v + 1);
  const [cmd, setCmd] = useState('');
  const [sudo, setSudo] = useState(false);
  const panel = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const lines = term.buffer.lines;
  const running = term.buffer.running;
  useLayoutEffect(() => { const el = panel.current; if (el) el.scrollTop = el.scrollHeight; });
  useEffect(() => { input.current?.focus(); }, []);

  const run = async (text: string) => {
    const command = text.trim();
    if (!command || term.buffer.running) return;
    term.history.add(command);
    term.buffer.command(command, loginOf(s));
    setCmd('');
    const ctrl = new AbortController();
    setCtrl(s.id, ctrl);
    bump();
    try {
      await execOnServer(s, { cmd: command, timeout_s: 600, sudo }, (e) => {
        term.buffer.apply(e);
        bump();
        if (e.t === 'awaiting_seal') {
          for (const k of ['decisions', 'inbox', 'servers']) void qc.invalidateQueries({ queryKey: [k] });
          toast({ tone: 'info', text: 'کارتش در کارتابل منتظر مُهر توست.', action: e.decisionRef ? { label: 'کارت', run: () => router.push(`/cartable?ref=${e.decisionRef}`) } : undefined });
        }
      }, ctrl.signal);
      term.buffer.ended('اتصال بسته شد؛ پایان فرمان نرسید. نتیجه در «فعالیت» ثبت است.');
    } catch (e) {
      if (ctrl.signal.aborted) term.buffer.ended('متوقف کردی؛ اتصال بسته شد.');
      else if (e instanceof ApiError && e.status === 0) term.buffer.apply({ t: 'failed', code: 'network_error', messageFa: 'اتصال قطع شد؛ نتیجه در «فعالیت» ثبت است.' });
      else term.buffer.apply({ t: 'failed', code: (e as { code?: string })?.code ?? 'error', messageFa: serverError(e) });
    } finally {
      setCtrl(s.id, null);
      bump();
      void qc.invalidateQueries({ queryKey: ['servers'] });
    }
  };

  const recorded = useMemo(() => (mine.data?.items ?? []).map((x) => x.cmd_masked ?? '').filter(Boolean), [mine.data]);
  const recent = term.history.with(recorded);
  const shown = lines.length > SHOWN ? lines.slice(-SHOWN) : lines;
  const can = !!cmd.trim() && !locked && isOnline(s);

  return (
    <div className="flex min-h-[calc(100dvh-9rem)] flex-col gap-3">
      <Link href={`/servers/${s.id}`} className="inline-flex items-center gap-1 self-start text-[13px] text-sec hover:text-ink"><Icon name="back" size={16} mirror />سرور</Link>
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <h1 className="text-h2 font-semibold text-ink">ترمینال</h1>
          <ServerTitle name={name} className="text-[13px] text-sec" />
        </div>
        <ServerStatePill state={s.state} locked={locked} />
      </div>
      {locked ? <LockedBanner company={s.company} /> : <p className="text-[12px] text-muted">هر فرمان با اثر انگشت تأیید میشود و با خروجی‌اش در «فعالیت» میماند؛ کارهای ویرانگر طبق قوانین سرورها منتظر مُهر میمانند.</p>}

      {/* The panel: the server's own text, left to right in monospace, whatever the page's direction. Lines are never wrapped (a table
          stays a table): the panel scrolls both ways, and follows the output down. */}
      <div ref={panel} dir="ltr" role="log" aria-label="خروجی ترمینال" aria-live="polite" className="min-h-[320px] flex-1 overflow-auto rounded-[14px] border border-div bg-tile p-3 text-left font-mono text-[12.5px] leading-[18px]" style={{ maxHeight: 'calc(100dvh - 22rem)' }}>
        {!lines.length ? (
          <div className="flex flex-col gap-1.5 text-muted">
            <span>{loginOf(s)}:~$</span>
            <span># type a command below, or pick one:</span>
            {SUGGESTED.map((x) => <button key={x} type="button" onClick={() => { setCmd(x); input.current?.focus(); }} className="self-start whitespace-pre text-gold-ink hover:underline">{`  ${x}`}</button>)}
          </div>
        ) : (
          <>
            {lines.length > SHOWN ? <div className="text-muted">… {lines.length - SHOWN} earlier lines</div> : null}
            {shown.map((l, i) => <div key={i} className={cx('whitespace-pre', COLOR[l.kind], l.kind === 'cmd' && i > 0 && 'mt-2.5')}>{l.text || ' '}</div>)}
            {running ? <div className="mt-1 flex items-center gap-1.5 text-muted"><span className="motion-reduce:hidden"><Spinner size={10} className="text-gold-ink" /></span>running…</div> : null}
          </>
        )}
      </div>

      {recent.length ? (
        <div dir="ltr" className="flex gap-1.5 overflow-x-auto pb-1" aria-label="فرمان‌های اخیر">
          {recent.map((h) => <button key={h} type="button" title="دوباره بنویس" onClick={() => { setCmd(h); input.current?.focus(); }} className="max-w-[280px] flex-none truncate rounded-[8px] bg-card px-2.5 py-1.5 font-mono text-[12px] text-sec hover:text-ink">{h}</button>)}
        </div>
      ) : null}

      <div className="flex items-center gap-2">
        <FilterChip selected={sudo} onClick={() => setSudo(!sudo)}><span className="fig">sudo</span></FilterChip>
        {lines.length && !running ? <Button variant="ghost" size="sm" onClick={() => { term.buffer.clear(); bump(); }}>پاک کردن صفحه</Button> : null}
        <span className="flex-1" />
        {term.buffer.lastExit != null && !running ? <span className={cx('fig text-[12px]', term.buffer.lastExit === 0 ? 'text-pos' : 'text-neg')}>exit {term.buffer.lastExit}</span> : null}
      </div>
      <form dir="ltr" onSubmit={(e) => { e.preventDefault(); if (can) void run(cmd); }} className="sticky bottom-[76px] flex items-center rounded-[12px] border border-strong bg-card pl-3 pr-1 lg:bottom-2">
        <span className="font-mono text-[13px] font-bold text-gold-ink">{sudo ? '#' : '$'}</span>
        <input ref={input} value={cmd} onChange={(e) => setCmd(e.target.value.replace(/\n/g, ' '))} disabled={locked} placeholder={locked ? 'locked' : 'command'} aria-label="فرمان"
          autoCapitalize="off" autoCorrect="off" autoComplete="off" spellCheck={false} className="h-12 min-w-0 flex-1 bg-transparent px-2 font-mono text-[13px] text-ink outline-none placeholder:text-muted" />
        {running ? <Button variant="danger" icon="stop" aria-label="توقف" onClick={() => abortTerm(s.id)} />
          : <Button type="submit" variant="primary" icon="send" aria-label="اجرا با اثر انگشت" disabled={!can} />}
      </form>
    </div>
  );
}

export default function TerminalPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const q = useServers();
  const s = q.data?.find((x) => x.id === id);
  if (s) return <Terminal s={s} />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (q.data) return <ErrorState error={{ messageFa: 'این سرور پیدا نشد.' }} />;
  return <Skeleton className="h-[60vh] rounded-[16px]" />;
}
