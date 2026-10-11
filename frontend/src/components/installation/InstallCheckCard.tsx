import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { CheckCircle2, XCircle, Loader2, ShieldCheck } from 'lucide-react';
import apiClient, { apiErrorMessage } from '@/utils/api';

interface Check { key: string; ok: boolean; label: string; detail: string; fix: string }

/** Fetches the practice's public page and confirms the chat script, key, server and allowed domain. */
export default function InstallCheckCard({ defaultUrl }: { defaultUrl?: string }) {
  const [url, setUrl] = useState(defaultUrl || '');
  const check = useMutation({
    mutationFn: () => apiClient.post('/growth/install-check/', url.trim() ? { url: url.trim() } : {}, { timeout: 45000 }).then((r) => r.data),
  });
  const r = check.data;
  return (
    <section className="bg-white rounded-xl border border-gray-200 shadow-sm p-5 space-y-3" data-testid="install-check">
      <div className="flex items-center gap-2">
        <ShieldCheck className="w-5 h-5 text-teal-600" />
        <h2 className="text-base font-bold text-gray-900">Verify installation</h2>
      </div>
      <p className="text-sm text-gray-500">Checks your live website for the chat script, the right practice key, this server and an allowed domain.</p>
      <form className="flex flex-col sm:flex-row gap-2" onSubmit={(e) => { e.preventDefault(); check.mutate(); }}>
        <label htmlFor="install-url" className="sr-only">Page to check</label>
        <input id="install-url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://yourpractice.com"
          className="flex-1 px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
        <button type="submit" disabled={check.isPending}
          className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-sm font-semibold disabled:opacity-60">
          {check.isPending && <Loader2 className="w-4 h-4 animate-spin" />}{check.isPending ? 'Checking…' : 'Check my website'}
        </button>
      </form>
      {check.isError && <p className="text-sm text-rose-700" role="alert">{apiErrorMessage(check.error, 'The check could not run.')}</p>}
      {r && (
        <div className={`rounded-lg border p-3 ${r.installed ? 'bg-emerald-50 border-emerald-200' : 'bg-amber-50 border-amber-200'}`}>
          <p className="text-sm font-semibold text-gray-900" data-testid="install-verdict">
            {r.installed ? 'The chat is installed correctly.' : 'The chat is not fully set up yet.'}
          </p>
          <ul className="mt-2 space-y-2">
            {r.checks.map((c: Check) => (
              <li key={c.key} className="flex gap-2 text-sm">
                {c.ok ? <CheckCircle2 className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" aria-label="passed" />
                  : <XCircle className="w-4 h-4 text-rose-600 mt-0.5 shrink-0" aria-label="failed" />}
                <span className="min-w-0">
                  <span className="font-medium text-gray-900">{c.label}</span>
                  <span className="block text-xs text-gray-600 break-words">{c.detail}</span>
                  {c.fix && <span className="block text-xs text-gray-800 mt-0.5"><span className="font-medium">Fix: </span>{c.fix}</span>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
