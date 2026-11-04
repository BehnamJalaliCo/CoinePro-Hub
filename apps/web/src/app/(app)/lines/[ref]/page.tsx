'use client';

import { use } from 'react';
import { LineView } from '@/components/v30/lines';

/** ⟨1.12⟩ §30: one production line. */
export default function LinePage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = use(params);
  return <LineView lineRef={decodeURIComponent(ref)} />;
}
