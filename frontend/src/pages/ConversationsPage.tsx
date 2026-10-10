import { useEffect, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { conversationsApi } from '@/services/api';
import { apiErrorMessage } from '@/utils/api';
import {
  MessageSquare,
  Search,
  Mail,
  Clock,
  FileText,
  Send,
  Phone,
  Sparkles,
  RefreshCw,
  ArrowLeft,
} from 'lucide-react';
import toast from 'react-hot-toast';

export default function ConversationsPage() {
  const [search, setSearch] = useState('');
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [replyText, setReplyText] = useState('');
  // Below the md breakpoint only one pane fits: the inbox list or the open thread.
  const [mobileView, setMobileView] = useState<'list' | 'thread'>('list');

  const queryClient = useQueryClient();

  // Debounce the search box so we query the server (which searches all pages), not just page 1.
  const [debouncedSearch, setDebouncedSearch] = useState('');
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search.trim()), 300);
    return () => clearTimeout(t);
  }, [search]);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['conversations', filterStatus, debouncedSearch],
    queryFn: () =>
      conversationsApi.list({
        ...(filterStatus !== 'all' ? { status: filterStatus } : {}),
        ...(debouncedSearch ? { search: debouncedSearch } : {}),
      }),
  });
  const { data: stats } = useQuery({
    queryKey: ['conversations-stats'],
    queryFn: () => conversationsApi.stats(),
  });

  const rawList = data?.results ?? data;
  const conversations: any[] = Array.isArray(rawList) ? rawList : [];
  const filtered = conversations;

  // Select the active conversation (or auto-select first if none selected)
  const selectedConversation =
    conversations.find((c: any) => String(c.id) === String(selectedId)) ||
    (filtered.length > 0 && selectedId === null ? filtered[0] : null);

  // Send message mutation
  const sendReplyMutation = useMutation({
    mutationFn: ({ message, convId }: { message: string; convId: string }) => conversationsApi.reply(convId, message),
    onSuccess: (res: any) => {
      const delivery = res?.delivery || {};
      if (delivery.channel === 'email' && !delivery.warning) {
        toast.success('Reply emailed to the patient');
      } else {
        toast(delivery.warning || 'Reply saved to the conversation', { icon: '⚠️', duration: 7000 });
      }
      setReplyText('');
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
    },
    onError: (err: any) => {
      // 502 = message saved but email delivery failed
      if (err?.response?.status === 502) {
        toast.error('Reply saved, but the email could not be delivered. Check Email Settings.');
        queryClient.invalidateQueries({ queryKey: ['conversations'] });
        return;
      }
      toast.error(apiErrorMessage(err, 'Failed to send message'));
    },
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'close' | 'escalate' }) =>
      action === 'close' ? conversationsApi.close(id) : conversationsApi.escalate(id),
    onSuccess: (_res, vars) => {
      toast.success(vars.action === 'close' ? 'Conversation closed' : 'Escalated to staff handoff');
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
      queryClient.invalidateQueries({ queryKey: ['conversations-stats'] });
    },
    onError: (err) => toast.error(apiErrorMessage(err, 'Could not update conversation.')),
  });

  const handleSend = () => {
    if (!replyText.trim() || !selectedConversation) return;
    sendReplyMutation.mutate({
      message: replyText.trim(),
      convId: String(selectedConversation.id),
    });
  };

  const applyAIDraft = (template: string) => {
    const patientName = selectedConversation?.patient_name || 'there';
    switch (template) {
      case 'offer_time':
        setReplyText(
          `Hi ${patientName}, which days and times work best for you? Our front desk will check the schedule and reply with available openings.`
        );
        break;
      case 'confirm':
        setReplyText(
          `Hi ${patientName}, thank you for reaching out! We have received your request and our front desk will contact you shortly to confirm a time.`
        );
        break;
      case 'greeting':
      default:
        setReplyText(
          `Hi ${patientName}, thank you for reaching out to our office! How can our front desk assist you with your dental care today?`
        );
        break;
    }
  };

  const getStatusBadge = (status: string) => {
    const styles: Record<string, string> = {
      active: 'bg-emerald-100 text-emerald-700',
      handoff: 'bg-red-100 text-red-700',
      completed: 'bg-blue-100 text-blue-700',
      abandoned: 'bg-gray-100 text-gray-500',
      closed: 'bg-gray-100 text-gray-600',
    };
    return styles[status] || 'bg-gray-100 text-gray-700';
  };

  return (
    <div className="h-[calc(100vh-7rem)] flex flex-col -mx-4 -mt-4 sm:-mx-6 sm:-mt-6 lg:-mx-8 lg:-mt-8 bg-white border border-gray-200 rounded-2xl overflow-hidden shadow-sm">
      {/* Top Bar with Metrics */}
      <div className="h-14 bg-white border-b border-gray-200 px-6 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-3 sm:gap-6 min-w-0 overflow-x-auto">
          <div className="flex items-center gap-2 flex-shrink-0">
            <span className="text-sm font-semibold text-gray-900"><span className="hidden sm:inline">Total conversations</span><span className="sm:hidden">Total</span></span>
            <span className="text-sm font-semibold text-teal-600">{stats?.total ?? data?.count ?? conversations.length}</span>
          </div>
          <div className="flex items-center gap-2 text-emerald-600">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-xs font-semibold">
              {stats?.active ?? 0} Active
            </span>
          </div>
          <div className="flex items-center gap-2 text-amber-600">
            <Clock className="w-3.5 h-3.5" />
            <span className="text-xs font-semibold">
              {(stats?.handoff ?? 0)} Handoff · {(stats?.urgent ?? 0)} Urgent
            </span>
          </div>
        </div>

        <button
          onClick={() => refetch()}
          className="p-1.5 hover:bg-gray-100 rounded-lg text-gray-500 transition"
          title="Refresh inbox"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 flex overflow-hidden">
        {/* LEFT PANE: Inbox List */}
        <div className={`w-full md:w-80 lg:w-96 bg-white border-r border-gray-200 flex-col flex-shrink-0 ${mobileView === 'thread' ? 'hidden md:flex' : 'flex'}`}>
          <div className="p-4 border-b border-gray-200 space-y-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                placeholder="Search patient, message..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full pl-9 pr-4 py-2 bg-gray-50 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 focus:bg-white transition-colors"
              />
            </div>

            {/* Status Filter Chips */}
            <div className="flex gap-1.5 overflow-x-auto pb-1 scrollbar-hide">
              {['all', 'active', 'handoff', 'completed', 'closed'].map((st) => (
                <button
                  key={st}
                  onClick={() => setFilterStatus(st)}
                  className={`px-3 py-1 rounded-full text-xs font-medium capitalize whitespace-nowrap transition-colors ${
                    filterStatus === st
                      ? 'bg-teal-600 text-white font-bold'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                >
                  {st}
                </button>
              ))}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto divide-y divide-gray-100">
            {isLoading ? (
              <div className="p-8 text-center text-gray-500 text-sm">Loading conversations...</div>
            ) : isError ? (
              <div className="p-8 text-center text-red-600 text-sm">Could not load conversations.</div>
            ) : filtered.length === 0 ? (
              <div className="p-8 text-center text-gray-500 text-sm">
                <MessageSquare className="w-8 h-8 text-gray-300 mx-auto mb-2" />
                No conversations found
              </div>
            ) : (
              filtered.map((conv: any) => {
                const isSelected = selectedConversation && String(selectedConversation.id) === String(conv.id);
                const lastMsg =
                  conv.messages && conv.messages.length > 0
                    ? conv.messages[conv.messages.length - 1]?.content
                    : 'Patient started conversation...';

                return (
                  <button
                    key={conv.id}
                    onClick={() => {
                      setSelectedId(String(conv.id));
                      setMobileView('thread');
                    }}
                    className={`w-full text-left p-4 hover:bg-gray-50/80 transition-colors ${
                      isSelected
                        ? 'bg-teal-50/60 border-l-4 border-teal-600'
                        : 'border-l-4 border-transparent'
                    }`}
                  >
                    <div className="flex items-start justify-between mb-1">
                      <span className="text-sm font-bold text-gray-900 truncate pr-2">
                        {conv.patient_name || conv.patient_email || 'Guest Patient'}
                      </span>
                      <span className="text-[11px] text-gray-400 flex-shrink-0">
                        {conv.last_activity_at
                          ? new Date(conv.last_activity_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                          : 'Live'}
                      </span>
                    </div>

                    <div className="flex items-center gap-2 mb-2">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${getStatusBadge(
                          conv.status || 'active'
                        )}`}
                      >
                        {conv.status || 'Active'}
                      </span>
                      {conv.intent && (
                        <span className="text-[10px] px-1.5 py-0.2 rounded bg-purple-50 text-purple-700 font-medium">
                          {conv.intent}
                        </span>
                      )}
                    </div>

                    <p className="text-xs text-gray-500 line-clamp-2 leading-relaxed">
                      {lastMsg}
                    </p>
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* CENTER PANE: Conversation Timeline & Workspace */}
        <div className={`flex-1 flex-col min-w-0 bg-gray-50/50 relative ${mobileView === 'list' ? 'hidden md:flex' : 'flex'}`}>
          {selectedConversation ? (
            <>
              {/* Workspace Header */}
              <div className="min-h-16 py-2 bg-white border-b border-gray-200 px-4 sm:px-6 flex flex-wrap items-center justify-between gap-2 flex-shrink-0">
                <div className="flex items-center gap-3 min-w-0">
                  <button
                    type="button"
                    onClick={() => setMobileView('list')}
                    className="md:hidden p-1.5 -ml-1 rounded-lg hover:bg-gray-100 text-gray-600"
                    aria-label="Back to conversation list"
                  >
                    <ArrowLeft className="w-4 h-4" />
                  </button>
                  <div className="w-10 h-10 bg-teal-100/80 rounded-full flex items-center justify-center text-teal-800 font-bold text-sm">
                    {(selectedConversation.patient_name || 'P').charAt(0).toUpperCase()}
                  </div>
                  <div>
                    <h2 className="text-base font-bold text-gray-900">
                      {selectedConversation.patient_name || 'Guest Patient'}
                    </h2>
                    <div className="flex items-center gap-3 text-xs text-gray-500">
                      {selectedConversation.patient_email && (
                        <span className="flex items-center gap-1">
                          <Mail className="w-3 h-3 text-gray-400" /> {selectedConversation.patient_email}
                        </span>
                      )}
                      {selectedConversation.patient_phone && (
                        <span className="flex items-center gap-1">
                          <Phone className="w-3 h-3 text-gray-400" /> {selectedConversation.patient_phone}
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <span className={`px-2.5 py-1 rounded-full text-xs font-bold uppercase ${getStatusBadge(selectedConversation.status)}`}>
                    {selectedConversation.status || 'Active'}
                  </span>
                  {selectedConversation.status !== 'handoff' && selectedConversation.status !== 'closed' && (
                    <button
                      onClick={() => statusMutation.mutate({ id: String(selectedConversation.id), action: 'escalate' })}
                      disabled={statusMutation.isPending}
                      className="px-2.5 py-1 text-xs font-semibold border border-red-200 text-red-700 rounded-lg hover:bg-red-50"
                    >
                      Escalate
                    </button>
                  )}
                  {selectedConversation.status !== 'closed' && (
                    <button
                      onClick={() => statusMutation.mutate({ id: String(selectedConversation.id), action: 'close' })}
                      disabled={statusMutation.isPending}
                      className="px-2.5 py-1 text-xs font-semibold border border-gray-200 text-gray-700 rounded-lg hover:bg-gray-50"
                    >
                      Close
                    </button>
                  )}
                </div>
              </div>

              {/* Message Timeline */}
              <div className="flex-1 overflow-y-auto p-6 space-y-4">
                {(selectedConversation.messages || []).length === 0 ? (
                  <div className="text-center py-12 text-gray-400 text-sm">
                    No messages recorded in this conversation yet.
                  </div>
                ) : (
                  (selectedConversation.messages || []).map((msg: any, i: number) => {
                    const isUser = msg.sender === 'user';
                    return (
                      <div
                        key={msg.id || i}
                        className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}
                      >
                        <div
                          className={`max-w-[75%] rounded-2xl px-4 py-3 shadow-sm ${
                            isUser
                              ? 'bg-teal-600 text-white rounded-br-none'
                              : 'bg-white border border-gray-200 text-gray-900 rounded-bl-none'
                          }`}
                        >
                          <div className="flex items-center justify-between gap-4 mb-1">
                            <span
                              className={`text-[10px] font-bold uppercase tracking-wider ${
                                isUser ? 'text-teal-200' : 'text-teal-700'
                              }`}
                            >
                              {isUser ? 'Patient' : msg.sender === 'staff' ? 'Front Desk' : 'AI Concierge'}
                            </span>
                            <span
                              className={`text-[10px] ${
                                isUser ? 'text-teal-200' : 'text-gray-400'
                              }`}
                            >
                              {msg.created_at
                                ? new Date(msg.created_at).toLocaleTimeString([], {
                                    hour: '2-digit',
                                    minute: '2-digit',
                                  })
                                : ''}
                            </span>
                          </div>
                          <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>

              {/* Smart Composer Pane */}
              <div className="bg-white border-t border-gray-200 p-4 space-y-3">
                {/* AI Quick Response Starters */}
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-semibold text-gray-500 flex items-center gap-1">
                    <Sparkles className="w-3.5 h-3.5 text-purple-600" /> Quick replies:
                  </span>
                  <button
                    onClick={() => applyAIDraft('greeting')}
                    className="px-2.5 py-1 bg-purple-50 text-purple-700 hover:bg-purple-100 rounded-lg text-xs font-medium transition"
                  >
                    ✨ Warm Welcome
                  </button>
                  <button
                    onClick={() => applyAIDraft('offer_time')}
                    className="px-2.5 py-1 bg-blue-50 text-blue-700 hover:bg-blue-100 rounded-lg text-xs font-medium transition"
                  >
                    📅 Propose Openings
                  </button>
                  <button
                    onClick={() => applyAIDraft('confirm')}
                    className="px-2.5 py-1 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 rounded-lg text-xs font-medium transition"
                  >
                    ✅ Request Confirmation
                  </button>
                </div>

                {/* Input area */}
                <div className="relative">
                  <textarea
                    value={replyText}
                    onChange={(e) => setReplyText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        handleSend();
                      }
                    }}
                    placeholder={selectedConversation.patient_email
                      ? `Reply to ${selectedConversation.patient_email} (Enter to send)…`
                      : 'No patient email on file: reply will be saved to the conversation only'}
                    className="w-full border border-gray-200 rounded-xl pl-4 pr-12 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 resize-none h-20"
                  />
                  <button
                    onClick={handleSend}
                    disabled={sendReplyMutation.isPending || !replyText.trim()}
                    className="absolute right-3 bottom-3 p-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg transition disabled:opacity-40"
                    title="Send reply"
                  >
                    <Send className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-gray-500">
              <MessageSquare className="w-12 h-12 text-gray-300 mb-3" />
              <p className="text-base font-semibold text-gray-800">No conversation selected</p>
              <p className="text-xs text-gray-400 mt-1">Select a conversation from the left to view details.</p>
            </div>
          )}
        </div>

        {/* RIGHT PANE: Patient & AI Context Summary */}
        {selectedConversation && (
          <div className="w-80 bg-white border-l border-gray-200 flex-col flex-shrink-0 overflow-y-auto hidden xl:flex">
            <div className="p-5 border-b border-gray-200 space-y-2">
              <h3 className="text-xs font-bold text-gray-900 uppercase tracking-wider flex items-center gap-1.5">
                <FileText className="w-4 h-4 text-teal-600" /> AI Conversation Summary
              </h3>
              <div className="bg-teal-50/70 border border-teal-100 rounded-xl p-3.5 text-xs text-teal-900 leading-relaxed font-medium">
                {selectedConversation.summary || (
                  <span className="text-gray-500 font-normal">
                    No summary yet. A summary appears once the patient submits a request.
                  </span>
                )}
              </div>
            </div>

            <div className="p-5 border-b border-gray-200 space-y-3">
              <h3 className="text-xs font-bold text-gray-900 uppercase tracking-wider">
                Clinical Context
              </h3>
              <div className="space-y-2 text-xs">
                <div>
                  <span className="text-gray-500 block mb-1">Detected Intent:</span>
                  <span className="inline-block px-2.5 py-0.5 rounded-full bg-purple-100 text-purple-700 font-bold capitalize">
                    {selectedConversation.intent || 'General Consultation'}
                  </span>
                </div>
                {selectedConversation.service_requested && (
                  <div>
                    <span className="text-gray-500 block mb-1">Service Requested:</span>
                    <span className="font-semibold text-gray-800">
                      {selectedConversation.service_requested}
                    </span>
                  </div>
                )}
                {selectedConversation.preferred_date && (
                  <div>
                    <span className="text-gray-500 block mb-1">Preferred Time:</span>
                    <span className="font-semibold text-gray-800">
                      {selectedConversation.preferred_date} {selectedConversation.preferred_time || ''}
                    </span>
                  </div>
                )}
              </div>
            </div>

            <div className="p-5 space-y-3">
              <h3 className="text-xs font-bold text-gray-900 uppercase tracking-wider">
                Patient Contact
              </h3>
              <div className="space-y-2.5 text-xs">
                <div className="flex justify-between py-1 border-b border-gray-100">
                  <span className="text-gray-500">Name</span>
                  <span className="font-semibold text-gray-900">
                    {selectedConversation.patient_name || 'Guest'}
                  </span>
                </div>
                <div className="flex justify-between py-1 border-b border-gray-100">
                  <span className="text-gray-500">Email</span>
                  <span className="font-semibold text-gray-900 truncate max-w-[150px]">
                    {selectedConversation.patient_email || '—'}
                  </span>
                </div>
                <div className="flex justify-between py-1 border-b border-gray-100">
                  <span className="text-gray-500">Phone</span>
                  <span className="font-semibold text-gray-900">
                    {selectedConversation.patient_phone || '—'}
                  </span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-gray-500">Channel</span>
                  <span className="font-semibold text-teal-700">Web AI Concierge</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
