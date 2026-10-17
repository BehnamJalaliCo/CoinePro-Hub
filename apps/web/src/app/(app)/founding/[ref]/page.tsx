'use client';

import Link from 'next/link';
import { use, useState } from 'react';
import { Icon } from '@/components/icon';
import { Button, Spinner } from '@/components/ui/button';
import { Md } from '@/components/ui/md';
import { Dialog } from '@/components/ui/overlay';
import { Card, ErrorState, Pill, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { FOUNDING_STATE, Figs, Score } from '@/components/v14/bits';
import { ApiError } from '@/lib/api/client';
import { useFounding, useFoundingAction, usePlan, useRun, type Founding } from '@/lib/api/v14';
import { cx, jTime, modelLabel, usd } from '@/lib/format';
import { DEPT_FA, ROLE_FA } from '@/lib/labels';

const STAGES: Array<[string, string]> = [['auditing', 'ممیزی'], ['proposed', 'پیشنهاد'], ['sealed', 'مُهر'], ['provisioning', 'ساخت سرور'], ['ready_for_login', 'ورود تو'], ['active', 'فعال']];
const SOFTWARE_FA: Record<string, string> = {
  'system-upgrade': 'به‌روزرسانی و ارتقای کامل سیستم', 'unattended-upgrades': 'به‌روزرسانی خودکار امنیتی', 'work-user': 'کاربر کاری', 'ssh-hardening': 'سخت‌سازی SSH (فقط کلید، بدون root)',
  docker: 'Docker', git: 'Git', 'node-lts': 'Node LTS', 'claude-code': 'Claude Code (ورود با حساب خودت)', 'repo-clone': 'clone ریپوی شرکت', 'private-network': 'شبکه‌ی خصوصی هتزنر',
  'hetzner-firewall': 'فایروال هتزنر', 'node-exporter': 'پایش (فقط روی IP خصوصی)',
};
const AUDIT_FA: Record<string, string> = { architecture: 'معماری', quality: 'کیفیت', security: 'امنیت', tests: 'تست‌ها', debt: 'بدهی فنی' };

function Copy({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <span dir="ltr" className="flex items-center gap-3 rounded-[10px] bg-page px-3 py-2">
      <span aria-hidden className="fig text-[13px] text-muted">$</span>
      <code className="fig min-w-0 flex-1 truncate text-[13px] text-ink">{text}</code>
      <button type="button" onClick={() => { void navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1500); }} className="text-[12px] font-semibold text-gold-ink">{done ? 'کپی شد' : 'کپی'}</button>
    </span>
  );
}

function Stepper({ f }: { f: Founding }) {
  const at = STAGES.findIndex(([k]) => k === f.state);
  return (
    <ol className="flex flex-wrap items-center gap-x-2 gap-y-2">
      {STAGES.map(([k, fa], i) => (
        <li key={k} className="flex items-center gap-2">
          <span className={cx('flex h-7 items-center gap-1.5 rounded-full px-3 text-[12px]', i < at ? 'bg-pos-soft text-pos' : i === at ? 'bg-gold-soft font-semibold text-gold-ink' : 'bg-tile text-muted')}>
            {i < at ? <Icon name="seal" size={12} active /> : <span>{(i + 1).toLocaleString('fa-IR')}</span>}{fa}
          </span>
          {i < STAGES.length - 1 ? <span className="h-px w-3 bg-div" /> : null}
        </li>
      ))}
    </ol>
  );
}

function Plan({ f }: { f: Founding }) {
  const plan = usePlan(f.plan);
  const run = useRun(plan.data?.run ?? null);
  const act = useFoundingAction();
  const toast = useToast();
  const err = (e: unknown) => toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : e instanceof Error ? e.message : 'انجام نشد.' });
  if (!f.plan) return null;
  if (!plan.data) return <Skeleton className="h-48" />;
  const p = plan.data;
  const r = run.data;
  return (
    <Card className="flex flex-col gap-4 p-4">
      <SectionTitle title="سرور" note={<><span className="fig">{p.ref}</span> · <span className="fig">{p.name}</span></>} action={<span className="fig text-[18px] font-semibold">€{p.monthly_eur.toFixed(2)}<span className="text-[12px] font-normal text-muted"> / ماه</span></span>} />
      <div className="grid grid-cols-3 gap-2 sm:gap-3">
        {[['نوع', p.type], ['محل', p.location], ['سیستم', p.image]].map(([k, v]) => <div key={k} className="flex min-w-0 flex-col rounded-[10px] bg-tile px-2.5 py-2 sm:px-3"><span className="text-[11px] text-muted">{k}</span><span className="fig truncate text-[13px] sm:text-[14px]">{v}</span></div>)}
      </div>
      <div className="flex flex-col gap-1.5">
        <span className="text-[12px] font-semibold text-sec">فایروال هتزنر (ورودی)</span>
        {p.firewall.map((w, i) => (
          <div key={i} className="flex items-center gap-3 text-[12px]"><span className="fig w-24 text-ink">{w.protocol} {w.port}</span><span className="fig min-w-0 flex-1 truncate text-muted">{w.sources.join(', ')}</span><span className="text-sec">{w.note_fa}</span></div>
        ))}
      </div>
      <div className="flex flex-col gap-1.5">
        <span className="text-[12px] font-semibold text-sec">نصب کامل</span>
        <ul className="grid gap-1 sm:grid-cols-2">{p.software.map((k) => <li key={k} className="flex items-center gap-2 text-[12px] text-ink"><Icon name="seal" size={12} className="text-pos" />{SOFTWARE_FA[k] ?? k}</li>)}</ul>
        <span className="text-[11px] text-muted">کاربر کاری <span className="fig">{p.work_user}</span>{p.repo ? <> · ریپو <span className="fig">{p.repo}</span></> : null} · رمز root ساخته نمیشود؛ فقط کلید عمومی تو.</span>
      </div>
      {p.state === 'proposed' ? (
        <Button variant="primary" icon="seal" loading={act.sealPlan.isPending} onClick={() => act.sealPlan.mutateAsync(p).then(() => toast({ tone: 'ok', text: 'مُهر شد؛ ساخت سرور شروع شد.' })).catch(err)}>
          با گذرکلید مُهر کن و بساز (<span className="fig">€{p.monthly_eur.toFixed(2)}</span> در ماه)
        </Button>
      ) : null}
      {r ? (
        <div className="flex flex-col gap-2 border-t border-div pt-3">
          <span className="flex items-center gap-2 text-[12px] font-semibold text-sec">ساخت {r.state === 'running' ? <Pill tone="lapis" live>در جریان</Pill> : r.state === 'done' ? <Pill tone="pos" dot>تمام شد</Pill> : <Pill tone="neg" dot>خطا</Pill>}</span>
          <ol className="flex flex-col gap-2">
            {r.steps.map((s) => (
              <li key={s.key} className="flex items-start gap-3">
                <span className={cx('mt-0.5 flex size-5 flex-none items-center justify-center rounded-full', s.state === 'done' ? 'bg-pos-soft text-pos' : s.state === 'running' ? 'bg-lapis-soft text-lapis' : s.state === 'failed' ? 'bg-neg-soft text-neg' : 'bg-tile text-muted')}>
                  {s.state === 'running' ? <Spinner size={12} /> : s.state === 'done' ? <Icon name="seal" size={11} active /> : s.state === 'failed' ? <Icon name="urgent" size={11} /> : null}
                </span>
                <span className="flex min-w-0 flex-1 flex-col"><span className="text-[13px] text-ink">{s.title_fa}</span>{s.log_tail ? <code dir="ltr" className="fig text-left text-[11px] text-muted">{s.log_tail}</code> : null}</span>
                {s.finished_at ? <span className="text-[11px] text-muted">{jTime(s.finished_at)}</span> : null}
              </li>
            ))}
          </ol>
          {r.server ? <span className="fig text-[12px] text-sec" dir="ltr">{r.server.name} · {r.server.ipv4} · {r.server.private_ip ?? ''}</span> : null}
        </div>
      ) : null}
    </Card>
  );
}

/** One founding, from audit to an active company (contract §18.8). */
export default function FoundingDetail({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = use(params);
  const q = useFounding(ref);
  const plan = usePlan(q.data?.plan ?? null);
  const run = useRun(plan.data?.run ?? null);
  const act = useFoundingAction();
  const toast = useToast();
  const [cancel, setCancel] = useState(false);
  if (q.isLoading) return <Skeleton className="h-64" />;
  if (q.error || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const f = q.data;
  const st = FOUNDING_STATE[f.state];
  const login = run.data?.login;
  return (
    <>
      <Link href="/founding" className="inline-flex items-center gap-1 self-start text-[13px] text-sec hover:text-ink"><Icon name="back" size={16} mirror />تأسیس شرکت</Link>
      <header className="flex flex-wrap items-center gap-3">
        <span className="flex size-12 items-center justify-center rounded-full bg-gold-soft text-gold-ink"><Icon name="found" size={24} /></span>
        <div className="flex min-w-0 flex-[1_1_16rem] flex-col"><span className="text-caption text-muted"><span className="fig">{f.ref}</span>{f.source.repo ? <> · <span className="fig">{f.source.repo}</span></> : ' · ایده'}</span><h1 className="flex flex-wrap items-baseline gap-x-2 text-h1 font-semibold">{f.name_fa}{f.name_en ? <span className="fig text-[16px] font-normal text-muted">{f.name_en}</span> : null}</h1></div>
        <Pill tone={st.tone} live={st.live} dot={!st.live}>{st.fa}</Pill>
        {/* Before a server exists nothing is spent, so cancelling is safe; afterwards only the owner removes servers, in Hetzner. */}
        {f.state === 'auditing' || f.state === 'proposed' ? <Button size="sm" variant="ghost" onClick={() => setCancel(true)}>لغو تأسیس</Button> : null}
      </header>
      <Dialog open={cancel} onOpenChange={setCancel} title="این تأسیس لغو شود؟"
        actions={<>
          <Button variant="ghost" onClick={() => setCancel(false)}>نه</Button>
          <Button variant="danger" loading={act.cancel.isPending} onClick={() => act.cancel.mutateAsync(f.ref).then(() => { setCancel(false); toast({ tone: 'ok', text: 'لغو شد.' }); }).catch((e) => toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'لغو نشد.' }))}>لغو کن</Button>
        </>}>
        <p className="text-[13px] leading-7 text-sec">ممیزی و پیشنهاد در سوابق میماند. هنوز سروری ساخته نشده و هزینه‌ای نیست.</p>
      </Dialog>
      <Stepper f={f} />
      {f.state === 'ready_for_login' && login ? (
        <Card className="tahrir flex flex-col gap-3 p-5">
          <SectionTitle title="سرور آماده است؛ نوبت توست" note="در ترمینال خودت وارد شو و Claude Code را با حساب خودت باز کن" />
          <ol className="flex flex-col gap-2 text-[13px]">
            <li className="flex flex-col gap-1"><span className="text-sec">۱. وارد سرور شو</span><Copy text={login.ssh} /></li>
            <li className="flex flex-col gap-1"><span className="text-sec">۲. Claude Code را باز کن و با حساب خودت وارد شو</span>{login.then.map((c) => <Copy key={c} text={c} />)}</li>
            <li className="text-sec">۳. وقتی وارد شدی، شرکت را فعال کن تا مدیرعامل شروع کند.</li>
          </ol>
          <Button variant="primary" icon="seal" loading={act.activate.isPending} onClick={() => act.activate.mutateAsync(f.ref).then(() => toast({ tone: 'ok', text: 'شرکت فعال شد؛ مدیرعامل شروع به کار کرد.' })).catch((e) => toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'فعال نشد.' }))}>وارد شدم؛ شرکت را فعال کن</Button>
        </Card>
      ) : null}
      <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          {f.audit ? (
            <Card className="flex flex-col gap-3 p-4">
              <SectionTitle title="ممیزی" note={<>جلسه‌ی فقط‌خواندنی <Link href={`/workshop/${f.audit.session_ref}`} className="fig text-gold-ink">{f.audit.session_ref}</Link></>} />
              <div className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3">{Object.entries(f.audit.scores).map(([k, v]) => <span key={k} className="flex flex-col gap-0.5"><span className="text-[11px] text-muted">{AUDIT_FA[k]}</span><Score value={v} /></span>)}</div>
              <Md text={f.audit.report_md} className="flex flex-col gap-2 text-[13px] leading-7 text-sec" />
            </Card>
          ) : f.state === 'auditing' ? <Card className="flex items-center gap-3 p-5 text-[13px] text-sec"><Spinner size={16} />ممیزی در جریان است؛ نتیجه و پیشنهاد به کارتابلت میاید.</Card> : null}
          {f.proposal ? (
            <Card className="flex flex-col gap-3 p-4">
              <SectionTitle title="پیشنهاد" note="ساختار، هدف‌ها، تیم و نقشه‌ی راه" action={f.decision_ref && f.state === 'proposed' ? <Link href={`/cartable?ref=${f.decision_ref}`} className="inline-flex h-8 items-center gap-1.5 rounded-[8px] bg-gold px-3 text-[12px] font-bold text-on-gold"><Icon name="seal" size={14} />مُهر در کارتابل</Link> : undefined} />
              <div className="flex flex-wrap gap-1.5">{f.proposal.departments.map((d) => <span key={d} className="rounded-full bg-tile px-2.5 py-1 text-[12px] text-sec">{DEPT_FA[d] ?? d}</span>)}</div>
              <ul className="flex flex-col gap-1">{f.proposal.kpis.map((k) => <li key={k.name_fa} className="flex items-center gap-2 text-[13px]"><Icon name="chart" size={14} className="text-muted" /><span className="flex-1">{k.name_fa}</span><span className="text-[12px] text-sec"><Figs text={k.target} /></span></li>)}</ul>
              <div className="flex flex-col gap-1 border-t border-div pt-2">
                {f.proposal.team.map((t) => <span key={t.role} className="flex items-center gap-3 text-[12px]"><span className="flex-1 text-ink">{ROLE_FA[t.role] ?? t.role}</span><span className="fig text-muted">{modelLabel(t.model)}</span><span className="fig w-14 text-left text-sec">{usd(t.monthly_usd, 0)}</span></span>)}
                <span className="flex items-center gap-3 text-[13px] font-semibold"><span className="flex-1">جمع ماهانه‌ی تیم</span><span className="fig">{usd(f.proposal.monthly_usd, 0)}</span></span>
              </div>
              {f.proposal.roadmap_md ? <Md text={f.proposal.roadmap_md} className="text-[13px] leading-7 text-sec" /> : null}
            </Card>
          ) : null}
        </div>
        <div className="flex min-w-0 flex-col gap-4"><Plan f={f} /></div>
      </div>
    </>
  );
}
