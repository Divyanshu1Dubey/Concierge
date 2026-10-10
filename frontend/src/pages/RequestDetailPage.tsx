import { useState, useEffect, useRef } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { requestsApi, emailsApi } from '@/services/api';
import {
  ArrowLeft, Send, Sparkles, Save,
  MessageSquare, AlertTriangle,
  Languages, CheckCircle2, RotateCw, Clock, Mail
} from 'lucide-react';
import toast from 'react-hot-toast';
import { apiErrorMessage } from '@/utils/api';
import { useAuthStore } from '@/stores/authStore';

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
  const [selectedTime, setSelectedTime] = useState('');
  const [customTime, setCustomTime] = useState('');
  const [offeredDate, setOfferedDate] = useState('');
  const [requestConfirmation, setRequestConfirmation] = useState(true);
  const [previewHtml, setPreviewHtml] = useState('');
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [aiSuggestion, setAiSuggestion] = useState('');
  const currentUser = useAuthStore((s) => s.user);
  const [showDelete, setShowDelete] = useState(false);
  const [deleteConversation, setDeleteConversation] = useState(true);
  const initializedFor = useRef<string | null>(null);

  const { data: request, isLoading, refetch } = useQuery({
    queryKey: ['appointment-request', id],
    queryFn: () => requestsApi.get(id!),
    enabled: !!id,
  });

  const checkReplies = useMutation({
    mutationFn: () => emailsApi.checkReplies(),
    onSuccess: (res: any) => {
      if (res?.configured === false) {
        toast('Reply checking is not set up yet, so patient replies are not collected automatically.', { icon: 'ℹ️' });
      } else if (res?.new_replies) {
        toast.success(`${res.new_replies} new patient repl${res.new_replies === 1 ? 'y' : 'ies'} found.`);
      } else {
        toast('No new replies.');
      }
      queryClient.invalidateQueries({ queryKey: ['appointment-request', id] });
    },
    onError: (err) => toast.error(apiErrorMessage(err, 'Could not check for replies.')),
  });

  const invalidateLists = () => {
    queryClient.invalidateQueries({ queryKey: ['appointment-requests'] });
    queryClient.invalidateQueries({ queryKey: ['requests-stats'] });
    queryClient.invalidateQueries({ queryKey: ['dashboard-metrics'] });
  };

  // Initialise the composer once per request so refetches (after notes/status changes)
  // never wipe what the staff member is typing.
  useEffect(() => {
    if (request && initializedFor.current !== request.id) {
      initializedFor.current = request.id;
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

  const formatOfferDate = (iso: string) => {
    if (!iso) return '';
    const [y, m, d] = iso.split('-').map(Number);
    return new Date(y, m - 1, d).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
  };
  const confirmationReady = Boolean(offeredDate && selectedTime);
  const sendsConfirmation = confirmationReady && requestConfirmation;

  const handleSelectTimeSlot = (time: string, dateIso: string = offeredDate) => {
    setSelectedTime(time);
    const dateText = dateIso ? formatOfferDate(dateIso) : (request?.preferred_date || 'your requested day');
    const timeOfferSentence = dateIso && requestConfirmation
      ? `We have reserved ${dateText} at ${time} for you. Please use the buttons in this email to confirm or request a different time.`
      : `We have reserved an opening for you on ${dateText} at ${time}. Please reply to confirm if this time works for you!`;

    const placeholderRegex = /(?:Please let us know what time works best for you and our front desk will help coordinate the visit\.|We have reserved an opening for you on [^\n]+? Please reply to confirm if this time works for you!|We have reserved [^\n]+? for you\. Please use the buttons in this email to confirm or request a different time\.|We have an opening available for you on [^\n.]+\.|We would love to offer you [^\n.]+\.|We have scheduled an opening for you at [^\n.]+\.)/i;

    let updatedBody = replyBody;
    if (placeholderRegex.test(updatedBody)) {
      updatedBody = updatedBody.replace(placeholderRegex, timeOfferSentence);
    } else if (updatedBody.includes('Best regards,')) {
      updatedBody = updatedBody.replace('Best regards,', `${timeOfferSentence}\n\nBest regards,`);
    } else {
      updatedBody = `${updatedBody.trim()}\n\n${timeOfferSentence}`;
    }

    setReplyBody(updatedBody);
    toast.success(`Selected ${time} — updated in email body!`);
  };

  // AI draft mutation
  const handleAiAction = async (action: string) => {
    if (!id) return;
    setIsAiLoading(true);
    try {
      const res = await requestsApi.aiDraft(id, {
        action,
        // A fresh draft starts from the practice's saved template; refinements work on the current text.
        current_text: action === 'draft' ? '' : replyBody,
        target_language: 'Spanish',
      });
      if (action === 'next_action' || action === 'explain' || action === 'summarize') {
        setAiSuggestion(res.result || '');
      } else if (res.result) {
        setReplyBody(res.result);
      }
      if (res.ai_unavailable) {
        toast('AI assistant is unavailable right now; showing the template draft.', { icon: '⚠️' });
      }
    } catch (err) {
      toast.error(apiErrorMessage(err, 'AI assistant request failed.'));
    } finally {
      setIsAiLoading(false);
    }
  };

  // Save draft mutation
  const saveDraftMutation = useMutation({
    mutationFn: () => requestsApi.saveDraft(id!, replyBody, selectedTime || undefined),
    onSuccess: () => {
      toast.success('Draft saved successfully!');
      queryClient.invalidateQueries({ queryKey: ['appointment-request', id] });
    },
    onError: (err) => toast.error(apiErrorMessage(err, 'Could not save draft.')),
  });

  const openPreview = async () => {
    if (!id || !confirmationReady) return;
    setIsPreviewLoading(true);
    try {
      const res = await requestsApi.offerPreview(id, { offered_date: offeredDate, offered_time: selectedTime, body: replyBody });
      setPreviewHtml(res.html || '');
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Could not build the preview.'));
    } finally {
      setIsPreviewLoading(false);
    }
  };

  // Send reply mutation
  const sendReplyMutation = useMutation({
    mutationFn: () =>
      requestsApi.sendReply(id!, {
        to_email: recipientEmail,
        subject: subject,
        body: replyBody,
        offered_time: selectedTime || undefined,
        offered_date: sendsConfirmation ? offeredDate : undefined,
        request_confirmation: sendsConfirmation,
      }),
    onSuccess: (data: any) => {
      const msg = data?.message || `Reply email sent to ${recipientEmail}.`;
      setSendSuccessMessage(msg);
      if (data?.delivery?.warning) {
        // e.g. development console backend: recorded but not delivered to an inbox.
        toast(msg, { icon: '⚠️', duration: 8000 });
      } else {
        toast.success(msg);
      }
      refetch();
      invalidateLists();
      setTimeout(() => setSendSuccessMessage(''), 8000);
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.message || apiErrorMessage(err, 'Failed to send reply to patient'));
    },
  });

  // Add Note mutation
  const addNoteMutation = useMutation({
    mutationFn: (text: string) => requestsApi.addNote(id!, text),
    onSuccess: () => {
      setNewNote('');
      toast.success('Note added');
      refetch();
    },
    onError: (err) => toast.error(apiErrorMessage(err, 'Could not add note.')),
  });

  // Update Status mutation
  const updateStatusMutation = useMutation({
    mutationFn: (newStatus: string) => requestsApi.updateStatus(id!, { status: newStatus }),
    onSuccess: () => {
      toast.success('Status updated');
      refetch();
      invalidateLists();
    },
    onError: (err) => toast.error(apiErrorMessage(err, 'Could not update status.')),
  });

  const deleteMutation = useMutation({
    mutationFn: () => requestsApi.remove(id!, deleteConversation),
    onSuccess: () => {
      toast.success('Request permanently deleted');
      invalidateLists();
      navigate('/dashboard/requests');
    },
    onError: (err) => toast.error(apiErrorMessage(err, 'Could not delete this request.')),
  });

  const updatePriorityMutation = useMutation({
    mutationFn: (newPriority: string) => requestsApi.updateStatus(id!, { priority: newPriority }),
    onSuccess: () => {
      toast.success('Priority updated');
      refetch();
      invalidateLists();
    },
    onError: (err) => toast.error(apiErrorMessage(err, 'Could not update priority.')),
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
  const canDelete = Boolean(
    currentUser?.is_agency_admin || currentUser?.is_practice_admin ||
    ['PRACTICE_ADMIN', 'ADMIN', 'OWNER', 'AGENCY_ADMIN'].includes((currentUser?.role || '').toUpperCase())
  );

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
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
        <div className="flex flex-wrap items-center gap-2">
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

          {canDelete && (
            <button
              type="button"
              onClick={() => setShowDelete(true)}
              className="text-sm px-3 py-1.5 rounded-lg border border-red-200 text-red-700 hover:bg-red-50 font-medium"
            >
              Delete
            </button>
          )}
        </div>
      </div>

      {previewHtml && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-slate-950/50" role="dialog" aria-modal="true" aria-labelledby="preview-title">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl h-[88vh] flex flex-col overflow-hidden">
            <div className="flex items-center justify-between gap-3 px-4 py-3 border-b">
              <h2 id="preview-title" className="text-sm font-semibold text-gray-900">Patient email preview</h2>
              <button type="button" onClick={() => setPreviewHtml('')} className="text-sm px-3 py-1 rounded-lg border border-gray-200 hover:bg-gray-50">Close</button>
            </div>
            <p className="px-4 py-2 text-[11px] text-gray-500 bg-gray-50 border-b">Buttons are disabled in the preview. The real email contains a secure link for this patient.</p>
            <iframe title="Patient email preview" srcDoc={previewHtml} sandbox="" className="flex-1 w-full border-0" />
          </div>
        </div>
      )}

      {showDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/50" role="dialog" aria-modal="true" aria-labelledby="delete-title">
          <div className="bg-white rounded-2xl shadow-xl max-w-md w-full p-6 space-y-4">
            <h2 id="delete-title" className="text-lg font-semibold text-gray-900">Delete this request permanently?</h2>
            <p className="text-sm text-gray-600">
              Use this for patient data-deletion requests. The request ({request.confirmation_code}) and its notes cannot be recovered.
              The deletion is recorded in the audit log without patient details. Emails already sent to the patient are not deleted and remain in the Email Log.
            </p>
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input type="checkbox" checked={deleteConversation} onChange={(e) => setDeleteConversation(e.target.checked)} className="rounded" />
              Also delete the chat conversation
            </label>
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={() => setShowDelete(false)} className="px-4 py-2 text-sm rounded-lg border border-gray-200 hover:bg-gray-50">Cancel</button>
              <button
                type="button"
                onClick={() => deleteMutation.mutate()}
                disabled={deleteMutation.isPending}
                className="px-4 py-2 text-sm rounded-lg bg-red-700 hover:bg-red-800 text-white font-medium disabled:opacity-50"
              >
                {deleteMutation.isPending ? 'Deleting…' : 'Delete permanently'}
              </button>
            </div>
          </div>
        </div>
      )}

      {sendSuccessMessage && (
        <div className="p-4 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-xl flex items-center gap-2 text-sm">
          <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0" />
          <span>{sendSuccessMessage}</span>
        </div>
      )}

      {/* Main 2-Column Command Center */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Details & Context (5 cols) */}
        <div className="lg:col-span-5 space-y-6 min-w-0">
          {/* Appointment confirmation status */}
          {request.latest_offer && (
            <OfferStatusCard offer={request.latest_offer} />
          )}

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
                <p className="font-medium text-gray-900 mt-0.5 break-all">{request.patient_email || 'None provided'}</p>
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

          {/* Email history (sent replies and patient responses) */}
          <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-3">
            <div className="flex items-center justify-between gap-2 border-b pb-2">
              <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
                <Mail className="w-4 h-4 text-teal-600" aria-hidden="true" /> Email history
              </h3>
              <button
                type="button"
                onClick={() => checkReplies.mutate()}
                disabled={checkReplies.isPending}
                className="text-xs font-medium px-2.5 py-1 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-700 disabled:opacity-50"
              >
                {checkReplies.isPending ? 'Checking…' : 'Check for replies'}
              </button>
            </div>
            {(request.email_history || []).length === 0 ? (
              <p className="text-xs text-gray-400 italic">No emails yet. Replies you send from this page appear here.</p>
            ) : (
              <ul className="space-y-2 max-h-72 overflow-y-auto">
                {(request.email_history || []).map((m: any) => (
                  <li
                    key={m.id}
                    className={`rounded-lg border p-2.5 text-xs ${m.direction === 'incoming' ? 'bg-blue-50 border-blue-200 text-blue-950' : 'bg-gray-50 border-gray-200 text-gray-800'}`}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2 text-[10.5px] mb-1">
                      <span className="font-semibold">
                        {m.direction === 'incoming' ? 'Patient replied' : 'Sent by practice'}
                        {m.status === 'failed' && <span className="ml-1 text-red-700">· delivery failed</span>}
                      </span>
                      <span className="text-gray-500">{new Date(m.sent_at || m.created_at).toLocaleString()}</span>
                    </div>
                    <p className="whitespace-pre-wrap break-words line-clamp-6">{m.body}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>

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
        <div className="lg:col-span-7 min-w-0 space-y-4">
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
              {aiSuggestion && (
                <div className="mt-2 p-2.5 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-900 flex items-start justify-between gap-2">
                  <span><strong>Suggested next step:</strong> {aiSuggestion}</span>
                  <button type="button" onClick={() => setAiSuggestion('')} className="text-amber-700 underline flex-shrink-0">Dismiss</button>
                </div>
              )}
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

            {/* Quick Propose Appointment Time Slots */}
            <div className="bg-slate-50 border border-slate-200/90 rounded-xl p-4 space-y-3">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-2">
                  <Clock className="w-4 h-4 text-teal-600" />
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-800">
                    Propose Visit Time
                  </span>
                  <span className="text-[11px] text-slate-500 font-medium">
                    (Click any time slot to auto-insert into email message)
                  </span>
                </div>
                {selectedTime && (
                  <span className="text-xs font-bold px-2.5 py-0.5 rounded-full bg-teal-100 text-teal-800 border border-teal-200 flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5 text-teal-600" />
                    Proposed: {selectedTime}
                  </span>
                )}
              </div>

              {/* Morning Slots */}
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[10px] font-extrabold text-slate-400 uppercase tracking-wider w-16">Morning:</span>
                {['8:30 AM', '9:00 AM', '9:30 AM', '10:00 AM', '10:30 AM', '11:00 AM', '11:30 AM'].map((slot) => (
                  <button
                    key={slot}
                    type="button"
                    onClick={() => handleSelectTimeSlot(slot)}
                    className={`px-2.5 py-1 text-xs font-semibold rounded-lg border transition shadow-2xs ${
                      selectedTime === slot
                        ? 'bg-teal-600 text-white border-teal-600 shadow-sm ring-2 ring-teal-200'
                        : 'bg-white text-slate-700 border-slate-200 hover:bg-teal-50 hover:border-teal-300 hover:text-teal-900'
                    }`}
                  >
                    {slot}
                  </button>
                ))}
              </div>

              {/* Afternoon Slots */}
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[10px] font-extrabold text-slate-400 uppercase tracking-wider w-16">Afternoon:</span>
                {['1:00 PM', '1:30 PM', '2:00 PM', '2:30 PM', '3:00 PM', '3:30 PM', '4:00 PM', '4:30 PM'].map((slot) => (
                  <button
                    key={slot}
                    type="button"
                    onClick={() => handleSelectTimeSlot(slot)}
                    className={`px-2.5 py-1 text-xs font-semibold rounded-lg border transition shadow-2xs ${
                      selectedTime === slot
                        ? 'bg-teal-600 text-white border-teal-600 shadow-sm ring-2 ring-teal-200'
                        : 'bg-white text-slate-700 border-slate-200 hover:bg-teal-50 hover:border-teal-300 hover:text-teal-900'
                    }`}
                  >
                    {slot}
                  </button>
                ))}
              </div>

              {/* Visit date + patient confirmation */}
              <div className="flex flex-wrap items-center gap-2 pt-1.5 border-t border-slate-200/70 text-xs">
                <label htmlFor="offer-date" className="text-slate-500 font-medium">Visit date:</label>
                <input
                  id="offer-date"
                  type="date"
                  min={new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10)}
                  value={offeredDate}
                  onChange={(e) => {
                    setOfferedDate(e.target.value);
                    if (selectedTime) handleSelectTimeSlot(selectedTime, e.target.value);
                  }}
                  className="px-2.5 py-1 bg-white border border-slate-200 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-teal-500"
                />
                {offeredDate && <span className="text-slate-600">{formatOfferDate(offeredDate)}</span>}
              </div>
              {confirmationReady && (
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-white border border-teal-200 px-3 py-2">
                  <label className="flex items-start gap-2 text-xs text-slate-700 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={requestConfirmation}
                      onChange={(e) => setRequestConfirmation(e.target.checked)}
                      className="mt-0.5 rounded text-teal-600"
                    />
                    <span>
                      <span className="font-semibold text-slate-900">Ask the patient to confirm</span>
                      <span className="block text-slate-500">Sends a branded email with Confirm and Request another time buttons. Their answer appears on this page.</span>
                    </span>
                  </label>
                  {requestConfirmation && (
                    <button
                      type="button"
                      onClick={openPreview}
                      disabled={isPreviewLoading}
                      className="px-3 py-1 text-xs font-semibold rounded-lg border border-teal-300 text-teal-800 hover:bg-teal-50 disabled:opacity-50"
                    >
                      {isPreviewLoading ? 'Preparing…' : 'Preview email'}
                    </button>
                  )}
                </div>
              )}

              {/* Custom Time */}
              <div className="flex items-center gap-2 pt-1.5 border-t border-slate-200/70 text-xs">
                <span className="text-slate-500 font-medium">Custom time:</span>
                <input
                  type="text"
                  placeholder="e.g. 11:15 AM or Tomorrow 3:00 PM"
                  value={customTime}
                  onChange={(e) => setCustomTime(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      if (customTime.trim()) handleSelectTimeSlot(customTime.trim());
                    }
                  }}
                  className="px-2.5 py-1 bg-white border border-slate-200 rounded-lg text-xs w-52 focus:outline-none focus:ring-2 focus:ring-teal-500"
                />
                <button
                  type="button"
                  onClick={() => {
                    if (customTime.trim()) handleSelectTimeSlot(customTime.trim());
                  }}
                  className="px-3 py-1 bg-slate-200 hover:bg-slate-300 text-slate-800 rounded-lg text-xs font-semibold transition"
                >
                  Set Time
                </button>
              </div>
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
                {sendReplyMutation.isPending ? 'Sending...' : sendsConfirmation ? 'Send confirmation request' : 'Send to Patient'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}


function OfferStatusCard({ offer }: { offer: any }) {
  const when = `${offer.date_display} at ${offer.offered_time}`;
  const tone: Record<string, { box: string; title: string; body: string }> = {
    pending: { box: 'bg-amber-50 border-amber-200 text-amber-950', title: 'Waiting for the patient', body: `Asked to confirm ${when}.` },
    confirmed: { box: 'bg-emerald-50 border-emerald-200 text-emerald-950', title: 'Patient confirmed', body: `${when}.` },
    reschedule_requested: { box: 'bg-blue-50 border-blue-200 text-blue-950', title: 'Patient asked for another time', body: `Instead of ${when}.` },
    expired: { box: 'bg-gray-50 border-gray-200 text-gray-800', title: 'No answer before the date', body: `${when} was not confirmed.` },
    closed: { box: 'bg-gray-50 border-gray-200 text-gray-800', title: 'Request closed', body: `The confirmation link for ${when} no longer works.` },
    superseded: { box: 'bg-gray-50 border-gray-200 text-gray-800', title: 'Replaced', body: `${when} was replaced by a newer time.` },
  };
  const t = tone[offer.state] || tone.pending;
  return (
    <div className={`rounded-xl border p-4 text-sm ${t.box}`} role="status">
      <p className="text-[11px] font-semibold uppercase tracking-wider opacity-70">Appointment confirmation</p>
      <p className="font-semibold mt-1">{t.title}</p>
      <p className="mt-0.5">{t.body}</p>
      {offer.patient_note && <p className="mt-2 text-[13px] whitespace-pre-wrap">Patient's note: “{offer.patient_note}”</p>}
      <p className="mt-2 text-[11px] opacity-70">
        Sent {new Date(offer.created_at).toLocaleString()}{offer.sent_by ? ` by ${offer.sent_by}` : ''}
        {offer.responded_at ? ` · answered ${new Date(offer.responded_at).toLocaleString()}` : ''}
      </p>
    </div>
  );
}
