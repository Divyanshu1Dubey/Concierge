import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Inbox } from 'lucide-react';
import { practicesApi } from '@/services/api';
import { apiErrorMessage } from '@/utils/api';

interface AccessRequest {
  id: number;
  practice_name: string;
  contact_name: string;
  email: string;
  phone: string;
  website: string;
  message: string;
  status: 'new' | 'contacted' | 'onboarded' | 'declined';
  handled_by: string | null;
  created_at: string;
}

const STATUS_STYLE: Record<string, string> = {
  new: 'bg-amber-100 text-amber-800',
  contacted: 'bg-blue-100 text-blue-800',
  onboarded: 'bg-emerald-100 text-emerald-800',
  declined: 'bg-gray-100 text-gray-600',
};

/** Agency admins: onboarding requests submitted from the public "Request access" form. */
export default function AccessRequestsPanel({ onStartOnboarding }: { onStartOnboarding?: (r: AccessRequest) => void }) {
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: ['access-requests'],
    queryFn: () => practicesApi.listAccessRequests(),
  });
  const update = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) => practicesApi.updateAccessRequest(id, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['access-requests'] }),
    onError: (err) => toast.error(apiErrorMessage(err, 'Could not update the request.')),
  });

  const rows: AccessRequest[] = data?.results || [];
  const open = rows.filter((r) => r.status === 'new' || r.status === 'contacted');

  return (
    <section className="bg-white rounded-xl border border-gray-200 p-5" aria-labelledby="access-requests-title">
      <div className="flex items-center justify-between gap-3 mb-3">
        <h2 id="access-requests-title" className="text-base font-semibold text-gray-900 flex items-center gap-2">
          <Inbox className="w-4 h-4 text-teal-600" aria-hidden="true" /> Access requests
        </h2>
        <span className="text-xs text-gray-500">{open.length} open</span>
      </div>
      {isLoading ? (
        <p className="text-sm text-gray-500">Loading requests…</p>
      ) : isError ? (
        <p className="text-sm text-red-600">Could not load access requests.</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-gray-500">No requests yet. Practices can apply from the "Request access" link on the sign-in page.</p>
      ) : (
        <ul className="divide-y divide-gray-100">
          {rows.slice(0, 20).map((r) => (
            <li key={r.id} className="py-3 flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-gray-900">{r.practice_name}</p>
                <p className="text-xs text-gray-600 break-all">{r.contact_name} · {r.email}{r.phone ? ` · ${r.phone}` : ''}</p>
                {r.website && <p className="text-xs text-gray-500 break-all">{r.website}</p>}
                {r.message && <p className="text-xs text-gray-600 mt-1 whitespace-pre-wrap">{r.message}</p>}
                <p className="text-[11px] text-gray-400 mt-1">{new Date(r.created_at).toLocaleString()}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${STATUS_STYLE[r.status]}`}>{r.status}</span>
                <select
                  aria-label={`Status for ${r.practice_name}`}
                  value={r.status}
                  disabled={update.isPending}
                  onChange={(e) => update.mutate({ id: r.id, status: e.target.value })}
                  className="text-xs border border-gray-300 rounded-lg px-2 py-1"
                >
                  <option value="new">New</option>
                  <option value="contacted">Contacted</option>
                  <option value="onboarded">Onboarded</option>
                  <option value="declined">Declined</option>
                </select>
                {onStartOnboarding && r.status !== 'onboarded' && r.status !== 'declined' && (
                  <button type="button" onClick={() => onStartOnboarding(r)}
                    className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-teal-600 hover:bg-teal-700 text-white">
                    Start onboarding
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}