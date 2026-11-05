'use client';

import { PageHeader } from '@/components/ui/primitives';
import { UsageView } from '@/components/v33/usage';

/** ⟨1.15⟩ §33.1: the advisor's usage reports. */
export default function Page() {
  return (
    <>
      <PageHeader eyebrow="عددها با کد، حرف‌ها با مشاور" title="مصرف" />
      <UsageView />
    </>
  );
}
