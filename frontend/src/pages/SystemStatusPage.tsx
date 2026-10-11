import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Activity, CheckCircle2, AlertTriangle, XCircle, Info, RefreshCw, DatabaseBackup, Play } from 'lucide-react';
import apiClient, { apiErrorMessage } from '@/utils/api';

interface Check { key: string; label: string; status: 'ok' | 'warn' | 'fail' | 'info'; detail: string; fix: string }
const ICON = {
  ok: { Icon: CheckCircle2, cls: 'text-emerald-600', label: 'OK' },
  warn: { Icon: AlertTriangle, cls: 'text-amber-500', label: 'Warning' },
  fail: { Icon: XCircle, cls: 'text-rose-600', label: 'Blocker' },
  info: { Icon: Info, cls: 'text-gray-400', label: 'Info' },
};

export default function SystemStatusPage() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ['system-status'],
    queryFn: () => apiClient.get('/growth/system-status/').then((r) => r.data),
    refetchInterval: (query) => ((query.state.data as any)?.restore_drill?.status === 'running' ? 4000 : false),
  });
  const drill = useMutation({
    mutationFn: () => apiClient.post('/growth/system-status/', { action: 'restore_drill' }).then((r) => r.data),
    onSuccess: () => { toast.success('Restore drill started. This takes a minute.'); qc.invalidateQueries({ queryKey: ['system-status'] }); },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });
  const runJobs = useMutation({
    mutationFn: () => apiClient.post('/growth/cron/status/', {}).then((r) => r.data),
    onSuccess: (r) => {
      const failed = r.ran.filter((x: any) => x.status === 'failed').length;
      toast[failed ? 'error' : 'success'](failed ? `${failed} job(s) failed. See history below.` : 'Due jobs ran.');
      qc.invalidateQueries({ queryKey: ['system-status'] });
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });
  const d = q.data;
  const rd = d?.restore_drill;

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2"><Activity className="w-6 h-6 text-teal-600" /> System status</h1>
          <p className="text-gray-500 mt-1 text-sm">Everything that must be true before practices rely on HeyJarvis, checked live on this server.</p>
        </div>
        <button onClick={() => q.refetch()} className="inline-flex items-center gap-1.5 px-3 py-2 border border-gray-200 rounded-lg text-sm hover:bg-gray-50">
          <RefreshCw className={`w-4 h-4 ${q.isFetching ? 'animate-spin' : ''}`} /> Re-check
        </button>
      </div>

      {q.isLoading ? <div className="h-40 bg-gray-100 rounded-xl animate-pulse" /> : q.isError ? (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded-xl p-4 text-sm">{apiErrorMessage(q.error, 'Could not load system status.')}</div>
      ) : d && (
        <>
          <div className={`rounded-xl border p-4 ${d.ready ? 'bg-emerald-50 border-emerald-200 text-emerald-900' : 'bg-rose-50 border-rose-200 text-rose-900'}`} data-testid="readiness-banner">
            <p className="font-semibold">{d.ready ? 'No blockers found.' : `${d.counts.fail} blocker${d.counts.fail === 1 ? '' : 's'} to fix before going live.`}</p>
            <p className="text-sm opacity-80">{d.counts.warn} warning{d.counts.warn === 1 ? '' : 's'} · {d.counts.ok} passing · checked {new Date(d.generated_at).toLocaleTimeString()}</p>
          </div>

          {d.sections.map((s: any) => (
            <section key={s.title} className="bg-white border border-gray-200 rounded-xl overflow-hidden">
              <h2 className="px-5 py-3 border-b border-gray-100 font-semibold text-gray-900 text-sm">{s.title}</h2>
              <ul className="divide-y divide-gray-100">
                {s.checks.map((c: Check) => {
                  const ic = ICON[c.status];
                  return (
                    <li key={c.key} className="px-5 py-3 flex gap-3" data-testid={`check-${c.key}`}>
                      <ic.Icon className={`w-5 h-5 shrink-0 mt-0.5 ${ic.cls}`} aria-label={ic.label} />
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-gray-900">{c.label}</p>
                        <p className="text-xs text-gray-500 break-words">{c.detail}</p>
                        {c.fix && <p className="text-sm text-gray-700 mt-1"><span className="font-medium">Fix: </span>{c.fix}</p>}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}

          <section className="bg-white border border-gray-200 rounded-xl p-5 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-semibold text-gray-900 text-sm flex items-center gap-2"><DatabaseBackup className="w-4 h-4 text-teal-600" /> Restore drill</h2>
              <button onClick={() => drill.mutate()} disabled={drill.isPending || rd?.status === 'running'}
                className="px-3 py-1.5 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-sm font-semibold disabled:opacity-50">
                {rd?.status === 'running' ? 'Running…' : 'Run restore drill'}
              </button>
            </div>
            <p className="text-xs text-gray-500">Restores the newest backup into a temporary database, upgrades it to the current version and checks it. The live database is never touched.</p>
            {rd && rd.status !== 'running' && (
              <div className={`text-sm rounded-lg p-3 ${rd.ok ? 'bg-emerald-50 text-emerald-900' : 'bg-rose-50 text-rose-900'}`} data-testid="restore-result">
                <p className="font-medium">{rd.ok ? `Passed for ${rd.source}` : `Failed${rd.source ? ` for ${rd.source}` : ''}`}{rd.finished_at ? ` · ${new Date(rd.finished_at).toLocaleString()}` : ''}</p>
                <ul className="mt-1 text-xs space-y-0.5">{(rd.steps || []).map((s: any) => <li key={s.step}>{s.ok ? '✓' : '✗'} {s.step}: {s.detail}</li>)}</ul>
              </div>
            )}
          </section>

          <section className="bg-white border border-gray-200 rounded-xl p-5">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
              <h2 className="font-semibold text-gray-900 text-sm">Scheduled job history</h2>
              <button onClick={() => runJobs.mutate()} disabled={runJobs.isPending} className="inline-flex items-center gap-1 px-3 py-1.5 border border-gray-200 rounded-lg text-sm hover:bg-gray-50 disabled:opacity-50">
                <Play className="w-3.5 h-3.5" /> {runJobs.isPending ? 'Running…' : 'Run due jobs now'}
              </button>
            </div>
            {d.jobs.length === 0 ? <p className="text-sm text-gray-500">No jobs have run yet.</p> : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm min-w-[520px]">
                  <thead><tr className="text-left text-xs text-gray-500"><th className="py-1 font-medium">Job</th><th className="py-1 font-medium">Result</th><th className="py-1 font-medium">Started</th><th className="py-1 font-medium">Took</th></tr></thead>
                  <tbody>{d.jobs.map((j: any, i: number) => (
                    <tr key={i} className="border-t border-gray-100">
                      <td className="py-1.5">{j.job}</td>
                      <td className={`py-1.5 ${j.status === 'failed' ? 'text-rose-700' : 'text-gray-700'}`}>{j.status}{j.error ? `: ${j.error}` : ''}</td>
                      <td className="py-1.5 text-gray-500">{new Date(j.started_at).toLocaleString()}</td>
                      <td className="py-1.5 text-gray-500 tabular-nums">{j.duration_ms !== null ? `${j.duration_ms} ms` : '–'}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            )}
          </section>

          <section className="bg-white border border-gray-200 rounded-xl p-5">
            <h2 className="font-semibold text-gray-900 text-sm mb-2">Practice setup</h2>
            <ul className="divide-y divide-gray-100 text-sm">
              {d.practices.map((p: any) => (
                <li key={p.id} className="py-2 flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium text-gray-800">{p.name}</span>
                  {p.ready ? <span className="text-xs text-emerald-700">Ready</span> : <span className="text-xs text-amber-700">Missing: {p.gaps.join(', ')}</span>}
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}
