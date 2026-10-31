'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import * as Tooltip from '@radix-ui/react-tooltip';
import { setNonce } from 'get-nonce';
import { ToastProvider } from './ui/toast';
import { ApiError } from '@/lib/api/client';
import { backoff, hubHealth, isTransientStatus } from '@/lib/hub-health';

/**
 * The page's CSP nonce for the styles the dialog, sheet, popover and menu libraries inject (react-remove-scroll's scroll lock and its
 * scrollbar compensation, through get-nonce): production allows inline <style> only with the nonce. Set during render, before any of them
 * mounts; on the server it is a no-op.
 */
function useStyleNonce(nonce: string | undefined) {
  const [done] = useState(() => { if (nonce && typeof document !== 'undefined') setNonce(nonce); return true; });
  return done;
}

export function Providers({ children, nonce }: { children: ReactNode; nonce?: string }) {
  useStyleNonce(nonce);
  const [qc] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 15_000,
            refetchOnWindowFocus: true,
            // 0.4.0: a read that met a 502/503/504 or no answer is tried again quietly; while the hub restarts (four of them in fifteen
            // seconds) it keeps waiting with a growing pause, so pages keep what they had instead of an error on every card.
            retry: (n, e) => {
              if (e instanceof ApiError && isTransientStatus(e.status)) return hubHealth.outage || n < 3;
              return !(e instanceof ApiError && e.status >= 400 && e.status < 500) && n < 2;
            },
            retryDelay: (n, e) => (e instanceof ApiError && isTransientStatus(e.status) ? backoff(n) : Math.min(1000 * 2 ** n, 8000)),
          },
        },
      }),
  );
  return (
    <QueryClientProvider client={qc}>
      <Tooltip.Provider delayDuration={400}>
        <ToastProvider>{children}</ToastProvider>
      </Tooltip.Provider>
    </QueryClientProvider>
  );
}
