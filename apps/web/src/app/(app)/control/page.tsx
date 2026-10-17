'use client';

import { useState } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark, Monogram } from '@/components/brand/marks';
import { Button } from '@/components/ui/button';
import { Dialog } from '@/components/ui/overlay';
import { Card, ErrorState, PageHeader, Pill, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { useCompanies, useControl, useKillSwitch } from '@/lib/api/hooks';
import { stepUp } from '@/lib/auth';
import { ago, cx, jDateTime, until } from '@/lib/format';

type Target = { scope: string; name: string; engaged: boolean };

/** Kill switches (OPERATING_MODEL §1.12): engaging is instant (speed matters); releasing needs the passkey. */
export default function ControlPage() {
  const q = useControl();
  const { data: companies } = useCompanies();
  const ks = useKillSwitch();
  const toast = useToast();
  const [t, setT] = useState<Target | null>(null);
  const [reason, setReason] = useState('');
  const name = (code: string) => companies?.find((c) => c.code === code)?.name_fa ?? code;

  const run = async () => {
    if (!t) return;
    try {
      const token = t.engaged ? await stepUp('kill_switch.release', t.scope) : undefined;
      await ks.mutateAsync({ scope: t.scope, state: t.engaged ? 'released' : 'engaged', reason: reason.trim() || (t.engaged ? 'آزاد شد' : 'توقف اضطراری'), stepUpToken: token });
      toast({ tone: t.engaged ? 'ok' : 'info', text: t.engaged ? `${t.name} دوباره کار میکند.` : `${t.name} متوقف شد؛ ایجنت‌هایش هیچ اقدام نوشتنی نمیکنند.` });
      setT(null); setReason('');
    } catch (e) { toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'انجام نشد.' }); }
  };

  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const holding = q.data?.holding;
  return (
    <>
      <PageHeader eyebrow="کلید توقف و توقف deploy" title="کنترل" />
      {!q.data ? <Skeleton className="h-64 rounded-[16px]" /> : (
        <>
          <Card className={cx('flex flex-wrap items-center gap-4 p-5', holding?.state === 'engaged' ? 'bg-neg-soft' : 'tahrir')}>
            <span className="flex size-14 items-center justify-center rounded-full bg-tile"><Monogram size={26} /></span>
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <span className="text-h3 font-semibold">کلید توقف کل هلدینگ</span>
              <span className="text-[13px] text-sec">{holding?.state === 'engaged' ? <>روشن از {ago(holding.changed_at)}: فقط کارهای اضطراری (<span className="fig">P0</span>) اجرا میشوند.</> : 'خاموش؛ همه‌چیز عادی است.'}</span>
              {holding?.reason ? <span className="text-[12px] text-muted">«{holding.reason}»</span> : null}
            </div>
            <Button variant={holding?.state === 'engaged' ? 'primary' : 'danger'} icon={holding?.state === 'engaged' ? 'resume' : 'pause'} onClick={() => setT({ scope: 'holding', name: 'کل هلدینگ', engaged: holding?.state === 'engaged' })}>
              {holding?.state === 'engaged' ? 'آزاد کن' : 'توقف همه‌چیز'}
            </Button>
          </Card>
          <SectionTitle title="شرکت‌ها" note="مدیرعامل هر شرکت هم میتواند کلید شرکت خودش را بزند؛ کلیدی را که تو زده‌ای فقط خودت آزاد میکنی." />
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {q.data.companies.map((k) => {
              const on = k.state === 'engaged';
              const freeze = q.data!.deploy_freezes.find((f) => f.company === k.company && new Date(f.until) > new Date());
              return (
                <Card key={k.scope} className={cx('flex flex-col gap-3 p-4', on && 'bg-neg-soft')}>
                  <div className="flex items-center gap-3">
                    <span className="flex size-11 items-center justify-center rounded-full border border-strong bg-tile text-ink"><CompanyMark code={k.company} height={20} /></span>
                    <div className="flex flex-1 flex-col"><span className="text-[15px] font-semibold">{name(k.company)}</span><span className="text-[12px] text-muted">{on ? `متوقف، ${ago(k.changed_at)}` : 'عادی'}{k.changed_by && on ? `، با ${k.changed_by === 'owner' ? 'تو' : k.changed_by}` : ''}</span></div>
                    {on ? <Pill tone="neg" icon="lock">متوقف</Pill> : <Pill tone="pos" dot>فعال</Pill>}
                  </div>
                  {freeze ? <div className="flex items-center gap-2 rounded-[10px] bg-warn-soft px-3 py-2 text-[12px] text-ink"><Icon name="pause" size={14} />توقف deploy تا {jDateTime(freeze.until)} ({until(freeze.until)})، {freeze.reason}</div> : null}
                  <Button variant={on ? 'primary' : 'danger'} size="sm" icon={on ? 'resume' : 'pause'} onClick={() => setT({ scope: k.scope, name: name(k.company), engaged: on })}>{on ? 'آزاد کن (passkey)' : 'توقف این شرکت'}</Button>
                </Card>
              );
            })}
          </div>
        </>
      )}
      <Dialog open={!!t} onOpenChange={(v) => !v && setT(null)} title={t?.engaged ? `آزاد کردن ${t?.name}` : `توقف ${t?.name}`} actions={<>
        <Button variant={t?.engaged ? 'primary' : 'danger'} loading={ks.isPending} onClick={run}>{t?.engaged ? 'آزاد کن' : 'متوقف کن'}</Button>
        <Button variant="secondary" onClick={() => setT(null)}>انصراف</Button>
      </>}>
        <div className="flex flex-col gap-3">
          <p>{t?.engaged ? 'ایجنت‌ها دوباره اجازه‌ی اقدام نوشتنی میگیرند. با اثر انگشت یا چهره تأیید میشود.' : 'همه‌ی اقدام‌های نوشتنی ایجنت‌ها در این محدوده فوراً رد میشوند؛ گزارش‌ها و Audit ادامه دارند.'}</p>
          <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} placeholder="دلیل (یک خط)" className="h-11 rounded-[10px] border border-strong bg-tile px-3 text-[14px] text-ink outline-none focus:border-gold-ink" />
        </div>
      </Dialog>
    </>
  );
}
