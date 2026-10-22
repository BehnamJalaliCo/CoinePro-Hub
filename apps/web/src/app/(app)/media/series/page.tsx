'use client';

import { useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Card, Empty, ErrorState, FilterChip, PageHeader, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { ScopeChips } from '@/components/v17/bits';
import { SERIES_STATUS } from '@/components/v19/bits';
import { ChannelWeek, LimitsCard, SeriesCard, SeriesEditor } from '@/components/v19/series';
import { useSeriesList, type Series, type SeriesStatus } from '@/lib/api/v19';
import { useScope } from '@/lib/scope';

const RULES: Array<[string, string]> = [
  ['مُهر روی برنامه است', 'یک بار مُهر میکنی؛ بعد هر آیتمی که همه‌ی چک‌ها را رد کند، در زمان برنامه خودکار منتشر میشود.'],
  ['ویرایش، مُهر را برمیدارد', 'برنامه‌ی مُهرشده‌ی ویرایش‌شده «منتظر مُهر» میشود؛ تا مُهر دوباره هیچ چیز خودکار نمیرود (409 series_not_sealed).'],
  ['فقط API رسمی', 'Bot API تلگرام و Graph API اینستاگرام برای حساب تجاری؛ هیچ مرورگر و هیچ کوکی. استوری کانال تلگرام API ندارد: کارت با فایل.'],
  ['هر چک ردشده، کارت', 'آیتم بیرون از برنامه، یک‌باره، یا با یک چک رد: «منتظر تو» و کارت انتشار (A3).'],
  ['دو سقف', 'سقف روزانه‌ی هر برنامه و سقف خود پلتفرم (اینستاگرام: 50 پست API در ۲۴ ساعت برای هر حساب).'],
  ['همه‌ی ترمزها', 'کلید توقف شرکت، توقف deploy، نگه‌داشتن ناظر و حالت نگهبان، انتشار را هم متوقف میکنند.'],
];
const STATUSES: Array<SeriesStatus | null> = [null, 'proposed', 'sealed', 'draft', 'paused', 'retired'];

function SeriesInner() {
  const params = useSearchParams();
  const focus = params.get('ref');
  const { company: scope } = useScope();
  const [company, setCompany] = useState<string | null>(scope);
  const [status, setStatus] = useState<SeriesStatus | null>(null);
  const [editing, setEditing] = useState<Series | 'new' | null>(null);
  const q = useSeriesList({ company });
  const all = q.data ?? [];
  const xs = (status ? all.filter((s) => s.status === status) : all).slice().sort((a, b) => Number(b.status === 'proposed') - Number(a.status === 'proposed') || a.company.localeCompare(b.company));
  useEffect(() => { if (focus && q.data) document.getElementById(focus)?.scrollIntoView({ block: 'center' }); }, [focus, q.data]);
  return (
    <>
      <PageHeader eyebrow="یک بار مُهر کن؛ بعد هر آیتمی که همه‌ی چک‌ها را رد کند خودش میرود" title="برنامه‌های انتشار"
        actions={<Button variant="primary" icon="add" onClick={() => setEditing('new')}>برنامه‌ی تازه</Button>} />
      <div className="flex flex-col gap-3">
        <ScopeChips value={company} onChange={setCompany} holding={false} allLabel="همه‌ی شرکت‌ها" />
        <div className="flex flex-wrap gap-1.5">{STATUSES.map((s) => <FilterChip key={s ?? 'all'} selected={status === s} onClick={() => setStatus(s)} count={s ? all.filter((x) => x.status === s).length : all.length}>{s ? SERIES_STATUS[s]!.fa : 'همه'}</FilterChip>)}</div>
      </div>
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : (
        <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
          <div className="flex min-w-0 flex-col gap-4">
            {q.isLoading ? <Skeleton className="h-80 rounded-[16px]" /> : !xs.length ? <Card className="p-2"><Empty icon="send" title="برنامه‌ای نیست" body="برنامه‌ی تازه بساز، یا منتظر پیشنهاد مدیر رسانه بمان." /></Card>
              : xs.map((s) => <SeriesCard key={s.ref} s={s} focus={focus === s.ref} onEdit={setEditing} />)}
          </div>
          <div className="flex min-w-0 flex-col gap-4">
            <ChannelWeek series={all} />
            <LimitsCard />
            <Card className="flex flex-col gap-3 p-4">
              <SectionTitle title="قاعده‌ی انتشار" note="هیچ استثنایی ندارد" />
              <ul className="flex flex-col gap-2">
                {RULES.map(([t, b]) => (
                  <li key={t} className="flex items-start gap-2.5 rounded-[12px] bg-tile p-3">
                    <span className="mt-0.5 text-gold-ink"><Icon name="seal" size={16} /></span>
                    <span className="flex flex-col gap-0.5"><span className="text-[13px] font-semibold text-ink">{t}</span><span className="text-[12px] leading-5 text-sec">{b}</span></span>
                  </li>
                ))}
              </ul>
            </Card>
          </div>
        </div>
      )}
      {editing ? <SeriesEditor s={editing === 'new' ? null : editing} onClose={() => setEditing(null)} onSaved={() => setEditing(null)} /> : null}
    </>
  );
}

/** برنامه‌های انتشار (contract §22.2): each company's sealed series per channel, sealed once with a passkey, and the platforms' own limits. */
export default function SeriesPage() {
  return <Suspense><SeriesInner /></Suspense>;
}
