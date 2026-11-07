'use client';

import { PageHeader } from '@/components/ui/primitives';
import { PlaybookLibrary } from '@/components/v40/playbook';

/** ⟨1.22⟩ §40: every playbook, a working group made from a session that the owner can give to any company or platform. */
export default function PlaybooksPage() {
  return (
    <>
      <PageHeader eyebrow="نتیجه‌ی جلسه‌ها، آماده‌ی دادن به هر شرکت و پلتفرم" title="کارگروه‌های آماده" />
      <PlaybookLibrary />
    </>
  );
}
