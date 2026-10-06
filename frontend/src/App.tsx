import React, { useState, useEffect, useCallback, useRef } from 'react';
import { api, getToken, removeToken } from './services/api';
import { playNotificationChime } from './services/audio';
import type { Lead, Message, Note, Task, DashboardStats, CategoryFilter } from './types';
import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import { ConversationView } from './components/ConversationView';
import { PatientContextPanel } from './components/PatientContextPanel';
import { NewNoteModal } from './components/NewNoteModal';
import { NewTaskModal } from './components/NewTaskModal';
import { LoginModal } from './components/LoginModal';

export const App: React.FC = () => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(!!getToken());
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    const saved = localStorage.getItem('fd_theme');
    if (saved === 'dark' || saved === 'light') return saved;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });
  const [soundEnabled, setSoundEnabled] = useState<boolean>(() => {
    return localStorage.getItem('fd_sound') === 'true';
  });

  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [availableIntents, setAvailableIntents] = useState<string[]>([]);
  const [category, setCategory] = useState<CategoryFilter>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [intentFilter, setIntentFilter] = useState('');
  const [activeLeadId, setActiveLeadId] = useState<number | null>(null);
  const [activeLead, setActiveLead] = useState<Lead | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [notes, setNotes] = useState<Note[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);

  const [isNoteModalOpen, setIsNoteModalOpen] = useState(false);
  const [isTaskModalOpen, setIsTaskModalOpen] = useState(false);
  const [isLoadingLeads, setIsLoadingLeads] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const prevNewLeadsCountRef = useRef<number | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => {
      setToastMessage((cur) => (cur === msg ? null : cur));
    }, 3000);
  };

  // Sync theme attribute
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('fd_theme', theme);
  }, [theme]);

  // Sync sound setting
  const toggleSound = () => {
    const next = !soundEnabled;
    setSoundEnabled(next);
    localStorage.setItem('fd_sound', String(next));
    showToast(next ? '🔔 Sound chime enabled' : '🔕 Sound alerts muted');
    if (next) playNotificationChime();
  };

  const toggleTheme = () => {
    setTheme((t) => (t === 'dark' ? 'light' : 'dark'));
  };

  // Listen to unauthorized event
  useEffect(() => {
    const handleUnauth = () => setIsAuthenticated(false);
    window.addEventListener('auth:unauthorized', handleUnauth);
    return () => window.removeEventListener('auth:unauthorized', handleUnauth);
  }, []);

  // Fetch Dashboard Stats
  const loadStats = useCallback(async () => {
    if (!isAuthenticated) return;
    try {
      const data = await api.getDashboard();
      setStats(data);

      if (prevNewLeadsCountRef.current !== null && data.new_leads > prevNewLeadsCountRef.current && soundEnabled) {
        playNotificationChime();
      }
      prevNewLeadsCountRef.current = data.new_leads;
    } catch {
      // ignore
    }
  }, [isAuthenticated, soundEnabled]);

  // Fetch Leads
  const loadLeads = useCallback(async () => {
    if (!isAuthenticated) return;
    setIsLoadingLeads(true);
    try {
      const params: { limit?: number; status?: string; intent?: string; urgency?: string } = { limit: 50 };
      if (category === 'new') params.status = 'new';
      else if (category === 'waiting') params.status = 'contacted';
      else if (category === 'urgent') params.urgency = 'urgent';
      else if (category === 'appointment') params.intent = 'appointment_request';

      if (category === 'all') {
        if (statusFilter) params.status = statusFilter;
        if (intentFilter) params.intent = intentFilter;
      }

      const res = await api.getLeads(params);
      setLeads(res.leads || []);
      if (res.intents && res.intents.length > 0) {
        setAvailableIntents(res.intents);
      }
    } catch {
      // ignore
    } finally {
      setIsLoadingLeads(false);
    }
  }, [isAuthenticated, category, statusFilter, intentFilter]);

  // Fetch Active Lead Details, Messages, Notes, Tasks
  const loadLeadDetails = useCallback(async (id: number) => {
    try {
      const lead = await api.getLead(id);
      setActiveLead(lead);

      if (lead.conversation_id) {
        const msgRes = await api.getConversationMessages(lead.conversation_id);
        setMessages(msgRes.messages || []);
      } else {
        setMessages([]);
      }

      const noteRes = await api.getNotes(id);
      setNotes(noteRes.notes || []);

      const taskRes = await api.getTasks();
      setTasks(taskRes.tasks || []);
    } catch {
      // ignore
    }
  }, []);

  // On activeLeadId change
  useEffect(() => {
    if (activeLeadId) {
      loadLeadDetails(activeLeadId);
    } else {
      setActiveLead(null);
      setMessages([]);
      setNotes([]);
    }
  }, [activeLeadId, loadLeadDetails]);

  // Initial and category-based load
  useEffect(() => {
    if (isAuthenticated) {
      loadStats();
      loadLeads();
    }
  }, [isAuthenticated, loadStats, loadLeads]);

  // Polling loop
  useEffect(() => {
    if (!isAuthenticated) return;
    const interval = setInterval(() => {
      loadStats();
      loadLeads();
      if (activeLeadId) {
        loadLeadDetails(activeLeadId);
      }
    }, 15000);
    return () => clearInterval(interval);
  }, [isAuthenticated, loadStats, loadLeads, activeLeadId, loadLeadDetails]);

  // Actions
  const handleRefresh = async () => {
    setIsRefreshing(true);
    await Promise.all([loadStats(), loadLeads()]);
    if (activeLeadId) await loadLeadDetails(activeLeadId);
    setIsRefreshing(false);
    showToast('Data refreshed');
  };

  const handleLogout = () => {
    removeToken();
    setIsAuthenticated(false);
  };

  const handleUpdateStatus = async (newStatus: string) => {
    if (!activeLead) return;
    try {
      const updated = await api.updateLeadStatus(activeLead.id, newStatus);
      setActiveLead(updated);
      showToast(`Status updated to ${newStatus}`);
      loadLeads();
      loadStats();
    } catch {
      showToast('Failed to update status');
    }
  };

  const handleResendEmail = async () => {
    if (!activeLead) return;
    try {
      await api.resendEmail(activeLead.id);
      showToast('Notification email resent');
    } catch {
      showToast('Failed to resend email');
    }
  };

  const handleRetryNotify = async () => {
    if (!activeLead) return;
    try {
      await api.retryNotify(activeLead.id);
      showToast('Notification retry queued');
    } catch {
      showToast('Failed to retry notify');
    }
  };

  const handleSendReply = async (body: string) => {
    if (!activeLead) return;
    try {
      await api.replyToLead(activeLead.id, body);
      showToast('Reply dispatched');
      loadLeadDetails(activeLead.id);
    } catch {
      showToast('Failed to send reply');
    }
  };

  const handleAiAction = async (action: string, instruction?: string): Promise<string> => {
    if (!activeLead) return '';
    try {
      const res = await api.performAiAction(activeLead.id, action, instruction);
      return res.result;
    } catch {
      showToast('AI assistance error');
      return 'Unable to generate recommendation at this moment.';
    }
  };

  const handleSaveNote = async (text: string) => {
    if (!activeLead) return;
    try {
      await api.createNote(activeLead.id, text);
      showToast('Internal note saved');
      loadLeadDetails(activeLead.id);
    } catch {
      showToast('Failed to save note');
    }
  };

  const handleSaveTask = async (data: { title: string; priority: string; due_at?: string }) => {
    try {
      await api.createTask({
        lead_id: activeLead?.id,
        title: data.title,
        priority: data.priority,
        due_at: data.due_at,
      });
      showToast('Task created');
      if (activeLead) loadLeadDetails(activeLead.id);
      loadStats();
    } catch {
      showToast('Failed to create task');
    }
  };

  const handleCompleteTask = async (taskId: number) => {
    try {
      await api.completeTask(taskId);
      showToast('Task marked complete');
      if (activeLead) loadLeadDetails(activeLead.id);
      loadStats();
    } catch {
      showToast('Failed to complete task');
    }
  };

  const handleCopySummary = () => {
    if (!activeLead) return;
    const summary = [
      `Patient Lead #${activeLead.id}`,
      `Name: ${activeLead.name || 'Anonymous'}`,
      `Email: ${activeLead.email || 'N/A'}`,
      `Phone: ${activeLead.phone || 'N/A'}`,
      `Service: ${activeLead.service || 'N/A'}`,
      `Intent: ${activeLead.intent || 'N/A'}`,
      `Status: ${activeLead.status || 'new'}`,
      `Preferred: ${[activeLead.preferred_date, activeLead.preferred_time].filter(Boolean).join(' ')}`,
      `Message: ${activeLead.message || 'N/A'}`,
    ].join('\n');

    if (navigator.clipboard) {
      navigator.clipboard.writeText(summary).then(() => {
        showToast('📋 Patient summary copied to clipboard!');
      });
    }
  };

  // Filter leads by search query locally
  const filteredLeads = leads.filter((l) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      (l.name && l.name.toLowerCase().includes(q)) ||
      (l.email && l.email.toLowerCase().includes(q)) ||
      (l.phone && l.phone.toLowerCase().includes(q)) ||
      (l.service && l.service.toLowerCase().includes(q)) ||
      (l.intent && l.intent.toLowerCase().includes(q)) ||
      (l.message && l.message.toLowerCase().includes(q))
    );
  });

  if (!isAuthenticated) {
    return <LoginModal onSuccess={() => setIsAuthenticated(true)} />;
  }

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <Header
        stats={stats}
        theme={theme}
        onToggleTheme={toggleTheme}
        soundEnabled={soundEnabled}
        onToggleSound={toggleSound}
        onRefresh={handleRefresh}
        onLogout={handleLogout}
        isRefreshing={isRefreshing}
      />

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <Sidebar
          category={category}
          onSelectCategory={(cat) => {
            setCategory(cat);
          }}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          statusFilter={statusFilter}
          onStatusFilterChange={setStatusFilter}
          intentFilter={intentFilter}
          onIntentFilterChange={setIntentFilter}
          availableIntents={availableIntents}
          leads={filteredLeads}
          activeLeadId={activeLeadId}
          onSelectLead={setActiveLeadId}
          isLoading={isLoadingLeads}
        />

        <ConversationView
          lead={activeLead}
          messages={messages}
          notes={notes}
          onUpdateStatus={handleUpdateStatus}
          onResendEmail={handleResendEmail}
          onRetryNotify={handleRetryNotify}
          onSendReply={handleSendReply}
          onAiAction={handleAiAction}
          onOpenNoteModal={() => setIsNoteModalOpen(true)}
          onOpenTaskModal={() => setIsTaskModalOpen(true)}
          onCopySummary={handleCopySummary}
        />

        <PatientContextPanel
          lead={activeLead}
          notes={notes}
          tasks={tasks}
          onCompleteTask={handleCompleteTask}
          onOpenNoteModal={() => setIsNoteModalOpen(true)}
          onOpenTaskModal={() => setIsTaskModalOpen(true)}
        />
      </div>

      {/* Note Modal */}
      <NewNoteModal
        isOpen={isNoteModalOpen}
        onClose={() => setIsNoteModalOpen(false)}
        onSave={handleSaveNote}
      />

      {/* Task Modal */}
      <NewTaskModal
        isOpen={isTaskModalOpen}
        onClose={() => setIsTaskModalOpen(false)}
        onSave={handleSaveTask}
      />

      {/* Toast Alert */}
      {toastMessage && (
        <div style={{
          position: 'fixed',
          bottom: '24px',
          right: '24px',
          background: 'var(--brand-green)',
          color: '#ffffff',
          padding: '10px 18px',
          borderRadius: '10px',
          fontSize: '13px',
          fontWeight: 500,
          boxShadow: 'var(--shadow-glass)',
          zIndex: 1000,
          animation: 'fadeIn 0.2s ease-out forwards',
        }}>
          {toastMessage}
        </div>
      )}
    </div>
  );
};

export default App;
