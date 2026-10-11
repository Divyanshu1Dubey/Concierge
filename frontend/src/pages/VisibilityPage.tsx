import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Globe, Search, CheckCircle2, AlertTriangle, XCircle, Copy, Loader2 } from 'lucide-react';
import { growthApi } from '@/services/growthApi';
import { apiErrorMessage } from '@/utils/api';

interface Finding { id: string; status: 'pass' | 'warn' | 'fail'; severity: string; category: string; title: string; detail: string; fix: string }
const CATEGORY: Record<string, string> = {
  facts: 'Practice facts', conversion: 'Turning visitors into patients', search: 'Search engines',
  ai: 'Structured data & AI assistants', technical: 'Technical basics',
};
const LH_LABELS: [string, string][] = [['performance', 'Performance'], ['accessibility', 'Accessibility'], ['best_practices', 'Best practices'], ['seo', 'SEO']];

function scoreColor(n: number) {
  return n >= 85 ? 'text-emerald-700 bg-emerald-50 border-emerald-200' : n >= 60 ? 'text-amber-700 bg-amber-50 border-amber-200' : 'text-rose-700 bg-rose-50 border-rose-200';
}

function CopyBlock({ title, text, help }: { title: string; text: string; help?: string }) {
  if (!text) return null;
  return (
    <div>
      <div className="flex items-center justify-between gap-2 mb-1">
        <h3 className="text-sm font-semibold text-gray-800">{title}</h3>
        <button onClick={() => navigator.clipboard.writeText(text).then(() => toast.success('Copied.'), () => toast.error('Could not copy. Select the text instead.'))}
          className="inline-flex items-center gap-1 text-xs px-2 py-1 border border-gray-200 rounded-md hover:bg-gray-50"><Copy className="w-3.5 h-3.5" /> Copy</button>
      </div>
      {help && <p className="text-xs text-gray-500 mb-1">{help}</p>}
      <pre tabIndex={0} aria-label={title} className="text-xs bg-gray-900 text-gray-100 rounded-lg p-3 overflow-x-auto max-h-64 whitespace-pre">{text}</pre>
    </div>
  );
}

export default function VisibilityPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['visibility'], queryFn: growthApi.visibility });
  const facts = useQuery({ queryKey: ['visibility-facts'], queryFn: growthApi.facts });
  const [url, setUrl] = useState('');
  useEffect(() => { if (q.data && !url) setUrl(q.data.website || ''); }, [q.data]); // eslint-disable-line react-hooks/exhaustive-deps
  const latest = q.data?.latest;
  const lhPending = latest?.lighthouse?.status === 'pending';

  // Lighthouse scores arrive in the background; poll the report until they do.
  const detail = useQuery({
    queryKey: ['visibility-report', latest?.id],
    queryFn: () => growthApi.visibilityReport(latest.id),
    enabled: Boolean(latest?.id && lhPending),
    refetchInterval: (query) => ((query.state.data as any)?.lighthouse?.status === 'pending' ? 5000 : false),
  });
  const report = detail.data || latest;

  const run = useMutation({
    mutationFn: () => growthApi.runVisibility(url.trim() || undefined),
    onSuccess: (r) => {
      if (r.status === 'failed') toast.error(r.error || 'The check could not finish.');
      else toast.success('Website checked.');
      qc.invalidateQueries({ queryKey: ['visibility'] });
    },
    onError: (e) => toast.error(apiErrorMessage(e, 'The check could not run.')),
  });

  const findings: Finding[] = report?.findings || [];
  const groups = Object.keys(CATEGORY).map((c) => ({ key: c, items: findings.filter((f) => f.category === c) })).filter((g) => g.items.length);
  const toFix = findings.filter((f) => f.status !== 'pass');

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2"><Globe className="w-6 h-6 text-teal-600" /> Website check</h1>
        <p className="text-gray-500 mt-1 text-sm">
          Checks that your website shows the same facts patients get from HeyJarvis, makes booking easy, and can be read by search engines and AI assistants.
          It does not promise rankings; it finds things you can fix.
        </p>
      </div>

      <form className="flex flex-col sm:flex-row gap-2" onSubmit={(e) => { e.preventDefault(); run.mutate(); }}>
        <label htmlFor="site-url" className="sr-only">Website address</label>
        <input id="site-url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://yourpractice.com"
          className="flex-1 px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
        <button type="submit" disabled={run.isPending} className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-sm font-semibold disabled:opacity-60">
          {run.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />} {run.isPending ? 'Checking…' : 'Check my website'}
        </button>
      </form>

      {q.isLoading ? <div className="h-40 bg-gray-100 rounded-xl animate-pulse" /> : !report ? (
        <div className="text-center bg-white border border-dashed border-gray-300 rounded-xl py-10 px-6 text-sm text-gray-600">
          No checks yet. Run one to get a prioritised list of fixes.
        </div>
      ) : report.status === 'failed' ? (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded-xl p-4 text-sm">
          <strong>The last check could not finish.</strong> {report.error}
        </div>
      ) : (
        <>
          <section className="bg-white border border-gray-200 rounded-xl p-5 flex flex-col sm:flex-row gap-5 sm:items-center">
            <div className={`shrink-0 w-24 h-24 rounded-2xl border flex flex-col items-center justify-center ${scoreColor(report.score)}`}>
              <span className="text-3xl font-bold tabular-nums">{report.score}</span><span className="text-[11px]">out of 100</span>
            </div>
            <div className="min-w-0 flex-1">
              <p className="font-semibold text-gray-900 truncate">{report.url}</p>
              <p className="text-sm text-gray-600 mt-0.5">{toFix.length === 0 ? 'Everything we check looks good.' : `${toFix.length} thing${toFix.length === 1 ? '' : 's'} to improve, most important first.`}</p>
              <p className="text-xs text-gray-500 mt-1">Checked {new Date(report.created_at).toLocaleString()}</p>
              <div className="mt-3 flex flex-wrap gap-2 text-xs">
                {report.lighthouse?.status === 'ok' && LH_LABELS.map(([k, l]) => report.lighthouse[k] !== undefined && (
                  <span key={k} className={`px-2 py-1 rounded-md border ${scoreColor(report.lighthouse[k])}`}>{l} {report.lighthouse[k]}</span>
                ))}
                {lhPending && (detail.data?.lighthouse?.status ?? 'pending') === 'pending' && <span className="inline-flex items-center gap-1 text-gray-500"><Loader2 className="w-3 h-3 animate-spin" /> Getting Google Lighthouse scores…</span>}
                {report.lighthouse?.status === 'failed' && <span className="text-gray-500">Lighthouse scores unavailable: {report.lighthouse.error}</span>}
                {report.lighthouse?.status === 'off' && <span className="text-gray-400">Lighthouse scores are off (add a PageSpeed API key in Integrations to include them).</span>}
              </div>
            </div>
          </section>

          {groups.map((g) => (
            <section key={g.key} className="bg-white border border-gray-200 rounded-xl overflow-hidden">
              <h2 className="px-5 py-3 border-b border-gray-100 font-semibold text-gray-900 text-sm">{CATEGORY[g.key]}</h2>
              <ul className="divide-y divide-gray-100">
                {g.items.map((f) => {
                  const Icon = f.status === 'pass' ? CheckCircle2 : f.status === 'warn' ? AlertTriangle : XCircle;
                  const color = f.status === 'pass' ? 'text-emerald-600' : f.status === 'warn' ? 'text-amber-500' : 'text-rose-600';
                  return (
                    <li key={f.id} className="px-5 py-3 flex gap-3" data-testid={`finding-${f.id}`}>
                      <Icon className={`w-5 h-5 shrink-0 mt-0.5 ${color}`} aria-label={f.status} />
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-gray-900">{f.title}{f.status !== 'pass' && f.severity === 'high' && <span className="ml-2 text-[10px] uppercase tracking-wide text-rose-700 bg-rose-50 px-1.5 py-0.5 rounded">Important</span>}</p>
                        <p className="text-xs text-gray-500 break-words">{f.detail}</p>
                        {f.fix && <p className="text-sm text-gray-700 mt-1"><span className="font-medium">How to fix: </span>{f.fix}</p>}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </>
      )}

      <section className="bg-white border border-gray-200 rounded-xl p-5 space-y-4">
        <div>
          <h2 className="font-semibold text-gray-900">Website facts from HeyJarvis</h2>
          <p className="text-sm text-gray-500 mt-0.5">Ready-to-paste code built from the facts you approved. Your web person can add it to the site so it stays consistent with the concierge.</p>
        </div>
        {facts.isLoading ? <div className="h-24 bg-gray-100 rounded-lg animate-pulse" /> : facts.data && (
          <>
            <CopyBlock title="Dentist structured data" text={facts.data.structured_data} help="Paste inside the <head> of your homepage." />
            {facts.data.faq_count > 0 ? (
              <>
                <CopyBlock title={`FAQ section (${facts.data.faq_count} answers)`} text={facts.data.faq_html} help="Paste where you want the questions to appear." />
                <CopyBlock title="FAQ structured data" text={facts.data.faq_structured_data} help="Paste on the same page as the FAQ section." />
              </>
            ) : <p className="text-sm text-gray-500">Add answers in Practice Knowledge to generate an FAQ section.</p>}
            <ul className="text-xs text-gray-500 list-disc pl-4 space-y-0.5">{facts.data.notes.map((n: string) => <li key={n}>{n}</li>)}</ul>
          </>
        )}
      </section>

      {q.data?.history?.length > 1 && (
        <section className="text-sm">
          <h2 className="font-semibold text-gray-900 mb-2">Earlier checks</h2>
          <ul className="space-y-1 text-gray-600">{q.data.history.slice(1).map((h: any) => (
            <li key={h.id} className="flex justify-between gap-3"><span className="truncate">{new Date(h.created_at).toLocaleDateString()} · {h.url}</span><span className="tabular-nums">{h.status === 'ok' ? `${h.score}/100` : 'failed'}</span></li>
          ))}</ul>
        </section>
      )}
    </div>
  );
}
