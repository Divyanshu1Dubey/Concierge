import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { MessageSquare, Navigation } from 'lucide-react';
import { growthApi } from '@/services/growthApi';
import { apiErrorMessage } from '@/utils/api';

/** Where this request came from (recorded when the website chat started). */
export function RequestSource({ source }: { source?: any }) {
  if (!source) return null;
  const bits = [source.landing_path && `page ${source.landing_path}`, source.referrer_host && `from ${source.referrer_host}`,
    source.utm_campaign && `campaign "${source.utm_campaign}"`].filter(Boolean);
  return (
    <p className="text-xs text-gray-500 mt-1 flex items-center gap-1.5" data-testid="request-source">
      <Navigation className="w-3 h-3 text-teal-600" aria-hidden />
      <span>Source: <span className="font-medium text-gray-700">{source.channel_label}</span>{bits.length ? ` · ${bits.join(' · ')}` : ''}</span>
    </p>
  );
}

/** Text messages with this patient (only shown when SMS is set up or messages exist). */
export function TextMessagesCard({ requestId, phone }: { requestId: string; phone?: string }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['sms', requestId], queryFn: () => growthApi.sms(requestId) });
  const [body, setBody] = useState('');
  const send = useMutation({
    mutationFn: () => growthApi.sendSms({ appointment_id: requestId, body }),
    onSuccess: () => { toast.success('Text sent.'); setBody(''); qc.invalidateQueries({ queryKey: ['sms', requestId] }); },
    onError: (e) => toast.error(apiErrorMessage(e, 'The text could not be sent.')),
  });
  const status = q.data?.status;
  const messages = q.data?.results || [];
  if (!q.data || (!status?.configured && messages.length === 0)) return null;
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-3">
      <h3 className="text-sm font-semibold text-gray-900 border-b pb-2 flex items-center gap-2"><MessageSquare className="w-4 h-4 text-teal-600" /> Text messages</h3>
      {status?.mode === 'console' && <p className="text-xs text-sky-700 bg-sky-50 rounded px-2 py-1">Test mode: texts are recorded but not delivered.</p>}
      <div className="space-y-2 max-h-56 overflow-y-auto">
        {messages.length === 0 && <p className="text-xs text-gray-500">No texts yet.</p>}
        {[...messages].reverse().map((m: any) => (
          <div key={m.id} className={`text-sm rounded-lg px-3 py-2 max-w-[85%] ${m.direction === 'in' ? 'bg-gray-100 text-gray-800' : 'bg-teal-600 text-white ml-auto'}`}>
            <p className="whitespace-pre-wrap break-words">{m.body}</p>
            <p className={`text-[10px] mt-1 ${m.direction === 'in' ? 'text-gray-500' : 'text-teal-100'}`}>
              {new Date(m.created_at).toLocaleString()}{m.status === 'failed' ? ` · failed: ${m.error}` : m.sent_by ? ` · ${m.sent_by}` : ''}
            </p>
          </div>
        ))}
      </div>
      {status?.configured && (phone ? (
        <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); send.mutate(); }}>
          <label htmlFor="sms-body" className="sr-only">Text message</label>
          <textarea id="sms-body" rows={2} maxLength={1000} value={body} onChange={(e) => setBody(e.target.value)} placeholder={`Text ${phone}`}
            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] text-gray-500">{body.length}/1000 · patients can reply STOP to opt out</span>
            <button className="px-3 py-1.5 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-xs font-semibold disabled:opacity-50" disabled={!body.trim() || send.isPending}>{send.isPending ? 'Sending…' : 'Send text'}</button>
          </div>
        </form>
      ) : <p className="text-xs text-gray-500">No phone number on this request.</p>)}
      {!status?.configured && <p className="text-xs text-gray-500">Text messaging is off. <Link to="/dashboard/integrations" className="underline">Set it up</Link>.</p>}
    </div>
  );
}
