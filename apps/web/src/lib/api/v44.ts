/**
 * ⟨0.19.8⟩ §44.5 «تأیید و انتشار»: the owner's tap on a file of a session's output publishes it (Instagram, through IG-Hub's own
 * runner). No card and no passkey: his word in the session is the seal for what goes out and can be taken back.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { call } from './v13';
import { served } from './v33';

export type PublishKind = 'reel' | 'post' | 'story';
export type PublishState = 'publishing' | 'published' | 'failed' | 'waiting_seal' | 'waiting_setup';
/** One publish of a session: the job on IG-Hub's server and where it stands (`waiting_setup`: no job yet). */
export type SessionPublish = {
  job: string | null; output: string | null; file_id: string; file_name: string | null; cover_name?: string | null; channel: 'instagram'; kind: PublishKind;
  account: string | null; state: PublishState; url: string | null; note_fa: string | null; at: string | null; published_at: string | null;
  /** ⟨0.19.9⟩ §45 the hub sent it on the owner's standing word (no tap). */
  auto?: boolean;
};
/**
 * What an output's page shows: its session, the company's accounts, its publishes (newest first). ⟨0.19.9⟩ §45 `tap`: it can be
 * published by a tap (`order` is null for a working group's daily output; a hub before §45 leaves `tap` out and only a session's
 * output has the button); `caption`: the caption its package carries; `group_fa`, `mode`: the working group whose routine made it
 * and the owner's standing word (`auto`: it goes out by itself).
 */
export type PublishPanel = {
  order: string | null; channel: 'instagram'; accounts: string[]; ready: boolean; publishes: SessionPublish[];
  tap?: boolean; caption?: string | null; group?: string | null; group_fa?: string | null; mode?: 'ask' | 'auto' | null;
};
/** ⟨0.19.9⟩ §45 the owner's standing word for one company in one working group. */
export type MemberPublish = { mode: 'ask' | 'auto'; account?: string | null; story?: boolean; since?: string | null };
/** The word as the hub takes it: the account only when he named one, `story` only on `auto`. */
export const publishRule = (p: MemberPublish) => (p.mode === 'auto'
  ? { mode: 'auto' as const, ...(p.account ? { account: p.account.replace(/^@/, '') } : {}), ...(p.story ? { story: true } : {}) }
  : { mode: 'ask' as const });
/** The accounts a refusal names («one of: @a, @b»): the company has several and he picks one. */
export const accountsNamed = (field: string | null | undefined) => [...new Set([...(field ?? '').matchAll(/@([A-Za-z0-9._]+)/g)].map((m) => m[1]!.replace(/\.+$/, '')))];
/** A member's standing word in one line. */
export const standingFa = (p: MemberPublish | null | undefined) => (p?.mode === 'auto'
  ? ['خودکار', p.account ? `\u2066@${p.account}\u2069` : null, p.story ? 'استوری هم' : null].filter(Boolean).join(' · ')
  : 'هر بار بپرس');

export const KIND_FA: Record<PublishKind, string> = { reel: 'ریلز', post: 'پست', story: 'استوری' };
/** A video goes out as a reel or a story, an image as a post or a story. */
export const kindsOf = (mime: string): PublishKind[] => (mime.startsWith('video/') ? ['reel', 'story'] : ['post', 'story']);
export const publishable = (mime: string) => mime.startsWith('video/') || mime.startsWith('image/');
/** Where one file stands (newest first): its reel or its post when there is one, else its story. */
export const publishOf = (p: PublishPanel, fileId: string) =>
  p.publishes.find((x) => x.file_id === fileId && x.kind !== 'story') ?? p.publishes.find((x) => x.file_id === fileId) ?? null;
/** The story of a file that also went out as a reel or a post (the standing word's «استوری هم»); null when the story is the row itself. */
export const storyOf = (p: PublishPanel, fileId: string) => {
  const s = p.publishes.find((x) => x.file_id === fileId && x.kind === 'story') ?? null;
  return s && publishOf(p, fileId)?.kind !== 'story' ? s : null;
};
export const STATE_FA: Record<string, string> = { publishing: 'در حال انتشار', published: 'منتشر شد', failed: 'انجام نشد', waiting_seal: 'منتظر مُهر' };
/** The image chosen as a reel's cover before he touches anything: the one named `cover…`, else the only one. */
export const coverOf = <T extends { name: string }>(images: ReadonlyArray<T>): T | null =>
  images.find((x) => x.name.toLowerCase().startsWith('cover')) ?? (images.length === 1 ? images[0]! : null);

/** `GET /deliverables/{ref}/publish`; null on a hub before §44.5. Refreshed while a publish is on its way. */
export const usePublishPanel = (ref: string | null, enabled = true) => useQuery({
  queryKey: ['publish', ref], enabled: !!ref && enabled, staleTime: 5_000,
  queryFn: () => served(call<PublishPanel>('GET', `/deliverables/${encodeURIComponent(ref!)}/publish`)),
  refetchInterval: (q) => (q.state.data?.publishes.some((p) => p.state === 'publishing') ? 5_000 : false),
});

/** `POST /deliverables/{ref}/publish`: the tap. `key` is kept across retries of one press. */
export function usePublish(ref: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { file_id: string; kind: PublishKind; caption?: string; account?: string | null; cover_file_id?: string | null; key: string }) =>
      call<SessionPublish>('POST', `/deliverables/${encodeURIComponent(ref)}/publish`, {
        file_id: v.file_id, kind: v.kind, ...(v.caption?.trim() ? { caption: v.caption.trim() } : {}), ...(v.account ? { account: v.account } : {}),
        // a reel's cover: an image of the same output
        ...(v.cover_file_id && v.kind === 'reel' ? { cover_file_id: v.cover_file_id } : {}),
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

