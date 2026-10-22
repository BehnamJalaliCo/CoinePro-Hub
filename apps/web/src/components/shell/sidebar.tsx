'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import * as Menu from '@radix-ui/react-dropdown-menu';
import { Icon } from '@/components/icon';
import { Avatar } from '@/components/brand/avatar';
import { CompanyMark, Monogram, Wordmark } from '@/components/brand/marks';
import { useCompanies, useInbox, usePresence, useSetKhalvat } from '@/lib/api/hooks';
import { useScope } from '@/lib/scope';
import { cx } from '@/lib/format';
import { NAV_GOVERNANCE, NAV_MAIN, NAV_MANAGEMENT, NAV_MEDIA, NAV_TOOLS, isActive, type NavItem } from './nav';

function Badge({ n }: { n: number }) {
  if (!n) return null;
  return <span className="mr-auto inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-gold px-1.5 text-[11px] font-bold text-on-gold">{n}</span>;
}

function Item({ item, counts }: { item: NavItem; counts: Record<string, number> }) {
  const pathname = usePathname();
  const on = isActive(pathname, item.href, item.exact);
  return (
    <Link
      href={item.href}
      aria-current={on ? 'page' : undefined}
      className={cx(
        'flex h-10 items-center gap-3 rounded-[10px] px-3 text-[14px] transition-colors duration-[120ms]',
        on ? 'bg-gold-soft font-semibold text-ink shadow-[inset_-2px_0_0_var(--hq-gold-ink)]' : 'text-sec hover:bg-hover hover:text-ink',
      )}
    >
      <span className={on ? 'text-gold-ink' : undefined}><Icon name={item.icon} size={20} active={on} /></span>
      <span>{item.label}</span>
      {item.badge ? <Badge n={counts[item.badge] ?? 0} /> : null}
    </Link>
  );
}

export function ScopeSwitcher() {
  const { company, setCompany } = useScope();
  const { data: companies } = useCompanies();
  const current = companies?.find((c) => c.code === company);
  return (
    <Menu.Root dir="rtl">
      <Menu.Trigger className="flex h-11 w-full items-center gap-2.5 rounded-[10px] border border-div bg-tile px-2.5 text-[13px] text-ink hover:bg-hover" aria-label="محدوده‌ی نمایش">
        {current && current.kind !== 'holding' ? <span className="text-sec"><CompanyMark code={current.code} height={16} mono /></span> : <Monogram size={16} />}
        <span className="flex-1 truncate text-right font-semibold">{current ? current.name_fa : 'کل هلدینگ'}</span>
        <span className="text-muted"><Icon name="scope" size={16} /></span>
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Content align="start" sideOffset={6} className="z-50 w-[236px] rounded-[14px] bg-raised p-1.5 shadow-[0_16px_40px_rgba(0,0,0,.4)]">
          <Menu.Item onSelect={() => setCompany(null)} className="flex h-10 cursor-pointer items-center gap-2.5 rounded-[8px] px-2.5 text-[13px] text-ink outline-none data-[highlighted]:bg-hover">
            <Monogram size={16} /><span className="flex-1">کل هلدینگ</span>{!company ? <Icon name="seal" size={14} active /> : null}
          </Menu.Item>
          <Menu.Separator className="my-1 h-px bg-div" />
          {(companies ?? []).filter((c) => c.kind !== 'holding').map((c) => (
            <Menu.Item key={c.code} onSelect={() => setCompany(c.code)} className="flex h-10 cursor-pointer items-center gap-2.5 rounded-[8px] px-2.5 text-[13px] text-ink outline-none data-[highlighted]:bg-hover">
              <span className="text-sec"><CompanyMark code={c.code} height={16} mono /></span>
              <span className="flex-1">{c.name_fa}</span>
              {c.kill_switch === 'engaged' ? <span className="text-neg"><Icon name="lock" size={14} /></span> : null}
              {company === c.code ? <span className="text-gold-ink"><Icon name="seal" size={14} active /></span> : null}
            </Menu.Item>
          ))}
        </Menu.Content>
      </Menu.Portal>
    </Menu.Root>
  );
}

export function Sidebar() {
  const { data: inbox } = useInbox();
  const { data: presence } = usePresence();
  const khalvat = useSetKhalvat();
  const counts = { decisions: inbox?.decisions_pending ?? 0, deliverables: inbox?.deliverables_unrated ?? 0, messages: inbox?.messages_unread ?? 0 };
  const on = presence?.khalvat ?? false;
  return (
    <aside className="sticky top-0 hidden h-dvh w-[260px] flex-none flex-col gap-3.5 border-l border-hair bg-card px-3 pb-3.5 pt-[18px] lg:flex">
      <Link href="/" className="flex items-center gap-2.5 px-1.5" aria-label="ستاد کوینه‌پرو">
        <Monogram size={30} />
        <div className="flex flex-col gap-1">
          <div dir="ltr" className="flex items-end justify-end gap-1.5"><Wordmark width={108} /><span className="fig pb-px text-[13px] font-semibold leading-none tracking-[.06em] text-ink">HQ</span></div>
          <span className="text-[11px] text-muted">ستاد کوینه‌پرو</span>
        </div>
      </Link>
      <ScopeSwitcher />
      {/* The lists scroll on their own when they are taller than the window; the logo, scope and owner card stay put. */}
      <div className="-mx-1 flex min-h-0 flex-1 flex-col gap-3.5 overflow-y-auto px-1">
        <nav aria-label="ناوبری اصلی" className="flex flex-col gap-0.5">{NAV_MAIN.map((i) => <Item key={i.href} item={i} counts={counts} />)}</nav>
        <div aria-hidden className="mx-1.5 h-px flex-none bg-div" />
        <nav aria-label="ابزار مدیریت" className="flex flex-col gap-0.5">
          <span className="px-3 pb-1 text-[11px] text-muted">ابزار مدیریت</span>
          {NAV_MANAGEMENT.map((i) => <Item key={i.href} item={i} counts={counts} />)}
        </nav>
        <div aria-hidden className="mx-1.5 h-px flex-none bg-div" />
        <nav aria-label="رسانه و حقوقی" className="flex flex-col gap-0.5">
          <span className="px-3 pb-1 text-[11px] text-muted">رسانه و حقوقی</span>
          {NAV_MEDIA.map((i) => <Item key={i.href} item={i} counts={counts} />)}
        </nav>
        <div aria-hidden className="mx-1.5 h-px flex-none bg-div" />
        <nav aria-label="حاکمیت" className="flex flex-col gap-0.5">
          <span className="px-3 pb-1 text-[11px] text-muted">حاکمیت</span>
          {NAV_GOVERNANCE.map((i) => <Item key={i.href} item={i} counts={counts} />)}
        </nav>
        <div aria-hidden className="mx-1.5 h-px flex-none bg-div" />
        <nav aria-label="ابزارها" className="flex flex-col gap-0.5">{NAV_TOOLS.map((i) => <Item key={i.href} item={i} counts={counts} />)}</nav>
      </div>
      <div className="flex items-center gap-2.5 rounded-[12px] bg-tile p-2.5">
        <Avatar kind="owner" size={32} />
        <div className="flex flex-1 flex-col">
          <span className="text-[13px] font-semibold">مدیر کل</span>
          <span className={cx('text-[11px]', on ? 'text-learn' : 'text-muted')}>{on ? 'خلوت روشن؛ فقط فوری' : 'خلوت خاموش'}</span>
        </div>
        <button
          type="button"
          aria-pressed={on}
          aria-label={on ? 'خاموش کردن خلوت' : 'روشن کردن خلوت'}
          title="خلوت"
          disabled={khalvat.isPending}
          onClick={() => khalvat.mutate(!on)}
          className={cx('flex size-9 items-center justify-center rounded-full border transition-colors', on ? 'border-transparent bg-learn-soft text-learn' : 'border-div text-sec hover:text-ink')}
        >
          <Icon name="khalvat" size={18} active={on} />
        </button>
      </div>
    </aside>
  );
}
