'use client';

import { useSearchParams } from 'next/navigation';
import { Suspense } from 'react';
import { Icon } from '@/components/icon';
import { Card, ErrorState, PageHeader, SectionTitle } from '@/components/ui/primitives';
import { CreativesCard } from '@/components/v18/creatives';
import { PlayerCard, PlayersSkeleton } from '@/components/v18/substitutes';
import { useSubstitutes } from '@/lib/api/v18';

const RULES: Array<[string, string]> = [
  ['Claude صاحب پروژه است', 'کد، تصمیم، رأی، یافته، متن مشتری، هر کار A2 به بالا و هر خروجی نهایی با ایجنت Claude مسئول میماند.'],
  ['یک سؤال محدود', 'بازیکن ذخیره رشته‌ی پیام، حافظه و مسیر نوشتن ندارد؛ با مشتری حرف نمیزند و چیزی منتشر نمیکند.'],
  ['ورودی ماسک‌شده', 'هیچ داده یا گفت‌وگوی مشتری، رمز یا فایل شرکت دیگر؛ کد فقط در بازبینی کد، از checkout فقط‌خواندنی.'],
  ['خروجی برچسب‌دار، نه شاهد', 'هر جواب منبعش را دارد و با لوگوی ارائه‌دهنده دیده میشود؛ هیچ یافته یا ادعایی فقط با حرف او بسته یا رد نمیشود.'],
  ['هیچ جابه‌جایی پنهانی', 'بازیکن محدود، خارج‌شده یا خاموش، جایگاهش رد میشود و صداکننده با مدل خودش ادامه میدهد؛ اجرای Claude هیچ‌وقت به بازیکن ذخیره نمیرود.'],
  ['سقف خودش', 'از سقف روزانه‌ی توکن ایجنت‌ها کم نمیکند؛ اشتراک و سقف روزانه‌ی هر جایگاه محدودش میکنند و خزانه با هزینه‌ی معادل ثبتش میکند.'],
];

function SubstitutesInner() {
  const params = useSearchParams();
  const q = useSubstitutes();
  const xs = q.data ?? [];
  return (
    <>
      <PageHeader eyebrow="Claude کل پروژه را در دست دارد؛ این‌ها برای یک کار محدود به زمین میآیند" title="بازیکن‌های ذخیره">
        <p className="max-w-3xl text-[13px] leading-6 text-sec">ChatGPT Plus و Google AI Pro را میپردازی، پس باید در طول ماه کار کنند: مدل‌های کدنویسی‌شان از CLI برای بررسی، نظر دوم، پیش‌نویس و خواندن سند بلند، و چت و ساخت عکس و ویدیو از مرورگر لاگین‌شده‌ی هاب برای تبلیغات. DeepSeek رایگان، فقط از مرورگر، برای جستجوی سریع و نظر سوم.</p>
      </PageHeader>
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isLoading ? <PlayersSkeleton /> : (
        <div className="grid items-start gap-4 lg:grid-cols-2 2xl:grid-cols-3">{xs.map((s) => <PlayerCard key={s.player} s={s} />)}</div>
      )}
      <CreativesCard initial={params.get('creative')} />
      <Card className="flex flex-col gap-3 p-4">
        <SectionTitle title="قاعده‌ی نیمکت" note="هیچ استثنایی ندارد" />
        <ul className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
          {RULES.map(([t, b]) => (
            <li key={t} className="flex items-start gap-2.5 rounded-[12px] bg-tile p-3">
              <span className="mt-0.5 text-gold-ink"><Icon name="lock" size={16} /></span>
              <span className="flex flex-col gap-0.5"><span className="text-[13px] font-semibold text-ink">{t}</span><span className="text-[12px] leading-5 text-sec">{b}</span></span>
            </li>
          ))}
        </ul>
      </Card>
    </>
  );
}

/** بازیکن‌های ذخیره (contract §21.13): GPT, Gemini and DeepSeek, their sign-ins, seats and month, and the creatives they render. */
export default function SubstitutesPage() {
  return <Suspense><SubstitutesInner /></Suspense>;
}
