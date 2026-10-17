'use client';

import { useState } from 'react';
import { Icon } from '@/components/icon';
import { Composer } from '@/components/media/composer';
import { Button } from '@/components/ui/button';
import { Card, FilterChip, PageHeader, Pill, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { Spark } from '@/components/v14/bits';
import { ApiError } from '@/lib/api/client';
import { useCurricula, useEvals, useTeachAction, useTeachings } from '@/lib/api/v14';
import { ago, cx } from '@/lib/format';

const ROLE_FA: Record<string, string> = { all: 'همه', overseer: 'ناظر کل', advisor: 'مشاور کل', ceo: 'مدیرعامل‌ها', assistant: 'دستیار', manager: 'مدیرها', cto: 'مدیر فنی' };
const T_FA: Record<string, { fa: string; tone: 'neutral' | 'lapis' | 'gold' | 'pos' | 'neg' }> = {
  drafting: { fa: 'در حال آماده‌سازی', tone: 'lapis' }, proposed: { fa: 'منتظر تأیید تو', tone: 'gold' }, approved: { fa: 'تأیید شد', tone: 'pos' }, rejected: { fa: 'رد شد', tone: 'neg' },
};

/** آکادمی هلدینگ (contract §18.6): the knowledge layer made measurable. Golden evals gate every new version; the owner teaches by voice. */
export default function AcademyPage() {
  const cur = useCurricula();
  const evals = useEvals();
  const teach = useTeachings();
  const act = useTeachAction();
  const toast = useToast();
  const [role, setRole] = useState('overseer');
  const err = (e: unknown) => toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : e instanceof Error ? e.message : 'انجام نشد.' });
  const roles = (cur.data ?? []).map((c) => c.role);
  const c = cur.data?.find((x) => x.role === role);
  const suites = (evals.data ?? []).filter((e) => e.role === role || e.role === 'all');
  return (
    <>
      <PageHeader eyebrow="فاین‌تیون ما: لایه‌ی دانشی که مال ماست و با عوض شدن مدل از دست نمیرود" title="آکادمی">
        <p className="max-w-3xl text-[13px] leading-6 text-sec">هر نقش برنامه‌ی آموزشی و آزمون طلایی دارد. هیچ نسخه‌ی تازه‌ای از منشور، مهارت یا مدل بدون نمره‌ی برابر یا بهتر از خط پایه فعال نمیشود.</p>
      </PageHeader>
      <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          <Card className="flex flex-col gap-3 p-4">
            <SectionTitle title="آموزش مستقیم" note="بگو یا بنویس؛ مدیر عملیات AI دقیقش میکند، ناظر بررسی میکند، آزمون اجرا میشود، تو تأیید میکنی" />
            <div className="flex flex-wrap gap-2">{roles.map((r) => <FilterChip key={r} selected={role === r} onClick={() => setRole(r)}>{ROLE_FA[r] ?? r}</FilterChip>)}</div>
            <Composer placeholder={`به ${ROLE_FA[role] ?? role} یاد بده…`} purpose="note" allowFiles={false} label="آموزش"
              onSend={async (v) => { await act.teach.mutateAsync({ target: { kind: 'role', ref: role }, text: v.body, source: v.attachments.length ? 'voice' : 'text', file_id: v.attachments[0] ?? null }).catch((e) => { err(e); throw e; }); toast({ tone: 'ok', text: 'ثبت شد؛ پیشنهاد دقیق و نمره‌ی آزمون به‌زودی میاید.' }); }} />
            <ul className="flex flex-col gap-2">
              {teach.isLoading ? <Skeleton className="h-24" /> : (teach.data ?? []).map((t) => (
                <li key={t.ref} className={cx('flex flex-col gap-2 rounded-[12px] p-3', t.status === 'proposed' ? 'bg-gold-soft' : 'bg-tile')}>
                  <div className="flex items-center gap-2 text-[11px] text-muted">
                    <span className="fig">{t.ref}</span>{t.source === 'voice' ? <Icon name="mic" size={12} /> : null}<span>{ROLE_FA[t.target.ref] ?? t.target.ref}</span><span className="flex-1">{ago(t.created_at)}</span>
                    <Pill tone={T_FA[t.status]!.tone} live={t.status === 'drafting'} dot={t.status !== 'drafting'}>{T_FA[t.status]!.fa}</Pill>
                  </div>
                  <p className="text-[14px] leading-7 text-ink">{t.text_md}</p>
                  {t.proposal ? <pre dir="ltr" className="fig overflow-x-auto whitespace-pre-wrap rounded-[10px] bg-page p-3 text-left text-[12px] leading-6 text-sec">{t.proposal.diff_md}</pre> : null}
                  {t.eval_run ? <span className={cx('text-[12px]', t.eval_run.passed ? 'text-pos' : 'text-neg')}>آزمون: <span className="fig">{t.eval_run.score}</span> در برابر خط پایه <span className="fig">{t.eval_run.baseline}</span> · {t.eval_run.passed ? 'قبول' : 'رد'}</span> : null}
                  {t.status === 'proposed' ? (
                    <div className="flex gap-2">
                      <Button size="sm" variant="primary" icon="seal" disabled={t.eval_run?.passed === false} loading={act.approve.isPending} onClick={() => act.approve.mutateAsync(t.ref).then(() => toast({ tone: 'ok', text: 'تأیید شد؛ نسخه‌ی تازه فعال شد.' })).catch(err)}>تأیید کن</Button>
                      <Button size="sm" variant="ghost" onClick={() => act.reject.mutateAsync(t.ref).catch(err)}>رد کن</Button>
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          </Card>
        </div>
        <div className="flex min-w-0 flex-col gap-4">
          <Card className="flex flex-col gap-3 p-4">
            <SectionTitle title={`برنامه‌ی ${ROLE_FA[role] ?? role}`} note={c ? <>نسخه‌ی <span className="fig">{c.version}</span></> : undefined} />
            {!c ? <Skeleton className="h-24" /> : c.modules.map((m) => (
              <div key={m.key} className="flex flex-col gap-1 border-b border-div pb-2 last:border-0">
                <span className="text-[13px] text-ink">{m.title_fa}</span>
                <span className="flex flex-wrap gap-1.5 text-[11px] text-muted">{[...m.skills, ...m.evals].map((r) => <span key={r} className="fig rounded-full bg-tile px-2 py-0.5 text-gold-ink">{r}</span>)}</span>
              </div>
            ))}
          </Card>
          <Card className="flex flex-col gap-3 p-4">
            <SectionTitle title="آزمون‌های طلایی" note="نمره‌ی نسخه‌ها در برابر خط پایه" />
            {evals.isLoading ? <Skeleton className="h-32" /> : suites.map((s) => {
              const last = s.runs.at(-1);
              return (
                <div key={s.ref} className="flex items-center gap-3 border-b border-div py-2 last:border-0">
                  <span className="flex min-w-0 flex-1 flex-col"><span className="text-[13px]">{s.title_fa}</span><span className="text-[11px] text-muted"><span className="fig">{s.ref}</span> · {s.cases} مورد · خط پایه <span className="fig">{s.baseline?.score ?? '—'}</span></span></span>
                  <Spark values={s.runs.map((r) => r.score)} min={60} max={100} />
                  {last ? <span className={cx('fig w-8 text-left text-[14px] font-semibold', last.passed ? 'text-pos' : 'text-neg')}>{last.score}</span> : null}
                </div>
              );
            })}
          </Card>
        </div>
      </div>
    </>
  );
}
