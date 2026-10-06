import React, { useState, useEffect } from 'react';
import { Moon, Sun, Bell, BellOff, LogOut, RefreshCw, Activity } from 'lucide-react';
import type { DashboardStats } from '../types';

interface HeaderProps {
  stats: DashboardStats | null;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
  soundEnabled: boolean;
  onToggleSound: () => void;
  onRefresh: () => void;
  onLogout: () => void;
  isRefreshing: boolean;
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

  return (
    <header style={{
      background: 'var(--bg-secondary)',
      borderBottom: '1px solid var(--border-subtle)',
      padding: '10px 20px',
      display: 'flex',
      flexDirection: 'column',
      gap: '10px',
      zIndex: 20,
    }}>
      {/* Top Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{
            fontSize: '24px',
            background: 'var(--brand-green)',
            color: '#fff',
            width: '40px',
            height: '40px',
            borderRadius: '10px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: 'var(--shadow-sm)'
          }}>
            🦷
          </div>
          <div>
            <h1 style={{ fontSize: '17px', fontWeight: 700, letterSpacing: '-0.02em', display: 'flex', alignItems: 'center', gap: '8px' }}>
              HeyJarvis Front Desk
              <span style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                fontSize: '11px',
                fontWeight: 600,
                color: 'var(--brand-accent)',
                background: 'rgba(16, 185, 129, 0.1)',
                padding: '2px 8px',
                borderRadius: '999px'
              }}>
                <Activity size={12} /> AI Live
              </span>
            </h1>
            <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              {stats?.tenant_name || 'Loading Clinic...'}
            </div>
          </div>
        </div>

        {/* Header Actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontFamily: 'monospace', marginRight: '6px' }}>
            {currentTime}
          </div>

          <a
            href="/frontdesk"
            title="Switch to Classic Frontdesk"
            style={{
              background: 'var(--bg-tertiary)',
              border: '1px solid var(--border-subtle)',
              color: 'var(--text-secondary)',
              textDecoration: 'none',
              padding: '6px 10px',
              borderRadius: '8px',
              fontSize: '12px',
              fontWeight: 500,
              display: 'flex',
              alignItems: 'center',
              gap: '4px'
            }}
          >
            Classic
          </a>

          <button
            onClick={onRefresh}
            title="Refresh Data"
            style={{
              background: 'var(--bg-tertiary)',
              border: '1px solid var(--border-subtle)',
              color: 'var(--text-secondary)',
              padding: '6px 10px',
              borderRadius: '8px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '12px',
              transition: 'all 0.15s ease'
            }}
          >
            <RefreshCw size={14} className={isRefreshing ? 'animate-spin' : ''} />
          </button>

          <button
            onClick={onToggleSound}
            title={soundEnabled ? 'Mute Sound Chimes' : 'Enable Sound Chimes'}
            style={{
              background: soundEnabled ? 'rgba(16, 185, 129, 0.1)' : 'var(--bg-tertiary)',
              border: '1px solid var(--border-subtle)',
              color: soundEnabled ? 'var(--brand-accent)' : 'var(--text-muted)',
              padding: '6px 10px',
              borderRadius: '8px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '12px'
            }}
          >
            {soundEnabled ? <Bell size={14} /> : <BellOff size={14} />}
          </button>

          <button
            onClick={onToggleTheme}
            title="Toggle Theme"
            style={{
              background: 'var(--bg-tertiary)',
              border: '1px solid var(--border-subtle)',
              color: 'var(--text-secondary)',
              padding: '6px 10px',
              borderRadius: '8px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '12px'
            }}
          >
            {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
          </button>

          <button
            onClick={onLogout}
            title="Log Out"
            style={{
              background: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid rgba(239, 68, 68, 0.2)',
              color: '#ef4444',
              padding: '6px 12px',
              borderRadius: '8px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '12px',
              fontWeight: 500
            }}
          >
            <LogOut size={14} /> Log out
          </button>
        </div>
      </div>

      {/* KPI Stats Strip */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(6, 1fr)',
        gap: '8px',
      }}>
        {[
          { label: 'Conversations', value: stats?.total_conversations ?? 0, color: 'var(--text-primary)' },
          { label: 'New Leads', value: stats?.new_leads ?? 0, color: (stats?.new_leads || 0) > 0 ? '#f59e0b' : 'var(--text-primary)', highlight: (stats?.new_leads || 0) > 0 },
          { label: 'Emails Sent', value: stats?.emails_sent ?? 0, color: 'var(--text-primary)' },
          { label: 'Open Tasks', value: stats?.open_tasks ?? 0, color: 'var(--text-primary)' },
          { label: 'Overdue', value: stats?.overdue_tasks ?? 0, color: (stats?.overdue_tasks || 0) > 0 ? '#ef4444' : 'var(--text-primary)', highlight: (stats?.overdue_tasks || 0) > 0 },
          { label: 'AI Drafts', value: stats?.pending_drafts ?? 0, color: '#8b5cf6' },
        ].map((item, idx) => (
          <div
            key={idx}
            style={{
              background: 'var(--bg-tertiary)',
              border: item.highlight ? '1px solid currentColor' : '1px solid var(--border-subtle)',
              borderRadius: '8px',
              padding: '6px 10px',
              display: 'flex',
              alignItems: 'baseline',
              justifyContent: 'space-between',
              transition: 'background 0.15s ease'
            }}
          >
            <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 500 }}>{item.label}</span>
            <span style={{ fontSize: '15px', fontWeight: 700, color: item.color }}>{item.value}</span>
          </div>
        ))}
      </div>
    </header>
  );
};
