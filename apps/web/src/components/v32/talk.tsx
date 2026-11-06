'use client';

// ⟨1.14⟩ Contract §32 «گفتگو»: the owner talks with the holding secretary, the overseer, the personal assistant, the advisor or any manager,
// by typing, by holding a button, or hands-free. The answer streams in (text, then the spoken sentences in order); work comes out only
// through cards he taps. The voice engine's key is given in the chat's own sheet, never as a message.

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Icon } from '@/components/icon';
import { ConversationPane, FACE_FA, Face, type PaneApi } from '@/components/session/conversation-pane';
import { Button, IconButton } from '@/components/ui/button';
import { Sheet } from '@/components/ui/overlay';
import { Card, FilterChip, Pill, Segmented, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { FaText } from '@/components/v29/text';
import { errText, field } from '@/components/v31/kit';
import { ApiError } from '@/lib/api/client';
import { useCompanies } from '@/lib/api/hooks';
import { useRoles } from '@/lib/api/v14';
import { MODE_FA, turnsOf, useConversation, useConversations, useEngines, usePersonas, useTalkActions, type Conversation, type Mode } from '@/lib/api/v32';
import { ago, cx } from '@/lib/format';
import { EngineLights, KeyDialog, MeterChip, MeterPanel, VoicesPanel, personaFa } from './engines';

const FACES = ['secretary', 'overseer', 'assistant', 'advisor'] as const;

export function Talk() {
  const router = useRouter();
  const toast = useToast();
  const act = useTalkActions();
  const engines = useEngines();
  const convs = useConversations();
  const companies = useCompanies();
  const [ref, setRef] = useState<string | null>(null);
  // A new slot remounts the pane (another conversation was picked); a conversation made on the first word keeps the same slot.
  const [slot, setSlot] = useState(0);
  const [face, setFace] = useState<string>('secretary');
  const conv = useConversation(ref);
  const [keyOpen, setKeyOpen] = useState<{ n: number; key: string } | null>(null);
  const [meterOpen, setMeterOpen] = useState(false);
  const [voicesOpen, setVoicesOpen] = useState(false);
  const [listOpen, setListOpen] = useState(false);
  const [plus, setPlus] = useState(false);
  const [pulse, setPulse] = useState(0);
  const [busy, setBusy] = useState(false);
  const pane = useRef<PaneApi | null>(null);
  const bindPane = useCallback((a: PaneApi | null) => { pane.current = a; }, []);

  const c = conv.data ?? null;
  const turns = turnsOf(c);
  const mode: Mode = c?.mode ?? 'consult';

  const openKey = (k = '') => setKeyOpen((o) => ({ n: (o?.n ?? 0) + 1, key: k }));
  const ensure = useCallback(async (): Promise<string> => {
    const created = await act.create.mutateAsync({ persona: face });
    setRef(created.ref);
    return created.ref;
  }, [act.create, face]);

  const open = (r: string | null, persona?: string) => {
    setSlot((n) => n + 1);
    setRef(r); if (persona) setFace(persona.includes('@') ? 'manager' : persona);
  };
  // ⟨1.17⟩ A talk bound to an order is that order's session: it opens there.
  const choose = (x: Conversation) => { if (x.order_ref) router.push(`/s/${encodeURIComponent(x.order_ref)}`); else open(x.ref, x.persona); };
  const pick = (k: string) => {
    const mine = (convs.data ?? []).find((x) => x.persona === k);
    setFace(k);
    if (mine) open(mine.ref, k); else open(null, k);
  };
  const setMode = (m: Mode) => { if (ref) act.patch.mutate({ ref, mode: m }, { onError: (e) => toast({ tone: 'error', text: errText(e, 'حالت عوض نشد.') }) }); };
  const minutes = () => ref && act.minutes.mutate(ref, { onSuccess: () => toast({ tone: 'ok', text: 'صورت‌جلسه آماده شد؛ کارتش پایین گفتگو است.' }), onError: (e) => toast({ tone: 'error', text: errText(e, 'صورت‌جلسه ساخته نشد.') }) });
  const present = c?.present ?? [];
  const nameOf = (code: string) => companies.data?.find((x) => x.code === code)?.name_fa ?? code;
  const presentFa = (p: string) => (p.includes('@') ? `${p.startsWith('ceo') ? 'مدیرعامل' : p.split('@')[0]} ${nameOf(p.split('@')[1]!)}` : personaFa(p));
  // ⟨1.17⟩ A talk bound to an order is that order's session: the page says so and leads there.
  const orderRef = c?.order_ref ?? null;

  return (
    <div className="flex flex-col gap-4">
      {/* The header of the talk screen: the engines' light, the meter, the key, the voices. */}
      <Card as="section" className="flex flex-col gap-3 p-4" aria-label="وضعیت صدا">
        <div className="flex flex-wrap items-center gap-2">
          <div className="min-w-0 flex-1"><EngineLights engines={engines.data} onKey={() => openKey()} /></div>
          <MeterChip onOpen={() => setMeterOpen(true)} pulse={pulse} />
          <IconButton icon="lock" label="کلید صدا" onClick={() => openKey()} />
          <IconButton icon="mic" label="صدای چهره‌ها" onClick={() => setVoicesOpen(true)} />
          <IconButton icon="messages" label="گفتگوها" onClick={() => setListOpen(true)} className="lg:hidden" />
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
        <aside className="hidden lg:block" aria-label="گفتگوها"><ConversationList current={ref} onPick={choose} onNew={() => open(null, face)} /></aside>

        <div className="flex min-w-0 flex-col gap-3">
          {/* The faces */}
          <div className="no-scrollbar flex items-start gap-3 overflow-x-auto pb-1" role="radiogroup" aria-label="با چه کسی حرف میزنی">
            {FACES.map((k) => {
              const on = (c ? c.persona === k : face === k) || (!!c && c.present.includes(k) && c.persona === k);
              const talking = busy && on;
              return (
                <button key={k} type="button" role="radio" aria-checked={on} onClick={() => pick(k)} className={cx('flex w-[84px] flex-none flex-col items-center gap-1.5 rounded-[14px] p-2 text-[12px]', on ? 'bg-gold-soft font-semibold text-ink' : 'text-sec hover:bg-hover')}>
                  <Face k={k} state={talking ? 'working' : 'idle'} />
                  <span className="text-center leading-4">{FACE_FA[k]}</span>
                </button>
              );
            })}
            {present.filter((p) => p.includes('@')).map((p) => (
              <span key={p} className="flex w-[84px] flex-none flex-col items-center gap-1.5 rounded-[14px] bg-gold-soft p-2 text-[12px] font-semibold text-ink" aria-label={`حاضر: ${presentFa(p)}`}>
                <Face k="manager" state={busy ? 'working' : 'idle'} />
                <span className="text-center leading-4">{presentFa(p)}</span>
              </span>
            ))}
            <button type="button" onClick={() => setPlus(true)} aria-label="مدیر یک شرکت را بیاور" className="flex w-[84px] flex-none flex-col items-center gap-1.5 rounded-[14px] p-2 text-[12px] text-sec hover:bg-hover">
              <span className="flex size-11 items-center justify-center rounded-full border border-dashed border-strong text-gold-ink"><Icon name="add" size={22} /></span>
              <span className="text-center leading-4">مدیر شرکت</span>
            </button>
          </div>

          {/* Mode, end of a working session, minutes */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="w-56 max-w-full"><Segmented<Mode> label="حالت گفتگو" value={mode} onChange={setMode} options={[{ value: 'consult', label: MODE_FA.consult }, { value: 'work', label: MODE_FA.work }]} /></div>
            {mode === 'work' && ref ? <Button size="sm" icon="stop" disabled={busy} onClick={() => void pane.current?.send('پایان جلسه')}>پایان جلسه</Button> : null}
            {ref ? <Button size="sm" icon="report" loading={act.minutes.isPending} disabled={busy || !turns.length} onClick={minutes}>صورت‌جلسه کن</Button> : null}
            {orderRef ? <Link href={`/s/${encodeURIComponent(orderRef)}`} className="ms-auto text-[13px] font-semibold text-gold-ink hover:underline">این گفتگو جلسه‌ی یک فرمان است؛ برو به جلسه</Link> : null}
          </div>

          <ConversationPane key={slot} conversationRef={ref} face={face} ensure={ensure} onBusy={setBusy} onMeter={() => setPulse((n) => n + 1)} onApi={bindPane} />
        </div>
      </div>

      <Sheet open={listOpen} onOpenChange={setListOpen} title="گفتگوها" width={420}>
        <ConversationList current={ref} onPick={(x) => { choose(x); setListOpen(false); }} onNew={() => { open(null, face); setListOpen(false); }} />
      </Sheet>
      <PlusSheet open={plus} onOpenChange={setPlus} onDone={(r) => { setPlus(false); if (r) { setRef(r); setFace('manager'); } }} current={ref} />
      {keyOpen ? <KeyDialog key={keyOpen.n} open onOpenChange={(v) => { if (!v) setKeyOpen(null); }} initialKey={keyOpen.key} /> : null}
      <MeterPanel open={meterOpen} onOpenChange={setMeterOpen} />
      <VoicesPanel open={voicesOpen} onOpenChange={setVoicesOpen} />
    </div>
  );
}

// ================================================================================================ the conversations ==
function ConversationList({ current, onPick, onNew }: { current: string | null; onPick: (c: Conversation) => void; onNew: () => void }) {
  const [q, setQ] = useState('');
  const [term, setTerm] = useState('');
  useEffect(() => { const h = setTimeout(() => setTerm(q.trim()), 250); return () => clearTimeout(h); }, [q]);
  const list = useConversations({ q: term });
  return (
    <Card as="section" className="flex flex-col gap-3 p-3" aria-label="فهرست گفتگوها">
      <div className="flex items-center gap-2">
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="جست‌وجو در گفتگوها" aria-label="جست‌وجو در گفتگوها" dir="auto" className={cx(field, 'h-10 min-w-0 flex-1')} />
        <IconButton icon="add" label="گفتگوی تازه" onClick={onNew} />
      </div>
      {list.isLoading ? <Skeleton className="h-24 rounded-[12px]" /> : list.data === null ? <p className="text-[13px] text-muted">گفتگو بعد از به‌روزرسانی ستاد میاید.</p> : !list.data?.length ? (
        <p className="py-4 text-center text-[13px] text-muted">{term ? 'چیزی پیدا نشد.' : 'هنوز گفتگویی نیست.'}</p>
      ) : (
        <ul className="flex flex-col gap-1" aria-label="گفتگوها">
          {list.data.map((c) => (
            <li key={c.ref}>
              <button type="button" onClick={() => onPick(c)} aria-current={c.ref === current ? 'true' : undefined} className={cx('flex w-full flex-col gap-0.5 rounded-[10px] px-3 py-2 text-start', c.ref === current ? 'bg-gold-soft' : 'hover:bg-hover')}>
                <span className="flex items-center gap-2 text-[13px] font-semibold text-ink"><span className="min-w-0 flex-1 truncate"><FaText text={c.title_fa} /></span>{c.open_cards ? <Pill tone="gold">{c.open_cards}</Pill> : null}</span>
                <span className="flex gap-2 text-[11px] text-muted"><span>{personaFa(c.persona.includes('@') ? 'manager' : c.persona)}</span><span>{c.last_turn_at ? ago(c.last_turn_at) : 'تازه'}</span></span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

// ============================================================================================= the «+» (company → role) ==
function PlusSheet({ open, onOpenChange, onDone, current }: { open: boolean; onOpenChange: (v: boolean) => void; onDone: (ref: string | null) => void; current: string | null }) {
  const companies = useCompanies();
  const roles = useRoles();
  const act = useTalkActions();
  const toast = useToast();
  const [co, setCo] = useState<string | null>(null);
  const list = useMemo(() => (companies.data ?? []).filter((c) => c.kind !== 'holding' && c.code !== 'HQ'), [companies.data]);
  const rs = (roles.data ?? []).filter((r) => r.scope === 'company' && (r.kind === 'ceo' || r.kind === 'manager') && (!r.company || r.company === co));
  const go = (role: string) => {
    if (!co) return;
    const done = (ref: string) => { setCo(null); onDone(ref); };
    const fail = (e: unknown) => toast({ tone: 'error', text: errText(e, e instanceof ApiError ? 'این مدیر نیامد.' : 'نشد؛ دوباره بزن.') });
    if (current) act.invite.mutate({ ref: current, role, company: co }, { onSuccess: (r) => done(r.ref), onError: fail });
    else act.create.mutate({ persona: 'manager', role, company: co }, { onSuccess: (r) => done(r.ref), onError: fail });
  };
  return (
    <Sheet open={open} onOpenChange={onOpenChange} title="مدیر یک شرکت را بیاور" description="اول شرکت، بعد نقش؛ فقط به اطلاعات همان شرکت دسترسی دارد" width={420}>
      <div className="flex flex-col gap-4">
        <fieldset className="flex flex-col gap-2"><legend className="pb-1 text-[12px] text-sec">شرکت</legend>
          <div className="flex flex-wrap gap-1.5">{list.map((c) => <FilterChip key={c.code} selected={co === c.code} onClick={() => setCo(c.code)}>{c.name_fa}</FilterChip>)}</div>
        </fieldset>
        {co ? (
          <fieldset className="flex flex-col gap-2"><legend className="pb-1 text-[12px] text-sec">نقش</legend>
            <div className="flex flex-wrap gap-1.5">{rs.map((r) => <FilterChip key={r.role} onClick={() => go(r.role)}>{r.title_fa}</FilterChip>)}</div>
          </fieldset>
        ) : null}
      </div>
    </Sheet>
  );
}
