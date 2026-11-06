'use client';

import { use } from 'react';
import { SessionView } from '@/components/session/session-view';

/** ⟨1.17⟩ §35: one order as a live session. */
export default function SessionPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = use(params);
  return <SessionView refId={decodeURIComponent(ref)} />;
}
