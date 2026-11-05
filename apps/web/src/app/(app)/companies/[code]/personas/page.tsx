'use client';

import { use } from 'react';
import { CompanyHead } from '@/components/v33/bits';
import { CompanyPersonas } from '@/components/v33/personas';

/** ⟨1.15⟩ §33.9: the company's personas and the message test. */
export default function Page({ params }: { params: Promise<{ code: string }> }) {
  const { code } = use(params);
  return (
    <>
      <CompanyHead code={code} here="personas" title="پرسونا" note="مخاطب‌های شرکت و آزمون پیام پیش از انتشار. نمره‌ها نظر مدل است، نه اندازه‌گیری." />
      <CompanyPersonas code={code} />
    </>
  );
}
