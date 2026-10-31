'use client';

// ⟨1.10⟩ §28.1 the owner's clean-up of outputs: a checkbox on every row (shift-click takes the range, one box takes all), a bar that
// follows the list with what can be done to the chosen ones — file in the archive, mark seen, or delete for good behind the passkey and
// a plain confirmation — and the same three on one output's own page.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button, IconButton } from '@/components/ui/button';
import { Dialog } from '@/components/ui/overlay';
import { useToast } from '@/components/ui/toast';
import { Consequences } from '@/components/v21/bits';
import { ApiError } from '@/lib/api/client';
import { notServed, useBulkOutputs, useServed } from '@/lib/api/v28';
import { cx } from '@/lib/format';

const fa = (n: number) => n.toLocaleString('fa-IR');

/** The chosen refs, in the order of [order]; a shift-click takes every row between the last one touched and this one. */
export function useSelection(order: string[]) {
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const anchor = useRef<string | null>(null);
  // Only what is in the list counts: a row that left it (another tab, a filter, a delete) is not acted on.
  const chosen = useMemo(() => order.filter((r) => picked.has(r)), [order, picked]);
  const toggle = useCallback((ref: string, range: boolean) => {
    // Read the anchor now: the updater runs later, after it has moved to this row.
    const a = anchor.current ? order.indexOf(anchor.current) : -1;
    const b = order.indexOf(ref);
    setPicked((s) => {
      const next = new Set(s);
      const on = !s.has(ref);
      if (range && a >= 0 && b >= 0) { for (const r of order.slice(Math.min(a, b), Math.max(a, b) + 1)) if (on) next.add(r); else next.delete(r); }
      else if (on) next.add(ref); else next.delete(ref);
      return next;
    });
    anchor.current = ref;
  }, [order]);
  const all = order.length > 0 && chosen.length === order.length;
  const some = chosen.length > 0 && !all;
  const toggleAll = useCallback(() => { setPicked(all ? new Set() : new Set(order)); anchor.current = null; }, [all, order]);
  const clear = useCallback(() => { setPicked(new Set()); anchor.current = null; }, []);
  return { chosen, has: (r: string) => picked.has(r), toggle, all, some, toggleAll, clear };
}

/** A row's box: a click adds or removes it; with shift held, the whole range since the last one touched. */
export function RowCheck({ on, label, onToggle }: { on: boolean; label: string; onToggle: (range: boolean) => void }) {
  // The click that changes the box knows whether shift was held; the change event that follows does not always say.
  const shift = useRef(false);
  return (
    <label className="-m-1 flex size-9 flex-none cursor-pointer items-center justify-center self-start rounded-[8px] hover:bg-hover" onClick={(e) => e.stopPropagation()}>
      <input
        type="checkbox" checked={on} aria-label={label} className="size-[18px] cursor-pointer accent-[var(--hq-gold-ink)]"
        onClick={(e) => { shift.current = e.shiftKey; }}
        onChange={() => { onToggle(shift.current); shift.current = false; }}
      />
    </label>
  );
}

/** «همه» above the list: on, off, or partly (indeterminate). */
export function SelectAll({ all, some, count, onToggle }: { all: boolean; some: boolean; count: number; onToggle: () => void }) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => { if (ref.current) ref.current.indeterminate = some; }, [some]);
  return (
    <label className="flex cursor-pointer items-center gap-2 rounded-[8px] px-1 py-1 text-[12px] text-sec hover:text-ink">
      <input ref={ref} type="checkbox" checked={all} onChange={onToggle} aria-label="انتخاب همه‌ی خروجی‌های فهرست" className="size-[18px] cursor-pointer accent-[var(--hq-gold-ink)]" />
      {all ? 'همه انتخاب شد' : `انتخاب همه (${fa(count)})`}
    </label>
  );
}

/** File, mark seen and delete for good: the three things the owner does with outputs, with their messages. */
export function useCleanup(onGone?: (refs: string[]) => void) {
  const bulk = useBulkOutputs();
  const toast = useToast();
  const err = (e: unknown, fallback: string) => toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : e instanceof Error && e.message ? e.message : fallback });
  const file = async (refs: string[]): Promise<boolean> => {
    try {
      const out = await bulk.file.mutateAsync(refs);
      const one = out.length === 1 ? out[0] : null;
      toast({ tone: 'ok', text: one ? <>در بایگانی ثبت شد: <span className="fig">{one.record}</span>؛ پیش‌نویس است تا بایگان کاملش کند.</> : `${fa(out.length)} خروجی در بایگانی ثبت شد؛ هر کدام سند خودش را دارد.` });
      return true;
    } catch (e) {
      if (notServed(e)) toast({ tone: 'info', text: 'بایگانی خروجی با به‌روزرسانی هاب فعال میشود.' }); else err(e, 'بایگانی نشد.');
      return false;
    }
  };
  const remove = async (refs: string[]): Promise<boolean> => {
    try {
      const n = await bulk.remove.mutateAsync(refs);
      // A hub before §28 does not delete outputs: the action is hidden from now on, quietly.
      if (n === null) return true;
      toast({ tone: 'ok', text: n === 1 ? 'برای همیشه پاک شد؛ یک خط در دفتر Audit ماند.' : `${fa(n)} خروجی برای همیشه پاک شد؛ از هر کدام یک خط در دفتر Audit ماند.` });
      onGone?.(refs);
      return true;
    } catch (e) {
      if (notServed(e)) toast({ tone: 'info', text: 'حذف خروجی با به‌روزرسانی هاب فعال میشود.' }); else err(e, 'پاک نشد.');
      return false;
    }
  };
  return { file, remove, filing: bulk.file.isPending, removing: bulk.remove.isPending };
}

/** The plain confirmation before a delete that cannot be undone. */
export function DeleteDialog({ open, onOpenChange, count, filed, busy, onConfirm }: {
  open: boolean; onOpenChange: (v: boolean) => void; count: number; filed: number; busy: boolean; onConfirm: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={count === 1 ? 'این خروجی برای همیشه پاک شود؟' : `${fa(count)} خروجی برای همیشه پاک شود؟`}
      actions={<>
        <Button variant="danger" icon="reject" loading={busy} onClick={onConfirm}>حذف برای همیشه</Button>
        <Button variant="ghost" onClick={() => onOpenChange(false)}>انصراف</Button>
      </>}>
      <div className="flex flex-col gap-3">
        <p className="font-semibold text-ink">از دیتابیس پاک میشود و برنمیگردد؛ فقط یک خط در دفتر Audit میماند.</p>
        <Consequences tone="neg" lines={[
          ['reject', 'متن، فایل‌ها و امتیازش از دیتابیس و انبار فایل پاک میشود؛ ایجنت‌ها و جستجو دیگر آن را نمیبینند.'],
          ['report', 'در دفتر Audit فقط شناسه، عنوان، شرکت، تو و زمان حذف میماند.'],
          ...(filed ? [['deliverable', filed === count ? 'سند بایگانی‌اش میماند؛ بایگانی سابقه‌ی رسمی توست.' : `سند بایگانیِ ${fa(filed)} خروجیِ بایگانی‌شده میماند.`] as ['deliverable', string]] : []),
          ['lock', 'با اثر انگشت یا چهره تأیید میشود، فقط برای همین مجموعه.'],
        ]} />
      </div>
    </Dialog>
  );
}

/** The bar under the list while something is chosen: how many, and the three actions. */
export function SelectionBar({ count, filed, onFile, onSeen, onDelete, onClear, busy }: {
  count: number; filed: number; onFile: () => void; onSeen: () => void; onDelete: () => void; onClear: () => void; busy: { file: boolean; seen: boolean };
}) {
  const canDelete = useServed('delete');
  if (!count) return null;
  return (
    <div role="toolbar" aria-label="کار با خروجی‌های انتخاب‌شده"
      className={cx('hq-rise sticky bottom-[5.5rem] z-20 flex flex-wrap items-center gap-2 rounded-[14px] bg-raised p-2 shadow-[0_12px_32px_rgba(0,0,0,.35)] ring-1 ring-[var(--hq-line-tahrir)] md:bottom-3 lg:bottom-0')}>
      <IconButton icon="close" label="لغو انتخاب" size={32} onClick={onClear} />
      <span className="flex-1 text-[13px] font-semibold text-ink" aria-live="polite">{fa(count)} انتخاب‌شده</span>
      <Button variant="secondary" size="sm" icon="deliverable" loading={busy.file} disabled={filed === count} onClick={onFile}>بایگانی</Button>
      <Button variant="secondary" size="sm" icon="seal" loading={busy.seen} onClick={onSeen}>خوانده‌شده</Button>
      {canDelete ? <Button variant="danger" size="sm" icon="reject" onClick={onDelete}>حذف برای همیشه</Button> : null}
    </div>
  );
}

/** One output's own page: the same delete, under its other actions. */
export function DeleteOne({ refId, filed, onGone }: { refId: string; filed: boolean; onGone: () => void }) {
  const [open, setOpen] = useState(false);
  const c = useCleanup(() => onGone());
  const served = useServed('delete');
  if (!served && !open) return null;
  return (
    <>
      <Button variant="danger" size="sm" icon="reject" onClick={() => setOpen(true)}>حذف برای همیشه</Button>
      <DeleteDialog open={open} onOpenChange={setOpen} count={1} filed={filed ? 1 : 0} busy={c.removing} onConfirm={async () => { if (await c.remove([refId])) setOpen(false); }} />
    </>
  );
}
