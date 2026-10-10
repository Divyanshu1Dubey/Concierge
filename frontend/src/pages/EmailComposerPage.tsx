import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { emailsApi } from '@/services/api';
import { Send, Search, ArrowUpRight, ArrowDownRight } from 'lucide-react';
import toast from 'react-hot-toast';
import { apiErrorMessage } from '@/utils/api';

interface EmailMessage {
  id: string;
  direction: 'incoming' | 'outgoing' | 'internal';
  subject: string;
  body: string;
  from_email: string;
  to_email: string;
  status: string;
  sent_at: string | null;
  created_at: string;
}

export default function EmailComposerPage() {
  const [selectedThread, setSelectedThread] = useState<string | null>(null);
  const [directionFilter, setDirectionFilter] = useState<string>('');
  const [search, setSearch] = useState('');
  const [composeOpen, setComposeOpen] = useState(false);
  const [toEmail, setToEmail] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const queryClient = useQueryClient();

  const { data: emails, isLoading, isError } = useQuery({
    queryKey: ['emails', directionFilter, search],
    queryFn: async () => {
      const params: Record<string, string> = {};
      if (directionFilter) params.direction = directionFilter;
      if (search) params.search = search;
      const response = await emailsApi.list(params);
      return response.results ?? response;
    },
  });

  const sendMutation = useMutation({
    mutationFn: (data: { to_email: string; subject: string; body: string }) =>
      emailsApi.send(data),
    onSuccess: (res: any) => {
      queryClient.invalidateQueries({ queryKey: ['emails'] });
      setComposeOpen(false);
      const recipient = toEmail;
      setToEmail('');
      setSubject('');
      setBody('');
      if (res?.delivery?.warning) {
        toast(res.message || `Email recorded for ${recipient}`, { icon: '⚠️', duration: 8000 });
      } else {
        toast.success(res?.message || `Email sent to ${recipient}`);
      }
    },
    onError: (err: any) => {
      queryClient.invalidateQueries({ queryKey: ['emails'] });
      toast.error(err?.response?.data?.message || apiErrorMessage(err, 'Failed to send email'));
    },
  });

  const handleSend = () => {
    if (!toEmail.trim() || !subject.trim() || !body.trim()) {
      toast.error('Recipient, subject and message are required.');
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(toEmail.trim())) {
      toast.error('Enter a valid recipient email.');
      return;
    }
    sendMutation.mutate({ to_email: toEmail, subject, body });
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Email</h1>
          <p className="text-sm text-gray-500 mt-1">Manage patient communications</p>
        </div>
        <button
          onClick={() => setComposeOpen(true)}
          className="inline-flex items-center gap-2 px-4 py-2 bg-teal-600 text-white rounded-lg hover:bg-teal-700 text-sm font-medium"
        >
          <Send className="w-4 h-4" />
          Compose
        </button>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4 bg-white rounded-xl p-4 border border-gray-200">
        <div className="flex-1 relative">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Search emails..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
          />
        </div>
        <select
          value={directionFilter}
          onChange={(e) => setDirectionFilter(e.target.value)}
          className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-teal-500"
        >
          <option value="">All</option>
          <option value="incoming">Incoming</option>
          <option value="outgoing">Outgoing</option>
        </select>
      </div>

      {/* Email List */}
      <div className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-100">
        {isLoading ? (
          <div className="p-8 text-center text-gray-500">Loading emails...</div>
        ) : isError ? (
          <div className="p-8 text-center text-red-600">Could not load emails.</div>
        ) : (emails as EmailMessage[] | undefined)?.length === 0 ? (
          <div className="p-8 text-center text-gray-500">No emails found</div>
        ) : (
          (emails as EmailMessage[] | undefined)?.map((email: EmailMessage) => (
            <div
              key={email.id}
              onClick={() => setSelectedThread(email.id.toString())}
              className={`p-4 hover:bg-gray-50 cursor-pointer transition-colors ${
                selectedThread === email.id.toString() ? 'bg-teal-50' : ''
              }`}
            >
              <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                <div className="flex items-center gap-3 min-w-0">
                  <div className={`w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center ${
                    email.direction === 'incoming' ? 'bg-blue-100' : 'bg-teal-100'
                  }`}>
                    {email.direction === 'incoming' ? (
                      <ArrowDownRight className="w-4 h-4 text-blue-600" />
                    ) : (
                      <ArrowUpRight className="w-4 h-4 text-teal-600" />
                    )}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-900 break-all">
                      {email.direction === 'incoming' ? email.from_email : email.to_email}
                    </p>
                    <p className="text-sm text-gray-600">{email.subject}</p>
                    <p className={`text-xs text-gray-500 mt-1 whitespace-pre-wrap ${selectedThread === email.id.toString() ? '' : 'line-clamp-1'}`}>{email.body}</p>
                  </div>
                </div>
                <span className="text-xs text-gray-400 flex-shrink-0 text-right ml-auto">
                  {new Date(email.created_at).toLocaleString()}
                  <span className={`block mt-1 font-semibold uppercase ${email.status === 'failed' ? 'text-red-600' : email.status === 'sent' ? 'text-emerald-600' : 'text-gray-400'}`}>
                    {email.status}
                  </span>
                </span>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Compose Modal */}
      {composeOpen && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between p-4 border-b border-gray-200">
              <h3 className="text-lg font-semibold">Compose Email</h3>
              <button onClick={() => setComposeOpen(false)} className="text-gray-400 hover:text-gray-600">X</button>
            </div>
            <div className="p-4 space-y-4 flex-1 overflow-y-auto">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">To</label>
                <input
                  type="email"
                  value={toEmail}
                  onChange={(e) => setToEmail(e.target.value)}
                  placeholder="patient@email.com"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-teal-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Subject</label>
                <input
                  type="text"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  placeholder="Subject"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-teal-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Message</label>
                <textarea
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  rows={8}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-teal-500 resize-none"
                />
              </div>
            </div>
            <div className="flex justify-end gap-3 p-4 border-t border-gray-200">
              <button
                onClick={() => setComposeOpen(false)}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800"
              >
                Cancel
              </button>
              <button
                onClick={handleSend}
                disabled={sendMutation.isPending || !toEmail.trim() || !subject.trim() || !body.trim()}
                className="inline-flex items-center gap-2 px-4 py-2 bg-teal-600 text-white rounded-lg hover:bg-teal-700 text-sm font-medium disabled:opacity-50"
              >
                <Send className="w-4 h-4" />
                {sendMutation.isPending ? 'Sending...' : 'Send'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
