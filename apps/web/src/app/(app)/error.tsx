'use client';

import { ErrorState } from '@/components/ui/primitives';

export default function AppError({ error, reset }: { error: Error; reset: () => void }) {
  return <ErrorState error={{ messageFa: 'این بخش با خطا روبه‌رو شد.', code: error.name }} onRetry={reset} />;
}
