'use client';

import Link from 'next/link';
import { Card, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { Spark } from '@/components/v14/bits';
import { useEvals, useModelComparison, useTrainingRecord, type EvalRun } from '@/lib/api/v14';
import { cx, jDate, modelLabel, usd } from '@/lib/format';

const MODEL_ORDER = ['claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-5-5'];
const byOrder = (a: string, b: string) => (MODEL_ORDER.indexOf(a) + 1 || 99) - (MODEL_ORDER.indexOf(b) + 1 || 99) || a.localeCompare(b);

/** Item 16 (contract §18.6): what an employee has been taught and how it scores — charter and curriculum versions, the
 *  skills in its prompt, its latest evals against each suite's baseline, the lessons it carries, the score trend. */
export function TrainingCard({ code }: { code: string }) {
  const q = useTrainingRecord(code);
  const evals = useEvals();
  const suite = (ref: string) => evals.data?.find((e) => e.ref === ref);
  const r = q.data;
  return (
    <Card className="flex flex-col gap-3 p-5">
      <SectionTitle title="آموزش" note="منشور، برنامه‌ی آکادمی، مهارت‌ها و آزمون‌ها" action={<Link href="/academy" className="text-[12px] text-gold-ink">آکادمی</Link>} />
      {q.isLoading ? <Skeleton className="h-24" /> : !r ? <p className="text-[13px] text-muted">هنوز سابقه‌ی آموزشی ندارد.</p> : (
        <>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-sec">
            <span>منشور نسخه‌ی <span className="fig">{r.charter_version}</span></span>
            {r.curriculum_version != null ? <span>برنامه‌ی آکادمی نسخه‌ی <span className="fig">{r.curriculum_version}</span></span> : null}
            <span className="flex-1" />
            {r.trend.length > 1 ? <span className="flex items-center gap-2 text-muted">روند <Spark values={r.trend} min={60} max={100} width={96} /></span> : null}
          </div>
          {r.skills.length ? (
            <div className="flex flex-wrap gap-1.5">
              {r.skills.map((s) => <Link key={s} href={`/skills?ref=${encodeURIComponent(s.split('@')[0]!)}`} className="fig rounded-full bg-tile px-2 py-0.5 text-[11px] text-gold-ink hover:bg-hover">{s}</Link>)}
            </div>
          ) : null}
          {r.evals.length ? (
            <ul className="flex flex-col">
              {r.evals.map((e) => {
                const s = suite(e.suite);
                const pass = s?.baseline ? e.score >= s.baseline.score - 1 : null;
                return (
                  <li key={`${e.suite}-${e.at}`} className="flex items-center gap-3 border-b border-div py-2 text-[13px] last:border-0">
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span className="truncate">{s?.title_fa ?? e.suite}</span>
                      <span className="text-[11px] text-muted"><span className="fig">{e.suite}</span> · {jDate(e.at)}{s?.baseline ? <> · خط پایه <span className="fig">{s.baseline.score}</span></> : null}</span>
                    </span>
                    <span className={cx('fig text-[14px] font-semibold', pass === false ? 'text-neg' : pass ? 'text-pos' : 'text-ink')}>{e.score}</span>
                  </li>
                );
              })}
            </ul>
          ) : <p className="text-[13px] text-muted">هنوز آزمونی نداده.</p>}
          {r.lessons.length ? (
            <p className="text-[12px] text-muted">درس‌هایی که با خودش دارد: {r.lessons.map((l, i) => <span key={l}>{i ? '، ' : ''}<Link href="/stars" className="fig text-gold-ink">{l}</Link></span>)}</p>
          ) : null}
        </>
      )}
    </Card>
  );
}

/** Item 30 (contract §18.6 ⟨1.4.5⟩): the newest run of each golden suite on each model, with what it cost. The cheapest
 *  model that passes a suite is marked, so the CEOs' model choice inside their envelope has evidence behind it. */
export function ModelComparison({ role }: { role: string }) {
  const q = useModelComparison(role);
  const evals = useEvals();
  const runs = q.data?.items ?? [];
  const models = [...new Set(runs.map((r) => r.subject.ref))].sort(byOrder);
  const suites = (evals.data ?? []).filter((e) => runs.some((r) => r.suite === e.ref));
  const cell = (suite: string, model: string) => runs.find((r) => r.suite === suite && r.subject.ref === model);
  const cheapestPass = (suite: string): EvalRun | undefined => runs
    .filter((r) => r.suite === suite && r.passed)
    .sort((a, b) => Number(a.equiv_cost_usd ?? Infinity) - Number(b.equiv_cost_usd ?? Infinity))[0];
  // The cheapest model that passes every suite of this role, if one does.
  const everywhere = models
    .filter((m) => suites.length > 0 && suites.every((s) => cell(s.ref, m)?.passed))
    .sort((a, b) => suites.reduce((t, s) => t + Number(cell(s.ref, a)?.equiv_cost_usd ?? 0), 0) - suites.reduce((t, s) => t + Number(cell(s.ref, b)?.equiv_cost_usd ?? 0), 0))[0];
  return (
    <Card className="flex flex-col gap-3 p-4">
      <SectionTitle title="مقایسه‌ی مدل‌ها" note="آخرین اجرای هر آزمون طلایی روی هر مدل، با هزینه‌ی همان اجرا" />
      {q.isLoading || evals.isLoading ? <Skeleton className="h-32" /> : !runs.length ? <p className="text-[13px] text-muted">برای این نقش هنوز آزمونی روی مدل‌ها اجرا نشده.</p> : (
        <>
          <div className="-mx-1 overflow-x-auto px-1">
            <table className="w-full min-w-[22rem] text-[12px]">
              <thead>
                <tr className="text-muted">
                  <th className="py-1.5 text-right font-normal">آزمون</th>
                  {models.map((m) => <th key={m} className="fig px-2 py-1.5 text-left font-normal">{modelLabel(m)}</th>)}
                </tr>
              </thead>
              <tbody>
                {suites.map((s) => {
                  const best = cheapestPass(s.ref);
                  return (
                    <tr key={s.ref} className="border-t border-div">
                      <td className="py-2"><span className="flex flex-col"><span className="text-[13px] text-ink">{s.title_fa}</span><span className="text-[11px] text-muted">خط پایه <span className="fig">{s.baseline?.score ?? '—'}</span></span></span></td>
                      {models.map((m) => {
                        const r = cell(s.ref, m);
                        return (
                          <td key={m} className="px-2 py-2 text-left align-top">
                            {r ? (
                              <span className="inline-flex flex-col items-end">
                                <span className={cx('fig text-[14px] font-semibold', r.passed ? 'text-pos' : 'text-neg')}>{r.score}{best?.id === r.id ? <span className="mr-1 inline-block size-1.5 rounded-full bg-gold align-middle" title="ارزان‌ترین قبول" /> : null}</span>
                                <span className="fig text-[11px] text-muted">{r.equiv_cost_usd != null ? usd(r.equiv_cost_usd) : '—'}</span>
                              </span>
                            ) : <span className="text-muted">—</span>}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="flex items-center gap-2 text-[12px] text-muted">
            <span className="inline-block size-1.5 rounded-full bg-gold" />ارزان‌ترین مدلی که آن آزمون را قبول شده.
            {everywhere ? <> ارزان‌ترین مدلی که همه را قبول شده: <span className="fig text-ink">{modelLabel(everywhere)}</span>.</> : ' هیچ مدلی همه را قبول نشده.'}
          </p>
        </>
      )}
    </Card>
  );
}
