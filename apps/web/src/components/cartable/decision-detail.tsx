'use client';

import { useRouter } from 'next/navigation';
import { useState, type ReactNode } from 'react';
import { Icon } from '@/components/icon';
import { Avatar } from '@/components/brand/avatar';
import { Seal } from '@/components/brand/seal';
import { Button } from '@/components/ui/button';
import { Dialog } from '@/components/ui/overlay';
import { Md } from '@/components/ui/md';
import { FilterChip, Pill } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { SealButton } from './seal-button';
import { ApiError, type Schemas } from '@/lib/api/client';
import { useAskAboutDecision, useCompanies, useDecide, useReviewWithAdvisor } from '@/lib/api/hooks';
import { stepUp } from '@/lib/auth';
import { companyOf } from '@/lib/company';
import { ACTOR_FA, DECISION_KIND, DECISION_STATUS, RISK } from '@/lib/labels';
import { ago, cx, jDateTime, tokens, until, usd } from '@/lib/format';

type Decision = Schemas['Decision'];
const STEP_UP_KINDS = new Set(['hire', 'dismissal', 'budget_change']);
export const needsStepUp = (d: Decision) => d.action_class === 'A3' || STEP_UP_KINDS.has(d.kind);

function Fact({ label, children, mono }: { label: string; children: ReactNode; mono?: boolean }) {
  return (
    <div className="flex flex-col gap-1 rounded-[12px] bg-tile p-3">
      <span className="text-[11px] text-muted">{label}</span>
      <span className={cx('text-[14px] font-semibold text-ink', mono && 'fig')}>{children}</span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-1.5">
      <h3 className="text-[12px] font-semibold text-gold-ink">{title}</h3>
      {children}
    </section>
  );
}

function Payload({ d }: { d: Decision }) {
  const p = (d.payload ?? {}) as Record<string, unknown>;
  const list = (v: unknown) => (Array.isArray(v) ? (v as unknown[]).map(String) : []);
  if (d.kind === 'hire') {
    return (
      <Section title="قرارداد استخدام">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <Fact label="نقش">{String(p.title_fa ?? p.role ?? '—')}</Fact>
          <Fact label="دپارتمان" mono>{String(p.department ?? '—')}</Fact>
          <Fact label="مدل و فکر" mono>{String(p.model ?? '—').replace('claude-', '')} · {String(p.effort ?? '—')}</Fact>
          <Fact label="برآورد ماهانه" mono>{tokens(Number(p.quota_estimate_month ?? d.quota_estimate.tokens ?? 0))} tok</Fact>
        </div>
        {list(p.duties).length ? <ul className="mt-1 flex list-disc flex-col gap-1 pr-5 text-[13px] leading-6 text-sec marker:text-muted">{list(p.duties).map((x) => <li key={x}>{x}</li>)}</ul> : null}
        {list(p.permissions).length ? (
          <div className="flex flex-wrap gap-1.5 pt-1">{list(p.permissions).map((x) => <span key={x} className="fig rounded-[6px] bg-tile px-2 py-0.5 text-[11px] text-sec">{x}</span>)}</div>
        ) : null}
      </Section>
    );
  }
  if (d.kind === 'deploy') {
    const ci = (p.ci ?? {}) as Record<string, unknown>;
    const tests = (p.tests ?? {}) as Record<string, unknown>;
    return (
      <Section title="انتشار">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Fact label="ریپو" mono>{String(p.repo ?? '—')}</Fact>
          <Fact label="تغییر" mono>{String(p.diff_stat ?? '—')}</Fact>
          <Fact label="CI"><span className={ci.status === 'passed' ? 'text-pos' : 'text-neg'}>{ci.status === 'passed' ? 'سبز' : String(ci.status ?? '—')}</span></Fact>
          <Fact label="تست‌ها" mono>{String(tests.passed ?? 0)} ✓ · {String(tests.failed ?? 0)} ✗</Fact>
        </div>
        {p.rollout ? <p className="text-[13px] text-sec">روش انتشار: <span className="fig text-ink">{String(p.rollout)}</span></p> : null}
      </Section>
    );
  }
  if (d.kind === 'budget_change') {
    return (
      <Section title="تغییر بودجه">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Fact label="دامنه" mono>{JSON.stringify(p.scope ?? '—').replace(/["{}]/g, '')}</Fact>
          <Fact label="دوره">{String(p.period ?? '—')}</Fact>
          <Fact label="سقف توکن" mono>{p.token_limit ? tokens(Number(p.token_limit)) : '—'}</Fact>
          <Fact label="سقف دلار" mono>{p.usd_limit ? usd(String(p.usd_limit)) : '—'}</Fact>
        </div>
      </Section>
    );
  }
  return null;
}

export function DecisionDetail({ d, onDone }: { d: Decision; onDone?: () => void }) {
  const router = useRouter();
  const toast = useToast();
  const decide = useDecide();
  const ask = useAskAboutDecision();
  const review = useReviewWithAdvisor();
  const { data: companies } = useCompanies();
  const co = companyOf(companies, d.company);
  const [busy, setBusy] = useState(false);
  const [reject, setReject] = useState(false);
  const [ret, setRet] = useState(false);
  const [note, setNote] = useState('');
  const [reason, setReason] = useState<string>('');
  const k = DECISION_KIND[d.kind] ?? { fa: d.kind, icon: 'decision' as const };
  const r = RISK[d.risk] ?? RISK.medium!;
  const pending = d.status === 'pending';

  const fail = (e: unknown) => toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'انجام نشد.' });

  const seal = async () => {
    setBusy(true);
    try {
      const token = needsStepUp(d) ? await stepUp('decision.approve', d.ref) : undefined;
      const out = await decide.mutateAsync({ ref: d.ref, verdict: 'approve', stepUpToken: token });
      toast({ tone: 'ok', text: <>مُهر خورد. {out.resolution ? <span className="fig">{out.resolution}</span> : null} به {ACTOR_FA(d.proposer)} خبر داده شد.</> });
      onDone?.();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <article className="flex flex-col gap-5">
      <header className="flex items-start gap-4">
        <span className="flex size-12 flex-none items-center justify-center rounded-[14px] bg-tile text-gold-ink"><Icon name={k.icon} size={24} /></span>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted">
            <span>{k.fa}</span><span className="fig">{d.ref}</span><span>،</span><span>{co.nameFa}</span>
          </div>
          <h2 className="text-h2 font-semibold text-ink">{d.title}</h2>
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Pill tone={r.tone} dot>{r.fa}</Pill>
            <Pill tone={d.reversible ? 'silver' : 'warn'} icon={d.reversible ? 'refresh' : 'urgent'}>{d.reversible ? 'برگشت‌پذیر' : 'برگشت‌ناپذیر'}</Pill>
            <Pill tone="neutral"><span className="fig">{d.action_class}</span></Pill>
            {!pending ? <Pill tone={d.status === 'approved' ? 'gold' : 'neutral'}>{DECISION_STATUS[d.status] ?? d.status}</Pill> : null}
          </div>
        </div>
      </header>

      <div className="flex items-center gap-3 rounded-[14px] bg-card p-3">
        <Avatar kind={d.proposer.kind === 'agent' ? (d.proposer.code.endsWith('-CEO') ? 'ceo' : d.proposer.code.endsWith('-MGR') ? 'manager' : 'employee') : 'owner'} dept={d.proposer.code.split('-')[1]} size={40} />
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="text-[13px] font-semibold">{ACTOR_FA(d.proposer)}</span>
          <span className="text-[12px] text-muted"><span className="fig">{d.proposer.code}</span>، {ago(d.created_at)}</span>
        </div>
        {d.expires_at && pending ? <span className={cx('text-[12px]', new Date(d.expires_at).getTime() - Date.now() < 12 * 3600_000 ? 'text-warn' : 'text-muted')}>{until(d.expires_at)}</span> : null}
      </div>

      <Section title="چی"><Md text={d.what} /></Section>
      <Section title="چرا"><Md text={d.why} /></Section>
      <Payload d={d} />
      <Section title="مصرف و ریسک">
        <div className="grid grid-cols-2 gap-2">
          <Fact label="برآورد توکن" mono>{tokens(d.quota_estimate.tokens)}</Fact>
          <Fact label="هزینه‌ی معادل" mono>{usd(d.quota_estimate.usd)}</Fact>
        </div>
        {d.risk_note ? <p className="flex items-start gap-2 rounded-[12px] bg-warn-soft p-3 text-[13px] leading-6 text-ink"><span className="text-warn"><Icon name="urgent" size={18} /></span>{d.risk_note}</p> : null}
      </Section>

      {pending ? (
        <div className="flex flex-col items-center gap-4 rounded-[18px] bg-card p-5">
          <SealButton code={d.company} nameFa={co.nameFa} nameEn={co.nameEn} holding={co.holding} busy={busy} onSealed={seal} />
          {needsStepUp(d) ? <p className="text-center text-[12px] text-muted">این تصمیم با اثر انگشت یا چهره تأیید میشود.</p> : null}
          <div className="flex flex-wrap justify-center gap-2">
            <Button variant="secondary" icon="messages" loading={ask.isPending} onClick={async () => { try { const o = await ask.mutateAsync({ ref: d.ref, question: '' }); router.push(`/messages?thread=${encodeURIComponent(String((o as { thread?: string }).thread ?? d.thread ?? ''))}`); } catch (e) { fail(e); } }}>توی چت بپرس</Button>
            <Button variant="silver" icon="advisor" loading={review.isPending} onClick={async () => { try { await review.mutateAsync(d.ref); router.push('/advisor'); } catch (e) { fail(e); } }}>با مشاور بررسی کن</Button>
            <Button variant="secondary" icon="back" onClick={() => setRet(true)}>برگشت با یادداشت</Button>
            <Button variant="danger" icon="reject" onClick={() => setReject(true)}>رد</Button>
          </div>
        </div>
      ) : d.seal ? (
        <div className="flex items-center gap-4 rounded-[18px] bg-card p-4">
          <Seal code={d.company} nameFa={co.nameFa} nameEn={co.nameEn} holding={co.holding} state="sealed" size={72} />
          <div className="flex flex-col gap-1 text-[13px]">
            <span className="font-semibold">مُهر خورد، {jDateTime(d.seal.sealed_at)}</span>
            {d.resolution ? <span className="text-sec">مصوبه‌ی <span className="fig text-gold-ink">{d.resolution}</span></span> : null}
            {d.note ? <span className="text-muted">{d.note}</span> : null}
          </div>
        </div>
      ) : null}

      <Dialog open={reject} onOpenChange={setReject} title="رد این تصمیم" actions={<>
        <Button variant="danger" loading={decide.isPending} onClick={async () => { try { await decide.mutateAsync({ ref: d.ref, verdict: 'reject', note, reasonCode: reason || undefined }); setReject(false); toast({ tone: 'info', text: 'رد شد و دلیلش برای یادگیری ثبت شد.' }); onDone?.(); } catch (e) { fail(e); } }}>رد کن</Button>
        <Button variant="secondary" onClick={() => setReject(false)}>انصراف</Button>
      </>}>
        <div className="flex flex-col gap-3">
          <p>دلیل کمک میکند سیستم دفعه‌ی بعد بهتر پیشنهاد بدهد.</p>
          <div className="flex flex-wrap gap-2">
            {[['cost', 'هزینه'], ['risk', 'ریسک'], ['timing', 'زمان'], ['quality', 'کیفیت'], ['other', 'دیگر']].map(([v, l]) => <FilterChip key={v} selected={reason === v} onClick={() => setReason(v!)}>{l}</FilterChip>)}
          </div>
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} maxLength={5000} placeholder="توضیح (اختیاری)" className="rounded-[10px] border border-strong bg-tile p-3 text-[14px] text-ink outline-none focus:border-gold-ink" />
        </div>
      </Dialog>
      <Dialog open={ret} onOpenChange={setRet} title="برگشت با یادداشت" actions={<>
        <Button variant="primary" disabled={!note.trim()} loading={decide.isPending} onClick={async () => { try { await decide.mutateAsync({ ref: d.ref, verdict: 'return', note }); setRet(false); toast({ tone: 'info', text: 'به پیشنهاددهنده برگشت.' }); onDone?.(); } catch (e) { fail(e); } }}>بفرست</Button>
        <Button variant="secondary" onClick={() => setRet(false)}>انصراف</Button>
      </>}>
        <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={4} maxLength={5000} placeholder="چه چیزی باید عوض شود؟" className="w-full rounded-[10px] border border-strong bg-tile p-3 text-[14px] text-ink outline-none focus:border-gold-ink" />
      </Dialog>
    </article>
  );
}
