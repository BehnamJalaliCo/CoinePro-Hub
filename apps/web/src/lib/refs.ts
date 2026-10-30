// The ref router (0.5.0, the same table as the Android app's core/data/Refs.kt): one place that turns a ref, a notification's link or a
// planner row into the page it opens. A ref's prefix says what it is (the hub's own sequences, apps/api/migrations): `W-` a work item,
// `MT-` a meeting, `D-` a card, `O-` an output, `AR-` an archive record, `C-` a founding… Only a work item opens the work page:
// `GET /work/{id}` takes a UUID (the page resolves a `W-` ref first), so anything else sent there would be `422 validation_failed`
// (0.4.0 sent `GET /work/MT-0077`).

const UUID = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;
const REF = /^([A-Z]{1,3})-(\d{1,10})$/;
const CHARTER = /^(?:[A-Z]{2,5}|holding)@\d+$/;
const WORK_REF = /^W-\d{3,8}$/;
/** A ref or code a person can read and say: `W-000003`, `O-000041`, `TY-CEO`, `AR-000110`; never an id. */
const HUMAN = /^[A-Z][A-Z0-9]{0,5}(?:-[A-Z0-9]{1,12}){1,3}(?:@\d+)?$/;

/** Prefix → page; `$` stands for the ref itself. */
const ROUTES: Record<string, string> = {
  // the work and the owner's day
  W: '/work/$', D: '/cartable?ref=$', O: '/outputs?ref=$', MT: '/meetings/$', PL: '/planner',
  // the workshop, founding (§17, §18.8)
  S: '/workshop/$', G: '/workshop', AP: '/workshop', C: '/founding/$', PV: '/founding',
  // the overseer, inquiries, errands, incidents, teachings (§18)
  FI: '/oversight', H: '/oversight', CH: '/oversight', SO: '/oversight', Q: '/advisor', E: '/assistant', I: '/sites', TE: '/academy',
  // revenue, support and growth (§19)
  SC: '/support/$', FB: '/feedback', TM: '/growth', LR: '/growth', RC: '/growth',
  // governance (§20)
  K: '/knowledge?ref=$', KB: '/knowledge?ref=$', OB: '/okr', KR: '/okr', RK: '/risks?ref=$', CE: '/calendar', OR: '/outcomes', M: '/resolutions', B: '/cartable',
  // management tools (§21)
  NT: '/notes?ref=$', BR: '/letter?ref=$', CR: '/substitutes?creative=$', DM: '/advisor', WR: '/advisor', DP: '/digital-ceo', CL: '/runs', AK: '/',
  // media and legal (§22)
  SR: '/media/series?ref=$', MI: '/media?item=$', LC: '/legal?case=$', L: '/messages?thread=L',
  // the archive (§23)
  AR: '/archive/$', LH: '/archive/holds?ref=$', PT: '/archive?party=$', FP: '/archive?folder=$',
  RR: '/archive/settings?tab=retention&ref=$', RM: '/archive/settings?tab=reminders&ref=$', AU: '/archive/settings?tab=automations&ref=$',
};

export const isUuid = (s: string | null | undefined): s is string => !!s && UUID.test(s);
export const isWorkRef = (s: string | null | undefined): s is string => !!s && WORK_REF.test(s);
/** Whether [s] may be shown as it is: a ref or a code, not an id or a hash. */
export const isHuman = (s: string | null | undefined): boolean => !!s && !UUID.test(s) && HUMAN.test(s) && (s.match(/\d/g)?.length ?? 0) < 12;

/** The prefix of a ref (`MT` of `MT-0077`), or null when [s] is not a ref. */
export function refPrefix(s: string | null | undefined): string | null {
  return s ? (REF.exec(s.trim())?.[1] ?? null) : null;
}

/** The page [ref] opens, or null when it has none. */
export function refRoute(ref: string): string | null {
  const r = ref.trim();
  if (CHARTER.test(r)) return '/charter';
  const p = refPrefix(r);
  if (!p) return null;
  const to = ROUTES[p];
  return to ? to.replace('$', encodeURIComponent(r)) : null;
}

/** A notification's `link` (contract §6; the kinds the hub raises, `domain/notify.raise_notification` callers). */
export function linkRoute(kind: string | null | undefined, ref: string | null | undefined): string | null {
  const r = ref?.trim() || null;
  const p = refPrefix(r);
  switch (kind) {
    case null: case undefined: return r ? refRoute(r) : null;
    case 'decision': return r ? `/cartable?ref=${r}` : '/cartable';
    case 'deliverable': return r ? `/outputs?ref=${r}` : '/outputs';
    case 'work': return r ? (isWorkRef(r) || isUuid(r) ? `/work/${r}` : refRoute(r)) : '/orders';
    case 'thread': return r ? `/messages?thread=${encodeURIComponent(r)}` : '/messages';
    case 'message': return '/advisor';
    case 'finding': case 'hold': case 'challenge': return '/oversight';
    case 'inquiry': return '/advisor';
    case 'meeting': return r ? `/meetings/${r}` : '/meetings';
    case 'founding': case 'provision_run': return p === 'C' ? `/founding/${r}` : '/founding';
    case 'server_plan': return '/founding';
    case 'code_session': return p === 'S' ? `/workshop/${r}` : '/workshop';
    // ⟨1.8⟩ §26: a company server (by its id) and its activity.
    case 'server': return r ? `/servers/${encodeURIComponent(r)}` : '/servers';
    case 'archive_record': return p === 'AR' ? `/archive/${r}` : '/archive';
    case 'archive_fixity': return '/archive';
    case 'support_conversation': return p === 'SC' ? `/support/${r}` : '/support';
    case 'support_queue': return '/support';
    case 'revenue_alert': return '/revenue';
    case 'substitute': return '/substitutes';
    case 'employee': return r ? `/employees/${r}` : null;
    case 'treasury': return '/treasury';
    case 'academy': return '/academy';
    case 'backup': return '/control';
    case 'audit': return '/audit';
    case 'device': return '/settings';
    default: return r ? refRoute(r) : null;
  }
}

/** A planner row (§1.9, ⟨1.5⟩): work, the owner's reminders (no page of their own), meetings and change-calendar events. */
export function plannerRoute(kind: string | null | undefined, ref: string): string | null {
  if (kind === 'meeting') return `/meetings/${ref}`;
  if (kind === 'calendar') return '/calendar';
  if (kind === 'reminder') return null;
  return refRoute(ref);
}

/** The last guard before the work page: a key that is a ref of something else goes to that thing's own page; a work ref or an id stays. */
export function workRoute(key: string): string | null {
  if (!key) return null;
  if (isWorkRef(key) || isUuid(key)) return `/work/${key}`;
  return refPrefix(key) ? refRoute(key) : `/work/${key}`;
}
