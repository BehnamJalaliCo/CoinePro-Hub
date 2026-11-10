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
};
/** What an output's page shows: its session (`order` null: no button), the company's accounts, its publishes (newest first). */
export type PublishPanel = { order: string | null; channel: 'instagram'; accounts: string[]; ready: boolean; publishes: SessionPublish[] };

export const KIND_FA: Record<PublishKind, string> = { reel: 'ریلز', post: 'پست', story: 'استوری' };
/** A video goes out as a reel or a story, an image as a post or a story. */
export const kindsOf = (mime: string): PublishKind[] => (mime.startsWith('video/') ? ['reel', 'story'] : ['post', 'story']);
export const publishable = (mime: string) => mime.startsWith('video/') || mime.startsWith('image/');
/** The newest publish of one file. */
export const publishOf = (p: PublishPanel, fileId: string) => p.publishes.find((x) => x.file_id === fileId) ?? null;

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
