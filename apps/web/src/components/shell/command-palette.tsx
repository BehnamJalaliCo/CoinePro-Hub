'use client';

import { Command } from 'cmdk';
import * as D from '@radix-ui/react-dialog';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { useCompanies, useDecisions, useEmployees } from '@/lib/api/hooks';
import { useMessageSearch } from '@/lib/api/v15';
import { jDate } from '@/lib/format';
import { useTheme } from '@/lib/theme';
import { NAV_GOVERNANCE, NAV_MAIN, NAV_MANAGEMENT, NAV_TOOLS } from './nav';

const itemCls = 'flex h-11 cursor-pointer items-center gap-3 rounded-[10px] px-3 text-[14px] text-ink outline-none data-[selected=true]:bg-hover';
const groupCls = '[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:pt-2 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:text-muted';

/** Command palette (D1): Ctrl/⌘ K — go anywhere, find a company, an employee or a decision. */
export function CommandPalette({ open, onOpenChange, onVoice }: { open: boolean; onOpenChange: (v: boolean) => void; onVoice?: () => void }) {
  const router = useRouter();
  const [, setTheme] = useTheme();
  const { data: companies } = useCompanies();
  const { data: employees } = useEmployees({});
  const { data: decisions } = useDecisions({ status: 'pending' });
  const go = (href: string) => { onOpenChange(false); router.push(href); };
  // Message search (§5.3) runs on the server once the query settles; cmdk keeps the hits because their value carries the query.
  const [search, setSearch] = useState('');
  const [settled, setSettled] = useState('');
  useEffect(() => { const t = setTimeout(() => setSettled(search.trim()), 300); return () => clearTimeout(t); }, [search]);
  const hits = useMessageSearch(open ? settled : '');

  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); onOpenChange(!open); }
    };
    window.addEventListener('keydown', k);
    return () => window.removeEventListener('keydown', k);
  }, [open, onOpenChange]);

  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-40 bg-scrim" />
        <D.Content className="fixed left-1/2 top-[12vh] z-50 w-[min(94vw,640px)] -translate-x-1/2 overflow-hidden rounded-[18px] bg-raised shadow-[0_24px_64px_rgba(0,0,0,.5)] outline-none">
          <D.Title className="sr-only">پالت فرمان</D.Title>
          <D.Description className="sr-only">جستجو در صفحه‌ها، شرکت‌ها، کارمندها، تصمیم‌ها و پیام‌ها</D.Description>
          <Command label="پالت فرمان" loop>
            <div className="flex items-center gap-3 border-b border-div px-4">
              <span className="text-muted"><Icon name="search" size={20} /></span>
              <Command.Input autoFocus value={search} onValueChange={setSearch} placeholder="کجا بروم؟ شرکت، کارمند، تصمیم، یا متن یک پیام…" className="h-14 flex-1 bg-transparent text-[15px] text-ink outline-none placeholder:text-muted" />
            </div>
            <Command.List className="max-h-[60vh] overflow-y-auto p-2">
              <Command.Empty className="px-3 py-8 text-center text-[13px] text-muted">چیزی پیدا نشد.</Command.Empty>
              {onVoice ? (
                <Command.Group heading="فرمان" className={groupCls}>
                  <Command.Item value="voice order فرمان صوتی ویس" onSelect={() => { onOpenChange(false); onVoice(); }} className={itemCls}>
                    <span className="text-gold-ink"><Icon name="mic" size={18} /></span>فرمان صوتی
                  </Command.Item>
                </Command.Group>
              ) : null}
              <Command.Group heading="صفحه‌ها" className={groupCls}>
                {[...NAV_MAIN, ...NAV_MANAGEMENT, ...NAV_GOVERNANCE, ...NAV_TOOLS].map((n) => (
                  <Command.Item key={n.href} value={`page ${n.label}`} onSelect={() => go(n.href)} className={itemCls}>
                    <span className="text-sec"><Icon name={n.icon} size={18} /></span>{n.label}
                  </Command.Item>
                ))}
              </Command.Group>
              {decisions?.items.length ? (
                <Command.Group heading="منتظر مُهر" className={groupCls}>
                  {decisions.items.map((d) => (
                    <Command.Item key={d.ref} value={`${d.ref} ${d.title}`} onSelect={() => go(`/cartable?ref=${d.ref}`)} className={itemCls}>
                      <span className="text-warn"><Icon name="level-decision" size={18} /></span><span className="flex-1 truncate">{d.title}</span><span className="fig text-[12px] text-muted">{d.ref}</span>
                    </Command.Item>
                  ))}
                </Command.Group>
              ) : null}
              {settled.length >= 2 && hits.data?.items.length ? (
                <Command.Group heading="در پیام‌ها" className={groupCls}>
                  {hits.data.items.slice(0, 8).map((h) => (
                    <Command.Item key={h.id} value={`msg ${h.ref} ${search} ${h.body.slice(0, 80)}`} onSelect={() => go(`/messages?thread=${encodeURIComponent(h.thread)}`)} className={itemCls}>
                      <span className="text-sec"><Icon name="messages" size={18} /></span>
                      <span className="min-w-0 flex-1 truncate">{h.body.replace(/[*_`#>]/g, '')}</span>
                      <span className="fig text-[12px] text-muted">{h.ref}</span><span className="text-[11px] text-muted">{jDate(h.created_at)}</span>
                    </Command.Item>
                  ))}
                </Command.Group>
              ) : null}
              <Command.Group heading="شرکت‌ها" className={groupCls}>
                {(companies ?? []).map((c) => (
                  <Command.Item key={c.code} value={`company ${c.code} ${c.name_fa ?? ''} ${c.name_en ?? ''}`} onSelect={() => go(`/companies/${c.code}`)} className={itemCls}>
                    <span className="text-sec"><CompanyMark code={c.code} height={16} mono /></span>{c.name_fa}
                  </Command.Item>
                ))}
              </Command.Group>
              <Command.Group heading="کارمندها" className={groupCls}>
                {(employees?.items ?? []).slice(0, 60).map((e) => (
                  <Command.Item key={e.code} value={`${e.code} ${e.title_fa} ${e.display_name ?? ''}`} onSelect={() => go(`/employees/${e.code}`)} className={itemCls}>
                    <span className="text-sec"><Icon name="agent" size={18} /></span><span className="flex-1 truncate">{e.title_fa}</span><span className="fig text-[12px] text-muted">{e.code}</span>
                  </Command.Item>
                ))}
              </Command.Group>
              <Command.Group heading="نما" className={groupCls}>
                <Command.Item value="theme night شب" onSelect={() => { setTheme('night'); onOpenChange(false); }} className={itemCls}><Icon name="sleeping" size={18} />تم شب</Command.Item>
                <Command.Item value="theme day روز" onSelect={() => { setTheme('day'); onOpenChange(false); }} className={itemCls}><Icon name="time" size={18} />تم روز</Command.Item>
              </Command.Group>
            </Command.List>
          </Command>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}

export function useCommandPalette() {
  const [open, setOpen] = useState(false);
  return { open, setOpen };
}
