'use client';

import { PageHeader } from '@/components/ui/primitives';
import { AllJourneys } from '@/components/v33/journey';

/** ⟨1.15⟩ §33.8: every company's journey on one timeline. */
export default function Page() {
  return (
    <>
      <PageHeader eyebrow="از تأسیس تا اولین فروش و سربه‌سر" title="سفر شرکت‌ها" />
      <AllJourneys />
    </>
  );
}
