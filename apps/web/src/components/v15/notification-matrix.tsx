'use client';

import { useMemo, useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Card, ErrorState, FilterChip, SectionTitle, Skeleton, Switch } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { useCompanies } from '@/lib/api/hooks';
import { LEVELS, effective, useNotificationSettings, useSaveNotificationSettings, type Level, type LevelSettings, type NotificationSettings } from '@/lib/api/v15';
import { LEVEL } from '@/lib/labels';
import { cx, jDateTime } from '@/lib/format';
import { useNow } from '@/lib/store';

type Matrix = NotificationSettings['matrix'];

const MUTE: Array<{ id: string; fa: string; until: () => string | null }> = [
  { id: 'none', fa: 'بی‌صدا نیست', until: () => null },
  { id: '1h', fa: 'یک ساعت', until: () => new Date(Date.now() + 3_600_000).toISOString() },
  { id: '8h', fa: 'هشت ساعت', until: () => new Date(Date.now() + 8 * 3_600_000).toISOString() },
  { id: 'week', fa: 'یک هفته', until: () => new Date(Date.now() + 7 * 86_400_000).toISOString() },
];

/** The per-company, per-level matrix (§6): "*" is the default for every company, a company row overrides it. Urgent always arrives. */
export function NotificationMatrix() {
  const q = useNotificationSettings();
  const save = useSaveNotificationSettings();
  const { data: companies } = useCompanies();
  const toast = useToast();
  const [scope, setScope] = useState('*');
  // Edits live in `edits` until saved; without edits the server's matrix shows as is.
  const [edits, setEdits] = useState<Matrix | null>(null);
  const draft = edits ?? q.data?.matrix ?? null;
  const now = useNow();
  const dirty = useMemo(() => !!edits && !!q.data && JSON.stringify(edits) !== JSON.stringify(q.data.matrix), [edits, q.data]);
  const set = (level: Level, patch: Partial<LevelSettings>) => setEdits((m) => {
    const next = structuredClone(m ?? q.data?.matrix ?? {});
    next[scope] = { ...(next[scope] ?? {}), [level]: { ...(next[scope]?.[level] ?? {}), ...patch } };
    return next;
  });
  const reset = (level: Level) => setEdits((m) => {
    const next = structuredClone(m ?? q.data?.matrix ?? {});
    if (next[scope]) { delete next[scope]![level]; if (!Object.keys(next[scope]!).length) delete next[scope]; }
    return next;
  });
  const submit = async () => {
    if (!draft || !q.data) return;
    try {
      await save.mutateAsync({ matrix: draft, version: q.data.version });
      setEdits(null);
      toast({ tone: 'ok', text: 'تنظیمات اعلان ذخیره شد.' });
    } catch (e) {
      if (e instanceof ApiError && e.code === 'version_conflict') { setEdits(null); void q.refetch(); }
      toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'ذخیره نشد.' });
    }
  };
  const scopes = [{ code: '*', name: 'همه‌ی شرکت‌ها' }, ...(companies ?? []).map((c) => ({ code: c.code, name: c.name_fa }))];
  return (
    <Card className="flex flex-col gap-4 p-5">
      <SectionTitle title="اعلان‌ها برای هر شرکت" note="ردیف هر شرکت جای پیش‌فرض «همه» را میگیرد. فوری همیشه میرسد." />
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !draft ? <Skeleton className="h-64" /> : (
        <>
          <div className="flex flex-wrap gap-2">{scopes.map((s) => <FilterChip key={s.code} selected={scope === s.code} onClick={() => setScope(s.code)}>{s.name}</FilterChip>)}</div>
          <div className="flex flex-col">
            <div className="grid grid-cols-[minmax(0,1fr)_repeat(3,3.25rem)] items-center gap-2 px-1 pb-1 text-[11px] text-muted">
              <span>سطح</span><span className="text-center">در اپ</span><span className="text-center">push</span><span className="text-center">صدا</span>
            </div>
            {LEVELS.map((level) => {
              const e = effective(draft, scope, level);
              const own = scope !== '*' && !!draft[scope]?.[level];
              const urgent = level === 'urgent';
              const muted = e.muted_until && new Date(e.muted_until).getTime() > now ? e.muted_until : null;
              return (
                <div key={level} className="flex flex-col gap-1.5 border-t border-div px-1 py-2.5">
                  <div className="grid grid-cols-[minmax(0,1fr)_repeat(3,3.25rem)] items-center gap-2">
                    <span className="flex min-w-0 items-center gap-2 text-[14px]"><Icon name={LEVEL[level]!.icon} size={18} />{LEVEL[level]!.fa}
                      {own ? <button type="button" onClick={() => reset(level)} className="text-[11px] text-gold-ink hover:underline">مثل همه</button> : null}
                    </span>
                    <span className="flex justify-center"><Switch label={`${LEVEL[level]!.fa}: در اپ`} checked={urgent || !!e.in_app} disabled={urgent} onChange={(v) => set(level, { in_app: v })} /></span>
                    <span className="flex justify-center"><Switch label={`${LEVEL[level]!.fa}: push`} checked={urgent || !!e.push} disabled={urgent} onChange={(v) => set(level, { push: v })} /></span>
                    <span className="flex justify-center"><Switch label={`${LEVEL[level]!.fa}: صدا`} checked={!!e.sound} onChange={(v) => set(level, { sound: v })} /></span>
                  </div>
                  {!urgent ? (
                    <label className="flex items-center gap-2 text-[12px] text-sec">
                      بی‌صدا
                      <select value={muted ? 'custom' : 'none'} onChange={(ev) => { const m = MUTE.find((x) => x.id === ev.target.value); if (m) set(level, { muted_until: m.until() }); }}
                        className="h-8 rounded-[8px] border border-strong bg-tile px-2 text-[12px] text-ink outline-none focus:border-gold-ink">
                        {muted ? <option value="custom">تا {jDateTime(muted)}</option> : null}
                        {MUTE.map((m) => <option key={m.id} value={m.id}>{m.fa}</option>)}
                      </select>
                    </label>
                  ) : null}
                </div>
              );
            })}
          </div>
          <div className={cx('flex items-center gap-2', !dirty && 'opacity-60')}>
            <Button variant="primary" loading={save.isPending} disabled={!dirty} onClick={submit}>ذخیره</Button>
            <Button variant="ghost" disabled={!dirty} onClick={() => setEdits(null)}>برگرداندن</Button>
          </div>
        </>
      )}
    </Card>
  );
}
