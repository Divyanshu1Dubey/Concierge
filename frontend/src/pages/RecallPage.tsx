import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { CalendarClock, Upload, UserPlus, BellOff, Trash2 } from 'lucide-react';
import { growthApi, isAdminUser } from '@/services/growthApi';
import { apiErrorMessage } from '@/utils/api';
import { useAuthStore } from '@/stores/authStore';

interface Contact { id: number; name: string; email: string; phone: string; last_visit: string | null; next_due: string | null; status: string;
  consent_outreach: boolean; source: string; opted_out_email: boolean; opted_out_sms: boolean }
const input = 'w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500';
const FILTERS = [{ key: '', label: 'Everyone' }, { key: 'overdue', label: 'Overdue' }, { key: 'soon', label: 'Due in 30 days' }];

export default function RecallPage() {
  const qc = useQueryClient();
  const user = useAuthStore((s) => s.user) as any;
  const canAdmin = isAdminUser(user);
  const [filter, setFilter] = useState('');
  const [search, setSearch] = useState('');
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ name: '', email: '', phone: '', last_visit: '', consent_outreach: false });
  const [importResult, setImportResult] = useState<any>(null);
  const [optOut, setOptOut] = useState({ channel: 'email', address: '' });
  const fileRef = useRef<HTMLInputElement>(null);
  const q = useQuery({ queryKey: ['recall', filter, search], queryFn: () => growthApi.recall({ ...(filter ? { due: filter } : {}), ...(search ? { q: search } : {}) }) });
  const settings = useQuery({ queryKey: ['growth-settings'], queryFn: growthApi.settings });
  const refresh = () => qc.invalidateQueries({ queryKey: ['recall'] });
  const onError = (e: unknown) => toast.error(apiErrorMessage(e));

  const add = useMutation({ mutationFn: () => growthApi.addRecall(form), onSuccess: () => { toast.success('Patient added.'); setAdding(false); setForm({ name: '', email: '', phone: '', last_visit: '', consent_outreach: false }); refresh(); }, onError });
  const upload = useMutation({ mutationFn: (f: File) => growthApi.importRecall(f), onSuccess: (r) => { setImportResult(r); refresh(); toast.success(`Imported: ${r.created} new, ${r.updated} updated.`); }, onError });
  const update = useMutation({ mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) => growthApi.updateRecall(id, body), onSuccess: refresh, onError });
  const remove = useMutation({ mutationFn: (id: number) => growthApi.deleteRecall(id), onSuccess: () => { toast.success('Removed.'); refresh(); }, onError });
  const recordOptOut = useMutation({ mutationFn: () => growthApi.setOptOut({ ...optOut, opted_out: true }), onSuccess: () => { toast.success('Opt-out recorded. They will not receive outreach.'); setOptOut({ ...optOut, address: '' }); refresh(); }, onError });

  const rows: Contact[] = q.data?.results || [];
  const counts = q.data?.counts || {};
  const recallOn = settings.data?.recall_enabled;

  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2"><CalendarClock className="w-6 h-6 text-teal-600" /> Recall list</h1>
        <p className="text-gray-500 mt-1 text-sm">
          Patients due for their next routine visit. Import a list from your practice software, or patients are added automatically when a request is marked completed.
        </p>
        {settings.data && !recallOn && (
          <p className="mt-2 text-xs bg-amber-50 border border-amber-200 text-amber-900 rounded-lg px-3 py-2 inline-block">
            Recall reminders are off, so no messages are drafted. A practice admin can turn them on in <Link to="/dashboard/growth" className="underline">Growth settings</Link>.
          </p>
        )}
      </div>

      <div className="grid grid-cols-3 gap-3">
        {[['Patients on the list', counts.total], ['Overdue', counts.overdue], ['Due in 30 days', counts.due_soon]].map(([l, n]) => (
          <div key={l as string} className="bg-white border border-gray-200 rounded-xl p-4"><div className="text-2xl font-bold tabular-nums">{n ?? '–'}</div><div className="text-xs text-gray-500">{l}</div></div>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="inline-flex bg-gray-100 rounded-lg p-1" role="tablist">
          {FILTERS.map((f) => <button key={f.key} role="tab" aria-selected={filter === f.key} onClick={() => setFilter(f.key)} className={`px-3 py-1.5 rounded-md text-sm ${filter === f.key ? 'bg-white shadow-sm font-medium' : 'text-gray-600'}`}>{f.label}</button>)}
        </div>
        <input aria-label="Search patients" placeholder="Search name, email or phone" className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm flex-1 min-w-[180px]" value={search} onChange={(e) => setSearch(e.target.value)} />
        <button onClick={() => setAdding(!adding)} className="inline-flex items-center gap-1 px-3 py-1.5 border border-gray-200 rounded-lg text-sm hover:bg-gray-50"><UserPlus className="w-4 h-4" /> Add patient</button>
        {canAdmin && (
          <>
            <input ref={fileRef} type="file" accept=".csv,text/csv" className="hidden" aria-label="CSV file" onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = ''; }} />
            <button onClick={() => fileRef.current?.click()} disabled={upload.isPending} className="inline-flex items-center gap-1 px-3 py-1.5 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-sm font-semibold disabled:opacity-50"><Upload className="w-4 h-4" /> {upload.isPending ? 'Importing…' : 'Import CSV'}</button>
          </>
        )}
      </div>
      {canAdmin && <p className="text-xs text-gray-500 -mt-3">CSV columns: name (or first/last name), email, phone, last visit, next due, consent (yes/no). Dates as YYYY-MM-DD or MM/DD/YYYY.</p>}

      {importResult && (
        <div className="bg-white border border-gray-200 rounded-xl p-4 text-sm">
          <p className="font-medium">Import finished: {importResult.created} added, {importResult.updated} updated, {importResult.skipped} skipped.</p>
          {importResult.errors?.length > 0 && <ul className="mt-1 text-xs text-rose-700 list-disc pl-4">{importResult.errors.map((e: string) => <li key={e}>{e}</li>)}</ul>}
        </div>
      )}

      {adding && (
        <form className="bg-gray-50 border border-gray-200 rounded-xl p-4 grid sm:grid-cols-2 gap-3" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
          <input className={input} aria-label="Name" placeholder="Full name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <input className={input} aria-label="Email" placeholder="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <input className={input} aria-label="Phone" placeholder="Phone" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          <label className="text-xs text-gray-600">Last visit<input type="date" className={input} value={form.last_visit} onChange={(e) => setForm({ ...form, last_visit: e.target.value })} /></label>
          <label className="flex items-center gap-2 text-sm sm:col-span-2"><input type="checkbox" className="accent-teal-600" checked={form.consent_outreach} onChange={(e) => setForm({ ...form, consent_outreach: e.target.checked })} /> Patient agreed to hear from the practice (needed for reactivation messages)</label>
          <div className="sm:col-span-2 flex gap-2"><button className="px-4 py-2 bg-teal-600 text-white rounded-lg text-sm font-semibold disabled:opacity-50" disabled={add.isPending || !form.name.trim()}>Add</button><button type="button" className="px-4 py-2 border border-gray-200 rounded-lg text-sm" onClick={() => setAdding(false)}>Cancel</button></div>
        </form>
      )}

      {q.isLoading ? <div className="h-40 bg-gray-100 rounded-xl animate-pulse" /> : rows.length === 0 ? (
        <div className="text-center bg-white border border-dashed border-gray-300 rounded-xl py-10 text-sm text-gray-600">No patients here yet.</div>
      ) : (
        <div className="bg-white border border-gray-200 rounded-xl overflow-x-auto">
          <table className="w-full text-sm min-w-[720px]">
            <thead className="bg-gray-50 text-left text-xs text-gray-500"><tr><th className="px-4 py-2 font-medium">Patient</th><th className="px-4 py-2 font-medium">Last visit</th><th className="px-4 py-2 font-medium">Next due</th><th className="px-4 py-2 font-medium">Contact</th><th className="px-4 py-2 font-medium">Status</th><th className="px-4 py-2" /></tr></thead>
            <tbody>
              {rows.map((c) => {
                const overdue = c.next_due && c.next_due < new Date().toISOString().slice(0, 10);
                return (
                  <tr key={c.id} className="border-t border-gray-100">
                    <td className="px-4 py-2"><div className="font-medium text-gray-900">{c.name}</div><div className="text-xs text-gray-500">{c.source === 'heyjarvis' ? 'Added from a completed request' : c.source === 'import' ? 'Imported' : 'Added by staff'}</div></td>
                    <td className="px-4 py-2 tabular-nums">{c.last_visit || '–'}</td>
                    <td className={`px-4 py-2 tabular-nums ${overdue ? 'text-rose-700 font-medium' : ''}`}>{c.next_due || '–'}</td>
                    <td className="px-4 py-2 text-xs text-gray-600">
                      {c.email && <div>{c.email}{c.opted_out_email && <span className="ml-1 text-rose-700">(opted out)</span>}</div>}
                      {c.phone && <div>{c.phone}{c.opted_out_sms && <span className="ml-1 text-rose-700">(STOP)</span>}</div>}
                      <label className="inline-flex items-center gap-1 mt-0.5"><input type="checkbox" className="accent-teal-600" checked={c.consent_outreach} onChange={(e) => update.mutate({ id: c.id, body: { consent_outreach: e.target.checked } })} /> agreed to outreach</label>
                    </td>
                    <td className="px-4 py-2">
                      <select aria-label={`Status for ${c.name}`} className="border border-gray-200 rounded-md text-xs px-2 py-1" value={c.status} onChange={(e) => update.mutate({ id: c.id, body: { status: e.target.value } })}>
                        <option value="active">Active</option><option value="scheduled">Scheduled</option><option value="inactive">Inactive</option>
                      </select>
                    </td>
                    <td className="px-4 py-2 text-right">{canAdmin && <button aria-label={`Remove ${c.name}`} onClick={() => { if (window.confirm(`Remove ${c.name} from the recall list?`)) remove.mutate(c.id); }} className="p-1.5 hover:bg-gray-50 rounded"><Trash2 className="w-4 h-4 text-gray-400" /></button>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <section className="bg-white border border-gray-200 rounded-xl p-4">
        <h2 className="font-semibold text-gray-900 text-sm flex items-center gap-2"><BellOff className="w-4 h-4 text-gray-500" /> Record an opt-out</h2>
        <p className="text-xs text-gray-500 mt-0.5">If a patient asks by phone or in person not to be contacted, record it here. Email unsubscribe links and STOP replies are recorded automatically.</p>
        <form className="mt-2 flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); recordOptOut.mutate(); }}>
          <select aria-label="Channel" className="px-3 py-2 border border-gray-200 rounded-lg text-sm" value={optOut.channel} onChange={(e) => setOptOut({ ...optOut, channel: e.target.value })}><option value="email">Email</option><option value="sms">Text message</option></select>
          <input aria-label="Email or phone" className="px-3 py-2 border border-gray-200 rounded-lg text-sm flex-1 min-w-[200px]" placeholder={optOut.channel === 'email' ? 'patient@email.com' : '(919) 555-0100'} value={optOut.address} onChange={(e) => setOptOut({ ...optOut, address: e.target.value })} />
          <button className="px-4 py-2 border border-gray-200 rounded-lg text-sm hover:bg-gray-50 disabled:opacity-50" disabled={!optOut.address.trim() || recordOptOut.isPending}>Record opt-out</button>
        </form>
      </section>
    </div>
  );
}
