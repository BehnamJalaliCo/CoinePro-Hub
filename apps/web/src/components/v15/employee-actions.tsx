'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Sheet } from '@/components/ui/overlay';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { useEmployees } from '@/lib/api/hooks';
import { useEmployeeAction } from '@/lib/api/v15';

const field = 'w-full rounded-[10px] border border-strong bg-tile px-3 text-[15px] text-ink outline-none focus:border-gold-ink';
export const EMPLOYEE_STATUS: Record<string, string> = { active: 'فعال', paused: 'در مکث', dismissed: 'اخراج شده' };
type E = { code: string; company: string; department: string | null; title_fa: string; display_name?: string | null; status: string; kind: string };

/** Pause, resume and dismiss (§4): pause stops new work being routed and keeps open work; dismissal is sealed and hands knowledge over. */
export function EmployeeActions({ e }: { e: E }) {
  const act = useEmployeeAction();
  const toast = useToast();
  const [dismiss, setDismiss] = useState(false);
  const [reason, setReason] = useState('');
  const [to, setTo] = useState('');
  const peers = useEmployees({ company: [e.company] });
  if (e.status === 'dismissed' || !['employee', 'manager', 'ceo'].includes(e.kind)) return null;
  const name = e.display_name ?? e.title_fa;
  const fail = (err: unknown) => toast({ tone: 'error', text: err instanceof ApiError ? err.messageFa : 'انجام نشد.' });
  const toggle = async () => {
    try {
      if (e.status === 'paused') { await act.resume.mutateAsync(e.code); toast({ tone: 'ok', text: `${name} دوباره کار میگیرد.` }); }
      else { await act.pause.mutateAsync(e.code); toast({ tone: 'info', text: `${name} در مکث است؛ کار تازه به او نمیرسد و کارهای باز میمانند.` }); }
    } catch (err) { fail(err); }
  };
  const run = async () => {
    try {
      const r = await act.dismiss.mutateAsync({ code: e.code, reason: reason.trim(), transfer_to: to || null });
      toast({ tone: 'info', text: <>{name} اخراج شد. {r.work_returned ? `${r.work_returned.toLocaleString('fa-IR')} کار باز برگشت.` : ''} {r.transfer_work ? <>کار انتقال دانش: <span className="fig">{r.transfer_work}</span></> : null}</> });
      setDismiss(false);
    } catch (err) { fail(err); }
  };
  const candidates = (peers.data?.items ?? []).filter((p) => p.code !== e.code && p.status === 'active' && (p.department === e.department || p.kind !== 'employee'));
  return (
    <>
      <Button variant="secondary" size="sm" icon={e.status === 'paused' ? 'resume' : 'pause'} loading={act.pause.isPending || act.resume.isPending} onClick={toggle}>{e.status === 'paused' ? 'ادامه' : 'مکث'}</Button>
      {e.kind !== 'ceo' ? <Button variant="ghost" size="sm" icon="dismiss" onClick={() => { setReason(''); setTo(''); setDismiss(true); }}>اخراج</Button> : null}
      <Sheet open={dismiss} onOpenChange={setDismiss} title={`اخراج ${name}`} description={<>کد <span className="fig">{e.code}</span> دیگر به کسی داده نمیشود.</>}
        footer={<><Button variant="danger" icon="seal" loading={act.dismiss.isPending} disabled={!reason.trim()} onClick={run}>اخراج با passkey</Button><Button variant="ghost" onClick={() => setDismiss(false)}>انصراف</Button></>}>
        <div className="flex flex-col gap-4 text-[13px]">
          <ul className="flex list-disc flex-col gap-1 pr-5 leading-6 text-sec marker:text-muted">
            <li>کارهای بازش به مدیرش برمیگردد، یا به کسی که اینجا انتخاب کنی.</li>
            <li>یک کار «انتقال دانش» ساخته میشود: خروجی‌ها، یادداشت‌ها، و نکات مثبت و منفی کارش.</li>
            <li>تاریخچه، خروجی‌ها و امتیازهایش میماند؛ هیچ چیز پاک نمیشود.</li>
          </ul>
          <label className="flex flex-col gap-1.5 font-semibold text-sec">دلیل (لازم)
            <textarea value={reason} onChange={(ev) => setReason(ev.target.value)} rows={3} maxLength={2000} className={`${field} py-3 leading-7`} />
          </label>
          <label className="flex flex-col gap-1.5 font-semibold text-sec">کارهای باز به
            <select value={to} onChange={(ev) => setTo(ev.target.value)} className={`${field} h-11 text-[14px]`}>
              <option value="">مدیرش (پیش‌فرض)</option>
              {candidates.map((p) => <option key={p.code} value={p.code}>{p.display_name ?? p.title_fa} · {p.code}</option>)}
            </select>
          </label>
        </div>
      </Sheet>
    </>
  );
}
