'use client';

import { use } from 'react';
import { CompanyHead } from '@/components/v33/bits';
import { CompanySales } from '@/components/v33/sales';

/** ⟨1.15⟩ §33.4: the company's small CRM — pipeline, leads, one lead with its follow-up draft. */
export default function Page({ params }: { params: Promise<{ code: string }> }) {
  const { code } = use(params);
  return (
    <>
      <CompanyHead code={code} here="sales" title="فروش" note="سرنخ‌ها از پشتیبانی، تلگرام و پرداخت‌ها میرسند. پیش‌نویس پیگیری فقط نشان داده میشود و از این‌جا چیزی فرستاده نمیشود." />
      <CompanySales code={code} />
    </>
  );
}
