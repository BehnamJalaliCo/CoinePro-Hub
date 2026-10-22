'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Icon } from '@/components/icon';
import { SealButton } from '@/components/cartable/seal-button';
import { Button } from '@/components/ui/button';
import { Md, MdInline } from '@/components/ui/md';
import { Dialog, Sheet } from '@/components/ui/overlay';
import { Empty, ErrorState, FilterChip, Pill, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ActorAvatar, CoMark, RefChip } from '@/components/v17/bits';
import { useCompanies, useDecide } from '@/lib/api/hooks';
import { faError, sealTarget, useCase, useCaseAction, type CaseEmail, type CaseKind, type EmailDraft, type LegalCase } from '@/lib/api/v19';
import { stepUp } from '@/lib/auth';
import { companyOf } from '@/lib/company';
import { ACTOR_FA } from '@/lib/labels';
import { useNow } from '@/lib/store';
import { ago, cx, jDateTime, until } from '@/lib/format';
import { CaseHolds } from '@/components/v20/holds';
import { Block, CASE_KIND, CASE_STATUS, FileChip, TIMELINE } from './bits';

const field = 'h-10 w-full rounded-[10px] border border-strong bg-card px-3 text-[14px] text-ink outline-none focus:border-gold-ink';

export function CaseRow({ c, selected, onOpen }: { c: LegalCase; selected: boolean; onOpen: () => void }) {
  const st = CASE_STATUS[c.status] ?? CASE_STATUS.open!;
  const next = [...c.deadlines].sort((a, b) => a.at.localeCompare(b.at))[0];
  return (
    <button type="button" onClick={onOpen} className={cx('flex w-full flex-col gap-1.5 rounded-[12px] p-3 text-start transition-colors', selected ? 'tahrir bg-gold-soft' : 'hover:bg-hover')}>
      <span className="flex items-center gap-2"><CoMark code={c.company} height={11} /><span className="min-w-0 flex-1 truncate text-[14px] font-semibold text-ink">{c.title_fa}</span></span>
      <span className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
        <Pill tone={st.tone} dot live={st.live} className="h-5 text-[11px]">{st.fa}</Pill><span className="fig">{c.ref}</span><span>{CASE_KIND[c.kind] ?? c.kind}</span><span>{ago(c.updated_at)}</span>
      </span>
      {next ? <span className="flex items-center gap-1 text-[11px] text-warn"><Icon name="time" size={12} />{next.what_fa}، {until(next.at)}</span> : null}
    </button>
  );
}

/** The exact message: from, to, cc, subject, body, attachment hashes and the digest the seal is bound to (§22.4). */
export function ExactEmail({ e }: { e: EmailDraft }) {
  return (
    <>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 rounded-[12px] bg-card p-3 text-[12px]">
        <dt className="text-muted">از</dt><dd dir="ltr" className="fig text-start text-ink">{e.from}</dd>
        <dt className="text-muted">به</dt><dd dir="ltr" className="fig break-all text-start text-ink">{e.to.join(', ')}</dd>
        {e.cc.length ? <><dt className="text-muted">رونوشت</dt><dd dir="ltr" className="fig break-all text-start text-ink">{e.cc.join(', ')}</dd></> : null}
        <dt className="text-muted">موضوع</dt><dd dir={e.lang === 'en' ? 'ltr' : 'rtl'} className={cx('text-start font-semibold text-ink', e.lang === 'en' && 'fig')}>{e.subject}</dd>
      </dl>
      <div dir={e.lang === 'en' ? 'ltr' : 'rtl'} className={cx('max-h-[360px] overflow-y-auto whitespace-pre-wrap rounded-[12px] bg-card p-3 text-start text-[13px] leading-6 text-ink', e.lang === 'en' && 'fig')}>{e.body_md}</div>
      {e.attachments.length ? <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted">پیوست:{e.attachments.map((a) => <span key={a.id} className="flex items-center gap-1"><FileChip f={a} /><span className="fig">sha256 {a.sha256.slice(0, 8)}</span></span>)}</div> : null}
      <p className="text-[11px] leading-5 text-muted">مُهر به همین پیام بسته است: <span className="fig">digest {e.digest.slice(0, 16)}…</span>. همان یک بار فرستاده میشود؛ هر تغییری بعد از دیدن تو کارت تازه میخواهد. هیچ ایمیلی خودکار فرستاده نمیشود.</p>
    </>
  );
}

/** The exact message the seal is bound to (§22.4): nothing is ever sent without it, and any change is a new card. */
function EmailToSeal({ e, c }: { e: CaseEmail; c: LegalCase }) {
  const decide = useDecide();
  const qc = useQueryClient();
  const toast = useToast();
  const { data: companies } = useCompanies();
  const co = companyOf(companies, c.company);
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<null | 'reject' | 'return'>(null);
  const [note, setNote] = useState('');
  const done = () => Promise.all(['legal', 'threads', 'messages'].map((k) => qc.invalidateQueries({ queryKey: [k] })));
  const seal = async () => {
    if (!e.decision_ref) return;
    setBusy(true);
    try {
      // Bound to the message digest, not to the card's ref (§22.6).
      const token = await stepUp('decision.approve', sealTarget({ kind: 'email_send', ref: e.decision_ref, payload: e }));
      await decide.mutateAsync({ ref: e.decision_ref, verdict: 'approve', stepUpToken: token });
      await done();
      toast({ tone: 'ok', text: 'مُهر خورد؛ دقیقاً همین پیام یک بار فرستاده شد.' });
    } catch (err) { toast({ tone: 'error', text: faError(err) }); } finally { setBusy(false); }
  };
  const answer = async () => {
    if (!e.decision_ref || !mode) return;
    try { await decide.mutateAsync({ ref: e.decision_ref, verdict: mode, note: note.trim() || undefined }); await done(); setMode(null); setNote(''); toast({ tone: 'info', text: mode === 'return' ? 'برگشت؛ مشاور پیش‌نویس تازه مینویسد و کارت تازه میآید.' : 'رد شد؛ چیزی فرستاده نشد.' }); }
    catch (err) { toast({ tone: 'error', text: faError(err) }); }
  };
  return (
    <section className="tahrir flex flex-col gap-3 rounded-[16px] bg-gold-soft p-4" aria-label="ایمیل منتظر مُهر">
      <div className="flex flex-wrap items-center gap-2 text-[13px]"><span className="text-gold-ink"><Icon name="seal" size={18} /></span><span className="font-semibold text-ink">ایمیل منتظر مُهر تو</span>{e.decision_ref ? <RefChip r={e.decision_ref} /> : null}</div>
      <ExactEmail e={e} />
      <div className="flex flex-wrap items-center gap-3">
        <SealButton code={c.company} nameFa={co.nameFa} nameEn={co.nameEn} holding={co.holding} busy={busy} onSealed={seal} size={64} />
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="secondary" icon="back" onClick={() => setMode('return')}>برگشت با یادداشت</Button>
          <Button size="sm" variant="danger" icon="reject" onClick={() => setMode('reject')}>نفرست</Button>
        </div>
      </div>
      <Dialog open={!!mode} onOpenChange={(v) => !v && setMode(null)} title={mode === 'return' ? 'برگشت به مشاور' : 'این ایمیل فرستاده نشود'} actions={<>
        <Button variant={mode === 'return' ? 'primary' : 'danger'} disabled={mode === 'return' && !note.trim()} loading={decide.isPending} onClick={answer}>{mode === 'return' ? 'بفرست' : 'نفرست'}</Button>
        <Button variant="secondary" onClick={() => setMode(null)}>انصراف</Button>
      </>}>
        <textarea value={note} onChange={(ev) => setNote(ev.target.value)} rows={3} maxLength={2000} placeholder={mode === 'return' ? 'چه چیزی عوض شود؟ (لازم)' : 'دلیل (اختیاری)'} className="w-full rounded-[10px] border border-strong bg-tile p-3 text-[14px] text-ink outline-none focus:border-gold-ink" />
      </Dialog>
    </section>
  );
}

function EmailItem({ e }: { e: CaseEmail }) {
  const [open, setOpen] = useState(false);
  const out = e.direction === 'out';
  return (
    <li className="flex flex-col gap-2 rounded-[12px] bg-tile p-3">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} className="flex flex-wrap items-center gap-2 text-start text-[12px]">
        <span className={out ? 'text-gold-ink' : 'text-lapis'}><Icon name={out ? 'send' : 'messages'} size={15} /></span>
        <span className="font-semibold text-ink">{out ? 'رفت' : 'آمد'}</span>
        <span dir="ltr" className="fig min-w-0 flex-1 truncate text-start text-sec">{e.subject}</span>
        <span className="text-muted">{jDateTime(e.at)}</span>
        {e.state === 'rejected' ? <Pill tone="neutral">فرستاده نشد</Pill> : e.state === 'superseded' ? <Pill tone="neutral">جایگزین شد</Pill> : null}
        <Icon name="chevron" size={14} />
      </button>
      {open ? (
        <div className="flex flex-col gap-1.5">
          <span dir="ltr" className="fig text-start text-[11px] text-muted">{e.from} → {e.to.join(', ')}{e.message_id ? ` · ${e.message_id}` : ''}</span>
          <Md text={e.body_md} className="fig flex flex-col gap-1.5 text-left text-[13px] leading-6 text-ink" />
          {e.decision_ref ? <span className="text-[11px] text-muted">با مُهر <RefChip r={e.decision_ref} /></span> : !out ? <span className="text-[11px] text-muted">با کد خوانده و ماسک شد؛ مشاور بیدار شد.</span> : null}
        </div>
      ) : null}
    </li>
  );
}

export function CaseDetail({ refId }: { refId: string }) {
  const q = useCase(refId);
  const act = useCaseAction();
  const toast = useToast();
  const now = useNow();
  const { data: companies } = useCompanies();
  const [closing, setClosing] = useState(false);
  const c = q.data;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!c) return <Skeleton className="h-96" />;
  const st = CASE_STATUS[c.status] ?? CASE_STATUS.open!;
  const pending = (c.emails ?? []).filter((e) => e.state === 'waiting_seal');
  const thread = (c.emails ?? []).filter((e) => e.state !== 'waiting_seal');
  const close = async () => {
    try { await act.close.mutateAsync(c.ref); setClosing(false); toast({ tone: 'info', text: 'پرونده بسته شد؛ تاریخچه‌اش میماند.' }); } catch (e) { toast({ tone: 'error', text: faError(e) }); }
  };
  return (
    <article className="flex flex-col gap-5">
      <header className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted"><CoMark code={c.company} height={11} /><span>{companyOf(companies, c.company).nameFa}</span><span className="fig">{c.ref}</span><span>{CASE_KIND[c.kind] ?? c.kind}</span></div>
        <h2 className="text-h2 font-semibold text-ink">{c.title_fa}</h2>
        <div className="flex flex-wrap items-center gap-2 text-[12px] text-sec">
          <Pill tone={st.tone} dot live={st.live}>{st.fa}</Pill>
          <span>طرف مقابل: <span className="text-ink">{c.counterpart.name}</span></span>
          {c.counterpart.address ? <span dir="ltr" className="fig text-muted">{c.counterpart.address}</span> : null}
          <span className="flex items-center gap-1"><ActorAvatar a={c.opened_by} size={18} />باز شده‌ی {ACTOR_FA(c.opened_by)}، {ago(c.created_at)}</span>
        </div>
        {c.brief_md ? <p className="rounded-[12px] bg-tile p-3 text-[13px] leading-6 text-ink">{c.brief_md}</p> : null}
      </header>
      {pending.map((e) => <EmailToSeal key={e.id} e={e} c={c} />)}
      {c.deadlines.length ? (
        <Block title="مهلت‌ها">
          <ul className="flex flex-col gap-1.5">{[...c.deadlines].sort((a, b) => a.at.localeCompare(b.at)).map((d) => (
            <li key={d.at + d.what_fa} className="flex flex-wrap items-center gap-2 rounded-[10px] bg-tile px-3 py-2 text-[12px]"><Icon name="time" size={14} /><span className="text-ink">{d.what_fa}</span><span className="flex-1" /><span className={cx(now && Date.parse(d.at) - now < 48 * 3600_000 ? 'text-warn' : 'text-muted')}>{jDateTime(d.at)}، {until(d.at)}</span></li>
          ))}</ul>
        </Block>
      ) : null}
      <Block title="روند پرونده">
        <ol className="relative flex flex-col gap-3 border-r border-div pr-4">
          {c.timeline.map((t, i) => {
            const k = TIMELINE[t.kind] ?? TIMELINE.note!;
            return (
              <li key={i} className="relative flex flex-col gap-1 text-[13px]">
                <span className="absolute -right-[25px] top-0.5 flex size-[18px] items-center justify-center rounded-full bg-card text-gold-ink ring-2 ring-[var(--hq-surface-page)]"><Icon name={k.icon} size={11} /></span>
                <span className="flex flex-wrap items-center gap-2 text-[11px] text-muted"><span className="font-semibold text-sec">{k.fa}</span><span>{jDateTime(t.at)}</span>{t.ref ? <RefChip r={t.ref} tone="neutral" /> : null}</span>
                <span className="leading-6 text-ink"><MdInline text={t.summary_fa} /></span>
              </li>
            );
          })}
        </ol>
      </Block>
      {thread.length ? <Block title="رشته‌ی ایمیل"><ul className="flex flex-col gap-2">{thread.map((e) => <EmailItem key={e.id} e={e} />)}</ul></Block> : null}
      {/* ⟨1.7⟩ §23.5: the case's legal holds in the archive; a new one is placed tied to this case. */}
      <CaseHolds caseRef={c.ref} />
      <div className="flex flex-wrap items-center gap-2 border-t border-div pt-3">
        <Link href="/messages?thread=L" className="inline-flex h-10 items-center gap-2 rounded-[10px] border border-strong px-4 text-[13px] font-semibold text-ink hover:bg-hover"><Icon name="messages" size={18} />در رشته‌ی L بپرس</Link>
        <span className="flex-1" />
        {c.status !== 'closed' ? <Button variant="ghost" icon="close" onClick={() => setClosing(true)}>بستن پرونده</Button> : null}
      </div>
      <Dialog open={closing} onOpenChange={setClosing} title="بستن پرونده" actions={<>
        <Button variant="primary" loading={act.close.isPending} onClick={close}>ببند</Button>
        <Button variant="secondary" onClick={() => setClosing(false)}>نه</Button>
      </>}><p>مشاور دیگر روی آن کار نمیکند؛ جواب تازه‌ای که برسد در روند پرونده ثبت میشود ولی او را بیدار نمیکند. تاریخچه میماند.</p></Dialog>
    </article>
  );
}

const KINDS = Object.keys(CASE_KIND) as CaseKind[];
export function NewCase({ onClose, onMade }: { onClose: () => void; onMade: (ref: string) => void }) {
  const act = useCaseAction();
  const toast = useToast();
  const { data: companies } = useCompanies();
  const [key] = useState(() => crypto.randomUUID());
  const [company, setCompany] = useState<string | null>(null);
  const [kind, setKind] = useState<CaseKind>('platform_restriction');
  const [title, setTitle] = useState('');
  const [brief, setBrief] = useState('');
  const ok = !!company && title.trim().length >= 4 && brief.trim().length >= 10;
  const submit = async () => {
    if (!company) return;
    try { const c = await act.open.mutateAsync({ body: { company, title_fa: title.trim(), kind, brief_md: brief.trim() }, key }); toast({ tone: 'ok', text: <>پرونده‌ی <span className="fig">{c.ref}</span> باز شد؛ مشاور حقوقی بیدار شد.</> }); onMade(c.ref); }
    catch (e) { toast({ tone: 'error', text: faError(e) }); }
  };
  return (
    <Sheet open onOpenChange={(v) => !v && onClose()} width={560} title="پرونده‌ی تازه" description="مشاور اول واقعیت‌ها و قاعده‌ی منتشرشده‌ی خود طرف مقابل را پیدا میکند؛ هر ایمیل یا فرم کارت مُهر توست. اگر کار وکیل انسانی باشد، همین را میگوید."
      footer={<div className="flex gap-2"><Button variant="primary" icon="send" disabled={!ok} loading={act.open.isPending} onClick={submit}>باز کن</Button><Button variant="ghost" onClick={onClose}>انصراف</Button></div>}>
      <div className="flex flex-col gap-4 text-[13px]">
        <fieldset className="flex flex-col gap-2"><legend className="pb-2 font-semibold text-sec">برای کدام شرکت</legend>
          <div className="flex flex-wrap gap-1.5">{(companies ?? []).map((c) => <FilterChip key={c.code} selected={company === c.code} onClick={() => setCompany(c.code)}><span className="flex items-center gap-1.5"><CoMark code={c.code} height={11} />{c.name_fa}</span></FilterChip>)}</div>
        </fieldset>
        <fieldset className="flex flex-col gap-2"><legend className="pb-2 font-semibold text-sec">نوع</legend>
          <div className="flex flex-wrap gap-1.5">{KINDS.map((k) => <FilterChip key={k} selected={kind === k} onClick={() => setKind(k)}>{CASE_KIND[k]}</FilterChip>)}</div>
        </fieldset>
        <label className="flex flex-col gap-1.5 font-semibold text-sec">عنوان<input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} placeholder="مثلاً: محدودیت پاسخ به دایرکت اینستاگرام FX" className={field} /></label>
        <label className="flex flex-col gap-1.5 font-semibold text-sec">چه شده
          <textarea value={brief} onChange={(e) => setBrief(e.target.value)} rows={5} maxLength={5000} placeholder="واقعیت‌ها، تاریخ، متن دقیق اعلان اگر هست" className="w-full rounded-[10px] border border-strong bg-card p-3 text-[14px] font-normal leading-6 text-ink outline-none focus:border-gold-ink" />
          <span className="text-[11px] font-normal text-muted">اسکرین‌شات را در رشته‌ی L بفرست؛ مشاور آن را به پرونده میبندد.</span>
        </label>
      </div>
    </Sheet>
  );
}

export function CasesEmpty() {
  return <Empty icon="decision" title="پرونده‌ای نیست" body="هر گیر حقوقی یا محدودیت پلتفرم را اینجا یا در رشته‌ی L بگو." />;
}
