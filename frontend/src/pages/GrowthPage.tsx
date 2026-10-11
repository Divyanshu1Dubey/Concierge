import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { TrendingUp, Mail, Settings2, Info, ArrowRight } from 'lucide-react';
import { growthApi, isAdminUser } from '@/services/growthApi';
import { apiErrorMessage } from '@/utils/api';
import { fmtMinutes } from '@/utils/format';
import { useAuthStore } from '@/stores/authStore';

const input = 'w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 disabled:bg-gray-50';
const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];


function Stat({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4">
      <div className="text-2xl font-bold text-gray-900 tabular-nums">{value}</div>
      <div className="text-xs text-gray-500 mt-0.5">{label}</div>
      {sub && <div className="text-xs text-gray-500 mt-1">{sub}</div>}
    </div>
  );
}

function Funnel({ f }: { f: any }) {
  const steps = [
    { label: 'Website chats', value: f.conversations },
    { label: 'Chats where the patient wrote', value: f.engaged_conversations },
    { label: 'Appointment requests', value: f.requests },
    { label: 'Contacted by your team', value: f.contacted },
    { label: 'Visit time offered', value: f.offered_time },
    { label: 'Confirmed', value: f.confirmed },
  ];
  const max = Math.max(1, ...steps.map((s) => s.value || 0));
  return (
    <div className="space-y-2">
      {steps.map((s) => (
        <div key={s.label} className="grid grid-cols-[minmax(0,180px)_1fr_48px] items-center gap-3 text-sm">
          <span className="text-gray-600 truncate">{s.label}</span>
          <div className="h-3 bg-gray-100 rounded-full overflow-hidden" aria-hidden>
            <div className="h-full bg-teal-500 rounded-full" style={{ width: `${Math.max(2, (100 * (s.value || 0)) / max)}%` }} />
          </div>
          <span className="text-right font-semibold tabular-nums text-gray-900">{s.value}</span>
        </div>
      ))}
    </div>
  );
}

function SettingsCard({ canEdit }: { canEdit: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['growth-settings'], queryFn: growthApi.settings });
  const [v, setV] = useState<any>(null);
  const [ack, setAck] = useState(false);
  useEffect(() => { if (q.data) setV({ ...q.data, briefing_recipients: (q.data.briefing_recipients || []).join(', ') }); }, [q.data]);
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => growthApi.updateSettings(body),
    onSuccess: () => { toast.success('Settings saved.'); qc.invalidateQueries({ queryKey: ['growth-settings'] }); },
    onError: (e) => toast.error(apiErrorMessage(e, 'Could not save settings.')),
  });
  if (!v) return <div className="h-40 bg-gray-100 rounded-xl animate-pulse" />;
  const set = (k: string, val: unknown) => setV({ ...v, [k]: val });
  const outreachOn = v.recall_enabled || v.reactivation_enabled || v.review_requests_enabled;
  const needsAck = outreachOn && !v.outreach_acknowledged;
  const toggle = (k: string, labelText: string, help?: string) => (
    <label className="flex items-start gap-3 py-2">
      <input type="checkbox" className="mt-1 h-4 w-4 accent-teal-600" checked={!!v[k]} disabled={!canEdit} onChange={(e) => set(k, e.target.checked)} />
      <span><span className="text-sm font-medium text-gray-800">{labelText}</span>{help && <span className="block text-xs text-gray-500">{help}</span>}</span>
    </label>
  );

  return (
    <form className="bg-white border border-gray-200 rounded-xl p-5 space-y-5" onSubmit={(e) => {
      e.preventDefault();
      const body: Record<string, unknown> = { ...v, briefing_recipients: v.briefing_recipients };
      delete body.outreach_acknowledged; delete body.outreach_acknowledged_at; delete body.briefing_weekday_label;
      if (ack) body.acknowledge_outreach = true;
      save.mutate(body);
    }}>
      <h2 className="font-semibold text-gray-900 flex items-center gap-2"><Settings2 className="w-4 h-4 text-teal-600" /> Growth settings</h2>
      {!canEdit && <p className="text-xs text-gray-500">Only a practice admin can change these.</p>}

      <section>
        <h3 className="text-sm font-semibold text-gray-800">Follow-up alerts</h3>
        {toggle('waiting_alerts_enabled', 'Alert the front desk when a request goes unanswered')}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pl-7">
          <label className="text-xs text-gray-600">After how many hours
            <input type="number" min={1} max={168} className={input} disabled={!canEdit} value={v.waiting_alert_hours} onChange={(e) => set('waiting_alert_hours', e.target.value)} />
          </label>
        </div>
        {toggle('confirmation_nudges_enabled', 'Remind us when a patient has not confirmed a visit time')}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pl-7">
          <label className="text-xs text-gray-600">After how many hours
            <input type="number" min={2} max={168} className={input} disabled={!canEdit} value={v.confirmation_nudge_hours} onChange={(e) => set('confirmation_nudge_hours', e.target.value)} />
          </label>
          <label className="text-xs text-gray-600">Sending drafted messages
            <select className={input} disabled={!canEdit} value={v.approval_policy} onChange={(e) => set('approval_policy', e.target.value)}>
              <option value="approve_each">Review and send each one</option>
              <option value="approve_batch">Allow "send all drafts" after review</option>
            </select>
          </label>
        </div>
      </section>

      <section>
        <h3 className="text-sm font-semibold text-gray-800">Weekly briefing email</h3>
        {toggle('briefing_enabled', 'Email a short weekly summary to the practice team')}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pl-7">
          <label className="text-xs text-gray-600">Day
            <select className={input} disabled={!canEdit} value={v.briefing_weekday} onChange={(e) => set('briefing_weekday', Number(e.target.value))}>
              {WEEKDAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}
            </select>
          </label>
          <label className="text-xs text-gray-600">Hour (practice time)
            <input type="number" min={0} max={23} className={input} disabled={!canEdit} value={v.briefing_hour} onChange={(e) => set('briefing_hour', e.target.value)} />
          </label>
          <label className="text-xs text-gray-600 sm:col-span-3">Send to (leave empty for practice admins)
            <input className={input} disabled={!canEdit} placeholder="doctor@practice.com, manager@practice.com" value={v.briefing_recipients} onChange={(e) => set('briefing_recipients', e.target.value)} />
          </label>
        </div>
      </section>

      <section>
        <h3 className="text-sm font-semibold text-gray-800">Patient outreach (off by default)</h3>
        <p className="text-xs text-gray-500">HeyJarvis drafts these messages in Follow-ups. Your team still reviews and sends each one, and every message lets the patient opt out.</p>
        {toggle('recall_enabled', 'Recall reminders', 'Patients on your recall list whose next routine visit is due.')}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pl-7">
          <label className="text-xs text-gray-600">Months between routine visits
            <input type="number" min={1} max={24} className={input} disabled={!canEdit} value={v.recall_interval_months} onChange={(e) => set('recall_interval_months', e.target.value)} />
          </label>
        </div>
        {toggle('reactivation_enabled', 'Reactivation', 'Patients who agreed to hear from you and have not visited in a long time.')}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pl-7">
          <label className="text-xs text-gray-600">Not seen for (months)
            <input type="number" min={6} max={60} className={input} disabled={!canEdit} value={v.reactivation_after_months} onChange={(e) => set('reactivation_after_months', e.target.value)} />
          </label>
        </div>
        {toggle('review_requests_enabled', 'Review requests', 'Every patient with a completed visit is asked the same way, at most once a year.')}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pl-7">
          <label className="text-xs text-gray-600 sm:col-span-2">Your Google review link
            <input className={input} disabled={!canEdit} placeholder="https://g.page/r/.../review" value={v.review_link} onChange={(e) => set('review_link', e.target.value)} />
          </label>
        </div>
        {needsAck && (
          <label className="mt-3 flex items-start gap-3 bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-900">
            <input type="checkbox" className="mt-0.5 h-4 w-4 accent-teal-600" checked={ack} onChange={(e) => setAck(e.target.checked)} disabled={!canEdit} />
            <span>
              I confirm our practice is responsible for patient outreach: we follow our privacy and patient-communication obligations
              (some messages may count as marketing and need patient permission), we never ask only happy patients for reviews, and we honour every opt-out.
              HeyJarvis does not provide legal advice.
            </span>
          </label>
        )}
        {v.outreach_acknowledged && <p className="text-xs text-gray-500 mt-2">Outreach notice accepted {new Date(v.outreach_acknowledged_at).toLocaleDateString()}.</p>}
      </section>

      <section>
        <h3 className="text-sm font-semibold text-gray-800">Value estimate (optional)</h3>
        <label className="text-xs text-gray-600 block max-w-xs">Average value of a completed visit ($)
          <input type="number" min={0} step="1" className={input} disabled={!canEdit} value={v.average_visit_value ?? ''} onChange={(e) => set('average_visit_value', e.target.value)} />
        </label>
        <p className="text-xs text-gray-500 mt-1">Used only to show a clearly labelled estimate. Leave empty to hide it.</p>
      </section>

      {canEdit && (
        <button type="submit" disabled={save.isPending || (needsAck && !ack)} className="px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-sm font-semibold disabled:opacity-50">
          {save.isPending ? 'Saving…' : 'Save settings'}
        </button>
      )}
    </form>
  );
}

export default function GrowthPage() {
  const user = useAuthStore((s) => s.user) as any;
  const canEdit = isAdminUser(user);
  const [days, setDays] = useState(30);
  const a = useQuery({ queryKey: ['growth-analytics', days], queryFn: () => growthApi.analytics(days) });
  const b = useQuery({ queryKey: ['growth-briefing'], queryFn: growthApi.briefing });
  const qc = useQueryClient();
  const sendNow = useMutation({
    mutationFn: growthApi.sendBriefing,
    onSuccess: (r) => { toast.success(r.message); qc.invalidateQueries({ queryKey: ['growth-briefing'] }); },
    onError: (e) => toast.error(apiErrorMessage(e, 'Could not send the briefing.')),
  });
  const d = a.data;
  const f = d?.funnel;
  const brief = b.data?.briefing;

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2"><TrendingUp className="w-6 h-6 text-teal-600" /> Growth</h1>
          <p className="text-gray-500 mt-1 text-sm">How website visitors become confirmed visits, from what HeyJarvis has recorded.</p>
        </div>
        <div className="inline-flex bg-gray-100 rounded-lg p-1" role="tablist" aria-label="Period">
          {[7, 30, 90].map((n) => (
            <button key={n} role="tab" aria-selected={days === n} onClick={() => setDays(n)}
              className={`px-3 py-1.5 rounded-md text-sm font-medium ${days === n ? 'bg-white shadow-sm text-gray-900' : 'text-gray-600'}`}>{n} days</button>
          ))}
        </div>
      </div>

      {a.isLoading ? <div className="h-48 bg-gray-100 rounded-xl animate-pulse" /> : a.isError ? (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded-xl p-4 text-sm">{apiErrorMessage(a.error, 'Could not load analytics.')}</div>
      ) : f && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <Stat label="Appointment requests" value={f.requests} sub={d.previous ? `${d.previous.requests} in the previous ${days} days` : undefined} />
            <Stat label="Confirmed visits" value={f.confirmed} sub={f.confirm_rate !== null ? `${f.confirm_rate}% of requests` : undefined} />
            <Stat label="Typical first reply" value={fmtMinutes(f.median_first_reply_minutes)} sub={f.replied_within_1h !== null ? `${f.replied_within_1h}% answered within an hour` : 'No replies recorded yet'} />
            <Stat label="Requests while closed" value={f.after_hours_requests ?? '–'} sub={f.after_hours_requests === null ? 'Set office hours to measure this' : 'outside office hours'} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <section className="bg-white border border-gray-200 rounded-xl p-5 min-w-0">
              <h2 className="font-semibold text-gray-900 mb-4">Conversion funnel</h2>
              <Funnel f={f} />
            </section>
            <section className="bg-white border border-gray-200 rounded-xl p-5 min-w-0">
              <h2 className="font-semibold text-gray-900 mb-3">Where requests come from</h2>
              {d.channels.length === 0 ? <p className="text-sm text-gray-500">No website chats in this period.</p> : (
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-xs text-gray-500"><th className="py-1 font-medium">Source</th><th className="py-1 font-medium text-right">Chats</th><th className="py-1 font-medium text-right">Requests</th><th className="py-1 font-medium text-right">Confirmed</th></tr></thead>
                  <tbody>
                    {d.channels.map((c: any) => (
                      <tr key={c.channel} className="border-t border-gray-100"><td className="py-1.5 text-gray-700">{c.label}</td>
                        <td className="py-1.5 text-right tabular-nums">{c.conversations}</td><td className="py-1.5 text-right tabular-nums">{c.requests}</td><td className="py-1.5 text-right tabular-nums">{c.confirmed}</td></tr>
                    ))}
                  </tbody>
                </table>
              )}
              {d.top_pages.length > 0 && (
                <div className="mt-4">
                  <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Pages where chats started</h3>
                  <ul className="mt-1 text-sm text-gray-700 space-y-0.5">{d.top_pages.map((p: any) => <li key={p.path} className="flex justify-between gap-2"><span className="truncate">{p.path}</span><span className="tabular-nums text-gray-500">{p.conversations}</span></li>)}</ul>
                </div>
              )}
              {d.campaigns.length > 0 && (
                <div className="mt-4">
                  <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Tagged campaigns</h3>
                  <ul className="mt-1 text-sm text-gray-700 space-y-0.5">{d.campaigns.map((c: any) => <li key={c.source + c.campaign} className="flex justify-between gap-2"><span className="truncate">{c.campaign} <span className="text-gray-400">({c.source})</span></span><span className="tabular-nums text-gray-500">{c.conversations}</span></li>)}</ul>
                </div>
              )}
            </section>
          </div>

          <section className="bg-white border border-gray-200 rounded-xl p-5 min-w-0">
            <h2 className="font-semibold text-gray-900 mb-3">Last 8 weeks</h2>
            <div className="flex items-end gap-2 h-32" aria-label="Weekly requests and confirmed visits">
              {d.trend.map((w: any) => {
                const max = Math.max(1, ...d.trend.map((x: any) => x.requests));
                return (
                  <div key={w.week_ending} className="flex-1 flex flex-col items-center gap-1 min-w-0" title={`Week ending ${w.week_ending}: ${w.requests} requests, ${w.confirmed} confirmed`}>
                    <div className="w-full h-24 flex items-end gap-0.5">
                      <div className="flex-1 bg-teal-200 rounded-t" style={{ height: `${(100 * w.requests) / max}%` }} />
                      <div className="flex-1 bg-teal-600 rounded-t" style={{ height: `${(100 * w.confirmed) / max}%` }} />
                    </div>
                    <span className="text-[10px] text-gray-500">{w.week_ending.slice(5)}</span>
                  </div>
                );
              })}
            </div>
            <p className="text-xs text-gray-500 mt-2"><span className="inline-block w-2.5 h-2.5 bg-teal-200 rounded-sm align-middle" /> requests &nbsp; <span className="inline-block w-2.5 h-2.5 bg-teal-600 rounded-sm align-middle" /> confirmed</p>
          </section>

          {d.value_estimate && (
            <p className="text-sm text-gray-700 bg-teal-50 border border-teal-100 rounded-lg p-3">
              Estimated value of completed visits: <strong>${d.value_estimate.estimated_value.toLocaleString()}</strong>. <span className="text-gray-500">{d.value_estimate.note}</span>
            </p>
          )}
          <div className="flex items-start gap-2 text-xs text-gray-500"><Info className="w-4 h-4 shrink-0" /><span>Not included: {d.unavailable.join(' ')}</span></div>
        </>
      )}

      <section className="bg-white border border-gray-200 rounded-xl p-5 min-w-0">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-semibold text-gray-900 flex items-center gap-2"><Mail className="w-4 h-4 text-teal-600" /> This week's briefing</h2>
          {canEdit && <button onClick={() => sendNow.mutate()} disabled={sendNow.isPending} className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm hover:bg-gray-50 disabled:opacity-50">{sendNow.isPending ? 'Sending…' : 'Send it now'}</button>}
        </div>
        {b.isLoading ? <div className="h-20 bg-gray-100 rounded-lg animate-pulse mt-3" /> : brief && (
          <div className="mt-3 text-sm text-gray-700 space-y-3">
            <p className="text-gray-500 text-xs">Preview of what {b.data.recipients.join(', ') || 'practice admins'} will receive. Covers {brief.period_start} to {brief.period_end}.</p>
            <p>{brief.numbers.requests} request{brief.numbers.requests === 1 ? '' : 's'}, {brief.numbers.confirmed} confirmed, {brief.waiting.open_follow_ups} follow-up{brief.waiting.open_follow_ups === 1 ? '' : 's'} open, {brief.waiting.unanswered_questions} unanswered patient question{brief.waiting.unanswered_questions === 1 ? '' : 's'}.</p>
            {brief.recommendations.length > 0 && (
              <ul className="space-y-2">{brief.recommendations.map((r: any) => (
                <li key={r.text} className="flex items-start gap-2 bg-teal-50 rounded-lg p-3"><ArrowRight className="w-4 h-4 text-teal-700 mt-0.5 shrink-0" /><span>{r.text}</span></li>
              ))}</ul>
            )}
            {b.data.history.length > 0 && <p className="text-xs text-gray-500">Last sent: week of {b.data.history[0].week_start} ({b.data.history[0].status}).</p>}
          </div>
        )}
      </section>

      <SettingsCard canEdit={canEdit} />
      <p className="text-xs text-gray-500">See who is waiting in <Link className="underline" to="/dashboard/follow-ups">Follow-ups</Link>.</p>
    </div>
  );
}
