'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState, type ReactNode } from 'react';
import { Icon } from '@/components/icon';
import type { IconName } from '@/generated/icons';
import { Orb } from '@/components/brand/avatar';
import { Monogram } from '@/components/brand/marks';
import { IconButton } from '@/components/ui/button';
import { Kbd } from '@/components/ui/primitives';
import { ApiError } from '@/lib/api/client';
import { useInbox, useSession } from '@/lib/api/hooks';
import { ScopeProvider } from '@/lib/scope';
import { useHoldingStream, type StreamEvent } from '@/lib/stream';
import { DecisionToasts, KillBand, LiveBeacon, LiveSeed, UrgentBanner } from '@/components/live/shell';
import { LiveContext } from '@/lib/live';
import { useTheme } from '@/lib/theme';
import { cx } from '@/lib/format';
import { VoiceOrder, VoiceOrderContext, type VoiceOpen } from '@/components/work/voice-order';
import { ServersWatcher } from '@/components/v26/watcher';
import { PulsesProvider } from '@/lib/pulses';
import { HubBanner, ShellExtras, ToolsSheet } from '@/components/v21/shell';
import { CommandPalette } from './command-palette';
import { NotificationsSheet } from './notifications';
import { useSessions } from '@/lib/api/v34';
import { NAV_MOBILE, isActive } from './nav';
import { CommandButton, CommandContext, CommandSheet, type CommandOpen } from '@/components/look/command';
import { useRouteSettle } from '@/components/look/transition';
import { ScopeSwitcher, Sidebar } from './sidebar';

function ThemeToggle() {
  const [t, set] = useTheme();
  const next = t === 'day' ? 'night' : 'day';
  return <IconButton icon={t === 'day' ? 'sleeping' : 'time'} label={next === 'day' ? 'تم روز' : 'تم شب'} onClick={() => set(next)} />;
}

const BAR_ITEM = 'inline-flex h-12 min-w-11 flex-none flex-col items-center justify-center gap-0.5 rounded-[10px] px-1.5 text-sec hover:bg-hover hover:text-ink md:h-10 md:flex-row md:gap-1.5 md:px-2.5';
const BAR_LABEL = 'text-[10px] leading-3 md:text-[13px] md:font-semibold md:leading-5';
/** One sign of the top bar with its name under it (beside it on a wide screen, where only «گفتگو» keeps its word). */
function BarItem({ icon, label, short, onClick, className }: { icon: IconName; label: string; short?: string; onClick: () => void; className?: string }) {
  return (
    <button type="button" aria-label={label} title={label} onClick={onClick} className={cx(BAR_ITEM, className)}>
      <Icon name={icon} size={20} /><span aria-hidden className={cx(BAR_LABEL, 'md:hidden')}>{short ?? label}</span>
    </button>
  );
}

function TopBar({ onPalette, onBell, onMore, onVoice, urgent }: { onPalette: () => void; onBell: () => void; onMore: () => void; onVoice: () => void; urgent: number }) {
  return (
    // ⟨1.24⟩ GL-2: the kill-switch band rides on top of the bar, on every screen.
    <div className="sticky top-0 z-30">
    <KillBand />
    <div className="flex h-16 items-center gap-3 border-b border-div bg-page/90 px-4 backdrop-blur-md md:px-6">
      <Link href="/" className="flex items-center gap-2 lg:hidden" aria-label="ستاد کوینه‌پرو"><Monogram size={26} /><span className="text-[15px] font-semibold">ستاد</span></Link>
      <button type="button" onClick={onPalette} className="hidden h-10 w-[min(360px,40vw)] items-center gap-2.5 rounded-[10px] border border-div bg-tile px-3 text-[13px] text-muted hover:text-sec md:flex" aria-label="جستجو و فرمان">
        <Icon name="search" size={18} /><span className="flex-1 text-right">جستجو یا فرمان…</span><Kbd>Ctrl K</Kbd>
      </button>
      <span className="flex-1" />
      {/* ⟨1.24⟩ GL-1: live / reconnecting / stale / offline, in words. */}
      <LiveBeacon compact />
      {/* ⟨1.0.1⟩ part C: on a phone every sign of the bar carries its name; the mic is quiet (the owner types), nothing here is gold. */}
      <BarItem icon="search" label="جستجو" onClick={onPalette} className="md:hidden" />
      <Link href="/talk" aria-label="گفتگو با ستاد" title="گفتگو با ستاد" className={BAR_ITEM}><Icon name="messages" size={20} /><span className={BAR_LABEL}>گفتگو</span></Link>
      <BarItem icon="mic" label="فرمان صوتی" short="صوتی" onClick={onVoice} />
      <span className="relative">
        <BarItem icon="bell" label="اعلان‌ها" short="اعلان" onClick={onBell} />
        {urgent > 0 ? <span className="pointer-events-none absolute right-2 top-0.5 size-2.5 rounded-full border-2 border-page bg-neg" /> : null}
      </span>
      {/* Phones: the theme lives in settings and the palette, so the bar keeps room for the names. */}
      <span className="hidden sm:inline-flex"><ThemeToggle /></span>
      <BarItem icon="more" label="همه‌ی بخش‌ها" short="بیشتر" onClick={onMore} />
    </div>
    </div>
  );
}

function BottomNav({ counts }: { counts: Record<string, number> }) {
  const pathname = usePathname();
  return (
    <nav aria-label="ناوبری اصلی" className="fixed inset-x-0 bottom-0 z-30 flex h-[76px] items-stretch border-t border-div bg-card/95 px-1 pb-[env(safe-area-inset-bottom)] backdrop-blur-md lg:hidden">
      {NAV_MOBILE.map((n) => {
        const on = isActive(pathname, n.href);
        if (n.href === '/advisor') {
          return (
            <Link key={n.href} href={n.href} aria-label="مشاور کل" className="flex flex-1 items-start justify-center">
              <span className={cx('-mt-5 rounded-full p-1.5', on ? 'bg-raised' : 'bg-page')}><Orb size={56} state={on ? 'listening' : 'rest'} /></span>
            </Link>
          );
        }
        const badge = n.badge ? counts[n.badge] ?? 0 : 0;
        return (
          <Link key={n.href} href={n.href} aria-current={on ? 'page' : undefined} className={cx('flex flex-1 flex-col items-center justify-center gap-1 text-[11px]', on ? 'font-bold text-ink' : 'text-muted')}>
            <span className="relative">
              <Icon name={n.icon} size={24} active={on} />
              {badge ? <span className="absolute -right-2.5 -top-1.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-page px-1 text-[10px] font-bold text-gold-ink shadow-[inset_0_0_0_1px_var(--hq-gold-ink)]">{badge}</span> : null}
            </span>
            {n.label}
          </Link>
        );
      })}
    </nav>
  );
}

function Splash() {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-4">
      <span style={{ animation: 'hq-breath 2.4s ease-in-out infinite' }}><Monogram size={56} /></span>
      <span className="text-caption text-muted">ستاد کوینه‌پرو</span>
    </div>
  );
}

/** The signed-in frame: sidebar (web) or bottom bar (phone), top bar, palette, notifications, live stream. */
export function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const session = useSession();
  const { data: inbox } = useInbox();
  const [feed, setFeed] = useState<StreamEvent[]>([]);
  const stream = useHoldingStream((e) => setFeed((f) => [e, ...f].slice(0, 40)));
  const [palette, setPalette] = useState(false);
  const [bell, setBell] = useState(false);
  const [more, setMore] = useState(false);
  const [voice, setVoice] = useState(false);
  // ⟨1.11⟩ the golden button opens as an order or a rule, optionally with words (a council's plan).
  const [voiceInit, setVoiceInit] = useState<{ n: number; o: VoiceOpen }>({ n: 0, o: {} });
  const openVoice = (o?: VoiceOpen) => { setVoiceInit((v) => ({ n: v.n + 1, o: o ?? {} })); setVoice(true); };
  // ⟨1.0.1⟩ part C: the command sheet, opened from the round button of every screen (and the home's row); mounted afresh each time.
  const [command, setCommand] = useState<{ n: number; open: boolean; o: CommandOpen }>({ n: 0, open: false, o: {} });
  const openCommand = (o?: CommandOpen) => setCommand((c) => ({ n: c.n + 1, open: true, o: o ?? {} }));
  useRouteSettle();
  // Inside a session its composer is the command.
  const inSession = /^\/s\/[^/]+/.test(pathname);

  useEffect(() => {
    if (session.error instanceof ApiError && session.error.status === 401) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [session.error, router, pathname]);

  const turn = useSessions('open').data?.filter((x) => x.badge === 'your_turn').length ?? 0;

  if (session.isLoading || (session.error instanceof ApiError && session.error.status === 401)) return <Splash />;

  const counts = { decisions: inbox?.decisions_pending ?? 0, deliverables: inbox?.deliverables_unrated ?? 0, messages: inbox?.messages_unread ?? 0, sessions: turn };
  const levels = inbox?.notifications as Record<string, number> | undefined;
  const urgent = (levels?.urgent ?? 0) + (levels?.decision ?? 0);

  return (
    <ScopeProvider>
      <LiveContext.Provider value={{ state: stream, last: feed[0] ?? null, feed }}>
      <PulsesProvider feed={feed}>
      <VoiceOrderContext.Provider value={openVoice}>
      <CommandContext.Provider value={openCommand}>
      <div className="flex min-h-dvh">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar onPalette={() => setPalette(true)} onBell={() => setBell(true)} onMore={() => setMore(true)} onVoice={() => openVoice()} urgent={urgent} />
          {/* 0.4.0: a hub restart is one calm line, not an error on every card. */}
          <HubBanner />
          {/* ⟨1.24⟩ NO-1: what is urgent stays here until the owner has seen it. */}
          <UrgentBanner />
          <main id="main" className="mx-auto flex w-full max-w-[1440px] flex-1 flex-col gap-6 px-4 pb-28 pt-5 md:px-6 lg:pb-10">{children}</main>
        </div>
      </div>
      <BottomNav counts={counts} />
      {inSession ? null : <CommandButton onClick={() => openCommand()} />}
      <CommandSheet key={`command-${command.n}`} open={command.open} onOpenChange={(v) => setCommand((c) => ({ ...c, open: v }))} initial={command.o} />
      <CommandPalette open={palette} onOpenChange={setPalette} onVoice={() => openVoice()} />
      <VoiceOrder key={voiceInit.n} open={voice} onOpenChange={setVoice} initial={voiceInit.o} />
      <NotificationsSheet open={bell} onOpenChange={setBell} />
      {/* 0.3.0–0.6.0: «خطاخوان», the hub's health and the alerts (toasts on screen, the browser's notifications otherwise). */}
      <ShellExtras feed={feed} stream={stream} />
      {/* ⟨1.8⟩ §26.3: a destructive command held for the seal on a company server says so at once. */}
      <ServersWatcher />
      {/* ⟨1.24⟩ K-2 the live store's seed; NO-1 the cards for the seal. */}
      <LiveSeed />
      <DecisionToasts />
      <ToolsSheet open={more} onOpenChange={setMore} extra={<ScopeSwitcher />} />
      </CommandContext.Provider>
      </VoiceOrderContext.Provider>
      </PulsesProvider>
      </LiveContext.Provider>
    </ScopeProvider>
  );
}
