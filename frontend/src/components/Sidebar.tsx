import React from 'react';
import { Search, AlertCircle, Calendar, Clock, Sparkles, FileText, CheckSquare, Inbox } from 'lucide-react';
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
      width: '320px',
      background: 'var(--bg-secondary)',
      borderRight: '1px solid var(--border-subtle)',
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      flexShrink: 0,
    }}>
      {/* Category Tabs */}
      <div style={{
        display: 'flex',
        padding: '8px 10px',
        borderBottom: '1px solid var(--border-subtle)',
        gap: '4px',
        overflowX: 'auto',
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
                padding: '6px 10px',
                borderRadius: '6px',
                border: 'none',
                background: isActive ? 'var(--brand-green)' : 'transparent',
                color: isActive ? '#fff' : 'var(--text-secondary)',
                fontSize: '12px',
                fontWeight: isActive ? 600 : 500,
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                transition: 'all 0.15s ease'
              }}
            >
              {tab.icon}
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Search Input */}
      <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--border-subtle)' }}>
        <div style={{
          position: 'relative',
          display: 'flex',
          alignItems: 'center',
        }}>
          <Search size={14} style={{ position: 'absolute', left: '10px', color: 'var(--text-muted)' }} />
          <input
            type="text"
            placeholder="Search patient, phone, query..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            style={{
              width: '100%',
              padding: '7px 10px 7px 30px',
              borderRadius: '8px',
              border: '1px solid var(--border-subtle)',
              background: 'var(--bg-tertiary)',
              color: 'var(--text-primary)',
              fontSize: '12px',
              outline: 'none',
            }}
          />
        </div>
      </div>

      {/* Dropdown Filters (only if category is 'all') */}
      {category === 'all' && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: '8px',
          padding: '8px 12px',
          borderBottom: '1px solid var(--border-subtle)',
        }}>
          <select
            value={statusFilter}
            onChange={(e) => onStatusFilterChange(e.target.value)}
            style={{
              padding: '6px',
              borderRadius: '6px',
              border: '1px solid var(--border-subtle)',
              background: 'var(--bg-tertiary)',
              color: 'var(--text-secondary)',
              fontSize: '11px',
              outline: 'none',
            }}
          >
            <option value="">All Statuses</option>
            <option value="new">New</option>
            <option value="contacted">Contacted</option>
            <option value="qualified">Qualified</option>
            <option value="booked">Booked</option>
            <option value="closed">Closed</option>
            <option value="spam">Spam</option>
          </select>

          <select
            value={intentFilter}
            onChange={(e) => onIntentFilterChange(e.target.value)}
            style={{
              padding: '6px',
              borderRadius: '6px',
              border: '1px solid var(--border-subtle)',
              background: 'var(--bg-tertiary)',
              color: 'var(--text-secondary)',
              fontSize: '11px',
              outline: 'none',
            }}
          >
            <option value="">All Intents</option>
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
          <div style={{ padding: '30px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
            Loading conversations...
          </div>
        ) : leads.length === 0 ? (
          <div style={{ padding: '40px 20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
            No matching conversations found
          </div>
        ) : (
          leads.map((lead) => {
            const isSelected = activeLeadId === lead.id;
            const isUrgent = lead.urgency === 'urgent' || lead.urgency === 'high';
            const formattedTime = new Date(lead.created_at).toLocaleDateString([], {
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            });

            return (
              <div
                key={lead.id}
                onClick={() => onSelectLead(lead.id)}
                style={{
                  padding: '12px 14px',
                  borderBottom: '1px solid var(--border-subtle)',
                  background: isSelected ? 'var(--bg-tertiary)' : 'transparent',
                  borderLeft: isSelected ? '3px solid var(--brand-accent)' : '3px solid transparent',
                  cursor: 'pointer',
                  transition: 'background 0.15s ease',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '3px' }}>
                  <span style={{ fontWeight: 600, fontSize: '13px', color: 'var(--text-primary)' }}>
                    {lead.name || 'Anonymous Visitor'}
                  </span>
                  <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                    {formattedTime}
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
                  {lead.email || lead.phone || lead.message || 'No additional details'}
                </div>

                <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
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
                      fontSize: '11px',
                      padding: '1px 6px',
                      borderRadius: '4px',
                      background: 'var(--bg-tertiary)',
                      color: 'var(--text-muted)',
                    }}>
                      {lead.service}
                    </span>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
};
