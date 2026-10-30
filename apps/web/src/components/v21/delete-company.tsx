'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Sheet } from '@/components/ui/overlay';
import { useToast } from '@/components/ui/toast';
import { ApiError, type Schemas } from '@/lib/api/client';
import { codeMatches, deleteOutcome, useCompanyRemoval, type DeleteOutcome } from '@/lib/api/v21';
import { forgetRequest } from '@/lib/api/observe';
import { cx } from '@/lib/format';
import { Consequences, inputCls } from './bits';

/**
 * «حذف شرکت» (0.5.0; contract §25): a company made by mistake — what goes and what stays, the company's code typed exactly, then the
 * passkey (`company.delete`). The hub keeps a company that has a history (work done, outputs, revenue: `409 company_has_history`) and the
 * sheet offers to archive it instead (`status: archived`, 🔏 `company.archive`), as it does while a hub has no delete at all (405).
 */
export function DeleteCompany({ t, company, onClose }: { t: { code: string; nameFa: string; holding: boolean }; company: Schemas['Company'] | null; onClose: () => void }) {
  const router = useRouter();
  const toast = useToast();
  const act = useCompanyRemoval();
  const [typed, setTyped] = useState('');
  const [outcome, setOutcome] = useState<DeleteOutcome | null>(null);
  const busy = act.remove.isPending || act.archive.isPending;
  const done = () => { onClose(); router.push('/companies'); };

  const remove = async () => {
    try {
      await act.remove.mutateAsync(t.code);
      toast({ tone: 'ok', text: `${t.nameFa} حذف شد.` });
      done();
    } catch (e) {
      const o = deleteOutcome(e);
      if (o === 'gone') { toast({ tone: 'ok', text: `${t.nameFa} حذف شد.` }); done(); return; }
      if (o === 'failed') toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'حذف نشد.' });
      // An expected answer (a history, or a hub without the route): it is not a fault for «خطاخوان».
      else if (e instanceof ApiError) forgetRequest(e.requestId);
      setOutcome(o);
    }
  };
  const archive = async () => {
    try {
      await act.archive.mutateAsync(t.code);
      toast({ tone: 'ok', text: `${t.nameFa} بایگانی شد؛ همه‌ی سوابقش میماند.` });
      done();
    } catch (e) { toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'بایگانی نشد.' }); }
  };

  const keep = outcome === 'has_history' || outcome === 'not_served';
  return (
    <Sheet open onOpenChange={(v) => !v && onClose()} title={`حذف ${t.nameFa}`} description="برای شرکتی که اشتباهی ساخته شده" width={480}>
      {keep ? (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5 rounded-[12px] bg-warn-soft p-3">
            <span className="text-[14px] font-semibold text-ink">{outcome === 'has_history' ? `${t.nameFa} سابقه دارد و حذف نمیشود` : 'هاب هنوز حذف شرکت را ندارد'}</span>
            <span className="text-[13px] leading-6 text-sec">{outcome === 'has_history'
              ? 'کاری انجام داده، خروجی یا درآمدی دارد؛ این‌ها در دفترها میمانند. به‌جای حذف، بایگانی‌اش کن: از گزارش‌ها، ستاره‌ها و نظارت بیرون میرود، در شرکت‌ها زیر «بایگانی‌شده» میاید و همه‌ی سوابقش سر جایش میماند.'
              : 'تا هاب حذف را بیاورد، بایگانی کن: از گزارش‌ها، ستاره‌ها و نظارت بیرون میرود و در شرکت‌ها زیر «بایگانی‌شده» میاید؛ هر وقت حذف آمد، از همین‌جا پاکش کن.'}</span>
          </div>
          <Button variant="primary" size="lg" icon="lock" loading={act.archive.isPending} onClick={archive}>بایگانی شرکت با گذرکلید</Button>
          <Button variant="ghost" onClick={onClose}>انصراف</Button>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <p className="text-[14px] leading-7 text-ink">{t.nameFa} برای همیشه پاک میشود. این کار برگشت ندارد.</p>
          <Consequences tone="neg" lines={[
            ['dismiss', 'شرکت، دپارتمان‌ها، جایگاه‌های خالی، نشان و تنظیماتش پاک میشوند.'],
            ['memory', 'فقط شرکتی پاک میشود که هنوز کاری انجام نداده، خروجی و درآمدی ندارد؛ وگرنه بایگانی پیشنهاد میشود.'],
            ['server', 'سرور و ریپو، اگر ساخته شده باشند، دست نمیخورند؛ پاک کردن سرور فقط با خودت در کنسول هتزنر است.'],
            ['lock', 'تأیید آخر با اثر انگشت یا چهره است و در دفتر Audit ثبت میشود.'],
          ]} />
          {company ? <span className="text-[12px] text-muted">الان: {company.counts.employees_active} کارمند فعال، {company.counts.work_open} کار باز، {company.counts.decisions_pending} کارت منتظر.</span> : null}
          <label className="flex flex-col gap-1.5">
            <span className="text-[13px] text-sec">برای تأیید، کد شرکت را بنویس: <span className="fig font-semibold text-ink">{t.code}</span></span>
            <input dir="ltr" value={typed} onChange={(e) => setTyped(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 10))} maxLength={10} placeholder={t.code} autoComplete="off" className={cx(inputCls, 'fig text-left')} aria-label="کد شرکت" />
          </label>
          {typed && !codeMatches(typed, t.code) ? <span className="text-[12px] text-neg">کد با <span className="fig">{t.code}</span> یکی نیست.</span> : null}
          <div className="flex gap-2">
            <Button variant="danger" icon="dismiss" className="flex-1" disabled={t.holding || busy || !codeMatches(typed, t.code)} loading={act.remove.isPending} onClick={remove}>حذف برای همیشه</Button>
            <Button variant="ghost" className="flex-1" onClick={onClose}>انصراف</Button>
          </div>
        </div>
      )}
    </Sheet>
  );
}
