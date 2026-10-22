'use client';

import { use } from 'react';
import { RecordView } from '@/components/v20/record';

/** A record of the archive (contract §23.1): metadata by its class, files and versions, links, holds, the seal and the access log. */
export default function RecordPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = use(params);
  return <RecordView key={ref} refId={decodeURIComponent(ref)} />;
}
