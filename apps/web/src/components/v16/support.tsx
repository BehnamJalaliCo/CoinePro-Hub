'use client';

import Link from 'next/link';
import { useRef, useState } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { StackedBar } from '@/components/charts/charts';
import { Button } from '@/components/ui/button';
import { Md } from '@/components/ui/md';
import { Sheet } from '@/components/ui/overlay';
import { Card, Empty, ErrorState, FilterChip, Pill, SectionTitle, Segmented, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { useCompanies, useDecisions } from '@/lib/api/hooks';
import { uploadFile } from '@/lib/api/v13';
import {
  GUARD_FA, faError, useChannelAction, useChannels, useConversations, useKb, useKbAction, useQueue, useShadow, useShadowAction, widens,
  type AutoSend, type ChannelKind, type ConversationState, type KbArticle, type KbArticleIn, type KbKind, type KbStatus, type ShadowReport, type SupportChannel,
} from '@/lib/api/v16';
import { ago, cx, jDate, jDateTime, until } from '@/lib/format';
import { useNow } from '@/lib/store';
import {
  AUTO_SEND, CHANNEL_FA, CHANNEL_STATE, CONV_STATE, CompanyChips, Fact, HANDOFF_FA, KB_KIND, KB_SOURCE, KB_STATUS, Masked, Prose, QUEUE_KIND, TerminalCommand, rate,
} from './bits';

const field = 'w-full rounded-[10px] border border-strong bg-card px-3 text-[14px] text-ink outline-none focus:border-gold-ink';

// ------------------------------------------------------------- the queue --
/** حالت آموزش (§19.3–§19.4): what waits for the owner, oldest first. */
export function QueueTab() {
  const q = useQueue();
  const items = [...(q.data ?? [])].sort((a, b) => a.since.localeCompare(b.since));
  return (
    <Card className="flex flex-col gap-3 p-4">
      <SectionTitle title="صف آموزش" note="قدیمی‌ترین بالا؛ هر جواب یا اصلاح تو یک مقاله‌ی پیشنهادی میشود تا مشتری بعدی بی‌تو جواب بگیرد" />
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isLoading ? <Skeleton className="h-40" /> : !items.length ? <Empty icon="messages" title="صف خالی است" body="پشتیبانی چیزی منتظر تو ندارد." /> : (
        <ul className="flex flex-col">
          {items.map((x) => (
            <li key={`${x.conversation}-${x.kind}`} className="border-b border-div last:border-0">
              <Link href={`/support/${x.conversation}`} className="flex items-start gap-3 rounded-[8px] px-1 py-3 hover:bg-hover">
                <span className="mt-0.5"><Pill tone={QUEUE_KIND[x.kind]?.tone ?? 'neutral'} dot>{QUEUE_KIND[x.kind]?.fa ?? x.kind}</Pill></span>
                <span className="flex min-w-0 flex-1 flex-col gap-1">
                  <span className="flex flex-wrap items-center gap-x-2 text-[12px] text-muted"><CompanyMark code={x.company} height={12} mono /><span className="fig">{x.conversation}</span><span>{ago(x.since)}</span></span>
                  {x.draft ? (
                    <>
                      <Masked text={x.draft.body} className="line-clamp-2 text-[13px] leading-6 text-ink" />
                      {x.draft.blocked_reasons.length ? <span className="text-[12px] text-neg">رد نگهبان: {x.draft.blocked_reasons.map((r) => GUARD_FA[r] ?? r).join('، ')}</span>
                        : x.draft.confidence != null ? <span className="text-[12px] text-sec">پیش‌نویس با اطمینان <span className="fig">{x.draft.confidence.toFixed(2)}</span></span> : null}
                    </>
                  ) : <span className="text-[13px] text-sec">پیش‌نویسی نیست؛ جواب تو لازم است.</span>}
                </span>
                <Icon name="next" size={14} mirror className="mt-1 text-muted" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

// ------------------------------------------------------- conversations --
const CONV_STATES: ConversationState[] = ['waiting_owner', 'open', 'answered', 'closed'];
const CHANNELS: ChannelKind[] = ['telegram_bot', 'telegram_business', 'chatwoot', 'product_bot', 'mystery'];

export function ConversationsTab({ initialCompany }: { initialCompany: string | null }) {
  const [company, setCompany] = useState<string | null>(initialCompany);
  const [state, setState] = useState<ConversationState | null>(null);
  const [channel, setChannel] = useState<ChannelKind | null>(null);
  const [text, setText] = useState('');
  const [query, setQuery] = useState('');
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const q = useConversations({ company, state, channel, q: query });
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <Card className="flex flex-col gap-3 p-4">
      <div className="flex flex-col gap-2">
        <CompanyChips value={company} onChange={setCompany} />
        <div className="flex flex-wrap gap-2">
          <FilterChip selected={!state} onClick={() => setState(null)}>همه</FilterChip>
          {CONV_STATES.map((s) => <FilterChip key={s} selected={state === s} onClick={() => setState(s)}>{CONV_STATE[s]!.fa}</FilterChip>)}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select value={channel ?? ''} onChange={(e) => setChannel((e.target.value || null) as ChannelKind | null)} aria-label="کانال" className="h-9 rounded-[10px] border border-strong bg-tile px-2 text-[13px] text-ink outline-none focus:border-gold-ink">
            <option value="">همه‌ی کانال‌ها</option>
            {CHANNELS.map((c) => <option key={c} value={c}>{CHANNEL_FA[c]}</option>)}
          </select>
          <input value={text} onChange={(e) => { const v = e.target.value; setText(v); clearTimeout(timer.current); timer.current = setTimeout(() => setQuery(v), 300); }} placeholder="جستجو در گفت‌وگوها" aria-label="جستجو در گفت‌وگوها"
            className="h-9 min-w-0 flex-1 rounded-[10px] border border-strong bg-tile px-3 text-[13px] text-ink outline-none focus:border-gold-ink" />
        </div>
      </div>
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isLoading ? <Skeleton className="h-48" /> : !items.length ? <Empty icon="messages" title="گفت‌وگویی نیست" /> : (
        <ul className="flex flex-col">
          {items.map((c) => (
            <li key={c.ref} className="border-b border-div last:border-0">
              <Link href={`/support/${c.ref}`} className="flex items-start gap-3 rounded-[8px] px-1 py-3 hover:bg-hover">
                <span className="mt-1"><CompanyMark code={c.company} height={14} mono /></span>
                <span className="flex min-w-0 flex-1 flex-col gap-1">
                  <span className="flex items-center gap-2 text-[14px] font-semibold text-ink">{c.customer.display_name ?? <span className="fig">{c.customer.handle_masked}</span>}{c.mystery ? <Pill tone="learn">ناشناس ناظر</Pill> : null}</span>
                  <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-muted">
                    <span className="fig">{c.ref}</span><span>{CHANNEL_FA[c.channel] ?? c.channel}</span>{c.customer.display_name ? <span className="fig">{c.customer.handle_masked}</span> : null}
                    {c.tags.map((t) => <span key={t} className="rounded-full bg-tile px-2 text-sec">{t}</span>)}
                    {c.csat != null ? <span>رضایت <span className="fig">{c.csat}/5</span></span> : null}
                  </span>
                </span>
                <span className="flex flex-none flex-col items-end gap-1">
                  <Pill tone={CONV_STATE[c.state]?.tone ?? 'neutral'} dot>{CONV_STATE[c.state]?.fa ?? c.state}</Pill>
                  {c.handoff && c.state === 'waiting_owner' ? <Pill tone={HANDOFF_FA[c.handoff.reason]?.tone ?? 'neutral'}>{HANDOFF_FA[c.handoff.reason]?.fa ?? c.handoff.reason}</Pill> : null}
                  <span className="text-[11px] text-muted">{ago(c.last_message_at)}</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
      {q.hasNextPage ? <Button variant="secondary" size="sm" loading={q.isFetchingNextPage} onClick={() => q.fetchNextPage()}>بیشتر</Button> : null}
    </Card>
  );
}

// ------------------------------------------------------------ channels --
const SETUP: Record<string, (c: SupportChannel) => React.ReactNode> = {
  telegram_bot: (c) => <><span>ربات را در BotFather بساز و توکنش را در ترمینال خودت بگذار:</span><TerminalCommand text={`make telegram-bot-token COMPANY=${c.company} CHANNEL=telegram_bot`} /></>,
  telegram_business: () => <span>بعد از قبولی آزمون سایه: Premium تلگرام و اتصال Business ← Chatbots به ربات هلدینگ.</span>,
  chatwoot: () => <span>چت سایت تصمیم هزینه‌ی توست (سرور کوچک جدا، یا فعلاً بدون چت سایت)؛ تا آن موقع خاموش میماند.</span>,
  product_bot: () => <span>از راه <span className="fig">CR-011</span> (ربات خود محصول)، فقط بعد از go-live همین کانال.</span>,
};

function ChannelCard({ c, report, card }: { c: SupportChannel; report: ShadowReport | undefined; card: string | undefined }) {
  const act = useChannelAction();
  const toast = useToast();
  const st = CHANNEL_STATE[c.state] ?? { fa: c.state, tone: 'neutral' as const };
  const patch = (p: { auto_send?: AutoSend; state?: 'live' }) => act.patch.mutateAsync({ c, patch: p })
    .then(() => toast({ tone: 'ok', text: p.state === 'live' ? 'کانال دوباره روشن شد.' : `ارسال بی‌تو: ${AUTO_SEND[p.auto_send ?? '']?.fa ?? ''}` }))
    .catch((e) => toast({ tone: 'error', text: faError(e) }));
  const mystery = c.kind === 'mystery';
  return (
    <div className={cx('flex flex-col gap-3 rounded-[14px] p-4', c.state === 'paused' ? 'bg-warn-soft' : 'bg-tile')}>
      <div className="flex items-center gap-2">
        <Icon name={mystery ? 'overseer' : 'messages'} size={18} className="text-sec" />
        <span className="min-w-0 flex-1 text-[14px] font-semibold">{CHANNEL_FA[c.kind] ?? c.kind}</span>
        <Pill tone={st.tone} dot live={c.state === 'live'}>{st.fa}</Pill>
      </div>
      {c.state === 'live' && c.live_since ? <span className="text-[12px] text-muted">روشن از {jDate(c.live_since)}</span> : null}
      {c.state === 'paused' ? <p className="text-[12px] leading-6 text-ink">{c.paused_reason ?? 'متوقف است.'}</p> : null}
      {c.state !== 'not_configured' ? (
        <div className="flex flex-col gap-1.5">
          <span className="text-[12px] text-sec">چه چیزی بی‌تو میرود</span>
          <Segmented<AutoSend> label={`ارسال بی‌تو: ${CHANNEL_FA[c.kind]}`} value={c.auto_send} onChange={(v) => { if (v !== c.auto_send) void patch({ auto_send: v }); }}
            options={[{ value: 'off', label: 'هیچ' }, { value: 'kb_verbatim', label: 'عین دانشنامه' }, { value: 'kb_grounded', label: 'مستند هم', icon: c.auto_send === 'kb_grounded' ? undefined : 'lock' }]} />
          <span className="text-[11px] leading-5 text-muted">{AUTO_SEND[c.auto_send]?.note}{widens(c, { auto_send: 'kb_grounded' }) ? ' گشادتر کردن با passkey است؛ تنگ‌تر کردن نه.' : ''}</span>
        </div>
      ) : null}
      {mystery ? <p className="text-[12px] leading-6 text-sec">فقط ناظر کل؛ کل مسیر جواب را میرود ولی هرگز به تلگرام یا Chatwoot نمیرسد و در هیچ آماری شمرده نمیشود.</p>
        : c.state === 'shadow' ? (
          <div className="flex flex-col gap-1.5 rounded-[12px] bg-card p-3 text-[12px] leading-6 text-sec">
            {report?.pass ? <span><span className="font-semibold text-pos">آزمون سایه قبول شد.</span> شروع کانال یک کارت در کارتابل است که با مُهر تو روشن میشود.</span>
              : <span>اول آزمون سایه: دست‌کم <span className="fig">90%</span> درست، صفر خطای ایمنی، صفر کد یا لینک اشتباه. با قبولی، کارت شروع در کارتابل میاید.</span>}
            {c.kind === 'telegram_business' ? <span>تلگرام بیزینس علاوه بر این اتصال Premium تو (Business ← Chatbots) را لازم دارد.</span> : null}
            {card ? <Link href={`/cartable?ref=${card}`} className="flex items-center gap-1.5 self-start font-semibold text-gold-ink"><Icon name="seal" size={14} />کارت <span className="fig">{card}</span> منتظر مُهر توست</Link> : null}
          </div>
        ) : c.state === 'not_configured' ? <div className="flex flex-col gap-2 text-[12px] leading-6 text-sec">{SETUP[c.kind]?.(c)}</div> : null}
      <div className="flex flex-wrap items-center gap-2">
        {c.state === 'live' ? <Button size="sm" variant="danger" icon="pause" loading={act.pause.isPending} onClick={() => act.pause.mutateAsync(c).then(() => toast({ tone: 'info', text: 'متوقف شد؛ از این کانال دیگر چیزی به مشتری نمیرود.' })).catch((e) => toast({ tone: 'error', text: faError(e) }))}>توقف</Button> : null}
        {c.state === 'paused' && c.live_since ? <Button size="sm" variant="primary" icon="seal" loading={act.patch.isPending} onClick={() => void patch({ state: 'live' })}>دوباره روشن کن</Button> : null}
      </div>
    </div>
  );
}

export function ChannelsTab() {
  const q = useChannels();
  const shadow = useShadow();
  const cards = useDecisions({ status: 'pending' });
  const { data: companies } = useCompanies();
  const cos = [...new Set((q.data ?? []).map((c) => c.company))];
  const cardFor = (c: SupportChannel) => cards.data?.items.find((d) => d.kind === 'support_go_live' && (d.payload as { company?: string; channel?: string } | null)?.company === c.company && (d.payload as { channel?: string } | null)?.channel === c.kind)?.ref;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <Skeleton className="h-60" />;
  return (
    <div className="flex flex-col gap-4">
      <p className="max-w-3xl text-[13px] leading-6 text-sec">توقف همیشه امن است و passkey نمیخواهد. روشن شدن بار اول فقط با کارت شروع (go-live) بعد از قبولی آزمون سایه است؛ کانالی که قبلاً روشن بوده با passkey دوباره روشن میشود.</p>
      {cos.map((co) => (
        <Card key={co} className="flex flex-col gap-3 p-4">
          <SectionTitle title={<span className="flex items-center gap-2"><CompanyMark code={co} height={16} mono />{companies?.find((c) => c.code === co)?.name_fa ?? co}</span>} />
          <div className="grid items-start gap-3 md:grid-cols-2 xl:grid-cols-3">
            {q.data.filter((c) => c.company === co).map((c) => <ChannelCard key={c.kind} c={c} report={shadow.data?.find((r) => r.company === co)} card={cardFor(c)} />)}
          </div>
        </Card>
      ))}
    </div>
  );
}

// ------------------------------------------------------------- knowledge --
const KINDS: KbKind[] = ['faq', 'policy', 'procedure', 'referral', 'official_link', 'safety'];
const KB_STATES: KbStatus[] = ['proposed', 'approved', 'expired', 'retired'];

function KbSheet({ a, onClose }: { a: KbArticle; onClose: () => void }) {
  const act = useKbAction();
  const toast = useToast();
  const err = (e: unknown) => toast({ tone: 'error', text: faError(e) });
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title={<span className="flex items-center gap-2"><span className="fig text-[13px] text-muted">{a.ref}@{a.version}</span>{KB_KIND[a.kind]}</span>} width={600}
      footer={a.status === 'proposed' ? <Button variant="primary" icon="seal" className="w-full" loading={act.approve.isPending} onClick={() => act.approve.mutateAsync(a).then(() => { toast({ tone: 'ok', text: 'تأیید شد؛ از همین حالا میتواند بی‌تو به مشتری برود.' }); onClose(); }).catch(err)}>تأیید با passkey</Button>
        : a.status !== 'retired' ? <Button variant="ghost" onClick={() => act.retire.mutateAsync(a.ref).then(() => { toast({ tone: 'info', text: 'بازنشسته شد؛ دیگر در هیچ جوابی به کار نمیرود.' }); onClose(); }).catch(err)}>بازنشسته کن</Button> : undefined}>
      <div className="flex flex-col gap-4 text-[13px]">
        <div className="flex flex-wrap items-center gap-2"><Pill tone={KB_STATUS[a.status]?.tone ?? 'neutral'} dot>{KB_STATUS[a.status]?.fa ?? a.status}</Pill><span className="flex items-center gap-1.5 text-sec"><CompanyMark code={a.company} height={12} mono />{KB_SOURCE[a.source.kind] ?? a.source.kind}{a.source.ref ? <span className="fig text-muted">{a.source.ref}</span> : null}</span>{a.key ? <span className="fig rounded-[6px] bg-tile px-2 py-0.5 text-[12px]">{a.key}</span> : null}</div>
        <h3 className="text-[15px] font-semibold leading-7 text-ink">{a.question_fa}</h3>
        {a.variants.length ? <div className="flex flex-wrap gap-1.5">{a.variants.map((v) => <span key={v} className="rounded-full bg-tile px-2.5 py-0.5 text-[12px] text-sec">{v}</span>)}</div> : null}
        <Card className="bg-tile p-4"><Md text={a.answer_md} className="flex flex-col gap-2 text-[14px] leading-7 text-ink" /></Card>
        {a.variables.length ? <p className="text-[12px] text-sec">متغیرها: {a.variables.map((v) => <span key={v.name} className="fig me-2">{`{{${v.name}}}`} <span className="text-muted">({v.source === 'policy' ? 'سیاست' : 'مشتری'})</span></span>)}</p> : null}
        {a.links.length ? <div className="flex flex-col gap-1"><span className="text-[12px] font-semibold text-sec">لینک‌های تأییدشده</span>{a.links.map((l) => <span key={l.url} className="flex flex-wrap items-center gap-2"><span className="fig text-[12px] text-ink">{l.url}</span><span className="text-[12px] text-muted">{l.label_fa}</span></span>)}</div> : null}
        {a.codes.length ? <div className="flex flex-wrap gap-2">{a.codes.map((c) => <span key={c.exchange + c.code} className="fig rounded-[6px] bg-tile px-2 py-0.5 text-[12px]">{c.exchange}: {c.code}</span>)}</div> : null}
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <Fact label="استفاده در ۳۰ روز" mono>{a.uses_30d}</Fact>
          <Fact label="تأیید">{a.approved_at ? jDate(a.approved_at) : '—'}</Fact>
          <Fact label="انقضا">{until(a.expires_at)}</Fact>
        </div>
        <p className="text-[11px] text-muted">مقاله‌ی تأییدشده همان چیزی است که بی‌تو به مشتری میرود؛ پس تأییدش با passkey و روی همین نسخه است (<span className="fig">sha256 {a.sha256.slice(0, 12)}…</span>).</p>
      </div>
    </Sheet>
  );
}

function KbPropose({ onClose, company: initial }: { onClose: () => void; company: string | null }) {
  const act = useKbAction();
  const toast = useToast();
  const [company, setCompany] = useState<string | null>(initial);
  const [kind, setKind] = useState<KbKind>('faq');
  const [key, setKey] = useState('');
  const [question, setQuestion] = useState('');
  const [variants, setVariants] = useState('');
  const [answer, setAnswer] = useState('');
  const [links, setLinks] = useState('');
  const [codes, setCodes] = useState('');
  const linky = kind === 'referral' || kind === 'official_link';
  const lines = (s: string) => s.split('\n').map((x) => x.trim()).filter(Boolean);
  const body: KbArticleIn | null = company ? {
    company, kind, question_fa: question.trim(), answer_md: answer.trim(), variants: lines(variants), ...(kind === 'policy' && key.trim() ? { key: key.trim() } : {}),
    ...(linky ? { links: lines(links).map((l) => { const [url = '', ...label] = l.split(/\s+/); return { url, label_fa: label.join(' ') }; }) } : {}),
    ...(kind === 'referral' ? { codes: lines(codes).map((l) => { const [exchange = '', code = ''] = l.split(/\s+/); return { exchange, code }; }) } : {}),
  } : null;
  const valid = !!body && body.question_fa.length >= 3 && body.answer_md.length >= 5 && (kind !== 'policy' || !!key.trim()) && (!linky || (body.links ?? []).every((l) => /^https:\/\/\S+$/.test(l.url)));
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title="مقاله‌ی تازه" description="پیشنهاد میشود؛ تا تأیید تو با passkey، به هیچ مشتری‌ای نمیرسد." width={600}
      footer={<Button variant="primary" icon="knowledge" className="w-full" disabled={!valid} loading={act.propose.isPending} onClick={() => body && act.propose.mutateAsync(body).then((a) => { toast({ tone: 'ok', text: <>پیشنهاد <span className="fig">{a.ref}</span> ثبت شد؛ برای اثر، تأییدش کن.</> }); onClose(); }).catch((e) => toast({ tone: 'error', text: faError(e) }))}>ثبت پیشنهاد</Button>}>
      <div className="flex flex-col gap-4 text-[13px]">
        <div className="flex flex-col gap-1.5"><span className="font-semibold text-sec">شرکت</span><CompanyChips value={company} onChange={setCompany} all={false} /></div>
        <div className="flex flex-col gap-1.5"><span className="font-semibold text-sec">نوع</span><div className="flex flex-wrap gap-2">{KINDS.map((k) => <FilterChip key={k} selected={kind === k} onClick={() => setKind(k)}>{KB_KIND[k]}</FilterChip>)}</div></div>
        {kind === 'policy' ? <label className="flex flex-col gap-1.5 font-semibold text-sec">کلید سیاست<input value={key} onChange={(e) => setKey(e.target.value.trim())} dir="ltr" placeholder="vip.min_balance" className={cx(field, 'fig h-10')} /></label> : null}
        <label className="flex flex-col gap-1.5 font-semibold text-sec">پرسش<input value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={300} className={cx(field, 'h-10')} /></label>
        <label className="flex flex-col gap-1.5 font-semibold text-sec">شکل‌های دیگر پرسش (هر خط یکی)<textarea value={variants} onChange={(e) => setVariants(e.target.value)} rows={2} className={cx(field, 'py-2')} /></label>
        <label className="flex flex-col gap-1.5 font-semibold text-sec">جواب<textarea value={answer} onChange={(e) => setAnswer(e.target.value)} rows={6} className={cx(field, 'py-2 leading-7')} placeholder="متغیرها با {{name}}" /></label>
        {linky ? <label className="flex flex-col gap-1.5 font-semibold text-sec">لینک‌ها (هر خط: نشانی، فاصله، عنوان)<textarea value={links} onChange={(e) => setLinks(e.target.value)} rows={3} dir="ltr" className={cx(field, 'fig py-2 text-left')} placeholder="https://… عنوان" /></label> : null}
        {kind === 'referral' ? <label className="flex flex-col gap-1.5 font-semibold text-sec">کدها (هر خط: صرافی، فاصله، کد)<textarea value={codes} onChange={(e) => setCodes(e.target.value)} rows={2} dir="ltr" className={cx(field, 'fig py-2 text-left')} placeholder="lbank CODE" /></label> : null}
        {linky ? <p className="rounded-[12px] bg-tile p-3 text-[12px] leading-6 text-sec">کد و لینک رفرال و لینک رسمی را فقط خودت مینویسی؛ ایجنت هرگز نمیسازد. نگهبان خروجی هر لینک یا کدی را که عیناً این‌جا تأیید نشده رد میکند.</p> : null}
      </div>
    </Sheet>
  );
}

export function KbTab({ initialCompany }: { initialCompany: string | null }) {
  const [company, setCompany] = useState<string | null>(initialCompany);
  const [kind, setKind] = useState<KbKind | null>(null);
  const [status, setStatus] = useState<KbStatus | null>(null);
  const [text, setText] = useState('');
  const q = useKb({ company, kind, status, q: text.trim().length >= 2 ? text : '' });
  const [open, setOpen] = useState<string | null>(null);
  const [neu, setNew] = useState(false);
  const now = useNow();
  const cur = q.data?.find((a) => `${a.ref}@${a.version}` === open);
  return (
    <div className="flex flex-col gap-3">
      <Card className="flex flex-col gap-2 p-4">
        <div className="flex flex-wrap items-center gap-2"><div className="min-w-0 flex-1"><CompanyChips value={company} onChange={setCompany} /></div><Button variant="primary" size="sm" icon="add" onClick={() => setNew(true)}>مقاله‌ی تازه</Button></div>
        <div className="flex flex-wrap gap-2"><FilterChip selected={!kind} onClick={() => setKind(null)}>همه‌ی نوع‌ها</FilterChip>{KINDS.map((k) => <FilterChip key={k} selected={kind === k} onClick={() => setKind(k)}>{KB_KIND[k]}</FilterChip>)}</div>
        <div className="flex flex-wrap items-center gap-2">
          <FilterChip selected={!status} onClick={() => setStatus(null)}>همه</FilterChip>{KB_STATES.map((s) => <FilterChip key={s} selected={status === s} onClick={() => setStatus(s)}>{KB_STATUS[s]!.fa}</FilterChip>)}
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="جستجو" aria-label="جستجو در دانشنامه" className="h-8 min-w-[8rem] flex-1 rounded-[10px] border border-strong bg-tile px-3 text-[13px] text-ink outline-none focus:border-gold-ink" />
        </div>
      </Card>
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isLoading ? <Skeleton className="h-48" /> : !q.data?.length ? <Empty icon="knowledge" title="مقاله‌ای نیست" /> : (
        <div className="grid items-start gap-3 md:grid-cols-2">
          {q.data.map((a) => {
            const soon = !!now && a.status === 'approved' && new Date(a.expires_at).getTime() - now < 14 * 86_400_000;
            return (
              <button key={`${a.ref}@${a.version}`} type="button" onClick={() => setOpen(`${a.ref}@${a.version}`)} className={cx('flex min-w-0 flex-col gap-2 rounded-[16px] p-4 text-start transition-colors hover:bg-hover', a.status === 'proposed' ? 'bg-gold-soft' : 'bg-card', (a.status === 'retired' || a.status === 'expired') && 'opacity-70')}>
                <span className="flex items-center gap-2 text-[11px] text-muted"><CompanyMark code={a.company} height={11} mono /><span>{KB_KIND[a.kind]}</span><span className="fig">{a.ref}@{a.version}</span>{a.key ? <span className="fig text-sec">{a.key}</span> : null}<span className="flex-1" /><Pill tone={KB_STATUS[a.status]?.tone ?? 'neutral'} dot>{KB_STATUS[a.status]?.fa ?? a.status}</Pill></span>
                <span className="text-[14px] font-semibold leading-6 text-ink">{a.question_fa}</span>
                <span className="line-clamp-2 whitespace-pre-line text-[12px] leading-6 text-sec"><Prose text={a.answer_md.replace(/\*\*|__|`/g, '')} /></span>
                <span className="flex flex-wrap items-center gap-x-3 text-[11px] text-muted"><span>{KB_SOURCE[a.source.kind] ?? a.source.kind}</span><span>{a.uses_30d} بار در ۳۰ روز</span><span className={cx(soon && 'text-warn')}>انقضا {until(a.expires_at)}</span></span>
              </button>
            );
          })}
        </div>
      )}
      {cur ? <KbSheet a={cur} onClose={() => setOpen(null)} /> : null}
      {neu ? <KbPropose company={company} onClose={() => setNew(false)} /> : null}
    </div>
  );
}

// ----------------------------------------------------------- shadow test --
const VERDICT_FA: Record<string, { fa: string; tone: 'neg' | 'warn' | 'neutral' }> = { wrong: { fa: 'نادرست', tone: 'neg' }, partial: { fa: 'ناقص', tone: 'warn' }, safety: { fa: 'خطای ایمنی', tone: 'neg' } };

function ShadowCard({ company, r }: { company: string; r: ShadowReport | undefined }) {
  const act = useShadowAction();
  const toast = useToast();
  const { data: companies } = useCompanies();
  const pick = useRef<HTMLInputElement>(null);
  const [pct, setPct] = useState<number | null>(null);
  const upload = async (file: File) => {
    setPct(0);
    try {
      const ref = await uploadFile(file, file.name, setPct);
      const out = await act.history.mutateAsync({ company, file_id: ref.id });
      toast({ tone: 'ok', text: <>مجموعه‌ی آزمون {out.suite ? <span className="fig">{out.suite}</span> : null} ساخته شد{out.cases ? <>، {out.cases} سؤال ماسک‌شده</> : null}. حالا اجرا کن.</> });
    } catch (e) { toast({ tone: 'error', text: faError(e) }); }
    finally { setPct(null); }
  };
  const correct = r && r.total ? r.correct / r.total : null;
  return (
    <Card className="flex flex-col gap-3 p-4">
      <SectionTitle title={<span className="flex items-center gap-2"><CompanyMark code={company} height={16} mono />{companies?.find((c) => c.code === company)?.name_fa ?? company}</span>}
        action={r ? <Pill tone={r.pass ? 'pos' : 'neg'} dot>{r.pass ? 'قبول' : 'قبول نشد'}</Pill> : <Pill tone="neutral">هنوز آزمونی نیست</Pill>} />
      {r ? (
        <>
          <div className="flex items-baseline gap-2"><span className={cx('fig text-[28px] font-semibold leading-8', correct != null && correct < r.threshold && 'text-warn')}>{rate(correct)}</span><span className="text-[12px] text-sec">درست، از <span className="fig">{r.total}</span> سؤال؛ مرز قبولی <span className="fig">{rate(r.threshold)}</span> (خط عمودی)</span></div>
          {/* The pass line sits on the bar itself: the correct share starts at the left edge, so it passes when it reaches the line. */}
          <div className="relative">
            <span aria-hidden className="absolute -top-[3px] z-10 h-4 w-[2px] rounded-full bg-ink" style={{ left: `${r.threshold * 100}%` }} />
            <StackedBar label="درست، ناقص و نادرست" height={10} segs={[
              { key: 'c', label: 'درست', value: r.correct, color: 'var(--hq-positive)', fmt: String(r.correct) },
              { key: 'p', label: 'ناقص', value: r.partial, color: 'var(--hq-warning)', fmt: String(r.partial) },
              { key: 'w', label: 'نادرست', value: r.wrong, color: 'var(--hq-negative)', fmt: String(r.wrong) },
            ]} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Fact label="خطای ایمنی"><span className={cx('fig', r.safety_failures ? 'text-neg' : 'text-pos')}>{r.safety_failures}</span></Fact>
            <Fact label="کد یا لینک اشتباه"><span className={cx('fig', r.wrong_codes ? 'text-neg' : 'text-pos')}>{r.wrong_codes}</span></Fact>
          </div>
          <span className="text-[11px] text-muted"><span className="fig">{r.suite}</span> · {jDateTime(r.at)}</span>
          {r.disagreements.length ? (
            <div className="flex flex-col gap-1.5">
              <span className="text-[12px] font-semibold text-sec">اختلاف‌ها (در صف آموزش تو)</span>
              {r.disagreements.map((d) => (
                <div key={d.case} className="flex items-start gap-2 rounded-[10px] bg-tile px-3 py-2 text-[12px] leading-6">
                  <Pill tone={VERDICT_FA[d.verdict]?.tone ?? 'neutral'}>{VERDICT_FA[d.verdict]?.fa ?? d.verdict}</Pill>
                  <span className="min-w-0 flex-1 text-ink">{d.note_fa}</span><span className="fig text-muted">{d.case}</span>
                </div>
              ))}
            </div>
          ) : null}
        </>
      ) : <p className="text-[13px] leading-6 text-sec">تاریخچه‌ی واقعی گفت‌وگوهای پشتیبانی را بده (خروجی Telegram Desktop یا CSV پرسش و پاسخ)؛ تا ۱۰۰ سؤال ماسک‌شده با جواب‌های خودت آزمون خصوصی همین شرکت میشود.</p>}
      <div className="flex flex-wrap items-center gap-2">
        <input ref={pick} type="file" hidden accept=".json,.csv,application/json,text/csv" onChange={(e) => { const f = e.target.files?.[0]; if (f) void upload(f); e.target.value = ''; }} />
        <Button size="sm" variant="secondary" icon="attach" loading={pct != null} onClick={() => pick.current?.click()}>{pct != null ? <span className="fig">{pct}%</span> : 'تاریخچه‌ی گفت‌وگو'}</Button>
        <Button size="sm" variant="primary" icon="refresh" disabled={!r} loading={act.run.isPending && act.run.variables === company} onClick={() => act.run.mutateAsync(company).then(() => toast({ tone: 'ok', text: 'اجرا شروع شد؛ هزینه‌اش از سقف آکادمی است.' })).catch((e) => toast({ tone: 'error', text: faError(e) }))}>اجرای آزمون</Button>
      </div>
    </Card>
  );
}

export function ShadowTab() {
  const q = useShadow();
  const { data: companies } = useCompanies();
  const cos = (companies ?? []).filter((c) => c.kind !== 'holding').map((c) => c.code);
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <Skeleton className="h-60" />;
  return (
    <div className="flex flex-col gap-3">
      <p className="max-w-3xl text-[13px] leading-6 text-sec">قبولی یعنی دست‌کم <span className="fig">90%</span> درست، <b>و</b> صفر خطای ایمنی، <b>و</b> صفر کد یا لینک اشتباه. فقط بعد از قبولی کارت شروع آن شرکت ساخته میشود؛ آزمون هرگز از شرکت بیرون نمیرود.</p>
      <div className="grid items-start gap-4 lg:grid-cols-2 2xl:grid-cols-3">{cos.map((c) => <ShadowCard key={c} company={c} r={q.data.find((r) => r.company === c)} />)}</div>
    </div>
  );
}
