'use client';

import { use } from 'react';
import { RunView } from '@/components/v30/runs';

/** ⟨1.12⟩ §30.3: one run of a line. */
export default function LineRunPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = use(params);
  return <RunView runRef={decodeURIComponent(ref)} />;
}
