'use client';

import { use } from 'react';
import { PlaybookPage } from '@/components/v40/playbook';

/** ⟨1.22⟩ §40.2–§40.3: one playbook. */
export default function PlaybookRoute({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = use(params);
  return <PlaybookPage refId={decodeURIComponent(ref)} />;
}
