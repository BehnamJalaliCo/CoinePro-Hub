'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Sheet } from '@/components/ui/overlay';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { useRecordResolution } from '@/lib/api/v15';

const field = 'w-full rounded-[10px] border border-strong bg-tile px-3 text-[15px] text-ink outline-none focus:border-gold-ink';

/** The owner records a resolution from a message (§5.3 POST /resolutions): numbered, append-only, linked to the message. */
export function RecordResolution({ source, onClose }: { source: { ref: string; body: string }; onClose: () => void }) {
  const firstLine = source.body.replace(/[*_`#>]/g, '').split('\n').find((l) => l.trim())?.trim() ?? '';
  const [title, setTitle] = useState(firstLine.length > 80 ? `${firstLine.slice(0, 77)}…` : firstLine);
  const [body, setBody] = useState(source.body);
  const record = useRecordResolution();
  const toast = useToast();
  const save = async () => {
    try {
      const r = await record.mutateAsync({ title: title.trim(), body: body.trim(), source_message: source.ref });
      toast({ tone: 'ok', text: <>مصوبه‌ی <span className="fig">{r.ref}</span> ثبت شد.</> });
      onClose();
    } catch (e) {
      toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'ثبت نشد.' });
    }
  };
  return (
    <Sheet open onOpenChange={(v) => !v && onClose()} title="ثبت به‌عنوان مصوبه" description={<>از پیام <span className="fig">{source.ref}</span>؛ بعد از ثبت عوض نمیشود.</>}
      footer={<><Button variant="primary" icon="seal" loading={record.isPending} disabled={!title.trim() || !body.trim()} onClick={save}>ثبت مصوبه</Button><Button variant="ghost" onClick={onClose}>نه</Button></>}>
      <div className="flex flex-col gap-4">
        <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-sec">عنوان
          <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} className={`${field} h-11`} />
        </label>
        <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-sec">متن
          <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={7} maxLength={20000} className={`${field} py-3 leading-7`} />
        </label>
      </div>
    </Sheet>
  );
}
