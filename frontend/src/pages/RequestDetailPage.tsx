import { useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { requestsApi } from '@/services/api';
import {
  ArrowLeft, Send, Sparkles, Save,
  MessageSquare, AlertTriangle,
  Languages, CheckCircle2, RotateCw
} from 'lucide-react';
import toast from 'react-hot-toast';

export default function RequestDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [subject, setSubject] = useState('');
  const [replyBody, setReplyBody] = useState('');
  const [recipientEmail, setRecipientEmail] = useState('');
  const [newNote, setNewNote] = useState('');
  const [isAiLoading, setIsAiLoading] = useState(false);
  const [sendSuccessMessage, setSendSuccessMessage] = useState('');

  const { data: request, isLoading, refetch } = useQuery({
    queryKey: ['appointment-request', id],
    queryFn: () => requestsApi.get(id!),
    enabled: !!id,
  });

  useEffect(() => {
    if (request) {
      setRecipientEmail(request.patient_email || '');
      setSubject(`Your appointment with ${request.practice_name || 'our practice'}`);
      if (request.response_draft) {
        setReplyBody(request.response_draft);
      } else {
        // Initial clean draft
        const pName = request.patient_name || 'there';
        const sName = request.service_name || request.intent || 'appointment';
        const d = request.preferred_date || 'this week';
        const t = request.preferred_time || 'flexible timing';
        setReplyBody(
          `Hi ${pName},\n\nThanks for reaching out! We would be delighted to coordinate your ${sName}.\n\nWe have your request for:\n• Preferred Date: ${d}\n• Preferred Time: ${t}\n\nPlease let us know what time works best for you and our front desk will help coordinate the visit.\n\nBest regards,\n${request.practice_name || 'HeyJarvis'} Front Desk\n${request.practice_phone || ''}`
        );
      }
    }
  }, [request]);

  // AI draft mutation
  const handleAiAction = async (action: string) => {
    if (!id) return;
    setIsAiLoading(true);
    try {
      const res = await requestsApi.aiDraft(id, {
        action,
        current_text: replyBody,
        target_language: 'Spanish',
      });
      if (res.result) {
        setReplyBody(res.result);
      }
    } catch (e) {
      console.error('AI Draft failed:', e);
    } finally {
      setIsAiLoading(false);
    }
  };

  // Save draft mutation
  const saveDraftMutation = useMutation({
    mutationFn: () => requestsApi.saveDraft(id!, replyBody),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['appointment-request', id] });
    },
  });

  // Send reply mutation
  const sendReplyMutation = useMutation({
    mutationFn: () =>
      requestsApi.sendReply(id!, {
        to_email: recipientEmail,
        subject: subject,
        body: replyBody,
      }),
    onSuccess: (data: any) => {
      const msg = data?.message || `Reply email successfully sent to ${recipientEmail}!`;
      setSendSuccessMessage(msg);
      toast.success(msg);
      refetch();
      queryClient.invalidateQueries({ queryKey: ['requests'] });
      setTimeout(() => setSendSuccessMessage(''), 8000);
    },
    onError: (err: any) => {
      const errMsg = err?.response?.data?.message || err?.response?.data?.error || 'Failed to send reply to patient';
      toast.error(errMsg);
    },
  });

  // Add Note mutation
  const addNoteMutation = useMutation({
    mutationFn: (text: string) => requestsApi.addNote(id!, text),
    onSuccess: () => {
      setNewNote('');
      refetch();
    },
  });

  // Update Status mutation
  const updateStatusMutation = useMutation({
    mutationFn: (newStatus: string) => requestsApi.updateStatus(id!, { status: newStatus }),
    onSuccess: () => {
      refetch();
      queryClient.invalidateQueries({ queryKey: ['requests'] });
    },
  });

  const updatePriorityMutation = useMutation({
    mutationFn: (newPriority: string) => requestsApi.updateStatus(id!, { priority: newPriority }),
    onSuccess: () => {
      refetch();
      queryClient.invalidateQueries({ queryKey: ['requests'] });
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="w-8 h-8 border-2 border-teal-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!request) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-500">Request not found.</p>
        <Link to="/dashboard/requests" className="text-teal-600 hover:underline mt-2 inline-block">
          Back to inbox
        </Link>
      </div>
    );
  }

  const isEmergency = request.urgency === 'URGENT' || request.intent === 'emergency';

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/dashboard/requests')}
            className="p-2 hover:bg-gray-100 rounded-lg text-gray-600 transition"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-gray-900">
                {request.patient_name || request.patient_email || 'Guest Patient'}
              </h1>
              {isEmergency && (
                <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-red-100 text-red-700 flex items-center gap-1">
                  <AlertTriangle className="w-3.5 h-3.5" />
                  EMERGENCY
                </span>
              )}
              <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${
                request.status === 'confirmed' ? 'bg-green-100 text-green-700' :
                request.status === 'contacted' ? 'bg-blue-100 text-blue-700' :
                'bg-yellow-100 text-yellow-700'
              }`}>
                {request.status?.toUpperCase()}
              </span>
            </div>
            <p className="text-sm text-gray-500 mt-0.5">
              Ref: <span className="font-mono">{request.confirmation_code}</span> • Received {new Date(request.created_at).toLocaleString()}
            </p>
          </div>
        </div>

        {/* Status Actions */}
        <div className="flex items-center gap-2">
          <select
            value={request.status}
            onChange={(e) => updateStatusMutation.mutate(e.target.value)}
            className="text-sm border border-gray-300 rounded-lg px-3 py-1.5 bg-white font-medium focus:ring-2 focus:ring-teal-500"
          >
            <option value="pending">Pending Review</option>
            <option value="contacted">Contacted</option>
            <option value="confirmed">Confirmed</option>
            <option value="completed">Completed</option>
            <option value="cancelled">Cancelled</option>
            <option value="spam">Spam</option>
          </select>

          <select
            value={request.priority || 'NORMAL'}
            onChange={(e) => updatePriorityMutation.mutate(e.target.value)}
            className="text-sm border border-gray-300 rounded-lg px-3 py-1.5 bg-white font-medium focus:ring-2 focus:ring-teal-500"
          >
            <option value="LOW">Low Priority</option>
            <option value="NORMAL">Normal Priority</option>
            <option value="HIGH">High Priority</option>
            <option value="URGENT">Urgent Priority</option>
          </select>
        </div>
      </div>

      {sendSuccessMessage && (
        <div className="p-4 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-xl flex items-center gap-2 text-sm">
          <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0" />
          <span>{sendSuccessMessage}</span>
        </div>
      )}

      {/* Main 2-Column Command Center */}
      <div className="grid lg:grid-cols-12 gap-6">
        {/* Left Column: Details & Context (5 cols) */}
        <div className="lg:col-span-5 space-y-6">
          {/* Patient Details Card */}
          <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
            <h2 className="text-base font-semibold text-gray-900 border-b pb-3">Patient & Request Information</h2>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-xs text-gray-500">Phone</p>
                <p className="font-medium text-gray-900 mt-0.5">{request.patient_phone || 'None provided'}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Email</p>
                <p className="font-medium text-gray-900 mt-0.5">{request.patient_email || 'None provided'}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Service / Reason</p>
                <p className="font-medium text-gray-900 mt-0.5">{request.service_title || 'General Appointment'}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Intent</p>
                <p className="font-medium text-gray-900 mt-0.5 capitalize">{request.intent?.replace(/_/g, ' ')}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Preferred Date</p>
                <p className="font-medium text-gray-900 mt-0.5">{request.preferred_date || 'Flexible'}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Preferred Time</p>
                <p className="font-medium text-gray-900 mt-0.5">{request.preferred_time || 'Flexible'}</p>
              </div>
            </div>

            {request.message && (
              <div className="bg-gray-50 rounded-lg p-3 text-sm text-gray-700">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Patient Note</p>
                {request.message}
              </div>
            )}
          </div>

          {/* AI Clinical / Summary Card */}
          <div className="bg-gradient-to-br from-teal-50 to-cyan-50 rounded-xl border border-teal-200 p-5 space-y-3">
            <div className="flex items-center gap-2 text-teal-800 font-semibold text-sm">
              <Sparkles className="w-4 h-4 text-teal-600" />
              <span>AI Intelligence Summary</span>
            </div>
            <p className="text-sm text-teal-950 leading-relaxed">
              {request.ai_summary || 'Patient reached out via Concierge widget to request assistance.'}
            </p>
          </div>

          {/* Transcript accordion/list if conversation attached */}
          {request.transcript && request.transcript.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-3">
              <div className="flex items-center gap-2 text-gray-900 font-semibold text-sm border-b pb-2">
                <MessageSquare className="w-4 h-4 text-gray-500" />
                <span>Chat Transcript ({request.transcript.length} messages)</span>
              </div>
              <div className="space-y-2.5 max-h-60 overflow-y-auto pr-1 text-xs">
                {request.transcript.map((msg: any, i: number) => (
                  <div
                    key={i}
                    className={`p-2.5 rounded-lg ${
                      msg.sender === 'user'
                        ? 'bg-gray-100 text-gray-800 ml-4'
                        : 'bg-teal-50 text-teal-900 mr-4'
                    }`}
                  >
                    <p className="font-semibold capitalize mb-0.5 text-[10px] text-gray-500">
                      {msg.sender === 'user' ? (request.patient_name || 'Patient') : 'HeyJarvis AI'}
                    </p>
                    <p>{msg.content}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Internal Staff Notes */}
          <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-3">
            <h3 className="text-sm font-semibold text-gray-900 border-b pb-2">Staff Internal Notes</h3>
            <div className="space-y-2 max-h-40 overflow-y-auto">
              {(request.internal_notes || []).map((note: any, i: number) => (
                <div key={i} className="bg-amber-50 border border-amber-200/60 rounded-lg p-2.5 text-xs text-amber-950">
                  <div className="flex justify-between items-center text-[10px] text-amber-700 mb-1">
                    <span className="font-semibold">{note.author}</span>
                    <span>{new Date(note.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                  </div>
                  <p>{note.text}</p>
                </div>
              ))}
              {(!request.internal_notes || request.internal_notes.length === 0) && (
                <p className="text-xs text-gray-400 italic">No internal staff notes yet.</p>
              )}
            </div>

            <div className="flex gap-2 pt-2">
              <input
                type="text"
                placeholder="Add confidential note (never seen by patient)..."
                value={newNote}
                onChange={(e) => setNewNote(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && newNote.trim()) {
                    addNoteMutation.mutate(newNote.trim());
                  }
                }}
                className="flex-1 text-xs border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-teal-500"
              />
              <button
                disabled={!newNote.trim() || addNoteMutation.isPending}
                onClick={() => addNoteMutation.mutate(newNote.trim())}
                className="px-3 py-2 bg-gray-900 text-white text-xs font-medium rounded-lg hover:bg-gray-800 disabled:opacity-50"
              >
                Add
              </button>
            </div>
          </div>
        </div>

        {/* Right Column: AI-Powered Reply Workspace (7 cols) */}
        <div className="lg:col-span-7 space-y-4">
          <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-5 shadow-sm">
            <div className="flex items-center justify-between border-b pb-4">
              <div>
                <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
                  <Send className="w-5 h-5 text-teal-600" />
                  Front Desk Reply Workspace
                </h2>
                <p className="text-xs text-gray-500 mt-0.5">
                  AI prepares response based on context & rules. Edit anytime before sending.
                </p>
              </div>

              {request.response_sent_at && (
                <span className="text-xs text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-full font-medium flex items-center gap-1">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  Sent {new Date(request.response_sent_at).toLocaleDateString()}
                </span>
              )}
            </div>

            {/* Recipient and Subject Fields */}
            <div className="space-y-3">
              <div>
                <label className="text-xs font-semibold text-gray-600 uppercase">To Patient Email</label>
                <input
                  type="email"
                  value={recipientEmail}
                  onChange={(e) => setRecipientEmail(e.target.value)}
                  placeholder="patient@example.com"
                  className="w-full text-sm border border-gray-300 rounded-lg px-3.5 py-2 mt-1 focus:ring-2 focus:ring-teal-500"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-gray-600 uppercase">Subject</label>
                <input
                  type="text"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  className="w-full text-sm border border-gray-300 rounded-lg px-3.5 py-2 mt-1 focus:ring-2 focus:ring-teal-500 font-medium"
                />
              </div>
            </div>

            {/* AI Action Toolbar */}
            <div className="bg-gray-50 rounded-xl p-3 border border-gray-200/80 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-gray-700 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-teal-600" />
                  Smart AI Actions:
                </span>
                {isAiLoading && (
                  <span className="text-xs text-teal-600 flex items-center gap-1">
                    <RotateCw className="w-3 h-3 animate-spin" />
                    Generating refinement...
                  </span>
                )}
              </div>

              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => handleAiAction('draft')}
                  disabled={isAiLoading}
                  className="px-2.5 py-1.5 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-xs font-medium transition shadow-sm"
                >
                  Draft Reply
                </button>
                <button
                  type="button"
                  onClick={() => handleAiAction('professional')}
                  disabled={isAiLoading}
                  className="px-2.5 py-1.5 bg-white border border-gray-300 hover:bg-gray-100 text-gray-700 rounded-lg text-xs font-medium transition"
                >
                  Make More Professional
                </button>
                <button
                  type="button"
                  onClick={() => handleAiAction('shorter')}
                  disabled={isAiLoading}
                  className="px-2.5 py-1.5 bg-white border border-gray-300 hover:bg-gray-100 text-gray-700 rounded-lg text-xs font-medium transition"
                >
                  Make Shorter
                </button>
                <button
                  type="button"
                  onClick={() => handleAiAction('warmer')}
                  disabled={isAiLoading}
                  className="px-2.5 py-1.5 bg-white border border-gray-300 hover:bg-gray-100 text-gray-700 rounded-lg text-xs font-medium transition"
                >
                  Make Warmer
                </button>
                <button
                  type="button"
                  onClick={() => handleAiAction('translate')}
                  disabled={isAiLoading}
                  className="px-2.5 py-1.5 bg-white border border-gray-300 hover:bg-gray-100 text-gray-700 rounded-lg text-xs font-medium transition flex items-center gap-1"
                >
                  <Languages className="w-3 h-3 text-gray-500" />
                  Translate (ES)
                </button>
                <button
                  type="button"
                  onClick={() => handleAiAction('next_action')}
                  disabled={isAiLoading}
                  className="px-2.5 py-1.5 bg-white border border-gray-300 hover:bg-gray-100 text-gray-700 rounded-lg text-xs font-medium transition"
                >
                  Suggest Next Step
                </button>
              </div>
            </div>

            {/* Editable Response Editor */}
            <div>
              <label className="text-xs font-semibold text-gray-600 uppercase">Email Body</label>
              <textarea
                rows={11}
                value={replyBody}
                onChange={(e) => setReplyBody(e.target.value)}
                className="w-full text-sm font-sans border border-gray-300 rounded-xl p-4 mt-1 leading-relaxed focus:ring-2 focus:ring-teal-500 focus:outline-none"
                placeholder="Compose reply..."
              />
            </div>

            {/* Action Buttons */}
            <div className="flex items-center justify-between pt-2 border-t">
              <button
                type="button"
                onClick={() => saveDraftMutation.mutate()}
                disabled={saveDraftMutation.isPending}
                className="px-4 py-2 border border-gray-300 hover:bg-gray-50 text-gray-700 text-sm font-medium rounded-lg flex items-center gap-1.5 transition"
              >
                <Save className="w-4 h-4 text-gray-500" />
                {saveDraftMutation.isPending ? 'Saving...' : 'Save Draft'}
              </button>

              <button
                type="button"
                onClick={() => sendReplyMutation.mutate()}
                disabled={sendReplyMutation.isPending || !recipientEmail || !replyBody.trim()}
                className="px-6 py-2.5 bg-gradient-to-r from-teal-600 to-cyan-600 hover:from-teal-700 hover:to-cyan-700 text-white text-sm font-semibold rounded-lg shadow-md hover:shadow-lg flex items-center gap-2 transition disabled:opacity-50"
              >
                <Send className="w-4 h-4" />
                {sendReplyMutation.isPending ? 'Sending Reply...' : 'Send to Patient'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
