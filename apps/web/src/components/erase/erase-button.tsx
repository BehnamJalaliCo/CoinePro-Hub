'use client';

// ⟨1.19⟩ §37 «پاک کردن برای همیشه»: a button that opens a dialog with what would go (the preview) and what stays, then the passkey and the
// erase. Shared by the session page and its archive rows, an output's detail and an archive record's detail.

import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Dialog } from '@/components/ui/overlay';
import { Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { errText } from '@/components/v31/kit';
import { COUNT_FA, eraseNow, useErasePreview, type EraseKind } from '@/lib/api/v37';

const fa = (n: number) => n.toLocaleString('fa-IR');

export function EraseDialog({ kind, refId, open, onOpenChange, onGone }: { kind: EraseKind; refId: string; open: boolean; onOpenChange: (v: boolean) => void; onGone: () => void }) {
  const toast = useToast();
  const qc = useQueryClient();
  const q = useErasePreview(kind, refId, open);
  const [busy, setBusy] = useState(false);
  const p = q.data;
  const counts = Object.entries(p?.counts ?? {}).filter(([, n]) => n > 0);
  const run = async () => {
    setBusy(true);
    try {
      await eraseNow(kind, refId);
      toast({ tone: 'ok', text: 'پاک شد.' });
      onOpenChange(false);
      // What belonged to it is dropped, not refetched (it would answer 404); every list is looked at again.
      qc.removeQueries({ predicate: (q) => q.queryKey.some((k) => k === refId || (typeof k === 'string' && k.includes(refId))) });
      onGone();
      void qc.invalidateQueries();
    } catch (e) {
      toast({ tone: 'error', text: errText(e, 'پاک نشد؛ دوباره بزن.') });
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog
      open={open} onOpenChange={(v) => { if (!busy) onOpenChange(v); }} title="پاک کردن برای همیشه"
      actions={(
        <>
          <Button variant="danger" icon="seal" loading={busy} disabled={!p} onClick={() => void run()}>پاکش کن (با اثر انگشت)</Button>
          <Button variant="ghost" disabled={busy} onClick={() => onOpenChange(false)}>نه، بماند</Button>
        </>
      )}
    >
      {q.isLoading ? <Skeleton className="h-20 rounded-[12px]" /> : q.error ? <p role="alert">{errText(q.error, 'پیش‌نمایش نیامد؛ دوباره بزن.')}</p> : p ? (
        <div className="flex flex-col gap-3" aria-label="پیش‌نمایش پاک کردن">
          <p className="font-semibold text-ink">«{p.title_fa}» برای همیشه پاک میشود و برنمیگردد.</p>
          {counts.length ? <ul className="flex flex-wrap gap-2">{counts.map(([k, n]) => <li key={k} className="rounded-full bg-tile px-3 py-1 text-[12px]"><span>{fa(n)}</span> {COUNT_FA[k] ?? k}</li>)}</ul> : null}
          {p.keeps_fa.length ? (
            <div>
              <span className="text-[12px] font-semibold text-gold-ink">آنچه میماند</span>
              <ul className="mt-1 flex list-disc flex-col gap-1 ps-5 text-[13px] leading-6">{p.keeps_fa.map((l) => <li key={l}>{l}</li>)}</ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </Dialog>
  );
}

export function EraseButton({ kind, refId, onGone, variant = 'danger', size = 'sm', label = 'پاک کردن برای همیشه' }: { kind: EraseKind; refId: string; onGone: () => void; variant?: 'danger' | 'ghost' | 'secondary' | 'text'; size?: 'sm' | 'md'; label?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button variant={variant} size={size} icon="reject" onClick={() => setOpen(true)}>{label}</Button>
      {open ? <EraseDialog kind={kind} refId={refId} open={open} onOpenChange={setOpen} onGone={onGone} /> : null}
    </>
  );
}
