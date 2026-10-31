'use client';

import { PageHeader } from '@/components/ui/primitives';
import { WatchBoard } from '@/components/v28/watch';

/** ⟨1.10⟩ §28.3 دیده‌بان: what the overseer, the advisor and the digital CEO found watching the apps, the hub and every company. */
export default function WatchPage() {
  return (
    <>
      <PageHeader eyebrow="ناظر کل، مشاور کل و مدیر کل دیجیتال؛ بی‌وقفه روی اپ‌ها، هاب و هر شرکت" title="دیده‌بان" />
      <WatchBoard />
    </>
  );
}
