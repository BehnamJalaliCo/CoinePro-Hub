'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState, type ReactNode } from 'react';
import { Icon } from '@/components/icon';
import { Orb } from '@/components/brand/avatar';
import { Monogram } from '@/components/brand/marks';
import { IconButton } from '@/components/ui/button';
import { Kbd } from '@/components/ui/primitives';
import { Sheet } from '@/components/ui/overlay';
import { ApiError } from '@/lib/api/client';
import { useInbox, useSession } from '@/lib/api/hooks';
import { ScopeProvider } from '@/lib/scope';
import { useHoldingStream, type StreamEvent, type StreamState } from '@/lib/stream';
import { LiveContext } from '@/lib/live';
import { useTheme } from '@/lib/theme';
import { cx } from '@/lib/format';
import { CommandPalette } from './command-palette';
import { NotificationsSheet } from './notifications';
import { NAV_MOBILE, NAV_TOOLS, isActive } from './nav';
import { ScopeSwitcher, Sidebar } from './sidebar';

function LiveDot({ state }: { state: StreamState }) {
  const label = state === 'live' ? 'زنده' : state === 'connecting' ? 'در حال اتصال' : 'قطع؛ دوباره وصل میشود';
  return (
    <span className={cx('inline-flex h-7 items-center gap-1.5 rounded-full px-2.5 text-[12px] font-semibold', state === 'live' ? 'bg-pos-soft text-pos' : state === 'offline' ? 'bg-warn-soft text-warn' : 'bg-tile text-muted')} title={label}>
      <span className="size-1.5 rounded-full bg-current" style={state === 'live' ? { animation: 'hq-live 1.4s infinite' } : undefined} />
      <span className="hidden sm:inline">{label}</span>
    </span>
  );
}

function ThemeToggle() {
  const [t, set] = useTheme();
  const next = t === 'day' ? 'night' : 'day';
  return <IconButton icon={t === 'day' ? 'sleeping' : 'time'} label={next === 'day' ? 'تم روز' : 'تم شب'} onClick={() => set(next)} />;
}

function TopBar({ onPalette, onBell, onMore, stream, urgent }: { onPalette: () => void; onBell: () => void; onMore: () => void; stream: StreamState; urgent: number }) {
  return (
    <div className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-div bg-page/90 px-4 backdrop-blur-md md:px-6">
      <Link href="/" className="flex items-center gap-2 lg:hidden" aria-label="ستاد کوینه‌پرو"><Monogram size={26} /><span className="text-[15px] font-semibold">ستاد</span></Link>
      <button type="button" onClick={onPalette} className="hidden h-10 w-[min(360px,40vw)] items-center gap-2.5 rounded-[10px] border border-div bg-tile px-3 text-[13px] text-muted hover:text-sec md:flex" aria-label="جستجو و فرمان">
        <Icon name="search" size={18} /><span className="flex-1 text-right">جستجو یا فرمان…</span><Kbd>Ctrl K</Kbd>
      </button>
      <span className="flex-1" />
      <LiveDot state={stream} />
      <IconButton icon="search" label="جستجو" onClick={onPalette} className="md:hidden" />
      <span className="relative">
        <IconButton icon="bell" label="اعلان‌ها" onClick={onBell} />
        {urgent > 0 ? <span className="pointer-events-none absolute right-1.5 top-1.5 size-2.5 rounded-full border-2 border-page bg-neg" /> : null}
      </span>
      <ThemeToggle />
      <IconButton icon="more" label="بیشتر" onClick={onMore} className="lg:hidden" />
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
              <span className={cx('-mt-5 rounded-full p-1.5', on ? 'bg-gold-soft' : 'bg-page')}><Orb size={56} state={on ? 'listening' : 'rest'} /></span>
            </Link>
          );
        }
        const badge = n.badge ? counts[n.badge] ?? 0 : 0;
        return (
          <Link key={n.href} href={n.href} aria-current={on ? 'page' : undefined} className={cx('flex flex-1 flex-col items-center justify-center gap-1 text-[11px]', on ? 'font-bold text-ink' : 'text-muted')}>
            <span className={cx('relative', on && 'text-gold-ink')}>
              <Icon name={n.icon} size={24} active={on} />
              {badge ? <span className="absolute -right-2.5 -top-1.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-gold px-1 text-[10px] font-bold text-on-gold">{badge}</span> : null}
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

  useEffect(() => {
    if (session.error instanceof ApiError && session.error.status === 401) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [session.error, router, pathname]);

  if (session.isLoading || (session.error instanceof ApiError && session.error.status === 401)) return <Splash />;

  const counts = { decisions: inbox?.decisions_pending ?? 0, deliverables: inbox?.deliverables_unrated ?? 0, messages: inbox?.messages_unread ?? 0 };
  const urgent = (inbox?.notifications as Record<string, number> | undefined)?.urgent ?? 0;

  return (
    <ScopeProvider>
      <LiveContext.Provider value={{ state: stream, last: feed[0] ?? null, feed }}>
      <div className="flex min-h-dvh">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar onPalette={() => setPalette(true)} onBell={() => setBell(true)} onMore={() => setMore(true)} stream={stream} urgent={urgent} />
          <main id="main" className="mx-auto flex w-full max-w-[1440px] flex-1 flex-col gap-6 px-4 pb-28 pt-5 md:px-6 lg:pb-10">{children}</main>
        </div>
      </div>
      <BottomNav counts={counts} />
      <CommandPalette open={palette} onOpenChange={setPalette} />
      <NotificationsSheet open={bell} onOpenChange={setBell} />
      <Sheet open={more} onOpenChange={setMore} title="بیشتر" width={360}>
        <div className="flex flex-col gap-3">
          <ScopeSwitcher />
          <nav className="flex flex-col gap-1">
            {NAV_TOOLS.map((n) => (
              <Link key={n.href} href={n.href} onClick={() => setMore(false)} className="flex h-12 items-center gap-3 rounded-[10px] px-3 text-[15px] text-ink hover:bg-hover">
                <span className="text-sec"><Icon name={n.icon} size={20} /></span>{n.label}
              </Link>
            ))}
            <Link href="/outputs" onClick={() => setMore(false)} className="flex h-12 items-center gap-3 rounded-[10px] px-3 text-[15px] text-ink hover:bg-hover"><span className="text-sec"><Icon name="deliverable" size={20} /></span>خروجی‌ها</Link>
          </nav>
        </div>
      </Sheet>
      </LiveContext.Provider>
    </ScopeProvider>
  );
}
