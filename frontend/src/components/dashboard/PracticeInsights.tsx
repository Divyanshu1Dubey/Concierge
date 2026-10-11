import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { AlertCircle, CheckCircle2, Circle, ArrowRight } from 'lucide-react';
import { practicesApi } from '@/services/api';
import { growthApi } from '@/services/growthApi';

interface SetupItem { key: string; label: string; done: boolean; detail: string; link: string | null }
interface Insights {
  attention: {
    waiting_over_24h: number;
    waiting_examples: { id: string; name: string; hours_waiting: number }[];
    asked_for_new_time: number;
    failed_emails_7d: number;
    unanswered_questions: number;
  };
  setup: SetupItem[];
  setup_complete: boolean;
  results_30d: {
    inquiries: number;
    requests: number;
    after_hours_requests: number | null;
    replied: number;
    median_minutes_to_reply: number | null;
    patient_confirmations: number;
  };
}

function formatWait(minutes: number | null) {
  if (minutes === null) return '—';
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.round(minutes / 60);
  return hours < 48 ? `${hours} h` : `${Math.round(hours / 24)} days`;
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** "Needs attention", setup checklist and last-30-days results, all from real records. */
export default function PracticeInsights({ isAdmin }: { isAdmin: boolean }) {
  const { data, isLoading, isError } = useQuery<Insights>({
    queryKey: ['practice-insights'],
    queryFn: () => practicesApi.insights(),
    refetchInterval: 120000,
  });
  const followUps = useQuery({ queryKey: ['follow-ups', 'open', ''], queryFn: () => growthApi.followUps({ status: 'open' }), refetchInterval: 120000 });
  const openFollowUps: number = followUps.data?.counts?.open || 0;
  if (isLoading || isError || !data || !data.attention) return null;
  const a = data.attention;
  const r = data.results_30d;

  const items: { text: string; detail?: string; to: string; show: boolean }[] = [
    { show: openFollowUps > 0, text: `${plural(openFollowUps, 'follow-up is', 'follow-ups are')} ready, with replies drafted for you`, to: '/dashboard/follow-ups' },
    {
      show: a.waiting_over_24h > 0,
      text: `${plural(a.waiting_over_24h, 'request has', 'requests have')} waited over 24 hours without a reply`,
      detail: a.waiting_examples.map((e) => `${e.name} (${e.hours_waiting} h)`).join(', '),
      to: '/dashboard/requests',
    },
    { show: a.asked_for_new_time > 0, text: `${plural(a.asked_for_new_time, 'patient', 'patients')} asked for a different appointment time`, to: '/dashboard/requests' },
    { show: a.failed_emails_7d > 0, text: `${plural(a.failed_emails_7d, 'email', 'emails')} could not be sent this week`, to: '/dashboard/email' },
    { show: a.unanswered_questions > 0, text: `${plural(a.unanswered_questions, 'patient question needs', 'patient questions need')} an answer`, to: '/dashboard/knowledge' },
  ].filter((i) => i.show);

  const doneCount = data.setup.filter((s) => s.done).length;

  return (
    <div className="space-y-4">
      {/* Needs attention */}
      {items.length > 0 ? (
        <section className="rounded-2xl border border-amber-200 bg-amber-50/70 p-5" aria-labelledby="attention-title">
          <h2 id="attention-title" className="text-sm font-semibold text-amber-950 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-amber-700" aria-hidden="true" /> Needs attention
          </h2>
          <ul className="mt-3 space-y-2">
            {items.map((i) => (
              <li key={i.text}>
                <Link to={i.to} className="group flex items-start justify-between gap-3 rounded-xl bg-white/80 hover:bg-white border border-amber-100 px-3.5 py-2.5">
                  <span className="min-w-0">
                    <span className="block text-sm font-medium text-gray-900">{i.text}</span>
                    {i.detail && <span className="block text-xs text-gray-600 truncate">{i.detail}</span>}
                  </span>
                  <ArrowRight className="w-4 h-4 text-amber-700 mt-0.5 flex-shrink-0 group-hover:translate-x-0.5 transition" aria-hidden="true" />
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : (
        <p className="text-sm text-emerald-800 flex items-center gap-2" role="status">
          <CheckCircle2 className="w-4 h-4" aria-hidden="true" /> You're all caught up. No patient is waiting on the front desk.
        </p>
      )}

      {/* Setup checklist (admins, until complete) */}
      {isAdmin && !data.setup_complete && (
        <section className="rounded-2xl border border-gray-200 bg-white p-5" aria-labelledby="setup-title">
          <div className="flex items-center justify-between gap-2">
            <h2 id="setup-title" className="text-sm font-semibold text-gray-900">Finish setting up Concierge</h2>
            <span className="text-xs font-semibold text-gray-600">{doneCount} of {data.setup.length} done</span>
          </div>
          <div className="mt-2 h-1.5 rounded-full bg-gray-100 overflow-hidden" aria-hidden="true">
            <div className="h-full bg-teal-600 rounded-full" style={{ width: `${(doneCount / data.setup.length) * 100}%` }} />
          </div>
          <ul className="mt-3 divide-y divide-gray-100">
            {data.setup.map((s) => (
              <li key={s.key} className="py-2.5 flex items-start gap-3">
                {s.done
                  ? <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0" aria-label="Done" />
                  : <Circle className="w-5 h-5 text-gray-300 flex-shrink-0" aria-label="Not done" />}
                <div className="min-w-0 flex-1">
                  <p className={`text-sm font-medium ${s.done ? 'text-gray-500' : 'text-gray-900'}`}>{s.label}</p>
                  <p className="text-xs text-gray-500">{s.detail}</p>
                </div>
                {!s.done && s.link && (
                  <Link to={s.link} className="text-xs font-semibold text-teal-700 hover:text-teal-900 whitespace-nowrap">Set up</Link>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Last 30 days */}
      <section aria-labelledby="results-title">
        <h2 id="results-title" className="eyebrow text-gray-500 mb-3">Last 30 days</h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          {[
            { label: 'Website conversations', value: String(r.inquiries) },
            { label: 'Requests captured', value: String(r.requests) },
            { label: 'Came in after hours', value: r.after_hours_requests === null ? '—' : String(r.after_hours_requests), hint: r.after_hours_requests === null ? 'Set office hours to see this' : undefined },
            { label: 'Typical time to first reply', value: formatWait(r.median_minutes_to_reply), hint: r.replied ? `${plural(r.replied, 'request', 'requests')} replied` : 'No replies sent yet' },
            { label: 'Patients confirmed by email', value: String(r.patient_confirmations) },
          ].map((s) => (
            <div key={s.label} className="rounded-xl border border-gray-200 bg-white px-4 py-3">
              <p className="text-[22px] font-semibold text-gray-900 leading-tight">{s.value}</p>
              <p className="text-xs text-gray-600 mt-0.5">{s.label}</p>
              {s.hint && <p className="text-[11px] text-gray-500 mt-0.5">{s.hint}</p>}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}