'use client';

import { useState } from 'react';
import { Icon } from '@/components/icon';
import { Button, Spinner } from '@/components/ui/button';
import { Md } from '@/components/ui/md';
import { Sheet } from '@/components/ui/overlay';
import { Card, Empty, FilterChip, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { CoMark, RefChip } from '@/components/v17/bits';
import { useCompanies } from '@/lib/api/hooks';
import { ASK_MAX, faError, useAsk, useAskHub, useAsks, type Ask, type AskCitation } from '@/lib/api/v18';
import { ago, cx, tokens, usd } from '@/lib/format';
import { CITATION } from './bits';

const STATE_FA: Record<string, string> = { queued: 'در صف…', searching: 'جستجو در مصوبه‌ها، تصمیم‌ها، سندها و کد…', answering: 'کتابدار هاب فقط از همین قطعه‌ها جواب مینویسد…', failed: 'جواب معتبری ساخته نشد.' };

function Citation({ c }: { c: AskCitation }) {
  const k = CITATION[c.kind] ?? { fa: c.kind, icon: 'info' as const };
  return (
    <li className="flex flex-col gap-1.5 rounded-[12px] bg-tile p-2.5">
      <div className="flex min-w-0 flex-wrap items-center gap-2 text-[12px]">
        <span className="inline-flex items-center gap-1 text-sec"><Icon name={k.icon} size={14} />{k.fa}</span>
        {c.ref ? <RefChip r={c.ref} /> : null}
        {c.path ? (
          <span dir="ltr" className="fig min-w-0 truncate text-[11px] text-muted" title={`${c.repo ?? ''} ${c.path}`}>
            {c.repo ? `${c.repo.split('/').at(-1)}/` : ''}{c.path}{c.lines ? `#L${c.lines[0]}-${c.lines[1]}` : ''}{c.commit ? ` @${c.commit}` : ''}
          </span>
        ) : null}
      </div>
      {c.snippet ? (c.kind === 'code' ? <pre dir="ltr" className="fig overflow-x-auto whitespace-pre rounded-[8px] bg-page p-2 text-[11px] leading-5 text-ink">{c.snippet}</pre> : <p className="text-[12px] leading-5 text-sec">«{c.snippet}»</p>) : null}
    </li>
  );
}

/** One question and its answer: state while it runs, the cited answer, what was not indexed, the cost. */
export function AskAnswer({ a }: { a: Ask }) {
  const live = a.state === 'queued' || a.state === 'searching' || a.state === 'answering';
  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted">
        <span className="fig">{a.ref}</span><span>{ago(a.created_at)}</span>
        {a.scope?.companies?.length ? <span className="flex items-center gap-1">{a.scope.companies.map((c) => <CoMark key={c} code={c} height={10} />)}</span> : null}
        <span className="flex-1" />
        {a.state === 'done' ? <span>{a.found ? `${a.found} قطعه` : 'چیزی پیدا نشد'} · <span className="fig">{tokens(a.usage.tokens)} · {usd(a.usage.usd, 3)}</span></span> : null}
      </div>
      {live || a.state === 'failed' ? (
        <div className={cx('flex items-center gap-2 text-[13px]', a.state === 'failed' ? 'text-neg' : 'text-sec')}>{live ? <Spinner size={16} className="text-gold-ink" /> : <Icon name="urgent" size={16} />}{STATE_FA[a.state]}</div>
      ) : null}
      {a.answer_md ? <Md text={a.answer_md} className="flex flex-col gap-2 text-[14px] leading-7 text-ink" /> : null}
      {a.citations.length ? <ul className="flex flex-col gap-1.5">{a.citations.map((c, i) => <Citation key={i} c={c} />)}</ul> : null}
      {a.not_indexed.length ? <p className="text-[11px] text-muted">هاب این ریپوها را نمیخواند و در جستجو نبودند: <span className="fig" dir="ltr">{a.not_indexed.join('، ')}</span></p> : null}
    </div>
  );
}

function History({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const q = useAsks();
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  const [sel, setSel] = useState<string | null>(null);
  return (
    <Sheet open={open} onOpenChange={onOpenChange} width={560} title="پرسش‌های قبلی از هاب" description="جستجو کد است (متن کامل، بدون embedding)؛ چیزی پیدا نشود، هیچ مدلی اجرا نمیشود.">
      {q.isLoading ? <Skeleton className="h-48" /> : !items.length ? <Empty icon="search" title="هنوز چیزی نپرسیده‌ای" /> : (
        <ul className="flex flex-col gap-2">
          {items.map((a) => (
            <li key={a.ref} className="flex flex-col gap-2 rounded-[12px] bg-tile p-3">
              <button type="button" onClick={() => setSel(sel === a.ref ? null : a.ref)} aria-expanded={sel === a.ref} className="flex items-start gap-2 text-start">
                <span className="min-w-0 flex-1 text-[13px] font-semibold text-ink">{a.q}</span>
                <span className="text-[11px] text-muted">{a.found ? `${a.found} قطعه` : 'بی‌نتیجه'}</span>
                <Icon name="chevron" size={14} className={cx('mt-0.5 text-muted transition-transform', sel === a.ref && 'rotate-180')} />
              </button>
              {sel === a.ref ? <div className="rounded-[10px] bg-card p-3"><AskAnswer a={a} /></div> : null}
            </li>
          ))}
        </ul>
      )}
    </Sheet>
  );
}

/** «از هاب بپرس» (§21.2): one question, a short answer with exact references to resolutions, decisions, deliverables, messages, docs or lines of code. */
export function AskBox() {
  const [q, setQ] = useState('');
  const [scope, setScope] = useState<string[]>([]);
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [ref, setRef] = useState<string | null>(null);
  const [hist, setHist] = useState(false);
  const ask = useAskHub();
  const one = useAsk(ref);
  const { data: companies } = useCompanies();
  const toast = useToast();
  const text = q.trim();
  const submit = async () => {
    if (!text || text.length > ASK_MAX) return;
    try {
      const a = await ask.mutateAsync({ q: text, scope: scope.length ? { companies: scope } : null, key });
      setRef(a.ref);
      setKey(crypto.randomUUID());
    } catch (e) { toast({ tone: 'error', text: faError(e) }); }
  };
  const toggle = (c: string) => setScope((s) => (s.includes(c) ? s.filter((x) => x !== c) : [...s, c]));
  return (
    <Card className="flex flex-col gap-3 p-4">
      <SectionTitle title="از هاب بپرس" note="جواب فقط از سوابق، سندها و کد، با ارجاع دقیق" action={<Button variant="text" size="sm" icon="time" onClick={() => setHist(true)}>قبلی‌ها</Button>} />
      <form onSubmit={(e) => { e.preventDefault(); void submit(); }} className="flex items-end gap-2 rounded-[14px] border border-strong bg-tile p-1.5 focus-within:border-gold-ink">
        <textarea value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void submit(); } }}
          rows={Math.min(4, Math.max(1, q.split('\n').length))} maxLength={ASK_MAX} placeholder="مثلاً: چرا گزارش روزانه‌ی مدیرعامل‌ها خاموش است؟" aria-label="پرسش از هاب"
          className="min-h-10 min-w-0 flex-1 resize-none bg-transparent px-2 py-2 text-[14px] leading-6 text-ink outline-none placeholder:text-muted" />
        <button type="submit" disabled={!text || ask.isPending} aria-label="بپرس" className="flex size-10 flex-none items-center justify-center rounded-full bg-gold text-on-gold hover:bg-gold-bright disabled:bg-disabled-fill disabled:text-disabled">
          {ask.isPending ? <Spinner size={16} /> : <Icon name="search" size={18} />}
        </button>
      </form>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[11px] text-muted">فقط در:</span>
        {(companies ?? []).map((c) => <FilterChip key={c.code} selected={scope.includes(c.code)} onClick={() => toggle(c.code)}><span className="flex items-center gap-1.5"><CoMark code={c.code} height={11} />{c.name_fa}</span></FilterChip>)}
        {q.length > ASK_MAX * 0.8 ? <span className="fig ms-auto text-[11px] text-muted">{q.length}/{ASK_MAX}</span> : null}
      </div>
      {ref ? (one.data ? <div className="rounded-[12px] bg-card p-1"><AskAnswer a={one.data} /></div> : <Skeleton className="h-16" />) : null}
      <History open={hist} onOpenChange={setHist} />
    </Card>
  );
}
