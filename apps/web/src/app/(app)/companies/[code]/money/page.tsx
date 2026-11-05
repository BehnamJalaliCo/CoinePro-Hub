'use client';

import { use } from 'react';
import { CompanyHead } from '@/components/v33/bits';
import { CompanyMoney } from '@/components/v33/money';

/** ⟨1.15⟩ §33.2–§33.3: the company's revenue board, payments (ledger against chain), reconcile by day and payment sources. */
export default function Page({ params }: { params: Promise<{ code: string }> }) {
  const { code } = use(params);
  return (
    <>
      <CompanyHead code={code} here="money" title="پول" note="درآمد از پرداخت‌های واقعی مشتری‌ها. ستاد فقط میخواند و تطبیق میدهد؛ هیچ پولی را جابه‌جا، تأیید یا رد نمیکند." />
      <CompanyMoney code={code} />
    </>
  );
}
