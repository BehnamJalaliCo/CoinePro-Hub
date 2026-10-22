'use client';

import { useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Md, MdInline } from '@/components/ui/md';
import { Dialog, Sheet } from '@/components/ui/overlay';
import { Card, Empty, Pill, SectionTitle, Segmented, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ActorAvatar, REVIEW_CHECK, RefChip } from '@/components/v17/bits';
import { MODEL_ORDER, faError, useDepartments19, useMandateAction, useRoleDraft, useRoleDraftAction, useRoleDrafts, type Department19, type Mandate, type ModelCeiling, type RoleDraft } from '@/lib/api/v19';
import { ACTOR_FA, DEPT_FA, ROLE_FA } from '@/lib/labels';
import { ago, cx, jDateTime, modelLabel, tokens } from '@/lib/format';
import { Block, ROLE_GATES, ROLE_STATE } from './bits';

const area = 'w-full rounded-[10px] border border-strong bg-card p-3 text-[14px] leading-6 text-ink outline-none focus:border-gold-ink';
const lines = (s: string) => s.split('\n').map((x) => x.trim()).filter(Boolean);

// ------------------------------------------------------------------ a role written on demand (§22.5) --
function Gates({ d }: { d: RoleDraft }) {
  const idx = ROLE_GATES.findIndex((g) => g.state === d.state);
  const stopped = d.state === 'rejected' || d.state === 'retired';
  return (
    <ol className="flex flex-wrap items-center gap-1" aria-label="دروازه‌های نقش تازه">
      {ROLE_GATES.map((g, i) => {
        const done = !stopped && (idx > i || d.state === 'active');
        const now = idx === i && d.state !== 'active';
        return <li key={g.state} className={cx('flex h-7 items-center gap-1 rounded-full px-2.5 text-[11px]', now ? 'bg-gold-soft font-semibold text-gold-ink' : done ? 'bg-pos-soft text-pos' : 'bg-tile text-muted')}><Icon name={done ? 'seal' : 'time'} size={12} />{g.fa}</li>;
      })}
      {stopped ? <li><Pill tone={ROLE_STATE[d.state]!.tone} icon={d.state === 'rejected' ? 'reject' : 'pause'}>{ROLE_STATE[d.state]!.fa}</Pill></li> : null}
    </ol>
  );
}

export function RoleDraftSheet({ refId, onClose }: { refId: string; onClose: () => void }) {
  const q = useRoleDraft(refId);
  const act = useRoleDraftAction();
  const toast = useToast();
  const [confirm, setConfirm] = useState(false);
  const d = q.data;
  const retire = async () => {
    if (!d) return;
    try { await act.retire.mutateAsync(d.ref); setConfirm(false); toast({ tone: 'info', text: 'بازنشسته شد؛ استخدام تازه روی آن نیست و کارمندهایش تا جابه‌جایی کار میکنند.' }); }
    catch (e) { toast({ tone: 'error', text: faError(e) }); }
  };
  return (
    <Sheet open onOpenChange={(v) => !v && onClose()} width={680}
      title={d ? <span className="flex flex-wrap items-center gap-2">{d.title_fa || 'نقش تازه'}<span className="fig text-[13px] text-muted">{d.ref}</span></span> : '…'}
      description={d ? <span>{DEPT_FA[d.department] ?? d.department} <span className="fig">{d.company}</span>{d.role ? <> · <span className="fig">{d.role}</span></> : null}{d.title_en ? <> · <span className="fig">{d.title_en}</span></> : null}</span> : undefined}
      footer={d?.state === 'active' ? (
        <div className="flex flex-wrap items-center gap-3"><span className="min-w-0 flex-1 text-[12px] text-muted">منشور روی سرور است، فقط برای همین شرکت و دپارتمان؛ {d.hires ? `${d.hires} نفر رویش کار میکنند.` : 'هنوز کسی رویش استخدام نشده.'}</span><Button variant="danger" icon="pause" onClick={() => setConfirm(true)}>بازنشسته کن</Button></div>
      ) : undefined}>
      {q.error ? <Empty icon="urgent" title={faError(q.error)} /> : !d ? <Skeleton className="h-96" /> : (
        <div className="flex flex-col gap-5">
          <Gates d={d} />
          {d.state_note_fa ? <div className="flex items-start gap-2 rounded-[12px] bg-neg-soft p-3 text-[13px] leading-6 text-ink"><span className="text-neg"><Icon name="urgent" size={16} /></span><span className="min-w-0 flex-1"><MdInline text={d.state_note_fa} /></span></div> : null}
          <div className="flex flex-wrap items-center gap-3 text-[12px] text-muted">
            {d.requested_by ? <span className="flex items-center gap-1.5"><ActorAvatar a={d.requested_by} size={18} />خواسته‌ی {ACTOR_FA(d.requested_by)}</span> : null}
            {d.written_by ? <span className="flex items-center gap-1.5"><ActorAvatar a={d.written_by} size={18} />نوشته‌ی {ACTOR_FA(d.written_by)}</span> : null}
            <span>{ago(d.created_at)}</span>
          </div>
          {d.brief_md ? <Block title="خواسته"><p className="rounded-[12px] bg-tile p-3 text-[13px] leading-6 text-ink">«{d.brief_md}»</p></Block> : null}
          {d.state === 'drafting' ? <p className="rounded-[12px] bg-tile p-3 text-[13px] leading-6 text-sec">مدیر دپارتمان بیدار شد و منشور را مینویسد: اول میگوید کدام منشور موجود را مقایسه کرد و چرا جواب نمیداد، بعد متن، ابزارها داخل سقف دپارتمان، مدل و دست‌کم سه مورد آزمون.</p> : null}
          {d.why_md ? <Block title="چرا یک نقش تازه"><Md text={d.why_md} className="flex flex-col gap-1.5 text-[13px] leading-6 text-ink" />
            {d.compared?.length ? <span className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted">مقایسه با:{d.compared.map((r) => <span key={r} className="rounded-full bg-tile px-2 py-0.5 text-sec">{ROLE_FA[r] ?? r}</span>)}</span> : null}
            {d.originality ? <span className={cx('text-[11px]', d.originality.ok ? 'text-muted' : 'text-neg')}>چک تکراری نبودن (قاعده): {d.originality.ok ? 'قبول' : 'رد'}{d.originality.note_fa ? ` · ${d.originality.note_fa}` : ''}</span> : null}
          </Block> : null}
          {d.model ? (
            <Block title="مدل، ابزار و سقف">
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {[['مدل', modelLabel(d.model)], ['فکر', d.effort], ['قدم هر اجرا', String(d.limits.steps_per_run)], ['سقف هر اجرا', `${tokens(d.limits.tokens_per_run)} tok`]].map(([l, v]) => (
                  <div key={l} className="flex flex-col gap-1 rounded-[12px] bg-tile p-3"><span className="text-[11px] text-muted">{l}</span><span className="fig text-[14px] font-semibold text-ink">{v}</span></div>
                ))}
              </div>
              <div className="flex flex-wrap gap-1.5">{d.tools.map((t) => <span key={t} className="fig rounded-[6px] bg-tile px-2 py-0.5 text-[11px] text-sec">{t}</span>)}</div>
              <p className="text-[11px] leading-5 text-muted">سقف سخت با کد: ابزارها زیرمجموعه‌ی سقف دپارتمان، هرگز قدرت نظارت، استخدام، تصمیم نقش، کلید توقف یا پیام مستقیم به تو؛ مدل حداکثر سقف دپارتمان؛ سقف‌ها حداکثر همان مدیر. A3 همیشه پیشنهاد میماند.</p>
            </Block>
          ) : null}
          {d.charter_md ? <Block title="متن منشور"><Md text={d.charter_md} className="fig flex max-h-[320px] flex-col gap-2 overflow-y-auto rounded-[12px] bg-tile p-3 text-left text-[13px] leading-6 text-ink" /></Block> : null}
          {d.review ? (
            <Block title={<span className="flex items-center gap-2">بازبینی ناظر کل <Pill tone={d.review.verdict === 'pass' ? 'pos' : d.review.verdict === 'reject' ? 'neg' : 'warn'} dot>{d.review.verdict === 'pass' ? 'قبول' : d.review.verdict === 'reject' ? 'رد' : 'اصلاح'}</Pill></span>}>
              <div className="flex flex-wrap gap-2">{Object.entries(d.review.checks).map(([k, ok]) => <span key={k} className={cx('flex items-center gap-1 text-[12px]', ok ? 'text-pos' : 'text-neg')}><Icon name={ok ? 'seal' : 'urgent'} size={12} />{REVIEW_CHECK[k] ?? k}</span>)}</div>
              <span className="fig text-[11px] text-muted">sha256 {d.review.sha256.slice(0, 16)}… · {ACTOR_FA(d.review.by)}</span>
            </Block>
          ) : d.state === 'in_review' ? <p className="text-[12px] text-muted">ناظر کل متن کامل ماسک‌شده را با sha256 میخواند؛ پنج چک: تزریق، رمز، تناقض، سیاست و سقف.</p> : null}
          {d.eval.cases.length ? (
            <Block title={<span className="flex items-center gap-2">آزمون خودش <span className="fig font-normal text-muted">{d.eval.suite}</span>{d.eval_run ? (d.eval_run.state === 'running' || d.eval_run.state === 'queued' ? <Pill tone="lapis" live>در حال اجرا</Pill> : <Pill tone={d.eval_run.passed ? 'pos' : 'neg'} dot>{d.eval_run.passed ? 'قبول' : 'رد'} · {d.eval_run.score}</Pill>) : null}</span>}>
              <ol className="flex flex-col gap-1.5">
                {d.eval.cases.map((c) => {
                  const r = d.eval_run?.cases?.find((x) => x.id === c.id);
                  return (
                    <li key={c.id} className="flex flex-col gap-1 rounded-[10px] bg-tile p-2.5 text-[12px]">
                      <span className="flex items-center gap-2"><span className="fig text-muted">{c.id}</span><span className="min-w-0 flex-1 text-ink">{c.input_md}</span><span className="text-muted">وزن {c.weight}</span>{r ? <span className="fig text-sec">{r.score}</span> : null}</span>
                      <span className="text-muted">معیار: {c.rubric_md}</span>
                    </li>
                  );
                })}
              </ol>
              <p className="text-[11px] text-muted">باید قبول شود؛ همین نمره خط پایه‌ی خود نقش میشود.</p>
            </Block>
          ) : null}
          {d.state === 'active' || d.approver ? (
            <p className="flex flex-wrap items-center gap-2 text-[12px] text-sec"><Icon name="seal" size={14} />تأیید {ACTOR_FA(d.approver)}{d.activated_at ? `، ${jDateTime(d.activated_at)}` : ''}{d.decision_ref ? <RefChip r={d.decision_ref} /> : null}{d.retired_at ? <span className="text-muted">· بازنشسته {jDateTime(d.retired_at)}</span> : null}</p>
          ) : null}
        </div>
      )}
      <Dialog open={confirm} onOpenChange={setConfirm} title="بازنشسته کردن نقش" actions={<>
        <Button variant="danger" icon="pause" loading={act.retire.isPending} onClick={retire}>بازنشسته کن</Button>
        <Button variant="secondary" onClick={() => setConfirm(false)}>نه</Button>
      </>}><p>کسی دیگر روی این نقش استخدام نمیشود؛ کارمندهایی که دارد تا جابه‌جایی یا برکناری کار میکنند. منشورش در تاریخچه میماند و نسخه‌ی تازه، پیش‌نویس تازه است.</p></Dialog>
    </Sheet>
  );
}

function AskRole({ company, department, onAsked }: { company: string; department: string; onAsked: (ref: string) => void }) {
  const act = useRoleDraftAction();
  const toast = useToast();
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [brief, setBrief] = useState('');
  const submit = async () => {
    try {
      const d = await act.ask.mutateAsync({ company, department, brief_md: brief.trim(), key });
      toast({ tone: 'ok', text: <>خواسته رسید (<span className="fig">{d.ref}</span>)؛ مدیر دپارتمان بیدار شد تا منشورش را بنویسد.</> });
      setBrief(''); setKey(crypto.randomUUID()); onAsked(d.ref);
    } catch (e) { toast({ tone: 'error', text: faError(e) }); }
  };
  return (
    <div className="flex flex-col gap-2 rounded-[12px] bg-tile p-3">
      <span className="text-[13px] font-semibold text-ink">نقش تازه بخواه</span>
      <textarea value={brief} onChange={(e) => setBrief(e.target.value)} rows={2} maxLength={2000} placeholder="مثلاً: یه تدوینگر پادکست میخوام برای نسخه‌ی صوتی تحلیل هفتگی" aria-label="شرح نقش تازه" className={area} />
      <div className="flex items-center gap-2"><Button size="sm" variant="secondary" icon="send" disabled={brief.trim().length < 6} loading={act.ask.isPending} onClick={submit}>بفرست به مدیر دپارتمان</Button><span className="text-[11px] text-muted">مدیر مینویسد؛ ناظر، آزمون و تأیید بعد از آن.</span></div>
    </div>
  );
}

function DraftRow({ d, onOpen }: { d: RoleDraft; onOpen: (ref: string) => void }) {
  const st = ROLE_STATE[d.state] ?? ROLE_STATE.drafting!;
  return (
    <button type="button" onClick={() => onOpen(d.ref)} className="flex w-full items-center gap-3 rounded-[12px] bg-tile p-3 text-start hover:bg-hover">
      <span className="text-sec"><Icon name="department" size={18} /></span>
      <span className="flex min-w-0 flex-1 flex-col"><span className="truncate text-[13px] font-semibold text-ink">{d.title_fa || 'در حال نوشتن'}</span><span className="text-[11px] text-muted"><span className="fig">{d.ref}</span>{d.role ? <> · <span className="fig">{d.role}</span></> : null} · {DEPT_FA[d.department] ?? d.department}</span></span>
      <Pill tone={st.tone} dot={!st.live} live={st.live} className="h-5 text-[11px]">{st.fa}</Pill>
    </button>
  );
}

// ------------------------------------------------------------------ a department by mandate and identity (§22.1) --
function MandateEditor({ company, d, onDone }: { company: string; d: Department19; onDone: () => void }) {
  const act = useMandateAction();
  const toast = useToast();
  const m = d.mandate;
  const [from, setFrom] = useState(m?.from_fa ?? '');
  const [to, setTo] = useState(m?.to_fa ?? '');
  const [outputs, setOutputs] = useState((m?.outputs_fa ?? []).join('\n'));
  const [bounds, setBounds] = useState((m?.boundaries_fa ?? []).join('\n'));
  const [tools, setTools] = useState((m?.tool_ceiling ?? []).join('\n'));
  const [model, setModel] = useState<ModelCeiling>(m?.model_ceiling ?? 'claude-sonnet-5-5');
  const [identity, setIdentity] = useState(d.identity_md ?? '');
  const ok = from.trim() && to.trim() && lines(outputs).length;
  const save = async () => {
    const mandate: Mandate = { from_fa: from.trim(), to_fa: to.trim(), outputs_fa: lines(outputs), boundaries_fa: lines(bounds), tool_ceiling: lines(tools), model_ceiling: model };
    try { await act.mutateAsync({ company, d, body: { mandate, identity_md: identity.trim() } }); toast({ tone: 'ok', text: 'ذخیره شد؛ از اجرای بعدی، مدیر و هر کارمند این دپارتمان همین شخصیت را میخوانند.' }); onDone(); }
    catch (e) { toast({ tone: 'error', text: faError(e) }); }
  };
  return (
    <div className="flex flex-col gap-3 text-[13px]">
      <label className="flex flex-col gap-1.5 font-semibold text-sec">مبدأ: از چه شروع میکند<textarea value={from} onChange={(e) => setFrom(e.target.value)} rows={2} className={area} /></label>
      <label className="flex flex-col gap-1.5 font-semibold text-sec">مقصد: به کجا باید برسد<textarea value={to} onChange={(e) => setTo(e.target.value)} rows={2} className={area} /></label>
      <label className="flex flex-col gap-1.5 font-semibold text-sec">خروجی‌ها (هر خط یکی)<textarea value={outputs} onChange={(e) => setOutputs(e.target.value)} rows={3} className={area} /></label>
      <label className="flex flex-col gap-1.5 font-semibold text-sec">مرزها (هر خط یکی)<textarea value={bounds} onChange={(e) => setBounds(e.target.value)} rows={3} className={area} /></label>
      <label className="flex flex-col gap-1.5 font-semibold text-sec">سقف ابزار (هر خط یک ابزار)<textarea dir="ltr" value={tools} onChange={(e) => setTools(e.target.value)} rows={4} className={cx(area, 'fig text-left text-[12px]')} /></label>
      <div className="flex flex-col gap-1.5"><span className="font-semibold text-sec">سقف مدل</span><Segmented label="سقف مدل" value={model} onChange={setModel} options={MODEL_ORDER.map((x) => ({ value: x, label: <span className="fig">{modelLabel(x)}</span> }))} /></div>
      <label className="flex flex-col gap-1.5 font-semibold text-sec">شخصیت دپارتمان (لحن، سلیقه؛ هر عضو میخواند)<textarea value={identity} onChange={(e) => setIdentity(e.target.value)} rows={5} className={area} /></label>
      <div className="flex flex-wrap items-center gap-2"><Button variant="primary" icon="seal" disabled={!ok} loading={act.isPending} onClick={save}>با گذرکلید ذخیره کن</Button><Button variant="ghost" onClick={onDone}>انصراف</Button>
        <span className="text-[11px] text-muted">مُهر به hash همین متن بسته است.</span></div>
    </div>
  );
}

export function DepartmentSheet({ company, code, onClose, onRole }: { company: string; code: string; onClose: () => void; onRole: (ref: string) => void }) {
  const deps = useDepartments19(company);
  const drafts = useRoleDrafts({ company, department: code });
  const [edit, setEdit] = useState(false);
  const d = deps.data?.find((x) => x.code === code);
  const m = d?.mandate;
  return (
    <Sheet open onOpenChange={(v) => !v && onClose()} width={680}
      title={d ? <span className="flex items-center gap-2">{d.name_fa}<span className="fig text-[13px] text-muted">{d.code}</span></span> : '…'}
      description={d ? <>دپارتمان با مأموریت و شخصیتش تعریف میشود، نه با فهرست نقش‌ها؛ {d.manager_title_fa} هر نقشی که کار لازم دارد مینویسد.</> : undefined}>
      {!d ? <Skeleton className="h-96" /> : edit ? <MandateEditor company={company} d={d} onDone={() => setEdit(false)} /> : (
        <div className="flex flex-col gap-5">
          {m ? (
            <Block title="مأموریت: مبدأ و مقصد" action={<Button size="sm" variant="text" icon="edit" onClick={() => setEdit(true)}>ویرایش</Button>}>
              <div className="grid gap-2 sm:grid-cols-2">
                <div className="flex flex-col gap-1 rounded-[12px] bg-tile p-3"><span className="text-[11px] text-muted">مبدأ</span><span className="text-[13px] leading-6 text-ink">{m.from_fa}</span></div>
                <div className="flex flex-col gap-1 rounded-[12px] bg-gold-soft p-3"><span className="text-[11px] text-gold-ink">مقصد</span><span className="text-[13px] leading-6 text-ink">{m.to_fa}</span></div>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="flex flex-col gap-1"><span className="text-[11px] text-muted">خروجی‌ها</span><ul className="flex list-disc flex-col gap-0.5 pr-5 text-[13px] leading-6 text-ink marker:text-muted">{m.outputs_fa.map((x) => <li key={x}>{x}</li>)}</ul></div>
                <div className="flex flex-col gap-1"><span className="text-[11px] text-muted">مرزها</span><ul className="flex list-disc flex-col gap-0.5 pr-5 text-[13px] leading-6 text-ink marker:text-muted">{m.boundaries_fa.map((x) => <li key={x}>{x}</li>)}</ul></div>
              </div>
              <div className="flex flex-col gap-1.5">
                <span className="text-[11px] text-muted">سقف ابزار و مدل (هیچ نقشی بیشتر از این نمیگیرد)</span>
                <div className="flex flex-wrap gap-1.5"><Pill tone="silver"><span className="fig">{modelLabel(m.model_ceiling)}</span></Pill>{m.tool_ceiling.map((t) => <span key={t} className="fig rounded-[6px] bg-tile px-2 py-0.5 text-[11px] text-sec">{t}</span>)}</div>
              </div>
            </Block>
          ) : <Empty icon="department" title="هنوز مأموریتی ثبت نشده" action={<Button size="sm" variant="secondary" icon="edit" onClick={() => setEdit(true)}>بنویس</Button>} />}
          {d.identity_md ? <Block title="شخصیت دپارتمان"><Md text={d.identity_md} className="flex flex-col gap-1.5 rounded-[12px] bg-tile p-3 text-[13px] leading-6 text-ink" /><span className="text-[11px] text-muted">بعد از منشور و پیش از مهارت‌ها در دستور مدیر و هر کارمند این دپارتمان میآید؛ نسخه‌اش روی هر اجرا ثبت میشود.</span></Block> : null}
          <Block title="تیم شروع (پیشنهاد، نه محدودیت)">
            {d.team?.length ? (
              <ul className="flex flex-col gap-1.5">{d.team.map((t) => (
                <li key={t.role} className="flex flex-wrap items-center gap-2 rounded-[10px] bg-tile px-3 py-2 text-[12px]"><span className="font-semibold text-ink">{t.title_fa}</span><span className="fig text-muted">{t.role}</span>{t.first ? <Pill tone="gold">اول</Pill> : null}<span className="min-w-0 flex-1 text-muted">{t.why_fa}</span></li>
              ))}</ul>
            ) : <p className="text-[12px] text-muted">قالب برای این دپارتمان هنوز منشور شروعی ندارد؛ مدیرش هر نقشی که کار لازم داشت مینویسد.</p>}
          </Block>
          <Block title="نقش‌هایی که مدیر نوشته">
            {drafts.isLoading ? <Skeleton className="h-16" /> : drafts.data?.length ? <div className="flex flex-col gap-1.5">{drafts.data.map((x) => <DraftRow key={x.ref} d={x} onOpen={onRole} />)}</div> : <p className="text-[12px] text-muted">هنوز نقشی ننوشته.</p>}
            {company !== 'HQ' || code !== 'LEGAL' ? <AskRole company={company} department={code} onAsked={onRole} /> : null}
          </Block>
        </div>
      )}
    </Sheet>
  );
}

/** The company's roles written on demand, on the people tab: what each department grew beyond the template. */
export function RolesOnDemand({ company, onOpen }: { company: string; onOpen: (ref: string) => void }) {
  const q = useRoleDrafts({ company });
  const xs = q.data ?? [];
  return (
    <Card className="flex flex-col gap-3 p-4">
      <SectionTitle title="نقش‌های تازه" note="مدیر هر دپارتمان مینویسد؛ ناظر، آزمون خودش و تأیید، بعد قابل استخدام" />
      {q.isLoading ? <Skeleton className="h-16" /> : !xs.length ? <p className="text-[13px] text-muted">هنوز نقشی بیرون از قالب نوشته نشده. روی هر دپارتمان بزن و «نقش تازه بخواه».</p> : (
        <div className="grid gap-2 md:grid-cols-2">{xs.map((d) => <DraftRow key={d.ref} d={d} onOpen={onOpen} />)}</div>
      )}
    </Card>
  );
}
