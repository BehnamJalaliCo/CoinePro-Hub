'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Sheet } from '@/components/ui/overlay';
import { Card, Empty, ErrorState, PageHeader, Pill, Segmented, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { FOUNDING_STATE } from '@/components/v14/bits';
import { foundingName, useFoundingAction, useFoundings } from '@/lib/api/v14';
import { ago, cx } from '@/lib/format';


function Start({ onClose }: { onClose: () => void }) {
  const act = useFoundingAction();
  const toast = useToast();
  const router = useRouter();
  const [kind, setKind] = useState<'repo' | 'idea'>('repo');
  const [repo, setRepo] = useState('');
  const [brief, setBrief] = useState('');
  const ok = kind === 'repo' ? /^[\w.-]+\/[\w.-]+$/.test(repo.trim().replace(/^https:\/\/github\.com\//, '')) : brief.trim().length >= 10;
  const go = () => act.start.mutateAsync({ kind, repo: kind === 'repo' ? repo.trim().replace(/^https:\/\/github\.com\//, '').replace(/\.git$/, '') : null, brief_md: brief.trim() })
    .then((f) => { onClose(); router.push(`/founding/${f.ref}`); })
    .catch((e) => toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'شروع نشد.' }));
  const field = 'w-full rounded-[10px] border border-strong bg-tile px-3 text-[15px] text-ink outline-none focus:border-gold-ink';
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title="تأسیس شرکت تازه" description="از روی یک ریپو یا یک ایده؛ ممیزی و پیشنهاد کامل به کارتابلت میاید." width={520}
      footer={<Button variant="primary" icon="found" className="w-full" disabled={!ok} loading={act.start.isPending} onClick={go}>شروع کن</Button>}>
      <div className="flex flex-col gap-4">
        <Segmented label="منبع" value={kind} onChange={setKind} options={[{ value: 'repo', label: 'ریپوی GitHub' }, { value: 'idea', label: 'ایده' }]} />
        {kind === 'repo' ? <label className="flex flex-col gap-1.5"><span className="text-[13px] text-sec">ریپو</span><input dir="ltr" value={repo} onChange={(e) => setRepo(e.target.value)} placeholder="owner/name" className={cx(field, 'fig h-12 text-left')} /></label> : null}
        <label className="flex flex-col gap-1.5"><span className="text-[13px] text-sec">{kind === 'repo' ? 'چه میخواهی از این شرکت (اختیاری)' : 'ایده و هدف'}</span><textarea value={brief} onChange={(e) => setBrief(e.target.value)} rows={4} className={cx(field, 'py-3 leading-7')} /></label>
        <p className="text-[12px] leading-6 text-muted">ممیزی فقط‌خواندنی است. شرکت فقط با مُهر تو ساخته میشود و سرور با مُهر جدا (هزینه‌ی واقعی).</p>
      </div>
    </Sheet>
  );
}

/** تأسیس شرکت (contract §18.8): from a repository or an idea to a sealed company and a server ready for the owner's own login. */
export default function FoundingPage() {
  const q = useFoundings();
  const [start, setStart] = useState(false);
  const items = q.data?.pages.flatMap((pg) => pg.items) ?? [];
  return (
    <>
      <PageHeader eyebrow="از ریپو یا ایده تا شرکت فعال و سرور آماده" title="تأسیس شرکت" actions={<Button variant="primary" icon="add" onClick={() => setStart(true)}>تأسیس تازه</Button>}>
        <p className="max-w-3xl text-[13px] leading-6 text-sec">ممیزی، پیشنهاد ساختار و تیم و نقشه‌ی راه، مُهر تو، و ساخت کامل سرور با API هتزنر (به‌روزرسانی، نصب و Claude Code آماده). بعد خودت وارد میشوی و ادامه میدهیم. رمز سرور هیچ‌وقت به ایجنت نمیرسد.</p>
      </PageHeader>
      {q.isLoading ? <Skeleton className="h-40" /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !items.length ? <Empty icon="found" title="هنوز تأسیسی نیست" /> : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {items.map((f) => (
            <Link key={f.ref} href={`/founding/${f.ref}`} className={cx('flex flex-col gap-2 rounded-[16px] p-4 hover:bg-hover', f.state === 'ready_for_login' || f.state === 'proposed' ? 'bg-gold-soft' : 'bg-card')}>
              <span className="flex items-center gap-2"><Icon name="found" size={18} className="text-gold-ink" /><span className="min-w-0 flex-1 truncate text-[15px] font-semibold">{foundingName(f)}</span><Pill tone={FOUNDING_STATE[f.state].tone} live={FOUNDING_STATE[f.state].live} dot={!FOUNDING_STATE[f.state].live}>{FOUNDING_STATE[f.state].fa}</Pill></span>
              <span className="flex items-center gap-2 text-[12px] text-muted"><span className="fig">{f.ref}</span>{f.source.repo ? <span className="fig truncate">{f.source.repo}</span> : <span>ایده</span>}<span className="flex-1" /><span>{ago(f.updated_at)}</span></span>
            </Link>
          ))}
          {q.hasNextPage ? <Button variant="secondary" size="sm" className="self-start" loading={q.isFetchingNextPage} onClick={() => q.fetchNextPage()}>بیشتر</Button> : null}
        </div>
      )}
      <Path />
      {start ? <Start onClose={() => setStart(false)} /> : null}
    </>
  );
}

const PATH: Array<{ t: string; d: string; you?: boolean }> = [
  { t: 'ممیزی', d: 'جلسه‌ی فقط‌خواندنی کارگاه روی ریپو: کد، وابستگی‌ها، ریسک‌ها، هزینه.' },
  { t: 'پیشنهاد', d: 'نام، رسالت، تیم و نقش‌ها، KPI، بودجه‌ی توکن و نقشه‌ی راه ۹۰ روزه.' },
  { t: 'مُهر شرکت', d: 'تو تأیید یا اصلاح میکنی؛ بدون مُهر هیچ شرکتی ساخته نمیشود.', you: true },
  { t: 'نقشه‌ی سرور', d: 'نوع و منطقه‌ی سرور، دیسک، فایروال هتزنر و هزینه‌ی ماهانه.' },
  { t: 'مُهر سرور', d: 'مُهر جدا روی خلاصه‌ی دقیق نقشه؛ هزینه‌ی واقعی از اینجا شروع میشود.', you: true },
  { t: 'ساخت', d: 'سرور تازه، به‌روزرسانی و ارتقا، Docker، Node، Claude Code، کاربر کاری؛ فقط با کلید SSH تو.' },
  { t: 'ورود تو', d: 'خودت وارد میشوی و Claude Code را لاگین میکنی؛ رمز هیچ‌وقت به ایجنت نمیرسد.', you: true },
  { t: 'فعال', d: 'مدیرعامل شروع میکند و شرکت وارد ستاره‌ها و نظارت میشود.' },
];

function Path() {
  return (
    <Card className="mt-6 flex flex-col gap-4">
      <div className="flex flex-col gap-0.5">
        <h2 className="text-h3 font-semibold text-ink">مسیر تأسیس</h2>
        <p className="text-caption text-muted">سه نقطه با توست؛ بقیه را ایجنت‌ها انجام میدهند و همه در دفتر Audit ثبت میشود</p>
      </div>
      <ol className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {PATH.map((s, i) => (
          <li key={s.t} className={cx('flex gap-3 rounded-[12px] p-3', s.you ? 'bg-gold-soft' : 'bg-tile')}>
            <span className={cx('grid size-7 flex-none place-items-center rounded-full text-[12px] font-semibold', s.you ? 'bg-gold text-on-gold' : 'bg-raised text-sec')}>{(i + 1).toLocaleString('fa-IR')}</span>
            <span className="flex min-w-0 flex-col gap-0.5">
              <span className="flex items-center gap-1.5 text-[14px] font-semibold text-ink">{s.t}{s.you ? <Icon name="seal" size={14} className="text-gold-ink" /> : null}</span>
              <span className="text-[12px] leading-6 text-sec">{s.d}</span>
            </span>
          </li>
        ))}
      </ol>
      <p className="text-[12px] leading-6 text-muted">پیش از اولین ساخت، یک بار در ترمینال خودت: <span className="fig" dir="ltr">make hetzner-token</span> و <span className="fig" dir="ltr">make owner-ssh-key</span>.</p>
    </Card>
  );
}
