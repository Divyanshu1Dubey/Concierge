import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Plug, CheckCircle2, AlertTriangle, Clock, Circle, Star, ExternalLink } from 'lucide-react';
import { growthApi, isAdminUser } from '@/services/growthApi';
import { apiErrorMessage } from '@/utils/api';
import { useAuthStore } from '@/stores/authStore';

interface Row { key: string; name: string; state: string; detail: string; action: string | null; category: string; requirements: string[]; [k: string]: any }
const STATE: Record<string, { label: string; cls: string; Icon: any }> = {
  working: { label: 'Working', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200', Icon: CheckCircle2 },
  test_mode: { label: 'Test mode', cls: 'bg-sky-50 text-sky-700 border-sky-200', Icon: CheckCircle2 },
  available: { label: 'Available', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200', Icon: CheckCircle2 },
  needs_setup: { label: 'Needs setup', cls: 'bg-amber-50 text-amber-800 border-amber-200', Icon: AlertTriangle },
  error: { label: 'Needs attention', cls: 'bg-rose-50 text-rose-700 border-rose-200', Icon: AlertTriangle },
  awaiting_approval: { label: 'Awaiting Google approval', cls: 'bg-violet-50 text-violet-700 border-violet-200', Icon: Clock },
  not_connected: { label: 'Not connected', cls: 'bg-gray-50 text-gray-600 border-gray-200', Icon: Circle },
};
const SECTIONS: [string, string][] = [['core', 'Essentials'], ['channels', 'Messaging'], ['visibility', 'Online visibility'], ['operations', 'Practice software'], ['website', 'Website']];
const input = 'w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500';
const btn = 'px-3 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-sm font-semibold disabled:opacity-50';
const btn2 = 'px-3 py-2 border border-gray-200 rounded-lg text-sm hover:bg-gray-50 disabled:opacity-50';

function TwilioForm({ row, onDone }: { row: Row; onDone: () => void }) {
  const [v, setV] = useState({ account_sid: '', auth_token: '', from_number: row.connected_source || '' });
  const save = useMutation({ mutationFn: () => growthApi.twilioSave(v), onSuccess: () => { toast.success('Twilio connected.'); onDone(); }, onError: (e) => toast.error(apiErrorMessage(e)) });
  const off = useMutation({ mutationFn: growthApi.twilioDisconnect, onSuccess: () => { toast.success('Disconnected.'); onDone(); }, onError: (e) => toast.error(apiErrorMessage(e)) });
  return (
    <form className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <input className={input} aria-label="Twilio account SID" placeholder="Account SID (AC…)" value={v.account_sid} onChange={(e) => setV({ ...v, account_sid: e.target.value })} />
      <input className={input} aria-label="Twilio auth token" type="password" autoComplete="off" placeholder={row.connected_source ? 'Auth token (unchanged)' : 'Auth token'} value={v.auth_token} onChange={(e) => setV({ ...v, auth_token: e.target.value })} />
      <input className={input} aria-label="Twilio sending number" placeholder="+1XXXXXXXXXX" value={v.from_number} onChange={(e) => setV({ ...v, from_number: e.target.value })} />
      <div className="sm:col-span-3 flex gap-2">
        <button className={btn} disabled={save.isPending}>{save.isPending ? 'Checking…' : 'Save & verify'}</button>
        {row.connected_source && <button type="button" className={btn2} onClick={() => off.mutate()}>Disconnect</button>}
      </div>
      <p className="sm:col-span-3 text-xs text-gray-500">Set the number's incoming-message webhook in Twilio to <code>/api/v1/growth/sms/inbound/</code> on this server so STOP replies are honoured.</p>
    </form>
  );
}

function NexHealthForm({ row, onDone }: { row: Row; onDone: () => void }) {
  const [v, setV] = useState({ api_key: '', subdomain: row.subdomain || '', location_id: String(row.location_id || '') });
  const [providers, setProviders] = useState<any[] | null>(null);
  const save = useMutation({ mutationFn: () => growthApi.nexhealthSave(v), onSuccess: (r) => { toast.success(r.message); onDone(); }, onError: (e) => toast.error(apiErrorMessage(e)) });
  const test = useMutation({ mutationFn: growthApi.nexhealthTest, onSuccess: (r) => { setProviders(r.providers); toast.success('Connected to NexHealth.'); onDone(); }, onError: (e) => toast.error(apiErrorMessage(e)) });
  const off = useMutation({ mutationFn: growthApi.nexhealthDisconnect, onSuccess: () => { toast.success('Disconnected.'); onDone(); } });
  return (
    <div className="mt-3 space-y-2">
      <form className="grid grid-cols-1 sm:grid-cols-3 gap-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <input className={input} aria-label="NexHealth API key" type="password" autoComplete="off" placeholder={row.subdomain ? 'API key (unchanged)' : 'API key'} value={v.api_key} onChange={(e) => setV({ ...v, api_key: e.target.value })} />
        <input className={input} aria-label="NexHealth subdomain" placeholder="Subdomain" value={v.subdomain} onChange={(e) => setV({ ...v, subdomain: e.target.value })} />
        <input className={input} aria-label="NexHealth location ID" placeholder="Location ID" value={v.location_id} onChange={(e) => setV({ ...v, location_id: e.target.value })} />
        <div className="sm:col-span-3 flex flex-wrap gap-2">
          <button className={btn} disabled={save.isPending}>Save</button>
          {row.subdomain && <button type="button" className={btn2} disabled={test.isPending} onClick={() => test.mutate()}>{test.isPending ? 'Testing…' : 'Test connection'}</button>}
          {row.subdomain && <button type="button" className={btn2} onClick={() => off.mutate()}>Disconnect</button>}
        </div>
      </form>
      {providers && <p className="text-xs text-gray-600">Providers found: {providers.map((p) => p.name).join(', ') || 'none'}.</p>}
    </div>
  );
}

function GoogleTools({ row, canEdit, onDone }: { row: Row; canEdit: boolean; onDone: () => void }) {
  const connected = row.state === 'working';
  const connect = useMutation({ mutationFn: growthApi.googleConnect, onSuccess: (r) => { window.location.href = r.url; }, onError: (e) => toast.error(apiErrorMessage(e)) });
  const locs = useQuery({ queryKey: ['gbp-locations'], queryFn: growthApi.googleLocations, enabled: connected && canEdit && !row.location, retry: false });
  const pick = useMutation({ mutationFn: (l: any) => growthApi.googleSelectLocation({ account: l.account, location: l.name, title: l.title }), onSuccess: () => { toast.success('Location saved.'); onDone(); }, onError: (e) => toast.error(apiErrorMessage(e)) });
  const reviews = useQuery({ queryKey: ['gbp-reviews'], queryFn: growthApi.googleReviews, enabled: connected && Boolean(row.location), retry: false });
  const [replying, setReplying] = useState<string | null>(null);
  const [text, setText] = useState('');
  const draft = useMutation({ mutationFn: (r: any) => growthApi.googleReviewDraft(r), onSuccess: (r) => setText(r.draft) });
  const reply = useMutation({ mutationFn: (name: string) => growthApi.googleReviewReply({ review: name, comment: text }), onSuccess: (r) => { toast.success(r.message); setReplying(null); reviews.refetch(); }, onError: (e) => toast.error(apiErrorMessage(e)) });
  const [post, setPost] = useState('');
  const publish = useMutation({ mutationFn: () => growthApi.googlePost({ summary: post }), onSuccess: (r) => { toast.success(r.message); setPost(''); }, onError: (e) => toast.error(apiErrorMessage(e)) });
  const off = useMutation({ mutationFn: growthApi.googleDisconnect, onSuccess: () => { toast.success('Disconnected from Google.'); onDone(); } });

  if (!connected) {
    return canEdit ? (
      <div className="mt-3"><button className={btn} disabled={!row.app_configured || connect.isPending} onClick={() => connect.mutate()}>Connect Google Business Profile</button></div>
    ) : null;
  }
  return (
    <div className="mt-3 space-y-4">
      {!row.location && canEdit && (
        <div>
          <p className="text-sm font-medium text-gray-800">Choose this practice's location</p>
          {locs.isLoading ? <p className="text-xs text-gray-500">Loading locations…</p> : locs.isError ? <p className="text-xs text-rose-700">{apiErrorMessage(locs.error)}</p> : (
            <ul className="mt-1 space-y-1">{(locs.data?.locations || []).map((l: any) => (
              <li key={l.name}><button className="text-sm text-teal-700 underline" onClick={() => pick.mutate(l)}>{l.title} <span className="text-gray-500">{l.address}</span></button></li>
            ))}</ul>
          )}
        </div>
      )}
      {row.location && (
        <div>
          <p className="text-sm font-medium text-gray-800">Recent reviews {reviews.data?.average_rating ? <span className="text-gray-500 font-normal">· {Number(reviews.data.average_rating).toFixed(1)} average from {reviews.data.total}</span> : null}</p>
          {reviews.isLoading ? <p className="text-xs text-gray-500">Loading reviews…</p> : reviews.isError ? <p className="text-xs text-rose-700">{apiErrorMessage(reviews.error)}</p> : (
            <ul className="mt-2 space-y-2">{(reviews.data?.reviews || []).slice(0, 10).map((r: any) => (
              <li key={r.name} className="border border-gray-100 rounded-lg p-3 text-sm">
                <div className="flex items-center gap-2"><span className="font-medium">{r.reviewer}</span><span className="inline-flex">{Array.from({ length: r.rating || 0 }).map((_, i) => <Star key={i} className="w-3.5 h-3.5 fill-amber-400 text-amber-400" />)}</span></div>
                {r.comment && <p className="text-gray-700 mt-1">{r.comment}</p>}
                {r.reply ? <p className="text-xs text-gray-500 mt-1">Your reply: {r.reply}</p> : replying === r.name ? (
                  <div className="mt-2 space-y-2">
                    <textarea className={input} rows={3} value={text} onChange={(e) => setText(e.target.value)} aria-label="Reply text" />
                    <p className="text-xs text-gray-500">Public reply. Do not confirm the reviewer is a patient or mention treatment.</p>
                    <div className="flex gap-2"><button className={btn} disabled={!text.trim() || reply.isPending} onClick={() => reply.mutate(r.name)}>Publish reply</button><button className={btn2} onClick={() => setReplying(null)}>Cancel</button></div>
                  </div>
                ) : <button className="text-xs text-teal-700 underline mt-1" onClick={() => { setReplying(r.name); setText(''); draft.mutate(r); }}>Draft a reply</button>}
              </li>
            ))}</ul>
          )}
        </div>
      )}
      {row.location && canEdit && (
        <div>
          <p className="text-sm font-medium text-gray-800">Post an update to your profile</p>
          <textarea className={`${input} mt-1`} rows={3} maxLength={1500} value={post} onChange={(e) => setPost(e.target.value)} placeholder="e.g. We're now open Saturday mornings for cleanings." aria-label="Profile update" />
          <button className={`${btn} mt-2`} disabled={!post.trim() || publish.isPending} onClick={() => publish.mutate()}>Publish update</button>
        </div>
      )}
      {canEdit && <button className={btn2} onClick={() => off.mutate()}>Disconnect Google</button>}
    </div>
  );
}

export default function IntegrationsPage() {
  const qc = useQueryClient();
  const user = useAuthStore((s) => s.user) as any;
  const canEdit = isAdminUser(user);
  const [params, setParams] = useSearchParams();
  const q = useQuery({ queryKey: ['integrations'], queryFn: growthApi.integrations });
  const [openKey, setOpenKey] = useState<string | null>(null);
  const refresh = () => { qc.invalidateQueries({ queryKey: ['integrations'] }); qc.invalidateQueries({ queryKey: ['gbp-locations'] }); };
  useEffect(() => {
    const g = params.get('google');
    if (!g) return;
    if (g === 'connected') toast.success('Google Business Profile connected.');
    else if (g === 'failed') toast.error('Google connection failed. Try again.');
    params.delete('google');
    setParams(params, { replace: true });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const rows: Row[] = q.data?.integrations || [];

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2"><Plug className="w-6 h-6 text-teal-600" /> Integrations</h1>
        <p className="text-gray-500 mt-1 text-sm">What is connected, what is working, and exactly what each connection still needs.</p>
      </div>
      {q.isLoading ? <div className="h-48 bg-gray-100 rounded-xl animate-pulse" /> : q.isError ? (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded-xl p-4 text-sm">{apiErrorMessage(q.error, 'Could not load integrations.')}</div>
      ) : SECTIONS.map(([cat, title]) => {
        const items = rows.filter((r) => r.category === cat);
        if (!items.length) return null;
        return (
          <section key={cat}>
            <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">{title}</h2>
            <div className="space-y-3">
              {items.map((r) => {
                const s = STATE[r.state] || STATE.not_connected;
                const configurable = canEdit && ['sms', 'nexhealth', 'google_business'].includes(r.key);
                const expanded = openKey === r.key || (r.key === 'google_business' && r.state === 'working');
                return (
                  <article key={r.key} className="bg-white border border-gray-200 rounded-xl p-4" data-testid={`integration-${r.key}`}>
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <h3 className="font-semibold text-gray-900">{r.name}</h3>
                        <p className="text-sm text-gray-600 mt-0.5">{r.detail}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-1 rounded-full border ${s.cls}`}><s.Icon className="w-3.5 h-3.5" />{s.label}</span>
                        {r.action && <Link to={r.action} className="inline-flex items-center gap-1 text-xs text-teal-700 underline"><ExternalLink className="w-3 h-3" />Open</Link>}
                      </div>
                    </div>
                    {r.requirements.length > 0 && r.state !== 'working' && (
                      <ul className="mt-2 text-xs text-gray-500 list-disc pl-4 space-y-0.5">{r.requirements.map((x) => <li key={x}>{x}</li>)}</ul>
                    )}
                    {configurable && r.key !== 'google_business' && (
                      <button className="mt-2 text-xs text-teal-700 underline" onClick={() => setOpenKey(openKey === r.key ? null : r.key)}>{openKey === r.key ? 'Hide settings' : 'Set up'}</button>
                    )}
                    {expanded && r.key === 'sms' && canEdit && <TwilioForm row={r} onDone={refresh} />}
                    {expanded && r.key === 'nexhealth' && canEdit && <NexHealthForm row={r} onDone={refresh} />}
                    {r.key === 'google_business' && <GoogleTools row={r} canEdit={canEdit} onDone={refresh} />}
                  </article>
                );
              })}
            </div>
          </section>
        );
      })}
      <p className="text-xs text-gray-500">Server-level settings (email provider, reply mailbox, scheduler secret, PageSpeed key, Google app credentials) are set by your HeyJarvis agency.</p>
    </div>
  );
}
