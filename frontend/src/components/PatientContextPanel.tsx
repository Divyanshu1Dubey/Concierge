import { User, Calendar, Shield, MessageSquare, CheckCircle2, Circle, Plus } from 'lucide-react';
import type { Lead, Note, Task } from '../types';

interface PatientContextPanelProps {
  lead: Lead | null;
  notes: Note[];
  tasks: Task[];
  onCompleteTask: (taskId: number) => void;
  onOpenNoteModal: () => void;
  onOpenTaskModal: () => void;
}

export const PatientContextPanel: React.FC<PatientContextPanelProps> = ({
  lead,
  notes,
  tasks,
  onCompleteTask,
  onOpenNoteModal,
  onOpenTaskModal,
}) => {
  if (!lead) {
    return (
      <aside style={{
        width: '300px',
        background: 'var(--bg-secondary)',
        borderLeft: '1px solid var(--border-subtle)',
        padding: '24px',
        color: 'var(--text-muted)',
        textAlign: 'center',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: '13px',
      }}>
        <div>Select a conversation to view patient details and open tasks.</div>
      </aside>
    );
  }

  const patientTasks = tasks.filter((t) => t.lead_id === lead.id || !t.lead_id);

  return (
    <aside style={{
      width: '320px',
      background: 'var(--bg-secondary)',
      borderLeft: '1px solid var(--border-subtle)',
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      overflowY: 'auto',
      flexShrink: 0,
    }}>
      {/* Patient Profile Card */}
      <div style={{ padding: '16px', borderBottom: '1px solid var(--border-subtle)' }}>
        <h3 style={{ fontSize: '13px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)', marginBottom: '12px' }}>
          Patient Context
        </h3>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '13px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <User size={15} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
            <div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Full Name</div>
              <div style={{ fontWeight: 600 }}>{lead.name || 'Not provided'}</div>
            </div>
          </div>

          {lead.service && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '14px', flexShrink: 0 }}>🩺</span>
              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Service Requested</div>
                <div style={{ fontWeight: 500 }}>{lead.service}</div>
              </div>
            </div>
          )}

          {(lead.preferred_date || lead.preferred_time) && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Calendar size={15} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Preferred Window</div>
                <div style={{ fontWeight: 500 }}>
                  {[lead.preferred_date, lead.preferred_time].filter(Boolean).join(' ')}
                </div>
              </div>
            </div>
          )}

          {lead.insurance && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Shield size={15} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Insurance Coverage</div>
                <div style={{ fontWeight: 500 }}>{lead.insurance}</div>
              </div>
            </div>
          )}

          {lead.message && (
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
              <MessageSquare size={15} style={{ color: 'var(--text-muted)', flexShrink: 0, marginTop: '2px' }} />
              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Initial Inquiry</div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', background: 'var(--bg-tertiary)', padding: '6px 8px', borderRadius: '6px' }}>
                  {lead.message}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Actionable Tasks Checklist */}
      <div style={{ padding: '16px', borderBottom: '1px solid var(--border-subtle)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
          <h3 style={{ fontSize: '13px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)' }}>
            Tasks ({patientTasks.length})
          </h3>
          <button
            onClick={onOpenTaskModal}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--brand-accent)',
              fontSize: '12px',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '2px',
            }}
          >
            <Plus size={13} /> Add
          </button>
        </div>

        {patientTasks.length === 0 ? (
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontStyle: 'italic' }}>
            No open tasks for this conversation.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {patientTasks.map((t) => (
              <div
                key={t.id}
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '8px',
                  padding: '8px',
                  borderRadius: '6px',
                  background: 'var(--bg-tertiary)',
                  fontSize: '12px',
                }}
              >
                <button
                  onClick={() => onCompleteTask(t.id)}
                  title="Mark task completed"
                  style={{
                    background: 'transparent',
                    border: 'none',
                    cursor: 'pointer',
                    color: t.completed ? '#10b981' : 'var(--text-muted)',
                    padding: 0,
                    marginTop: '1px',
                  }}
                >
                  {t.completed ? <CheckCircle2 size={16} /> : <Circle size={16} />}
                </button>
                <div style={{ flex: 1 }}>
                  <div style={{
                    fontWeight: 500,
                    textDecoration: t.completed ? 'line-through' : 'none',
                    color: t.completed ? 'var(--text-muted)' : 'var(--text-primary)',
                  }}>
                    {t.title}
                  </div>
                  {t.due_at && (
                    <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '2px' }}>
                      Due: {new Date(t.due_at).toLocaleDateString()}
                    </div>
                  )}
                </div>
                {t.priority === 'urgent' && (
                  <span className="badge badge-urgent" style={{ fontSize: '9px', padding: '1px 4px' }}>
                    Urgent
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Internal Notes Quick View */}
      <div style={{ padding: '16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
          <h3 style={{ fontSize: '13px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)' }}>
            Notes ({notes.length})
          </h3>
          <button
            onClick={onOpenNoteModal}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--brand-accent)',
              fontSize: '12px',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '2px',
            }}
          >
            <Plus size={13} /> Add
          </button>
        </div>

        {notes.length === 0 ? (
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontStyle: 'italic' }}>
            No internal staff notes yet.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {notes.map((n) => (
              <div
                key={n.id}
                style={{
                  padding: '8px 10px',
                  borderRadius: '6px',
                  background: 'var(--bg-tertiary)',
                  fontSize: '12px',
                  color: 'var(--text-secondary)',
                }}
              >
                <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '3px' }}>
                  {new Date(n.created_at).toLocaleString()}
                </div>
                <div>{n.note}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
};
