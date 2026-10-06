import React from 'react';
import { Search, AlertCircle, Calendar, Clock, Sparkles, FileText, CheckSquare, Inbox, X, Filter } from 'lucide-react';
import type { Lead, CategoryFilter } from '../types';

interface SidebarProps {
  category: CategoryFilter;
  onSelectCategory: (cat: CategoryFilter) => void;
  searchQuery: string;
  onSearchChange: (query: string) => void;
  statusFilter: string;
  onStatusFilterChange: (status: string) => void;
  intentFilter: string;
  onIntentFilterChange: (intent: string) => void;
  availableIntents: string[];
  leads: Lead[];
  activeLeadId: number | null;
  onSelectLead: (leadId: number) => void;
  isLoading: boolean;
}

// Generate consistent avatar color based on name string
function getAvatarGradient(name?: string): string {
  if (!name) return 'linear-gradient(135deg, #059669, #10b981)';
  const colors = [
    'linear-gradient(135deg, #059669, #10b981)',
    'linear-gradient(135deg, #2563eb, #3b82f6)',
    'linear-gradient(135deg, #7c3aed, #8b5cf6)',
    'linear-gradient(135deg, #d97706, #f59e0b)',
    'linear-gradient(135deg, #0284c7, #0ea5e9)',
    'linear-gradient(135deg, #dc2626, #ef4444)',
  ];
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  return colors[Math.abs(hash) % colors.length];
}

function getInitials(name?: string): string {
  if (!name) return 'PT';
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function formatRelativeTime(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMin / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMin < 1) return 'Just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return `${diffDays}d ago`;
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  } catch {
    return dateStr;
  }
}

export const Sidebar: React.FC<SidebarProps> = ({
  category,
  onSelectCategory,
  searchQuery,
  onSearchChange,
  statusFilter,
  onStatusFilterChange,
  intentFilter,
  onIntentFilterChange,
  availableIntents,
  leads,
  activeLeadId,
  onSelectLead,
  isLoading,
}) => {
  const tabs: { key: CategoryFilter; label: string; icon: React.ReactNode }[] = [
    { key: 'all', label: 'All', icon: <Inbox size={13} /> },
    { key: 'new', label: 'New', icon: <Sparkles size={13} /> },
    { key: 'waiting', label: 'Waiting', icon: <Clock size={13} /> },
    { key: 'appointment', label: 'Appts', icon: <Calendar size={13} /> },
    { key: 'urgent', label: 'Urgent', icon: <AlertCircle size={13} /> },
    { key: 'notes', label: 'Notes', icon: <FileText size={13} /> },
    { key: 'tasks', label: 'Tasks', icon: <CheckSquare size={13} /> },
  ];

  return (
    <aside style={{
      width: '330px',
      background: 'var(--bg-secondary)',
      borderRight: '1px solid var(--border-subtle)',
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      flexShrink: 0,
      overflow: 'hidden',
    }}>
      {/* Category Tabs */}
      <div style={{
        display: 'flex',
        padding: '10px 12px',
        borderBottom: '1px solid var(--border-subtle)',
        gap: '4px',
        overflowX: 'auto',
        background: 'var(--bg-primary)',
      }}>
        {tabs.map((tab) => {
          const isActive = category === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => onSelectCategory(tab.key)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
                padding: '6px 11px',
                borderRadius: '8px',
                border: 'none',
                background: isActive ? 'var(--brand-gradient)' : 'transparent',
                color: isActive ? '#ffffff' : 'var(--text-secondary)',
                fontSize: '12px',
                fontWeight: isActive ? 700 : 500,
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                transition: 'all 0.15s cubic-bezier(0.4, 0, 0.2, 1)',
                boxShadow: isActive ? '0 2px 8px var(--brand-accent-glow)' : 'none',
              }}
            >
              {tab.icon}
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* Search Input Bar */}
      <div style={{
        padding: '10px 14px',
        borderBottom: '1px solid var(--border-subtle)',
        background: 'var(--bg-secondary)',
      }}>
        <div style={{
          position: 'relative',
          display: 'flex',
          alignItems: 'center',
        }}>
          <Search size={14} style={{ position: 'absolute', left: '11px', color: 'var(--text-muted)' }} />
          <input
            type="text"
            placeholder="Search patient, phone, symptoms..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            style={{
              width: '100%',
              padding: '8px 30px 8px 32px',
              borderRadius: '8px',
              border: '1px solid var(--border-subtle)',
              background: 'var(--bg-tertiary)',
              color: 'var(--text-primary)',
              fontSize: '12px',
              outline: 'none',
              transition: 'border-color 0.15s ease',
            }}
            onFocus={(e) => (e.target.style.borderColor = 'var(--brand-accent)')}
            onBlur={(e) => (e.target.style.borderColor = 'var(--border-subtle)')}
          />
          {searchQuery && (
            <button
              onClick={() => onSearchChange('')}
              style={{
                position: 'absolute',
                right: '8px',
                background: 'transparent',
                border: 'none',
                color: 'var(--text-muted)',
                cursor: 'pointer',
                padding: '2px',
                display: 'flex',
              }}
            >
              <X size={13} />
            </button>
          )}
        </div>

        {/* Lead Count Pill */}
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginTop: '8px',
          fontSize: '11px',
          color: 'var(--text-muted)',
        }}>
          <span>Showing <b>{leads.length}</b> inquiries</span>
          {category !== 'all' && (
            <span style={{ textTransform: 'capitalize', color: 'var(--brand-accent)', fontWeight: 600 }}>
              Tab: {category}
            </span>
          )}
        </div>
      </div>

      {/* Dropdown Filters (only in 'all' view) */}
      {category === 'all' && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: '8px',
          padding: '8px 14px',
          borderBottom: '1px solid var(--border-subtle)',
          background: 'var(--bg-tertiary)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Filter size={11} color="var(--text-muted)" />
            <select
              value={statusFilter}
              onChange={(e) => onStatusFilterChange(e.target.value)}
              style={{
                width: '100%',
                padding: '5px 8px',
                borderRadius: '6px',
                border: '1px solid var(--border-subtle)',
                background: 'var(--bg-secondary)',
                color: 'var(--text-secondary)',
                fontSize: '11px',
                fontWeight: 500,
                outline: 'none',
                cursor: 'pointer',
              }}
            >
              <option value="">Status: All</option>
              <option value="new">New</option>
              <option value="contacted">Contacted</option>
              <option value="qualified">Qualified</option>
              <option value="booked">Booked</option>
              <option value="closed">Closed</option>
              <option value="spam">Spam</option>
            </select>
          </div>

          <select
            value={intentFilter}
            onChange={(e) => onIntentFilterChange(e.target.value)}
            style={{
              width: '100%',
              padding: '5px 8px',
              borderRadius: '6px',
              border: '1px solid var(--border-subtle)',
              background: 'var(--bg-secondary)',
              color: 'var(--text-secondary)',
              fontSize: '11px',
              fontWeight: 500,
              outline: 'none',
              cursor: 'pointer',
            }}
          >
            <option value="">Intent: All</option>
            {availableIntents.map((it) => (
              <option key={it} value={it}>
                {it.replace(/_/g, ' ')}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Lead Cards List */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {isLoading ? (
          <div style={{ padding: '40px 20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
            <div className="pulse-indicator" style={{ margin: '0 auto 12px auto', width: '12px', height: '12px' }} />
            Syncing leads from database...
          </div>
        ) : leads.length === 0 ? (
          <div style={{ padding: '48px 24px', textAlign: 'center', color: 'var(--text-muted)' }}>
            <div style={{ fontSize: '32px', marginBottom: '8px' }}>🔍</div>
            <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '4px' }}>
              No inquiries found
            </div>
            <div style={{ fontSize: '12px', lineHeight: 1.4 }}>
              Try clearing filters or search query to view all patient records.
            </div>
          </div>
        ) : (
          leads.map((lead) => {
            const isSelected = activeLeadId === lead.id;
            const isUrgent = lead.urgency === 'urgent' || lead.urgency === 'high';
            const relativeTime = formatRelativeTime(lead.created_at);
            const initials = getInitials(lead.name);
            const avatarBg = getAvatarGradient(lead.name);

            return (
              <div
                key={lead.id}
                onClick={() => onSelectLead(lead.id)}
                style={{
                  padding: '12px 14px',
                  borderBottom: '1px solid var(--border-subtle)',
                  background: isSelected ? 'var(--bg-elevated)' : 'transparent',
                  borderLeft: isSelected ? '3px solid var(--brand-accent)' : '3px solid transparent',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                  position: 'relative',
                }}
                onMouseEnter={(e) => {
                  if (!isSelected) e.currentTarget.style.background = 'var(--bg-hover)';
                }}
                onMouseLeave={(e) => {
                  if (!isSelected) e.currentTarget.style.background = 'transparent';
                }}
              >
                <div style={{ display: 'flex', gap: '10px', alignItems: 'flex-start' }}>
                  {/* Patient Avatar */}
                  <div style={{
                    width: '34px',
                    height: '34px',
                    borderRadius: '10px',
                    background: avatarBg,
                    color: '#ffffff',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontWeight: 700,
                    fontSize: '12px',
                    flexShrink: 0,
                    boxShadow: 'var(--shadow-sm)',
                  }}>
                    {initials}
                  </div>

                  {/* Patient Info */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '2px' }}>
                      <span style={{
                        fontWeight: 700,
                        fontSize: '13px',
                        color: 'var(--text-primary)',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}>
                        {lead.name || 'Anonymous Visitor'}
                      </span>
                      <span style={{ fontSize: '10px', color: 'var(--text-muted)', flexShrink: 0, marginLeft: '6px' }}>
                        {relativeTime}
                      </span>
                    </div>

                    <div style={{
                      fontSize: '12px',
                      color: 'var(--text-secondary)',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      marginBottom: '6px',
                    }}>
                      {lead.message || lead.phone || lead.email || 'Website inquiry received'}
                    </div>

                    {/* Metadata Badges */}
                    <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', alignItems: 'center' }}>
                      <span className={`badge badge-${lead.status || 'new'}`}>
                        {lead.status || 'new'}
                      </span>
                      {isUrgent && (
                        <span className="badge badge-urgent">
                          Urgent
                        </span>
                      )}
                      {lead.service && (
                        <span style={{
                          fontSize: '10px',
                          fontWeight: 500,
                          padding: '1px 6px',
                          borderRadius: '4px',
                          background: 'var(--bg-tertiary)',
                          color: 'var(--text-muted)',
                          border: '1px solid var(--border-subtle)',
                        }}>
                          {lead.service}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
};
