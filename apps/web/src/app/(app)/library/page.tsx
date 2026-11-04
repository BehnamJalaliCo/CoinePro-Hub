'use client';

import { PageHeader } from '@/components/ui/primitives';
import { Library } from '@/components/v30/library';

/** ⟨1.12⟩ §30.5: covers, voices, prompts and patterns the lines use. */
export default function LibraryPage() {
  return (
    <>
      <PageHeader eyebrow="پوشه‌ی کاورها، صداها، پرامپت‌ها و الگوها" title="کتابخانه‌ی تولید" />
      <Library />
    </>
  );
}
