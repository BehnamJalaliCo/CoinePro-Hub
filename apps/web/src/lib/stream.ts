'use client';

import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { isMock } from './api/client';

export type StreamEvent = { id: string; type: string; at: string; company: string | null; ref: string | null; data: Record<string, unknown> };

// Every named SSE event of contract §7 and §16 (EventSource only delivers named events to their listeners).
const EVENT_TYPES = [
  'work.created', 'work.updated', 'work.delegated', 'work.completed',
  'decision.created', 'decision.decided', 'deliverable.created', 'deliverable.rated',
  'message.created', 'notification.created', 'presence.changed', 'control.changed',
  'employee.updated', 'activity.changed', 'llm.call.started', 'llm.call.finished',
  'budget.alert', 'run.started', 'run.step', 'run.finished',
  // ⟨1.3⟩ §17.6
  'file.ready', 'file.failed', 'workshop.session', 'workshop.approval', 'order.routed',
  // ⟨1.4⟩ §18.10, ⟨1.4.2⟩ §18.11
  'oversight.finding', 'oversight.hold', 'oversight.watch', 'inquiry.answered', 'errand.updated', 'stars.rollup', 'skill.updated',
  'academy.eval', 'founding.updated', 'provision.step', 'backup.done', 'backup.failed', 'hiring.changed', 'story.created',
  // ⟨1.4.6⟩ §18.14
  'brand.updated',
  // ⟨1.5⟩ §19.9
  'revenue.day', 'revenue.alert', 'support.message', 'support.queue', 'support.channel', 'rescue.updated', 'lifecycle.sent', 'nps.closed', 'feedback.item',
  // ⟨1.5⟩ §20.11
  'meeting.scheduled', 'meeting.started', 'meeting.turn', 'meeting.claim', 'meeting.whisper', 'meeting.ended',
  'charter.sealed', 'kpi.stale', 'okr.updated', 'outcome.due', 'risk.updated', 'calendar.conflict', 'knowledge.updated', 'knowledge.expiring',
  // ⟨1.5⟩ §21.12
  'memo.ready', 'advisor.proactive', 'ask.answered', 'review.updated', 'briefing.ready', 'rankings.updated', 'hr.round', 'note.created',
  'decision.reminded', 'claim.verdict', 'dceo.scored', 'substitute.updated', 'creative.updated',
  // ⟨1.6⟩ §22.6
  'media.item', 'legal.case', 'role.updated',
  // ⟨1.7⟩ §23.11
  'record.filed', 'record.updated', 'record.sealed', 'reminder.due', 'hold.changed', 'fixity.failed', 'schema.changed',
] as const;

const CORE_TOPICS = 'work,decisions,deliverables,messages,notifications,activity,llm,control';
// Unknown topics are ignored from contract v1.4.2 on, so the app names every topic it can use, the newer ones too.
const TOPICS = `${CORE_TOPICS},runs,files,workshop,orders,oversight,inquiries,errands,stars,skills,academy,founding,backups,stories,companies,revenue,support,growth,feedback,meetings,governance,knowledge,advisor,ask,reviews,briefings,people,notes,quality,dceo,treasury,creatives,media,legal,archive`;
// The hub refuses a `topics` longer than 200 characters (422), so the topics are split into disjoint groups, one connection each.
const TOPICS_MAX = 200;
export function topicGroups(all: string = TOPICS, max: number = TOPICS_MAX): string[] {
  const groups: string[] = [];
  let cur = '';
  for (const t of all.split(',')) {
    const next = cur ? `${cur},${t}` : t;
    if (next.length > max && cur) { groups.push(cur); cur = t; } else cur = next;
  }
  if (cur) groups.push(cur);
  return groups;
}

// Event type prefix -> query keys to refresh (contract §7, §16).
const INVALIDATE: Array<[string, string[]]> = [
  ['decision.', ['decisions', 'inbox', 'away']],
  ['deliverable.', ['deliverables', 'inbox']],
  ['work.', ['work', 'planner', 'companies']],
  ['message.', ['threads', 'messages', 'inbox']],
  ['notification.', ['notifications', 'inbox']],
  ['control.', ['control', 'companies']],
  ['employee.', ['employees', 'companies']],
  ['presence.', ['presence', 'inbox']],
  ['budget.', ['treasury']],
  ['llm.', ['treasury']],
  ['run.', ['runs']],
  ['file.', ['messages']],
  ['workshop.', ['workshop']],
  ['order.', ['orders', 'planner', 'work']],
  ['hiring.', ['hiring']],
  ['story.', ['stories']],
  ['oversight.', ['oversight']],
  ['inquiry.', ['inquiries']],
  ['errand.', ['errands']],
  ['stars.', ['stars']],
  ['skill.', ['skills']],
  ['academy.', ['academy']],
  ['founding.', ['founding']],
  ['provision.', ['founding']],
  ['backup.', ['backups']],
  // A traced or sealed brand: the company's versions, every mark and seal (GET /brands), and the founding's step.
  ['brand.', ['brand', 'brands', 'companies', 'founding']],
  // ⟨1.5⟩ §19.9: the radar, the desk (queue, conversations, channels), rescue and lifecycle sends, a closed NPS wave (its comments
  // reach the feedback inbox), and feedback items.
  ['revenue.', ['revenue']],
  ['support.', ['support']],
  ['rescue.', ['growth']],
  ['lifecycle.', ['growth']],
  ['nps.', ['growth', 'feedback']],
  ['feedback.', ['feedback']],
  // ⟨1.5⟩ §20.11: a meeting's turns, claims and whispers (the room and the planner); a sealed charter; a stale KPI (cards and the
  // scorecard); OKR and outcome updates; risks; calendar conflicts (the deploy cards carry them too); knowledge and its expiry.
  ['meeting.', ['meetings', 'planner']],
  ['charter.', ['charter']],
  ['kpi.', ['cards', 'scorecards', 'kpis']],
  ['okr.', ['okr']],
  ['outcome.', ['outcomes']],
  ['risk.', ['risks']],
  ['calendar.', ['calendar', 'planner', 'decisions']],
  ['knowledge.', ['knowledge']],
  // ⟨1.5⟩ §21.12: a memo is ready (the card shows it), a proactive note (thread A), an answer, the weekly review, a briefing, ranks and
  // the HR round (its cards), a note, a claim's verdict (the health board), a scored prediction, a substitute's state, a creative.
  // `decision.reminded` is covered by `decision.`.
  ['memo.', ['memos', 'decisions']],
  ['advisor.', ['advisor', 'messages', 'threads']],
  ['ask.', ['ask']],
  ['review.', ['reviews']],
  ['briefing.', ['briefings']],
  ['rankings.', ['rankings']],
  ['hr.', ['hr', 'decisions']],
  ['note.', ['notes']],
  ['claim.', ['claims', 'runs-health']],
  ['dceo.', ['dceo', 'decisions']],
  ['substitute.', ['substitutes', 'treasury']],
  ['creative.', ['creatives']],
  // ⟨1.6⟩ §22.6: an item moved in the pipeline (the board, its series, the cards it raised); a case changed (its thread L and its email
  // cards); a role written on demand changed state (the department's roles, GET /roles for hiring, the story it makes).
  ['media.', ['media', 'decisions']],
  ['legal.', ['legal', 'threads', 'decisions']],
  ['role.', ['roles', 'stories', 'decisions']],
  // ⟨1.7⟩ §23.11: a record filed, changed or sealed; a reminder due; a hold placed or released (its case too); a fixity failure; a schema change.
  ['record.', ['archive']],
  ['reminder.', ['archive']],
  ['hold.', ['archive', 'legal']],
  ['fixity.', ['archive']],
  ['schema.', ['archive', 'decisions']],
];

export type StreamState = 'connecting' | 'live' | 'offline';

/** The app's SSE connections (one per topic group); each resumes with Last-Event-ID (the browser does it). */
export function useHoldingStream(onEvent?: (e: StreamEvent) => void): StreamState {
  const qc = useQueryClient();
  const [state, setState] = useState<StreamState>(isMock ? 'live' : 'connecting');
  const cb = useRef(onEvent);
  useLayoutEffect(() => { cb.current = onEvent; });

  useEffect(() => {
    if (isMock) {
      let n = 0;
      const t = setInterval(() => {
        n += 1;
        cb.current?.({ id: String(n), type: 'activity.changed', at: new Date().toISOString(), company: ['TY', 'FX', 'PC'][n % 3] ?? null, ref: null, data: { pulse: n } });
      }, 2400);
      return () => clearInterval(t);
    }
    const groups = topicGroups();
    const sources: Array<EventSource | null> = groups.map(() => null);
    const openSet = new Set<number>();
    const timers: Array<ReturnType<typeof setTimeout> | undefined> = groups.map(() => undefined);
    let closed = false;
    // A server older than contract v1.4.2 refuses topics it does not know (422), which EventSource only sees as an error
    // before the stream opened; after one such failure only the core topics are asked for, on the first connection alone.
    let coreOnly = false;
    const open = (i: number, retry: number) => {
      if (coreOnly && i > 0) return;
      let opened = false;
      const es = new EventSource(`/api/v1/stream?topics=${coreOnly ? CORE_TOPICS : groups[i]}`, { withCredentials: true });
      sources[i] = es;
      es.onopen = () => { opened = true; retry = 0; openSet.add(i); setState('live'); };
      es.onerror = () => {
        if (!opened && i === 0 && !coreOnly && retry >= 1) coreOnly = true;
        openSet.delete(i);
        if (openSet.size === 0) setState('offline');
        es.close();
        if (closed) return;
        const next = Math.min(retry + 1, 6);
        timers[i] = setTimeout(() => open(i, next), 1000 * 2 ** next);
      };
      es.onmessage = (m) => handle(m);
      for (const t of EVENT_TYPES) es.addEventListener(t, handle as EventListener);
    };
    const handle = (m: MessageEvent) => {
      let e: StreamEvent;
      try { e = JSON.parse(m.data) as StreamEvent; } catch { return; }
      for (const [prefix, keys] of INVALIDATE) if (e.type.startsWith(prefix)) for (const k of keys) void qc.invalidateQueries({ queryKey: [k] });
      cb.current?.(e);
    };
    groups.forEach((_, i) => open(i, 0));
    return () => { closed = true; for (const t of timers) if (t) clearTimeout(t); for (const es of sources) es?.close(); };
  }, [qc]);

  return state;
}
