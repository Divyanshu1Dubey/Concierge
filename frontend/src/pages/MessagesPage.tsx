import { useState } from 'react';
import { Mail, Search, Inbox, Send, Filter, ArrowUpRight, ArrowDownRight } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/utils/api';

interface EmailMessage {
  id: number;
  direction: 'inbound' | 'outbound';
  subject: string;
  body: string;
  sender: string;
  recipient: string;
  status: string;
  sent_at: string;
  received_at: string;
  created_at: string;
}

export default function MessagesPage() {
  const [directionFilter, setDirectionFilter] = useState<'inbound' | 'outbound' | ''>('');
  const [search, setSearch] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['messages', directionFilter, search],
    queryFn: async () => {
      const params: Record<string, string> = {};
      if (directionFilter) params.direction = directionFilter;
      if (search) params.search = search;
      const response = await api.get('/emails/messages/', { params });
      return response.data;
    },
  });

  const emails: EmailMessage[] = data?.results ?? data ?? [];

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    if (date.toDateString() === now.toDateString()) {
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Messages</h1>
        <p className="text-gray-500 mt-1">Email communications with patients</p>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search messages..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent"
            />
          </div>
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-gray-400" />
            <select
              value={directionFilter}
              onChange={(e) => setDirectionFilter(e.target.value as 'inbound' | 'outbound' | '')}
              className="px-4 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent bg-white"
            >
              <option value="">All Messages</option>
              <option value="inbound">Inbound</option>
              <option value="outbound">Outbound</option>
            </select>
          </div>
        </div>
      </div>

      {/* Messages list */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {isLoading ? (
          <div className="p-8 text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-4 border-teal-200 border-t-teal-600 mx-auto" />
            <p className="text-sm text-gray-500 mt-2">Loading messages...</p>
          </div>
        ) : emails.length === 0 ? (
          <div className="p-12 text-center">
            <Mail className="w-12 h-12 text-gray-300 mx-auto mb-3" />
            <p className="text-gray-500 font-medium">No messages found</p>
            <p className="text-sm text-gray-400 mt-1">Email communications will appear here</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {emails.map((email) => (
              <div key={email.id} className="flex items-start gap-4 p-4 hover:bg-gray-50 cursor-pointer transition-colors">
                <div className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center ${email.direction === 'outbound' ? 'bg-blue-100' : 'bg-green-100'}`}>
                  {email.direction === 'outbound' ? (
                    <Send className="w-5 h-5 text-blue-600" />
                  ) : (
                    <Inbox className="w-5 h-5 text-green-600" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium text-gray-900 truncate">{email.subject || '(No subject)'}</p>
                    <span className="text-xs text-gray-400 flex-shrink-0 ml-2">{formatDate(email.sent_at || email.received_at || email.created_at)}</span>
                  </div>
                  <p className="text-sm text-gray-500 mt-1 line-clamp-2">{email.body?.slice(0, 200) || 'No content'}</p>
                  <div className="flex items-center gap-3 mt-2">
                    <span className={`inline-flex items-center gap-1 text-xs ${email.direction === 'outbound' ? 'text-blue-600' : 'text-green-600'}`}>
                      {email.direction === 'outbound' ? (
                        <><ArrowUpRight className="w-3 h-3" /> To: {email.recipient}</>
                      ) : (
                        <><ArrowDownRight className="w-3 h-3" /> From: {email.sender}</>
                      )}
                    </span>
                    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                      email.status === 'sent' ? 'bg-green-100 text-green-700' :
                      email.status === 'failed' ? 'bg-red-100 text-red-700' :
                      'bg-yellow-100 text-yellow-700'
                    }`}>
                      {email.status}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
