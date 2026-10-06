import React, { useState, useRef, useEffect } from 'react';
import {
  Copy, Mail, Phone, RefreshCw, Send, Sparkles, Check,
  Plus, FileText, Bot, User, Clock, CheckCheck, CornerDownLeft, ShieldAlert
} from 'lucide-react';
import type { Lead, Message, Note } from '../types';

interface ConversationViewProps {
  lead: Lead | null;
  messages: Message[];
  notes: Note[];
  onUpdateStatus: (newStatus: string) => void;
  onResendEmail: () => void;
  onRetryNotify: () => void;
  onSendReply: (body: string) => Promise<void>;
  onAiAction: (action: string, instruction?: string) => Promise<string>;
  onOpenNoteModal: () => void;
  onOpenTaskModal: () => void;
  onCopySummary: () => void;
}

export const ConversationView: React.FC<ConversationViewProps> = ({
  lead,
  messages,
  notes,
  onUpdateStatus,
  onResendEmail,
  onRetryNotify,
  onSendReply,
  onAiAction,
  onOpenNoteModal,
  onOpenTaskModal,
  onCopySummary,
}) => {
  const [replyText, setReplyText] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [aiLoadingAction, setAiLoadingAction] = useState<string | null>(null);
  const [aiResult, setAiResult] = useState<string | null>(null);
  const [copiedSummary, setCopiedSummary] = useState(false);
  const [copiedMsgId, setCopiedMsgId] = useState<number | null>(null);
  const timelineEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to latest message on messages change
  useEffect(() => {
    timelineEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, notes]);

  if (!lead) {
    return (
      <div style={{
        flex: 1,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexDirection: 'column',
        gap: '16px',
        color: 'var(--text-muted)',
        background: 'var(--bg-primary)',
        padding: '30px',
      }}>
        <div style={{
          width: '76px',
          height: '76px',
          borderRadius: '24px',
          background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.15), rgba(6, 78, 59, 0.3))',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '38px',
          boxShadow: '0 8px 24px rgba(16, 185, 129, 0.15)',
        }}>
          🦷
        </div>
        <div style={{ textAlign: 'center', maxWidth: '360px' }}>
          <h2 className="font-display" style={{
            fontSize: '20px',
            fontWeight: 800,
            color: 'var(--text-primary)',
            marginBottom: '6px',
          }}>
            HeyJarvis Command Center
          </h2>
          <p style={{ fontSize: '13px', color: 'var(--text-muted)', lineHeight: 1.5, margin: 0 }}>
            Select an active patient inquiry from the left panel to review transcripts, trigger AI drafts, or manage appointments.
          </p>
        </div>
      </div>
    );
  }

  const handleCopySummary = () => {
    onCopySummary();
    setCopiedSummary(true);
    setTimeout(() => setCopiedSummary(false), 2000);
  };

  const handleCopyMsg = (id: number, text: string) => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text);
      setCopiedMsgId(id);
      setTimeout(() => setCopiedMsgId(null), 2000);
    }
  };

  const handleSend = async () => {
    if (!replyText.trim() || isSending) return;
    setIsSending(true);
    try {
      await onSendReply(replyText.trim());
      setReplyText('');
    } finally {
      setIsSending(false);
    }
  };

  const handleTriggerAi = async (action: string) => {
    setAiLoadingAction(action);
    setAiResult(null);
    try {
      const res = await onAiAction(action, replyText.trim() || undefined);
      setAiResult(res);
    } finally {
      setAiLoadingAction(null);
    }
  };

  const isUrgent = lead.urgency === 'urgent' || lead.urgency === 'high';

  return (
    <main style={{
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      background: 'var(--bg-primary)',
      overflow: 'hidden',
    }}>
      {/* Patient Header Strip */}
      <div style={{
        padding: '14px 24px',
        background: 'var(--bg-secondary)',
        borderBottom: '1px solid var(--border-subtle)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '12px',
        boxShadow: 'var(--shadow-sm)',
        zIndex: 10,
      }}>
        {/* Left Info */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <h2 className="font-display" style={{
              fontSize: '18px',
              fontWeight: 800,
              color: 'var(--text-primary)',
              margin: 0,
            }}>
              {lead.name || 'Anonymous Visitor'}
            </h2>
            {isUrgent && (
              <span className="badge badge-urgent">
                <ShieldAlert size={11} /> URGENT
              </span>
            )}
            <span className={`badge badge-${lead.status || 'new'}`}>
              {lead.status}
            </span>
            {lead.service && (
              <span style={{
                fontSize: '11px',
                padding: '2px 8px',
                borderRadius: '6px',
                background: 'var(--bg-tertiary)',
                color: 'var(--text-secondary)',
                fontWeight: 500,
                border: '1px solid var(--border-subtle)',
              }}>
                {lead.service}
              </span>
            )}
          </div>

          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '14px',
            fontSize: '12px',
            color: 'var(--text-muted)',
            flexWrap: 'wrap',
          }}>
            {lead.phone && (
              <a
                href={`tel:${lead.phone}`}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  color: 'var(--brand-accent)',
                  textDecoration: 'none',
                  fontWeight: 500,
                }}
              >
                <Phone size={13} /> {lead.phone}
              </a>
            )}
            {lead.email && (
              <a
                href={`mailto:${lead.email}`}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  color: 'var(--text-secondary)',
                  textDecoration: 'none',
                }}
              >
                <Mail size={13} /> {lead.email}
              </a>
            )}
            <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <Clock size={12} /> {new Date(lead.created_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}
            </span>
            <span>ID #{lead.id}</span>
          </div>
        </div>

        {/* Action Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          {/* Status Dropdown */}
          <select
            value={lead.status}
            onChange={(e) => onUpdateStatus(e.target.value)}
            style={{
              padding: '6px 12px',
              borderRadius: '8px',
              border: '1px solid var(--border-subtle)',
              background: 'var(--bg-tertiary)',
              color: 'var(--text-primary)',
              fontSize: '12px',
              fontWeight: 600,
              outline: 'none',
              cursor: 'pointer',
              transition: 'border-color 0.15s ease',
            }}
          >
            <option value="new">Status: New</option>
            <option value="contacted">Status: Contacted</option>
            <option value="qualified">Status: Qualified</option>
            <option value="booked">Status: Booked</option>
            <option value="closed">Status: Closed</option>
            <option value="spam">Status: Spam</option>
          </select>

          <button
            onClick={handleCopySummary}
            className="btn-action"
            title="Copy patient intake record to clipboard"
          >
            {copiedSummary ? <Check size={13} color="#10b981" /> : <Copy size={13} />}
            <span>{copiedSummary ? 'Copied' : 'Copy Intake'}</span>
          </button>

          <button
            onClick={onResendEmail}
            className="btn-action"
            title="Resend email alert to clinic team"
          >
            <Mail size={13} />
            <span>Notify Email</span>
          </button>

          <button
            onClick={onRetryNotify}
            className="btn-action"
            title="Retry webhook/SMS notification dispatch"
          >
            <RefreshCw size={13} />
            <span>Retry Notify</span>
          </button>

          <button
            onClick={onOpenNoteModal}
            className="btn-action"
            title="Add private internal staff note"
          >
            <Plus size={13} />
            <span>Note</span>
          </button>

          <button
            onClick={onOpenTaskModal}
            className="btn-action btn-primary"
            title="Add task checklist item"
          >
            <Plus size={13} />
            <span>Task</span>
          </button>
        </div>
      </div>

      {/* Messages Timeline Container */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '24px',
        display: 'flex',
        flexDirection: 'column',
        gap: '14px',
      }}>
        {messages.length === 0 && notes.length === 0 ? (
          <div style={{
            margin: 'auto',
            textAlign: 'center',
            color: 'var(--text-muted)',
            padding: '40px 20px',
          }}>
            <FileText size={36} style={{ marginBottom: '10px', opacity: 0.4 }} />
            <div style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text-secondary)' }}>
              No messages recorded
            </div>
            <div style={{ fontSize: '12px', marginTop: '4px' }}>
              Patient submitted intake via website widget. Use AI actions below to generate a reply!
            </div>
          </div>
        ) : (
          <>
            {messages.map((m) => {
              const isUser = m.role === 'user';
              const isAssistant = m.role === 'assistant';
              const isCopied = copiedMsgId === m.id;

              return (
                <div
                  key={m.id}
                  style={{
                    alignSelf: isUser ? 'flex-start' : 'flex-end',
                    maxWidth: '78%',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: isUser ? 'flex-start' : 'flex-end',
                    position: 'relative',
                  }}
                  className="animate-fade-in"
                >
                  {/* Sender Header */}
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    fontSize: '11px',
                    color: 'var(--text-muted)',
                    marginBottom: '4px',
                  }}>
                    {isUser ? (
                      <>
                        <User size={12} />
                        <span style={{ fontWeight: 600 }}>{lead.name || 'Visitor'}</span>
                      </>
                    ) : isAssistant ? (
                      <>
                        <Bot size={12} color="var(--brand-accent)" />
                        <span style={{ fontWeight: 600, color: 'var(--brand-accent)' }}>HeyJarvis AI</span>
                      </>
                    ) : (
                      <>
                        <Bot size={12} color="#60a5fa" />
                        <span style={{ fontWeight: 600, color: '#60a5fa' }}>Front Desk Staff</span>
                      </>
                    )}
                    <span>•</span>
                    <span>{new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                  </div>

                  {/* Message Bubble Card */}
                  <div style={{
                    padding: '12px 16px',
                    borderRadius: isUser ? '16px 16px 16px 4px' : '16px 16px 4px 16px',
                    background: isUser ? 'var(--bg-secondary)' : isAssistant ? 'var(--brand-gradient)' : 'linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%)',
                    color: isUser ? 'var(--text-primary)' : '#ffffff',
                    border: isUser ? '1px solid var(--border-subtle)' : 'none',
                    fontSize: '13px',
                    lineHeight: '1.5',
                    boxShadow: 'var(--shadow-sm)',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                    position: 'relative',
                  }}>
                    {m.body}

                    {/* Copy Button */}
                    <button
                      onClick={() => handleCopyMsg(m.id, m.body)}
                      title="Copy message"
                      style={{
                        position: 'absolute',
                        top: '6px',
                        right: '6px',
                        background: 'transparent',
                        border: 'none',
                        color: isUser ? 'var(--text-muted)' : 'rgba(255, 255, 255, 0.7)',
                        cursor: 'pointer',
                        padding: '2px',
                        borderRadius: '4px',
                        display: 'flex',
                        opacity: 0.6,
                        transition: 'opacity 0.15s ease',
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.opacity = '1')}
                      onMouseLeave={(e) => (e.currentTarget.style.opacity = '0.6')}
                    >
                      {isCopied ? <CheckCheck size={12} color="#10b981" /> : <Copy size={12} />}
                    </button>
                  </div>
                </div>
              );
            })}

            {/* Internal Staff Notes in Timeline */}
            {notes.map((n) => (
              <div
                key={`timeline-note-${n.id}`}
                style={{
                  alignSelf: 'center',
                  width: '92%',
                  background: 'rgba(245, 158, 11, 0.08)',
                  border: '1px solid rgba(245, 158, 11, 0.25)',
                  borderRadius: '12px',
                  padding: '10px 14px',
                  fontSize: '12px',
                  color: 'var(--text-primary)',
                }}
                className="animate-fade-in"
              >
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  color: '#d97706',
                  fontWeight: 700,
                  marginBottom: '4px',
                }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                    📝 Internal Staff Note
                  </span>
                  <span style={{ fontSize: '10px', fontWeight: 500, color: 'var(--text-muted)' }}>
                    {new Date(n.created_at).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })}
                  </span>
                </div>
                <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.45 }}>{n.note}</div>
              </div>
            ))}
            <div ref={timelineEndRef} />
          </>
        )}
      </div>

      {/* AI Draft Suggestion Panel */}
      {aiResult && (
        <div style={{
          padding: '14px 20px',
          background: 'var(--bg-secondary)',
          borderTop: '1px solid var(--border-subtle)',
          borderLeft: '4px solid var(--ai-purple)',
          margin: '0 20px',
          borderRadius: '12px 12px 0 0',
          boxShadow: 'var(--shadow-md)',
        }} className="animate-slide-up">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{
              fontSize: '12px',
              fontWeight: 700,
              color: 'var(--ai-purple)',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}>
              <Sparkles size={14} /> AI Recommendation Draft
            </span>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                onClick={() => {
                  setReplyText(aiResult);
                }}
                className="btn-action"
                style={{ fontSize: '11px', padding: '4px 10px' }}
              >
                Insert into Composer
              </button>
              <button
                onClick={() => {
                  if (navigator.clipboard) navigator.clipboard.writeText(aiResult);
                }}
                className="btn-action"
                style={{ fontSize: '11px', padding: '4px 10px' }}
              >
                Copy
              </button>
              <button
                onClick={() => setAiResult(null)}
                style={{
                  fontSize: '11px',
                  padding: '4px 8px',
                  border: 'none',
                  background: 'transparent',
                  color: 'var(--text-muted)',
                  cursor: 'pointer',
                }}
              >
                Dismiss
              </button>
            </div>
          </div>
          <div style={{
            fontSize: '13px',
            color: 'var(--text-secondary)',
            whiteSpace: 'pre-wrap',
            maxHeight: '130px',
            overflowY: 'auto',
            lineHeight: 1.5,
            padding: '6px 0',
          }}>
            {aiResult}
          </div>
        </div>
      )}

      {/* AI Quick Prompts Toolbar */}
      <div style={{
        padding: '10px 24px',
        background: 'var(--bg-secondary)',
        borderTop: '1px solid var(--border-subtle)',
        display: 'flex',
        gap: '6px',
        overflowX: 'auto',
        alignItems: 'center',
      }}>
        <span style={{
          fontSize: '11px',
          fontWeight: 700,
          color: 'var(--text-muted)',
          display: 'flex',
          alignItems: 'center',
          gap: '4px',
          marginRight: '4px',
          whiteSpace: 'nowrap',
        }}>
          <Sparkles size={12} color="var(--ai-purple)" /> Copilot:
        </span>

        {[
          { key: 'draft_email', label: '✉️ Draft Email' },
          { key: 'quick_reply', label: '💬 Quick Reply' },
          { key: 'summarize', label: '📋 Summarize' },
          { key: 'next_action', label: '🎯 Next Action' },
          { key: 'follow_up', label: '🔄 Follow Up' },
          { key: 'confirm', label: '✅ Confirm' },
          { key: 'warm', label: '🔥 Warmer' },
          { key: 'shorten', label: '⚡ Shorten' },
        ].map((item) => (
          <button
            key={item.key}
            onClick={() => handleTriggerAi(item.key)}
            disabled={aiLoadingAction !== null}
            className="btn-action btn-ai"
            style={{
              padding: '4px 10px',
              fontSize: '11px',
              whiteSpace: 'nowrap',
              opacity: aiLoadingAction !== null && aiLoadingAction !== item.key ? 0.6 : 1,
            }}
          >
            {aiLoadingAction === item.key ? 'Thinking...' : item.label}
          </button>
        ))}
      </div>

      {/* Composer Input Area */}
      <div style={{
        padding: '14px 24px',
        background: 'var(--bg-secondary)',
        borderTop: '1px solid var(--border-subtle)',
        display: 'flex',
        gap: '12px',
        alignItems: 'flex-end',
      }}>
        <div style={{ flex: 1, position: 'relative' }}>
          <textarea
            value={replyText}
            onChange={(e) => setReplyText(e.target.value)}
            placeholder="Type reply or natural instruction (e.g. 'Offer 10:30 AM tomorrow'). Press Enter to send..."
            rows={2}
            style={{
              width: '100%',
              padding: '10px 14px',
              borderRadius: '10px',
              border: '1px solid var(--border-subtle)',
              background: 'var(--bg-primary)',
              color: 'var(--text-primary)',
              fontSize: '13px',
              fontFamily: 'inherit',
              resize: 'none',
              outline: 'none',
              transition: 'border-color 0.15s ease',
            }}
            onFocus={(e) => (e.target.style.borderColor = 'var(--brand-accent)')}
            onBlur={(e) => (e.target.style.borderColor = 'var(--border-subtle)')}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
          />
          <div style={{
            position: 'absolute',
            right: '10px',
            bottom: '8px',
            fontSize: '10px',
            color: 'var(--text-muted)',
            display: 'flex',
            alignItems: 'center',
            gap: '2px',
            pointerEvents: 'none',
          }}>
            <span>Enter</span>
            <CornerDownLeft size={10} />
          </div>
        </div>

        <button
          onClick={handleSend}
          disabled={!replyText.trim() || isSending}
          className="btn-primary"
          style={{
            padding: '10px 18px',
            borderRadius: '10px',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            cursor: !replyText.trim() || isSending ? 'not-allowed' : 'pointer',
            opacity: !replyText.trim() || isSending ? 0.6 : 1,
            height: '42px',
          }}
        >
          <Send size={14} />
          <span>{isSending ? 'Sending...' : 'Send'}</span>
        </button>
      </div>
    </main>
  );
};
