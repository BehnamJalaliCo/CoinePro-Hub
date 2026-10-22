'use client';

import Link from 'next/link';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Icon } from '@/components/icon';
import { Avatar, Orb } from '@/components/brand/avatar';
import { MessageMedia } from '@/components/media/attachments';
import { Composer } from '@/components/media/composer';
import { Md } from '@/components/ui/md';
import { RecordResolution } from '@/components/v15/record-resolution';
import { Empty, ErrorState, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ApiError, isMock, type Schemas } from '@/lib/api/client';
import { useMarkRead, useMessages, useSend } from '@/lib/api/hooks';
import type { MediaRef } from '@/lib/api/v13';
import type { AdvisorMeta } from '@/lib/api/v18';
import { TRIGGER } from '@/components/v18/bits';
import { cx, jDateTime, jTime } from '@/lib/format';

type Msg = Schemas['Message'];

const LINKS: Record<string, (ref: string) => string> = {
  decision: (r) => `/cartable?ref=${r}`, work: (r) => `/work/${r}`, resolution: () => '/resolutions',
  errand: () => '/assistant', teaching: () => '/academy', inquiry: () => '/advisor', finding: () => '/oversight', session: (r) => `/workshop/${r}`,
  // ⟨1.6⟩ §22: the counsel's cases (thread L), media items and series.
  case: (r) => `/legal?case=${r}`, media_item: (r) => `/media?item=${r}`, series: (r) => `/media/series?ref=${r}`,
};
function linkHref(kind: string, ref: string) {
  return LINKS[kind]?.(ref) ?? '#';
}

function Bubble({ m, agentKind, onResolve }: { m: Msg; agentKind: string; onResolve: (m: Msg) => void }) {
  const mine = m.author.kind === 'owner';
  const links = Object.entries((m.links ?? {}) as Record<string, string | null>).filter(([, v]) => v);
  // ⟨1.3⟩ attachments carry kind, variants and transcript; the generated FileRef is still the 1.2 shape.
  const media = (m.attachments ?? []) as unknown as MediaRef[];
  const voice = m.kind === 'voice_transcript';
  // ⟨1.5⟩ §21.1, §21.3: the advisor's devil's-advocate replies, proactive notes and the weekly review brief carry `meta`.
  const meta = ((m as unknown as { meta?: AdvisorMeta | null }).meta ?? {}) as AdvisorMeta;
  return (
    <div className={cx('flex gap-3', mine ? 'flex-row-reverse' : '')}>
      {!mine ? <span className="mt-1">{agentKind === 'advisor' ? <Orb size={32} /> : <Avatar kind={agentKind} size={32} />}</span> : null}
      <div className={cx('flex max-w-[min(680px,86%)] flex-col gap-1.5', mine ? 'items-end' : 'items-start')}>
        {media.length ? <MessageMedia items={media} transcriptInBody={voice} /> : null}
        {m.body.trim() ? (
          <div className={cx('rounded-[16px] px-4 py-3', mine ? 'rounded-tl-[6px] bg-raised text-ink' : 'rounded-tr-[6px] bg-card')}>
            <Md text={m.body} className="flex flex-col gap-2 text-[14px] leading-7 text-ink" />
          </div>
        ) : null}
        <div className={cx('flex flex-wrap items-center gap-2 px-1 text-[11px] text-muted', mine && 'flex-row-reverse')}>
          {meta.mode === 'devil' ? <span className="rounded-full bg-neg-soft px-2 py-0.5 font-semibold text-neg">مخالف‌خوان</span> : null}
          {meta.proactive ? <span className="inline-flex items-center gap-1 rounded-full bg-lapis-soft px-2 py-0.5 font-semibold text-lapis"><Icon name={TRIGGER[meta.proactive.kind]?.icon ?? 'bell'} size={12} />گزارش فعال · {TRIGGER[meta.proactive.kind]?.fa ?? meta.proactive.kind}</span> : null}
          {meta.review ? <span className="rounded-full bg-gold-soft px-2 py-0.5 font-semibold text-gold-ink">مرور هفتگی <span className="fig">{meta.review}</span></span> : null}
          {voice ? <span className="flex items-center gap-1" title="از ویس، به متن دقیق"><Icon name="mic" size={12} />ویس</span> : null}
          <span title={jDateTime(m.created_at)}>{jTime(m.created_at)}</span>
          <span className="fig">{m.ref}</span>
          {links.map(([k, v]) => (
            <Link key={k} href={linkHref(k, v!)} className="fig rounded-full bg-tile px-2 py-0.5 text-gold-ink hover:bg-hover">{v}</Link>
          ))}
          {m.body.trim() ? <button type="button" onClick={() => onResolve(m)} className="rounded-full px-2 py-0.5 text-sec hover:bg-hover hover:text-ink" title="این پیام را به‌عنوان مصوبه ثبت کن">مصوبه</button> : null}
        </div>
      </div>
    </div>
  );
}

type Live = { state: 'idle' | 'thinking' | 'writing' | 'failed'; text: string };

/** Watch the agent's reply as it is written (contract §16.3). Falls back to polling when the live endpoint is absent. */
function useLiveReply(code: string) {
  const qc = useQueryClient();
  const [live, setLive] = useState<Live>({ state: 'idle', text: '' });
  const es = useRef<EventSource | null>(null);
  const start = () => {
    setLive({ state: 'thinking', text: '' });
    if (isMock) {
      const full = 'دریافت شد. در حالت نمایشی پاسخ واقعی ساخته نمیشود؛ روی سرور، مشاور با Opus 5.5 جواب میدهد و ارجاع‌هایش را میاورد.';
      let i = 0;
      const t = setInterval(() => {
        i += 6;
        setLive({ state: 'writing', text: full.slice(0, i) });
        if (i >= full.length) { clearInterval(t); setTimeout(() => setLive({ state: 'idle', text: '' }), 600); }
      }, 60);
      return;
    }
    es.current?.close();
    const src = new EventSource(`/api/v1/threads/${encodeURIComponent(code)}/live`, { withCredentials: true });
    es.current = src;
    let got = false;
    src.addEventListener('reply.delta', (e) => { got = true; const d = JSON.parse((e as MessageEvent).data) as { text: string }; setLive((l) => ({ state: 'writing', text: l.text + d.text })); });
    const finish = () => { src.close(); void qc.invalidateQueries({ queryKey: ['messages', code] }); void qc.invalidateQueries({ queryKey: ['threads'] }); setLive({ state: 'idle', text: '' }); };
    src.addEventListener('reply.done', finish);
    src.addEventListener('reply.failed', () => { src.close(); setLive({ state: 'failed', text: '' }); });
    src.onerror = () => {
      src.close();
      if (got) return finish();
      // Live endpoint not available: poll for the stored reply for up to two minutes.
      let n = 0;
      const t = setInterval(() => { n++; void qc.invalidateQueries({ queryKey: ['messages', code] }); if (n > 40) { clearInterval(t); setLive({ state: 'idle', text: '' }); } }, 3000);
    };
  };
  useEffect(() => () => es.current?.close(), []);
  return { live, start, stop: () => { es.current?.close(); setLive({ state: 'idle', text: '' }); } };
}

export function Chat({ code, agentKind, placeholder, suggestions, mode }: { code: string; agentKind: string; placeholder: string; suggestions?: string[]; mode?: 'devil' | null }) {
  const q = useMessages(code);
  const send = useSend(code);
  const { mutate: markRead } = useMarkRead(code);
  const toast = useToast();
  const { live, start } = useLiveReply(code);
  const [resolve, setResolve] = useState<Msg | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const items = useMemo(() => q.data?.items ?? [], [q.data]);
  const last = items.at(-1)?.ref;

  useEffect(() => { end.current?.scrollIntoView({ block: 'end' }); }, [items.length, live.text]);
  useEffect(() => { if (last) markRead(last); }, [last, markRead]);

  const submit = async (v: { body: string; attachments: string[] }) => {
    if (!v.body && !v.attachments.length) return;
    try {
      await send.mutateAsync({ ...v, mode });
      start();
    } catch (e) {
      toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'فرستاده نشد.' });
      throw e;
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="scroll-fade-top flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-1 pb-4 pt-6">
        {q.isLoading ? <div className="flex flex-col gap-4">{Array.from({ length: 3 }, (_, i) => <Skeleton key={i} className={cx('h-20', i % 2 ? 'mr-auto w-2/3' : 'w-3/4')} />)}</div>
          : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
          : !items.length && live.state === 'idle' ? (
            <Empty icon="messages" title="گفت‌وگو هنوز شروع نشده" body="هر پیام شناسه‌ی ثابت دارد و برای همیشه میماند؛ بعداً میتوانی به آن استناد کنی." />
          ) : items.map((m) => <Bubble key={m.id} m={m} agentKind={agentKind} onResolve={setResolve} />)}
        {live.state !== 'idle' ? (
          <div className="flex gap-3">
            <span className="mt-1">{agentKind === 'advisor' ? <Orb size={32} state={live.state === 'thinking' ? 'thinking' : 'speaking'} /> : <Avatar kind={agentKind} size={32} state="working" />}</span>
            <div className="max-w-[min(680px,86%)] rounded-[16px] rounded-tr-[6px] bg-card px-4 py-3">
              {live.state === 'thinking' ? <span className="text-[13px] text-muted">در حال فکر…</span>
                : live.state === 'failed' ? <span className="text-[13px] text-neg">پاسخ ساخته نشد؛ دوباره بپرس.</span>
                : <Md text={live.text} className="flex flex-col gap-2 text-[14px] leading-7 text-ink" />}
            </div>
          </div>
        ) : null}
        <div ref={end} />
      </div>
      {suggestions && !items.length ? (
        <div className="flex flex-wrap gap-2 pb-3">
          {suggestions.map((s) => <button key={s} type="button" onClick={() => void submit({ body: s, attachments: [] }).catch(() => undefined)} className="rounded-full border border-strong px-3 py-1.5 text-[13px] text-sec hover:bg-hover hover:text-ink">{s}</button>)}
        </div>
      ) : null}
      <Composer placeholder={placeholder} onSend={submit} sending={send.isPending} />
      {resolve ? <RecordResolution source={{ ref: resolve.ref, body: resolve.body }} onClose={() => setResolve(null)} /> : null}
    </div>
  );
}
