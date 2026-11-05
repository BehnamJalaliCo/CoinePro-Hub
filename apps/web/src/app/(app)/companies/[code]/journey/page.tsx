'use client';

import { use } from 'react';
import { CompanyHead } from '@/components/v33/bits';
import { CompanyJourney } from '@/components/v33/journey';

/** ⟨1.15⟩ §33.8: the company's journey from founding to break-even. */
export default function Page({ params }: { params: Promise<{ code: string }> }) {
  const { code } = use(params);
  return (
    <>
      <CompanyHead code={code} here="journey" title="سفر شرکت" note="هر مرحله وقتی میرسد که ردیف‌هایش در سامانه باشد، نه با اعلام ایجنت." />
      <CompanyJourney code={code} />
    </>
  );
}
