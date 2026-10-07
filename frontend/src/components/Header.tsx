import React, { useState, useEffect } from 'react';
import { Moon, Sun, Bell, BellOff, LogOut, RefreshCw, Sparkles, AlertTriangle, CheckSquare, Mail, MessageSquare } from 'lucide-react';
import type { DashboardStats, CategoryFilter } from '../types';

interface HeaderProps {
  stats: DashboardStats | null;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
  soundEnabled: boolean;
  onToggleSound: () => void;
  onRefresh: () => void;
  onLogout: () => void;
  isRefreshing: boolean;
  onSelectCategory?: (category: CategoryFilter) => void;
  activeCategory?: CategoryFilter;
}

export const Header: React.FC<HeaderProps> = ({
  stats,
  theme,
  onToggleTheme,
  soundEnabled,
  onToggleSound,
  onRefresh,
  onLogout,
  isRefreshing,
  onSelectCategory,
  activeCategory,
}) => {
  const [currentTime, setCurrentTime] = useState<string>('');

  useEffect(() => {
    const updateTime = () => {
      setCurrentTime(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
    };
    updateTime();
    const timer = setInterval(updateTime, 1000);
    return () => clearInterval(timer);
  }, []);

  const kpis = [
    {
      id: 'all',
      label: 'Conversations',
      value: stats?.total_conversations ?? 0,
      icon: <MessageSquare size={13} />,
      color: 'var(--text-primary)',
      category: 'all' as CategoryFilter,
    },
    {
      id: 'new',
      label: 'New Leads',
      value: stats?.new_leads ?? 0,
      icon: <Sparkles size={13} />,
      color: (stats?.new_leads || 0) > 0 ? '#f59e0b' : 'var(--text-primary)',
      badge: (stats?.new_leads || 0) > 0,
      badgeColor: '#f59e0b',
      category: 'new' as CategoryFilter,
    },
    {
      id: 'emails',
      label: 'Emails Sent',
      value: stats?.emails_sent ?? 0,
      icon: <Mail size={13} />,
      color: 'var(--text-primary)',
    },
    {
      id: 'tasks',
      label: 'Open Tasks',
      value: stats?.open_tasks ?? 0,
      icon: <CheckSquare size={13} />,
      color: 'var(--text-primary)',
      category: 'tasks' as CategoryFilter,
    },
    {
      id: 'urgent',
      label: 'Overdue / Urgent',
      value: stats?.overdue_tasks ?? 0,
      icon: <AlertTriangle size={13} />,
      color: (stats?.overdue_tasks || 0) > 0 ? '#ef4444' : 'var(--text-primary)',
      badge: (stats?.overdue_tasks || 0) > 0,
      badgeColor: '#ef4444',
      category: 'urgent' as CategoryFilter,
    },
    {
      id: 'drafts',
      label: 'AI Drafts',
      value: stats?.pending_drafts ?? 0,
      icon: <Sparkles size={13} />,
      color: '#8b5cf6',
    },
  ];

  return (
    <header style={{
      background: 'var(--bg-secondary)',
      borderBottom: '1px solid var(--border-subtle)',
      padding: '12px 24px',
      display: 'flex',
      flexDirection: 'column',
      gap: '12px',
      zIndex: 20,
      boxShadow: 'var(--shadow-sm)',
    }}>
      {/* Top Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        {/* Brand identity */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{
            fontSize: '22px',
            background: 'var(--brand-gradient)',
            color: '#fff',
            width: '42px',
            height: '42px',
            borderRadius: '12px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 4px 14px var(--brand-accent-glow)',
            flexShrink: 0,
          }}>
            🦷
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <h1 className="font-display" style={{
                fontSize: '18px',
                fontWeight: 800,
                letterSpacing: '-0.02em',
                margin: 0,
                color: 'var(--text-primary)',
              }}>
                HeyJarvis
              </h1>
              <span style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px',
                fontSize: '11px',
                fontWeight: 600,
                color: 'var(--brand-accent)',
                background: 'var(--brand-green-light)',
                padding: '2px 8px',
                borderRadius: '999px',
                border: '1px solid rgba(16, 185, 129, 0.25)',
              }}>
                <span className="pulse-indicator" />
                AI Front Desk
              </span>
            </div>
            <div style={{
              fontSize: '12px',
              color: 'var(--text-muted)',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              marginTop: '1px',
            }}>
              <span style={{ fontWeight: 500, color: 'var(--text-secondary)' }}>
                {stats?.tenant_name || 'Raleigh Comprehensive Dentistry'}
              </span>
              <span>•</span>
              <span style={{ fontSize: '11px' }}>Database Synced</span>
            </div>
          </div>
        </div>

        {/* Control Actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div style={{
            fontSize: '12px',
            color: 'var(--text-muted)',
            fontFamily: 'monospace',
            background: 'var(--bg-tertiary)',
            padding: '5px 10px',
            borderRadius: '6px',
            border: '1px solid var(--border-subtle)',
            marginRight: '4px',
          }}>
            {currentTime}
          </div>

          <a
            href="/frontdesk"
            title="Switch to Classic Frontdesk HTML UI"
            className="btn-action"
            style={{ fontSize: '12px' }}
          >
            Classic Desk
          </a>

          <button
            onClick={onRefresh}
            title="Refresh from Database"
            className="btn-action"
            disabled={isRefreshing}
          >
            <RefreshCw size={13} style={{
              animation: isRefreshing ? 'spin 1s linear infinite' : 'none',
              transformOrigin: 'center',
            }} />
            <span>{isRefreshing ? 'Syncing...' : 'Sync'}</span>
          </button>

          <button
            onClick={onToggleSound}
            title={soundEnabled ? 'Mute Audio Alerts' : 'Enable Audio Chimes'}
            className="btn-action"
            style={{
              color: soundEnabled ? 'var(--brand-accent)' : 'var(--text-muted)',
              borderColor: soundEnabled ? 'rgba(16, 185, 129, 0.3)' : 'var(--border-subtle)',
            }}
          >
            {soundEnabled ? <Bell size={14} /> : <BellOff size={14} />}
          </button>

          <button
            onClick={onToggleTheme}
            title={theme === 'dark' ? 'Switch to Light Theme' : 'Switch to Dark Theme'}
            className="btn-action"
          >
            {theme === 'dark' ? <Sun size={14} color="#f59e0b" /> : <Moon size={14} />}
          </button>

          <button
            onClick={onLogout}
            title="Sign Out"
            style={{
              background: 'rgba(239, 68, 68, 0.08)',
              border: '1px solid rgba(239, 68, 68, 0.2)',
              color: '#ef4444',
              padding: '6px 12px',
              borderRadius: '8px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '12px',
              fontWeight: 600,
              transition: 'all 0.15s ease',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(239, 68, 68, 0.16)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'rgba(239, 68, 68, 0.08)')}
          >
            <LogOut size={13} />
            <span>Sign Out</span>
          </button>
        </div>
      </div>

      {/* KPI Stats Strip */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(6, 1fr)',
        gap: '10px',
      }}>
        {kpis.map((item) => {
          const isFilterActive = item.category && activeCategory === item.category;
          return (
            <div
              key={item.id}
              onClick={() => {
                if (item.category && onSelectCategory) {
                  onSelectCategory(item.category);
                }
              }}
              style={{
                background: isFilterActive ? 'var(--bg-elevated)' : 'var(--bg-tertiary)',
                border: isFilterActive ? '1px solid var(--brand-accent)' : '1px solid var(--border-subtle)',
                boxShadow: isFilterActive ? '0 0 12px var(--brand-accent-glow)' : 'none',
                borderRadius: '10px',
                padding: '8px 12px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                cursor: item.category ? 'pointer' : 'default',
                transition: 'all 0.15s cubic-bezier(0.4, 0, 0.2, 1)',
              }}
              onMouseEnter={(e) => {
                if (item.category) {
                  e.currentTarget.style.transform = 'translateY(-1px)';
                  e.currentTarget.style.borderColor = 'var(--border-medium)';
                }
              }}
              onMouseLeave={(e) => {
                if (item.category) {
                  e.currentTarget.style.transform = 'translateY(0)';
                  if (!isFilterActive) e.currentTarget.style.borderColor = 'var(--border-subtle)';
                }
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ color: 'var(--text-muted)', display: 'flex' }}>
                  {item.icon}
                </span>
                <span style={{ fontSize: '11px', color: 'var(--text-secondary)', fontWeight: 600 }}>
                  {item.label}
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                <span className="font-display" style={{
                  fontSize: '17px',
                  fontWeight: 800,
                  color: item.color,
                }}>
                  {item.value}
                </span>
                {item.badge && (
                  <span style={{
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    backgroundColor: item.badgeColor,
                    display: 'inline-block',
                  }} />
                )}
              </div>
            </div>
          );
        })}
      </div>
    </header>
  );
};
