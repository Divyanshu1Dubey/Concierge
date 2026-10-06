const API_BASE = '/api/admin';

export function getToken(): string | null {
  return localStorage.getItem('fd_jwt');
}

export function setToken(token: string): void {
  localStorage.setItem('fd_jwt', token);
}

export function removeToken(): void {
  localStorage.removeItem('fd_jwt');
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    'Accept': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  if (options.body && typeof options.body === 'string' && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (res.status === 401) {
    removeToken();
    window.dispatchEvent(new Event('auth:unauthorized'));
    throw new Error('Unauthorized');
  }

  if (!res.ok) {
    let errDetail = res.statusText;
    try {
      const errJson = await res.json();
      errDetail = errJson.detail || errJson.message || res.statusText;
    } catch {
      // ignore
    }
    throw new Error(errDetail);
  }

  return res.json();
}

export const api = {
  // Auth
  login: async (tenant_slug: string, email: string, password: string) => {
    return request<{ access_token: string; token_type: string }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ tenant_slug, email, password }),
    });
  },

  // Front Desk Dashboard
  getDashboard: async () => {
    return request<import('../types').DashboardStats>('/fd/dashboard');
  },

  // Leads
  getLeads: async (params: { limit?: number; status?: string; intent?: string; urgency?: string }) => {
    const qs = new URLSearchParams();
    if (params.limit) qs.set('limit', String(params.limit));
    if (params.status) qs.set('status', params.status);
    if (params.intent) qs.set('intent', params.intent);
    if (params.urgency) qs.set('urgency', params.urgency);
    return request<{ leads: import('../types').Lead[]; intents: string[] }>(`/fd/leads?${qs.toString()}`);
  },

  getLead: async (id: number) => {
    return request<import('../types').Lead>(`/fd/leads/${id}`);
  },

  updateLeadStatus: async (id: number, status: string) => {
    return request<import('../types').Lead>(`/fd/leads/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    });
  },

  resendEmail: async (leadId: number) => {
    return request<{ status: string }>(`/fd/leads/${leadId}/resend-email`, {
      method: 'POST',
    });
  },

  retryNotify: async (leadId: number) => {
    return request<{ status: string }>(`/fd/leads/${leadId}/retry-notify`, {
      method: 'POST',
    });
  },

  replyToLead: async (leadId: number, body: string) => {
    return request<{ status: string }>(`/fd/leads/${leadId}/reply`, {
      method: 'POST',
      body: JSON.stringify({ body }),
    });
  },

  // AI Actions
  performAiAction: async (leadId: number, action: string, instruction?: string) => {
    return request<{ result: string }>(`/fd/ai/action`, {
      method: 'POST',
      body: JSON.stringify({ lead_id: leadId, action, instruction }),
    });
  },

  // Messages
  getConversationMessages: async (convId: string) => {
    return request<{ messages: import('../types').Message[] }>(`/fd/conversations/${convId}/messages`);
  },

  // Notes
  getNotes: async (leadId?: number) => {
    const qs = leadId ? `?lead_id=${leadId}` : '';
    return request<{ notes: import('../types').Note[] }>(`/fd/notes${qs}`);
  },

  createNote: async (leadId: number, note: string) => {
    return request<import('../types').Note>('/fd/notes', {
      method: 'POST',
      body: JSON.stringify({ lead_id: leadId, note }),
    });
  },

  // Tasks
  getTasks: async () => {
    return request<{ tasks: import('../types').Task[] }>('/fd/tasks');
  },

  createTask: async (data: { lead_id?: number; title: string; priority: string; due_at?: string | null }) => {
    return request<import('../types').Task>('/fd/tasks', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  completeTask: async (id: number) => {
    return request<{ status: string }>(`/fd/tasks/${id}/complete`, {
      method: 'POST',
    });
  },

  // Drafts
  getDrafts: async (leadId: number) => {
    return request<{ drafts: import('../types').Draft[] }>(`/fd/drafts?lead_id=${leadId}`);
  },
};
