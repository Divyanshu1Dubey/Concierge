import apiClient from '@/utils/api';

// ─── Auth ─────────────────────────────────────────────────────────────────────

export const authApi = {
  me: () => apiClient.get('/auth/me/').then((r) => r.data),
  login: (credentials: { email: string; password: string }) =>
    apiClient.post('/auth/login/', credentials).then((r) => r.data),
  logout: () => apiClient.post('/auth/logout/').then((r) => r.data),
  google: () => {
    const isRemote = typeof window !== 'undefined' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
    const apiBase = isRemote ? window.location.origin : (import.meta.env.VITE_API_URL?.replace('/api', '') || 'http://localhost:8000');
    window.location.href = `${apiBase}/api/auth/google/`;
    return Promise.resolve(null);
  },
};

// ─── Practice & Tenant Administration ─────────────────────────────────────────

export const practicesApi = {
  getTenant: () => apiClient.get('/practices/').then((r) => r.data),
  updateTenant: (data: Record<string, unknown>) => apiClient.put('/practices/', data).then((r) => r.data),
  metrics: () => apiClient.get('/practices/metrics/').then((r) => r.data),
  regenerateKey: () => apiClient.post('/practices/key/regenerate/').then((r) => r.data),
  domains: () => apiClient.get('/practices/domains/').then((r) => r.data),
  addDomain: (hostname: string) => apiClient.post('/practices/domains/', { hostname }).then((r) => r.data),
  deleteDomain: (id: number) => apiClient.delete(`/practices/domains/${id}/`).then((r) => r.data),
  bookingRules: () => apiClient.get('/practices/booking-rules/').then((r) => r.data),
  updateBookingRules: (data: Record<string, unknown>) => apiClient.put('/practices/booking-rules/', data).then((r) => r.data),
  settings: () => apiClient.get('/practices/settings/').then((r) => r.data),
  updateSettings: (data: Record<string, unknown>) => apiClient.put('/practices/settings/', data).then((r) => r.data),
  emailConfig: () => apiClient.get('/practices/email-config/').then((r) => r.data),
  updateEmailConfig: (data: Record<string, unknown>) => apiClient.put('/practices/email-config/', data).then((r) => r.data),
  testEmail: () => apiClient.post('/practices/email-config/test/').then((r) => r.data),
  templates: () => apiClient.get('/practices/templates/').then((r) => r.data),
  updateTemplate: (id: number, data: Record<string, unknown>) => apiClient.put(`/practices/templates/${id}/`, data).then((r) => r.data),
  team: () => apiClient.get('/practices/team/').then((r) => r.data),
  inviteMember: (data: { email: string; role: string; first_name?: string; last_name?: string }) =>
    apiClient.post('/practices/team/', data).then((r) => r.data),
  updateMemberRole: (id: string, role: string) => apiClient.put(`/practices/team/${id}/`, { role }).then((r) => r.data),
  removeMember: (id: string) => apiClient.delete(`/practices/team/${id}/`).then((r) => r.data),
  auditLogs: () => apiClient.get('/practices/audit-logs/').then((r) => r.data),
  wordpressUrl: '/api/practices/integration/wordpress/',
  exportUrl: (type: 'leads' | 'conversations') => `/api/practices/export/${type}/`,
  list: () => apiClient.get('/practices/').then((r) => r.data),
  get: () => apiClient.get('/practices/').then((r) => r.data),
  getAll: () => apiClient.get('/practices/').then((r) => r.data),
  listAll: () => apiClient.get('/practices/all/').then((r) => r.data),
  createPractice: (data: Record<string, unknown>) => apiClient.post('/practices/all/', data).then((r) => r.data),
  toggleStatus: (id: number | string) => apiClient.post(`/practices/${id}/toggle-status/`).then((r) => r.data),
  getPracticeUsers: (practiceId: number | string) =>
    apiClient.get(`/practices/${practiceId}/users/`).then((r) => r.data),
  addPracticeUser: (
    practiceId: number | string,
    data: {
      email: string;
      password: string;
      role: string;
      first_name?: string;
      last_name?: string;
      phone?: string;
    }
  ) => apiClient.post(`/practices/${practiceId}/users/`, data).then((r) => r.data),
  practiceUserAction: (
    practiceId: number | string,
    userId: number | string,
    action: string,
    data?: Record<string, unknown>
  ) => apiClient.post(`/practices/${practiceId}/users/${userId}/action/`, { action, ...data }).then((r) => r.data),
  deletePracticeUser: (practiceId: number | string, userId: number | string) =>
    apiClient.delete(`/practices/${practiceId}/users/${userId}/action/`).then((r) => r.data),
  getPracticeIntegration: (practiceId: number | string) =>
    apiClient.get(`/practices/${practiceId}/integration/`).then((r) => r.data),
  getWordPressPluginUrl: (practiceId: number | string) =>
    `/api/practices/${practiceId}/integration/wordpress/`,
};

// ─── Users ────────────────────────────────────────────────────────────────────

export const usersApi = {
  list: () => apiClient.get('/practices/team/').then((r) => r.data),
};

// ─── Conversations ────────────────────────────────────────────────────────────

export const conversationsApi = {
  list: (params?: { status?: string; lead_status?: string; urgency?: string; search?: string }) =>
    apiClient.get('/conversations/', { params }).then((r) => r.data),
  get: (id: string) =>
    apiClient.get(`/conversations/${id}/`).then((r) => r.data),
  messages: (id: string) =>
    apiClient.get(`/conversations/${id}/messages/`).then((r) => r.data),
  stats: () =>
    apiClient.get('/conversations/stats/').then((r) => r.data),
  close: (id: string) =>
    apiClient.post(`/conversations/${id}/close/`).then((r) => r.data),
  escalate: (id: string) =>
    apiClient.post(`/conversations/${id}/escalate/`).then((r) => r.data),
};

// ─── Appointment Requests & Front Desk Command Center ─────────────────────────

export const appointmentRequestsApi = {
  list: (params?: { status?: string; intent?: string; urgency?: string; search?: string }) =>
    apiClient.get('/requests/', { params }).then((r) => r.data),
  get: (id: string) =>
    apiClient.get(`/requests/${id}/`).then((r) => r.data),
  aiDraft: (id: string, data: { action: string; current_text?: string; target_language?: string }) =>
    apiClient.post(`/requests/${id}/ai-draft/`, data).then((r) => r.data),
  saveDraft: (id: string, draft: string) =>
    apiClient.post(`/requests/${id}/save-draft/`, { draft }).then((r) => r.data),
  sendReply: (id: string, data: { to_email: string; subject: string; body: string; reply_to?: string; notes?: string }) =>
    apiClient.post(`/requests/${id}/send-reply/`, data).then((r) => r.data),
  respond: (id: string, data: { offered_date?: string; offered_time?: string; notes?: string; generated_response?: string; to_email?: string; subject?: string; body?: string }) =>
    apiClient.post(`/requests/${id}/respond/`, {
      to_email: data.to_email,
      subject: data.subject || 'Appointment Coordination',
      body: data.body || data.generated_response || '',
      notes: data.notes || '',
    }).then((r) => r.data),
  addNote: (id: string, text: string) =>
    apiClient.post(`/requests/${id}/notes/`, { text }).then((r) => r.data),
  updateStatus: (id: string, data: { status?: string; priority?: string; assigned_to?: string }) =>
    apiClient.post(`/requests/${id}/status/`, data).then((r) => r.data),
  stats: () => apiClient.get('/requests/stats/').then((r) => r.data),
};

// Aliases
export const requestsApi = appointmentRequestsApi;

// ─── Patients & Leads ─────────────────────────────────────────────────────────

export const patientsApi = {
  list: (params?: { search?: string }) =>
    apiClient.get('/requests/', { params }).then((r) => r.data),
  getAll: (params?: { search?: string }) =>
    apiClient.get('/requests/', { params }).then((r) => r.data),
  get: (id: string) =>
    apiClient.get(`/requests/${id}/`).then((r) => r.data),
  create: (data: Record<string, unknown>) =>
    apiClient.post('/requests/', data).then((r) => r.data),
};

export const leadsApi = {
  list: (params?: { search?: string }) =>
    apiClient.get('/requests/', { params }).then((r) => r.data),
  getAll: (params?: { search?: string }) =>
    apiClient.get('/requests/', { params }).then((r) => r.data),
};

// ─── Booking Rules Alias ──────────────────────────────────────────────────────

export const bookingApi = {
  getRules: () =>
    apiClient.get('/practices/booking-rules/').then((r) => r.data),
  updateRules: (_practiceId: unknown, data: Record<string, unknown>) =>
    apiClient.put('/practices/booking-rules/', data).then((r) => r.data),
};

// ─── Knowledge & Email ────────────────────────────────────────────────────────

export const knowledgeApi = {
  list: () => apiClient.get('/practices/templates/').then((r) => r.data),
  getAll: () => apiClient.get('/practices/templates/').then((r) => r.data),
};

export const emailsApi = {
  list: (params?: { thread?: string; direction?: string }) =>
    apiClient.get('/emails/', { params }).then((r) => r.data),
  send: (data: {
    to_email: string;
    subject: string;
    body: string;
    thread?: string;
  }) => apiClient.post('/emails/send/', data).then((r) => r.data),
  threads: (params?: { patient_email?: string }) =>
    apiClient.get('/emails/threads/', { params }).then((r) => r.data),
};

// ─── Chat (Public Widget & Hosted Concierge) ──────────────────────────────────

export const chatApi = {
  send: (message: string, conversationId?: string, clientKey?: string) =>
    apiClient.post('/conversations/chat/', {
      message,
      conversation_id: conversationId,
      client_key: clientKey
    }).then((r) => r.data),
  config: (clientKey: string) =>
    apiClient.get('/conversations/widget/config/', { params: { client_key: clientKey } }).then((r) => r.data),
  hostedConfig: (slug: string) =>
    apiClient.get(`/conversations/concierge/${slug}/`).then((r) => r.data),
};

