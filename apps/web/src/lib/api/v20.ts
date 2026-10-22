'use client';

// Contract v1.7 §23 (prompt 14): the archive of record, open-layered. Records, versions and files sealed on their manifest; classes and
// their fields (the open layer) over a closed list of field types; the file plan, parties and link kinds; levels and clearance; retention,
// disposal by the owner's seal and legal holds; reminders; automations over a closed vocabulary; system sources; search; the schema API.
// The server builds it in prompt 14; until the OpenAPI file is regenerated, the types live here, written from the contract (nullable
// exactly as written). Where §23 leaves a shape open, the reading here is marked "assumed" and listed for §23.12.

import { keepPreviousData, useInfiniteQuery, useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { bodyTarget, stepUp } from '@/lib/auth';
import { ApiError, isMock, type Problem } from './client';
import { call, type Actor } from './v13';
import { qs } from './v15';

type Page<T> = { items: T[]; next_cursor: string | null };
const items = <T>(x: T[] | Page<T>): T[] => (Array.isArray(x) ? x : x.items);
const enc = encodeURIComponent;
const ifVersion = (v: number | null | undefined): Record<string, string> => (v ? { 'If-Match': `"${v}"` } : { 'If-None-Match': '*' });

// ------------------------------------------------------------------ the closed vocabulary (§23.2, §23.7, §23.8) --
/** Field types, v1. Adding one is a prompt; using them is not. */
export const FIELD_TYPES = ['text', 'long_text', 'number', 'money', 'percent', 'date', 'date_range', 'enum', 'multi_enum', 'boolean', 'party', 'company', 'ref', 'url', 'email', 'phone', 'id_code', 'iban'] as const;
export type FieldType = (typeof FIELD_TYPES)[number];
export const REF_KINDS = ['decision', 'resolution', 'case', 'work', 'record', 'employee', 'revenue_account'] as const;
export type RefKind = (typeof REF_KINDS)[number];
export const EVENTS = ['filed', 'sealed', 'reminder_due', 'retention_due', 'hold_set', 'version_added'] as const;
export type AutomationEvent = (typeof EVENTS)[number];
export const ACTIONS = ['notify', 'work_item', 'link', 'move_to_folder', 'raise_level', 'add_reminder'] as const;
export type AutomationAction = (typeof ACTIONS)[number];
export const OPS = ['eq', 'lt', 'gt', 'contains'] as const;
export const SOURCE_KEYS = ['charter_sealed', 'resolution_month', 'brand_sealed', 'founding_registration', 'legal_email', 'case_closed', 'server_plan_sealed', 'backup_restore_test'] as const;
/** The schema parts PUT /archive/schema/{part}/{key} takes. */
export const PARTS = ['classes', 'folders', 'levels', 'clearance', 'retention', 'reminders', 'party_kinds', 'link_kinds', 'automations'] as const;
export type SchemaPart = (typeof PARTS)[number];

// ------------------------------------------------------------------ the open layer (§23.2–§23.8) --
export type Option = { key: string; title_fa: string };
export type Field = {
  key: string; title_fa: string; type: FieldType; required: boolean; searchable: boolean; sensitive: boolean; // sensitive → masked below `confidential`
  options?: Option[]; ref_kinds?: RefKind[]; currency?: string; help_fa?: string | null; status: 'active' | 'retired';
};
export type RecordClass = {
  key: string; title_fa: string; parent: string | null; scopes: 'all' | string[]; icon: string; default_level: string; default_folder: string | null;
  fields: Field[]; required_files: number; allowed_mime: string[]; ocr: boolean; retention: string | null;
  reminder_fields: string[]; auto_link: Array<{ field: string; link_kind: string }>; version: number; status: 'active' | 'retired';
  records?: number; // assumed: records filed under it (any class version), for impact and the editors
};
export type FolderNode = { ref: string; scope: string; parent: string | null; title_fa: string; classes: string[]; default_level: string | null; order: number; status: 'active' | 'retired'; version?: number; records?: number };
export type PartyKind = { key: string; title_fa: string; identifier_fields: Field[]; version?: number; status?: 'active' | 'retired'; parties?: number };
export type Party = { ref: string; kind: string; name_fa: string; name_en: string | null; identifiers: Record<string, unknown>; scopes: string[]; status: 'active' | 'retired'; version?: number; records?: number };
export type LinkKind = { key: string; title_fa: string; inverse_fa: string; to_kinds: string[]; version?: number; status?: 'active' | 'retired'; records?: number };
export type Level = {
  key: string; title_fa: string; rank: number; color_index: number; watermark: boolean; encrypt: boolean; step_up_to_view: boolean; agents_max: boolean;
  version?: number; status?: 'active' | 'retired'; records?: number;
};
/** One subject's grants. Assumed: the matrix is saved one subject (row) at a time, key `role:<role>` or `employee:<code>`; `own` = the
 *  subject's own company; `metadata_level` = what metadata it may see of the records it files itself (the archivist). */
export type Clearance = { subject: { kind: 'role' | 'employee'; ref: string }; scope: string; level: string; metadata_level?: string | null; version?: number };
export type ClearanceIn = { subject: Clearance['subject']; grants: Array<{ scope: string; level: string }>; metadata_level: string | null };
export type Keep = { years?: number; months?: number } | 'permanent';
export type RetentionRule = { ref: string; title_fa: string; trigger: string; keep: Keep; then: 'review' | 'dispose_card'; version: number; status: 'active' | 'retired'; records?: number };
export type ReminderTo = 'owner' | { role: string } | { company_ceo: true };
export type ReminderRule = { ref: string; class: string; field: string; lead_days: number[]; to: ReminderTo; channel: 'cartable' | 'digest'; version: number; status: 'active' | 'retired' };
export type Condition = { class?: string; scope?: string; level_min?: string; field?: { key: string; op: (typeof OPS)[number]; value: string | number | boolean } };
/** Assumed args per action: notify {to, level, text_fa} · work_item {role, title_fa} · link {kind, to: {kind, ref}} · move_to_folder {folder} ·
 *  raise_level {level} · add_reminder {field, lead_days}. */
export type Step = { action: AutomationAction; args: Record<string, unknown> };
export type Automation = {
  ref: string; title_fa: string; on: AutomationEvent; when: Condition; do: Step[]; version: number; status: 'active' | 'retired';
  runs_30d?: number; last_run_at?: string | null; // assumed
};
/** Assumed shape of one switch of GET /archive/sources. */
export type SourceSwitch = { key: string; title_fa: string; class: string; enabled: boolean; filed: number; last_at: string | null; note_fa: string | null };
export type FieldTypeDef = { key: FieldType; title_fa: string };
export type ArchiveSchema = {
  classes: RecordClass[]; field_types: FieldTypeDef[]; folders: FolderNode[]; levels: Level[]; clearance: Clearance[];
  retention: RetentionRule[]; reminders: ReminderRule[]; party_kinds: PartyKind[]; parties?: Party[]; link_kinds: LinkKind[];
  automations: Automation[]; sources: SourceSwitch[];
  // assumed: the rest of the closed vocabulary travels with the schema so no editor hard-codes it
  vocab?: { events: AutomationEvent[]; actions: AutomationAction[]; ops: string[]; ref_kinds: RefKind[]; currencies: string[]; mimes: string[] };
};
export type Impact = { records: number; missing_required: number };
/** Assumed answer of a schema PUT or retire; `?dry_run=1` answers the same without applying (no step-up), for the impact shown first. */
export type SchemaResult<T = unknown> = { part: SchemaPart; key: string; version: number; impact: Impact; row: T | null; dry_run?: boolean };

// ------------------------------------------------------------------ records (§23.1) --
export type RecordState = 'draft' | 'filed' | 'sealed' | 'superseded' | 'disposed';
export type TextState = 'none' | 'text_layer' | 'ocr' | 'failed';
export type RecordFile = { file_id: string; name: string; mime: string; size_bytes: number; sha256: string; pages: number | null; text_state: TextState; ocr_confidence: number | null };
export type RecordVersion = {
  n: number; files: RecordFile[]; manifest_sha256: string; note_fa: string | null; created_by: Actor; created_at: string; sealed: boolean;
  state?: 'current' | 'superseded'; // assumed: «the old one becomes superseded»
};
export type LinkTarget = { kind: string; ref: string };
/** Assumed extras: when and by whom, whether it was sealed with a version (then it stays), the far side's title when visible, and
 *  `inverse` for a link another record holds to this one (shown with the kind's `inverse_fa`). */
export type RecordLink = { kind: string; to: LinkTarget; at?: string; by?: Actor; sealed?: boolean; title_fa?: string | null; inverse?: boolean };
export type ReminderState = 'pending' | 'sent' | 'done';
export type ArchiveRecord = {
  id: string; ref: string; scope: string; class: string | null; class_version: number | null; title_fa: string;
  folder: string | null; level: string; state: RecordState; metadata: Record<string, unknown>;
  parties: Array<{ party: string; role_fa: string }>; links: RecordLink[]; holds: string[];
  retention: { rule: string | null; trigger_at: string | null; review_at: string | null; disposable: boolean };
  reminders: Array<{ field: string; at: string; lead_days: number; state: ReminderState }>;
  current_version: number; versions: RecordVersion[]; source: { kind: 'owner' | 'agent' | 'system'; ref: string | null };
  created_by: Actor; created_at: string; filed_at: string | null; sealed_at: string | null; version: number;
  // assumed: the document's own date (the class's first date field, else when filed) that `from`/`to` filter on; field keys masked for
  // this reader; a draft's suggestion (rules, or the archivist while the kill switch is released), never filed by itself
  doc_date?: string | null; masked?: string[];
  suggestion?: { class: string | null; title_fa: string | null; metadata: Record<string, unknown>; parties: string[]; by: 'rules' | 'archivist'; note_fa: string | null } | null;
  /** §23.12: after disposal. Assumed `hashes`: one {name, sha256} per destroyed file. */
  tombstone?: { decision: string; at: string; hashes: Array<{ name: string; sha256: string }> } | null;
};
/** Metadata values by field type (assumed): money {amount: decimal string, currency}; date "YYYY-MM-DD"; date_range {from, to}; enum key;
 *  multi_enum [key]; party "PT-…"; company code; ref {kind, ref}; the rest strings, numbers or booleans. */
export type Money = { amount: string; currency: string };
export type RecordIn = {
  scope: string; class: string; title_fa: string; metadata: Record<string, unknown>; level?: string; folder?: string | null; file_ids: string[];
  parties?: Array<{ party: string; role_fa: string }>; links?: Array<{ kind: string; to: LinkTarget }>; file: boolean;
};
/** Assumed: a draft also takes `class` (an imported draft has none until someone classifies it); a filed record's class never changes. */
export type RecordPatch = Partial<Pick<ArchiveRecord, 'title_fa' | 'metadata' | 'folder' | 'parties' | 'level' | 'class'>>;
export type RecordFilters = {
  scope?: string | null; class?: string | null; folder?: string | null; level?: string | null; state?: RecordState | null; party?: string | null;
  q?: string | null; from?: string | null; to?: string | null; expiring_within_days?: number | null; held?: boolean | null;
};
export type SearchHit = { ref: string; title_fa: string; class: string | null; snippet_fa: string; score: number };
/** Assumed row of GET …/access (owner only). A level change (§23.1: raise, or declassify with step-up, sealed records too) is a row
 *  with action `level` and the two level keys. */
export type AccessRow = {
  at: string; actor: Actor; action: 'view' | 'download' | 'metadata' | 'level'; file_id: string | null; version: number | null; step_up: boolean; watermarked: boolean;
  level_from?: string | null; level_to?: string | null;
};
/** Assumed answer of POST /archive/intake: the secret scan, hashes and text of files just uploaded (§17.1), and the rule-based suggestion. */
export type Intake = { files: RecordFile[]; suggestion: ArchiveRecord['suggestion'] };

// ------------------------------------------------------------------ holds, reminders, retention, fixity (§23.5, §23.6, §23.10) --
export type HoldScope = { records?: string[]; folders?: string[]; classes?: string[]; parties?: string[]; from?: string | null; to?: string | null };
export type LegalHold = {
  ref: string; title_fa: string; case: string | null; reason_md: string; scope: HoldScope; state: 'active' | 'released';
  placed_by: Actor; placed_at: string; released_at: string | null;
  records?: number; record_refs?: string[]; // assumed: what it covers now, within the reader's clearance
};
export type HoldIn = { title_fa: string; case: string | null; reason_md: string; scope: HoldScope };
/** Assumed item of GET /archive/reminders. */
export type DueReminder = {
  id: string; record: string; title_fa: string; scope: string; class: string; field: string; at: string; lead_days: number; days_left: number;
  state: ReminderState; rule: string | null; to: ReminderTo; channel: 'cartable' | 'digest';
};
/** Assumed item of GET /archive/retention/due. */
export type RetentionDue = {
  ref: string; title_fa: string; scope: string; class: string | null; rule: string; trigger_at: string | null; due_at: string;
  then: 'review' | 'dispose_card'; holds: string[]; decision_ref: string | null;
};
export type Fixity = { at: string; checked: number; failed: string[]; next_at?: string | null };

// ------------------------------------------------------------------ hooks: schema --
export const useArchiveSchema = () =>
  useQuery({ queryKey: ['archive', 'schema'], queryFn: () => call<ArchiveSchema>('GET', '/archive/schema'), staleTime: 30_000 });

/** The step-up action of a part: clearance has its own (§23.4), every other part `archive.schema`; both on the body hash. */
const schemaAction = (part: SchemaPart) => (part === 'clearance' ? 'archive.clearance' : 'archive.schema');

export function useSchemaAction() {
  const qc = useQueryClient();
  const done = () => Promise.all(['archive', 'decisions'].map((k) => qc.invalidateQueries({ queryKey: [k] })));
  return {
    /** The server's impact (and its validation, `422 schema_invalid`) before the passkey: nothing applied. */
    preview: useMutation({ mutationFn: (v: { part: SchemaPart; key: string; body: unknown; version: number | null }) => call<SchemaResult>('PUT', `/archive/schema/${v.part}/${enc(v.key)}?dry_run=1`, v.body, ifVersion(v.version)) }),
    /** 🔏 `archive.schema` (or `archive.clearance`) on the SHA-256 of the exact body; `If-Match` on the row, `If-None-Match: *` for a new key. */
    save: useMutation({
      mutationFn: async (v: { part: SchemaPart; key: string; body: unknown; version: number | null }) => {
        const text = JSON.stringify(v.body);
        return call<SchemaResult>('PUT', `/archive/schema/${v.part}/${enc(v.key)}`, v.body, { ...ifVersion(v.version), 'X-Step-Up': await stepUp(schemaAction(v.part), await bodyTarget(text)) });
      },
      onSuccess: done,
    }),
    retirePreview: useMutation({ mutationFn: (v: { part: SchemaPart; key: string; version: number }) => call<SchemaResult>('POST', `/archive/schema/${v.part}/${enc(v.key)}/retire?dry_run=1`, { part: v.part, key: v.key, version: v.version }) }),
    /** Nothing that uses it is deleted; the same target as a save, on the body {part, key, version} (assumed). */
    retire: useMutation({
      mutationFn: async (v: { part: SchemaPart; key: string; version: number }) => {
        const body = { part: v.part, key: v.key, version: v.version };
        return call<SchemaResult>('POST', `/archive/schema/${v.part}/${enc(v.key)}/retire`, body, { 'X-Step-Up': await stepUp(schemaAction(v.part), await bodyTarget(JSON.stringify(body))) });
      },
      onSuccess: done,
    }),
  };
}

export const useSources = () => useQuery({ queryKey: ['archive', 'sources'], queryFn: async () => items(await call<SourceSwitch[] | Page<SourceSwitch>>('GET', '/archive/sources')) });
export function useSourceSwitch() {
  const qc = useQueryClient();
  // Assumed body: the switches that change, {key: on}; answers every source.
  return useMutation({ mutationFn: (v: Record<string, boolean>) => call<SourceSwitch[]>('PUT', '/archive/sources', v), onSuccess: () => qc.invalidateQueries({ queryKey: ['archive'] }) });
}

// ------------------------------------------------------------------ hooks: records --
export const useRecords = (f: RecordFilters = {}) =>
  useInfiniteQuery({
    queryKey: ['archive', 'records', f],
    queryFn: ({ pageParam }) => call<Page<ArchiveRecord>>('GET', `/archive/records${qs({ ...f, expiring_within_days: f.expiring_within_days ?? undefined, held: f.held ?? undefined, limit: 50, cursor: pageParam })}`),
    initialPageParam: null as string | null, getNextPageParam: (l) => l.next_cursor, placeholderData: keepPreviousData,
  });
export const useArchiveSearch = (q: string, f: { scope?: string | null; class?: string | null; level?: string | null; from?: string | null; to?: string | null } = {}) =>
  useQuery({
    queryKey: ['archive', 'search', q, f],
    queryFn: async () => (await call<Page<SearchHit>>('GET', `/archive/search${qs({ q, ...f })}`)).items,
    enabled: q.trim().length >= 2, placeholderData: keepPreviousData,
  });
export const useRecord = (ref: string | null) =>
  useQuery({ queryKey: ['archive', 'record', ref], queryFn: () => call<ArchiveRecord>('GET', `/archive/records/${enc(ref!)}`), enabled: !!ref });
/** Several records at once (a disposal card's list); a record above the reader's clearance or disposed comes back as an error. */
export const useRecordsByRef = (refs: string[]) =>
  useQueries({ queries: refs.map((ref) => ({ queryKey: ['archive', 'record', ref], queryFn: () => call<ArchiveRecord>('GET', `/archive/records/${enc(ref)}`), retry: false })) });
export const useAccessLog = (ref: string | null) =>
  useQuery({ queryKey: ['archive', 'access', ref], queryFn: async () => items(await call<AccessRow[] | Page<AccessRow>>('GET', `/archive/records/${enc(ref!)}/access`)), enabled: !!ref });

export function useRecordAction() {
  const qc = useQueryClient();
  const done = () => Promise.all(['archive', 'decisions', 'legal'].map((k) => qc.invalidateQueries({ queryKey: [k] })));
  return {
    /** The owner may file at once (`file: true`); otherwise a draft. `Idempotency-Key` is required. */
    create: useMutation({ mutationFn: (v: { body: RecordIn; key: string }) => call<ArchiveRecord>('POST', '/archive/records', v.body, { 'Idempotency-Key': v.key }), onSuccess: done }),
    /** `If-Match`; a sealed record answers 409 sealed_record, a held one 423 held. The level only goes up here. */
    patch: useMutation({ mutationFn: (v: { r: ArchiveRecord; body: RecordPatch }) => call<ArchiveRecord>('PATCH', `/archive/records/${enc(v.r.ref)}`, v.body, { 'If-Match': `"${v.r.version}"` }), onSuccess: done }),
    /** Lowering the level is the owner's alone: 🔏 `archive.declassify`, target `ref@version:level`, on the same PATCH with `level` as its
     *  only field. A sealed record takes it too (§23.1: the level is outside the sealed manifest). */
    declassify: useMutation({
      mutationFn: async (v: { r: ArchiveRecord; level: string }) =>
        call<ArchiveRecord>('PATCH', `/archive/records/${enc(v.r.ref)}`, { level: v.level }, { 'If-Match': `"${v.r.version}"`, 'X-Step-Up': await stepUp('archive.declassify', `${v.r.ref}@${v.r.version}:${v.level}`) }),
      onSuccess: done,
    }),
    /** Assumed `POST …/file`: a completed draft becomes `filed` (owner). */
    file: useMutation({ mutationFn: (r: ArchiveRecord) => call<ArchiveRecord>('POST', `/archive/records/${enc(r.ref)}/file`, {}, { 'If-Match': `"${r.version}"` }), onSuccess: done }),
    /** A correction is a new version; on a sealed record the old one is superseded and the record goes back to `filed`. */
    version: useMutation({ mutationFn: (v: { ref: string; file_ids: string[]; note_fa: string }) => call<ArchiveRecord>('POST', `/archive/records/${enc(v.ref)}/versions`, { file_ids: v.file_ids, note_fa: v.note_fa }), onSuccess: done }),
    /** 🔏 `archive.seal` on the current version's manifest; the body names it so a changed manifest is refused (assumed). */
    seal: useMutation({
      mutationFn: async (r: ArchiveRecord) => {
        const manifest = r.versions.find((x) => x.n === r.current_version)?.manifest_sha256 ?? '';
        return call<ArchiveRecord>('POST', `/archive/records/${enc(r.ref)}/seal`, { manifest_sha256: manifest }, { 'X-Step-Up': await stepUp('archive.seal', manifest) });
      },
      onSuccess: done,
    }),
    link: useMutation({ mutationFn: (v: { ref: string; kind: string; to: LinkTarget }) => call<ArchiveRecord>('POST', `/archive/records/${enc(v.ref)}/links`, { kind: v.kind, to: v.to }), onSuccess: done }),
    /** Assumed: the link to remove travels in the query (`kind`, `to_kind`, `to_ref`). */
    unlink: useMutation({ mutationFn: (v: { ref: string; kind: string; to: LinkTarget }) => call<ArchiveRecord>('DELETE', `/archive/records/${enc(v.ref)}/links${qs({ kind: v.kind, to_kind: v.to.kind, to_ref: v.to.ref })}`), onSuccess: done }),
    /** Owner: one draft per file for the archivist to classify. */
    import: useMutation({ mutationFn: (v: { scope: string; file_ids: string[]; class?: string | null }) => call<Page<ArchiveRecord> | ArchiveRecord[]>('POST', '/archive/import', { scope: v.scope, file_ids: v.file_ids, class: v.class ?? undefined }), onSuccess: done }),
  };
}
/** The secret scan first (`422 secret_in_document`: the file is not stored), then hashes, text and the rule-based suggestion. */
export const useIntake = () => useMutation({ mutationFn: (file_ids: string[]) => call<Intake>('POST', '/archive/intake', { file_ids }) });

// Same path as the typed client, so next.config's alias swaps the fixtures out of production builds.
const mockHandle = isMock ? async (r: Request) => (await import('@/lib/api/mock')).handle(r) : undefined;
/** GET one file of a record as an object URL: `X-Step-Up` for levels with `step_up_to_view` (🔏 `archive.view`, target = ref). Every call
 *  is an access-log row; watermarked levels come back watermarked (viewer, time, ref). */
export async function fetchRecordFile(ref: string, fileId: string, token?: string): Promise<string> {
  const h = new Headers({ Accept: '*/*' });
  if (token) h.set('X-Step-Up', token);
  const req = new Request(new URL(`/api/v1/archive/records/${enc(ref)}/files/${enc(fileId)}`, window.location.origin), { headers: h, credentials: 'same-origin' });
  let res: Response;
  try { res = mockHandle ? await mockHandle(req) : await fetch(req); } catch { throw new ApiError(0, undefined); }
  if (!res.ok) {
    let p: Partial<Problem> | undefined;
    try { p = (await res.json()) as Partial<Problem>; } catch { /* not JSON */ }
    throw new ApiError(res.status, p);
  }
  return URL.createObjectURL(await res.blob());
}
/** The file as an object URL. A level with `step_up_to_view` waits for `open()`: one passkey (single use), then one call. The key lives
 *  outside ['archive'] so a refresh of the archive never re-reads the file (each read is an access-log row). */
export function useRecordFile(ref: string, file: RecordFile | null, needsStepUp: boolean) {
  const qc = useQueryClient();
  const [token, setToken] = useState<{ for: string; t: string } | null>(null);
  const [asking, setAsking] = useState<unknown>(null);
  const fid = file?.file_id ?? '';
  const t = token?.for === `${ref}/${fid}` ? token.t : null;
  const q = useQuery({
    queryKey: ['archive-file', ref, fid, t],
    queryFn: async () => {
      const url = await fetchRecordFile(ref, fid, t ?? undefined);
      void qc.invalidateQueries({ queryKey: ['archive', 'access', ref] });
      return url;
    },
    enabled: !!file && (!needsStepUp || !!t), retry: false, staleTime: Infinity, gcTime: 60_000, refetchOnWindowFocus: false,
  });
  return {
    url: q.data ?? null, error: q.error ?? asking, busy: q.isFetching,
    /** 🔏 `archive.view` on the ref, then the call. */
    open: async () => {
      setAsking(null);
      try { setToken({ for: `${ref}/${fid}`, t: await stepUp('archive.view', ref) }); } catch (e) { setAsking(e); }
    },
  };
}

// ------------------------------------------------------------------ hooks: parties, holds, reminders, retention, fixity --
export const useParties = (f: { kind?: string | null; scope?: string | null; q?: string | null } = {}) =>
  useQuery({ queryKey: ['archive', 'parties', f], queryFn: async () => items(await call<Party[] | Page<Party>>('GET', `/archive/parties${qs({ kind: f.kind, scope: f.scope, q: f.q })}`)), placeholderData: keepPreviousData });
export type PartyIn = Pick<Party, 'kind' | 'name_fa' | 'name_en' | 'identifiers' | 'scopes'>;
export function usePartyAction() {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: ['archive'] });
  return {
    create: useMutation({ mutationFn: (v: { body: PartyIn; key: string }) => call<Party>('POST', '/archive/parties', v.body, { 'Idempotency-Key': v.key }), onSuccess: done }),
    patch: useMutation({ mutationFn: (v: { p: Party; body: Partial<PartyIn> & { status?: Party['status'] } }) => call<Party>('PATCH', `/archive/parties/${enc(v.p.ref)}`, v.body, { 'If-Match': `"${v.p.version ?? 1}"` }), onSuccess: done }),
  };
}

export const useHolds = (f: { state?: 'active' | 'released' | null; case?: string | null } = {}) =>
  useQuery({ queryKey: ['archive', 'holds', f], queryFn: async () => items(await call<LegalHold[] | Page<LegalHold>>('GET', `/archive/holds${qs({ state: f.state, case: f.case })}`)) });
export function useHoldAction() {
  const qc = useQueryClient();
  const done = () => Promise.all(['archive', 'legal', 'decisions'].map((k) => qc.invalidateQueries({ queryKey: [k] })));
  return {
    place: useMutation({ mutationFn: (v: { body: HoldIn; key: string }) => call<LegalHold>('POST', '/archive/holds', v.body, { 'Idempotency-Key': v.key }), onSuccess: done }),
    /** The owner's alone: 🔏 `archive.hold.release`, target = ref. */
    release: useMutation({ mutationFn: async (ref: string) => call<LegalHold>('POST', `/archive/holds/${enc(ref)}/release`, {}, { 'X-Step-Up': await stepUp('archive.hold.release', ref) }), onSuccess: done }),
  };
}

export const useDueReminders = () =>
  useQuery({ queryKey: ['archive', 'reminders'], queryFn: async () => items(await call<DueReminder[] | Page<DueReminder>>('GET', '/archive/reminders')), refetchInterval: 300_000 });
/** Assumed `POST /archive/reminders/{id}/done`: the underlying action is done (renewed, reviewed), the reminder closes. */
export function useReminderDone() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (id: string) => call<DueReminder>('POST', `/archive/reminders/${enc(id)}/done`, {}), onSuccess: () => Promise.all(['archive', 'decisions'].map((k) => qc.invalidateQueries({ queryKey: [k] }))) });
}
export const useRetentionDue = () =>
  useQuery({ queryKey: ['archive', 'retention'], queryFn: async () => items(await call<RetentionDue[] | Page<RetentionDue>>('GET', '/archive/retention/due')) });
export const useFixity = () => useQuery({ queryKey: ['archive', 'fixity'], queryFn: () => call<Fixity>('GET', '/archive/fixity'), refetchInterval: 600_000 });

// ------------------------------------------------------------------ kinds and codes (§23.11, §14) --
export const ARCHIVE_KINDS = ['archive_schema', 'archive_disposal'] as const;
/** Assumed payload of `archive_schema`: the exact PUT, with the row version it was written against and the impact the server measured. */
export type SchemaCardPayload = { part: SchemaPart; key: string; base_version: number | null; body: Record<string, unknown>; impact?: Impact | null };
export type DisposalCardPayload = { records: Array<{ ref: string; class: string | null; title_fa: string; retention_rule: string; trigger_at: string | null }> };

const CODE_FA: Record<string, string> = {
  clearance: 'این سند بالاتر از مجوز دیدن است.',
  sealed_record: 'این سند مُهر خورده و دیگر عوض نمیشود؛ اصلاح یعنی نسخه‌ی تازه.',
  schema_invalid: 'این تغییر با واژگان بسته‌ی بایگانی نمیخواند؛ چیزی ذخیره نشد.',
  secret_in_document: 'در این فایل الگوی رمز، کلید خصوصی یا عبارت بازیابی پیدا شد؛ فایل ذخیره نشد و هیچ بخشی از آن ثبت نشد.',
  held: 'این سند توقیف قانونی دارد؛ جز نسخه‌ی تازه هیچ تغییری نمیپذیرد.',
  version_conflict: 'همین حالا عوض شده؛ دوباره نگاه کن و بعد ذخیره کن.',
  precondition_required: 'نسخه همراه درخواست نیامد؛ صفحه را تازه کن.',
  step_up_required: 'این کار تأیید با اثر انگشت یا چهره میخواهد.',
  decision_not_pending: 'این کارت دیگر منتظر تصمیم نیست.',
  not_found: 'پیدا نشد.',
  not_ready: 'این کار روی این نسخه‌ی سرور هنوز آماده نیست.',
};
/** The Persian sentence for a failed §23 call; the server's own sentence for everything else (with the fields that failed). */
export function faError(e: unknown): string {
  if (!(e instanceof ApiError)) return e instanceof Error ? e.message : 'انجام نشد.';
  const base = CODE_FA[e.code] ?? e.messageFa;
  // A refused schema change or record names what failed; the server's sentence says which field and why.
  if ((e.code === 'schema_invalid' || e.code === 'validation_failed') && e.messageFa) return e.messageFa;
  return base;
}
