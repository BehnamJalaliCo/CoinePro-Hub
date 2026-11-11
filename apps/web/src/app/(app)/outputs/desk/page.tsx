'use client';

import { OutputsTabs, PublishDeskView } from '@/components/look/desk';
import { PageHeader } from '@/components/ui/primitives';

/** ⟨1.0.1⟩ Part C, «میز انتشار» (C2.3; contract §55.2): everything that can go out, is set to go out, or went out, on one page. */
export default function PublishDeskPage() {
  return (
    <>
      <PageHeader eyebrow="هر خروجی آماده، یک جا" title="میز انتشار">
        <OutputsTabs />
      </PageHeader>
      <PublishDeskView />
    </>
  );
}
