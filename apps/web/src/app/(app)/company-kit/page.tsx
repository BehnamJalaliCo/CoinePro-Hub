'use client';

import { PageHeader } from '@/components/ui/primitives';
import { CompanyKit } from '@/components/v31/kit';

/** ⟨1.13⟩ §31.2: a ready company with one order. */
export default function Page() {
  return (
    <>
      <PageHeader eyebrow="الگو را انتخاب کن، پیش‌نمایش را ببین، مُهر بزن" title="شرکت آماده" />
      <CompanyKit />
    </>
  );
}
