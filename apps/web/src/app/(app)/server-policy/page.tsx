'use client';

// ⟨1.8⟩ «قوانین سرورها» (§26.3, `GET/PUT /control/server-policy`): everything on the companies' servers runs free; only the categories
// switched on here wait for the owner's seal. A change is saved with the passkey on the exact body (Android: Policy.kt).

import Link from 'next/link';
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Card, ErrorState, PageHeader, Skeleton, Switch } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import {
  FREE_ON_SERVERS, SEAL_CATEGORIES, policyChanges, policyWith, putServerPolicy, sealCategory, serverError, useServerPolicy, type ServerPolicy,
} from '@/lib/api/v26';

export default function ServerPolicyPage() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useServerPolicy();
  const [edited, setDraft] = useState<ServerPolicy | null>(null);
  const [busy, setBusy] = useState(false);
  const base = q.data ?? null;
  const draft = edited ?? base;
  const changes = base && draft ? policyChanges(base, draft) : [];

  const save = async () => {
    if (!draft) return;
    setBusy(true);
    try {
      const out = await putServerPolicy(draft);
      qc.setQueryData(['servers', 'policy'], out);
      setDraft(null);
      void qc.invalidateQueries({ queryKey: ['servers'] });
      toast({ tone: 'ok', text: 'قوانین سرورها ذخیره شد.' });
    } catch (e) {
      toast({ tone: 'error', text: serverError(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader eyebrow="کنترل بی‌اصطکاک سرورهای شرکت‌ها" title="قوانین سرورها" />
      <div className="grid max-w-5xl items-start gap-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <div className="flex flex-col gap-4">
          {!draft ? (q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : <Skeleton className="h-[420px] rounded-[16px]" />) : (
            <Card className="flex flex-col px-4 py-1.5">
              <div className="flex items-center gap-2 py-2">
                <h2 className="flex-1 text-[13px] font-semibold text-gold-ink">فقط این‌ها منتظر مُهر تو میمانند</h2>
                <span className="text-[12px] text-muted">{draft.seal_required.filter((k) => SEAL_CATEGORIES.some((c) => c.key === k)).length} از {SEAL_CATEGORIES.length}</span>
              </div>
              {SEAL_CATEGORIES.map((c) => (
                <div key={c.key} className="flex items-center gap-3 border-t border-div py-3">
                  <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span className="text-[13px] font-semibold text-ink">{c.titleFa}</span>
                    <span dir="ltr" className="fig text-start text-[12px] text-muted">{c.catches}</span>
                    <span className="text-[11px] text-muted">{c.whyFa}</span>
                  </div>
                  <Switch checked={draft.seal_required.includes(c.key)} onChange={(on) => setDraft(policyWith(draft, c.key, on))} label={c.titleFa} />
                </div>
              ))}
              <p className="border-t border-div py-2.5 text-[11px] text-muted">دروازه هم از روی ابزار و هم از روی الگوی فرمان میگیرد؛ در Claude Code روی سرور هم همین الگوها پیش از اجرا جلویش را میگیرند و کارتش به کارتابل میاید.</p>
              <Link href="/cartable" className="mb-1.5 inline-flex h-8 items-center gap-1.5 self-start rounded-[8px] px-2 text-[12px] font-semibold text-gold-ink hover:bg-gold-soft"><Icon name="cartable" size={16} />کارتابل</Link>
            </Card>
          )}
          <div className="flex flex-col gap-2">
            {changes.map(([k, on]) => <span key={k} className={on ? 'text-[12px] text-gold-ink' : 'text-[12px] text-warn'}>{on ? 'منتظر مُهر میشود: ' : 'بدون مُهر اجرا میشود: '}{sealCategory(k)?.titleFa ?? k}</span>)}
            <Button variant="primary" size="lg" icon="seal" disabled={!changes.length} loading={busy} onClick={save}>با گذرکلید ذخیره کن</Button>
            {changes.length ? <Button variant="ghost" size="sm" onClick={() => setDraft(null)}>برگرداندن</Button> : null}
            <p className="text-[11px] text-muted">هشدار: دسته‌ای که خاموش کنی، از همان لحظه بی‌مُهر تو روی همه‌ی سرورهای همه‌ی شرکت‌ها اجرا میشود.</p>
          </div>
        </div>
        <Card className="flex gap-2.5 bg-pos-soft p-4">
          <span className="text-pos"><Icon name="resume" size={20} /></span>
          <div className="flex min-w-0 flex-1 flex-col gap-1.5">
            <span className="text-[14px] font-semibold text-ink">بقیه‌ی کارها آزاد است، بی‌کارت</span>
            <span className="text-[12px] leading-6 text-sec">ایجنت‌ها هر کاری را که از شرکت بخواهی روی سرورها انجام میدهند؛ هر فراخوانی با فرمانش (رمزها ماسک‌شده) در Audit میماند و تو در «فعالیت» هر سرور زنده میبینی.</span>
            <div className="flex flex-wrap gap-1.5">{FREE_ON_SERVERS.map((f) => <span key={f} className="rounded-[8px] bg-card px-2 py-0.5 text-[11px] text-ink">{f}</span>)}</div>
            <Link href="/servers" className="mt-1 inline-flex h-8 items-center gap-1.5 self-start rounded-[8px] px-2 text-[12px] font-semibold text-gold-ink hover:bg-gold-soft"><Icon name="server" size={16} />همه‌ی سرورها</Link>
          </div>
        </Card>
      </div>
    </>
  );
}
