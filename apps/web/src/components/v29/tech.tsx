'use client';

// ⟨1.11⟩ «شرکت ← فنی» (contract §29.1): where the technical lives now. The company's technical findings and notifications (tech, infra,
// security; `?scope=all&domain=…&company=…`), each with who handles it (the company's CTO or SRE, the holding's security analyst), its
// servers and its full catalogue, and the ways to the network map, the watch, the error reader and the code workshop. None of it is on
// the owner's home or in his regular notifications any more; only the critical few still reach him.

import Link from 'next/link';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { SeverityPill } from '@/components/v14/bits';
import { CompanyServers } from '@/components/v26/company';
import { CompanyCatalogue } from '@/components/v28/catalogue';
import { Md } from '@/components/ui/md';
import { Card, Empty, ErrorState, Pill, SectionTitle, Segmented, Skeleton } from '@/components/ui/primitives';
import type { IconName } from '@/generated/icons';
import { useEmployees } from '@/lib/api/hooks';
import { CRITICAL_FA, DOMAIN_FA, useTechFindings, useTechNotifications, type Domain } from '@/lib/api/v29';
import { isOpenFinding, useServed } from '@/lib/api/v28';
import { linkRoute } from '@/lib/refs';
import { useNow } from '@/lib/store';
import { ago, cx } from '@/lib/format';
import { FaText } from './text';

export type TechTab = 'findings' | 'servers' | 'catalogue';

const LINKS: Array<{ href: string; label: string; icon: IconName }> = [
  { href: '/network', label: 'شبکه‌ی هلدینگ', icon: 'globe' },
  { href: '/watch', label: 'دیده‌بان', icon: 'scope' },
  { href: '/errors', label: 'خطاخوان', icon: 'urgent' },
  { href: '/workshop', label: 'کارگاه کد', icon: 'code' },
  { href: '/sites', label: 'پایش سایت‌ها', icon: 'server' },
];

function useWho() {
  const { data } = useEmployees({});
  return (code: string | null | undefined) => (code ? data?.items.find((e) => e.code === code)?.title_fa ?? code : null);
}

function Findings({ code }: { code: string }) {
  const q = useTechFindings(code);
  const who = useWho();
  const now = useNow();
  const open = (q.data ?? []).filter(isOpenFinding);
  return (
    <Card className="flex flex-col gap-2 p-5" aria-label="یافته‌های فنی">
      <SectionTitle title="یافته‌های فنی" note="فنی، زیرساخت و امنیت؛ هر کدام دست مدیر فنی همین شرکت" action={<Link href="/oversight" className="text-[12px] font-semibold text-gold-ink hover:underline">ناظر کل</Link>} />
      {q.isLoading ? <Skeleton className="h-32" /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !open.length ? <Empty icon="seal" title="یافته‌ی فنی بازی نیست" /> : (
        <ul className="flex flex-col">
          {open.map((f) => (
            <li key={f.ref} className="flex flex-col gap-1.5 border-t border-div py-3 first:border-0">
              <span className="flex flex-wrap items-center gap-2">
                <SeverityPill s={f.severity} />
                {f.domain ? <Pill tone="neutral">{DOMAIN_FA[f.domain as Domain] ?? f.domain}</Pill> : null}
                {f.critical_reason ? <Pill tone="neg" dot>{CRITICAL_FA[f.critical_reason] ?? 'بحرانی'}</Pill> : null}
                <span className="flex-1" />
                <span className="text-[11px] text-muted">{now ? ago(f.opened_at, now) : ''}</span>
              </span>
              <span className="text-[14px] font-semibold"><FaText text={f.title_fa} /></span>
              {f.body_md ? <div className="hq-prose text-[13px] text-sec"><Md text={f.body_md} /></div> : null}
              {f.routed_to ? <span className="flex items-center gap-1.5 text-[12px] text-sec"><Icon name="delegate" size={14} />در دست: {who(f.routed_to)}</span> : null}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Notifications({ code }: { code: string }) {
  const q = useTechNotifications(code);
  const now = useNow();
  const list = q.data ?? [];
  return (
    <Card className="flex flex-col gap-2 p-5" aria-label="اعلان‌های فنی">
      <SectionTitle title="اعلان‌های فنی" note="آنچه دیگر به اعلان‌های عادی تو نمیاید" />
      {q.isLoading ? <Skeleton className="h-28" /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !list.length ? <Empty icon="bell" title="اعلان فنی‌ای نیست" /> : (
        <ul className="flex flex-col">
          {list.map((n) => {
            const href = linkRoute(n.link?.kind, n.link?.ref);
            const body = (
              <>
                <span className="flex flex-wrap items-center gap-2">
                  {n.domain ? <Pill tone="neutral">{DOMAIN_FA[n.domain as Domain] ?? n.domain}</Pill> : null}
                  {n.owner_visible ? <Pill tone="neg" dot>{n.critical_reason ? CRITICAL_FA[n.critical_reason] : 'به تو هم رسید'}</Pill> : null}
                  <span className="flex-1" />
                  <span className="text-[11px] text-muted">{now ? ago(n.created_at, now) : ''}</span>
                </span>
                <span className="text-[13px] font-semibold"><FaText text={n.title_fa} /></span>
                <span className="text-[12px] leading-5 text-sec"><FaText text={n.body_fa} /></span>
              </>
            );
            return (
              <li key={n.id} className="border-t border-div first:border-0">
                {href ? <Link href={href} className="flex flex-col gap-1 py-3 hover:bg-hover/40">{body}</Link> : <div className="flex flex-col gap-1 py-3">{body}</div>}
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

/** The company's technical tab, with its own parts. */
export function CompanyTech({ code, nameFa, holding, tab, onTab }: { code: string; nameFa: string; holding: boolean; tab: TechTab; onTab: (t: TechTab) => void }) {
  const catalogueServed = useServed('catalogue');
  const shown: TechTab = holding ? 'findings' : tab === 'catalogue' && !catalogueServed ? 'findings' : tab;
  return (
    <div className="flex flex-col gap-4">
      {!holding ? (
        <div className="no-scrollbar max-w-xl overflow-x-auto">
          <Segmented label="بخش فنی" value={shown} onChange={onTab}
            options={[{ value: 'findings', label: 'یافته‌ها و اعلان‌ها' }, { value: 'servers', label: 'سرورها' }, ...(catalogueServed ? [{ value: 'catalogue' as const, label: 'کاتالوگ کامل' }] : [])]} />
        </div>
      ) : null}
      {shown === 'servers' ? <CompanyServers code={code} /> : shown === 'catalogue' ? <CompanyCatalogue code={code} nameFa={nameFa} /> : (
        <div className="grid items-start gap-4 xl:grid-cols-2">
          <Findings code={code} />
          <Notifications code={code} />
        </div>
      )}
      <nav aria-label="جاهای فنی دیگر" className="flex flex-wrap gap-2">
        {LINKS.map((l) => (
          <Link key={l.href} href={l.href} className={cx('inline-flex h-9 items-center gap-1.5 rounded-full border border-strong px-3 text-[12px] text-sec hover:bg-hover hover:text-ink')}>
            <Icon name={l.icon} size={15} />{l.label}
          </Link>
        ))}
        <span className="inline-flex h-9 items-center gap-1.5 px-1 text-[11px] text-muted"><CompanyMark code={code} height={11} mono />فقط کارهای فنی؛ تصمیم‌های کسب‌وکاری در خانه میمانند.</span>
      </nav>
    </div>
  );
}
