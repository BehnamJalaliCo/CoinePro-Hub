'use client';

import { Icon } from '@/components/icon';
import { Card, ErrorState, PageHeader, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { ActiveVoice, BlindTest, ReferenceCard, VoiceRegistry } from '@/components/v19/voice';
import { useVoices } from '@/lib/api/v19';

const RULES: Array<[string, string]> = [
  ['بی پرداخت به سرویس صدا', 'صدا روی خود هاب ساخته میشود، با مدل متن‌باز؛ همان موتوری که گزارش صوتی صبح را میخواند.'],
  ['انتخاب با گوش تو', 'هر نامزد همان متن‌های فارسی را میخواند (عدد، اصطلاح لاتین، کلمه‌ی کریپتو، جمله‌ی بلند)؛ سرور RTF و حافظه را اندازه میگیرد و تو کور نمره میدهی.'],
  ['لایسنس روی هر استفاده', 'صدای غیرتجاری بی‌انتخاب صریح تو فعال نمیشود و برچسبش همه‌جا دیده میشود.'],
  ['صدای خودت فقط روی هاب', 'نمونه‌ی ضبط‌شده‌ات مثل هر فایل تو نگه داشته میشود و هیچ‌جا فرستاده نمیشود.'],
];

/** صدای هاب (contract §22.3): the active voice, the owner's choice, the owner's own recorded voice, the blind listening test and the registry. */
export default function VoicePage() {
  const q = useVoices();
  const voices = q.data ?? [];
  return (
    <>
      <PageHeader eyebrow="متن‌باز، روی خود هاب، انتخاب با گوش تو" title="صدای هاب">
        <p className="max-w-3xl text-[13px] leading-6 text-sec">برای ریلزها، استوری‌های صدادار و گزارش‌های صوتی. هیچ سرویس پولی صدا نیست؛ نامزدها روی CPU هاب اندازه گرفته میشوند و تو بی‌دیدن نام، با گوش انتخاب میکنی.</p>
      </PageHeader>
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isLoading ? <Skeleton className="h-96 rounded-[16px]" /> : (
        <>
          <ActiveVoice voices={voices} />
          <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
            <div className="flex min-w-0 flex-col gap-4">
              <BlindTest voices={voices} />
              <VoiceRegistry voices={voices} />
            </div>
            <div className="flex min-w-0 flex-col gap-4">
              <ReferenceCard />
              <Card className="flex flex-col gap-3 p-4">
                <SectionTitle title="قاعده‌ی صدا" note="هیچ استثنایی ندارد" />
                <ul className="flex flex-col gap-2">
                  {RULES.map(([t, b]) => (
                    <li key={t} className="flex items-start gap-2.5 rounded-[12px] bg-tile p-3">
                      <span className="mt-0.5 text-gold-ink"><Icon name="mic" size={16} /></span>
                      <span className="flex flex-col gap-0.5"><span className="text-[13px] font-semibold text-ink">{t}</span><span className="text-[12px] leading-5 text-sec">{b}</span></span>
                    </li>
                  ))}
                </ul>
              </Card>
            </div>
          </div>
        </>
      )}
    </>
  );
}
