'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Dialog, Sheet } from '@/components/ui/overlay';
import { FilterChip } from '@/components/ui/primitives';
import { PriorityPicker } from '@/components/v21/priority';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { useWorkAction, type EvidenceIn } from '@/lib/api/v15';

const field = 'w-full rounded-[10px] border border-strong bg-tile px-3 text-[15px] text-ink outline-none focus:border-gold-ink';
const KINDS: Array<{ id: EvidenceIn['kind']; fa: string; hint: string }> = [
  { id: 'deliverable', fa: 'خروجی', hint: 'O-000031' },
  { id: 'link', fa: 'لینک', hint: 'https://…' },
  { id: 'metric', fa: 'متریک', hint: 'uptime 99.9%' },
  { id: 'log', fa: 'لاگ', hint: 'شناسه یا خلاصه' },
];
type W = { id: string; ref: string; title: string; brief: string; priority: string; due_at: string | null; version: number; status: string };
export const CLOSED = ['done', 'cancelled', 'failed'];

/** Local "YYYY-MM-DDTHH:mm" for a datetime-local input, in the browser's zone. */
const toLocal = (iso: string | null) => (iso ? new Date(new Date(iso).getTime() - new Date().getTimezoneOffset() * 60_000).toISOString().slice(0, 16) : '');

/** The owner's hands on one work item (§4): edit, close with evidence (a tick needs evidence, §1.9), or cancel with everything under it. */
export function WorkActions({ w }: { w: W }) {
  const act = useWorkAction();
  const toast = useToast();
  const [mode, setMode] = useState<'edit' | 'complete' | 'cancel' | null>(null);
  const [title, setTitle] = useState(w.title);
  const [brief, setBrief] = useState(w.brief);
  const [priority, setPriority] = useState(w.priority);
  const [due, setDue] = useState(toLocal(w.due_at));
  const [reason, setReason] = useState('');
  const [ev, setEv] = useState<EvidenceIn[]>([{ kind: 'deliverable', ref: '', note: '' }]);
  if (CLOSED.includes(w.status)) return null;
  const fail = (e: unknown) => toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'انجام نشد.' });
  const open = (m: typeof mode) => { setTitle(w.title); setBrief(w.brief); setPriority(w.priority); setDue(toLocal(w.due_at)); setMode(m); };
  const saveEdit = async () => {
    const patch: Record<string, string | null> = {};
    if (title.trim() !== w.title) patch.title = title.trim();
    if (brief.trim() !== w.brief) patch.brief = brief.trim();
    if (priority !== w.priority) patch.priority = priority;
    if (due !== toLocal(w.due_at)) patch.due_at = due ? new Date(due).toISOString() : null;
    if (!Object.keys(patch).length) return setMode(null);
    try { await act.edit.mutateAsync({ id: w.id, version: w.version, patch }); toast({ tone: 'ok', text: 'کار به‌روز شد.' }); setMode(null); } catch (e) { fail(e); }
  };
  const valid = ev.filter((x) => x.ref.trim());
  const complete = async () => {
    try { await act.complete.mutateAsync({ id: w.id, evidence: valid.map((x) => ({ kind: x.kind, ref: x.ref.trim(), note: x.note?.trim() || null })) }); toast({ tone: 'ok', text: <>کار <span className="fig">{w.ref}</span> با شاهد بسته شد.</> }); setMode(null); } catch (e) { fail(e); }
  };
  const cancel = async () => {
    try { await act.cancel.mutateAsync({ id: w.id, reason: reason.trim() }); toast({ tone: 'info', text: <>کار <span className="fig">{w.ref}</span> و همه‌ی کارهای زیرش لغو شد.</> }); setMode(null); } catch (e) { fail(e); }
  };
  return (
    <>
      <Button variant="secondary" size="sm" icon="edit" onClick={() => open('edit')}>ویرایش</Button>
      <Button variant="secondary" size="sm" icon="seal" onClick={() => open('complete')}>تکمیل با شاهد</Button>
      <Button variant="ghost" size="sm" icon="close" onClick={() => open('cancel')}>لغو</Button>
      <Sheet open={mode === 'edit'} onOpenChange={(v) => !v && setMode(null)} title="ویرایش کار" description={<span className="fig">{w.ref}</span>}
        footer={<><Button variant="primary" loading={act.edit.isPending} disabled={!title.trim()} onClick={saveEdit}>ذخیره</Button><Button variant="ghost" onClick={() => setMode(null)}>انصراف</Button></>}>
        <div className="flex flex-col gap-4">
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-sec">عنوان<input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={300} className={`${field} h-11`} /></label>
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-sec">شرح<textarea value={brief} onChange={(e) => setBrief(e.target.value)} rows={6} maxLength={20000} className={`${field} py-3 leading-7`} /></label>
          <div className="flex flex-col gap-1.5 text-[13px] font-semibold text-sec">اولویت
            {/* 0.4.0: priorities in words, each with its one-line meaning. */}
            <PriorityPicker value={priority} onChange={setPriority} />
          </div>
          <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-sec">موعد<input type="datetime-local" value={due} onChange={(e) => setDue(e.target.value)} dir="ltr" className={`${field} fig h-11`} /></label>
        </div>
      </Sheet>
      <Sheet open={mode === 'complete'} onOpenChange={(v) => !v && setMode(null)} title="تکمیل با شاهد" description="کار فقط با شاهد بسته میشود؛ شاهد در کار میماند و ناظر میتواند بررسی‌اش کند."
        footer={<><Button variant="primary" icon="seal" loading={act.complete.isPending} disabled={!valid.length} onClick={complete}>ببند</Button><Button variant="ghost" onClick={() => setMode(null)}>انصراف</Button></>}>
        <div className="flex flex-col gap-3">
          {ev.map((x, i) => (
            <div key={i} className="flex flex-col gap-2 rounded-[12px] bg-tile p-3">
              <div className="flex flex-wrap gap-1.5">{KINDS.map((k) => <FilterChip key={k.id} selected={x.kind === k.id} onClick={() => setEv(ev.map((y, j) => (j === i ? { ...y, kind: k.id } : y)))}>{k.fa}</FilterChip>)}</div>
              <input value={x.ref} onChange={(e) => setEv(ev.map((y, j) => (j === i ? { ...y, ref: e.target.value } : y)))} maxLength={500} dir="ltr" placeholder={KINDS.find((k) => k.id === x.kind)?.hint} aria-label="شاهد" className={`${field} fig h-11 bg-card`} />
              <input value={x.note ?? ''} onChange={(e) => setEv(ev.map((y, j) => (j === i ? { ...y, note: e.target.value } : y)))} maxLength={1000} placeholder="توضیح کوتاه (اختیاری)" aria-label="توضیح شاهد" className={`${field} h-10 bg-card text-[14px]`} />
            </div>
          ))}
          {ev.length < 10 ? <Button variant="text" size="sm" icon="add" onClick={() => setEv([...ev, { kind: 'link', ref: '', note: '' }])}>شاهد دیگر</Button> : null}
        </div>
      </Sheet>
      <Dialog open={mode === 'cancel'} onOpenChange={(v) => !v && setMode(null)} title={<>لغو <span className="fig">{w.ref}</span>؟</>}
        actions={<><Button variant="danger" loading={act.cancel.isPending} disabled={!reason.trim()} onClick={cancel}>لغو کن</Button><Button variant="secondary" onClick={() => setMode(null)}>نه</Button></>}>
        <div className="flex flex-col gap-3">
          <p>این کار و همه‌ی کارهای زیرش لغو میشوند و کارهای تکرارشونده‌اش هم تمام میشود. تاریخچه میماند.</p>
          <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={2000} placeholder="دلیل (لازم)" className={`${field} h-11 text-[14px]`} />
        </div>
      </Dialog>
    </>
  );
}
