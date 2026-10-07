import React from 'react';
import { User, Calendar, Shield, MessageSquare, CheckCircle2, Circle, Plus, Phone, Mail, Clock, CheckSquare } from 'lucide-react';
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
        width: '320px',
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
        <div>Select an inquiry to view patient profile, records, and tasks.</div>
      </aside>
    );
  }

  const patientTasks = tasks.filter((t) => t.lead_id === lead.id || !t.lead_id);

  return (
    <aside style={{
      width: '330px',
      background: 'var(--bg-secondary)',
      borderLeft: '1px solid var(--border-subtle)',
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      overflowY: 'auto',
      flexShrink: 0,
    }}>
      {/* Patient Profile Section */}
      <div style={{ padding: '18px 20px', borderBottom: '1px solid var(--border-subtle)' }}>
        <h3 className="font-display" style={{
          fontSize: '13px',
          fontWeight: 800,
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          color: 'var(--text-muted)',
          marginBottom: '14px',
        }}>
          Patient Profile
        </h3>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '13px' }}>
          {/* Full Name */}
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
            <div style={{
              width: '28px',
              height: '28px',
              borderRadius: '8px',
              background: 'var(--bg-tertiary)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--text-muted)',
              flexShrink: 0,
            }}>
              <User size={15} />
            </div>
            <div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 600 }}>Full Name</div>
              <div style={{ fontWeight: 700, color: 'var(--text-primary)' }}>
                {lead.name || 'Anonymous Visitor'}
              </div>
            </div>
          </div>

          {/* Contact Details */}
          {(lead.phone || lead.email) && (
            <div style={{
              background: 'var(--bg-tertiary)',
              borderRadius: '10px',
              padding: '10px 12px',
              display: 'flex',
              flexDirection: 'column',
              gap: '6px',
            }}>
              {lead.phone && (
                <a
                  href={`tel:${lead.phone}`}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    fontSize: '12px',
                    color: 'var(--brand-accent)',
                    textDecoration: 'none',
                    fontWeight: 600,
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
                    gap: '8px',
                    fontSize: '12px',
                    color: 'var(--text-secondary)',
                    textDecoration: 'none',
                  }}
                >
                  <Mail size={13} /> {lead.email}
                </a>
              )}
            </div>
          )}

          {/* Service Requested */}
          {lead.service && (
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
              <div style={{
                width: '28px',
                height: '28px',
                borderRadius: '8px',
                background: 'var(--bg-tertiary)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '13px',
                flexShrink: 0,
              }}>
                🩺
              </div>
              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 600 }}>Service Requested</div>
                <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{lead.service}</div>
              </div>
            </div>
          )}

          {/* Preferred Time / Date */}
          {(lead.preferred_date || lead.preferred_time) && (
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
              <div style={{
                width: '28px',
                height: '28px',
                borderRadius: '8px',
                background: 'var(--bg-tertiary)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--text-muted)',
                flexShrink: 0,
              }}>
                <Calendar size={15} />
              </div>
              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 600 }}>Preferred Schedule</div>
                <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                  {[lead.preferred_date, lead.preferred_time].filter(Boolean).join(' at ')}
                </div>
              </div>
            </div>
          )}

          {/* Insurance */}
          {lead.insurance && (
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
              <div style={{
                width: '28px',
                height: '28px',
                borderRadius: '8px',
                background: 'var(--bg-tertiary)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--text-muted)',
                flexShrink: 0,
              }}>
                <Shield size={15} />
              </div>
              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 600 }}>Insurance / Carrier</div>
                <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{lead.insurance}</div>
              </div>
            </div>
          )}

          {/* Intake Message */}
          {lead.message && (
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
              <div style={{
                width: '28px',
                height: '28px',
                borderRadius: '8px',
                background: 'var(--bg-tertiary)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--text-muted)',
                flexShrink: 0,
              }}>
                <MessageSquare size={15} />
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 600, marginBottom: '3px' }}>
                  Intake Description
                </div>
                <div style={{
                  fontSize: '12px',
                  color: 'var(--text-secondary)',
                  background: 'var(--bg-tertiary)',
                  padding: '8px 10px',
                  borderRadius: '8px',
                  lineHeight: 1.45,
                }}>
                  {lead.message}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Actionable Tasks Checklist */}
      <div style={{ padding: '18px 20px', borderBottom: '1px solid var(--border-subtle)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <CheckSquare size={14} color="var(--brand-accent)" />
            <h3 className="font-display" style={{
              fontSize: '13px',
              fontWeight: 800,
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              color: 'var(--text-muted)',
              margin: 0,
            }}>
              Tasks ({patientTasks.length})
            </h3>
          </div>
          <button
            onClick={onOpenTaskModal}
            className="btn-action"
            style={{
              padding: '3px 8px',
              fontSize: '11px',
              color: 'var(--brand-accent)',
              borderColor: 'rgba(16, 185, 129, 0.3)',
            }}
          >
            <Plus size={12} /> Add Task
          </button>
        </div>

        {patientTasks.length === 0 ? (
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontStyle: 'italic', padding: '6px 0' }}>
            No pending tasks for this patient.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {patientTasks.map((t) => (
              <div
                key={t.id}
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '10px',
                  padding: '9px 10px',
                  borderRadius: '8px',
                  background: 'var(--bg-tertiary)',
                  fontSize: '12px',
                  border: '1px solid var(--border-subtle)',
                  transition: 'background 0.15s ease',
                }}
              >
                <button
                  onClick={() => onCompleteTask(t.id)}
                  title={t.completed ? 'Completed' : 'Mark as completed'}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    cursor: 'pointer',
                    color: t.completed ? '#10b981' : 'var(--text-muted)',
                    padding: 0,
                    marginTop: '1px',
                    display: 'flex',
                  }}
                >
                  {t.completed ? <CheckCircle2 size={16} /> : <Circle size={16} />}
                </button>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontWeight: 600,
                    textDecoration: t.completed ? 'line-through' : 'none',
                    color: t.completed ? 'var(--text-muted)' : 'var(--text-primary)',
                    wordBreak: 'break-word',
                  }}>
                    {t.title}
                  </div>
                  {t.due_at && (
                    <div style={{
                      fontSize: '10px',
                      color: 'var(--text-muted)',
                      marginTop: '3px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '3px',
                    }}>
                      <Clock size={10} /> Due: {new Date(t.due_at).toLocaleDateString([], { month: 'short', day: 'numeric' })}
                    </div>
                  )}
                </div>
                {t.priority === 'urgent' && (
                  <span className="badge badge-urgent" style={{ fontSize: '9px', padding: '1px 5px' }}>
                    Urgent
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Internal Staff Notes Quick View */}
      <div style={{ padding: '18px 20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
          <h3 className="font-display" style={{
            fontSize: '13px',
            fontWeight: 800,
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            color: 'var(--text-muted)',
            margin: 0,
          }}>
            Staff Notes ({notes.length})
          </h3>
          <button
            onClick={onOpenNoteModal}
            className="btn-action"
            style={{
              padding: '3px 8px',
              fontSize: '11px',
              color: 'var(--brand-accent)',
              borderColor: 'rgba(16, 185, 129, 0.3)',
            }}
          >
            <Plus size={12} /> Add Note
          </button>
        </div>

        {notes.length === 0 ? (
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontStyle: 'italic', padding: '6px 0' }}>
            No internal staff notes recorded yet.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {notes.map((n) => (
              <div
                key={n.id}
                style={{
                  padding: '9px 12px',
                  borderRadius: '8px',
                  background: 'var(--bg-tertiary)',
                  fontSize: '12px',
                  color: 'var(--text-secondary)',
                  border: '1px solid var(--border-subtle)',
                }}
              >
                <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '4px', fontWeight: 500 }}>
                  {new Date(n.created_at).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })}
                </div>
                <div style={{ lineHeight: 1.45, whiteSpace: 'pre-wrap' }}>{n.note}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
};
