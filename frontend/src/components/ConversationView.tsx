import React, { useState } from 'react';
import {
  Copy, Mail, Phone, RefreshCw, Send, Sparkles, Check,
  Plus, FileText
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

  if (!lead) {
    return (
      <div style={{
        flex: 1,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexDirection: 'column',
        gap: '12px',
        color: 'var(--text-muted)',
      }}>
        <div style={{ fontSize: '48px' }}>🦷</div>
        <h2 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--text-primary)' }}>HeyJarvis AI Front Desk</h2>
        <p style={{ fontSize: '13px', maxWidth: '340px', textAlign: 'center' }}>
          Select a patient conversation from the sidebar to view details, use AI tools, and handle appointment requests.
        </p>
      </div>
    );
  }

  const handleCopySummary = () => {
    onCopySummary();
    setCopiedSummary(true);
    setTimeout(() => setCopiedSummary(false), 2000);
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
      {/* Lead Detail Header */}
      <div style={{
        padding: '14px 20px',
        background: 'var(--bg-secondary)',
        borderBottom: '1px solid var(--border-subtle)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '12px',
      }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <h2 style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-primary)' }}>
              {lead.name || 'Anonymous Visitor'}
            </h2>
            {isUrgent && <span className="badge badge-urgent">URGENT</span>}
            <span className={`badge badge-${lead.status || 'new'}`}>{lead.status}</span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '14px', fontSize: '12px', color: 'var(--text-muted)' }}>
            {lead.email && (
              <a href={`mailto:${lead.email}`} style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'inherit', textDecoration: 'none' }}>
                <Mail size={13} /> {lead.email}
              </a>
            )}
            {lead.phone && (
              <a href={`tel:${lead.phone}`} style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'inherit', textDecoration: 'none' }}>
                <Phone size={13} /> {lead.phone}
              </a>
            )}
            <span>ID #{lead.id}</span>
            <span>{new Date(lead.created_at).toLocaleString()}</span>
          </div>
        </div>

        {/* Action Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <select
            value={lead.status}
            onChange={(e) => onUpdateStatus(e.target.value)}
            style={{
              padding: '6px 10px',
              borderRadius: '6px',
              border: '1px solid var(--border-subtle)',
              background: 'var(--bg-tertiary)',
              color: 'var(--text-primary)',
              fontSize: '12px',
              fontWeight: 500,
              outline: 'none',
              cursor: 'pointer',
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
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '5px',
              padding: '6px 10px',
              borderRadius: '6px',
              border: '1px solid var(--border-subtle)',
              background: 'var(--bg-tertiary)',
              color: 'var(--text-secondary)',
              fontSize: '12px',
              cursor: 'pointer',
            }}
          >
            {copiedSummary ? <Check size={13} color="#10b981" /> : <Copy size={13} />}
            {copiedSummary ? 'Copied!' : 'Copy'}
          </button>

          <button
            onClick={onResendEmail}
            title="Resend notification email to clinic"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '5px',
              padding: '6px 10px',
              borderRadius: '6px',
              border: '1px solid var(--border-subtle)',
              background: 'var(--bg-tertiary)',
              color: 'var(--text-secondary)',
              fontSize: '12px',
              cursor: 'pointer',
            }}
          >
            <Mail size={13} /> Email
          </button>

          <button
            onClick={onRetryNotify}
            title="Retry webhook/SMS notify"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '5px',
              padding: '6px 10px',
              borderRadius: '6px',
              border: '1px solid var(--border-subtle)',
              background: 'var(--bg-tertiary)',
              color: 'var(--text-secondary)',
              fontSize: '12px',
              cursor: 'pointer',
            }}
          >
            <RefreshCw size={13} /> Notify
          </button>

          <button
            onClick={onOpenNoteModal}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              padding: '6px 10px',
              borderRadius: '6px',
              border: '1px solid var(--border-subtle)',
              background: 'var(--bg-tertiary)',
              color: 'var(--text-secondary)',
              fontSize: '12px',
              cursor: 'pointer',
            }}
          >
            <Plus size={13} /> Note
          </button>

          <button
            onClick={onOpenTaskModal}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              padding: '6px 10px',
              borderRadius: '6px',
              border: '1px solid var(--brand-green)',
              background: 'var(--brand-green)',
              color: '#fff',
              fontSize: '12px',
              cursor: 'pointer',
            }}
          >
            <Plus size={13} /> Task
          </button>
        </div>
      </div>

      {/* Messages Timeline */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '20px',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
      }}>
        {messages.length === 0 && notes.length === 0 ? (
          <div style={{ textAlign: 'center', color: 'var(--text-muted)', margin: 'auto' }}>
            <FileText size={32} style={{ marginBottom: '8px', opacity: 0.5 }} />
            <div>No previous messages recorded in this conversation.</div>
          </div>
        ) : (
          <>
            {messages.map((m) => {
              const isUser = m.role === 'user';
              return (
                <div
                  key={m.id}
                  style={{
                    alignSelf: isUser ? 'flex-start' : 'flex-end',
                    maxWidth: '75%',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: isUser ? 'flex-start' : 'flex-end',
                  }}
                >
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '3px' }}>
                    {isUser ? 'Visitor' : 'Concierge AI'}
                  </span>
                  <div style={{
                    padding: '10px 14px',
                    borderRadius: isUser ? '14px 14px 14px 2px' : '14px 14px 2px 14px',
                    background: isUser ? 'var(--bg-secondary)' : 'var(--brand-green)',
                    color: isUser ? 'var(--text-primary)' : '#ffffff',
                    border: isUser ? '1px solid var(--border-subtle)' : 'none',
                    fontSize: '13px',
                    lineHeight: '1.45',
                    boxShadow: 'var(--shadow-sm)',
                    whiteSpace: 'pre-wrap',
                  }}>
                    {m.body}
                  </div>
                  <span style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '3px' }}>
                    {new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>
              );
            })}

            {/* Internal Notes in Timeline */}
            {notes.map((n) => (
              <div
                key={`note-${n.id}`}
                style={{
                  alignSelf: 'center',
                  width: '90%',
                  background: 'rgba(245, 158, 11, 0.08)',
                  border: '1px solid rgba(245, 158, 11, 0.25)',
                  borderRadius: '10px',
                  padding: '8px 12px',
                  fontSize: '12px',
                  color: 'var(--text-primary)',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', color: '#d97706', fontWeight: 600, marginBottom: '2px' }}>
                  <span>📝 Internal Note</span>
                  <span style={{ fontSize: '10px', fontWeight: 400 }}>{new Date(n.created_at).toLocaleString()}</span>
                </div>
                <div>{n.note}</div>
              </div>
            ))}
          </>
        )}
      </div>

      {/* AI Assistance Panel & Result Preview */}
      {aiResult && (
        <div style={{
          padding: '12px 16px',
          background: 'var(--bg-secondary)',
          borderTop: '1px solid var(--border-subtle)',
          borderLeft: '4px solid #8b5cf6',
          margin: '0 20px',
          borderRadius: '8px 8px 0 0',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: '#8b5cf6', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <Sparkles size={13} /> AI Generated Draft
            </span>
            <div style={{ display: 'flex', gap: '6px' }}>
              <button
                onClick={() => setReplyText(aiResult)}
                style={{
                  fontSize: '11px',
                  padding: '3px 8px',
                  borderRadius: '4px',
                  border: '1px solid var(--border-subtle)',
                  background: 'var(--bg-tertiary)',
                  cursor: 'pointer'
                }}
              >
                Insert into Composer
              </button>
              <button
                onClick={() => setAiResult(null)}
                style={{
                  fontSize: '11px',
                  padding: '3px 8px',
                  borderRadius: '4px',
                  border: 'none',
                  background: 'transparent',
                  color: 'var(--text-muted)',
                  cursor: 'pointer'
                }}
              >
                Dismiss
              </button>
            </div>
          </div>
          <div style={{ fontSize: '13px', color: 'var(--text-secondary)', whiteSpace: 'pre-wrap', maxHeight: '120px', overflowY: 'auto' }}>
            {aiResult}
          </div>
        </div>
      )}

      {/* AI Quick Actions Chips */}
      <div style={{
        padding: '8px 20px',
        background: 'var(--bg-secondary)',
        borderTop: '1px solid var(--border-subtle)',
        display: 'flex',
        gap: '6px',
        overflowX: 'auto',
      }}>
        {[
          { key: 'draft_email', label: '✉️ Draft Email' },
          { key: 'quick_reply', label: '💬 Quick Reply' },
          { key: 'summarize', label: '📋 Summarize' },
          { key: 'next_action', label: '🎯 Next Action' },
          { key: 'follow_up', label: '🔄 Follow Up' },
          { key: 'confirm', label: '✅ Confirm' },
          { key: 'shorten', label: '🔽 Shorten' },
          { key: 'warm', label: '🔥 Warmer' },
        ].map((item) => (
          <button
            key={item.key}
            onClick={() => handleTriggerAi(item.key)}
            disabled={aiLoadingAction !== null}
            style={{
              padding: '4px 10px',
              borderRadius: '6px',
              border: '1px solid var(--border-subtle)',
              background: aiLoadingAction === item.key ? 'rgba(139, 92, 246, 0.15)' : 'var(--bg-tertiary)',
              color: 'var(--text-secondary)',
              fontSize: '11px',
              fontWeight: 500,
              cursor: aiLoadingAction !== null ? 'not-allowed' : 'pointer',
              whiteSpace: 'nowrap',
              transition: 'all 0.15s ease'
            }}
          >
            {aiLoadingAction === item.key ? 'Thinking...' : item.label}
          </button>
        ))}
      </div>

      {/* Composer Input Area */}
      <div style={{
        padding: '12px 20px',
        background: 'var(--bg-secondary)',
        borderTop: '1px solid var(--border-subtle)',
        display: 'flex',
        gap: '10px',
        alignItems: 'flex-end',
      }}>
        <textarea
          value={replyText}
          onChange={(e) => setReplyText(e.target.value)}
          placeholder="Type reply or AI instructions (e.g., 'Offer 10:30 AM tomorrow')..."
          rows={2}
          style={{
            flex: 1,
            padding: '10px 12px',
            borderRadius: '8px',
            border: '1px solid var(--border-subtle)',
            background: 'var(--bg-primary)',
            color: 'var(--text-primary)',
            fontSize: '13px',
            fontFamily: 'inherit',
            resize: 'none',
            outline: 'none',
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
        />

        <button
          onClick={handleSend}
          disabled={!replyText.trim() || isSending}
          style={{
            padding: '10px 16px',
            borderRadius: '8px',
            border: 'none',
            background: 'var(--brand-green)',
            color: '#ffffff',
            fontWeight: 600,
            fontSize: '13px',
            cursor: !replyText.trim() || isSending ? 'not-allowed' : 'pointer',
            opacity: !replyText.trim() || isSending ? 0.6 : 1,
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <Send size={14} /> Send
        </button>
      </div>
    </main>
  );
};
