import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import {
  ListChecks, Send, Clock, Check, X, Sparkles, Mail, MessageSquare, Phone, ExternalLink, RotateCcw, Inbox,
} from 'lucide-react';
import { growthApi } from '@/services/growthApi';
import { apiErrorMessage } from '@/utils/api';
import { ago } from '@/utils/format';

interface Task {
  id: string; kind: string; kind_label: string; status: string; title: string; reason: string; channel: string;
  patient_name: string; patient_email: string; patient_phone: string; appointment_id: string | null;
  draft_subject: string; draft_body: string; draft_source: string; due_at: string; snoozed_until: string | null;
  completed_at: string | null; completed_by: string; result_note: string; is_outreach: boolean; can_send: boolean;
  priority?: { score: number; level: 'high' | 'normal' | 'low'; reasons: string[] };
  is_public_reply?: boolean;
}

const TABS = [
  { key: 'open', label: 'To do' },
  { key: 'snoozed', label: 'Snoozed' },
  { key: 'closed', label: 'Done' },
];
const KIND_STYLE: Record<string, string> = {
  waiting_reply: 'bg-amber-50 text-amber-800 border-amber-200',
  patient_replied: 'bg-orange-50 text-orange-800 border-orange-200',
  unconfirmed_offer: 'bg-sky-50 text-sky-800 border-sky-200',
  reschedule_requested: 'bg-violet-50 text-violet-800 border-violet-200',
  recall_due: 'bg-teal-50 text-teal-800 border-teal-200',
  reactivation: 'bg-teal-50 text-teal-800 border-teal-200',
  review_request: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  review_reply: 'bg-indigo-50 text-indigo-800 border-indigo-200',
  manual: 'bg-gray-50 text-gray-700 border-gray-200',
};
const input = 'w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500';


function TaskCard({ task, smsReady, onChanged }: { task: Task; smsReady: boolean; onChanged: () => void }) {
  const [subject, setSubject] = useState(task.draft_subject);
  const [body, setBody] = useState(task.draft_body);
  const [channel, setChannel] = useState(task.channel === 'phone' ? (task.patient_email ? 'email' : 'sms') : task.channel);
  const [open, setOpen] = useState(false);
  useEffect(() => { setSubject(task.draft_subject); setBody(task.draft_body); }, [task.draft_subject, task.draft_body]);
  const onError = (e: unknown) => toast.error(apiErrorMessage(e, 'That did not work. Please try again.'));

  const act = useMutation({
    mutationFn: (payload: Record<string, unknown>) => growthApi.updateFollowUp(task.id, payload),
    onSuccess: (_r, vars) => {
      const a = vars.action;
      toast.success(a === 'snooze' ? 'Snoozed until tomorrow.' : a === 'done' ? 'Marked done.' : a === 'dismiss' ? 'Dismissed.' : a === 'reopen' ? 'Moved back to the list.' : 'Draft saved.');
      onChanged();
    },
    onError,
  });
  const send = useMutation({
    mutationFn: () => growthApi.sendFollowUp(task.id, { subject, body, channel }),
    onSuccess: (r) => { toast.success(r.message || 'Sent.'); onChanged(); },
    onError,
  });
  const ai = useMutation({
    mutationFn: () => growthApi.aiDraft(task.id, { body }),
    onSuccess: (r) => { setBody(r.body); toast.success('Draft rewritten. Review it before sending.'); },
    onError,
  });

  const closed = !['open', 'snoozed'].includes(task.status);
  const canEmail = Boolean(task.patient_email);
  const canText = Boolean(task.patient_phone) && smsReady;
  const ChannelIcon = channel === 'sms' ? MessageSquare : Mail;
  const isPublic = Boolean(task.is_public_reply);

  return (
    <article className="bg-white border border-gray-200 rounded-xl p-4 shadow-sm" data-testid="follow-up">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`text-[11px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full border ${KIND_STYLE[task.kind] || KIND_STYLE.manual}`}>{task.kind_label}</span>
            {!closed && task.priority?.level === 'high' && (
              <span className="text-[11px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200"
                title={task.priority.reasons.join(', ')} data-testid="priority-high">Contact first</span>
            )}
            <span className="text-xs text-gray-500">{closed && task.completed_at ? `Closed ${ago(task.completed_at)}` : ago(task.due_at)}</span>
            {!closed && task.priority && task.priority.reasons.length > 0 && <span className="text-xs text-gray-500">· {task.priority.reasons.join(' · ')}</span>}
          </div>
          <h3 className="mt-1.5 font-semibold text-gray-900">{task.title}</h3>
          <p className="text-sm text-gray-600 mt-0.5">{task.reason}</p>
          <p className="text-xs text-gray-500 mt-1 flex flex-wrap gap-x-3 gap-y-1">
            {task.patient_email && <span className="inline-flex items-center gap-1"><Mail className="w-3 h-3" />{task.patient_email}</span>}
            {task.patient_phone && <a href={`tel:${task.patient_phone}`} className="inline-flex items-center gap-1 hover:text-teal-700"><Phone className="w-3 h-3" />{task.patient_phone}</a>}
          </p>
          {closed && task.result_note && <p className="text-xs text-gray-500 mt-1">{task.result_note}{task.completed_by ? ` · ${task.completed_by}` : ''}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          {task.appointment_id && (
            <Link to={`/dashboard/requests/${task.appointment_id}`} className="inline-flex items-center gap-1 px-3 py-1.5 border border-gray-200 rounded-lg text-xs font-medium hover:bg-gray-50">
              <ExternalLink className="w-3.5 h-3.5" /> Open request
            </Link>
          )}
          {!closed && task.can_send && (
            <button onClick={() => setOpen(!open)} className="inline-flex items-center gap-1 px-3 py-1.5 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-xs font-semibold">
              <Send className="w-3.5 h-3.5" /> {open ? 'Hide draft' : 'Review & send'}
            </button>
          )}
          {!closed && (
            <>
              <button onClick={() => act.mutate({ action: 'snooze', hours: 24 })} title="Snooze for a day" aria-label="Snooze for a day" className="p-1.5 border border-gray-200 rounded-lg hover:bg-gray-50"><Clock className="w-4 h-4 text-gray-600" /></button>
              <button onClick={() => act.mutate({ action: 'done' })} title="Mark done (handled another way)" aria-label="Mark done" className="p-1.5 border border-gray-200 rounded-lg hover:bg-gray-50"><Check className="w-4 h-4 text-emerald-600" /></button>
              <button onClick={() => act.mutate({ action: 'dismiss' })} title="Dismiss" aria-label="Dismiss" className="p-1.5 border border-gray-200 rounded-lg hover:bg-gray-50"><X className="w-4 h-4 text-gray-500" /></button>
            </>
          )}
          {closed && task.status !== 'sent' && (
            <button onClick={() => act.mutate({ action: 'reopen' })} className="inline-flex items-center gap-1 px-3 py-1.5 border border-gray-200 rounded-lg text-xs hover:bg-gray-50"><RotateCcw className="w-3.5 h-3.5" /> Reopen</button>
          )}
        </div>
      </div>

      {open && !closed && (
        <div className="mt-4 border-t border-gray-100 pt-4 space-y-3">
          {isPublic && (
            <p className="text-xs text-indigo-800 bg-indigo-50 rounded-lg px-3 py-2">
              This reply is public on Google. Do not confirm the reviewer is a patient and do not mention treatment or health details.
            </p>
          )}
          {!isPublic && <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="font-semibold text-gray-700">Send by</span>
            <button disabled={!canEmail} onClick={() => setChannel('email')} className={`px-2.5 py-1 rounded-full border ${channel === 'email' ? 'bg-teal-600 text-white border-teal-600' : 'border-gray-200 text-gray-600'} disabled:opacity-40`}>Email</button>
            <button disabled={!canText} onClick={() => setChannel('sms')} title={!smsReady ? 'Text messaging is not set up (Integrations)' : undefined}
              className={`px-2.5 py-1 rounded-full border ${channel === 'sms' ? 'bg-teal-600 text-white border-teal-600' : 'border-gray-200 text-gray-600'} disabled:opacity-40`}>Text message</button>
            {task.is_outreach && <span className="text-gray-500">An unsubscribe option is added automatically.</span>}
          </div>}
          {!isPublic && channel === 'email' && (
            <div>
              <label htmlFor={`subj-${task.id}`} className="text-xs font-semibold text-gray-700 block mb-1">Subject</label>
              <input id={`subj-${task.id}`} className={input} value={subject} maxLength={200} onChange={(e) => setSubject(e.target.value)} />
            </div>
          )}
          <div>
            <label htmlFor={`body-${task.id}`} className="text-xs font-semibold text-gray-700 block mb-1">Message</label>
            <textarea id={`body-${task.id}`} rows={channel === 'sms' ? 4 : 8} className={input} value={body}
              maxLength={channel === 'sms' ? 1000 : 5000} onChange={(e) => setBody(e.target.value)} />
            {task.kind === 'unconfirmed_offer' && channel === 'email' && (
              <p className="text-xs text-gray-500 mt-1">A fresh confirm / choose-another-time button is added below your message, and the old link stops working.</p>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={() => send.mutate()} disabled={send.isPending || !body.trim() || (!isPublic && channel === 'email' && !subject.trim())}
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-sm font-semibold disabled:opacity-50">
              <ChannelIcon className="w-4 h-4" /> {send.isPending ? 'Sending…' : isPublic ? 'Publish on Google' : `Send ${channel === 'sms' ? 'text' : 'email'}`}
            </button>
            {!isPublic && channel === 'email' && (
              <button onClick={() => ai.mutate()} disabled={ai.isPending} className="inline-flex items-center gap-1.5 px-3 py-2 border border-gray-200 rounded-lg text-sm hover:bg-gray-50 disabled:opacity-50">
                <Sparkles className="w-4 h-4 text-teal-600" /> {ai.isPending ? 'Rewriting…' : 'Improve with AI'}
              </button>
            )}
            <button onClick={() => act.mutate({ action: 'edit', draft_subject: subject, draft_body: body, channel })} className="px-3 py-2 border border-gray-200 rounded-lg text-sm hover:bg-gray-50">Save draft</button>
          </div>
        </div>
      )}
    </article>
  );
}

export default function FollowUpsPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState('open');
  const [kind, setKind] = useState('');
  const q = useQuery({
    queryKey: ['follow-ups', tab, kind],
    queryFn: () => growthApi.followUps({ status: tab, ...(kind ? { kind } : {}) }),
    refetchInterval: 60000,
  });
  const tasks: Task[] = q.data?.results || [];
  const counts = q.data?.counts || {};
  const smsReady = Boolean(q.data?.sms?.configured);
  const batchAllowed = q.data?.approval_policy === 'approve_batch';
  const refresh = () => qc.invalidateQueries({ queryKey: ['follow-ups'] });
  const batch = useMutation({
    mutationFn: () => growthApi.sendBatch(tasks.filter((t) => t.can_send && t.draft_body && t.channel !== 'phone').map((t) => t.id)),
    onSuccess: (r) => { toast.success(`${r.sent} message(s) sent.${r.failed?.length ? ` ${r.failed.length} need attention.` : ''}`); refresh(); },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });
  const kinds = Object.entries(counts.by_kind || {}).filter(([, n]) => (n as number) > 0);

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2"><ListChecks className="w-6 h-6 text-teal-600" /> Follow-ups</h1>
        <p className="text-gray-500 mt-1 text-sm">
          Patients who are waiting on your team. Replies are drafted for you; nothing is sent until you review it and press Send.
        </p>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex bg-gray-100 rounded-lg p-1" role="tablist">
          {TABS.map((t) => (
            <button key={t.key} role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}
              className={`px-3 py-1.5 rounded-md text-sm font-medium ${tab === t.key ? 'bg-white shadow-sm text-gray-900' : 'text-gray-600'}`}>
              {t.label}
              {t.key === 'open' && counts.open ? <span className="ml-1.5 text-xs bg-teal-600 text-white rounded-full px-1.5">{counts.open}</span> : null}
              {t.key === 'snoozed' && counts.snoozed ? <span className="ml-1.5 text-xs text-gray-500">{counts.snoozed}</span> : null}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          {tab === 'open' && kinds.length > 1 && (
            <select aria-label="Filter by type" value={kind} onChange={(e) => setKind(e.target.value)} className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm">
              <option value="">All types</option>
              {kinds.map(([k, n]) => <option key={k} value={k}>{tasks.find((t) => t.kind === k)?.kind_label || k.replace(/_/g, ' ')} ({n as number})</option>)}
            </select>
          )}
          {tab === 'open' && batchAllowed && tasks.length > 1 && (
            <button onClick={() => { if (window.confirm(`Send all ${tasks.length} drafted messages as they are?`)) batch.mutate(); }}
              className="px-3 py-1.5 border border-teal-600 text-teal-700 rounded-lg text-sm font-medium hover:bg-teal-50">Send all drafts</button>
          )}
        </div>
      </div>

      {q.isLoading ? (
        <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="h-24 bg-gray-100 rounded-xl animate-pulse" />)}</div>
      ) : q.isError ? (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded-xl p-4 text-sm">
          {apiErrorMessage(q.error, 'Could not load follow-ups.')} <button className="underline ml-1" onClick={() => q.refetch()}>Try again</button>
        </div>
      ) : tasks.length === 0 ? (
        <div className="text-center bg-white border border-dashed border-gray-300 rounded-xl py-12 px-6">
          <Inbox className="w-8 h-8 text-gray-300 mx-auto" />
          <p className="mt-3 font-semibold text-gray-800">{tab === 'open' ? 'Nobody is waiting on you right now.' : tab === 'snoozed' ? 'Nothing snoozed.' : 'No completed follow-ups yet.'}</p>
          {tab === 'open' && <p className="text-sm text-gray-500 mt-1">New requests appear here if they go unanswered, and when a patient has not confirmed a visit time.</p>}
        </div>
      ) : (
        <div className="space-y-3">
          {tasks.map((t) => <TaskCard key={t.id} task={t} smsReady={smsReady} onChanged={refresh} />)}
        </div>
      )}
      <p className="text-xs text-gray-500">
        Alert timing, confirmation reminders and outreach programs are set in <Link to="/dashboard/growth" className="underline">Growth</Link>.
      </p>
    </div>
  );
}
