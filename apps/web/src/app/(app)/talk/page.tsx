'use client';

import { PageHeader } from '@/components/ui/primitives';
import { Talk } from '@/components/v32/talk';

/** ⟨1.14⟩ §32: the owner's conversation with the holding, by voice or text. */
export default function Page() {
  return (
    <>
      <PageHeader eyebrow="حرف بزن؛ کار فقط با کارتی که تو میزنی ساخته میشود" title="گفتگو" />
      <Talk />
    </>
  );
}
