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
import { useNow } from '@/lib/store';
import { companyOf } from '@/lib/company';
import type { LifecycleRule, ShadowReport, Template } from '@/lib/api/v16';
import { AUTO_SEND, CHANNEL_FA, PURPOSE_FA, triggerFa } from '@/components/v16/bits';
import { DecisionOutcomes, ExpectedBlock, GovernancePayload } from '@/components/v17/cartable';
import { DeployPayloadBlock, EvaluationBlock, MemoBlock, PredictionLine, WaitingLine } from '@/components/v18/decision';
import { MediaDecisionPayload } from '@/components/v19/decision';
import type { Decision18 } from '@/lib/api/v18';
import { MEDIA_KINDS, sealTarget } from '@/lib/api/v19';
import { ACTOR_FA, DECISION_KIND, DECISION_STATUS, RISK } from '@/lib/labels';
import { ago, cx, jDateTime, modelLabel, tokens, until, usd } from '@/lib/format';

type Decision = Schemas['Decision'];
// code_session: its seal creates a Code Workshop grant (contract §5.1 ⟨1.4.3⟩). The round-two kinds are sealed the same way, each card
// bound to what it proposes (§18.13 ⟨1.4.5⟩); a server plan is sealed only on its own route, against its digest (§18.8).
// ⟨1.5⟩ the revenue-and-support cards (§19.9) are sealed the same way, each bound to its template, rule or shadow report; so are the
// governance kinds marked 🔏 in §20.11 (a charter amendment, a risk acceptance, an authority change), target = ref; and ⟨1.5⟩ §21.12 the
// monthly HR round's `evaluation` (payload v2). ⟨1.6⟩ §22.6: `media_publish`, `email_send` and `role_new` are sealed too; `email_send` on the
// message digest rather than the ref (sealTarget).
const STEP_UP_KINDS = new Set(['hire', 'dismissal', 'budget_change', 'code_session', 'protocol', 'tool_enable', 'errand_action', 'company_found', 'lesson_adoption', 'message_template', 'lifecycle_rule', 'support_go_live', 'charter_amendment', 'risk_acceptance', 'authority_change', 'evaluation', 'media_publish', 'email_send', 'role_new']);
export const needsStepUp = (d: Decision) => d.action_class === 'A3' || STEP_UP_KINDS.has(d.kind);
/** Kinds sealed on their own page, never by the cartable's approve: a server plan's seal is bound to its digest (§18.8). */
const OWN_ROUTE: Record<string, { href: (d: Decision) => string; fa: string }> = {
  // The card carries {plan, company}; the plan page sends a founding's plan on to its founding (§18.16).
  server_plan: { href: (d) => { const plan = (d.payload as { plan?: unknown } | null)?.plan; return typeof plan === 'string' ? `/founding/${plan}` : '/founding'; }, fa: 'مُهر طرح سرور' },
  // ⟨1.6⟩ §22.2: a series is sealed on its own page, on the series digest (`media.series`); sealing it decides the card.
  media_series: { href: (d) => { const s = (d.payload as { series?: unknown } | null)?.series; return typeof s === 'string' ? `/media/series?ref=${s}` : '/media/series'; }, fa: 'مُهر برنامه‌ی انتشار' },
};

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
          <Fact label="مدل و فکر" mono>{modelLabel(String(p.model ?? ''))} · {String(p.effort ?? '—')}</Fact>
          <Fact label="برآورد ماهانه" mono>{tokens(Number(p.quota_estimate_month ?? d.quota_estimate.tokens ?? 0))} tok</Fact>
        </div>
        {list(p.duties).length ? <ul className="mt-1 flex list-disc flex-col gap-1 pr-5 text-[13px] leading-6 text-sec marker:text-muted">{list(p.duties).map((x) => <li key={x}>{x}</li>)}</ul> : null}
        {list(p.permissions).length ? (
          <div className="flex flex-wrap gap-1.5 pt-1">{list(p.permissions).map((x) => <span key={x} className="fig rounded-[6px] bg-tile px-2 py-0.5 text-[11px] text-sec">{x}</span>)}</div>
        ) : null}
      </Section>
    );
  }
  // ⟨1.5⟩ §21.6: one definition of the deploy payload, bound to head_sha, with the real diff and the substitute's second review.
  if (d.kind === 'deploy') return <DeployPayloadBlock d={d as unknown as Decision18} />;
  // ⟨1.5⟩ §21.5: the monthly HR round's evaluation, payload v2.
  if (d.kind === 'evaluation') return <EvaluationBlock d={d as unknown as Decision18} />;
  if (d.kind === 'tool_enable') {
    const diff = (p.diff ?? {}) as Record<string, unknown>;
    const rows: [string, string, string][] = [['added', 'تازه', 'text-warn'], ['changed', 'عوض‌شده', 'text-warn'], ['removed', 'حذف‌شده', 'text-muted']];
    return (
      <Section title="ابزارهای این سرور عوض شده‌اند">
        <p className="text-[13px] leading-6 text-sec">سرور <span className="fig text-ink">{String(p.key ?? '—')}</span> خاموش است. با مُهر، دقیقاً با همین فهرست روشن میشود.</p>
        {rows.map(([key, fa, tone]) => (list(diff[key]).length ? (
          <div key={key} className="flex flex-wrap items-center gap-1.5">
            <span className={cx('text-[12px] font-semibold', tone)}>{fa}</span>
            {list(diff[key]).map((x) => <span key={x} className="fig rounded-[6px] bg-tile px-2 py-0.5 text-[11px] text-sec">{x}</span>)}
          </div>
        ) : null))}
      </Section>
    );
  }
  if (d.kind === 'a3_action' && p.action === 'mcp_call') {
    const args = (p.args ?? {}) as Record<string, unknown>;
    return (
      <Section title="فراخوانی ابزار بیرونی">
        <div className="grid grid-cols-2 gap-2">
          <Fact label="سرور" mono>{String(p.server ?? '—')}</Fact>
          <Fact label="ابزار" mono>{String(p.tool ?? '—')}</Fact>
        </div>
        {Object.keys(args).length ? (
          <dl className="flex flex-col gap-1 rounded-[12px] bg-tile p-3 text-[13px]">
            {Object.entries(args).map(([k, v]) => (
              <div key={k} className="flex gap-2"><dt className="fig flex-none text-muted">{k}</dt><dd className="fig min-w-0 break-words text-ink">{typeof v === 'string' ? v : JSON.stringify(v)}</dd></div>
            ))}
          </dl>
        ) : null}
        <p className="text-[12px] text-muted">با مُهر، همین فراخوانی با همین ورودی فقط یک بار اجرا میشود.</p>
      </Section>
    );
  }
  if (d.kind === 'support_go_live') {
    const r = (p.shadow_report ?? null) as ShadowReport | null;
    return (
      <Section title="شروع پشتیبانی">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Fact label="کانال">{CHANNEL_FA[String(p.channel)] ?? String(p.channel ?? '—')}</Fact>
          <Fact label="ارسال بی‌تو">{AUTO_SEND[String(p.auto_send)]?.fa ?? String(p.auto_send ?? '—')}</Fact>
          <Fact label="آستانه‌ی عین دانشنامه" mono>{p.verbatim_threshold != null ? String(p.verbatim_threshold) : '—'}</Fact>
          <Fact label="آستانه‌ی پیش‌نویس مستند" mono>{p.grounded_threshold != null ? String(p.grounded_threshold) : '—'}</Fact>
        </div>
        {r ? (
          <p className="text-[13px] leading-6 text-sec">
            آزمون سایه‌ی <span className="fig text-ink">{r.suite}</span>: <span className="fig text-ink">{r.total ? Math.round((r.correct / r.total) * 100) : 0}%</span> درست از <span className="fig">{r.total}</span>،
            خطای ایمنی <span className={cx('fig', r.safety_failures ? 'text-neg' : 'text-ink')}>{r.safety_failures}</span>، کد یا لینک اشتباه <span className={cx('fig', r.wrong_codes ? 'text-neg' : 'text-ink')}>{r.wrong_codes}</span> · {r.pass ? 'قبول' : 'رد'}.
          </p>
        ) : null}
        <p className="text-[12px] text-muted">آستانه‌ها مسیر ویرایش ندارند؛ عوض کردنشان یعنی آزمون سایه‌ی تازه و کارت تازه. با مُهر، کانال روشن و آستانه‌ها همین اعداد میشوند.</p>
      </Section>
    );
  }
  if (d.kind === 'message_template') {
    const t = (p.template ?? {}) as Partial<Template>;
    const sha = String(p.sha256 || t.sha256 || '');
    return (
      <Section title={`قالب ${PURPOSE_FA[String(t.purpose)] ?? ''}`}>
        <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted"><span className="fig">{t.ref}@{t.version}</span>{(t.variables ?? []).map((v) => <span key={v} className="fig rounded-[6px] bg-tile px-2 py-0.5 text-sec">{`{{${v}}}`}</span>)}</div>
        <p className="whitespace-pre-wrap rounded-[12px] bg-tile p-3 text-[14px] leading-7 text-ink">{t.body_fa}</p>
        {sha ? <p className="text-[11px] text-muted">مُهر به همین متن بسته است: <span className="fig">sha256 {sha.slice(0, 16)}…</span></p> : null}
      </Section>
    );
  }
  if (d.kind === 'lifecycle_rule') {
    const r = (p.rule ?? {}) as Partial<LifecycleRule>;
    const l = (p.limits ?? r.limits ?? null) as LifecycleRule['limits'] | null;
    return (
      <Section title="قاعده‌ی پیام">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Fact label="قاعده" mono>{r.ref}@{r.version}</Fact>
          <Fact label="کی">{r.trigger ? triggerFa(r.trigger) : '—'}</Fact>
          <Fact label="قالب" mono>{String(p.template ?? r.template ?? '—')}</Fact>
          <Fact label="کانال">{CHANNEL_FA[String(r.channel)] ?? '—'}</Fact>
        </div>
        {l ? <p className="text-[13px] leading-6 text-sec">هر مشتری حداکثر یک بار در {l.per_customer_days} روز، سقف روزانه <span className="fig">{l.daily_cap}</span>، ساعت سکوت <span className="fig">{l.quiet_hours[0]}–{l.quiet_hours[1]}</span>{l.max_follow_ups ? <>، حداکثر {l.max_follow_ups} پیگیری</> : null}.</p> : null}
        <p className="text-[12px] text-muted">مُهر این کارت تأیید پیشاپیش توست؛ قاعده فقط تا وقتی قالبِ همین نسخه مُهرشده است اجرا میشود.</p>
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
  // ⟨1.6⟩ the media studio and the legal counsel (§22.6)
  if ((MEDIA_KINDS as readonly string[]).includes(d.kind)) return <MediaDecisionPayload d={d} />;
  // ⟨1.5⟩ the governance kinds (§20.11)
  return <GovernancePayload d={d} />;
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
  const now = useNow();

  const fail = (e: unknown) => toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'انجام نشد.' });

  const seal = async () => {
    setBusy(true);
    try {
      const token = needsStepUp(d) ? await stepUp('decision.approve', sealTarget(d)) : undefined;
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
        {d.expires_at && pending ? <span className={cx('text-[12px]', !!now && new Date(d.expires_at).getTime() - now < 12 * 3600_000 ? 'text-warn' : 'text-muted')}>{until(d.expires_at)}</span> : null}
      </div>
      {/* ⟨1.5⟩ §21.8: how long it has waited and which reminders went out. */}
      <WaitingLine d={d as unknown as Decision18} />

      <Section title="چی"><Md text={d.what} /></Section>
      <Section title="چرا"><Md text={d.why} /></Section>
      <Payload d={d} />
      {/* ⟨1.5⟩ §20.6: what the card promises, and its 30/60/90-day reviews once sealed. */}
      <ExpectedBlock d={d} />
      <DecisionOutcomes d={d} />
      {/* ⟨1.5⟩ §21.1: the advisor's memo, standard or devil's advocate, with the substitutes' second and third opinions. */}
      <MemoBlock d={d as unknown as Decision18} />
      <Section title="مصرف و ریسک">
        <div className="grid grid-cols-2 gap-2">
          <Fact label="برآورد توکن" mono>{tokens(d.quota_estimate.tokens)}</Fact>
          <Fact label="هزینه‌ی معادل" mono>{usd(d.quota_estimate.usd)}</Fact>
        </div>
        {d.risk_note ? <p className="flex items-start gap-2 rounded-[12px] bg-warn-soft p-3 text-[13px] leading-6 text-ink"><span className="text-warn"><Icon name="urgent" size={18} /></span>{d.risk_note}</p> : null}
      </Section>

      {pending ? (
        <div className="flex flex-col items-center gap-4 rounded-[18px] bg-card p-5">
          {OWN_ROUTE[d.kind] ? (
            <Button variant="primary" icon="seal" onClick={() => router.push(OWN_ROUTE[d.kind]!.href(d))}>{OWN_ROUTE[d.kind]!.fa}</Button>
          ) : (
            <SealButton code={d.company} nameFa={co.nameFa} nameEn={co.nameEn} holding={co.holding} busy={busy} onSealed={seal} />
          )}
          {needsStepUp(d) || OWN_ROUTE[d.kind] ? <p className="text-center text-[12px] text-muted">این تصمیم با اثر انگشت یا چهره تأیید میشود.</p> : null}
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
      ) : d.decided_at || d.note ? (
        // Rejected, returned, expired or withdrawn: what happened, when, by whom, and why.
        <div className="flex items-start gap-3 rounded-[18px] bg-card p-4 text-[13px]">
          <span className="mt-0.5 text-sec"><Icon name={d.status === 'rejected' ? 'reject' : d.status === 'returned' ? 'back' : d.status === 'expired' ? 'time' : 'close'} size={20} /></span>
          <div className="flex flex-col gap-1">
            <span className="font-semibold">{DECISION_STATUS[d.status] ?? d.status}{d.decided_at ? `، ${jDateTime(d.decided_at)}` : ''}{d.decided_by ? <span className="font-normal text-sec">، {ACTOR_FA(d.decided_by)}</span> : null}</span>
            {d.note ? <span className="text-muted">{d.note}</span> : null}
          </div>
        </div>
      ) : null}
      {/* ⟨1.5⟩ §21.10: the digital CEO's sealed prediction, shown only once the owner has decided. */}
      <PredictionLine d={d as unknown as Decision18} />

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
