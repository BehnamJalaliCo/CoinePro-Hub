'use client';

import Link from 'next/link';
import { use, useState } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { Button } from '@/components/ui/button';
import { Card, ErrorState, Pill, SectionTitle, Skeleton, Switch } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { AUTHOR_FA, CHANNEL_FA, CHANNEL_STATE, CONV_STATE, Fact, GuardReasons, HANDOFF_FA, MSG_STATUS, Masked } from '@/components/v16/bits';
import { useCompanies } from '@/lib/api/hooks';
import { blockedReasons, faError, useChannels, useConversation, useConversationAction, type SupportMessage } from '@/lib/api/v16';
import { cx, jDateTime, jTime } from '@/lib/format';

const area = 'w-full rounded-[12px] border border-strong bg-card px-3 py-2.5 text-[14px] leading-7 text-ink outline-none focus:border-gold-ink';

function Check({ ok, label }: { ok: boolean; label: string }) {
  return <span className={cx('inline-flex items-center gap-1', ok ? 'text-pos' : 'text-neg')}><Icon name={ok ? 'seal' : 'urgent'} size={12} />{label}</span>;
}

function Bubble({ m, onEdit, onTeach, onSend }: { m: SupportMessage; onEdit: (m: SupportMessage) => void; onTeach: (m: SupportMessage) => void; onSend: (m: SupportMessage) => void }) {
  const inbound = m.direction === 'in';
  const st = MSG_STATUS[m.status] ?? { fa: m.status, tone: 'neutral' as const };
  const pending = !inbound && (m.status === 'draft' || m.status === 'blocked');
  return (
    <div className={cx('flex', inbound ? 'justify-start' : 'justify-end')}>
      <div className={cx('flex max-w-[min(640px,92%)] flex-col gap-1.5', inbound ? 'items-start' : 'items-end')}>
        <div className={cx('rounded-[16px] px-4 py-3', inbound ? 'rounded-tr-[6px] bg-tile' : m.author === 'owner' ? 'rounded-tl-[6px] bg-raised' : 'rounded-tl-[6px] bg-card ring-1 ring-[var(--hq-line-divider)]',
          m.status === 'blocked' && 'ring-1 ring-[var(--hq-neg-line)]', m.status === 'draft' && 'ring-1 ring-[var(--hq-gold-ink)]')}>
          <Masked text={m.body} className="text-[14px] leading-7 text-ink" />
        </div>
        <div className={cx('flex flex-wrap items-center gap-x-2 gap-y-1 px-1 text-[11px] text-muted', !inbound && 'justify-end')}>
          <span className="font-semibold text-sec">{AUTHOR_FA[m.author] ?? m.author}</span>
          <span title={jDateTime(m.at)}>{jTime(m.at)}</span>
          {!inbound ? <Pill tone={st.tone} className="h-5 px-2 text-[11px]">{st.fa}</Pill> : null}
          {!inbound ? <Check ok={m.checks.guard === 'pass'} label="نگهبان" /> : null}
          {!inbound && m.checks.grounded ? <Check ok={m.checks.grounded === 'pass'} label="مستند" /> : null}
          {m.confidence != null ? <span>اطمینان <span className="fig">{m.confidence.toFixed(2)}</span></span> : null}
          {m.kb_refs.map((r) => <span key={r} className="fig rounded-full bg-tile px-2 text-sec">{r}</span>)}
        </div>
        {m.status === 'blocked' ? <GuardReasons reasons={m.blocked_reasons} className="w-full" /> : null}
        {pending ? (
          <div className="flex flex-wrap gap-2">
            {m.status === 'draft' ? <Button size="sm" variant="secondary" icon="send" onClick={() => onSend(m)}>همین را بفرست</Button> : null}
            <Button size="sm" variant="secondary" icon="edit" onClick={() => onEdit(m)}>اصلاح و فرستادن</Button>
            <Button size="sm" variant="text" icon="learning" onClick={() => onTeach(m)}>آموزش با این</Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

/** One conversation (§19.3): messages oldest first, masked; the owner's reply goes through the outbound guard like everything else. */
export default function ConversationPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = use(params);
  const q = useConversation(ref);
  const c = q.data;
  const channels = useChannels(c?.company ?? null);
  const { data: companies } = useCompanies();
  const act = useConversationAction();
  const toast = useToast();
  // The reply: one Idempotency-Key per text, so a retry of the same text never sends twice and an edited text is a new send.
  const [reply, setReply] = useState({ text: '', key: '' });
  const [reasons, setReasons] = useState<string[]>([]);
  const [replyErr, setReplyErr] = useState<string | null>(null);
  const [teach, setTeach] = useState({ text: '', key: '' });
  const [from, setFrom] = useState<SupportMessage | null>(null);
  const [general, setGeneral] = useState(true);
  const [teachReasons, setTeachReasons] = useState<string[]>([]);
  const setReplyText = (text: string) => setReply({ text, key: crypto.randomUUID() });
  const setTeachText = (text: string) => setTeach({ text, key: crypto.randomUUID() });

  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!c) return <div className="flex flex-col gap-4"><Skeleton className="h-16" /><Skeleton className="h-96" /></div>;
  const ch = channels.data?.find((x) => x.kind === c.channel);
  const live = ch?.state === 'live';
  const co = companies?.find((x) => x.code === c.company);

  const send = async (text: string, key: string) => {
    setReasons([]); setReplyErr(null);
    try {
      await act.reply.mutateAsync({ ref, body: text.trim(), key });
      setReply({ text: '', key: '' });
      toast({ tone: 'ok', text: 'از نگهبان گذشت و فرستاده شد.' });
    } catch (e) {
      const r = blockedReasons(e);
      if (r.length) setReasons(r); else setReplyErr(faError(e));
    }
  };
  const doTeach = async () => {
    setTeachReasons([]);
    try {
      const out = await act.teach.mutateAsync({ ref, message_id: from?.id ?? null, answer_md: teach.text.trim(), generalise: general, key: teach.key || crypto.randomUUID() });
      setTeach({ text: '', key: '' }); setFrom(null);
      toast({ tone: 'ok', text: <>{out.message ? 'جوابت فرستاده شد و ' : 'جوابی فرستاده نشد (کانال روشن نیست یا گفت‌وگو منتظر نبود)؛ '}مقاله‌ی پیشنهادی <span className="fig">{out.article.ref}</span> ساخته شد تا تأییدش کنی.</> });
    } catch (e) {
      const r = blockedReasons(e);
      if (r.length) setTeachReasons(r); else toast({ tone: 'error', text: faError(e) });
    }
  };
  const close = () => act.close.mutateAsync(ref).then(() => toast({ tone: 'info', text: 'بسته شد؛ قاعده‌ی رضایت (اگر فعال باشد) سراغ مشتری میرود.' })).catch((e) => toast({ tone: 'error', text: faError(e) }));

  return (
    <>
      <header className="flex flex-wrap items-end gap-x-4 gap-y-3">
        <div className="flex min-w-0 flex-[1_1_16rem] flex-col gap-1">
          <Link href="/support" className="flex items-center gap-1 self-start text-caption text-muted hover:text-ink"><Icon name="back" size={14} />پشتیبانی</Link>
          <h1 className="text-h1 font-semibold text-ink">{c.customer.display_name ?? <span className="fig">{c.customer.handle_masked}</span>}</h1>
          <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted">
            <span className="fig">{c.ref}</span><CompanyMark code={c.company} height={12} mono /><span>{co?.name_fa ?? c.company}</span><span>{CHANNEL_FA[c.channel] ?? c.channel}</span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone={CONV_STATE[c.state]?.tone ?? 'neutral'} dot>{CONV_STATE[c.state]?.fa ?? c.state}</Pill>
          {c.handoff && c.state === 'waiting_owner' ? <Pill tone={HANDOFF_FA[c.handoff.reason]?.tone ?? 'neutral'} icon={c.handoff.reason === 'security' ? 'urgent' : undefined}>{HANDOFF_FA[c.handoff.reason]?.fa ?? c.handoff.reason}</Pill> : null}
          {c.state !== 'closed' ? <Button size="sm" variant="ghost" icon="close" loading={act.close.isPending} onClick={close}>بستن گفت‌وگو</Button> : null}
        </div>
      </header>
      {c.handoff?.reason === 'security' && c.state === 'waiting_owner' ? (
        <p className="flex items-start gap-2 rounded-[14px] bg-neg-soft p-3 text-[13px] leading-6 text-ink"><span className="text-neg"><Icon name="urgent" size={18} /></span>گزارش امنیتی (مثل جعل هویت): مشتری جمله‌ی ایمنی را گرفته؛ رمز یا عبارتی که فرستاده ماسک شده و به هیچ مدلی نرسیده. جواب تو هم از نگهبان رد میشود.</p>
      ) : null}
      {c.mystery ? <p className="rounded-[14px] bg-learn-soft p-3 text-[13px] leading-6 text-ink">گفت‌وگوی مشتری ناشناس ناظر (PR-043): کل مسیر را رفته ولی هرگز به تلگرام یا Chatwoot نرسیده و در هیچ آماری نیست.</p> : null}

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
        <Card className="flex min-w-0 flex-col gap-4 p-4">
          <SectionTitle title="پیام‌ها" note="قدیمی‌ترین بالا؛ رمز، کارت و عبارت بازیابی پیش از ذخیره ماسک میشوند" />
          <div className="flex flex-col gap-4">
            {c.messages.map((m) => (
              <Bubble key={m.id} m={m}
                onEdit={(x) => setReplyText(x.body)}
                onSend={(x) => void send(x.body, crypto.randomUUID())}
                onTeach={(x) => { setFrom(x); setTeachText(x.body); }} />
            ))}
          </div>
          <div className="flex flex-col gap-2 border-t border-div pt-4">
            <label htmlFor="reply" className="text-[13px] font-semibold text-sec">جواب تو</label>
            {!live ? <p className="rounded-[10px] bg-tile p-2.5 text-[12px] leading-6 text-sec">کانال {CHANNEL_FA[c.channel] ?? c.channel} {CHANNEL_STATE[ch?.state ?? '']?.fa ?? 'روشن نیست'} است؛ جواب مستقیم فرستاده نمیشود. «آموزش» هنوز مقاله‌ی پیشنهادی میسازد.</p> : null}
            <textarea id="reply" value={reply.text} onChange={(e) => setReplyText(e.target.value)} rows={4} maxLength={4000} disabled={c.state === 'closed'} placeholder={c.state === 'closed' ? 'گفت‌وگو بسته است.' : 'از نگهبان خروجی رد میشود؛ لینک فقط از لینک‌های تأییدشده'} className={area} />
            <GuardReasons reasons={reasons} />
            {replyErr ? <p role="alert" className="text-[12px] text-neg">{replyErr}</p> : null}
            <div className="flex items-center gap-2">
              <Button variant="primary" icon="send" disabled={!reply.text.trim() || c.state === 'closed' || !live} loading={act.reply.isPending} onClick={() => void send(reply.text, reply.key || crypto.randomUUID())}>{reasons.length ? 'دوباره بفرست' : 'بفرست'}</Button>
              <span className="text-[11px] text-muted">بعد از هر اصلاح، نگهبان دوباره میسنجد.</span>
            </div>
          </div>
        </Card>

        <div className="flex min-w-0 flex-col gap-4">
          <Card className="flex flex-col gap-3 p-4">
            <SectionTitle title="آموزش" note="جواب درست را بنویس؛ فرستاده میشود (اگر منتظر توست) و مقاله‌ی پیشنهادی میشود" />
            {from ? <span className="flex items-center gap-2 rounded-[10px] bg-tile px-3 py-1.5 text-[12px] text-sec"><span className="flex-1">اصلاح پیش‌نویس <span className="fig">{from.id}</span></span><button type="button" onClick={() => setFrom(null)} aria-label="بی‌پیش‌نویس" className="text-muted hover:text-ink"><Icon name="close" size={14} /></button></span> : null}
            <textarea value={teach.text} onChange={(e) => setTeachText(e.target.value)} rows={6} maxLength={4000} aria-label="جواب آموزش" placeholder="جواب درست، همان‌طور که خودت به مشتری میگویی" className={area} />
            <div className="flex items-center gap-3 rounded-[12px] bg-tile p-3 text-[12px] leading-5"><span className="flex-1">تعمیم بده: بی‌داده‌ی مشتری، با متغیرهای مشخص، تا برای مشتری بعدی هم به کار برود</span><Switch label="تعمیم" checked={general} onChange={setGeneral} /></div>
            <GuardReasons reasons={teachReasons} />
            <Button variant="primary" icon="learning" disabled={teach.text.trim().length < 5} loading={act.teach.isPending} onClick={() => void doTeach()}>بفرست و یاد بده</Button>
          </Card>
          <Card className="flex flex-col gap-3 p-4">
            <SectionTitle title="مشتری" note="نام کاربری ماسک‌شده؛ بیرون از این صفحه فقط نام مستعار" />
            <div className="grid grid-cols-2 gap-2">
              <Fact label="نام کاربری" mono>{c.customer.handle_masked}</Fact>
              <Fact label="زبان" mono>{c.customer.lang}</Fact>
              <Fact label="باز شد">{jDateTime(c.opened_at)}</Fact>
              <Fact label="آخرین پیام">{jDateTime(c.last_message_at)}</Fact>
              {c.csat != null ? <Fact label="رضایت" mono>{c.csat}/5</Fact> : null}
              {c.handoff ? <Fact label="سپرده به تو">{jDateTime(c.handoff.at)}</Fact> : null}
            </div>
            {c.tags.length ? <div className="flex flex-wrap gap-1.5">{c.tags.map((t) => <span key={t} className="rounded-full bg-tile px-2.5 py-0.5 text-[12px] text-sec">{t}</span>)}</div> : null}
            {c.rescue ? <Link href="/revenue" className="flex items-center gap-2 rounded-[12px] bg-tile p-3 text-[13px] hover:bg-hover"><Icon name="refresh" size={16} className="text-gold-ink" /><span className="flex-1">پرونده‌ی نجات رفرال <span className="fig">{c.rescue}</span></span><Icon name="next" size={14} mirror className="text-muted" /></Link> : null}
          </Card>
        </div>
      </div>
    </>
  );
}
