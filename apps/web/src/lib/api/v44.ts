/**
 * ⟨0.19.8⟩ §44.5 «تأیید و انتشار»: the owner's tap on a file of a session's output publishes it (Instagram, through IG-Hub's own
 * runner). No card and no passkey: his word in the session is the seal for what goes out and can be taken back.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { call } from './v13';
import { served } from './v33';
import { OWNER_TZ } from '@/lib/format';

export type PublishKind = 'reel' | 'post' | 'story' | 'carousel';
export type PublishState = 'publishing' | 'scheduled' | 'published' | 'failed' | 'waiting_seal' | 'waiting_setup';
/** One publish of a session: the job on IG-Hub's server and where it stands (`waiting_setup`: no job yet). */
export type SessionPublish = {
  job: string | null; output: string | null; file_id: string; file_name: string | null; cover_name?: string | null; channel: 'instagram'; kind: PublishKind;
  account: string | null; state: PublishState; url: string | null; note_fa: string | null; at: string | null; published_at: string | null;
  /** ⟨0.19.9⟩ §45 the hub sent it on the owner's standing word (no tap). */
  auto?: boolean;
  /** ⟨0.20.0⟩ §46 the time it is set for (`scheduled` till then); the word viewers comment for its link; a carousel's files. */
  scheduled_at?: string | null; comment?: string | null; files?: string[];
};
/**
 * ⟨0.20.0⟩ §46 A comment rule for one post (the owner: «هر بار شاید یک کامنت باشد»): who comments one of `keywords` on it gets
 * `reply` in private, with `link` as its button. IG-Hub keeps the rule for that post alone.
 */
export type PublishComment = { keywords: string[]; reply: string; link?: string | null };
/**
 * What an output's page shows: its session, the company's accounts, its publishes (newest first). ⟨0.19.9⟩ §45 `tap`: it can be
 * published by a tap (`order` is null for a working group's daily output; a hub before §45 leaves `tap` out and only a session's
 * output has the button); `caption`: the caption its package carries; `group_fa`, `mode`: the working group whose routine made it
 * and the owner's standing word (`auto`: it goes out by itself).
 */
export type PublishPanel = {
  order: string | null; channel: 'instagram'; accounts: string[]; ready: boolean; publishes: SessionPublish[];
  tap?: boolean; caption?: string | null; group?: string | null; group_fa?: string | null; mode?: 'ask' | 'auto' | null;
  /** ⟨0.20.0⟩ §46 the comment rule its package carries (`comment.txt`): the sheet opens with it. */
  comment?: PublishComment | null;
};
/** ⟨0.19.9⟩ §45 the owner's standing word for one company in one working group. */
export type MemberPublish = { mode: 'ask' | 'auto'; account?: string | null; story?: boolean; since?: string | null; /** ⟨0.20.0⟩ §46 «HH:MM», his zone */ at?: string | null };
/** «HH:MM» as the hub takes it, from what he typed (Persian or Latin digits; «9:5» is not one); null when it is no hour. */
export const clockOf = (raw: string | null | undefined): string | null => {
  const t = (raw ?? '').trim().replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 0x06f0)).replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 0x0660));
  const m = /^([01]?\d|2[0-3]):([0-5]\d)$/.exec(t);
  return m ? `${m[1]!.padStart(2, '0')}:${m[2]}` : null;
};
/** The word as the hub takes it: the account only when he named one, `story` and the hour only on `auto`. */
export const publishRule = (p: MemberPublish) => (p.mode === 'auto'
  ? { mode: 'auto' as const, ...(p.account ? { account: p.account.replace(/^@/, '') } : {}), ...(p.story ? { story: true } : {}), ...(clockOf(p.at) ? { at: clockOf(p.at)! } : {}) }
  : { mode: 'ask' as const });
/** The accounts a refusal names («one of: @a, @b»): the company has several and he picks one. */
export const accountsNamed = (field: string | null | undefined) => [...new Set([...(field ?? '').matchAll(/@([A-Za-z0-9._]+)/g)].map((m) => m[1]!.replace(/\.+$/, '')))];
/** A member's standing word in one line. */
export const standingFa = (p: MemberPublish | null | undefined) => (p?.mode === 'auto'
  ? ['خودکار', clockOf(p.at) ? `ساعت ${clockOf(p.at)}` : null, p.account ? `\u2066@${p.account}\u2069` : null, p.story ? 'استوری هم' : null].filter(Boolean).join(' · ')
  : 'هر بار بپرس');

export const KIND_FA: Record<PublishKind, string> = { reel: 'ریلز', post: 'پست', story: 'استوری', carousel: 'اسلاید' };
/** A video goes out as a reel or a story, an image as a post or a story; ⟨0.20.0⟩ §46 with `others` in the same output, also a carousel of them all. */
export const kindsOf = (mime: string, others = 0): PublishKind[] => [...(mime.startsWith('video/') ? ['reel', 'story'] as const : ['post', 'story'] as const), ...(others > 0 ? ['carousel'] as const : [])];
/** A carousel takes ten files at most: this one and nine others. */
export const CAROUSEL_OTHERS = 9;
/**
 * ⟨0.20.0⟩ §46 The time he set, as the hub takes it (with the owner's zone): today (`day` 0) or tomorrow (1) at `clock` («18:30»,
 * Persian digits too). Null when `clock` is no hour.
 */
export const scheduledIso = (day: 0 | 1, clock: string, now: Date = new Date()): string | null => {
  const hm = clockOf(clock);
  if (!hm) return null;
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', {
    timeZone: OWNER_TZ, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  }).formatToParts(now).map((x) => [x.type, x.value]));
  // the zone's offset at this moment: its wall clock read as UTC, less the moment itself
  const wall = Date.UTC(+parts.year!, +parts.month! - 1, +parts.day!, +parts.hour!, +parts.minute!, +parts.second!);
  const off = Math.round((wall - Math.floor(now.getTime() / 1000) * 1000) / 60_000);
  const date = new Date(Date.UTC(+parts.year!, +parts.month! - 1, +parts.day! + day));
  const sign = off < 0 ? '-' : '+';
  const two = (n: number) => String(n).padStart(2, '0');
  return `${date.getUTCFullYear()}-${two(date.getUTCMonth() + 1)}-${two(date.getUTCDate())}T${hm}:00${sign}${two(Math.floor(Math.abs(off) / 60))}:${two(Math.abs(off) % 60)}`;
};
/** The comment rule from the three fields: null when a word or its reply is missing (`commentHalf` says he began one). */
export const commentOf = (word: string, reply: string, link: string): PublishComment | null => {
  const words = word.split(/[,،]/).map((w) => w.trim()).filter(Boolean);
  if (!words.length || !reply.trim()) return null;
  return { keywords: words.slice(0, 10), reply: reply.trim(), ...(link.trim().startsWith('https://') ? { link: link.trim() } : {}) };
};
/** He began a comment rule and left it half: a word without its reply, a reply or a link without the word. */
export const commentHalf = (word: string, reply: string, link: string) => !!(word.trim() || reply.trim() || link.trim()) && commentOf(word, reply, link) === null;
export const publishable = (mime: string) => mime.startsWith('video/') || mime.startsWith('image/');
/** Where one file stands (newest first): its reel or its post when there is one, else its story. */
export const publishOf = (p: PublishPanel, fileId: string) =>
  p.publishes.find((x) => x.file_id === fileId && x.kind !== 'story') ?? p.publishes.find((x) => x.file_id === fileId) ?? null;
/** The story of a file that also went out as a reel or a post (the standing word's «استوری هم»); null when the story is the row itself. */
export const storyOf = (p: PublishPanel, fileId: string) => {
  const s = p.publishes.find((x) => x.file_id === fileId && x.kind === 'story') ?? null;
  return s && publishOf(p, fileId)?.kind !== 'story' ? s : null;
};
export const STATE_FA: Record<string, string> = { publishing: 'در حال انتشار', scheduled: 'زمان‌بندی شد', published: 'منتشر شد', failed: 'انجام نشد', waiting_seal: 'منتظر مُهر' };
/** The image chosen as a reel's cover before he touches anything: the one named `cover…`, else the only one. */
export const coverOf = <T extends { name: string }>(images: ReadonlyArray<T>): T | null =>
  images.find((x) => x.name.toLowerCase().startsWith('cover')) ?? (images.length === 1 ? images[0]! : null);

/** `GET /deliverables/{ref}/publish`; null on a hub before §44.5. Refreshed while a publish is on its way. */
export const usePublishPanel = (ref: string | null, enabled = true) => useQuery({
  queryKey: ['publish', ref], enabled: !!ref && enabled, staleTime: 5_000,
  queryFn: () => served(call<PublishPanel>('GET', `/deliverables/${encodeURIComponent(ref!)}/publish`)),
  // on its way: every 5s; ⟨0.20.0⟩ §46 set for an hour: once a minute, so the row turns when it goes out
  refetchInterval: (q) => (q.state.data?.publishes.some((p) => p.state === 'publishing') ? 5_000 : q.state.data?.publishes.some((p) => p.state === 'scheduled') ? 60_000 : false),
});

/** `POST /deliverables/{ref}/publish`: the tap. `key` is kept across retries of one press. */
export function usePublish(ref: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: {
      file_id: string; kind: PublishKind; caption?: string; account?: string | null; cover_file_id?: string | null; key: string;
      file_ids?: string[]; scheduled_at?: string | null; comment?: PublishComment | null;
    }) =>
      call<SessionPublish>('POST', `/deliverables/${encodeURIComponent(ref)}/publish`, {
        file_id: v.file_id, kind: v.kind, ...(v.caption?.trim() ? { caption: v.caption.trim() } : {}), ...(v.account ? { account: v.account } : {}),
        // a reel's cover: an image of the same output
        ...(v.cover_file_id && v.kind === 'reel' ? { cover_file_id: v.cover_file_id } : {}),
        // ⟨0.20.0⟩ §46 a carousel's other files, the time, the comment rule of this post
        ...(v.kind === 'carousel' && v.file_ids?.length ? { file_ids: v.file_ids } : {}),
        ...(v.scheduled_at ? { scheduled_at: v.scheduled_at } : {}),
        ...(v.comment && v.kind !== 'story' ? { comment: v.comment } : {}),
      }, { 'Idempotency-Key': v.key }),
    onSuccess: () => { for (const k of ['publish', 'orders']) void qc.invalidateQueries({ queryKey: [k] }); },
  });
}

/**
 * ⟨0.19.9⟩ §45 `PUT /groups/{key}/members/{code}/publish`: the owner's standing permission to publish, for one company in one
 * working group. His tap, no passkey. A company with several accounts and none named is a 422 whose `account` field names them.
 */
export function useMemberPublish(group: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { company: string; publish: MemberPublish }) =>
      call<{ company: string; publish: MemberPublish }>('PUT', `/groups/${encodeURIComponent(group)}/members/${encodeURIComponent(v.company)}/publish`, publishRule(v.publish)),
    onSuccess: () => { for (const k of ['playbooks', 'groups', 'g29', 'publish']) void qc.invalidateQueries({ queryKey: [k] }); },
  });
}

